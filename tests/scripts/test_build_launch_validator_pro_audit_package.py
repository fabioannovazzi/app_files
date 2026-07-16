from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from scripts.build_launch_validator_pro_audit_package import build_pro_audit_packages


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_pro_audit_packages_exports_units_results_and_package_rows(
    tmp_path: Path,
) -> None:
    report_id = "lip_gloss"
    cache_id = "lip_gloss"
    reports_dir = tmp_path / "launch_reports"
    cache_dir = reports_dir / ".launch_report_reading_cache" / cache_id
    validation_dir = reports_dir / "validation"
    package_root = tmp_path / "packages"
    package_dir = package_root / report_id
    output_dir = tmp_path / "audit"
    slide = {
        "slideId": "slide-001.html",
        "slideNumber": 1,
        "pageNumber": 1,
        "blocks": [
            {
                "blockId": "block-title",
                "type": "title",
                "text": "Lip Gloss Overview",
            },
            {
                "blockId": "block-claim",
                "type": "bullet_item",
                "items": ["Glossy finish appears in 26% of recent launches."],
            },
            {
                "blockId": "block-note",
                "type": "bullet_item",
                "items": ["Source: deterministic launch package."],
            },
            {
                "blockId": "block-artifact",
                "type": "body_text",
                "text": "OCR fused artifact 12345",
            },
        ],
    }
    _write_json(
        cache_dir / "slide_analysis.json",
        {
            "deckId": cache_id,
            "lang": "eng",
            "slides": [slide],
        },
    )
    _write_json(cache_dir / "layout.json", {"slides": [slide]})
    _write_json(
        cache_dir / "ocr.json",
        {
            "slides": [
                {
                    "slideId": "slide-001.html",
                    "slideNumber": 1,
                    "lines": [
                        "Glossy finish appears in 26% of recent launches.",
                    ],
                }
            ]
        },
    )
    _write_json(
        validation_dir / f"{report_id}.validation.json",
        {
            "status": "pass_with_warnings",
            "package_dir": str(package_dir),
            "summary": {
                "verified_count": 1,
                "unresolved_count": 1,
                "non_claim_count": 1,
                "mapping_issue_count": 1,
                "image_region_count": 1,
                "claim_count": 1,
                "slide_count": 1,
            },
            "reading_quality": {"status": "read_ok"},
            "claims": [
                {
                    "status": "verified",
                    "claim_family": "bundle_metric",
                    "claim_text": "Glossy finish appears in 26% of recent launches.",
                    "slide_id": "slide-001.html",
                    "slide_number": 1,
                    "page_number": 1,
                    "source_kind": "bullet",
                    "block_id": "block-claim",
                    "block_type": "bullet_item",
                    "entity": "glossy finish",
                    "file": "innovation_pairs.csv",
                    "details": {
                        "observed_values": {"percents": [26.0]},
                        "expected": {"pct_recent": 26.0, "recent_base": 50},
                        "threshold_policy": {"tolerance_pct": 0.5},
                    },
                }
            ],
            "non_claims": [
                {
                    "status": "non_claim",
                    "claim_family": "filter_non_claim",
                    "claim_text": "Lip Gloss Overview",
                    "slide_id": "slide-001.html",
                    "slide_number": 1,
                    "page_number": 1,
                    "source_kind": "block_text",
                    "block_id": "block-title",
                    "block_type": "title",
                    "details": {"filter_rule_id": "NF01"},
                }
            ],
            "mapping_issues": [
                {
                    "status": "ocr_layout_mapping_issue",
                    "claim_family": "ocr_layout_mapping_issue",
                    "claim_text": "OCR fused artifact 12345",
                    "slide_id": "slide-001.html",
                    "slide_number": 1,
                    "page_number": 1,
                    "source_kind": "block_text",
                    "block_id": "block-artifact",
                    "block_type": "body_text",
                    "details": {"mapping_issue_type": "ocr_fused_or_stray_token_text"},
                }
            ],
            "image_regions": [
                {
                    "status": "image_region",
                    "claim_family": "figure_region",
                    "claim_text": "Image region",
                    "slide_id": "slide-001.html",
                    "slide_number": 1,
                    "page_number": 1,
                    "source_kind": "figure_region",
                    "region_index": 0,
                }
            ],
            "unresolved": [
                {
                    "status": "unresolved",
                    "claim_family": "unclassified",
                    "claim_text": "Source: deterministic launch package.",
                    "slide_id": "slide-001.html",
                    "slide_number": 1,
                    "page_number": 1,
                    "source_kind": "bullet",
                    "block_id": "block-note",
                    "block_type": "bullet_item",
                    "details": {
                        "message": "claim-like text was not parsed deterministically"
                    },
                }
            ],
        },
    )
    package_dir.mkdir(parents=True)
    (package_dir / "innovation_pairs.csv").write_text(
        "bundle_label,pct_recent,recent_base\n" "glossy finish,0.26,50\n",
        encoding="utf-8",
    )

    report_output_dir = output_dir / "test-run" / report_id
    report_output_dir.mkdir(parents=True)
    (report_output_dir / "instructions.md").write_text("stale", encoding="utf-8")

    summary = build_pro_audit_packages(
        reports_dir=reports_dir,
        validation_dir=validation_dir,
        output_dir=output_dir,
        package_root=package_root,
        report_ids=[report_id],
        run_id="test-run",
        generated_at=datetime(2026, 4, 22, 9, 0, tzinfo=UTC),
    )

    context = json.loads((report_output_dir / "report_context.json").read_text())
    deterministic_results = json.loads(
        (report_output_dir / "deterministic_results.json").read_text()
    )
    caught_units = json.loads((report_output_dir / "caught_units.json").read_text())
    unresolved_units = json.loads(
        (report_output_dir / "unresolved_units.json").read_text()
    )
    non_claim_units = json.loads(
        (report_output_dir / "non_claim_units.json").read_text()
    )
    mapping_issue_units = json.loads(
        (report_output_dir / "mapping_issue_units.json").read_text()
    )
    uncaught_units = json.loads((report_output_dir / "uncaught_units.json").read_text())
    image_regions = json.loads((report_output_dir / "image_regions.json").read_text())
    unmatched_results = json.loads(
        (report_output_dir / "unmatched_deterministic_results.json").read_text()
    )
    package_evidence = json.loads(
        (report_output_dir / "package_evidence.json").read_text()
    )
    prompt = (report_output_dir / "prompt.md").read_text(encoding="utf-8")
    data_only_zip = output_dir / "test-run" / f"{report_id}_data_only.zip"

    assert summary["report_count"] == 1
    assert summary["reports"][0]["cache_id"] == cache_id
    assert summary["reports"][0]["prompt_path"] == str(report_output_dir / "prompt.md")
    assert summary["reports"][0]["data_only_zip"] == str(data_only_zip)
    assert context["counts"]["mapped_unit_count"] == 4
    assert context["counts"]["caught_unit_count"] == 1
    assert context["counts"]["unresolved_unit_count"] == 1
    assert context["counts"]["non_claim_unit_count"] == 1
    assert context["counts"]["mapping_issue_unit_count"] == 1
    assert context["counts"]["uncaught_unit_count"] == 0
    assert context["counts"]["image_region_count"] == 1
    assert context["reading_completeness"]["status"] == "read_ok"
    assert deterministic_results[0]["details"]["observed_values"]["percents"] == [26.0]
    assert deterministic_results[0]["details"]["expected"]["recent_base"] == 50
    assert deterministic_results[0]["has_details"] is True
    assert caught_units[0]["deterministic_status"] == "caught"
    assert unresolved_units[0]["deterministic_status"] == "unresolved"
    assert non_claim_units[0]["deterministic_status"] == "non_claim"
    assert mapping_issue_units[0]["deterministic_status"] == "mapping_issue"
    assert uncaught_units == []
    assert image_regions[0]["claim_family"] == "figure_region"
    assert any(item["result_type"] == "image_region" for item in unmatched_results)
    assert package_evidence["records"][0]["matched_rows"][0]["pct_recent"] == "0.26"
    assert "This is a test-loop audit" in prompt
    assert "result's visible `details` evidence" in prompt
    assert (report_output_dir / "pro_output_schema.json").exists()
    assert not (report_output_dir / "instructions.md").exists()
    with zipfile.ZipFile(data_only_zip) as archive:
        archived_names = set(archive.namelist())
    assert "prompt.md" not in archived_names
    assert "report_context.json" in archived_names
    assert "mapped_text_units.json" in archived_names
    assert "non_claim_units.json" in archived_names
    assert "mapping_issue_units.json" in archived_names
    assert "image_regions.json" in archived_names


def test_build_pro_audit_packages_rebases_server_package_path(
    tmp_path: Path,
) -> None:
    report_id = "bronzer_ulta"
    cache_id = report_id
    reports_dir = tmp_path / "launch_reports"
    cache_dir = reports_dir / ".launch_report_reading_cache" / cache_id
    validation_dir = reports_dir / "validation"
    package_root = tmp_path / "data" / "pdp" / "reports" / "packages" / "launch"
    package_dir = package_root / "bronzer" / "ulta"
    output_dir = tmp_path / "audit"
    slide = {
        "slideId": "slide-001.html",
        "slideNumber": 1,
        "pageNumber": 1,
        "blocks": [
            {
                "blockId": "block-claim",
                "type": "title",
                "text": "Matte finish appears in 21% of recent launches.",
            }
        ],
    }
    _write_json(
        cache_dir / "slide_analysis.json",
        {"deckId": cache_id, "lang": "eng", "slides": [slide]},
    )
    _write_json(cache_dir / "layout.json", {"slides": [slide]})
    _write_json(
        cache_dir / "ocr.json",
        {
            "slides": [
                {
                    "slideId": "slide-001.html",
                    "slideNumber": 1,
                    "lines": ["Matte finish appears in 21% of recent launches."],
                }
            ]
        },
    )
    _write_json(
        validation_dir / f"{report_id}.validation.json",
        {
            "status": "pass_with_warnings",
            "package_dir": "/srv/app_files/data/pdp/reports/packages/launch/category/retailer",
            "resolver": {
                "status": "matched",
                "package_dir": "/srv/app_files/data/pdp/reports/packages/launch/category/retailer",
                "package_retailer": "ulta",
                "package_category_key": "bronzer",
            },
            "summary": {
                "verified_count": 1,
                "unresolved_count": 0,
                "claim_count": 1,
                "slide_count": 1,
            },
            "reading_quality": {"status": "read_ok"},
            "claims": [
                {
                    "status": "verified",
                    "claim_family": "bundle_metric",
                    "claim_text": "Matte finish appears in 21% of recent launches.",
                    "slide_id": "slide-001.html",
                    "slide_number": 1,
                    "page_number": 1,
                    "source_kind": "title",
                    "block_id": "block-claim",
                    "block_type": "title",
                    "entity": "matte finish",
                    "details": {
                        "expected": {"pct_recent": 21.0},
                        "candidate_evaluations": [
                            {
                                "file": "innovation_pairs.csv",
                                "package_values": {
                                    "bundle_label": "matte finish",
                                    "pct_recent": 0.21,
                                },
                            }
                        ],
                    },
                }
            ],
            "unresolved": [],
        },
    )
    package_dir.mkdir(parents=True)
    (package_dir / "innovation_pairs.csv").write_text(
        "bundle_label,pct_recent\nmatte finish,0.21\n",
        encoding="utf-8",
    )

    build_pro_audit_packages(
        reports_dir=reports_dir,
        validation_dir=validation_dir,
        output_dir=output_dir,
        package_root=package_root,
        report_ids=[report_id],
        run_id="test-run",
        generated_at=datetime(2026, 5, 11, 9, 0, tzinfo=UTC),
    )

    package_evidence = json.loads(
        (output_dir / "test-run" / report_id / "package_evidence.json").read_text()
    )

    assert package_evidence["package_dir"] == str(package_dir)
    assert package_evidence["records"][0]["matched_rows"][0]["pct_recent"] == 0.21
    assert package_evidence["records"][0]["detail_source"] == "candidate_evaluations"
