"""Vera must deliver reader-visible evidence, even when the shared audit passes."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.plugins.test_deep_research_validator_plugin import (
    _answer_contract,
    _claim_review,
    _claims_review,
)

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins/vera/scripts/opinion_validation.py"
RULE = "The fictional filing period is thirty days."
AUTHORITY = "https://example.invalid/fictional-act"
LABEL = "Fictional Act, section 4"
CITE = f"[{LABEL}]({AUTHORITY})"
LIMIT = "Its application depends on when the notice was served."


@pytest.fixture
def vera():
    spec = importlib.util.spec_from_file_location("test_vera_opinion_policy", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def records(text, *, claims=None, sources=None, revision="not_required"):
    claim = _claim_review(RULE, cited_passage=RULE)
    return (
        {
            "character_count": len(text),
            "word_count": len(text.split()),
            "urls": [AUTHORITY],
        },
        {
            "sources": (
                sources
                if sources is not None
                else [
                    {
                        "kind": "url",
                        "source_id": "source-001",
                        "url": AUTHORITY,
                        "status": "available",
                        "excerpt": RULE,
                    }
                ]
            )
        },
        _claims_review(
            claims if claims is not None else [claim],
            validated_document=text,
            document_revision_status=revision,
        ),
        _answer_contract(generation_route="codex_direct", document_type="tax opinion"),
    )


def write_position(vera, folder, text, *, docx=False):
    folder.mkdir()
    inputs = records(text)
    paths = []
    for name, data in zip(
        (
            "document_inventory.json",
            "source_inventory.json",
            "review-draft.json",
            "answer_contract.json",
        ),
        inputs,
    ):
        path = folder / name
        path.write_text(json.dumps(data), encoding="utf-8")
        paths.append(path)
    return vera.write_validation_package(
        *paths[:3], folder, answer_contract_path=paths[3], write_docx=docx
    )


@pytest.mark.parametrize(
    "text",
    [
        RULE,
        f"{RULE}\n\nReferences\n{CITE}",
        f"{RULE} A different finding. {CITE}",
        f"{RULE} [{LABEL}](https://example.invalid/different)",
        f"{RULE} [1]({AUTHORITY})",
        f"{RULE}\n\nSource list\n{RULE} {CITE}",
    ],
)
def test_opinion_cannot_be_ready_with_evidence_elsewhere_or_for_another_source(
    vera, text
):
    audit = vera.build_audit(*records(text))
    assert audit["delivery_readiness"] == "blocked"
    assert "material_conclusion_evidence:1" in audit["failed_checks"]


def test_actual_reviewed_opinion_includes_named_source_in_markdown_and_word(
    vera, tmp_path
):
    folder = tmp_path / "opinion"
    text = f"{RULE} {CITE}"
    paths = write_position(vera, folder, text, docx=True)
    assert (folder / "validated_document.md").read_text().strip() == text
    assert (
        json.loads((folder / "validation_audit.json").read_text())["delivery_readiness"]
        == "reviewed_answer_ready"
    )
    with ZipFile(paths["validated_document_docx"]) as archive:
        assert LABEL in archive.read("word/document.xml").decode()
        assert AUTHORITY in archive.read("word/_rels/document.xml.rels").decode()
    vera.verify_opinion(folder)


def test_private_document_can_be_cited_by_title_and_locator(vera):
    claim = _claim_review(RULE, cited_passage=RULE)
    claim["source_checks"][0]["opinion_citation"] = "Engagement letter, clause 5"
    text = f"{RULE} (Engagement letter, clause 5)"
    source = {
        "kind": "file",
        "source_id": "source-001",
        "name": "Engagement letter.pdf",
        "status": "available",
        "excerpt": RULE,
    }
    audit = vera.build_audit(*records(text, claims=[claim], sources=[source]))
    assert audit["delivery_readiness"] == "reviewed_answer_ready"


def test_uncertain_conclusion_requires_its_visible_qualification(vera):
    claim = _claim_review(
        RULE, cited_passage=RULE, judgment_status="professional_judgment_required"
    )
    claim["issues"] = [
        {
            "type": "judgment_dependent",
            "explanation": LIMIT,
            "treatment_action": "professional_review",
            "treatment_status": "professional_review_required",
            "treatment_explanation": "The basis is cited and the remaining judgment is disclosed.",
        }
    ]
    claim["opinion_limit"] = LIMIT
    without = vera.build_audit(
        *records(
            f"{RULE} {CITE}\n\n{LIMIT}",
            claims=[claim],
            revision="professional_review_required",
        )
    )
    with_limit = vera.build_audit(
        *records(
            f"{RULE} {CITE} {LIMIT}",
            claims=[claim],
            revision="professional_review_required",
        )
    )
    assert "material_conclusion_evidence:1" in without["failed_checks"]
    assert "material_conclusion_evidence:1" not in with_limit["failed_checks"]
    assert with_limit["delivery_readiness"] == "professional_review_required"


def test_verify_checks_opposing_document_and_rejects_changed_final_text(vera, tmp_path):
    write_position(vera, tmp_path / "position", f"{RULE} {CITE}")
    write_position(vera, tmp_path / "adversarial", RULE)
    with pytest.raises(ValueError, match="adversarial.*material_conclusion_evidence:1"):
        vera.verify_opinion(tmp_path)
    (tmp_path / "adversarial/validated_document.md").write_text(f"{RULE} {CITE}")
    with pytest.raises(ValueError, match="differs from its reviewed text"):
        vera.verify_opinion(tmp_path)


def test_installed_command_rejects_material_conclusion_with_only_internal_support(
    vera, tmp_path
):
    folder = tmp_path / "opinion"
    write_position(vera, folder, RULE)
    assert (folder / "validated_document.md").read_text().strip() == RULE
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "verify", str(folder)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "material_conclusion_evidence:1" in result.stderr


def test_second_conclusion_cannot_borrow_the_first_source(vera):
    second = "A written extension is possible."
    other = "https://example.invalid/extension"
    claims = [
        _claim_review(RULE, cited_passage=RULE),
        _claim_review(
            second, claim_index=2, source_ref="source-002", cited_passage=second
        ),
    ]
    sources = [
        {
            "source_id": "source-001",
            "url": AUTHORITY,
            "status": "available",
            "excerpt": RULE,
        },
        {
            "source_id": "source-002",
            "url": other,
            "status": "available",
            "excerpt": second,
        },
    ]
    wrong = f"{RULE} {CITE}\n\n{second} {CITE}"
    right = f"{RULE} {CITE}\n\n{second} [Extension, article 2]({other}#article2)"
    assert vera.build_audit(*records(wrong, claims=claims, sources=sources))[
        "failed_checks"
    ] == ["material_conclusion_evidence:2"]
    assert (
        vera.build_audit(*records(right, claims=claims, sources=sources))[
            "delivery_readiness"
        ]
        == "reviewed_answer_ready"
    )


def test_comparison_must_restate_both_cited_positions(vera, tmp_path):
    text = f"{RULE} {CITE}"
    write_position(vera, tmp_path / "position", text)
    write_position(vera, tmp_path / "adversarial", text)
    comparison = tmp_path / "opinion_comparison.md"
    assessment = tmp_path / "adversarial_assessment.json"
    comparison.write_text(text)
    assessment.write_text(
        json.dumps(
            {"comparison": {"original_conclusion": text, "opposing_conclusion": RULE}}
        )
    )
    with pytest.raises(ValueError, match="comparison: cite.*opposing_conclusion"):
        vera.verify_opinion(tmp_path)
    assessment.write_text(
        json.dumps(
            {"comparison": {"original_conclusion": text, "opposing_conclusion": text}}
        )
    )
    vera.verify_opinion(tmp_path)


def test_unsupported_conclusion_can_disclose_an_evidence_gap_without_inventing_a_citation(
    vera,
):
    finding = "The filing date cannot be established."
    limit = "The dated notice was unavailable."
    claim = _claim_review(
        finding,
        support_status="uncertain",
        issues=[
            {
                "type": "missing_source_support",
                "explanation": limit,
                "treatment_action": "state_uncertainty",
                "treatment_status": "applied",
                "treatment_explanation": "The opinion records the missing evidence.",
            }
        ],
    )
    claim["opinion_limit"] = limit
    check = claim["source_checks"][0]
    check.update(
        identity_status="not_assessed",
        authority_relation="uncertain",
        official_text_access="unavailable",
        text_fidelity="not_verified",
        limitations=[limit],
    )
    source = {"source_id": "source-001", "name": "Notice", "status": "unavailable"}
    inputs = records(f"{finding} {limit}", claims=[claim], sources=[source])
    inputs[2]["overall_assessment"].update(
        outcome="evidence_limited", residual_uncertainties=[limit]
    )
    result = vera.build_audit(*inputs)
    assert result["failed_checks"] == []
    assert result["delivery_readiness"] == "evidence_limited"


def test_letter_source_record_does_not_waive_the_final_opinion_check(vera):
    inputs = records(RULE)
    inputs[3]["evidence_display"] = "source_record_only"
    assert vera.build_audit(*inputs)["delivery_readiness"] == "reviewed_answer_ready"
    assert (
        "material_conclusion_evidence:1"
        in vera.build_audit(*inputs, require_opinion=True)["failed_checks"]
    )
