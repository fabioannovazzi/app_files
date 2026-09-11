"""Exercise the opinion lifecycle with synthetic, already-authored reviews."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins/vera/scripts/adversarial_opinion.py"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def opinion() -> Any:
    return _load("test_vera_adversarial_module", SCRIPT)


@pytest.fixture(scope="module")
def examples() -> Any:
    return _load(
        "test_vera_adversarial_review_examples",
        ROOT / "tests/plugins/test_vera_validated_answer_pipeline.py",
    )


def _write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _phase(
    path: Path,
    examples: Any,
    *,
    opposing: bool = False,
    generation_route: str = "codex_direct",
) -> None:
    path.mkdir(exist_ok=True)
    if not (path / "answer_contract.json").is_file():
        contract = examples._answer_contract(generation_route, "legal opinion")
        contract["adversarial_policy"] = "required"
        _write(path / "answer_contract.json", contract)
    review = examples._claims_review("legal opinion")
    if opposing:
        # Separate fictional authority; the test verifies packaging, not law.
        review = json.loads(json.dumps(review).replace("30 days", "20 days"))
    _write(path / "claims_review.json", review)
    document = review["validated_document"]
    (path / "validated_document.md").write_text(document + "\n")
    _write(
        path / "document_inventory.json", {"character_count": len(document), "urls": []}
    )
    passage = (
        "The response must be filed within 20 days."
        if opposing
        else "The response must be filed within 30 days."
    )
    _write(
        path / "source_inventory.json",
        {
            "sources": [
                {"source_id": "source-001", "status": "available", "excerpt": passage}
            ]
        },
    )


def _assessment(
    root: Path, *, outcome: str = "credible_counterposition"
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "language": "it",
        "brief_sha256": hashlib.sha256(
            (root / "adversarial_brief.json").read_bytes()
        ).hexdigest(),
        "outcome": outcome,
        "rationale": "Synthetic model-authored assessment for lifecycle testing.",
        "search_record": [
            {
                "question": "Which fictional deadline applies?",
                "search_or_source": "Reviewed fictional rule B",
                "finding": "Rule B contains a different deadline.",
                "source_refs": ["source-001"],
            }
        ],
        "comparison": {
            "original_conclusion": "The original applies fictional rule A.",
            "opposing_conclusion": "The opposing reading applies fictional rule B.",
            "decisive_issues": ["Applicability of rule B."],
            "evidence_gaps": [],
            "professional_choices": ["Assess applicability."],
            "original_position_effect": "unchanged",
            "effect_analysis": "The original remains a supported position.",
        },
        "comparison_review": {
            "status": "reviewed",
            "analysis": "Both reviewed positions were compared.",
        },
    }


def _case(root: Path, opinion: Any, examples: Any) -> dict[str, Any]:
    _phase(root / "position", examples)
    opinion.prepare_adversarial(root)
    _phase(root / "adversarial", examples, opposing=True)
    assessment = _assessment(root)
    _write(root / "adversarial_assessment.json", assessment)
    return assessment


def test_supported_original_gets_separately_reviewed_opposing_delivery(
    tmp_path: Path, opinion: Any, examples: Any
) -> None:
    _case(tmp_path, opinion, examples)

    delivery = opinion.package_opinion(tmp_path)

    assert delivery["status"] == "complete"
    assert delivery["original_validation_readiness"] == "reviewed_answer_ready"
    assert delivery["adversarial_validation_readiness"] == "reviewed_answer_ready"
    assert delivery["adversarial_outcome"] == "credible_counterposition"
    assert "opinion_comparison.md" in delivery["files"]
    assert (
        "Parere e posizione contraria" in (tmp_path / "opinion_package.md").read_text()
    )
    assert opinion.verify_opinion(tmp_path) == delivery


@pytest.mark.parametrize(
    "outcome", ["no_substantial_counterposition", "evidence_limited"]
)
def test_bounded_negative_or_limited_result_is_preserved(
    tmp_path: Path, opinion: Any, examples: Any, outcome: str
) -> None:
    assessment = _case(tmp_path, opinion, examples)
    assessment["outcome"] = outcome
    assessment["rationale"] = (
        "The examined fictional evidence does not resolve applicability."
    )
    assessment["comparison"][
        "opposing_conclusion"
    ] = "No substantial opposing case established within the examined scope."
    _write(tmp_path / "adversarial_assessment.json", assessment)

    delivery = opinion.package_opinion(tmp_path)

    assert delivery["adversarial_outcome"] == outcome
    assert delivery["status"] == (
        "evidence_limited" if outcome == "evidence_limited" else "complete"
    )
    assert (
        "No substantial opposing case"
        in (tmp_path / "opinion_comparison.md").read_text()
    )


@pytest.mark.parametrize(
    "outcome,revision,expected",
    [
        ("not_reliable", "required", "not_reliable"),
        ("evidence_limited", "not_required", "evidence_limited"),
        (
            "professional_review_required",
            "professional_review_required",
            "professional_review_required",
        ),
    ],
)
def test_preparation_does_not_gate_on_original_validation_outcome(
    tmp_path: Path,
    opinion: Any,
    examples: Any,
    outcome: str,
    revision: str,
    expected: str,
) -> None:
    _phase(tmp_path / "position", examples)
    path = tmp_path / "position/claims_review.json"
    review = json.loads(path.read_text())
    review["overall_assessment"]["outcome"] = outcome
    review["document_revision"]["status"] = revision
    _write(path, review)

    brief = opinion.prepare_adversarial(tmp_path)

    assert brief["original_validation_readiness"] == expected
    assert (tmp_path / "adversarial/answer_contract.json").is_file()


def test_original_validation_alone_cannot_complete_opinion_journey(
    tmp_path: Path, opinion: Any, examples: Any
) -> None:
    _phase(tmp_path / "position", examples)
    opinion.prepare_adversarial(tmp_path)

    with pytest.raises(ValueError, match="Missing adversarial/"):
        opinion.package_opinion(tmp_path)


def test_stale_original_cannot_be_paired_with_prior_counter_opinion(
    tmp_path: Path, opinion: Any, examples: Any
) -> None:
    _case(tmp_path, opinion, examples)
    (tmp_path / "position/validated_document.md").write_text(
        "Changed original position."
    )

    with pytest.raises(ValueError, match="Original position changed"):
        opinion.package_opinion(tmp_path)


@pytest.mark.parametrize(
    "field", ["jurisdiction", "output_language", "evidence_display"]
)
def test_opposing_contract_cannot_change_original_basis(
    tmp_path: Path, opinion: Any, examples: Any, field: str
) -> None:
    _case(tmp_path, opinion, examples)
    path = tmp_path / "adversarial/answer_contract.json"
    contract = json.loads(path.read_text())
    contract[field] = "Changed basis"
    _write(path, contract)

    with pytest.raises(ValueError, match="bound jurisdiction"):
        opinion.package_opinion(tmp_path)


def test_missing_counter_source_reference_is_rejected(
    tmp_path: Path, opinion: Any, examples: Any
) -> None:
    _case(tmp_path, opinion, examples)
    path = tmp_path / "adversarial/source_inventory.json"
    _write(path, {"sources": []})

    with pytest.raises(ValueError, match="source reference"):
        opinion.package_opinion(tmp_path)


@pytest.mark.parametrize(
    "filename",
    [
        "opinion_comparison.md",
        "adversarial/validated_document.md",
        "position/claims_review.json",
    ],
)
def test_reopen_rejects_changed_delivered_artifacts(
    tmp_path: Path, opinion: Any, examples: Any, filename: str
) -> None:
    _case(tmp_path, opinion, examples)
    opinion.package_opinion(tmp_path)
    (tmp_path / filename).write_text("Unreviewed edit")

    with pytest.raises(ValueError, match="changed opinion artifact"):
        opinion.verify_opinion(tmp_path)


def test_reprepare_invalidates_previously_completed_delivery(
    tmp_path: Path, opinion: Any, examples: Any
) -> None:
    _case(tmp_path, opinion, examples)
    opinion.package_opinion(tmp_path)
    opinion.prepare_adversarial(tmp_path)

    with pytest.raises(ValueError, match="last preparation"):
        opinion.verify_opinion(tmp_path)


def test_new_counter_evidence_invalidates_delivery(
    tmp_path: Path, opinion: Any, examples: Any
) -> None:
    _case(tmp_path, opinion, examples)
    opinion.package_opinion(tmp_path)
    (tmp_path / "adversarial/new-evidence.txt").write_text("New material evidence")

    with pytest.raises(ValueError, match="Opinion phase changed"):
        opinion.verify_opinion(tmp_path)


def test_counter_opinion_cannot_be_replaced_without_review(
    tmp_path: Path, opinion: Any, examples: Any
) -> None:
    _case(tmp_path, opinion, examples)
    (tmp_path / "adversarial/validated_document.md").write_text(
        "A different counter-opinion"
    )

    with pytest.raises(ValueError, match="reviewed text differs"):
        opinion.package_opinion(tmp_path)


@pytest.mark.parametrize(
    "effect", ["revision_required", "professional_review_required"]
)
def test_comparison_objection_preserves_required_followup(
    tmp_path: Path, opinion: Any, examples: Any, effect: str
) -> None:
    assessment = _case(tmp_path, opinion, examples)
    assessment["comparison"]["original_position_effect"] = effect
    _write(tmp_path / "adversarial_assessment.json", assessment)

    delivery = opinion.package_opinion(tmp_path)

    assert delivery["status"] == effect
    assert delivery["original_validation_readiness"] == "reviewed_answer_ready"


def test_source_capture_cannot_escape_run(
    tmp_path: Path, opinion: Any, examples: Any
) -> None:
    _case(tmp_path, opinion, examples)
    source_path = tmp_path / "adversarial/source_inventory.json"
    sources = json.loads(source_path.read_text())
    sources["sources"][0]["captured_text_path"] = "../../other-case.txt"
    _write(source_path, sources)

    with pytest.raises(ValueError, match="Invalid artifact path"):
        opinion.package_opinion(tmp_path)


def test_symlink_evidence_is_rejected(
    tmp_path: Path, opinion: Any, examples: Any
) -> None:
    _case(tmp_path, opinion, examples)
    (tmp_path / "adversarial/source-copy.txt").symlink_to(
        tmp_path / "position/validated_document.md"
    )

    with pytest.raises(ValueError, match="Symlink artifact rejected"):
        opinion.package_opinion(tmp_path)


def test_cli_rejects_unbound_client_context(tmp_path: Path) -> None:
    context = tmp_path / "context.json"
    _write(context, {})

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "prepare",
            "--output-dir",
            str(tmp_path),
            "--client-engagement",
            str(context),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert not (tmp_path / "adversarial_brief.json").exists()


@pytest.mark.parametrize(
    "generation_route",
    [
        "codex_direct",
        "deep_research_plugin",
        "chatgpt_deep_research",
        "external_document",
    ],
)
def test_counter_contract_uses_current_host_without_repeating_original_route(
    tmp_path: Path, opinion: Any, examples: Any, generation_route: str
) -> None:
    _phase(tmp_path / "position", examples, generation_route=generation_route)
    original = (tmp_path / "position/answer_contract.json").read_bytes()

    brief = opinion.prepare_adversarial(tmp_path)

    assert "adversarial_policy" not in brief["counter_contract"]
    assert brief["counter_contract"]["generation_route"] == "codex_direct"
    assert brief["counter_contract"]["validation_scope"] == "all_material_claims"
    assert (tmp_path / "position/answer_contract.json").read_bytes() == original


@pytest.fixture
def completed_case(tmp_path: Path, opinion: Any, examples: Any) -> tuple[Path, Path]:
    """Seal a real Studio Archive run so reopening tests the actual boundary."""
    ledger = _load(
        "adversarial_test_ledger",
        ROOT / "plugins/studio-archive/scripts/client_ledger.py",
    )
    reports = _load("adversarial_test_model_data", ROOT / "tests/model_data_helpers.py")
    client = tmp_path / "Synthetic Client"
    client.mkdir()
    client_id = "client_aaaaaaaaaaaaaaaaaaaaaaaa"
    ledger.create_client_manifest(client, client_id)
    engagement = ledger.create_engagement(
        client, client_id, "Synthetic opinion exercise"
    )
    source = tmp_path / "source.txt"
    source.write_text("Fictional source for lifecycle verification.")
    imported = ledger.import_document(
        client, client_id, engagement["engagement_id"], source, "source"
    )
    prepared = ledger.prepare_run(
        client,
        client_id,
        engagement["engagement_id"],
        "deep-research-validator",
        "adversarial-regression",
        input_ids=[imported["receipt"]["input_id"]],
    )
    run_id = prepared["run"]["run_id"]
    running = ledger.start_run(client, engagement["engagement_id"], run_id)
    output = Path(running["output_dir"])
    _case(output, opinion, examples)
    opinion.package_opinion(output)
    reports.write_no_model_report(output, "deep-research-validator", run_id)
    declarations = [
        {
            "artifact_id": f"artifact_{index:03d}",
            "path": path.relative_to(output).as_posix(),
            "purpose": "Preserve the synthetic opinion review artifact.",
            "audience": "review",
            "media_type": "application/octet-stream",
        }
        for index, path in enumerate(sorted(output.rglob("*")), 1)
        if path.is_file()
    ]
    ledger.finalize_run(client, engagement["engagement_id"], run_id, declarations)
    ledger.complete_run(client, engagement["engagement_id"], run_id)
    return output, Path(running["context"]["context_path"])


def test_cli_reopens_completed_run_without_writing(
    completed_case: tuple[Path, Path],
) -> None:
    output, context = completed_case
    before = (output / "opinion_delivery.json").read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "verify",
            "--output-dir",
            str(output),
            "--client-engagement",
            str(context),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (output / "opinion_delivery.json").read_bytes() == before


@pytest.mark.parametrize("action", ["prepare", "package"])
def test_cli_cannot_mutate_completed_run(
    completed_case: tuple[Path, Path], action: str
) -> None:
    output, context = completed_case
    before = (output / "opinion_progress.json").read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            action,
            "--output-dir",
            str(output),
            "--client-engagement",
            str(context),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "running state" in result.stderr
    assert (output / "opinion_progress.json").read_bytes() == before
