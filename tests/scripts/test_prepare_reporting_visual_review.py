from __future__ import annotations

import json
from pathlib import Path

from scripts import prepare_reporting_visual_review as review


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _reference_manifest() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "source_notes": [],
        "families": [
            {
                "family_id": "stacked_bar_column",
                "label": "Stacked",
                "match_terms": ["stacked column", "cohort"],
                "review_focus": ["Check labels."],
                "reference_examples": [
                    {
                        "source": "IBCS",
                        "title": "Stacked examples",
                        "url": "https://www.ibcs.com/resource_category/chart-templates/",
                        "local_asset": "",
                        "notes": "Use for labels.",
                    }
                ],
            },
            {
                "family_id": "column_bar",
                "label": "Column",
                "match_terms": ["bar", "column"],
                "review_focus": ["Check titles."],
                "reference_examples": [],
            },
            {
                "family_id": "general_chart",
                "label": "General",
                "match_terms": [],
                "review_focus": [],
                "reference_examples": [],
            },
        ],
    }


def test_infer_family_uses_tokens_so_barcode_does_not_match_bar() -> None:
    item = {
        "label": "mix_cohort / cohort_lost_stacked_column",
        "context_summary": {
            "grammar": "stacked column",
            "dimensions": "Barcode_Lost",
        },
    }

    family_id = review.infer_family_id(item, _reference_manifest())

    assert family_id == "stacked_bar_column"


def test_infer_family_prefers_artifact_contract_over_label_terms() -> None:
    reference_manifest = _reference_manifest()
    reference_manifest["families"].append(
        {
            "family_id": "reporting_table",
            "label": "Reporting table",
            "match_terms": ["table"],
            "review_focus": [],
            "reference_examples": [],
        }
    )
    item = {
        "label": "period / time_series_table",
        "artifact_type": "table",
        "context_summary": {
            "grammar": "period_comparison.time_series_table",
        },
        "artifact_contract": {
            "object_type": "table",
            "visual_family": "reporting_table",
        },
    }

    family_id = review.infer_family_id(item, reference_manifest)

    assert family_id == "reporting_table"


def test_build_review_packet_resolves_gallery_paths_and_references(
    tmp_path: Path,
) -> None:
    gallery_dir = tmp_path / "runs" / "png_examples" / "png-gallery"
    source_dir = tmp_path / "runs" / "png_examples" / "mix_cohort"
    (gallery_dir / "mix_cohort__cohort_lost_stacked_column.png").parent.mkdir(
        parents=True
    )
    source_dir.mkdir(parents=True)
    output_path = gallery_dir / "mix_cohort__cohort_lost_stacked_column.png"
    source_path = source_dir / "cohort_lost_stacked_column.png"
    context_path = source_dir / "cohort_lost_stacked_column_chart_context.json"
    output_path.write_bytes(b"png")
    source_path.write_bytes(b"png")
    context_path.write_text("{}", encoding="utf-8")
    manifest_path = gallery_dir / "manifest.json"
    reference_path = tmp_path / "docs" / "visual_reporting_references.json"
    _write_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "items": [
                {
                    "label": "mix_cohort / cohort_lost_stacked_column",
                    "plugin_source": "mix-contribution-analysis",
                    "source": "../mix_cohort/cohort_lost_stacked_column.png",
                    "output": "mix_cohort__cohort_lost_stacked_column.png",
                    "artifact_type": "png",
                    "context_summary": {
                        "capability": "mix.cohort_lost",
                        "grammar": "stacked column",
                    },
                    "sidecars": [
                        {
                            "label": "context",
                            "href": "../mix_cohort/cohort_lost_stacked_column_chart_context.json",
                        }
                    ],
                    "quality_flags": [],
                }
            ],
        },
    )
    _write_json(reference_path, _reference_manifest())

    packet = review.build_review_packet(
        manifest_path,
        reference_path,
        only_filters=["cohort_lost"],
    )

    assert packet.payload["item_count"] == 1
    item = packet.payload["items"][0]
    assert item["family_id"] == "stacked_bar_column"
    assert item["output_path"] == str(output_path.resolve())
    assert item["source_path"] == str(source_path.resolve())
    assert item["sidecars"][0]["path"] == str(context_path.resolve())
    assert item["sidecars"][0]["exists"] is True
    assert item["reference_examples"][0]["source"] == "IBCS"


def test_build_review_packet_can_filter_by_inferred_family(tmp_path: Path) -> None:
    gallery_dir = tmp_path / "gallery"
    manifest_path = gallery_dir / "manifest.json"
    reference_path = tmp_path / "refs.json"
    _write_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "items": [
                {
                    "label": "distribution / boxplot",
                    "plugin_source": "distribution-analysis",
                    "source": "../distribution/boxplot.png",
                    "output": "distribution__boxplot.png",
                    "context_summary": {"grammar": "boxplot"},
                },
                {
                    "label": "mix / column_total",
                    "plugin_source": "mix-contribution-analysis",
                    "source": "../mix/column_total.png",
                    "output": "mix__column_total.png",
                    "context_summary": {"grammar": "column"},
                },
            ],
        },
    )
    _write_json(
        reference_path,
        {
            "schema_version": "1.0",
            "families": [
                {
                    "family_id": "distribution",
                    "label": "Distribution",
                    "match_terms": ["boxplot"],
                    "review_focus": [],
                    "reference_examples": [],
                },
                {
                    "family_id": "column_bar",
                    "label": "Column",
                    "match_terms": ["column"],
                    "review_focus": [],
                    "reference_examples": [],
                },
                {
                    "family_id": "general_chart",
                    "label": "General",
                    "match_terms": [],
                    "review_focus": [],
                    "reference_examples": [],
                },
            ],
        },
    )

    packet = review.build_review_packet(
        manifest_path,
        reference_path,
        family_filter="column_bar",
    )

    assert packet.payload["item_count"] == 1
    assert packet.payload["items"][0]["label"] == "mix / column_total"


def test_build_review_packet_selects_classified_reference_examples(
    tmp_path: Path,
) -> None:
    gallery_dir = tmp_path / "gallery"
    source_dir = tmp_path / "mix"
    manifest_path = gallery_dir / "manifest.json"
    reference_path = tmp_path / "refs.json"
    asset_path = tmp_path / "assets" / "stacked.png"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"not-opened-by-packet-test")
    _write_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "items": [
                {
                    "label": "mix / stacked_column",
                    "plugin_source": "mix-contribution-analysis",
                    "source": "../mix/stacked_column.png",
                    "output": "mix__stacked_column.png",
                    "context_summary": {"grammar": "stacked column"},
                }
            ],
        },
    )
    source_dir.mkdir()
    (source_dir / "stacked_column.png").write_bytes(b"png")
    _write_json(
        reference_path,
        {
            "schema_version": "2.0",
            "families": [
                {
                    "family_id": "stacked_bar_column",
                    "label": "Stacked",
                    "match_terms": ["stacked column"],
                    "default_variants": ["stacked"],
                    "review_focus": ["Check labels."],
                    "reference_example_ids": ["stacked_reference"],
                },
                {
                    "family_id": "general_chart",
                    "label": "General",
                    "match_terms": [],
                    "default_variants": ["general"],
                    "review_focus": [],
                    "reference_example_ids": [],
                },
            ],
            "examples": [
                {
                    "example_id": "stacked_reference",
                    "source": "IBCS",
                    "title": "Stacked reference",
                    "family_id": "stacked_bar_column",
                    "variant_ids": ["stacked_column", "vertical"],
                    "source_url": "https://example.test/source",
                    "asset_url": "https://example.test/asset.png",
                    "local_asset": str(asset_path),
                    "asset_type": "image/png",
                    "primary_use": "Stacked labels.",
                    "look_at": ["segment labels"],
                    "avoid_using_for": ["tables"],
                    "selection_tags": ["stacked"],
                    "license_note": "Use with attribution.",
                }
            ],
        },
    )

    packet = review.build_review_packet(manifest_path, reference_path)

    item = packet.payload["items"][0]
    reference = item["reference_examples"][0]
    assert item["variant_ids"] == ["stacked_column", "stacked", "column"]
    assert reference["example_id"] == "stacked_reference"
    assert reference["matched_variant_ids"] == ["stacked_column"]
    assert reference["local_asset"] == str(asset_path.resolve())
    assert reference["local_asset_exists"] is True
