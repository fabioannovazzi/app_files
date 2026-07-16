from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
import zipfile
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    ROOT / "plugins" / "attribute-reporting" / "scripts" / "attribute_reporting.py"
)
APPLY_SCRIPT_PATH = (
    ROOT / "plugins" / "attribute-reporting" / "scripts" / "apply_validated_mappings.py"
)
REPORT_ID = "retailer--skin-care--report"
AUTHOR_AGENT_ID = "codex-author"
REVIEWER_AGENT_ID = "codex-reviewer"
CLAIM_ID = "covered-products"
PRODUCT_COUNT = 12
TAXONOMY_VERSION = "skin-care-v3"
TAXONOMY_SHA256 = "a" * 64
TABLE_KEYS = (
    "attribute_bundle_comparison_table",
    "attribute_bridge_table",
    "rank_weighted_visibility_table",
    "product_signal_evidence_table",
)
SECTION_IDS = (
    "executive_summary",
    "winning_now",
    "brand_context",
    "emerging_signal",
    "winner_emerging_bridge",
    "product_evidence",
    "method_and_caveats",
)
REVIEW_DIMENSIONS = (
    "claim_coverage",
    "story_coherence",
    "importance_calibration",
    "caveat_handling",
    "brand_and_example_interpretation",
    "html_readability",
)


def _load_reporting_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "attribute_reporting_test_target", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_apply_module(reporting: Any) -> Any:
    previous_reporting = sys.modules.get("attribute_reporting")
    sys.modules["attribute_reporting"] = reporting
    try:
        spec = importlib.util.spec_from_file_location(
            "attribute_reporting_apply_test_target", APPLY_SCRIPT_PATH
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if previous_reporting is None:
            sys.modules.pop("attribute_reporting", None)
        else:
            sys.modules["attribute_reporting"] = previous_reporting


@pytest.fixture(scope="module")
def reporting() -> Any:
    return _load_reporting_module()


@pytest.mark.parametrize(
    ("codex_value", "expected"),
    [
        pytest.param("Dewy", "Dewy", id="mapped"),
        pytest.param(None, None, id="negative-no-value"),
        pytest.param("not in taxonomy", "not in taxonomy", id="oov"),
        pytest.param("N/A", "N/A", id="uncertain-placeholder"),
    ],
)
def test_codex_negative_decisions_suppress_legacy_model_values(
    codex_value: str | None,
    expected: str | None,
) -> None:
    from modules.add_attributes.pdp_attribute_export import (
        _choose_canonical_attribute_value,
    )

    chosen = _choose_canonical_attribute_value(
        {
            "codex": codex_value,
            "vision": "Legacy Vision",
            "web": "Matte",
            "llm": "Natural",
        }
    )

    assert chosen == expected


def test_retailer_filter_remains_authoritative_over_codex_mapping() -> None:
    from modules.add_attributes.pdp_attribute_export import (
        _choose_canonical_attribute_value,
    )

    chosen = _choose_canonical_attribute_value(
        {
            "retailer_filter": "Matte",
            "codex": "Dewy",
            "vision": "Natural",
        }
    )

    assert chosen == "Matte"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _package_fingerprint(package_dir: Path, paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.relative_to(package_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _report_model() -> dict[str, Any]:
    sections = [
        {
            "section_id": section_id,
            "title": section_id.replace("_", " ").title(),
            "summary": "Evidence-backed context for this section.",
            "claim_ids": [CLAIM_ID] if section_id == "executive_summary" else [],
            "table_keys": [],
        }
        for section_id in SECTION_IDS
    ]
    return {
        "schema_version": "attribute_reporting.report_model.v1",
        "report_id": REPORT_ID,
        "author": {
            "execution": "codex_agent",
            "agent_id": AUTHOR_AGENT_ID,
            "role": "report_author",
        },
        "title": "Retailer skin care attribute report",
        "subtitle": "A bounded evidence view",
        "audience": "Product teams",
        "acknowledged_warning_codes": [],
        "sections": sections,
        "claims": [
            {
                "claim_id": CLAIM_ID,
                "kind": "deterministic",
                "checker": "source_fact",
                "headline": "Covered products",
                "text_template": "The evidence contains {{product_count}} products.",
                "interpretation": "This is the covered product set.",
                "caveat": "",
                "confidence": "high",
                "evidence_refs": [
                    {
                        "ref_id": "product_count",
                        "source": "summary.json",
                        "selector": {"json_path": ["product_count"]},
                        "format": "integer",
                    }
                ],
                "supporting_claim_ids": [],
            }
        ],
        "featured_products": [],
        "limitations": [],
        "authoring_status": "codex_complete",
    }


def _write_report_artifacts(
    tmp_path: Path,
    *,
    package_warning: tuple[str, str] | None = None,
) -> tuple[Path, Path]:
    package_dir = tmp_path / "package"
    output_dir = tmp_path / "report"
    package_dir.mkdir()
    output_dir.mkdir()

    _write_json(package_dir / "summary.json", {"product_count": PRODUCT_COUNT})
    _write_json(package_dir / "package_integrity.json", {"status": "pass"})
    manifest_files = {
        "summary": "summary.json",
        "integrity": "package_integrity.json",
    }
    warnings: list[dict[str, str]] = []
    if package_warning is not None:
        warning_code, warning_message = package_warning
        _write_json(
            package_dir / "package_warnings.json",
            {
                "warnings": [
                    {"code": warning_code, "message": warning_message},
                ]
            },
        )
        manifest_files["warnings"] = "package_warnings.json"
        warnings.append(
            {
                "code": warning_code,
                "message": warning_message,
                "interpretation": "",
                "source": "package_warnings.json",
            }
        )
    _write_json(
        package_dir / "pack_manifest.json",
        {"files": manifest_files},
    )
    package_paths = [
        package_dir / "pack_manifest.json",
        package_dir / "package_integrity.json",
        package_dir / "summary.json",
    ]
    if package_warning is not None:
        package_paths.append(package_dir / "package_warnings.json")
    source_hashes = {
        path.name: _sha256(path)
        for path in sorted(package_paths, key=lambda item: item.name)
    }
    catalog = {
        "schema_version": "attribute_reporting.evidence_catalog.v1",
        "report_id": REPORT_ID,
        "package": {
            "path": str(package_dir),
            "sha256": _package_fingerprint(package_dir, package_paths),
            "integrity_sha256": _sha256(package_dir / "package_integrity.json"),
            "retailer": "retailer",
            "retailer_label": "Retailer",
            "category_key": "skin-care",
            "category_label": "Skin Care",
            "discovery_crawl_ts": "2026-07-15T09:00:00Z",
        },
        "warnings": warnings,
        "source_hashes": source_hashes,
        "sources": [],
        "attribute_tables": [{"table_key": key} for key in TABLE_KEYS],
    }
    _write_json(output_dir / "evidence_catalog.json", catalog)
    report_model = _report_model()
    if package_warning is not None:
        warning_code, warning_message = package_warning
        report_model["acknowledged_warning_codes"] = [warning_code]
        report_model["limitations"] = [{"code": warning_code, "text": warning_message}]
    _write_json(output_dir / "report_model.json", report_model)
    _write_json(
        output_dir / "semantic_review.json",
        {
            "schema_version": "attribute_reporting.semantic_review.v1",
            "overall_verdict": "unable_to_determine",
        },
    )
    return package_dir, output_dir


def _write_supported_review(output_dir: Path, render_manifest: dict[str, Any]) -> None:
    _write_json(
        output_dir / "semantic_review.json",
        {
            "schema_version": "attribute_reporting.semantic_review.v1",
            "review_id": "independent-review",
            "author_agent_id": AUTHOR_AGENT_ID,
            "reviewer": {
                "execution": "codex_agent",
                "agent_id": REVIEWER_AGENT_ID,
                "role": "independent_reviewer",
                "independent_from_author": True,
            },
            "targets": {
                "report_id": REPORT_ID,
                "evidence_catalog_sha256": render_manifest["evidence_catalog_sha256"],
                "report_model_sha256": render_manifest["report_model_sha256"],
                "draft_html_sha256": render_manifest["draft_html_sha256"],
            },
            "overall_verdict": "correct",
            "summary": "Every claim is supported.",
            "dimensions": {
                dimension: {"status": "pass", "rationale": "Supported."}
                for dimension in REVIEW_DIMENSIONS
            },
            "claim_reviews": [
                {
                    "claim_id": CLAIM_ID,
                    "verdict": "supported",
                    "reason": "The displayed value is bound to the package summary.",
                }
            ],
            "report_level_findings": [],
            "images_reviewed": [],
        },
    )


def _change_summary_source(package_dir: Path) -> None:
    _write_json(package_dir / "summary.json", {"product_count": PRODUCT_COUNT + 1})


def _remove_summary_source(package_dir: Path) -> None:
    (package_dir / "summary.json").unlink()


def _add_claim_review_caveat(review: dict[str, Any]) -> None:
    review["claim_reviews"][0]["verdict"] = "supported_with_caveat"
    review["claim_reviews"][0]["reason"] = "The claim needs a visible caveat."


def _add_dimension_review_caveat(review: dict[str, Any]) -> None:
    review["dimensions"]["story_coherence"] = {
        "status": "caveat",
        "rationale": "The story has a visible coherence caveat.",
    }


def _add_overall_review_caveat(review: dict[str, Any]) -> None:
    review["overall_verdict"] = "correct_with_caveats"
    review["summary"] = "The overall review has a visible caveat."


def _bundle_evidence_row(bundle_key: str) -> dict[str, str]:
    return {
        "bundle_key": bundle_key,
        "bundle_label": bundle_key.replace("_", " ").title(),
        "count_top_seller": "4",
        "top_seller_brand_count": "2",
        "pct_top_seller": "0.60",
        "pct_other": "0.20",
        "count_recent": "5",
        "recent_brand_count": "3",
        "pct_recent": "0.50",
        "pct_rest": "0.10",
    }


def _write_bundle_evidence(package_dir: Path) -> None:
    rows = [
        _bundle_evidence_row("finish_dewy"),
        _bundle_evidence_row("finish_matte"),
    ]
    _write_csv(package_dir / "top_seller_pairs.csv", rows)
    _write_csv(package_dir / "innovation_pairs.csv", rows)


def _bundle_share_ref(
    ref_id: str,
    *,
    source: str,
    bundle_key: str,
    field: str,
) -> dict[str, Any]:
    return {
        "ref_id": ref_id,
        "source": source,
        "selector": {"match": {"bundle_key": bundle_key}, "field": field},
        "format": "percent_1",
    }


def _bundle_checker_claim(checker: str, *, split_rows: bool) -> dict[str, Any]:
    winner_baseline_key = "finish_matte" if split_rows else "finish_dewy"
    emerging_baseline_key = (
        "finish_matte"
        if split_rows and checker == "bundle_signal_emerging"
        else "finish_dewy"
    )
    winner_refs = [
        _bundle_share_ref(
            "winner-focus-share",
            source="top_seller_pairs.csv",
            bundle_key="finish_dewy",
            field="pct_top_seller",
        ),
        _bundle_share_ref(
            "winner-baseline-share",
            source="top_seller_pairs.csv",
            bundle_key=winner_baseline_key,
            field="pct_other",
        ),
    ]
    emerging_refs = [
        _bundle_share_ref(
            "emerging-focus-share",
            source="innovation_pairs.csv",
            bundle_key="finish_dewy",
            field="pct_recent",
        ),
        _bundle_share_ref(
            "emerging-baseline-share",
            source="innovation_pairs.csv",
            bundle_key=emerging_baseline_key,
            field="pct_rest",
        ),
    ]
    refs_by_checker = {
        "bundle_signal_winning_now": winner_refs,
        "bundle_signal_emerging": emerging_refs,
        "bundle_bridge": [*winner_refs, *emerging_refs],
    }
    return {
        "claim_id": "bundle-signal",
        "checker": checker,
        "evidence_refs": refs_by_checker[checker],
    }


def _write_bundle_report_case(
    tmp_path: Path,
    *,
    checker: str,
    split_rows: bool,
) -> Path:
    package_dir, output_dir = _write_report_artifacts(tmp_path)
    _write_bundle_evidence(package_dir)
    claim_spec = _bundle_checker_claim(checker, split_rows=split_rows)
    model_path = output_dir / "report_model.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    claim = model["claims"][0]
    claim["checker"] = checker
    claim["evidence_refs"] = claim_spec["evidence_refs"]
    displayed_tokens = " and ".join(
        "{{" + ref["ref_id"] + "}}" for ref in claim["evidence_refs"]
    )
    claim["text_template"] = f"The displayed bundle shares are {displayed_tokens}."
    _write_json(model_path, model)
    return output_dir


def _write_mapping_artifacts(tmp_path: Path) -> tuple[Path, Path, Path]:
    taxonomy_snapshot = {
        "version": TAXONOMY_VERSION,
        "sha256": TAXONOMY_SHA256,
    }
    tasks_path = tmp_path / "mapping_tasks.json"
    decisions_path = tmp_path / "mapping_decisions.json"
    output_path = tmp_path / "validated_mappings.json"
    stable_key = "retailer|skin-care|parent|product-one||finish"
    task_id = "map-" + hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:24]
    _write_json(
        tasks_path,
        {
            "schema_version": "attribute_reporting.mapping_tasks.v1",
            "taxonomy_snapshot": taxonomy_snapshot,
            "tasks": [
                {
                    "task_id": task_id,
                    "product": {
                        "retailer": "retailer",
                        "row_type": "parent",
                        "parent_product_id": "product-one",
                        "variant_id": "",
                        "category_key": "skin-care",
                        "source_row_sha256": "c" * 64,
                    },
                    "attribute": {
                        "id": "finish",
                        "label": "Finish",
                        "selection": "single",
                        "allowed_values": [{"id": "dewy", "label": "Dewy"}],
                    },
                }
            ],
        },
    )
    _write_json(
        decisions_path,
        {
            "schema_version": "attribute_reporting.mapping_decisions.v1",
            "taxonomy_snapshot": taxonomy_snapshot,
            "agent": {"execution": "codex_agent", "agent_id": AUTHOR_AGENT_ID},
            "decisions": [
                {
                    "task_id": task_id,
                    "status": "mapped",
                    "value_id": "dewy",
                    "value_label": "Dewy",
                    "confidence": "high",
                    "reason": "The product evidence explicitly says dewy.",
                }
            ],
        },
    )
    return tasks_path, decisions_path, output_path


def _central_taxonomy() -> dict[str, Any]:
    return {
        "version": TAXONOMY_VERSION,
        "categories": [
            {
                "id": "skin-care",
                "label": "Skin Care",
                "attributes": [
                    {
                        "id": "finish",
                        "label": "Finish",
                        "scope": "product",
                        "selection": "single",
                        "nodes": [
                            {"id": "dewy", "label": "Dewy"},
                            {"id": "matte", "label": "Matte"},
                        ],
                    },
                    {
                        "id": "benefits",
                        "label": "Benefits",
                        "scope": "product",
                        "selection": "multi",
                        "nodes": [
                            {"id": "fragrance_free", "label": "Fragrance Free"},
                            {"id": "vegan", "label": "Vegan"},
                        ],
                    },
                    {
                        "id": "shade",
                        "label": "Shade",
                        "scope": "variant",
                        "selection": "single",
                        "nodes": [
                            {"id": "light", "label": "Light"},
                            {"id": "deep", "label": "Deep"},
                        ],
                    },
                ],
            }
        ],
    }


def _write_mapping_task_package(
    tmp_path: Path,
    *,
    local_image: tuple[str, bytes] | None = None,
    resolved_finish: bool = False,
) -> Path:
    package_dir = tmp_path / "mapping-package"
    package_dir.mkdir()
    _write_json(
        package_dir / "summary.json",
        {"retailer": "retailer", "category_key": "skin-care"},
    )
    _write_json(package_dir / "package_integrity.json", {"status": "pass"})
    product_row = {
        "parent_product_id": "product-one",
        "product_name": "Example Serum",
        "brand": "Example Brand",
        "description_excerpt": "A dewy vegan serum.",
        "pdp_url": "https://example.com/product-one",
    }
    if resolved_finish:
        product_row["finish"] = "Dewy"
    if local_image is not None:
        image_name, image_bytes = local_image
        image_path = package_dir / image_name
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(image_bytes)
        product_row["pack_image_file"] = image_name
    _write_csv(package_dir / "product_filter_matrix.csv", [product_row])
    manifest_files = {
        "summary": "summary.json",
        "integrity": "package_integrity.json",
        "product_filter_matrix": "product_filter_matrix.csv",
    }
    if local_image is not None:
        manifest_files["product_image"] = local_image[0]
    _write_json(package_dir / "pack_manifest.json", {"files": manifest_files})
    return package_dir


def _write_preliminary_sanitization_receipt(package_dir: Path) -> Path:
    receipt_path = package_dir / "server_sanitization_receipt.json"
    _write_json(
        receipt_path,
        {
            "schema_version": (
                "attribute_reporting.server_bridge.package_sanitization.v1"
            ),
            "image_policy": "urls_only_no_image_bytes",
            "removed_image_file_count": 2,
            "sanitized_private_path_field_count": 4,
            "mapping_provenance": {},
            "package_integrity_status": "pass",
        },
    )
    return receipt_path


def _mapping_decisions(
    tasks: dict[str, Any],
    *,
    multi_value_ids: list[str],
) -> dict[str, Any]:
    chosen_ids = {
        "finish": ["dewy"],
        "benefits": multi_value_ids,
    }
    decisions = []
    for task in tasks["tasks"]:
        attribute = task["attribute"]
        labels_by_id = {
            item["id"]: item["label"] for item in attribute["allowed_values"]
        }
        value_ids = chosen_ids[attribute["id"]]
        decisions.append(
            {
                "task_id": task["task_id"],
                "status": "mapped",
                "value_ids": value_ids,
                "value_labels": [labels_by_id[value_id] for value_id in value_ids],
                "confidence": "high",
                "reason": "The product evidence directly supports the selection.",
            }
        )
    return {
        "schema_version": "attribute_reporting.mapping_decisions.v1",
        "taxonomy_snapshot": dict(tasks["taxonomy_snapshot"]),
        "agent": {"execution": "codex_agent", "agent_id": AUTHOR_AGENT_ID},
        "decisions": decisions,
    }


def _prepare_apply_case(
    tmp_path: Path,
    reporting: Any,
    *,
    with_image: bool = False,
    resolved_finish: bool = False,
    tasks_mutator: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    local_image = (
        ("images/product.png", b"\x89PNG\r\n\x1a\n" + b"\0" * 64)
        if with_image
        else None
    )
    package_dir = _write_mapping_task_package(
        tmp_path,
        local_image=local_image,
        resolved_finish=resolved_finish,
    )
    taxonomy = _central_taxonomy()
    tasks_path = tmp_path / "generated_mapping_tasks.json"
    decisions_path = tmp_path / "generated_mapping_decisions.json"
    validated_path = tmp_path / "generated_validated_mappings.json"
    review_path = tmp_path / "generated_mapping_review.json"
    receipt_path = tmp_path / "mapping_apply_receipt.json"
    tasks = reporting.create_mapping_tasks(package_dir, taxonomy, tasks_path)
    if tasks_mutator is not None:
        tasks_mutator(tasks)
        _write_json(tasks_path, tasks)
    decisions = _mapping_decisions(tasks, multi_value_ids=["vegan"])
    _write_json(decisions_path, decisions)
    validated = reporting.validate_mapping_decisions(
        tasks_path,
        decisions_path,
        validated_path,
    )
    review = reporting.create_mapping_review_template(
        tasks_path,
        decisions_path,
        validated_path,
        review_path,
        reviewer_agent_id=REVIEWER_AGENT_ID,
    )
    review["overall_verdict"] = "approved"
    review["summary"] = "Every product mapping is supported by the bounded evidence."
    for task_review in review["task_reviews"]:
        task_review["verdict"] = "supported"
        task_review["reason"] = (
            "The selected taxonomy value matches the product evidence."
        )
    _write_json(review_path, review)
    review_validation = reporting.validate_mapping_review_payloads(
        tasks,
        decisions,
        validated,
        review,
    )
    operation_id = _canonical_sha256(
        {
            "validation_sha256": validated["validation_sha256"],
            "mapping_review_validation_sha256": review_validation[
                "review_validation_sha256"
            ],
        }
    )
    return {
        "package_dir": package_dir,
        "taxonomy": taxonomy,
        "tasks": tasks,
        "tasks_path": tasks_path,
        "decisions": decisions,
        "decisions_path": decisions_path,
        "validated": validated,
        "validated_path": validated_path,
        "review": review,
        "review_path": review_path,
        "review_validation": review_validation,
        "operation_id": operation_id,
        "receipt_path": receipt_path,
    }


def _copy_mapping_provenance(
    output_dir: Path,
    case: dict[str, Any],
    *,
    include_review: bool = True,
) -> None:
    artifacts = {
        "mapping_tasks.json": case["tasks"],
        "mapping_decisions.json": case["decisions"],
        "validated_mappings.json": case["validated"],
    }
    if include_review:
        artifacts["mapping_review.json"] = case["review"]
    for file_name, payload in artifacts.items():
        _write_json(output_dir / file_name, payload)


def _write_server_acceptance_provenance(
    output_dir: Path,
    case: dict[str, Any],
) -> None:
    _copy_mapping_provenance(output_dir, case)
    _write_json(
        output_dir / "mapping_review_validation.json",
        case["review_validation"],
    )
    taxonomy_snapshot = case["tasks"]["taxonomy_snapshot"]
    submission = {
        "schema_version": (
            "attribute_reporting.server_bridge.mapping_submission_receipt.v1"
        ),
        "operation_id": case["operation_id"],
        "submitted_by": "analyst@example.com",
        "database_write": "applied",
        "validation_sha256": case["validated"]["validation_sha256"],
        "mapping_review_sha256": case["review_validation"]["mapping_review_sha256"],
        "mapping_review_validation_sha256": case["review_validation"][
            "review_validation_sha256"
        ],
        "mapping_review_state": case["review_validation"]["review_state"],
        "taxonomy_snapshot": {
            "version": taxonomy_snapshot["version"],
            "sha256": taxonomy_snapshot["sha256"],
        },
    }
    _write_json(output_dir / "mapping_submission_receipt.json", submission)
    provenance_names = (
        "mapping_tasks.json",
        "mapping_decisions.json",
        "validated_mappings.json",
        "mapping_review.json",
        "mapping_submission_receipt.json",
        "mapping_review_validation.json",
    )
    _write_json(
        output_dir / "server_sanitization_receipt.json",
        {
            "schema_version": (
                "attribute_reporting.server_bridge.package_sanitization.v1"
            ),
            "image_policy": "urls_only_no_image_bytes",
            "package_integrity_status": "pass",
            "mapping_provenance": {
                file_name: _sha256(output_dir / file_name)
                for file_name in provenance_names
            },
        },
    )


def _write_transport_receipts(
    package_dir: Path,
    receipt_dir: Path,
) -> tuple[Path, Path]:
    receipt_dir.mkdir(parents=True, exist_ok=True)
    archive_path = receipt_dir / "rebuilt.zip"
    package_files = sorted(
        (path for path in package_dir.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(package_dir).as_posix(),
    )
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in package_files:
            archive.write(path, path.relative_to(package_dir).as_posix())
    archive_sha256 = _sha256(archive_path)
    download_path = receipt_dir / "rebuilt-download.json"
    extraction_path = receipt_dir / "rebuilt-extraction.json"
    _write_json(
        download_path,
        {
            "schema_version": "attribute_reporting.local_download_receipt.v1",
            "job_id": "rebuilt-job",
            "path": str(archive_path.resolve()),
            "sha256": archive_sha256,
            "size_bytes": archive_path.stat().st_size,
        },
    )
    file_rows = [
        {
            "path": path.relative_to(package_dir).as_posix(),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in package_files
    ]
    _write_json(
        extraction_path,
        {
            "schema_version": "attribute_reporting.local_extraction_receipt.v1",
            "archive_path": str(archive_path.resolve()),
            "archive_sha256": archive_sha256,
            "output_dir": str(package_dir.resolve()),
            "file_count": len(file_rows),
            "total_size_bytes": sum(row["size_bytes"] for row in file_rows),
            "files": file_rows,
        },
    )
    return download_path, extraction_path


def _write_no_work_workset(
    path: Path,
    *,
    evidence_job_id: str = "rebuilt-job",
    resolved_attribute_cells: int = 3,
) -> dict[str, Any]:
    mapping_tasks = {
        "schema_version": "attribute_reporting.mapping_tasks.v1",
        "generated_at": "2026-07-15T12:00:00+00:00",
        "taxonomy_snapshot": {
            "version": TAXONOMY_VERSION,
            "sha256": TAXONOMY_SHA256,
            "category_key": "skin-care",
        },
        "scope": {
            "retailer": "retailer",
            "category_key": "skin-care",
            "row_type": "parent",
            "source_package": f"evidence-job:{evidence_job_id}",
        },
        "coverage": {
            "product_rows": 1,
            "resolved_attribute_cells": resolved_attribute_cells,
            "unresolved_attribute_cells": 0,
            "migration_recheck_tasks": 0,
            "variant_attribute_cells_skipped": 2,
            "task_count_before_limit": 0,
            "task_count": 0,
            "truncated": False,
            "include_resolved": False,
        },
        "tasks": [],
    }
    workset = {
        "schema_version": "attribute_reporting.server_bridge.mapping_workset.v1",
        "workset_id": "no-work-workset",
        "workset_sha256": _canonical_sha256(mapping_tasks),
        "evidence_job_id": evidence_job_id,
        "taxonomy_snapshot": {
            "version": TAXONOMY_VERSION,
            "sha256": TAXONOMY_SHA256,
        },
        "requested_by": "analyst@example.com",
        "created_at": "2026-07-15T12:00:00+00:00",
        "status": "no_work",
        "mapping_mode": "unresolved",
        "mapping_state_snapshot_sha256": "b" * 64,
        "correction_precondition_sha256": None,
        "correction_reason": None,
        "mapping_tasks": mapping_tasks,
    }
    _write_json(path, workset)
    return workset


def _attach_transport_lineage(
    reporting: Any,
    *,
    package_dir: Path,
    output_dir: Path,
    download_receipt: Path,
    extraction_receipt: Path,
) -> None:
    copied_download = output_dir / "local_download_receipt.json"
    copied_extraction = output_dir / "local_extraction_receipt.json"
    copied_download.write_bytes(download_receipt.read_bytes())
    copied_extraction.write_bytes(extraction_receipt.read_bytes())
    lineage = reporting._validate_local_transport_receipts(
        package_dir,
        json.loads(copied_download.read_text(encoding="utf-8")),
        json.loads(copied_extraction.read_text(encoding="utf-8")),
    )
    lineage["artifacts"] = {
        copied_download.name: _sha256(copied_download),
        copied_extraction.name: _sha256(copied_extraction),
    }
    run_intake = {
        "schema_version": "attribute_reporting.run_intake.v1",
        "inputs": {
            "mapping_provenance": None,
            "transport_lineage": lineage,
        },
    }
    _write_json(output_dir / "run_intake.json", run_intake)
    catalog_path = output_dir / "evidence_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["transport_lineage"] = lineage
    catalog["run_intake_sha256"] = _canonical_sha256(run_intake)
    _write_json(catalog_path, catalog)


def _attach_no_work_mapping_basis(
    reporting: Any,
    *,
    output_dir: Path,
    workset_path: Path,
) -> None:
    catalog_path = output_dir / "evidence_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    workset = json.loads(workset_path.read_text(encoding="utf-8"))
    target = output_dir / "mapping_no_work_workset.json"
    target.write_bytes(workset_path.read_bytes())
    basis = reporting._validate_no_work_workset(
        workset,
        package_summary=catalog["package"],
        expected_job_id="rebuilt-job",
    )
    basis["server_sanitization_receipt_sha256"] = (
        reporting._validate_preliminary_sanitization_receipt(
            Path(catalog["package"]["path"])
        )
    )
    basis.update(
        {
            "artifact": target.name,
            "artifact_sha256": _sha256(target),
        }
    )
    intake_path = output_dir / "run_intake.json"
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    intake["inputs"]["mapping_review_basis"] = basis
    catalog["mapping_review_basis"] = basis
    catalog["run_intake_sha256"] = _canonical_sha256(intake)
    _write_json(intake_path, intake)
    _write_json(catalog_path, catalog)


def _install_fake_apply_modules(
    monkeypatch: pytest.MonkeyPatch,
    *,
    taxonomy: dict[str, Any],
    store_paths: list[Path],
    atomic_calls: list[tuple[list[Any], list[Any]]],
    database_write_result: bool = True,
) -> None:
    modules_package = ModuleType("modules")
    add_attributes_package = ModuleType("modules.add_attributes")
    pdp_package = ModuleType("modules.pdp")
    taxonomy_module = ModuleType("modules.add_attributes.attribute_taxonomy")
    constants_module = ModuleType("modules.pdp.review_constants")
    store_module = ModuleType("modules.pdp.store")
    for package in (modules_package, add_attributes_package, pdp_package):
        setattr(package, "__path__", [])

    def get_runtime_attribute_taxonomy() -> dict[str, Any]:
        return taxonomy

    def enforce_default_pdp_store_path(path: Path) -> Path:
        return path

    class FakePDPStore:
        def __init__(self, path: Path) -> None:
            store_paths.append(path)

        def upsert_attribute_values_with_audit(
            self,
            value_records: list[Any],
            audit_records: list[Any],
            *,
            operation_id: str,
            reject_existing_source_values: bool,
        ) -> bool:
            assert len(operation_id) == 64
            assert reject_existing_source_values is True
            atomic_calls.append((list(value_records), list(audit_records)))
            return database_write_result

        def upsert_attribute_values(self, _records: list[Any]) -> None:
            raise AssertionError("Non-atomic value write must not be called")

        def append_attribute_audit(self, _records: list[Any]) -> None:
            raise AssertionError("Non-atomic audit write must not be called")

    setattr(
        taxonomy_module,
        "get_runtime_attribute_taxonomy",
        get_runtime_attribute_taxonomy,
    )
    setattr(constants_module, "DEFAULT_PDP_STORE_PATH", Path("pdp_store.sqlite"))
    setattr(
        constants_module,
        "enforce_default_pdp_store_path",
        enforce_default_pdp_store_path,
    )
    setattr(store_module, "AttributeValueRecord", SimpleNamespace)
    setattr(store_module, "AttributeAuditRecord", SimpleNamespace)
    setattr(store_module, "PDPStore", FakePDPStore)
    setattr(modules_package, "add_attributes", add_attributes_package)
    setattr(modules_package, "pdp", pdp_package)
    setattr(add_attributes_package, "attribute_taxonomy", taxonomy_module)
    setattr(pdp_package, "review_constants", constants_module)
    setattr(pdp_package, "store", store_module)
    fake_modules = {
        "modules": modules_package,
        "modules.add_attributes": add_attributes_package,
        "modules.add_attributes.attribute_taxonomy": taxonomy_module,
        "modules.pdp": pdp_package,
        "modules.pdp.review_constants": constants_module,
        "modules.pdp.store": store_module,
    }
    for module_name, module in fake_modules.items():
        monkeypatch.setitem(sys.modules, module_name, module)


def _set_apply_argv(
    monkeypatch: pytest.MonkeyPatch,
    case: dict[str, Any],
    *,
    receipt_path: Path | None = None,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "apply_validated_mappings.py",
            str(case["validated_path"]),
            "--tasks",
            str(case["tasks_path"]),
            "--decisions",
            str(case["decisions_path"]),
            "--mapping-review",
            str(case["review_path"]),
            "--app-root",
            str(ROOT),
            "--receipt",
            str(receipt_path or case["receipt_path"]),
        ],
    )


def _rewrite_tampered_validation(case: dict[str, Any], reporting: Any) -> None:
    tasks = json.loads(case["tasks_path"].read_text(encoding="utf-8"))
    decisions = json.loads(case["decisions_path"].read_text(encoding="utf-8"))
    validated = reporting.validate_mapping_payloads(
        tasks,
        decisions,
        taxonomy=case["taxonomy"],
    )
    _write_json(case["validated_path"], validated)


def _tamper_mapping_workset(case: dict[str, Any], reporting: Any) -> None:
    tasks = json.loads(case["tasks_path"].read_text(encoding="utf-8"))
    decisions = json.loads(case["decisions_path"].read_text(encoding="utf-8"))
    removed_task = tasks["tasks"].pop()
    decisions["decisions"] = [
        decision
        for decision in decisions["decisions"]
        if decision["task_id"] != removed_task["task_id"]
    ]
    tasks["coverage"]["task_count_before_limit"] = len(tasks["tasks"])
    tasks["coverage"]["task_count"] = len(tasks["tasks"])
    _write_json(case["tasks_path"], tasks)
    _write_json(case["decisions_path"], decisions)
    _rewrite_tampered_validation(case, reporting)


def _tamper_mapping_task_id(case: dict[str, Any], _reporting: Any) -> None:
    tasks = json.loads(case["tasks_path"].read_text(encoding="utf-8"))
    decisions = json.loads(case["decisions_path"].read_text(encoding="utf-8"))
    tampered_task_id = "map-" + "f" * 24
    tasks["tasks"][0]["task_id"] = tampered_task_id
    decisions["decisions"][0]["task_id"] = tampered_task_id
    _write_json(case["tasks_path"], tasks)
    _write_json(case["decisions_path"], decisions)


def _tamper_mapping_content(case: dict[str, Any], reporting: Any) -> None:
    tasks = json.loads(case["tasks_path"].read_text(encoding="utf-8"))
    tasks["tasks"][0]["product"]["description"] = "Injected product content."
    _write_json(case["tasks_path"], tasks)
    _rewrite_tampered_validation(case, reporting)


def _tamper_mapping_image_hash(case: dict[str, Any], reporting: Any) -> None:
    tasks = json.loads(case["tasks_path"].read_text(encoding="utf-8"))
    tasks["tasks"][0]["product"]["local_images"][0]["sha256"] = "f" * 64
    _write_json(case["tasks_path"], tasks)
    _rewrite_tampered_validation(case, reporting)


class _RecordingCursor:
    def __init__(self, row: tuple[int] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[int] | None:
        return self._row


class _RecordingConnection:
    def __init__(
        self,
        *,
        parent_exists: bool = True,
        variant_exists: bool = True,
        operation_applied: bool = False,
    ) -> None:
        self.parent_exists = parent_exists
        self.variant_exists = variant_exists
        self.operation_applied = operation_applied
        self.execute_calls: list[tuple[str, tuple[str, ...]]] = []
        self.executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = []
        self.commit_count = 0
        self.transaction_replay_disabled = False

    def disable_transaction_replay(self) -> None:
        self.transaction_replay_disabled = True

    def execute(self, sql: str, params: tuple[str, ...]) -> _RecordingCursor:
        self.execute_calls.append((sql, params))
        if "decision_rule = 'codex_mapping_batch'" in sql:
            exists = self.operation_applied
        elif "FROM variants" in sql:
            exists = self.variant_exists
        elif "FROM parent_products" in sql:
            exists = self.parent_exists
        else:
            exists = False
        return _RecordingCursor((1,) if exists else None)

    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        self.executemany_calls.append((sql, list(rows)))

    def commit(self) -> None:
        self.commit_count += 1


def _attribute_record_pair() -> tuple[Any, Any]:
    from modules.pdp.store import AttributeAuditRecord, AttributeValueRecord

    value_record = AttributeValueRecord(
        retailer="retailer",
        row_type="parent",
        parent_product_id="product-one",
        variant_id="",
        category_key="skin-care",
        attribute_id="finish",
        attribute_label="Finish",
        value="Dewy",
        oov_candidate=None,
        note=None,
        source="codex",
        updated_at="2026-07-15T09:00:00Z",
    )
    audit_record = AttributeAuditRecord(
        timestamp="2026-07-15T09:00:00Z",
        source="codex",
        row_type="parent",
        retailer="retailer",
        parent_product_id="product-one",
        variant_id="",
        attribute_id="finish",
        value="Dewy",
        decision_rule="codex_mapped",
        evidence_json="{}",
        category_key="skin-care",
    )
    return value_record, audit_record


def test_prepare_run_builds_deterministic_tables_from_minimal_package(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir = tmp_path / "minimal-package"
    package_dir.mkdir()
    _write_json(
        package_dir / "summary.json",
        {
            "retailer": "retailer",
            "retailer_label": "Retailer",
            "category_key": "skin-care",
            "category_label": "Skin Care",
        },
    )
    _write_json(package_dir / "package_integrity.json", {"status": "pass"})
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_key": "finish=dewy+benefits=vegan",
                "bundle_label": "Dewy + Vegan",
                "count_top_seller": "2",
                "count_other": "1",
                "pct_top_seller": "0.5",
                "pct_other": "0.1",
                "delta": "0.4",
                "prevalence_ratio": "5.0",
                "top_seller_brand_count": "2",
                "signal_usefulness": "headline_signal",
            }
        ],
    )
    _write_json(
        package_dir / "pack_manifest.json",
        {
            "files": {
                "summary": "summary.json",
                "integrity": "package_integrity.json",
                "top_seller_pairs": "top_seller_pairs.csv",
            }
        },
    )
    output_dir = tmp_path / "prepared-report"

    prepared = reporting.prepare_run(
        package_dir,
        output_dir,
        author_agent_id=AUTHOR_AGENT_ID,
    )

    catalog = json.loads(Path(prepared["evidence_catalog"]).read_text(encoding="utf-8"))
    tables = {item["table_key"]: item for item in catalog["attribute_tables"]}
    bundle_table = tables["attribute_bundle_comparison_table"]
    bundle_csv = output_dir / "evidence" / bundle_table["csv"]
    assert set(tables) == set(TABLE_KEYS)
    assert bundle_table["row_count"] == 1
    assert bundle_table["csv_sha256"] == _sha256(bundle_csv)
    assert "Dewy + Vegan" in bundle_csv.read_text(encoding="utf-8")


def test_prepare_run_carries_approved_mapping_provenance_into_report(
    tmp_path: Path, reporting: Any
) -> None:
    case = _prepare_apply_case(tmp_path, reporting)
    provenance_dir = tmp_path / "mapping-provenance"
    _copy_mapping_provenance(provenance_dir, case)

    prepared = reporting.prepare_run(
        case["package_dir"],
        tmp_path / "prepared-report",
        author_agent_id=AUTHOR_AGENT_ID,
        mapping_provenance_dir=provenance_dir,
    )

    intake = json.loads(Path(prepared["run_intake"]).read_text(encoding="utf-8"))
    recorded = intake["inputs"]["mapping_provenance"]
    assert recorded["review_state"] == "approved"
    assert recorded["server_acceptance"]["status"] == "local_review_only"
    assert set(recorded["artifacts"]) == {
        "mapping_tasks.json",
        "mapping_decisions.json",
        "validated_mappings.json",
        "mapping_review.json",
    }
    for file_name, expected_sha256 in recorded["artifacts"].items():
        assert _sha256(tmp_path / "prepared-report" / file_name) == expected_sha256


def test_prepare_run_pins_server_accepted_mapping_provenance(
    tmp_path: Path, reporting: Any
) -> None:
    case = _prepare_apply_case(tmp_path, reporting)
    provenance_dir = tmp_path / "server-mapping-provenance"
    _write_server_acceptance_provenance(provenance_dir, case)
    download_receipt, extraction_receipt = _write_transport_receipts(
        case["package_dir"],
        tmp_path / "transport",
    )

    prepared = reporting.prepare_run(
        case["package_dir"],
        tmp_path / "prepared-report",
        author_agent_id=AUTHOR_AGENT_ID,
        mapping_provenance_dir=provenance_dir,
        download_receipt_path=download_receipt,
        extraction_receipt_path=extraction_receipt,
    )

    intake = json.loads(Path(prepared["run_intake"]).read_text(encoding="utf-8"))
    acceptance = intake["inputs"]["mapping_provenance"]["server_acceptance"]
    assert acceptance["status"] == "server_accepted"
    assert acceptance["operation_id"] == case["operation_id"]
    assert acceptance["database_write"] == "applied"
    assert set(acceptance["artifacts"]) == {
        "mapping_submission_receipt.json",
        "mapping_review_validation.json",
        "server_sanitization_receipt.json",
    }
    lineage = intake["inputs"]["transport_lineage"]
    catalog = json.loads(Path(prepared["evidence_catalog"]).read_text(encoding="utf-8"))
    assert lineage == catalog["transport_lineage"]
    assert lineage["status"] == "verified"
    assert set(lineage["artifacts"]) == {
        "local_download_receipt.json",
        "local_extraction_receipt.json",
    }
    for file_name, expected_sha256 in lineage["artifacts"].items():
        assert _sha256(tmp_path / "prepared-report" / file_name) == expected_sha256


def test_prepare_run_requires_transport_receipts_with_server_provenance(
    tmp_path: Path, reporting: Any
) -> None:
    case = _prepare_apply_case(tmp_path, reporting)
    provenance_dir = tmp_path / "server-mapping-provenance"
    _write_server_acceptance_provenance(provenance_dir, case)

    with pytest.raises(reporting.ContractError, match="requires both"):
        reporting.prepare_run(
            case["package_dir"],
            tmp_path / "prepared-report",
            author_agent_id=AUTHOR_AGENT_ID,
            mapping_provenance_dir=provenance_dir,
        )


def test_prepare_run_records_zero_task_mapping_review_as_not_applicable(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir = _write_mapping_task_package(tmp_path)
    sanitization_path = _write_preliminary_sanitization_receipt(package_dir)
    download_receipt, extraction_receipt = _write_transport_receipts(
        package_dir,
        tmp_path / "transport",
    )
    workset_path = tmp_path / "mapping" / "workset.json"
    _write_no_work_workset(workset_path, resolved_attribute_cells=4)

    prepared = reporting.prepare_run(
        package_dir,
        tmp_path / "prepared-report",
        author_agent_id=AUTHOR_AGENT_ID,
        download_receipt_path=download_receipt,
        extraction_receipt_path=extraction_receipt,
        no_work_workset_path=workset_path,
    )

    intake = json.loads(Path(prepared["run_intake"]).read_text(encoding="utf-8"))
    basis = intake["inputs"]["mapping_review_basis"]
    assert intake["inputs"]["mapping_provenance"] is None
    assert basis["status"] == "no_work"
    assert basis["mapping_review"] == "not_applicable"
    assert basis["task_count"] == 0
    assert basis["resolved_attribute_cells"] == 4
    assert basis["server_sanitization_receipt_sha256"] == _sha256(sanitization_path)
    assert basis["artifact"] == "mapping_no_work_workset.json"
    assert (
        _sha256(tmp_path / "prepared-report" / basis["artifact"])
        == basis["artifact_sha256"]
    )


def test_prepare_run_requires_preliminary_transport_receipts_for_no_work(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir = _write_mapping_task_package(tmp_path)
    _write_preliminary_sanitization_receipt(package_dir)
    workset_path = tmp_path / "mapping" / "workset.json"
    _write_no_work_workset(workset_path)

    with pytest.raises(reporting.ContractError, match="requires both"):
        reporting.prepare_run(
            package_dir,
            tmp_path / "prepared-report",
            author_agent_id=AUTHOR_AGENT_ID,
            no_work_workset_path=workset_path,
        )


def test_prepare_run_rejects_tampered_server_mapping_acceptance(
    tmp_path: Path, reporting: Any
) -> None:
    case = _prepare_apply_case(tmp_path, reporting)
    provenance_dir = tmp_path / "server-mapping-provenance"
    _write_server_acceptance_provenance(provenance_dir, case)
    receipt_path = provenance_dir / "mapping_submission_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["database_write"] = "not-written"
    _write_json(receipt_path, receipt)
    download_receipt, extraction_receipt = _write_transport_receipts(
        case["package_dir"],
        tmp_path / "transport",
    )

    with pytest.raises(reporting.ContractError, match="accepted write"):
        reporting.prepare_run(
            case["package_dir"],
            tmp_path / "prepared-report",
            author_agent_id=AUTHOR_AGENT_ID,
            mapping_provenance_dir=provenance_dir,
            download_receipt_path=download_receipt,
            extraction_receipt_path=extraction_receipt,
        )


def test_prepare_run_rejects_incomplete_mapping_provenance(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir = _write_mapping_task_package(tmp_path)
    provenance_dir = tmp_path / "mapping-provenance"
    _write_json(provenance_dir / "mapping_tasks.json", {"tasks": []})

    with pytest.raises(reporting.ContractError, match="provenance is incomplete"):
        reporting.prepare_run(
            package_dir,
            tmp_path / "prepared-report",
            author_agent_id=AUTHOR_AGENT_ID,
            mapping_provenance_dir=provenance_dir,
        )


def test_prepare_run_rejects_package_edited_after_safe_extraction(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir = _write_mapping_task_package(tmp_path)
    download_receipt, extraction_receipt = _write_transport_receipts(
        package_dir,
        tmp_path / "transport",
    )
    summary_path = package_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["retailer"] = "changed-after-extraction"
    _write_json(summary_path, summary)

    with pytest.raises(reporting.ContractError, match="changed after extraction"):
        reporting.prepare_run(
            package_dir,
            tmp_path / "prepared-report",
            author_agent_id=AUTHOR_AGENT_ID,
            download_receipt_path=download_receipt,
            extraction_receipt_path=extraction_receipt,
        )


def test_prepare_run_rejects_download_archive_changed_after_receipt(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir = _write_mapping_task_package(tmp_path)
    download_receipt, extraction_receipt = _write_transport_receipts(
        package_dir,
        tmp_path / "transport",
    )
    archive_path = tmp_path / "transport" / "rebuilt.zip"
    with archive_path.open("ab") as archive:
        archive.write(b"changed-after-download")

    with pytest.raises(reporting.ContractError, match="archive changed"):
        reporting.prepare_run(
            package_dir,
            tmp_path / "prepared-report",
            author_agent_id=AUTHOR_AGENT_ID,
            download_receipt_path=download_receipt,
            extraction_receipt_path=extraction_receipt,
        )


def test_prepare_run_allows_only_manifest_pinned_local_hydration_additions(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir = _write_mapping_task_package(tmp_path)
    download_receipt, extraction_receipt = _write_transport_receipts(
        package_dir,
        tmp_path / "transport",
    )
    image_bytes = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
    image_path = package_dir / "images" / "local" / "product-one.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(image_bytes)
    _write_json(
        package_dir / "local_image_manifest.json",
        {
            "schema_version": "attribute_reporting.local_image_manifest.v1",
            "package_dir": str(package_dir.resolve()),
            "products": [
                {
                    "product_id": "product-one",
                    "status": "downloaded",
                    "image_path": "images/local/product-one.png",
                    "sha256": _sha256(image_path),
                    "byte_count": len(image_bytes),
                }
            ],
        },
    )

    prepared = reporting.prepare_run(
        package_dir,
        tmp_path / "prepared-report",
        author_agent_id=AUTHOR_AGENT_ID,
        download_receipt_path=download_receipt,
        extraction_receipt_path=extraction_receipt,
    )

    assert prepared["transport_lineage"]["extraction"]["hydration_additions"] == [
        "images/local/product-one.png",
        "local_image_manifest.json",
    ]


def test_prepare_run_rejects_unapproved_post_extraction_file(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir = _write_mapping_task_package(tmp_path)
    download_receipt, extraction_receipt = _write_transport_receipts(
        package_dir,
        tmp_path / "transport",
    )
    (package_dir / "unapproved.txt").write_text("not extracted", encoding="utf-8")

    with pytest.raises(reporting.ContractError, match="unapproved post-extraction"):
        reporting.prepare_run(
            package_dir,
            tmp_path / "prepared-report",
            author_agent_id=AUTHOR_AGENT_ID,
            download_receipt_path=download_receipt,
            extraction_receipt_path=extraction_receipt,
        )


@pytest.mark.parametrize(
    "checker",
    [
        "bundle_signal_winning_now",
        "bundle_signal_emerging",
        "bundle_bridge",
    ],
)
def test_bundle_checker_rejects_display_values_split_across_exact_rows(
    tmp_path: Path,
    reporting: Any,
    checker: str,
) -> None:
    output_dir = _write_bundle_report_case(
        tmp_path,
        checker=checker,
        split_rows=True,
    )

    with pytest.raises(reporting.ContractError, match="one exact bundle row"):
        reporting.render_report(output_dir)


@pytest.mark.parametrize(
    ("checker", "expected_exact_rows"),
    [
        pytest.param("bundle_signal_winning_now", 1, id="winner"),
        pytest.param("bundle_signal_emerging", 1, id="emerging"),
        pytest.param("bundle_bridge", 2, id="bridge"),
    ],
)
def test_bundle_checker_accepts_displayed_shares_from_one_exact_row_per_layer(
    tmp_path: Path,
    reporting: Any,
    checker: str,
    expected_exact_rows: int,
) -> None:
    output_dir = _write_bundle_report_case(
        tmp_path,
        checker=checker,
        split_rows=False,
    )

    manifest = reporting.render_report(output_dir)

    ledger = json.loads((output_dir / "claim_ledger.json").read_text(encoding="utf-8"))
    checks = ledger["claims"][0]["checks"]
    check_ids = [item["check_id"] for item in checks]
    assert manifest["status"] == "ready_for_independent_semantic_review"
    assert check_ids.count("one_exact_bundle_row") == expected_exact_rows
    assert check_ids.count("focus_share_above_baseline") == expected_exact_rows
    assert all(item["status"] == "pass" for item in checks)


def test_render_report_resolves_bound_claim_into_html_and_ledger(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)

    manifest = reporting.render_report(output_dir)

    draft = (output_dir / "report_draft.html").read_text(encoding="utf-8")
    ledger = json.loads((output_dir / "claim_ledger.json").read_text(encoding="utf-8"))
    claim = ledger["claims"][0]
    assert manifest["status"] == "ready_for_independent_semantic_review"
    assert "The evidence contains 12 products." in draft
    assert f'data-claim-id="{CLAIM_ID}"' in draft
    assert claim["resolved_text"] == "The evidence contains 12 products."
    assert claim["evidence"][0]["raw_value"] == PRODUCT_COUNT
    assert claim["evidence"][0]["formatted_value"] == str(PRODUCT_COUNT)
    assert claim["status"] == "pass"


def test_render_report_rejects_unbound_numeric_prose(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    model_path = output_dir / "report_model.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model["claims"][0]["text_template"] = "The evidence contains 12 products."
    _write_json(model_path, model)

    with pytest.raises(reporting.ContractError, match="unbound numeric literal"):
        reporting.render_report(output_dir)


@pytest.mark.parametrize("non_finite", ["NaN", "Infinity", "-Infinity"])
def test_render_report_rejects_non_finite_evidence_numbers(
    tmp_path: Path,
    reporting: Any,
    non_finite: str,
) -> None:
    package_dir, output_dir = _write_report_artifacts(tmp_path)
    _write_json(package_dir / "summary.json", {"product_count": non_finite})

    with pytest.raises(reporting.ContractError, match="must be finite"):
        reporting.render_report(output_dir)


def test_prepare_run_rejects_allowed_csv_symlink_escaping_package(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir = tmp_path / "symlink-package"
    package_dir.mkdir()
    _write_json(
        package_dir / "summary.json",
        {"retailer": "retailer", "category_key": "skin-care"},
    )
    _write_json(package_dir / "package_integrity.json", {"status": "pass"})
    outside_csv = tmp_path / "outside-top-seller-pairs.csv"
    _write_csv(outside_csv, [_bundle_evidence_row("finish_dewy")])
    (package_dir / "top_seller_pairs.csv").symlink_to(outside_csv)
    _write_json(
        package_dir / "pack_manifest.json",
        {
            "files": {
                "summary": "summary.json",
                "integrity": "package_integrity.json",
                "top_seller_pairs": "top_seller_pairs.csv",
            }
        },
    )

    with pytest.raises(reporting.ContractError, match="escapes the evidence package"):
        reporting.prepare_run(
            package_dir,
            tmp_path / "prepared-report",
            author_agent_id=AUTHOR_AGENT_ID,
        )


def test_render_report_rejects_allowed_csv_symlink_escaping_package(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir, output_dir = _write_report_artifacts(tmp_path)
    outside_csv = tmp_path / "outside-top-seller-pairs.csv"
    _write_csv(outside_csv, [_bundle_evidence_row("finish_dewy")])
    (package_dir / "top_seller_pairs.csv").symlink_to(outside_csv)
    model_path = output_dir / "report_model.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model["claims"][0]["text_template"] = "The focus share is {{focus-share}}."
    model["claims"][0]["evidence_refs"] = [
        _bundle_share_ref(
            "focus-share",
            source="top_seller_pairs.csv",
            bundle_key="finish_dewy",
            field="pct_top_seller",
        )
    ]
    _write_json(model_path, model)

    with pytest.raises(reporting.ContractError, match="escapes the evidence package"):
        reporting.render_report(output_dir)


@pytest.mark.parametrize(
    ("field", "text"),
    [
        pytest.param("title", "Top 10 attribute signals", id="title"),
        pytest.param("subtitle", "The 2026 product view", id="subtitle"),
    ],
)
def test_render_report_rejects_unbound_numeric_title_or_subtitle(
    tmp_path: Path,
    reporting: Any,
    field: str,
    text: str,
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    model_path = output_dir / "report_model.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model[field] = text
    _write_json(model_path, model)

    with pytest.raises(reporting.ContractError, match="unbound numeric literal"):
        reporting.render_report(output_dir)


def test_render_report_rejects_semantic_claim_with_fresh_evidence_refs(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    model_path = output_dir / "report_model.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    semantic_claim_id = "semantic-interpretation"
    model["claims"].append(
        {
            "claim_id": semantic_claim_id,
            "kind": "semantic",
            "checker": None,
            "headline": "Interpretation",
            "text_template": "The covered set supports this interpretation.",
            "interpretation": "A semantic synthesis of the bound count.",
            "caveat": "",
            "confidence": "medium",
            "evidence_refs": [
                {
                    "ref_id": "fresh-count",
                    "source": "summary.json",
                    "selector": {"json_path": ["product_count"]},
                    "format": "integer",
                }
            ],
            "supporting_claim_ids": [CLAIM_ID],
        }
    )
    model["sections"][0]["claim_ids"].append(semantic_claim_id)
    _write_json(model_path, model)

    with pytest.raises(reporting.ContractError, match="fresh evidence refs"):
        reporting.render_report(output_dir)


def test_validate_mapping_decisions_preserves_pinned_taxonomy_identity(
    tmp_path: Path, reporting: Any
) -> None:
    tasks_path, decisions_path, output_path = _write_mapping_artifacts(tmp_path)

    validated = reporting.validate_mapping_decisions(
        tasks_path, decisions_path, output_path
    )

    mapping = validated["mappings"][0]
    assert validated["status"] == "valid"
    assert validated["mapping_count"] == 1
    assert validated["taxonomy_snapshot"] == {
        "version": TAXONOMY_VERSION,
        "sha256": TAXONOMY_SHA256,
    }
    assert mapping["value_id"] == "dewy"
    assert mapping["value_label"] == "Dewy"
    assert mapping["taxonomy_version"] == TAXONOMY_VERSION
    assert mapping["taxonomy_sha256"] == TAXONOMY_SHA256
    assert json.loads(output_path.read_text(encoding="utf-8")) == validated
    assert output_path.stat().st_mode & 0o777 == 0o600


def test_validate_mapping_decisions_replaces_permissive_output_privately(
    tmp_path: Path, reporting: Any
) -> None:
    tasks_path, decisions_path, output_path = _write_mapping_artifacts(tmp_path)
    output_path.write_text("{}\n", encoding="utf-8")
    output_path.chmod(0o644)

    reporting.validate_mapping_decisions(tasks_path, decisions_path, output_path)

    assert output_path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    ("taxonomy_field", "stale_value", "error_pattern"),
    [
        ("version", "skin-care-v2", "different taxonomy version"),
        ("sha256", "b" * 64, "different taxonomy sha256"),
    ],
)
def test_validate_mapping_decisions_rejects_stale_taxonomy_snapshot(
    tmp_path: Path,
    reporting: Any,
    taxonomy_field: str,
    stale_value: str,
    error_pattern: str,
) -> None:
    tasks_path, decisions_path, output_path = _write_mapping_artifacts(tmp_path)
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    decisions["taxonomy_snapshot"][taxonomy_field] = stale_value
    _write_json(decisions_path, decisions)

    with pytest.raises(reporting.ContractError, match=error_pattern):
        reporting.validate_mapping_decisions(tasks_path, decisions_path, output_path)


def test_validate_mapping_decisions_rejects_value_outside_pinned_taxonomy(
    tmp_path: Path, reporting: Any
) -> None:
    tasks_path, decisions_path, output_path = _write_mapping_artifacts(tmp_path)
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    decisions["decisions"][0]["value_id"] = "matte"
    decisions["decisions"][0]["value_label"] = "Matte"
    _write_json(decisions_path, decisions)

    with pytest.raises(reporting.ContractError, match="not an exact value"):
        reporting.validate_mapping_decisions(tasks_path, decisions_path, output_path)


def test_create_mapping_tasks_emits_unresolved_single_and_multi_product_tasks(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir = _write_mapping_task_package(tmp_path)
    taxonomy = _central_taxonomy()
    output_path = tmp_path / "mapping_tasks.json"

    payload = reporting.create_mapping_tasks(package_dir, taxonomy, output_path)

    tasks_by_attribute = {task["attribute"]["id"]: task for task in payload["tasks"]}
    assert set(tasks_by_attribute) == {"finish", "benefits"}
    assert tasks_by_attribute["finish"]["attribute"]["selection"] == "single"
    assert tasks_by_attribute["benefits"]["attribute"]["selection"] == "multi"
    assert all(task["mapping_reason"] == "unresolved" for task in payload["tasks"])
    assert all(
        task["existing_evidence_source"] == "unresolved" for task in payload["tasks"]
    )
    assert all(task["product"]["row_type"] == "parent" for task in payload["tasks"])
    assert payload["taxonomy_snapshot"] == {
        "version": TAXONOMY_VERSION,
        "sha256": _canonical_sha256(taxonomy),
        "category_key": "skin-care",
    }
    assert payload["scope"]["source_matrix_sha256"] == _sha256(
        package_dir / "product_filter_matrix.csv"
    )
    assert payload["scope"]["source_pack_manifest_sha256"] == _sha256(
        package_dir / "pack_manifest.json"
    )
    assert payload["scope"]["source_package_sha256"] == _package_fingerprint(
        package_dir,
        [
            package_dir / "pack_manifest.json",
            package_dir / "package_integrity.json",
            package_dir / "product_filter_matrix.csv",
            package_dir / "summary.json",
        ],
    )
    assert payload["scope"]["summary_sha256"] == _sha256(package_dir / "summary.json")
    assert payload["scope"]["package_integrity_sha256"] == _sha256(
        package_dir / "package_integrity.json"
    )
    assert payload["coverage"] == {
        "product_rows": 1,
        "resolved_attribute_cells": 0,
        "unresolved_attribute_cells": 2,
        "migration_recheck_tasks": 0,
        "variant_attribute_cells_skipped": 1,
        "task_count_before_limit": 2,
        "task_count": 2,
        "truncated": False,
        "include_resolved": False,
    }
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload


def test_correction_selection_keeps_only_pinned_codex_effective_resolved_tasks(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir = _write_mapping_task_package(tmp_path)
    _write_csv(
        package_dir / "product_filter_matrix.csv",
        [
            {
                "parent_product_id": "product-one",
                "product_name": "Codex and filter product",
                "brand": "Example Brand",
                "description_excerpt": "A dewy vegan serum.",
                "pdp_url": "https://example.com/product-one",
                "finish": "Dewy",
                "finish_effective_source": "codex",
                "benefits": "Vegan",
                "benefits_effective_source": "retailer_filter",
            },
            {
                "parent_product_id": "product-two",
                "product_name": "Unpinned and unresolved product",
                "brand": "Example Brand",
                "description_excerpt": "A matte serum.",
                "pdp_url": "https://example.com/product-two",
                "finish": "Matte",
                "finish_effective_source": "codex",
                "benefits": "",
                "benefits_effective_source": "",
            },
        ],
    )
    payload = reporting.create_mapping_tasks(
        package_dir,
        _central_taxonomy(),
        tmp_path / "mapping_tasks.json",
        include_resolved=True,
    )
    tasks_by_identity = {
        (task["product"]["parent_product_id"], task["attribute"]["id"]): task
        for task in payload["tasks"]
    }

    assert (
        tasks_by_identity[("product-one", "finish")]["existing_evidence_source"]
        == "codex"
    )
    assert (
        tasks_by_identity[("product-one", "benefits")]["existing_evidence_source"]
        == "retailer_filter"
    )
    selection = reporting.select_codex_effective_correction_tasks(
        payload["tasks"],
        [
            {
                "source": "codex",
                "retailer": "retailer",
                "row_type": "parent",
                "parent_product_id": "product-one",
                "variant_id": "",
                "category_key": "skin-care",
                "base_attribute_id": attribute_id,
            }
            for attribute_id in ("finish", "benefits")
        ],
    )

    assert selection["task_count_before_selection"] == 4
    assert selection["task_count"] == 1
    assert selection["excluded_unresolved_count"] == 1
    assert selection["excluded_non_codex_effective_count"] == 1
    assert selection["excluded_not_pinned_count"] == 1
    assert (
        selection["tasks"][0]["task_id"]
        == tasks_by_identity[("product-one", "finish")]["task_id"]
    )


def test_mapping_tasks_retain_codex_source_for_one_hot_multi_value(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir = _write_mapping_task_package(tmp_path)
    _write_csv(
        package_dir / "product_filter_matrix.csv",
        [
            {
                "parent_product_id": "product-one",
                "product_name": "One-hot product",
                "brand": "Example Brand",
                "description_excerpt": "A vegan serum.",
                "pdp_url": "https://example.com/product-one",
                "benefits__vegan": "1",
                "benefits__vegan_effective_source": "codex",
            }
        ],
    )

    payload = reporting.create_mapping_tasks(
        package_dir,
        _central_taxonomy(),
        tmp_path / "mapping_tasks.json",
        include_resolved=True,
    )
    benefits_task = next(
        task for task in payload["tasks"] if task["attribute"]["id"] == "benefits"
    )

    assert benefits_task["mapping_reason"] == "migration_recheck"
    assert benefits_task["existing_evidence_source"] == "codex"


def test_create_mapping_tasks_excludes_inactive_taxonomy_leaves(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir = _write_mapping_task_package(tmp_path)
    taxonomy = _central_taxonomy()
    finish_nodes = taxonomy["categories"][0]["attributes"][0]["nodes"]
    finish_nodes.extend(
        [
            {"id": "draft_finish", "label": "Draft Finish", "status": "draft"},
            {
                "id": "review_finish",
                "label": "Review Finish",
                "status": "needs_review",
            },
            {
                "id": "retired_finish",
                "label": "Retired Finish",
                "status": "deprecated",
            },
        ]
    )

    payload = reporting.create_mapping_tasks(
        package_dir,
        taxonomy,
        tmp_path / "mapping_tasks.json",
    )

    finish_task = next(
        task for task in payload["tasks"] if task["attribute"]["id"] == "finish"
    )
    assert finish_task["attribute"]["allowed_values"] == [
        {"id": "dewy", "label": "Dewy"},
        {"id": "matte", "label": "Matte"},
    ]


def test_create_mapping_tasks_rejects_unsupported_local_image(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir = _write_mapping_task_package(
        tmp_path,
        local_image=("images/product.png", b"not-a-png"),
    )

    with pytest.raises(reporting.ContractError, match="supported raster image"):
        reporting.create_mapping_tasks(
            package_dir,
            _central_taxonomy(),
            tmp_path / "mapping_tasks.json",
        )


def test_validate_mapping_decisions_canonicalizes_multi_select_arrays(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir = _write_mapping_task_package(tmp_path)
    taxonomy = _central_taxonomy()
    tasks_path = tmp_path / "mapping_tasks.json"
    decisions_path = tmp_path / "mapping_decisions.json"
    validated_path = tmp_path / "validated_mappings.json"
    tasks = reporting.create_mapping_tasks(package_dir, taxonomy, tasks_path)
    decisions = _mapping_decisions(
        tasks,
        multi_value_ids=["vegan", "fragrance_free"],
    )
    _write_json(decisions_path, decisions)

    validated = reporting.validate_mapping_decisions(
        tasks_path,
        decisions_path,
        validated_path,
    )

    multi_mapping = next(
        mapping
        for mapping in validated["mappings"]
        if mapping["attribute_id"] == "benefits"
    )
    assert multi_mapping["selection"] == "multi"
    assert multi_mapping["value_ids"] == ["fragrance_free", "vegan"]
    assert multi_mapping["value_labels"] == ["Fragrance Free", "Vegan"]
    assert multi_mapping["value_id"] is None
    assert multi_mapping["value_label"] is None


def test_validate_mapping_review_pins_every_artifact_and_task_content(
    tmp_path: Path, reporting: Any
) -> None:
    case = _prepare_apply_case(tmp_path, reporting, with_image=True)

    validation = reporting.validate_mapping_review_payloads(
        case["tasks"],
        case["decisions"],
        case["validated"],
        case["review"],
    )

    assert validation["status"] == "valid"
    assert validation["review_state"] == "approved"
    assert validation["task_count"] == case["validated"]["mapping_count"]
    assert validation["task_verdict_counts"]["supported"] == 2
    assert (
        validation["targets"]["taxonomy_snapshot"] == case["tasks"]["taxonomy_snapshot"]
    )
    assert validation["targets"]["tasks_sha256"] == case["validated"]["tasks_sha256"]
    assert (
        validation["targets"]["decisions_sha256"]
        == case["validated"]["decisions_sha256"]
    )
    assert (
        validation["targets"]["validation_sha256"]
        == case["validated"]["validation_sha256"]
    )
    source_hash_by_task = {
        task["task_id"]: task["product"]["source_row_sha256"]
        for task in case["tasks"]["tasks"]
    }
    assert all(
        task_review["targets"]["source_row_sha256"]
        == source_hash_by_task[task_review["task_id"]]
        for task_review in case["review"]["task_reviews"]
    )
    assert all(
        task_review["targets"]["local_image_sha256s"]
        for task_review in case["review"]["task_reviews"]
    )


@pytest.mark.parametrize(
    ("mutate_review", "error_pattern"),
    [
        pytest.param(
            lambda review, case: review["reviewer"].update(
                {"agent_id": AUTHOR_AGENT_ID}
            ),
            "not independent",
            id="same-agent",
        ),
        pytest.param(
            lambda review, case: review["task_reviews"].pop(),
            "cover every task",
            id="missing-task",
        ),
        pytest.param(
            lambda review, case: review["targets"].update(
                {"decisions_sha256": "f" * 64}
            ),
            "stale or different",
            id="stale-content",
        ),
    ],
)
def test_validate_mapping_review_rejects_non_independent_incomplete_or_stale_review(
    tmp_path: Path,
    reporting: Any,
    mutate_review: Callable[[dict[str, Any], dict[str, Any]], None],
    error_pattern: str,
) -> None:
    case = _prepare_apply_case(tmp_path, reporting)
    review = json.loads(json.dumps(case["review"]))
    mutate_review(review, case)

    with pytest.raises(reporting.ContractError, match=error_pattern):
        reporting.validate_mapping_review_payloads(
            case["tasks"],
            case["decisions"],
            case["validated"],
            review,
        )


def test_apply_validated_mappings_revalidates_and_writes_one_atomic_batch(
    tmp_path: Path,
    reporting: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _prepare_apply_case(tmp_path, reporting)
    apply_module = _load_apply_module(reporting)
    store_paths: list[Path] = []
    atomic_calls: list[tuple[list[Any], list[Any]]] = []
    _install_fake_apply_modules(
        monkeypatch,
        taxonomy=case["taxonomy"],
        store_paths=store_paths,
        atomic_calls=atomic_calls,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "apply_validated_mappings.py",
            str(case["validated_path"]),
            "--tasks",
            str(case["tasks_path"]),
            "--decisions",
            str(case["decisions_path"]),
            "--mapping-review",
            str(case["review_path"]),
            "--app-root",
            str(ROOT),
            "--receipt",
            str(case["receipt_path"]),
        ],
    )

    status = apply_module.main()

    assert status == 0
    assert store_paths == [Path("pdp_store.sqlite")]
    assert len(atomic_calls) == 1
    value_records, audit_records = atomic_calls[0]
    values_by_attribute = {
        record.attribute_id: record.value for record in value_records
    }
    assert values_by_attribute == {
        "finish": "Dewy",
        "benefits__fragrance_free": "False",
        "benefits__vegan": "True",
        "benefits__unknown": "False",
        "benefits__other": "False",
        "benefits__not_in_taxonomy": "False",
    }
    assert all(record.source == "codex" for record in value_records)
    assert len(audit_records) == len(value_records)
    audits_by_attribute = {record.attribute_id: record for record in audit_records}
    selected_audit = audits_by_attribute["benefits__vegan"]
    selected_lineage = json.loads(selected_audit.evidence_json)
    assert selected_audit.decision_rule == "codex_multi_leaf"
    assert selected_lineage["base_attribute_id"] == "benefits"
    assert selected_lineage["leaf_value_id"] == "vegan"
    assert selected_lineage["selected_value_ids"] == ["vegan"]
    assert selected_lineage["taxonomy_version"] == TAXONOMY_VERSION
    assert selected_lineage["taxonomy_sha256"] == _canonical_sha256(case["taxonomy"])
    assert selected_lineage["tasks_sha256"] == case["validated"]["tasks_sha256"]
    assert selected_lineage["decisions_sha256"] == case["validated"]["decisions_sha256"]
    assert (
        selected_lineage["validation_sha256"] == case["validated"]["validation_sha256"]
    )
    assert (
        selected_lineage["mapping_review_sha256"]
        == case["review_validation"]["mapping_review_sha256"]
    )
    assert (
        selected_lineage["mapping_review_validation_sha256"]
        == case["review_validation"]["review_validation_sha256"]
    )
    assert selected_lineage["mapping_review_state"] == "approved"
    assert selected_lineage["mapping_reviewer"]["agent_id"] == REVIEWER_AGENT_ID
    assert selected_lineage["source_scope"] == case["tasks"]["scope"]
    receipt = json.loads(case["receipt_path"].read_text(encoding="utf-8"))
    assert receipt["status"] == "applied"
    assert receipt["mapping_count"] == 2
    assert receipt["attribute_value_record_count"] == 6
    assert receipt["taxonomy_version"] == TAXONOMY_VERSION
    assert receipt["taxonomy_sha256"] == _canonical_sha256(case["taxonomy"])
    assert receipt["tasks_sha256"] == case["validated"]["tasks_sha256"]
    assert receipt["decisions_sha256"] == case["validated"]["decisions_sha256"]
    assert receipt["validation_sha256"] == case["validated"]["validation_sha256"]
    assert receipt["operation_id"] == case["operation_id"]
    assert (
        receipt["mapping_review_sha256"]
        == case["review_validation"]["mapping_review_sha256"]
    )
    assert receipt["mapping_review_state"] == "approved"
    assert receipt["source_scope"] == case["tasks"]["scope"]


def test_apply_validated_mappings_rejects_semantically_unsupported_mapping(
    tmp_path: Path,
    reporting: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _prepare_apply_case(tmp_path, reporting)
    review = json.loads(json.dumps(case["review"]))
    review["task_reviews"][0]["verdict"] = "unsupported"
    review["task_reviews"][0][
        "reason"
    ] = "The bounded product evidence contradicts the selected taxonomy value."
    review["overall_verdict"] = "rejected"
    review["summary"] = "One mapping is semantically unsupported."
    _write_json(case["review_path"], review)
    apply_module = _load_apply_module(reporting)
    store_paths: list[Path] = []
    atomic_calls: list[tuple[list[Any], list[Any]]] = []
    _install_fake_apply_modules(
        monkeypatch,
        taxonomy=case["taxonomy"],
        store_paths=store_paths,
        atomic_calls=atomic_calls,
    )
    _set_apply_argv(monkeypatch, case)

    status = apply_module.main()

    assert status == 1
    assert store_paths == []
    assert atomic_calls == []
    assert not case["receipt_path"].exists()


def test_apply_validated_mappings_rejects_tampered_artifact_before_store_write(
    tmp_path: Path,
    reporting: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _prepare_apply_case(tmp_path, reporting)
    tampered = json.loads(case["validated_path"].read_text(encoding="utf-8"))
    tampered["mappings"][0]["value_labels"] = ["Matte"]
    _write_json(case["validated_path"], tampered)
    apply_module = _load_apply_module(reporting)
    store_paths: list[Path] = []
    atomic_calls: list[tuple[list[Any], list[Any]]] = []
    _install_fake_apply_modules(
        monkeypatch,
        taxonomy=case["taxonomy"],
        store_paths=store_paths,
        atomic_calls=atomic_calls,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "apply_validated_mappings.py",
            str(case["validated_path"]),
            "--tasks",
            str(case["tasks_path"]),
            "--decisions",
            str(case["decisions_path"]),
            "--mapping-review",
            str(case["review_path"]),
            "--app-root",
            str(ROOT),
            "--receipt",
            str(case["receipt_path"]),
        ],
    )

    status = apply_module.main()

    assert status == 1
    assert store_paths == []
    assert atomic_calls == []
    assert not case["receipt_path"].exists()


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param(_tamper_mapping_workset, id="workset"),
        pytest.param(_tamper_mapping_task_id, id="task-id"),
        pytest.param(_tamper_mapping_content, id="content"),
        pytest.param(_tamper_mapping_image_hash, id="image-hash"),
    ],
)
def test_apply_validated_mappings_rejects_source_workset_tampering(
    tmp_path: Path,
    reporting: Any,
    monkeypatch: pytest.MonkeyPatch,
    tamper: Callable[[dict[str, Any], Any], None],
) -> None:
    case = _prepare_apply_case(tmp_path, reporting, with_image=True)
    tamper(case, reporting)
    apply_module = _load_apply_module(reporting)
    store_paths: list[Path] = []
    atomic_calls: list[tuple[list[Any], list[Any]]] = []
    _install_fake_apply_modules(
        monkeypatch,
        taxonomy=case["taxonomy"],
        store_paths=store_paths,
        atomic_calls=atomic_calls,
    )
    _set_apply_argv(monkeypatch, case)

    status = apply_module.main()

    assert status == 1
    assert store_paths == []
    assert atomic_calls == []
    assert not case["receipt_path"].exists()


def test_apply_validated_mappings_rejects_invalid_receipt_before_database_write(
    tmp_path: Path,
    reporting: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _prepare_apply_case(tmp_path, reporting)
    apply_module = _load_apply_module(reporting)
    store_paths: list[Path] = []
    atomic_calls: list[tuple[list[Any], list[Any]]] = []
    invalid_receipt_path = ROOT / "tests" / f".{tmp_path.name}-mapping-receipt.json"
    _install_fake_apply_modules(
        monkeypatch,
        taxonomy=case["taxonomy"],
        store_paths=store_paths,
        atomic_calls=atomic_calls,
    )
    _set_apply_argv(monkeypatch, case, receipt_path=invalid_receipt_path)

    status = apply_module.main()

    assert status == 1
    assert store_paths == []
    assert atomic_calls == []
    assert not invalid_receipt_path.exists()


def test_apply_validated_mappings_rechecks_completed_replay_against_database_marker(
    tmp_path: Path,
    reporting: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _prepare_apply_case(tmp_path, reporting)
    operation_id = case["operation_id"]
    _write_json(
        case["receipt_path"],
        {"operation_id": operation_id, "status": "applied"},
    )
    apply_module = _load_apply_module(reporting)
    store_paths: list[Path] = []
    atomic_calls: list[tuple[list[Any], list[Any]]] = []
    _install_fake_apply_modules(
        monkeypatch,
        taxonomy=case["taxonomy"],
        store_paths=store_paths,
        atomic_calls=atomic_calls,
        database_write_result=False,
    )
    _set_apply_argv(monkeypatch, case)

    status = apply_module.main()

    receipt = json.loads(case["receipt_path"].read_text(encoding="utf-8"))
    assert status == 0
    assert store_paths == [Path("pdp_store.sqlite")]
    assert len(atomic_calls) == 1
    assert receipt["operation_id"] == operation_id
    assert receipt["status"] == "applied"
    assert receipt["database_write"] == "already_applied"


def test_apply_validated_mappings_recovers_pending_same_operation_from_database_marker(
    tmp_path: Path,
    reporting: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _prepare_apply_case(tmp_path, reporting)
    operation_id = case["operation_id"]
    _write_json(
        case["receipt_path"],
        {"operation_id": operation_id, "status": "pending"},
    )
    apply_module = _load_apply_module(reporting)
    store_paths: list[Path] = []
    atomic_calls: list[tuple[list[Any], list[Any]]] = []
    _install_fake_apply_modules(
        monkeypatch,
        taxonomy=case["taxonomy"],
        store_paths=store_paths,
        atomic_calls=atomic_calls,
        database_write_result=False,
    )
    _set_apply_argv(monkeypatch, case)

    status = apply_module.main()

    receipt = json.loads(case["receipt_path"].read_text(encoding="utf-8"))
    assert status == 0
    assert store_paths == [Path("pdp_store.sqlite")]
    assert len(atomic_calls) == 1
    assert receipt["operation_id"] == operation_id
    assert receipt["status"] == "applied"
    assert receipt["database_write"] == "already_applied"


def test_finalize_report_returns_correct_for_intact_supported_report(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)

    verdict = reporting.finalize_report(output_dir)

    report_html = (output_dir / "report.html").read_text(encoding="utf-8")
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert verdict["verdict"] == "correct"
    assert verdict["mechanical_findings"] == []
    assert verdict["basis"]["semantic_review"] == "correct"
    assert 'data-correctness-verdict="correct"' in report_html
    assert final_artifacts["status"] == "final_ready"


def test_finalize_report_lists_generated_attribute_table_artifacts(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    catalog_path = output_dir / "evidence_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    table_dir = output_dir / "evidence" / "attribute_tables"
    table_dir.mkdir(parents=True)
    table_records = []
    for table_key in TABLE_KEYS:
        csv_name = f"{table_key}.csv"
        html_name = f"{table_key}.html"
        csv_path = table_dir / csv_name
        html_path = table_dir / html_name
        csv_path.write_text("field,value\nexample,1\n", encoding="utf-8")
        html_path.write_text(
            "<table><tr><td>example</td></tr></table>", encoding="utf-8"
        )
        table_records.append(
            {
                "table_key": table_key,
                "csv": f"attribute_tables/{csv_name}",
                "html": f"attribute_tables/{html_name}",
            }
        )
    _write_json(table_dir / "manifest.json", {"tables": table_records})
    catalog["attribute_tables"] = table_records
    _write_json(catalog_path, catalog)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)

    reporting.finalize_report(output_dir)

    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    outputs_by_path = {item["path"]: item for item in final_artifacts["outputs"]}
    expected_paths = {
        "evidence/attribute_tables/manifest.json",
        *{f"evidence/attribute_tables/{table_key}.csv" for table_key in TABLE_KEYS},
        *{f"evidence/attribute_tables/{table_key}.html" for table_key in TABLE_KEYS},
    }
    assert expected_paths <= set(outputs_by_path)
    assert (
        outputs_by_path["evidence/attribute_tables/manifest.json"]["artifact_role"]
        == "attribute_table_manifest"
    )
    for table_key in TABLE_KEYS:
        csv_output = outputs_by_path[f"evidence/attribute_tables/{table_key}.csv"]
        html_output = outputs_by_path[f"evidence/attribute_tables/{table_key}.html"]
        assert csv_output["table_key"] == table_key
        assert csv_output["artifact_role"] == "attribute_table"
        assert html_output["table_key"] == table_key
        assert html_output["artifact_role"] == "attribute_table"


def test_finalize_report_rechecks_pinned_transport_receipt_copies(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir, output_dir = _write_report_artifacts(tmp_path)
    download_receipt, extraction_receipt = _write_transport_receipts(
        package_dir,
        tmp_path / "transport",
    )
    _attach_transport_lineage(
        reporting,
        package_dir=package_dir,
        output_dir=output_dir,
        download_receipt=download_receipt,
        extraction_receipt=extraction_receipt,
    )
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    copied_receipt = output_dir / "local_download_receipt.json"
    copied_payload = json.loads(copied_receipt.read_text(encoding="utf-8"))
    copied_payload["job_id"] = "tampered-job"
    _write_json(copied_receipt, copied_payload)

    verdict = reporting.finalize_report(output_dir)

    finding_codes = {item["code"] for item in verdict["mechanical_findings"]}
    assert "transport_receipt_changed" in finding_codes
    assert verdict["verdict"] == "incorrect"


def test_rendered_draft_shows_pending_verdict_until_final_checks_replace_it(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    render_manifest = reporting.render_report(output_dir)
    draft = (output_dir / "report_draft.html").read_text(encoding="utf-8")
    _write_supported_review(output_dir, render_manifest)

    reporting.finalize_report(output_dir)

    final_html = (output_dir / "report.html").read_text(encoding="utf-8")
    assert 'data-correctness-verdict="pending"' in draft
    assert "Correctness review pending" in draft
    assert 'data-correctness-verdict="pending"' not in final_html
    assert "Correctness review pending" not in final_html


def _require_browser_qa(output_dir: Path) -> None:
    intake_path = output_dir / "run_intake.json"
    intake = (
        json.loads(intake_path.read_text(encoding="utf-8"))
        if intake_path.is_file()
        else {"quality_gates": {}}
    )
    intake["quality_gates"]["browser_qa_required"] = True
    _write_json(intake_path, intake)


def _write_browser_qa(
    output_dir: Path,
    render_manifest: dict[str, Any],
    *,
    status: str = "pass",
    findings: list[dict[str, Any]] | None = None,
) -> None:
    supplied = {item["code"]: item for item in findings or []}
    viewport_rows: list[dict[str, Any]] = []
    all_findings: list[dict[str, Any]] = []
    suffixes = (
        "horizontal_overflow",
        "local_images",
        "asset_locality",
        "table_scrolling",
        "required_elements",
        "product_links",
        "runtime",
    )
    for name, width, height in (("desktop", 1440, 1000), ("mobile", 390, 844)):
        screenshot = output_dir / "qa" / "screenshots" / f"report-{name}.png"
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        screenshot.write_bytes(f"{name}-screenshot".encode("utf-8"))
        viewport_findings = []
        for suffix in suffixes:
            code = f"browser.{name}.{suffix}"
            viewport_findings.append(
                supplied.get(
                    code,
                    {
                        "code": code,
                        "status": "pass",
                        "message": "Browser check passed.",
                        "details": [],
                    },
                )
            )
        all_findings.extend(viewport_findings)
        viewport_rows.append(
            {
                "name": name,
                "width": width,
                "height": height,
                "screenshot": screenshot.relative_to(output_dir).as_posix(),
                "screenshot_sha256": _sha256(screenshot),
                "metrics": {},
                "findings": viewport_findings,
            }
        )
    _write_json(
        output_dir / "browser_qa.json",
        {
            "schema_version": "attribute_reporting.browser_qa.v1",
            "checked_at": "2026-07-15T12:00:00+00:00",
            "report_id": render_manifest["report_id"],
            "targets": {
                "draft_html": str(output_dir / "report_draft.html"),
                "draft_html_sha256": render_manifest["draft_html_sha256"],
                "render_manifest_sha256": _sha256(output_dir / "render_manifest.json"),
            },
            "status": status,
            "viewports": viewport_rows,
            "findings": all_findings,
            "browser_error": "",
        },
    )


def test_finalize_report_requires_browser_qa_when_clara_gate_is_enabled(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    _require_browser_qa(output_dir)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)

    verdict = reporting.finalize_report(output_dir)

    assert verdict["verdict"] == "unable_to_determine"
    assert verdict["basis"]["browser_qa"] == "unable_to_determine"
    assert verdict["browser_findings"][0]["code"] == "browser_qa_missing"


def test_finalize_report_accepts_current_passing_browser_qa(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    _require_browser_qa(output_dir)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    _write_browser_qa(output_dir, render_manifest)

    verdict = reporting.finalize_report(output_dir)

    assert verdict["verdict"] == "correct"
    assert verdict["basis"]["browser_qa"] == "correct"
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert any(item["path"] == "browser_qa.json" for item in final_artifacts["outputs"])


def test_finalize_report_marks_browser_failure_incorrect(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    _require_browser_qa(output_dir)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    message = "The mobile report overflows horizontally."
    _write_browser_qa(
        output_dir,
        render_manifest,
        status="fail",
        findings=[
            {
                "code": "browser.mobile.horizontal_overflow",
                "status": "fail",
                "message": message,
                "details": {},
            }
        ],
    )

    verdict = reporting.finalize_report(output_dir)

    assert verdict["verdict"] == "incorrect"
    assert verdict["basis"]["browser_qa"] == "incorrect"
    assert message in (output_dir / "report.html").read_text(encoding="utf-8")


def test_finalize_report_rejects_stale_browser_qa(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    _require_browser_qa(output_dir)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    _write_browser_qa(output_dir, render_manifest)
    qa_path = output_dir / "browser_qa.json"
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    qa["targets"]["draft_html_sha256"] = "f" * 64
    _write_json(qa_path, qa)

    verdict = reporting.finalize_report(output_dir)

    assert verdict["verdict"] == "unable_to_determine"
    assert verdict["browser_findings"][0]["code"] == "browser_qa_stale"


def test_finalize_report_rejects_browser_qa_without_viewport_evidence(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    _require_browser_qa(output_dir)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    _write_browser_qa(output_dir, render_manifest)
    qa_path = output_dir / "browser_qa.json"
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    qa["viewports"] = []
    qa["findings"] = []
    _write_json(qa_path, qa)

    verdict = reporting.finalize_report(output_dir)

    assert verdict["verdict"] == "unable_to_determine"
    assert verdict["browser_findings"][0]["code"] == "browser_qa_invalid"


@pytest.mark.parametrize("review_condition", ["missing", "stale"])
def test_finalize_report_cannot_return_correct_without_current_mapping_review(
    tmp_path: Path,
    reporting: Any,
    review_condition: str,
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    case = _prepare_apply_case(tmp_path, reporting)
    if review_condition == "stale":
        stale_review = json.loads(json.dumps(case["review"]))
        stale_review["targets"]["mapping_content_sha256"] = "f" * 64
        case["review"] = stale_review
        _copy_mapping_provenance(output_dir, case)
    else:
        _copy_mapping_provenance(output_dir, case, include_review=False)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)

    verdict = reporting.finalize_report(output_dir)

    assert verdict["verdict"] == "unable_to_determine"
    assert verdict["basis"]["mapping_review"] == "unable_to_determine"
    assert verdict["mapping_findings"]
    assert 'data-correctness-verdict="unable_to_determine"' in (
        output_dir / "report.html"
    ).read_text(encoding="utf-8")


def test_finalize_report_marks_rejected_mapping_review_incorrect(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    case = _prepare_apply_case(tmp_path, reporting)
    rejected_review = json.loads(json.dumps(case["review"]))
    rejected_review["task_reviews"][0]["verdict"] = "unsupported"
    rejected_review["task_reviews"][0][
        "reason"
    ] = "The selected value contradicts the product text and local image evidence."
    rejected_review["overall_verdict"] = "rejected"
    rejected_review["summary"] = "One mapping is unsupported."
    case["review"] = rejected_review
    _copy_mapping_provenance(output_dir, case)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)

    verdict = reporting.finalize_report(output_dir)

    assert verdict["verdict"] == "incorrect"
    assert verdict["basis"]["mapping_review"] == "incorrect"
    assert verdict["mapping_findings"][0]["status"] == "fail"
    assert rejected_review["task_reviews"][0]["reason"] in (
        output_dir / "report.html"
    ).read_text(encoding="utf-8")


def test_finalize_report_known_mapping_failure_dominates_incomplete_semantic_review(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    case = _prepare_apply_case(tmp_path, reporting)
    rejected_review = json.loads(json.dumps(case["review"]))
    rejected_review["task_reviews"][0]["verdict"] = "unsupported"
    rejected_review["task_reviews"][0]["reason"] = "The mapping is contradicted."
    rejected_review["overall_verdict"] = "rejected"
    rejected_review["summary"] = "A mapping is known to be wrong."
    case["review"] = rejected_review
    _copy_mapping_provenance(output_dir, case)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    semantic_path = output_dir / "semantic_review.json"
    semantic = json.loads(semantic_path.read_text(encoding="utf-8"))
    semantic["claim_reviews"][0]["verdict"] = "unable_to_determine"
    semantic["claim_reviews"][0]["reason"] = "Independent review is incomplete."
    semantic["overall_verdict"] = "unable_to_determine"
    semantic["summary"] = "The report review is incomplete."
    _write_json(semantic_path, semantic)

    verdict = reporting.finalize_report(output_dir)

    assert verdict["verdict"] == "incorrect"
    assert verdict["basis"]["mapping_review"] == "incorrect"
    assert verdict["basis"]["semantic_review"] == "unable_to_determine"


def test_finalize_report_surfaces_approved_mapping_review_caveat(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    case = _prepare_apply_case(tmp_path, reporting)
    caveated_review = json.loads(json.dumps(case["review"]))
    caveated_review["task_reviews"][0]["verdict"] = "supported_with_caveat"
    caveat = "The mapping is supported, but the product image is low resolution."
    caveated_review["task_reviews"][0]["reason"] = caveat
    caveated_review["overall_verdict"] = "approved_with_caveats"
    caveated_review["summary"] = "The mappings are supported with one caveat."
    case["review"] = caveated_review
    _copy_mapping_provenance(output_dir, case)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)

    verdict = reporting.finalize_report(output_dir)

    assert verdict["verdict"] == "correct_with_caveats"
    assert verdict["basis"]["mapping_review"] == "correct_with_caveats"
    assert caveat in (output_dir / "report.html").read_text(encoding="utf-8")


def test_finalize_report_discloses_variant_mapping_coverage_gap(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    case = _prepare_apply_case(tmp_path, reporting)
    _copy_mapping_provenance(output_dir, case)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)

    verdict = reporting.finalize_report(output_dir)

    assert verdict["verdict"] == "correct_with_caveats"
    assert any(
        item["code"] == "variant_mapping_coverage_incomplete"
        for item in verdict["mapping_findings"]
    )


def test_finalize_report_discloses_resolved_central_cells_not_re_reviewed(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    case = _prepare_apply_case(tmp_path, reporting, resolved_finish=True)
    _copy_mapping_provenance(output_dir, case)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)

    verdict = reporting.finalize_report(output_dir)

    finding = next(
        item
        for item in verdict["mapping_findings"]
        if item["code"] == "central_resolved_mappings_trusted_input"
    )
    report_html = (output_dir / "report.html").read_text(encoding="utf-8")
    assert verdict["verdict"] == "correct_with_caveats"
    assert "1 pre-existing resolved attribute cell" in finding["message"]
    assert "were not re-reviewed in this run" in report_html


def test_finalize_report_discloses_correction_selection_exclusions(
    tmp_path: Path, reporting: Any
) -> None:
    def add_correction_scope(tasks: dict[str, Any]) -> None:
        tasks["coverage"]["include_resolved"] = True
        tasks["correction_selection"] = {
            "schema_version": "attribute_reporting.correction_task_selection.v1",
            "criteria": {},
            "task_count_before_selection": 7,
            "task_count": 2,
            "excluded_unresolved_count": 2,
            "excluded_non_codex_effective_count": 3,
            "excluded_not_pinned_count": 0,
        }

    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    case = _prepare_apply_case(
        tmp_path,
        reporting,
        tasks_mutator=add_correction_scope,
    )
    _copy_mapping_provenance(output_dir, case)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)

    verdict = reporting.finalize_report(output_dir)

    finding_codes = {item["code"] for item in verdict["mapping_findings"]}
    report_html = (output_dir / "report.html").read_text(encoding="utf-8")
    assert verdict["verdict"] == "correct_with_caveats"
    assert "correction_unresolved_cells_not_reviewed" in finding_codes
    assert "correction_non_codex_effective_cells_not_reviewed" in finding_codes
    assert "2 unresolved attribute cells" in report_html
    assert "3 resolved attribute cells" in report_html


def test_finalize_report_no_work_uses_not_applicable_review_with_visible_basis(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir, output_dir = _write_report_artifacts(tmp_path)
    _write_preliminary_sanitization_receipt(package_dir)
    download_receipt, extraction_receipt = _write_transport_receipts(
        package_dir,
        tmp_path / "transport",
    )
    _attach_transport_lineage(
        reporting,
        package_dir=package_dir,
        output_dir=output_dir,
        download_receipt=download_receipt,
        extraction_receipt=extraction_receipt,
    )
    workset_path = tmp_path / "mapping" / "workset.json"
    _write_no_work_workset(workset_path, resolved_attribute_cells=6)
    _attach_no_work_mapping_basis(
        reporting,
        output_dir=output_dir,
        workset_path=workset_path,
    )
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)

    verdict = reporting.finalize_report(output_dir)

    report_html = (output_dir / "report.html").read_text(encoding="utf-8")
    assert verdict["verdict"] == "correct_with_caveats"
    assert verdict["basis"]["mapping_review"] == "not_applicable"
    assert verdict["mapping_findings"][0]["code"] == (
        "mapping_no_work_trusted_current_package"
    )
    assert any(
        item["code"] == "variant_mapping_coverage_incomplete"
        for item in verdict["mapping_findings"]
    )
    assert "6 pre-existing resolved attribute cells" in report_html
    assert "mapping review is not applicable" in report_html
    assert "2 variant-level attribute cells" in report_html


def test_finalize_report_cannot_ignore_deleted_intake_pinned_mapping_provenance(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    case = _prepare_apply_case(tmp_path, reporting)
    _copy_mapping_provenance(output_dir, case)
    artifact_hashes = {
        file_name: _sha256(output_dir / file_name)
        for file_name in (
            "mapping_tasks.json",
            "mapping_decisions.json",
            "validated_mappings.json",
            "mapping_review.json",
        )
    }
    _write_json(
        output_dir / "run_intake.json",
        {
            "inputs": {
                "mapping_provenance": {
                    "artifacts": artifact_hashes,
                    "server_acceptance": {
                        "status": "local_review_only",
                        "artifacts": {},
                    },
                }
            }
        },
    )
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    for file_name in artifact_hashes:
        (output_dir / file_name).unlink()

    verdict = reporting.finalize_report(output_dir)

    assert verdict["verdict"] == "unable_to_determine"
    assert verdict["basis"]["mapping_review"] == "unable_to_determine"
    assert verdict["mapping_findings"][0]["code"] == (
        "mapping_review_artifacts_missing"
    )


@pytest.mark.parametrize(
    ("mutate_review", "expected_message"),
    [
        pytest.param(
            _add_claim_review_caveat,
            "The claim needs a visible caveat.",
            id="claim",
        ),
        pytest.param(
            _add_dimension_review_caveat,
            "The story has a visible coherence caveat.",
            id="dimension",
        ),
        pytest.param(
            _add_overall_review_caveat,
            "The overall review has a visible caveat.",
            id="overall",
        ),
    ],
)
def test_finalize_report_makes_semantic_caveats_visible(
    tmp_path: Path,
    reporting: Any,
    mutate_review: Callable[[dict[str, Any]], None],
    expected_message: str,
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    review_path = output_dir / "semantic_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    mutate_review(review)
    _write_json(review_path, review)

    verdict = reporting.finalize_report(output_dir)

    report_html = (output_dir / "report.html").read_text(encoding="utf-8")
    run_review = (output_dir / "codex_run_review.md").read_text(encoding="utf-8")
    assert verdict["verdict"] == "correct_with_caveats"
    assert any(
        item.get("status") == "caveat" and item["message"] == expected_message
        for item in verdict["semantic_findings"]
    )
    assert any(item["message"] == expected_message for item in verdict["caveats"])
    assert expected_message in report_html
    assert expected_message in run_review


@pytest.mark.parametrize(
    ("claim_verdict", "expected_verdict", "reason"),
    [
        pytest.param(
            "unsupported",
            "incorrect",
            "The claim is unsupported by the reviewed evidence.",
            id="incorrect",
        ),
        pytest.param(
            "unable_to_determine",
            "unable_to_determine",
            "The reviewer cannot determine whether the claim is supported.",
            id="unable-to-determine",
        ),
    ],
)
def test_finalize_report_makes_non_pass_semantic_reason_visible_in_html(
    tmp_path: Path,
    reporting: Any,
    claim_verdict: str,
    expected_verdict: str,
    reason: str,
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    review_path = output_dir / "semantic_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["claim_reviews"][0]["verdict"] = claim_verdict
    review["claim_reviews"][0]["reason"] = reason
    _write_json(review_path, review)

    verdict = reporting.finalize_report(output_dir)

    report_html = (output_dir / "report.html").read_text(encoding="utf-8")
    assert verdict["verdict"] == expected_verdict
    assert f'data-correctness-verdict="{expected_verdict}"' in report_html
    assert reason in report_html


def test_finalize_report_makes_image_review_caveat_visible(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir, output_dir = _write_report_artifacts(tmp_path)
    image_name = "images/featured.png"
    image_path = package_dir / image_name
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 64)
    _write_csv(
        package_dir / "top_seller_products.csv",
        [
            {
                "parent_product_id": "featured-product",
                "product_name": "Featured Product",
                "brand": "Example Brand",
                "pdp_url": "https://example.com/featured-product",
                "pack_image_file": image_name,
            }
        ],
    )
    model_path = output_dir / "report_model.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model["featured_products"] = [
        {
            "product_id": "featured-product",
            "role": "winning_now",
            "rationale": "This product illustrates the bound claim.",
            "supporting_claim_ids": [CLAIM_ID],
        }
    ]
    _write_json(model_path, model)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    image_record = render_manifest["featured_products"][0]
    review_path = output_dir / "semantic_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    image_message = "The local product image has a visible caveat."
    review["images_reviewed"] = [
        {
            "product_id": image_record["product_id"],
            "image_path": image_record["image_path"],
            "image_sha256": image_record["image_sha256"],
            "status": "caveat",
            "observation": image_message,
        }
    ]
    _write_json(review_path, review)

    verdict = reporting.finalize_report(output_dir)

    report_html = (output_dir / "report.html").read_text(encoding="utf-8")
    assert verdict["verdict"] == "correct_with_caveats"
    assert any(item["message"] == image_message for item in verdict["caveats"])
    assert image_message in report_html


@pytest.mark.parametrize(
    ("mutate_source", "expected_finding"),
    [
        pytest.param(
            _change_summary_source,
            "source_sha256_mismatch",
            id="source-hash",
        ),
        pytest.param(_remove_summary_source, "source_missing", id="source-missing"),
    ],
)
def test_finalize_report_source_findings_fail_package_integrity_basis(
    tmp_path: Path,
    reporting: Any,
    mutate_source: Callable[[Path], None],
    expected_finding: str,
) -> None:
    package_dir, output_dir = _write_report_artifacts(tmp_path)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    mutate_source(package_dir)

    verdict = reporting.finalize_report(output_dir)

    finding_codes = {item["code"] for item in verdict["mechanical_findings"]}
    assert expected_finding in finding_codes
    assert verdict["verdict"] == "incorrect"
    assert verdict["basis"]["package_integrity"] == "fail"


def test_finalize_report_detects_mutated_used_csv_omitted_from_pack_manifest(
    tmp_path: Path, reporting: Any
) -> None:
    package_dir, output_dir = _write_report_artifacts(tmp_path)
    source_name = "top_seller_pairs.csv"
    source_path = package_dir / source_name
    original_row = _bundle_evidence_row("finish_dewy")
    _write_csv(source_path, [original_row])
    catalog_path = output_dir / "evidence_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["sources"] = [
        {
            "file": source_name,
            "status": "available",
            "sha256": _sha256(source_path),
            "row_count": 1,
            "columns": list(original_row),
            "preview": [original_row],
        }
    ]
    _write_json(catalog_path, catalog)
    model_path = output_dir / "report_model.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model["claims"][0]["text_template"] = "The focus share is {{focus-share}}."
    model["claims"][0]["evidence_refs"] = [
        _bundle_share_ref(
            "focus-share",
            source=source_name,
            bundle_key="finish_dewy",
            field="pct_top_seller",
        )
    ]
    _write_json(model_path, model)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    mutated_row = {**original_row, "pct_top_seller": "0.70"}
    _write_csv(source_path, [mutated_row])

    verdict = reporting.finalize_report(output_dir)

    finding_codes = {item["code"] for item in verdict["mechanical_findings"]}
    assert verdict["verdict"] == "incorrect"
    assert "source_catalog_sha256_mismatch" in finding_codes
    assert "source_ledger_sha256_mismatch" in finding_codes
    assert verdict["basis"]["package_integrity"] == "fail"


def test_finalize_report_rejects_warning_injected_after_catalog_review(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    catalog_path = output_dir / "evidence_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["warnings"].append(
        {
            "code": "late-warning",
            "message": "A warning was injected after semantic review.",
            "source": "tampered-catalog",
        }
    )
    _write_json(catalog_path, catalog)

    verdict = reporting.finalize_report(output_dir)

    finding_codes = {item["code"] for item in verdict["mechanical_findings"]}
    assert verdict["verdict"] == "incorrect"
    assert "catalog_sha256_mismatch" in finding_codes


def test_finalize_report_rejects_package_warning_deleted_from_catalog_after_render(
    tmp_path: Path, reporting: Any
) -> None:
    warning_code = "coverage-caveat"
    _package_dir, output_dir = _write_report_artifacts(
        tmp_path,
        package_warning=(warning_code, "Coverage requires a visible caveat."),
    )
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    catalog_path = output_dir / "evidence_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["warnings"] = []
    _write_json(catalog_path, catalog)

    verdict = reporting.finalize_report(output_dir)

    finding_codes = {item["code"] for item in verdict["mechanical_findings"]}
    assert verdict["verdict"] == "incorrect"
    assert "catalog_sha256_mismatch" in finding_codes
    assert "catalog_warning_mismatch" in finding_codes
    assert verdict["basis"]["package_integrity"] == "fail"


def test_finalize_report_cannot_return_correct_when_semantic_review_fails(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    review_path = output_dir / "semantic_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["report_level_findings"] = [
        {
            "code": "story_overstatement",
            "status": "fail",
            "finding": "The report-level story overstates the supported evidence.",
        }
    ]
    _write_json(review_path, review)

    verdict = reporting.finalize_report(output_dir)

    semantic_codes = {item["code"] for item in verdict["semantic_findings"]}
    assert verdict["verdict"] == "incorrect"
    assert verdict["basis"]["semantic_review"] == "incorrect"
    assert "story_overstatement" in semantic_codes
    assert 'data-correctness-verdict="incorrect"' in (
        output_dir / "report.html"
    ).read_text(encoding="utf-8")


def test_finalize_report_marks_tampered_html_incorrect(
    tmp_path: Path, reporting: Any
) -> None:
    _package_dir, output_dir = _write_report_artifacts(tmp_path)
    render_manifest = reporting.render_report(output_dir)
    _write_supported_review(output_dir, render_manifest)
    draft_path = output_dir / "report_draft.html"
    draft = draft_path.read_text(encoding="utf-8")
    draft_path.write_text(
        draft.replace(
            "The evidence contains 12 products.",
            "The evidence contains 13 products.",
        ),
        encoding="utf-8",
    )

    verdict = reporting.finalize_report(output_dir)

    finding_codes = {item["code"] for item in verdict["mechanical_findings"]}
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert verdict["verdict"] == "incorrect"
    assert "draft_sha256_mismatch" in finding_codes
    assert verdict["basis"]["html_parity"] == "fail"
    assert final_artifacts["status"] == "not_ready"


def test_store_atomic_attribute_write_checks_identities_and_commits_once() -> None:
    from modules.pdp.store import (
        AttributeAuditRecord,
        AttributeValueRecord,
        PDPStore,
    )

    connection = _RecordingConnection()
    connection_owners: list[str] = []

    @contextmanager
    def write_connection(owner: str):
        connection_owners.append(owner)
        yield connection

    store = PDPStore.__new__(PDPStore)
    store._write_connection = write_connection
    value_records = [
        AttributeValueRecord(
            retailer="retailer",
            row_type="parent",
            parent_product_id="product-one",
            variant_id="",
            category_key="skin-care",
            attribute_id="finish",
            attribute_label="Finish",
            value="Dewy",
            oov_candidate=None,
            note=None,
            source="codex",
            updated_at="2026-07-15T09:00:00Z",
        ),
        AttributeValueRecord(
            retailer="retailer",
            row_type="variant",
            parent_product_id="product-one",
            variant_id="variant-one",
            category_key="skin-care",
            attribute_id="shade",
            attribute_label="Shade",
            value="Light",
            oov_candidate=None,
            note=None,
            source="codex",
            updated_at="2026-07-15T09:00:00Z",
        ),
    ]
    audit_records = [
        AttributeAuditRecord(
            timestamp="2026-07-15T09:00:00Z",
            source="codex",
            row_type=record.row_type,
            retailer=record.retailer,
            parent_product_id=record.parent_product_id,
            variant_id=record.variant_id,
            attribute_id=record.attribute_id,
            value=record.value,
            decision_rule="codex_mapped",
            evidence_json="{}",
            category_key=record.category_key,
        )
        for record in value_records
    ]

    store.upsert_attribute_values_with_audit(value_records, audit_records)

    executed_sql = [sql for sql, _params in connection.execute_calls]
    inserted_sql = [sql for sql, _rows in connection.executemany_calls]
    assert connection_owners == ["upsert_attribute_values_with_audit"]
    assert sum("FROM parent_products" in sql for sql in executed_sql) == 2
    assert sum("FROM variants" in sql for sql in executed_sql) == 1
    assert len(connection.executemany_calls) == 2
    assert "INSERT INTO pdp_attribute_values" in inserted_sql[0]
    assert "INSERT INTO pdp_attribute_audit" in inserted_sql[1]
    assert len(connection.executemany_calls[0][1]) == 2
    assert len(connection.executemany_calls[1][1]) == 2
    assert connection.commit_count == 1
    assert connection.transaction_replay_disabled is True


def test_store_atomic_attribute_write_rejects_missing_variant_without_commit() -> None:
    from modules.pdp.store import (
        AttributeAuditRecord,
        AttributeValueRecord,
        PDPStore,
    )

    connection = _RecordingConnection(variant_exists=False)

    @contextmanager
    def write_connection(_owner: str):
        yield connection

    store = PDPStore.__new__(PDPStore)
    store._write_connection = write_connection
    value_record = AttributeValueRecord(
        retailer="retailer",
        row_type="variant",
        parent_product_id="product-one",
        variant_id="missing-variant",
        category_key="skin-care",
        attribute_id="shade",
        attribute_label="Shade",
        value="Light",
        oov_candidate=None,
        note=None,
        source="codex",
        updated_at="2026-07-15T09:00:00Z",
    )
    audit_record = AttributeAuditRecord(
        timestamp="2026-07-15T09:00:00Z",
        source="codex",
        row_type="variant",
        retailer="retailer",
        parent_product_id="product-one",
        variant_id="missing-variant",
        attribute_id="shade",
        value="Light",
        decision_rule="codex_mapped",
        evidence_json="{}",
        category_key="skin-care",
    )

    with pytest.raises(ValueError, match="target variant does not exist"):
        store.upsert_attribute_values_with_audit([value_record], [audit_record])

    assert len(connection.execute_calls) == 2
    assert connection.executemany_calls == []
    assert connection.commit_count == 0
    assert connection.transaction_replay_disabled is True


@pytest.mark.parametrize(
    ("include_value", "include_audit"),
    [
        pytest.param(True, False, id="missing-audit"),
        pytest.param(False, True, id="missing-value"),
    ],
)
def test_store_atomic_attribute_write_rejects_unpaired_records_before_transaction(
    include_value: bool,
    include_audit: bool,
) -> None:
    from modules.pdp.store import PDPStore

    value_record, audit_record = _attribute_record_pair()
    connection_owners: list[str] = []

    @contextmanager
    def write_connection(owner: str):
        connection_owners.append(owner)
        yield _RecordingConnection()

    store = PDPStore.__new__(PDPStore)
    store._write_connection = write_connection
    value_records = [value_record] if include_value else []
    audit_records = [audit_record] if include_audit else []

    with pytest.raises(ValueError, match="one matching audit row per value"):
        store.upsert_attribute_values_with_audit(value_records, audit_records)

    assert connection_owners == []


def test_store_atomic_attribute_write_existing_operation_is_idempotent() -> None:
    from modules.pdp.store import PDPStore

    operation_id = "a" * 64
    connection = _RecordingConnection(operation_applied=True)

    @contextmanager
    def write_connection(_owner: str):
        yield connection

    store = PDPStore.__new__(PDPStore)
    store._write_connection = write_connection
    value_record, audit_record = _attribute_record_pair()

    wrote_database = store.upsert_attribute_values_with_audit(
        [value_record],
        [audit_record],
        operation_id=operation_id,
    )

    assert wrote_database is False
    assert len(connection.execute_calls) == 2
    assert "pg_advisory_xact_lock" in connection.execute_calls[0][0]
    assert "codex_mapping_batch" in connection.execute_calls[1][0]
    assert connection.executemany_calls == []
    assert connection.commit_count == 0
    assert connection.transaction_replay_disabled is True


def test_store_atomic_attribute_write_does_not_commit_when_audit_insert_fails() -> None:
    from modules.pdp.store import PDPStore

    class AuditFailingConnection(_RecordingConnection):
        def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
            super().executemany(sql, rows)
            if "INSERT INTO pdp_attribute_audit" in sql:
                raise RuntimeError("audit insert failed")

    connection = AuditFailingConnection()

    @contextmanager
    def write_connection(_owner: str):
        yield connection

    store = PDPStore.__new__(PDPStore)
    store._write_connection = write_connection
    value_record, audit_record = _attribute_record_pair()

    with pytest.raises(RuntimeError, match="audit insert failed"):
        store.upsert_attribute_values_with_audit([value_record], [audit_record])

    inserted_sql = [sql for sql, _rows in connection.executemany_calls]
    assert len(inserted_sql) == 2
    assert "INSERT INTO pdp_attribute_values" in inserted_sql[0]
    assert "INSERT INTO pdp_attribute_audit" in inserted_sql[1]
    assert connection.commit_count == 0
    assert connection.transaction_replay_disabled is True
