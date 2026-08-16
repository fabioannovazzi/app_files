from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import fitz
import jsonschema
import pytest
from docx import Document
from pptx import Presentation

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
SKILL_ROOT = CLARA_ROOT / "skills" / "advisory-deliverable-validator"
SCRIPT_PATH = SKILL_ROOT / "scripts" / "advisory_validation.py"
CONTRACT_SCHEMA_PATH = CLARA_ROOT / "contracts" / "advisory_contract.v1.schema.json"
REVIEW_SCHEMA_PATH = (
    SKILL_ROOT / "references" / "advisory_validation_review.schema.json"
)


def _validator_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "clara_advisory_deliverable_validator", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _contract(*, format_checks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "decision": "Whether to proceed with the proposed channel pilot.",
        "purpose": "Give the steering group a source-backed recommendation.",
        "audience": ["Steering group", "Engagement partner"],
        "deliverable_type": "advisory memo",
        "output_language": "en",
        "scope_included": ["Commercial evidence", "Implementation conditions"],
        "scope_excluded": ["Legal and tax advice"],
        "available_inputs": ["advisory_memo.md", "evidence.md"],
        "evidence_requirements": ["Material factual claims identify support"],
        "analysis_plan": ["Review support", "Challenge the recommendation"],
        "assumptions": ["The supplied extract is complete"],
        "unresolved_questions": [],
        "success_criteria": ["The decision and conditions are explicit"],
        "selected_clara_workflow": "clara:clara",
        "validation_profile": {
            "review_dimensions": [
                "contract_conformance",
                "factual_source_support",
                "calculations_data_provenance",
                "reasoning_assumptions",
                "contradictions_missing_evidence",
                "recommendation_evidence_decision_fit",
                "professional_judgement_boundaries",
                "correction_needs",
                "residual_uncertainty",
                "delivery_readiness",
            ],
            "format_checks": format_checks or [],
        },
        "validation_scope": {
            "coverage": "all_material_content",
            "included_sections": ["Entire deliverable"],
            "excluded_sections": [],
            "limitations": [],
        },
        "correction_policy": {
            "mode": "separate_artifact",
            "preserve_original": True,
            "allowed": True,
            "approval_required_before_delivery": True,
        },
        "professional_judgement_policy": {
            "owner": "Engagement partner",
            "model_role": "Identify issues and draft corrections for review",
            "approval_required_before_delivery": True,
        },
    }


def _dimension_review() -> dict[str, Any]:
    return {
        "status": "conforms",
        "analysis": "The reviewed content conforms on this dimension.",
        "evidence_refs": ["extracted_deliverable.md"],
        "issues": [],
        "correction_status": "not_needed",
        "professional_review_required": False,
    }


def _review(
    inventory: dict[str, Any],
    *,
    format_checks: list[dict[str, Any]] | None = None,
    correction_status: str = "not_required",
) -> dict[str, Any]:
    dimensions = {
        dimension: _dimension_review()
        for dimension in _validator_module().REVIEW_DIMENSIONS
    }
    if correction_status == "completed":
        dimensions["correction_needs"]["correction_status"] = "completed"
    return {
        "schema_version": "1.0",
        "language": "en",
        "advisory_contract_sha256": inventory["advisory_contract_sha256"],
        "deliverable_sha256": inventory["source_sha256"],
        "coverage_review": {
            "selection_method": "model_led_materiality_review",
            "scope": "all_material_content",
            "reviewed_sections": ["Entire deliverable"],
            "omitted_sections": [],
            "limitations": [],
            "analysis": "All material content was reviewed.",
        },
        "dimension_reviews": dimensions,
        "findings": [],
        "format_specific_checks": format_checks or [],
        "correction": {
            "status": correction_status,
            "summary": (
                "A separate correction was completed."
                if correction_status == "completed"
                else "No correction was required."
            ),
            "corrected_artifact": (
                "advisory_memo_corrected.md" if correction_status == "completed" else ""
            ),
            "unresolved_changes": [],
        },
        "overall_assessment": {
            "outcome": "ready",
            "analysis": "No material unresolved issue was identified.",
            "residual_uncertainties": [],
            "professional_review_items": [],
        },
        "delivery_readiness": {"status": "ready", "conditions": []},
    }


def _write_deliverable(path: Path) -> None:
    suffix = path.suffix
    text = "# Recommendation\n\nProceed with a bounded pilot. Source: [1]. Value: EUR 120,000."
    if suffix in {".md", ".markdown", ".txt"}:
        path.write_text(text, encoding="utf-8")
    elif suffix == ".html":
        path.write_text(
            '<html><body><h1>Recommendation</h1><p>Proceed with a bounded pilot.</p><a href="https://example.com/evidence">Evidence</a></body></html>',
            encoding="utf-8",
        )
    elif suffix == ".docx":
        document = Document()
        document.add_heading("Recommendation", level=1)
        document.add_paragraph("Proceed with a bounded pilot. Value: EUR 120,000.")
        document.save(path)
    elif suffix == ".pptx":
        presentation = Presentation()
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = "Recommendation"
        slide.placeholders[1].text = "Proceed with a bounded pilot. Value: EUR 120,000."
        presentation.save(path)
    elif suffix == ".pdf":
        document = fitz.open()
        page = document.new_page()
        page.insert_text(
            (72, 72), "Recommendation: proceed with a bounded pilot. Value EUR 120,000."
        )
        document.save(path)
        document.close()
    else:
        raise AssertionError(f"unexpected test suffix: {suffix}")


def _prepare(tmp_path: Path, *, format_checks: list[dict[str, Any]] | None = None):
    validator = _validator_module()
    deliverable = tmp_path / "advisory_memo.md"
    contract_path = tmp_path / "advisory_contract.json"
    output_dir = tmp_path / "validation"
    _write_deliverable(deliverable)
    contract_path.write_text(
        json.dumps(_contract(format_checks=format_checks)), encoding="utf-8"
    )
    paths = validator.prepare_validation(deliverable, contract_path, output_dir)
    inventory = json.loads(paths["deliverable_inventory"].read_text(encoding="utf-8"))
    return validator, deliverable, contract_path, output_dir, paths, inventory


def test_advisory_contract_schema_covers_the_stable_cross_workflow_boundary() -> None:
    payload = _contract()
    schema = json.loads(CONTRACT_SCHEMA_PATH.read_text(encoding="utf-8"))

    jsonschema.Draft202012Validator(schema).validate(payload)

    validator = _validator_module()
    assert validator.validate_advisory_contract(payload) == []
    assert set(validator.REQUIRED_CONTRACT_FIELDS) == {
        "schema_version",
        "decision",
        "purpose",
        "audience",
        "deliverable_type",
        "output_language",
        "scope_included",
        "scope_excluded",
        "available_inputs",
        "evidence_requirements",
        "analysis_plan",
        "assumptions",
        "unresolved_questions",
        "success_criteria",
        "selected_clara_workflow",
        "validation_profile",
        "validation_scope",
        "correction_policy",
        "professional_judgement_policy",
    }


@pytest.mark.parametrize(
    "suffix", [".md", ".markdown", ".txt", ".html", ".pdf", ".docx", ".pptx"]
)
def test_prepare_extracts_every_supported_primary_format(
    tmp_path: Path, suffix: str
) -> None:
    validator = _validator_module()
    deliverable = tmp_path / f"deliverable{suffix}"
    _write_deliverable(deliverable)

    text, metadata = validator.read_supported_deliverable(deliverable)

    assert "Recommendation" in text
    assert metadata["parser"] in {
        "plain_text",
        "html_text",
        "pymupdf_text",
        "python_docx",
        "python_pptx_visible_text",
    }


def test_prepare_rejects_spreadsheet_as_primary_but_allows_it_as_evidence(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    spreadsheet = tmp_path / "analysis.xlsx"
    spreadsheet.write_bytes(b"synthetic workbook fixture")
    contract_path = tmp_path / "advisory_contract.json"
    contract_path.write_text(json.dumps(_contract()), encoding="utf-8")

    with pytest.raises(
        validator.AdvisoryValidationError,
        match="unsupported primary deliverable format",
    ):
        validator.prepare_validation(
            spreadsheet, contract_path, tmp_path / "unsupported-primary"
        )

    deliverable = tmp_path / "memo.md"
    _write_deliverable(deliverable)
    paths = validator.prepare_validation(
        deliverable,
        contract_path,
        tmp_path / "with-evidence",
        source_files=[spreadsheet],
    )
    source_inventory = json.loads(paths["source_inventory"].read_text(encoding="utf-8"))
    assert source_inventory["sources"][0]["supported_source_type"] is True


def test_prepare_inventories_links_values_and_preserves_original(
    tmp_path: Path,
) -> None:
    validator, deliverable, _, _, paths, inventory = _prepare(tmp_path)
    original_bytes = deliverable.read_bytes()

    citations = json.loads(paths["citation_inventory"].read_text(encoding="utf-8"))
    calculations = json.loads(
        paths["calculation_inventory"].read_text(encoding="utf-8")
    )

    assert inventory["source_sha256"] == validator._sha256(deliverable)
    assert citations["citation_markers"] == ["[1]"]
    assert "EUR 120,000" in calculations["numeric_tokens"]
    assert deliverable.read_bytes() == original_bytes
    assert inventory["boundary"]["semantic_selection"] == "model_led"
    assert inventory["boundary"]["hidden_model_api_calls"] is False


def test_package_accepts_a_complete_model_led_review(tmp_path: Path) -> None:
    validator, _, contract_path, output_dir, paths, inventory = _prepare(tmp_path)
    review = _review(inventory)
    review_path = output_dir / "advisory_validation_review_draft.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")

    schema = json.loads(REVIEW_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(review)
    package_paths, audit = validator.package_validation(
        paths["deliverable_inventory"],
        review_path,
        contract_path,
        output_dir,
    )

    assert audit["record_complete"] is True
    assert audit["effective_delivery_readiness"] == "ready"
    assert package_paths["review"].is_file()
    assert package_paths["audit"].is_file()
    assert "Delivery readiness: ready" in package_paths["package"].read_text(
        encoding="utf-8"
    )


def test_package_blocks_a_missing_required_format_check(tmp_path: Path) -> None:
    required_check = {
        "workflow": "clara:reporting-engine",
        "requirement": "required",
        "reason": "The recommendation relies on spreadsheet calculations.",
        "artifact_refs": [],
    }
    validator, _, contract_path, output_dir, paths, inventory = _prepare(
        tmp_path, format_checks=[required_check]
    )
    review = _review(inventory)
    review["overall_assessment"]["outcome"] = "blocked"
    review["delivery_readiness"]["status"] = "blocked"
    review_path = output_dir / "advisory_validation_review_draft.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")

    _, audit = validator.package_validation(
        paths["deliverable_inventory"], review_path, contract_path, output_dir
    )

    assert audit["record_complete"] is False
    assert audit["effective_delivery_readiness"] == "blocked"
    assert "required format check is missing: clara:reporting-engine" in audit["errors"]


def test_completed_correction_requires_a_separate_changed_artifact(
    tmp_path: Path,
) -> None:
    validator, deliverable, contract_path, output_dir, paths, inventory = _prepare(
        tmp_path
    )
    review = _review(inventory, correction_status="completed")
    review_path = output_dir / "advisory_validation_review_draft.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    corrected = tmp_path / "advisory_memo_corrected.md"
    corrected.write_text(
        deliverable.read_text(encoding="utf-8") + "\nCondition: confirm the owner.\n",
        encoding="utf-8",
    )

    _, audit = validator.package_validation(
        paths["deliverable_inventory"],
        review_path,
        contract_path,
        output_dir,
        corrected_deliverable=corrected,
    )

    assert audit["record_complete"] is True
    assert audit["checks"]["original_unchanged"] is True
    assert audit["checks"]["separate_corrected_artifact"] is True
    assert audit["corrected_artifact"]["path"] == str(corrected.resolve())


def test_semantic_evaluation_fixtures_cover_required_cases() -> None:
    payload = json.loads(
        (SKILL_ROOT / "evals" / "semantic_validation_cases.json").read_text(
            encoding="utf-8"
        )
    )
    case_ids = {case["id"] for case in payload["cases"]}

    assert {
        "supported-recommendation",
        "partially-supported-market-claim",
        "unsupported-claim",
        "contradicted-recommendation-premise",
        "reasoning-gap",
        "calculation-provenance-gap",
        "contract-failure",
        "judgment-dependent-choice",
        "external-document-without-contract",
        "unsupported-primary-format",
    } <= case_ids
    assert "deterministic keyword or scorecard logic" in payload["purpose"]


def test_skill_and_public_page_keep_format_checks_and_model_data_explicit() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    public_page = (
        ROOT
        / "static"
        / "shared"
        / "clara-advisory-deliverable-validator"
        / "index.html"
    ).read_text(encoding="utf-8")
    public_copy = (ROOT / "static" / "shared" / "product-function-pages.js").read_text(
        encoding="utf-8"
    )
    workflow_copy = public_copy.split('"clara-advisory-deliverable-validator":', 1)[
        1
    ].split('"clara-documents":', 1)[0]

    assert 'data-function-page="clara-advisory-deliverable-validator"' in public_page
    assert workflow_copy.count('modelDataStatus: "relevant"') == 5
    assert "Validate an advisory deliverable" in workflow_copy
    assert "No automatic anonymization is applied" in workflow_copy
    assert "mechanical closure remains partial" in workflow_copy
    assert "does not automatically open URLs" in workflow_copy
    for workflow in (
        "clara:claim-basis-map",
        "clara:html-deck",
        "clara:reporting-engine",
        "clara:deck-correction",
    ):
        assert workflow in skill
    assert "keyword classifier" in skill
    assert "semantic scorecard" in skill
    assert "scripts make no model API calls" in skill
