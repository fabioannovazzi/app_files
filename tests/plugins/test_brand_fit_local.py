from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "plugins" / "attribute-reporting" / "scripts" / "brand_fit.py"
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00"
)


@pytest.fixture
def brand_fit() -> ModuleType:
    spec = importlib.util.spec_from_file_location("brand_fit_local_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_brand_fit_helpers_do_not_call_a_model_provider_api() -> None:
    script_root = SCRIPT_PATH.parent
    combined = "\n".join(
        (script_root / name).read_text(encoding="utf-8")
        for name in (
            "brand_fit.py",
            "prepare_brand_fit_run.py",
            "render_brand_fit_report.py",
            "check_brand_fit_report.py",
        )
    ).casefold()

    assert "import openai" not in combined
    assert "query_llm" not in combined
    assert "api_key" not in combined


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def brand_fit_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _write_csv(
    path: Path, rows: list[dict[str, str]], fields: list[str] | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = fields or list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _source_run(tmp_path: Path, *, verdict: str = "correct") -> Path:
    run = tmp_path / "retailer-report"
    run.mkdir()
    receipt = {
        "schema_version": "attribute_reporting.local_download_receipt.v1",
        "job_id": "e" * 32,
        "path": str(tmp_path / "retailer.zip"),
        "sha256": "a" * 64,
        "size_bytes": 1,
    }
    _write_json(run / "local_download_receipt.json", receipt)
    catalog = {
        "schema_version": "attribute_reporting.evidence_catalog.v1",
        "report_id": "source-retailer-report",
        "transport_lineage": {
            "download": {
                "job_id": "e" * 32,
                "archive_sha256": "a" * 64,
            },
            "artifacts": {
                "local_download_receipt.json": _sha(run / "local_download_receipt.json")
            },
        },
    }
    _write_json(run / "evidence_catalog.json", catalog)
    model = {
        "schema_version": "attribute_reporting.report_model.v1",
        "report_id": "source-retailer-report",
        "author": {"execution": "codex_agent", "agent_id": "source-author"},
        "claims": [{"claim_id": "source-claim"}],
    }
    ledger = {
        "schema_version": "attribute_reporting.claim_ledger.v1",
        "report_id": "source-retailer-report",
        "claims": [],
    }
    _write_json(run / "report_model.json", model)
    _write_json(run / "claim_ledger.json", ledger)
    placeholder = (
        "<!-- ATTRIBUTE_REPORTING_VERDICT -->"
        '<aside class="verdict unable_to_determine provisional" '
        'data-correctness-verdict="pending">'
        '<span class="mark">?</span><div><strong>Correctness review pending</strong>'
        "<span>The final evidence-backed verdict will replace this banner after "
        "independent semantic review and browser QA.</span></div></aside>"
    )
    draft = f"<!doctype html><main>{placeholder}<p>Retailer Signals</p></main>"
    (run / "report_draft.html").write_text(draft, encoding="utf-8")
    render = {
        "schema_version": "attribute_reporting.render_manifest.v1",
        "report_id": "source-retailer-report",
        "evidence_catalog_sha256": brand_fit_hash(catalog),
        "report_model_sha256": brand_fit_hash(model),
        "claim_ledger_sha256": brand_fit_hash(ledger),
        "draft_html": "report_draft.html",
        "draft_html_sha256": _sha(run / "report_draft.html"),
        "featured_products": [],
    }
    _write_json(run / "render_manifest.json", render)
    review = {
        "schema_version": "attribute_reporting.semantic_review.v1",
        "review_id": "source-semantic-review",
        "reviewer": {
            "execution": "codex_agent",
            "agent_id": "source-reviewer",
            "role": "independent_reviewer",
            "independent_from_author": True,
        },
        "author_agent_id": "source-author",
        "targets": {
            "report_id": "source-retailer-report",
            "evidence_catalog_sha256": render["evidence_catalog_sha256"],
            "report_model_sha256": render["report_model_sha256"],
            "draft_html_sha256": render["draft_html_sha256"],
        },
        "overall_verdict": verdict,
        "summary": "Independent source review completed.",
        "dimensions": {
            dimension: {"status": "pass", "rationale": "Reviewed and supported."}
            for dimension in (
                "claim_coverage",
                "story_coherence",
                "importance_calibration",
                "caveat_handling",
                "brand_and_example_interpretation",
                "html_readability",
            )
        },
        "claim_reviews": [
            {
                "claim_id": "source-claim",
                "verdict": (
                    "supported_with_caveat"
                    if verdict == "correct_with_caveats"
                    else "supported"
                ),
                "reason": "The source claim is supported by its reviewed evidence.",
            }
        ],
        "report_level_findings": [],
        "images_reviewed": [],
    }
    _write_json(run / "semantic_review.json", review)
    _write_json(
        run / "correctness_verdict.json",
        {
            "schema_version": "attribute_reporting.correctness_verdict.v1",
            "report_id": "source-retailer-report",
            "verdict": verdict,
            "label": ("Correct" if verdict == "correct" else "Correct with caveats"),
            "basis": {
                "package_integrity": "pass",
                "mechanical_claims": "pass",
                "html_parity": "pass",
                "mapping_review": "not_applicable",
                "browser_qa": "not_applicable",
                "semantic_review": verdict,
            },
            "mechanical_findings": [],
            "mapping_findings": [],
            "browser_findings": [],
            "semantic_findings": [],
            "caveats": (
                [{"code": "source-caveat", "message": "Reviewed source caveat."}]
                if verdict == "correct_with_caveats"
                else []
            ),
            "active_warning_codes": [],
            "report_model_sha256": render["report_model_sha256"],
            "draft_html_sha256": render["draft_html_sha256"],
            "mapping_review_sha256": None,
            "mapping_review_validation_sha256": None,
            "browser_qa_sha256": None,
            "semantic_review_sha256": brand_fit_hash(review),
        },
    )
    report = run / "report.html"
    report.write_text(
        draft.replace(
            placeholder,
            f'<aside class="verdict" data-correctness-verdict="{verdict}">Checked</aside>',
        ),
        encoding="utf-8",
    )
    _write_json(
        run / "final_artifacts.json",
        {
            "schema_version": "attribute_reporting.final_artifacts.v1",
            "status": "final_ready",
            "report_id": "source-retailer-report",
            "correctness_verdict": verdict,
            "privacy": {"storage": "private_local_only", "uploaded_to_server": False},
            "outputs": [
                {"path": "report.html", "sha256": _sha(report)},
                {
                    "path": "correctness_verdict.json",
                    "sha256": _sha(run / "correctness_verdict.json"),
                },
            ],
        },
    )
    return run


def _package_and_receipts(
    tmp_path: Path,
    brand_fit: ModuleType,
    source_run: Path,
    *,
    duplicate_signal: bool = False,
    server_image: bool = False,
    source_job_override: str | None = None,
    embedded_image_data: bool = False,
    missing_mapping_snapshot: bool = False,
    mapping_scope_override: str | None = None,
    stale_pack_manifest: bool = False,
    disguised_binary_name: str | None = None,
    portable_note: str | None = None,
    embedded_field_name: str | None = None,
    blank_embedded_field_name: str | None = None,
) -> tuple[Path, Path, Path]:
    package = tmp_path / "brand-fit-package"
    package.mkdir()
    source = brand_fit.completed_retailer_report(source_run)
    signal_rows = [
        {
            "bundle_id": "bundle-one",
            "bundle_label": "Soft structure",
            "signal_layers": "winning_now",
            "signal_score": "high",
        }
    ]
    if duplicate_signal:
        signal_rows.append(dict(signal_rows[0]))
    rows_by_name: dict[str, tuple[list[dict[str, str]], list[str] | None]] = {
        "signal_bundles.csv": (signal_rows, None),
        "plain_language_signal_guide.csv": (
            [
                {
                    "signal_name": "Soft structure",
                    "plain_english_read": "Visible retailer signal",
                }
            ],
            None,
        ),
        "attribute_coverage.csv": ([{"attribute": "form", "coverage": "broad"}], None),
        "retailer_brand_anchors.csv": (
            [
                {
                    "parent_product_id": "shared-product",
                    "product_name": "Retailer Cardigan",
                    "product_scope": "brand_at_retailer",
                    "anchor_status": "current",
                    "pdp_url": "https://example.com/retailer-cardigan",
                    "hero_image_url": "https://cdn.example.com/retailer.png",
                }
            ],
            None,
        ),
        "retailer_brand_anchor_signal_fit.csv": (
            [
                {
                    "parent_product_id": "shared-product",
                    "bundle_id": "bundle-one",
                    "fit_status": "matched",
                }
            ],
            None,
        ),
        "retailer_live_presence_audit.csv": ([], ["product_id", "status"]),
        "brand_at_retailer_review_validation.csv": (
            [],
            ["product_id", "review_status"],
        ),
        "brand_at_retailer_bundle_matches.csv": (
            [
                {
                    "product_key": "shared-product",
                    "bundle_id": "bundle-one",
                    "bundle_label": "Soft structure",
                }
            ],
            None,
        ),
        "manufacturer_catalog_products.csv": (
            [
                {
                    "parent_product_id": "shared-product",
                    "product_name": "Owned Cardigan",
                    "product_scope": "owned_catalogue",
                    "brand": "Example Brand",
                    "pdp_url": "https://brand.example/owned-cardigan",
                    "hero_image_url": "https://cdn.example.com/owned.png",
                }
            ],
            None,
        ),
        "manufacturer_products_not_at_retailer.csv": (
            [
                {
                    "parent_product_id": "owned-only",
                    "product_name": "Owned Pullover",
                    "product_scope": "owned_catalogue",
                }
            ],
            None,
        ),
        "manufacturer_catalog_bundle_matches.csv": (
            [
                {
                    "product_key": "shared-product",
                    "bundle_id": "bundle-one",
                    "bundle_label": "Soft structure",
                }
            ],
            None,
        ),
        "reference_candidates.csv": (
            [
                {
                    "parent_product_id": "owned-only",
                    "product_name": "Owned Pullover",
                    "product_scope": "candidate",
                    "matched_bundle_labels": "Soft structure",
                    "reference_rationale": "Candidate lead for Codex review",
                }
            ],
            None,
        ),
        "image_index.csv": (
            [{"parent_product_id": "shared-product", "image_available": "true"}],
            None,
        ),
    }
    for name in brand_fit.EVIDENCE_FILES:
        rows, fields = rows_by_name[name]
        _write_csv(package / name, rows, fields)
    if embedded_image_data:
        rows_by_name["manufacturer_catalog_products.csv"][0][0][
            "hero_image_url"
        ] = "data:image/png;base64,iVBORw0KGgo"
        _write_csv(
            package / "manufacturer_catalog_products.csv",
            rows_by_name["manufacturer_catalog_products.csv"][0],
        )
    snapshot_core = {
        "scope": {
            "retailer": "example-retailer",
            "retailer_category_keys": ["sweaters"],
            "brand_source_retailer": "brand-owned",
            "owned_category_keys": ["sweaters"],
        },
        "batch_generated_at": "2026-07-17T08:00:00+00:00",
        "entries": [
            {
                "name": name,
                "payload_sha256": character * 64,
                "payload_size_bytes": index + 1,
                "generated_at": "2026-07-17T08:00:00+00:00",
            }
            for index, (name, character) in enumerate(
                zip(
                    ("parent_filtered", "variant_result", "combined", "parents_all"),
                    ("1", "2", "3", "4"),
                    strict=True,
                )
            )
        ],
    }
    mapping_scopes: list[dict[str, Any]] = []
    for retailer_name in ("brand-owned", "example-retailer"):
        scope = {
            "source": "codex",
            "retailer": (
                mapping_scope_override
                if retailer_name == "example-retailer" and mapping_scope_override
                else retailer_name
            ),
            "category_key": "sweaters",
        }
        core = {"scope": scope, "groups": []}
        mapping_scopes.append(
            {
                "schema_version": "attribute_reporting.server_bridge.mapping_state_snapshot.v1",
                **core,
                "state_sha256": brand_fit_hash(core),
                "captured_at": "2026-07-17T08:30:00+00:00",
            }
        )
    mapping_core = {
        "scopes": [
            {"scope": scope["scope"], "state_sha256": scope["state_sha256"]}
            for scope in mapping_scopes
        ]
    }
    mapping_snapshot = {
        "schema_version": "attribute_reporting.server_bridge.brand_fit_mapping_state_snapshot.v1",
        "captured_at": "2026-07-17T08:30:00+00:00",
        "scopes": mapping_scopes,
        "state_sha256": brand_fit_hash(mapping_core),
    }
    summary = {
        "analysis_type": "brand_retailer_reference_handoff",
        "retailer": "example-retailer",
        "category_key": "sweaters",
        "brand_name": "Example Brand",
        "brand_source_retailer": "brand-owned",
        "source_retailer_report": {
            "sha256": source["sha256"],
            "verdict": source["verdict"],
        },
        "source_retailer_evidence": {
            "job_id": source_job_override or source["job_id"],
            "package_sha256": source["package_sha256"],
        },
        "retailer_presence": {
            "mode": "current_database_snapshot",
            "read_at": "2026-07-17T09:00:00+00:00",
        },
        "product_data_snapshot": {
            "schema_version": "attribute_reporting.server_bridge.product_data_snapshot.v1",
            **snapshot_core,
            "snapshot_sha256": brand_fit_hash(snapshot_core),
            "read_at": "2026-07-17T09:00:00+00:00",
        },
        "mapping_state_snapshot_sha256": mapping_snapshot["state_sha256"],
        "package_warning_count": 0,
        "package_warnings": [],
    }
    if portable_note is not None:
        summary["portable_note"] = portable_note
    if embedded_field_name is not None:
        summary[embedded_field_name] = "opaque-image-payload"
    if blank_embedded_field_name is not None:
        summary[blank_embedded_field_name] = None
    _write_json(package / "summary.json", summary)
    _write_json(package / "package_integrity.json", {"status": "pass"})
    _write_json(
        package / "package_warnings.json",
        {"status": "pass", "warning_count": 0, "warnings": []},
    )
    _write_json(
        package / "server_sanitization_receipt.json",
        {
            "schema_version": "attribute_reporting.server_bridge.package_sanitization.v1",
            "image_policy": "urls_only_no_image_bytes",
            "removed_image_file_count": 0,
            "sanitized_private_path_field_count": 0,
            "mapping_provenance": {},
            "package_integrity_status": "pass",
        },
    )
    if not missing_mapping_snapshot:
        _write_json(package / "mapping_state_snapshot.json", mapping_snapshot)
    if server_image:
        image_path = package / "images" / "server.png"
        image_path.parent.mkdir()
        image_path.write_bytes(PNG_BYTES)
    if disguised_binary_name:
        (package / disguised_binary_name).write_bytes(PNG_BYTES)
    manifest_files = sorted(
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file() and path.name != "pack_manifest.json"
    )
    manifest_summary = dict(summary)
    if stale_pack_manifest:
        manifest_summary["brand_name"] = "Stale Brand"
    _write_json(
        package / "pack_manifest.json",
        {
            "package_type": "brand_retailer_reference_handoff",
            "files": manifest_files,
            "summary": manifest_summary,
        },
    )

    archive = tmp_path / "brand-fit.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(package).as_posix())
    extracted_files = [
        {
            "path": path.relative_to(package).as_posix(),
            "sha256": _sha(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(package.rglob("*"))
        if path.is_file()
    ]
    download = tmp_path / "brand-fit-download.json"
    extraction = tmp_path / "brand-fit-extraction.json"
    _write_json(
        download,
        {
            "schema_version": "attribute_reporting.local_download_receipt.v1",
            "job_id": "b" * 32,
            "path": str(archive),
            "sha256": _sha(archive),
            "size_bytes": archive.stat().st_size,
        },
    )
    _write_json(
        extraction,
        {
            "schema_version": "attribute_reporting.local_extraction_receipt.v1",
            "archive_path": str(archive),
            "archive_sha256": _sha(archive),
            "output_dir": str(package),
            "file_count": len(extracted_files),
            "total_size_bytes": sum(item["size_bytes"] for item in extracted_files),
            "files": extracted_files,
        },
    )
    local_image = package / "images" / "local" / "retailer.png"
    local_image.parent.mkdir(parents=True, exist_ok=True)
    local_image.write_bytes(PNG_BYTES)
    image_sources = (
        "retailer_brand_anchors.csv",
        "manufacturer_catalog_products.csv",
        "manufacturer_products_not_at_retailer.csv",
        "reference_candidates.csv",
    )
    image_products: list[dict[str, Any]] = []
    for name in image_sources:
        row = rows_by_name[name][0][0]
        product_id = str(
            row.get("parent_product_id")
            or row.get("product_key")
            or row.get("listing_identity")
            or ""
        )
        product_scope = str(row.get("product_scope") or name.removesuffix(".csv"))
        row_sha = brand_fit._row_sha256(row)
        image_products.append(
            {
                "record_id": f"{name}:{product_scope}:{product_id}",
                "product_id": product_id,
                "source_rows": {name: row_sha},
                "source_row_sha256": row_sha,
                "status": "downloaded",
                "image_path": "images/local/retailer.png",
                "sha256": _sha(local_image),
                "byte_count": len(PNG_BYTES),
            }
        )
    _write_json(
        package / "local_image_manifest.json",
        {
            "schema_version": "attribute_reporting.local_image_manifest.v1",
            "source_table_sha256": {
                name: _sha(package / name) for name in image_sources
            },
            "policy": {
                "storage": "local_machine_only",
                "uploaded_to_server": False,
                "analytical_package_files_modified": False,
            },
            "products": image_products,
            "summary": {
                "product_count": 4,
                "available_count": 4,
                "failure_count": 0,
                "unavailable_count": 0,
                "not_attempted_count": 0,
                "status": "complete",
            },
        },
    )
    return package, download, extraction


def _author_model(output: Path) -> None:
    model = json.loads((output / "report_model.json").read_text(encoding="utf-8"))
    model["authoring_status"] = "codex_complete"
    model["title"] = "Example Brand Fit"
    model["subtitle"] = "Retailer signals, current presence, and owned catalogue"
    model["claims"] = [
        {
            "claim_id": "retailer-signal",
            "kind": "deterministic",
            "headline": "Retailer signal",
            "text_template": "The retailer signal is {{signal.bundle_label}} in {{signal.signal_layers}}.",
            "interpretation": "This is source evidence, not an automatic recommendation.",
            "caveat": "",
            "confidence": "high",
            "evidence_refs": [
                {
                    "ref_id": "signal",
                    "source": "evidence/brand_fit/signal_bundles.csv",
                    "selector": {"match": {"bundle_id": "bundle-one"}},
                    "fields": ["bundle_label", "signal_layers"],
                }
            ],
            "supporting_claim_ids": [],
        },
        {
            "claim_id": "current-presence",
            "kind": "deterministic",
            "headline": "Current retailer presence",
            "text_template": "The current brand anchor is {{anchor.product_name}} with status {{anchor.anchor_status}}.",
            "interpretation": "The anchor describes the stored current retailer presence.",
            "caveat": "",
            "confidence": "high",
            "evidence_refs": [
                {
                    "ref_id": "anchor",
                    "source": "evidence/brand_fit/retailer_brand_anchors.csv",
                    "selector": {"match": {"parent_product_id": "shared-product"}},
                    "fields": ["product_name", "anchor_status"],
                }
            ],
            "supporting_claim_ids": [],
        },
        {
            "claim_id": "owned-catalogue",
            "kind": "deterministic",
            "headline": "Owned catalogue",
            "text_template": "The owned catalogue includes {{owned.product_name}} from {{owned.brand}}.",
            "interpretation": "This row establishes the wider brand-owned product scope.",
            "caveat": "",
            "confidence": "high",
            "evidence_refs": [
                {
                    "ref_id": "owned",
                    "source": "evidence/brand_fit/manufacturer_catalog_products.csv",
                    "selector": {"match": {"parent_product_id": "shared-product"}},
                    "fields": ["product_name", "brand"],
                }
            ],
            "supporting_claim_ids": [],
        },
        {
            "claim_id": "brand-fit-read",
            "kind": "semantic",
            "headline": "Brand Fit read",
            "text_template": "The source signal and current anchor warrant a closer catalogue review.",
            "interpretation": "Codex should evaluate the wider owned catalogue before recommending action.",
            "caveat": "",
            "confidence": "medium",
            "evidence_refs": [],
            "supporting_claim_ids": [
                "retailer-signal",
                "current-presence",
                "owned-catalogue",
            ],
        },
    ]
    assignments = {
        "retailer_signals": ["retailer-signal"],
        "current_retailer_presence": ["current-presence"],
        "owned_catalogue": ["owned-catalogue"],
        "brand_fit_opportunities": ["brand-fit-read"],
    }
    tables = {
        "retailer_signals": ["retailer_signals"],
        "current_retailer_presence": ["current_retailer_presence"],
        "owned_catalogue": ["owned_catalogue"],
        "brand_fit_opportunities": ["brand_fit_candidates"],
    }
    for section in model["sections"]:
        section["summary"] = (
            "This section is authored from the pinned Brand Fit evidence."
        )
        section["claim_ids"] = assignments.get(section["section_id"], [])
        section["table_keys"] = tables.get(section["section_id"], [])
    model["featured_products"] = [
        {
            "product_id": "shared-product",
            "source": "evidence/brand_fit/retailer_brand_anchors.csv",
            "selector": {"match": {"parent_product_id": "shared-product"}},
            "role": "current_presence",
            "rationale": "A current anchor used to interpret the retailer signal.",
            "supporting_claim_ids": ["current-presence"],
        }
    ]
    _write_json(output / "report_model.json", model)


def _complete_review(
    output: Path, *, reviewer_id: str = "reviewer-agent", claim_status: str = "pass"
) -> None:
    review = json.loads((output / "semantic_review.json").read_text(encoding="utf-8"))
    review["review_status"] = "codex_complete"
    review["reviewer"]["agent_id"] = reviewer_id
    for item in review["claim_reviews"]:
        item.update(
            {
                "status": claim_status,
                "rationale": "The claim matches its exact evidence and is calibrated.",
            }
        )
    for item in review["image_reviews"]:
        item.update(
            {
                "status": "pass",
                "rationale": "The local image matches the selected product row.",
            }
        )
    for item in review["dimensions"].values():
        item.update(
            {"status": "pass", "rationale": "This dimension is supported and readable."}
        )
    review["overall_status"] = claim_status
    review["summary"] = (
        "Independent review covered every claim, dimension, and selected image."
    )
    _write_json(output / "semantic_review.json", review)


def _write_browser_qa(output: Path, *, omit_mobile: bool = False) -> None:
    catalog = json.loads((output / "evidence_catalog.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "render_manifest.json").read_text(encoding="utf-8"))
    viewports: list[dict[str, Any]] = []
    flattened: list[dict[str, Any]] = []
    for name, width, height in (("desktop", 1440, 1000), ("mobile", 390, 844)):
        if omit_mobile and name == "mobile":
            continue
        screenshot = output / "qa" / "screenshots" / f"report-{name}.png"
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        screenshot.write_bytes(PNG_BYTES)
        metrics = {
            "horizontalOverflow": False,
            "brokenImages": [],
            "unsafeAssets": [],
            "uncontainedWideTables": [],
            "missingRequiredElements": [],
            "unsafeProductLinks": [],
        }
        findings = [
            {
                "code": f"browser.{name}.{suffix}",
                "status": "pass",
                "message": "Measured browser check passed.",
                "details": [],
            }
            for suffix in (
                "horizontal_overflow",
                "local_images",
                "asset_locality",
                "table_scrolling",
                "required_elements",
                "product_links",
                "runtime",
            )
        ]
        viewports.append(
            {
                "name": name,
                "width": width,
                "height": height,
                "screenshot": screenshot.relative_to(output).as_posix(),
                "screenshot_sha256": _sha(screenshot),
                "metrics": metrics,
                "findings": findings,
            }
        )
        flattened.extend(findings)
    _write_json(
        output / "browser_qa.json",
        {
            "schema_version": "attribute_reporting.browser_qa.v1",
            "report_id": catalog["report_id"],
            "targets": {
                "draft_html": str((output / "report_draft.html").resolve()),
                "draft_html_sha256": manifest["draft_html_sha256"],
                "render_manifest_sha256": _sha(output / "render_manifest.json"),
            },
            "status": "pass",
            "viewports": viewports,
            "findings": flattened,
            "browser_error": "",
        },
    )


def _rendered_case(
    tmp_path: Path,
    brand_fit: ModuleType,
    *,
    source_verdict: str = "correct",
    require_browser_qa: bool = False,
) -> Path:
    source = _source_run(tmp_path, verdict=source_verdict)
    package, download, extraction = _package_and_receipts(tmp_path, brand_fit, source)
    output = tmp_path / "brand-fit-report"
    brand_fit.prepare_brand_fit_run(
        package,
        retailer_run_dir=source,
        output_dir=output,
        author_agent_id="author-agent",
        download_receipt_path=download,
        extraction_receipt_path=extraction,
        require_browser_qa=require_browser_qa,
    )
    _author_model(output)
    brand_fit.render_brand_fit_report(output)
    return output


def test_prepare_brand_fit_run_binds_checked_report_transport_and_local_images(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(tmp_path, brand_fit, source)

    catalog = brand_fit.prepare_brand_fit_run(
        package,
        retailer_run_dir=source,
        output_dir=tmp_path / "output",
        author_agent_id="author-agent",
        download_receipt_path=download,
        extraction_receipt_path=extraction,
        require_browser_qa=False,
    )

    assert catalog["source_retailer_report"]["sha256"] == _sha(source / "report.html")
    assert catalog["source_retailer_report"]["uploaded_to_server"] is False
    assert catalog["transport"]["download_receipt"]["job_id"] == "b" * 32
    copied_manifest = json.loads(
        (tmp_path / "output" / "evidence" / "local_image_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert copied_manifest["policy"]["uploaded_to_server"] is False
    assert (
        tmp_path / "output" / copied_manifest["products"][0]["image_path"]
    ).is_file()


def test_prepare_brand_fit_run_rejects_tampered_source_report(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(tmp_path, brand_fit, source)
    (source / "report.html").write_text("tampered", encoding="utf-8")

    with pytest.raises(brand_fit.BrandFitContractError, match="hash is stale"):
        brand_fit.prepare_brand_fit_run(
            package,
            retailer_run_dir=source,
            output_dir=tmp_path / "output",
            author_agent_id="author-agent",
            download_receipt_path=download,
            extraction_receipt_path=extraction,
        )


def test_prepare_brand_fit_run_rejects_server_image_bytes(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(
        tmp_path, brand_fit, source, server_image=True
    )

    with pytest.raises(brand_fit.BrandFitContractError, match="contains image bytes"):
        brand_fit.prepare_brand_fit_run(
            package,
            retailer_run_dir=source,
            output_dir=tmp_path / "output",
            author_agent_id="author-agent",
            download_receipt_path=download,
            extraction_receipt_path=extraction,
        )


def test_prepare_brand_fit_run_rejects_different_source_evidence_job(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(
        tmp_path,
        brand_fit,
        source,
        source_job_override="f" * 32,
    )

    with pytest.raises(brand_fit.BrandFitContractError, match="evidence job"):
        brand_fit.prepare_brand_fit_run(
            package,
            retailer_run_dir=source,
            output_dir=tmp_path / "output",
            author_agent_id="author-agent",
            download_receipt_path=download,
            extraction_receipt_path=extraction,
        )


def test_prepare_brand_fit_run_rejects_embedded_image_data(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(
        tmp_path,
        brand_fit,
        source,
        embedded_image_data=True,
    )

    with pytest.raises(brand_fit.BrandFitContractError, match="embedded image"):
        brand_fit.prepare_brand_fit_run(
            package,
            retailer_run_dir=source,
            output_dir=tmp_path / "output",
            author_agent_id="author-agent",
            download_receipt_path=download,
            extraction_receipt_path=extraction,
        )


@pytest.mark.parametrize("field_name", ["image_blob", "image_data", "image_data_uri"])
def test_prepare_brand_fit_run_rejects_embedded_image_fields(
    tmp_path: Path,
    brand_fit: ModuleType,
    field_name: str,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(
        tmp_path,
        brand_fit,
        source,
        embedded_field_name=field_name,
    )

    with pytest.raises(brand_fit.BrandFitContractError, match="embedded image"):
        brand_fit.prepare_brand_fit_run(
            package,
            retailer_run_dir=source,
            output_dir=tmp_path / "output",
            author_agent_id="author-agent",
            download_receipt_path=download,
            extraction_receipt_path=extraction,
        )


def test_prepare_brand_fit_run_allows_sanitized_empty_embedded_image_field(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(
        tmp_path,
        brand_fit,
        source,
        blank_embedded_field_name="image_data",
    )

    catalog = brand_fit.prepare_brand_fit_run(
        package,
        retailer_run_dir=source,
        output_dir=tmp_path / "output",
        author_agent_id="author-agent",
        download_receipt_path=download,
        extraction_receipt_path=extraction,
        require_browser_qa=False,
    )

    assert catalog["analysis_type"] == "brand_fit"


@pytest.mark.parametrize(
    "private_value",
    [
        "postgres://user:secret@db/private",
        "mysql://user:secret@db/private",
        "mariadb://user:secret@db/private",
        "mongodb://user:secret@db/private",
        "redis://user:secret@db/private",
        "file:///srv/private/product.png",
        "DATABASE_URL=postgresql://user:secret@db/private",
    ],
)
def test_prepare_brand_fit_run_rejects_private_database_markers(
    tmp_path: Path,
    brand_fit: ModuleType,
    private_value: str,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(
        tmp_path,
        brand_fit,
        source,
        portable_note=private_value,
    )

    with pytest.raises(brand_fit.BrandFitContractError, match="unsafe local URL/path"):
        brand_fit.prepare_brand_fit_run(
            package,
            retailer_run_dir=source,
            output_dir=tmp_path / "output",
            author_agent_id="author-agent",
            download_receipt_path=download,
            extraction_receipt_path=extraction,
        )


def test_prepare_brand_fit_run_allows_benign_file_colon_prose(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(
        tmp_path,
        brand_fit,
        source,
        portable_note="Source file: summary.json contains the report binding.",
    )

    catalog = brand_fit.prepare_brand_fit_run(
        package,
        retailer_run_dir=source,
        output_dir=tmp_path / "output",
        author_agent_id="author-agent",
        download_receipt_path=download,
        extraction_receipt_path=extraction,
        require_browser_qa=False,
    )

    assert catalog["analysis_type"] == "brand_fit"


@pytest.mark.parametrize("disguised_name", ["payload.bin", "payload"])
def test_prepare_brand_fit_run_rejects_disguised_server_binary(
    tmp_path: Path,
    brand_fit: ModuleType,
    disguised_name: str,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(
        tmp_path,
        brand_fit,
        source,
        disguised_binary_name=disguised_name,
    )

    with pytest.raises(brand_fit.BrandFitContractError, match="disallowed file type"):
        brand_fit.prepare_brand_fit_run(
            package,
            retailer_run_dir=source,
            output_dir=tmp_path / "output",
            author_agent_id="author-agent",
            download_receipt_path=download,
            extraction_receipt_path=extraction,
        )


def test_prepare_brand_fit_run_requires_mapping_state_snapshot(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(
        tmp_path,
        brand_fit,
        source,
        missing_mapping_snapshot=True,
    )

    with pytest.raises(brand_fit.BrandFitContractError, match="snapshot is missing"):
        brand_fit.prepare_brand_fit_run(
            package,
            retailer_run_dir=source,
            output_dir=tmp_path / "output",
            author_agent_id="author-agent",
            download_receipt_path=download,
            extraction_receipt_path=extraction,
        )


def test_prepare_brand_fit_run_rejects_wrong_mapping_state_scope(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(
        tmp_path,
        brand_fit,
        source,
        mapping_scope_override="wrong-retailer",
    )

    with pytest.raises(brand_fit.BrandFitContractError, match="scopes do not match"):
        brand_fit.prepare_brand_fit_run(
            package,
            retailer_run_dir=source,
            output_dir=tmp_path / "output",
            author_agent_id="author-agent",
            download_receipt_path=download,
            extraction_receipt_path=extraction,
        )


def test_prepare_brand_fit_run_rejects_stale_pack_manifest(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(
        tmp_path,
        brand_fit,
        source,
        stale_pack_manifest=True,
    )

    with pytest.raises(brand_fit.BrandFitContractError, match="manifest is invalid"):
        brand_fit.prepare_brand_fit_run(
            package,
            retailer_run_dir=source,
            output_dir=tmp_path / "output",
            author_agent_id="author-agent",
            download_receipt_path=download,
            extraction_receipt_path=extraction,
        )


def test_prepare_brand_fit_run_requires_local_image_hydration_manifest(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(tmp_path, brand_fit, source)
    (package / "local_image_manifest.json").unlink()

    with pytest.raises(
        brand_fit.BrandFitContractError, match="image-hydration manifest"
    ):
        brand_fit.prepare_brand_fit_run(
            package,
            retailer_run_dir=source,
            output_dir=tmp_path / "output",
            author_agent_id="author-agent",
            download_receipt_path=download,
            extraction_receipt_path=extraction,
        )


def test_render_brand_fit_report_rejects_non_unique_evidence_selector(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(
        tmp_path, brand_fit, source, duplicate_signal=True
    )
    output = tmp_path / "output"
    brand_fit.prepare_brand_fit_run(
        package,
        retailer_run_dir=source,
        output_dir=output,
        author_agent_id="author-agent",
        download_receipt_path=download,
        extraction_receipt_path=extraction,
        require_browser_qa=False,
    )
    _author_model(output)

    with pytest.raises(brand_fit.BrandFitContractError, match="matched 2 rows"):
        brand_fit.render_brand_fit_report(output)


def test_render_brand_fit_report_rejects_cross_scope_product_role(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    output = _rendered_case(tmp_path, brand_fit)
    model = json.loads((output / "report_model.json").read_text(encoding="utf-8"))
    model["featured_products"][0]["role"] = "owned_catalogue"
    _write_json(output / "report_model.json", model)

    with pytest.raises(brand_fit.BrandFitContractError, match="role does not match"):
        brand_fit.render_brand_fit_report(output)


def test_render_brand_fit_report_rejects_cross_scope_table(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(tmp_path, brand_fit, source)
    output = tmp_path / "output"
    brand_fit.prepare_brand_fit_run(
        package,
        retailer_run_dir=source,
        output_dir=output,
        author_agent_id="author-agent",
        download_receipt_path=download,
        extraction_receipt_path=extraction,
        require_browser_qa=False,
    )
    _author_model(output)
    model = json.loads((output / "report_model.json").read_text(encoding="utf-8"))
    model["sections"][1]["table_keys"] = ["owned_catalogue"]
    _write_json(output / "report_model.json", model)

    with pytest.raises(brand_fit.BrandFitContractError, match="another evidence scope"):
        brand_fit.render_brand_fit_report(output)


def test_check_brand_fit_report_returns_correct_for_intact_independent_review(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    output = _rendered_case(tmp_path, brand_fit)
    _complete_review(output)

    verdict = brand_fit.check_brand_fit_report(output)

    assert verdict["verdict"] == "Correct"
    assert (
        json.loads((output / "final_artifacts.json").read_text(encoding="utf-8"))[
            "status"
        ]
        == "final_ready"
    )
    assert "Direct verdict: **Correct**" in (output / "codex_run_review.md").read_text(
        encoding="utf-8"
    )


def test_check_brand_fit_report_accepts_measured_desktop_and_mobile_qa(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    output = _rendered_case(tmp_path, brand_fit, require_browser_qa=True)
    _complete_review(output)
    _write_browser_qa(output)

    verdict = brand_fit.check_brand_fit_report(output)

    assert verdict["verdict"] == "Correct"
    assert verdict["basis"]["browser_qa"] == "pass"


def test_check_brand_fit_report_rejects_incomplete_browser_qa(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    output = _rendered_case(tmp_path, brand_fit, require_browser_qa=True)
    _complete_review(output)
    _write_browser_qa(output, omit_mobile=True)

    verdict = brand_fit.check_brand_fit_report(output)

    assert verdict["verdict"] == "Unable to determine"
    assert verdict["basis"]["browser_qa"] == "unable"


def test_check_brand_fit_report_rejects_same_agent_reviewer(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    output = _rendered_case(tmp_path, brand_fit)
    _complete_review(output, reviewer_id="author-agent")

    verdict = brand_fit.check_brand_fit_report(output)

    assert verdict["verdict"] == "Unable to determine"
    assert any("not independent" in finding for finding in verdict["semantic_findings"])


def test_check_brand_fit_report_marks_tampered_evidence_incorrect(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    output = _rendered_case(tmp_path, brand_fit)
    _complete_review(output)
    with (output / "evidence" / "brand_fit" / "signal_bundles.csv").open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write("\n")

    verdict = brand_fit.check_brand_fit_report(output)

    assert verdict["verdict"] == "Incorrect"
    assert any(
        "evidence changed" in finding for finding in verdict["mechanical_findings"]
    )


def test_check_brand_fit_report_carries_source_report_caveat(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    output = _rendered_case(tmp_path, brand_fit, source_verdict="correct_with_caveats")
    _complete_review(output)

    verdict = brand_fit.check_brand_fit_report(output)

    assert verdict["verdict"] == "Correct with caveats"
    assert verdict["basis"]["source_retailer_report"] == "Correct with caveats"


def test_check_brand_fit_report_caveats_partial_local_image_hydration(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    source = _source_run(tmp_path)
    package, download, extraction = _package_and_receipts(tmp_path, brand_fit, source)
    manifest_path = package / "local_image_manifest.json"
    image_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    image_manifest["products"][0].update(
        {"status": "unavailable", "image_path": "", "sha256": ""}
    )
    image_manifest["summary"].update(
        {
            "available_count": 3,
            "unavailable_count": 1,
            "status": "partial",
        }
    )
    _write_json(manifest_path, image_manifest)
    output = tmp_path / "brand-fit-report"
    brand_fit.prepare_brand_fit_run(
        package,
        retailer_run_dir=source,
        output_dir=output,
        author_agent_id="author-agent",
        download_receipt_path=download,
        extraction_receipt_path=extraction,
        require_browser_qa=False,
    )
    _author_model(output)
    brand_fit.render_brand_fit_report(output)
    _complete_review(output)

    verdict = brand_fit.check_brand_fit_report(output)

    assert verdict["verdict"] == "Correct with caveats"
    assert "Local product-image hydration is incomplete" in verdict["caveats"]
    assert any("shared-product" in caveat for caveat in verdict["caveats"])


def test_completed_retailer_report_rejects_false_verdict_upgrade(
    tmp_path: Path,
    brand_fit: ModuleType,
) -> None:
    source = _source_run(tmp_path, verdict="correct_with_caveats")
    correctness_path = source / "correctness_verdict.json"
    correctness = json.loads(correctness_path.read_text(encoding="utf-8"))
    correctness["verdict"] = "correct"
    _write_json(correctness_path, correctness)
    report_path = source / "report.html"
    report_path.write_text(
        report_path.read_text(encoding="utf-8").replace(
            'data-correctness-verdict="correct_with_caveats"',
            'data-correctness-verdict="correct"',
        ),
        encoding="utf-8",
    )
    final_path = source / "final_artifacts.json"
    final = json.loads(final_path.read_text(encoding="utf-8"))
    final["correctness_verdict"] = "correct"
    for item in final["outputs"]:
        if item["path"] == "report.html":
            item["sha256"] = _sha(report_path)
        if item["path"] == "correctness_verdict.json":
            item["sha256"] = _sha(correctness_path)
    _write_json(final_path, final)

    with pytest.raises(
        brand_fit.BrandFitContractError, match="semantic review|verdict"
    ):
        brand_fit.completed_retailer_report(source)
