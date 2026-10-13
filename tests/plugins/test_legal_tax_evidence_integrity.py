"""Exercise answer identity and retained source revisions through public helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.plugins.test_deep_research_validator_plugin import (
    _answer_contract,
    _claim_review,
    _claims_review,
    load_script,
)


def _inputs(root: Path, reviewed: str = "The fictional period is 30 days."):
    root.mkdir()
    values = {
        "document_inventory.json": {"character_count": 40, "urls": []},
        "source_inventory.json": {
            "sources": [{"source_id": "source-001", "status": "available"}]
        },
        "claims_review.json": _claims_review(
            [_claim_review("The fictional period is 30 days.")],
            validated_document=reviewed,
        ),
        "answer_contract.json": _answer_contract(generation_route="codex_direct"),
    }
    for name, value in values.items():
        (root / name).write_text(json.dumps(value), encoding="utf-8")
    return root


@pytest.mark.parametrize("reviewed", ["The fictional period is 30 days.", ""])
def test_package_rejects_a_different_override_before_writing(tmp_path, reviewed):
    module = load_script("answer_identity_rejection", "package_validation.py")
    inputs = _inputs(tmp_path / "inputs", reviewed)
    override = inputs / "override.md"
    override.write_text("The fictional period is 60 days.", encoding="utf-8")
    output = tmp_path / "output"

    with pytest.raises(ValueError, match="reviewed answer"):
        module.write_validation_package(
            inputs / "document_inventory.json",
            inputs / "source_inventory.json",
            inputs / "claims_review.json",
            output,
            answer_contract_path=inputs / "answer_contract.json",
            validated_document_path=override,
        )

    assert not output.exists()
    assert (
        json.loads((inputs / "claims_review.json").read_text())["validated_document"]
        == reviewed
    )


def test_package_accepts_only_the_same_reviewed_override(tmp_path):
    module = load_script("answer_identity_acceptance", "package_validation.py")
    inputs = _inputs(tmp_path / "inputs")
    reviewed = json.loads((inputs / "claims_review.json").read_text())[
        "validated_document"
    ]
    override = inputs / "same.md"
    override.write_text(reviewed + "\n", encoding="utf-8")

    paths = module.write_validation_package(
        inputs / "document_inventory.json",
        inputs / "source_inventory.json",
        inputs / "claims_review.json",
        tmp_path / "output",
        answer_contract_path=inputs / "answer_contract.json",
        validated_document_path=override,
    )

    assert paths["validated_document"].read_text().strip() == reviewed
    assert (
        json.loads(paths["claims_review"].read_text())["validated_document"] == reviewed
    )


def _inspect(module, root, files):
    inventory = root / "document_inventory.json"
    inventory.write_text(json.dumps({"urls": []}), encoding="utf-8")
    paths = module.write_source_inventory(
        inventory, root / "research", source_files=files, fetch_urls=False
    )
    return json.loads(paths["source_inventory"].read_text())


def test_reinspection_preserves_existing_source_ids_and_captures(tmp_path):
    module = load_script("persistent_source_identity", "inspect_sources.py")
    files = []
    for name in ("A", "B", "C"):
        path = tmp_path / f"{name}.txt"
        path.write_text(f"Fictional authority {name}.", encoding="utf-8")
        files.append(path)
    first = _inspect(module, tmp_path, files[:2])
    original = first["sources"][0]
    capture = tmp_path / "research" / original["captured_text_path"]
    captured_bytes = capture.read_bytes()

    second = _inspect(module, tmp_path, [files[2], *files[:2]])

    source_a = next(
        source for source in second["sources"] if source["path"] == original["path"]
    )
    assert source_a["source_id"] == original["source_id"]
    assert source_a["capture_id"] == original["capture_id"]
    assert capture.read_bytes() == captured_bytes


def test_changed_source_creates_a_new_immutable_capture(tmp_path):
    module = load_script("immutable_source_revision", "inspect_sources.py")
    source = tmp_path / "authority.html"
    source.write_text(
        "<html><body>Original fictional rule.</body></html>", encoding="utf-8"
    )
    first = _inspect(module, tmp_path, [source])["sources"][0]
    old_path = tmp_path / "research" / first["captured_text_path"]
    old_bytes = old_path.read_bytes()
    source.write_text(
        "<html><body>Amended fictional rule.</body></html>", encoding="utf-8"
    )

    second = _inspect(module, tmp_path, [source])["sources"][0]

    assert second["source_id"] == first["source_id"]
    assert second["capture_id"] != first["capture_id"]
    assert second["captured_text_path"] != first["captured_text_path"]
    assert old_path.read_bytes() == old_bytes
    assert {item["capture_id"] for item in second["capture_history"]} == {
        first["capture_id"],
        second["capture_id"],
    }


def test_changed_capture_digest_blocks_ready_delivery(tmp_path):
    inspector = load_script("source_hash_inspection", "inspect_sources.py")
    package = load_script("source_hash_audit", "package_validation.py")
    source = tmp_path / "authority.txt"
    source.write_text("Original fictional rule.", encoding="utf-8")
    inventory = _inspect(inspector, tmp_path, [source])
    captured = inventory["sources"][0]
    path = tmp_path / "research" / captured["captured_text_path"]
    path.write_text("Different fictional rule.", encoding="utf-8")
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest()
        != captured["extracted_text_sha256"]
    )

    audit = package.build_audit(
        {"character_count": 40, "urls": []},
        inventory,
        _claims_review(
            [
                _claim_review(
                    "Different fictional rule.",
                    cited_passage="Different fictional rule.",
                    capture_id=captured["capture_id"],
                )
            ]
        ),
        _answer_contract(generation_route="codex_direct"),
        source_base_dir=tmp_path / "research",
    )

    observation = audit["claim_observations"][0]["source_observations"][0]
    assert observation["capture_integrity"] == "digest_mismatch"
    assert observation["exact_passage_presence"] == "not_tested"
    assert audit["delivery_readiness"] == "review_record_incomplete"


def test_unexplained_missing_verbatim_passage_blocks_delivery(tmp_path):
    module = load_script("verbatim_disposition", "package_validation.py")
    claim = _claim_review(
        "A fictional conclusion.", cited_passage="A quotation not in the supplied text."
    )
    claim["source_checks"][0]["passage_kind"] = "verbatim"

    review = _claims_review([claim])
    audit = module.build_audit(
        {"character_count": 40, "urls": []},
        {
            "sources": [
                {
                    "source_id": "source-001",
                    "status": "available",
                    "excerpt": "Other supplied text.",
                }
            ]
        },
        review,
        _answer_contract(generation_route="codex_direct"),
    )

    assert audit["delivery_readiness"] == "review_record_incomplete"
    assert any(
        error["error"] == "verbatim_discrepancy_requires_disposition"
        for error in audit["consistency_errors"]
    )


@pytest.mark.parametrize("field", ["captured_text_path", "captured_original_path"])
def test_both_retained_byte_streams_are_verified(tmp_path, field):
    inspector = load_script("retained_bytes_inspector", "inspect_sources.py")
    evidence = load_script("retained_bytes_reader", "evidence_refs.py")
    source = tmp_path / "authority.txt"
    source.write_text("Fictional rule.")
    captured = _inspect(inspector, tmp_path, [source])["sources"][0]
    (tmp_path / "research" / captured[field]).write_bytes(b"changed")

    assert (
        evidence.read_capture(captured, tmp_path / "research")[2] == "digest_mismatch"
    )


def test_duplicate_resource_and_omitted_sources_preserve_unique_ids(tmp_path):
    inspector = load_script("duplicate_resource_inspector", "inspect_sources.py")
    source = tmp_path / "authority.txt"
    source.write_text("Fictional rule.")
    first = _inspect(inspector, tmp_path, [source, source])
    assert len(first["sources"]) == 1
    second = _inspect(inspector, tmp_path, [])
    assert second["sources"][0]["source_id"] == first["sources"][0]["source_id"]
    assert second["sources"][0]["inspected_this_pass"] is False


def test_reference_builder_resolves_historical_capture_and_rejects_altered_bytes(
    tmp_path,
):
    inspector = load_script("capture_reference_inspector", "inspect_sources.py")
    evidence = load_script("capture_reference_builder", "evidence_refs.py")
    source = tmp_path / "authority.txt"
    source.write_text("Original fictional rule.")
    first = _inspect(inspector, tmp_path, [source])["sources"][0]
    source.write_text("Amended fictional rule.")
    _inspect(inspector, tmp_path, [source])
    selected = {
        "kind": "source_capture",
        "artifact": "research/" + first["captured_text_path"],
        "inventory": "research/source_inventory.json",
        "source_id": first["source_id"],
        "capture_id": first["capture_id"],
        "start_char": 0,
        "end_char": 8,
        "passage": "Original",
    }

    reference = evidence.make_reference(tmp_path, selected)
    assert len(evidence.validate_reference(tmp_path, reference)) == 3
    (tmp_path / selected["artifact"]).write_text("Altered original rule.")
    with pytest.raises(ValueError, match="verified capture bytes"):
        evidence.make_reference(tmp_path, selected)


@pytest.mark.parametrize(
    "selection",
    [
        {"kind": "unsupported", "artifact": "note.json"},
        {"kind": "fact", "artifact": "../note.json", "pointer": ""},
        {"kind": "fact", "artifact": "note.json", "pointer": "/missing"},
        {"kind": "fact", "artifact": "note.json", "pointer": "/a~2b"},
        {"kind": "fact", "artifact": "note.json", "start_char": True, "end_char": 4},
        {
            "kind": "fact",
            "artifact": "note.json",
            "start_char": 0,
            "end_char": 4,
            "passage": "wrong",
        },
        {"kind": "claim", "artifact": "note.json", "claim_index": 99},
    ],
)
def test_reference_builder_rejects_unresolvable_locators(tmp_path, selection):
    evidence = load_script("invalid_reference_builder", "evidence_refs.py")
    (tmp_path / "note.json").write_text(
        json.dumps({"a/b": ["actual"], "claims": [{"claim_index": 1}]})
    )
    with pytest.raises(ValueError):
        evidence.make_reference(tmp_path, selection)


def test_reference_builder_handles_json_pointer_escapes_and_claim_identity(tmp_path):
    evidence = load_script("valid_reference_builder", "evidence_refs.py")
    (tmp_path / "note.json").write_text(
        json.dumps({"a/b": ["actual"], "claims": [{"claim_index": 1}]})
    )
    ref = evidence.make_reference(
        tmp_path,
        {"kind": "inspection_note", "artifact": "note.json", "pointer": "/a~1b/0"},
    )
    assert evidence.reference_value(tmp_path, ref) == "actual"
    assert (
        evidence.make_reference(
            tmp_path, {"kind": "claim", "artifact": "note.json", "claim_index": 1}
        )["claim_index"]
        == 1
    )


@pytest.mark.parametrize(
    "kind,original,disposition,expected",
    [
        ("paraphrase", None, None, "reviewed_answer_ready"),
        ("translation", "Actual original text.", None, "reviewed_answer_ready"),
        ("translation", None, None, "review_record_incomplete"),
        (
            "verbatim",
            None,
            {
                "status": "evidence_limit",
                "capture_id": None,
                "analysis": "Extraction is incomplete.",
            },
            "evidence_limited",
        ),
        (
            "verbatim",
            None,
            {
                "status": "verified_in_original",
                "capture_id": None,
                "analysis": "Unrecorded claim of inspection.",
            },
            "review_record_incomplete",
        ),
        ("none", None, None, "review_record_incomplete"),
    ],
)
def test_passage_types_keep_paraphrases_and_quotation_limits_distinct(
    tmp_path, kind, original, disposition, expected
):
    module = load_script("passage_type_audit", "package_validation.py")
    claim = _claim_review(
        "Fictional conclusion.", cited_passage="A paraphrase or absent quotation."
    )
    check = claim["source_checks"][0]
    check["passage_kind"] = kind
    if original:
        check["original_passage"] = original
    if disposition:
        check["passage_disposition"] = disposition
        check["limitations"] = ["Quote could not be established from this extraction."]
    review = _claims_review([claim])
    if disposition and disposition["status"] == "evidence_limit":
        review["overall_assessment"]["residual_uncertainties"] = [
            "Quotation remains unverified."
        ]
    audit = module.build_audit(
        {"character_count": 40, "urls": []},
        {
            "sources": [
                {
                    "source_id": "source-001",
                    "status": "available",
                    "excerpt": "Actual original text.",
                }
            ]
        },
        review,
        _answer_contract(generation_route="codex_direct"),
    )
    assert audit["delivery_readiness"] == expected


@pytest.mark.parametrize("matching_note", [True, False])
def test_missing_quote_requires_an_inspection_note_for_the_same_original(
    tmp_path, matching_note, monkeypatch
):
    inspector = load_script("quote_original_inspector", "inspect_sources.py")
    package = load_script("quote_original_package", "package_validation.py")
    evidence = load_script("quote_original_reference", "evidence_refs.py")
    source = tmp_path / "authority.txt"
    source.write_text("Original fictional quotation.")
    # Exercise an extraction defect without editing or refreshing any retained capture.
    monkeypatch.setattr(
        inspector,
        "_extract_source_text",
        lambda raw, **kwargs: (
            "Partial extraction.",
            {
                "format": "pdf",
                "status": "available",
                "capture_scope": "partial_pdf_text",
            },
        ),
    )
    inventory = _inspect(inspector, tmp_path, [source])
    record = inventory["sources"][0]
    base = tmp_path / "research"
    note = {
        "capture_id": record["capture_id"],
        "source_bytes_sha256": record["source_bytes_sha256"],
        "quoted_passage": (
            "Original fictional quotation." if matching_note else "Other quotation."
        ),
        "original_locator": "Line 1 of retained synthetic original",
    }
    (base / "inspection.json").write_text(json.dumps({"inspection": note}))
    ref = evidence.make_reference(
        base,
        {
            "kind": "inspection_note",
            "artifact": "inspection.json",
            "pointer": "/inspection",
        },
    )
    claim = _claim_review(
        "Fictional conclusion.",
        cited_passage="Original fictional quotation.",
        capture_id=record["capture_id"],
    )
    claim["source_checks"][0].update(
        passage_kind="verbatim",
        passage_disposition={
            "capture_id": record["capture_id"],
            "status": "verified_in_original",
            "analysis": "Examined the retained original at the recorded locator.",
            "reference": ref,
        },
    )
    audit = package.build_audit(
        {"character_count": 40, "urls": []},
        inventory,
        _claims_review([claim]),
        _answer_contract(generation_route="codex_direct"),
        source_base_dir=base,
    )
    assert audit["delivery_readiness"] == (
        "reviewed_answer_ready" if matching_note else "review_record_incomplete"
    )


def test_reference_cli_emits_a_verified_selection_without_changing_evidence(
    tmp_path, monkeypatch, capsys
):
    import sys

    evidence = load_script("evidence_reference_cli", "evidence_refs.py")
    (tmp_path / "answer.md").write_text("Reviewed fictional answer.")
    path = tmp_path / "selection.json"
    path.write_text(json.dumps({"kind": "answer", "artifact": "answer.md"}))
    monkeypatch.setattr(
        sys,
        "argv",
        ["evidence_refs.py", "--output-dir", str(tmp_path), "--selection", str(path)],
    )
    assert evidence.main() == 0
    assert (
        json.loads(capsys.readouterr().out)["sha256"]
        == hashlib.sha256((tmp_path / "answer.md").read_bytes()).hexdigest()
    )
    assert (tmp_path / "answer.md").read_text() == "Reviewed fictional answer."


def test_prior_capture_remains_reviewable_after_current_acquisition_fails(tmp_path):
    inspector = load_script("failed_reinspection", "inspect_sources.py")
    package = load_script("prior_capture_review", "package_validation.py")
    source = tmp_path / "authority.txt"
    source.write_text("Historical fictional rule.")
    first = _inspect(inspector, tmp_path, [source])["sources"][0]
    source.unlink()
    latest = _inspect(inspector, tmp_path, [source])
    assert latest["sources"][0]["status"] == "unreadable"
    audit = package.build_audit(
        {"character_count": 40, "urls": []},
        latest,
        _claims_review(
            [
                _claim_review(
                    "Historical fictional rule.",
                    cited_passage="Historical fictional rule.",
                    capture_id=first["capture_id"],
                )
            ]
        ),
        _answer_contract(generation_route="codex_direct"),
        source_base_dir=tmp_path / "research",
    )
    observation = audit["claim_observations"][0]["source_observations"][0]
    assert observation["capture_integrity"] == "verified"
    assert observation["exact_passage_presence"] == "present"


def test_verbatim_presence_preserves_letter_case(tmp_path):
    package = load_script("literal_case_review", "package_validation.py")
    claim = _claim_review("Fictional rule.", cited_passage="FICTIONAL rule.")
    claim["source_checks"][0]["passage_kind"] = "verbatim"
    audit = package.build_audit(
        {"character_count": 40, "urls": []},
        {
            "sources": [
                {
                    "source_id": "source-001",
                    "status": "available",
                    "excerpt": "Fictional rule.",
                }
            ]
        },
        _claims_review([claim]),
        _answer_contract(generation_route="codex_direct"),
    )
    assert audit["delivery_readiness"] == "review_record_incomplete"
