from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from scripts.validate_reporting_visual_references import (
    validate_reporting_visual_references,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), "white").save(path)


def _valid_manifest(tmp_path: Path) -> dict[str, object]:
    asset_path = tmp_path / "refs" / "example.png"
    _write_png(asset_path)
    return {
        "schema_version": "2.0",
        "assets_root": str(tmp_path / "refs"),
        "families": [
            {
                "family_id": "column_bar",
                "label": "Column and bar",
                "match_terms": ["column", "bar"],
                "default_variants": ["column"],
                "review_focus": ["Check title."],
                "reference_example_ids": ["example_column"],
            }
        ],
        "examples": [
            {
                "example_id": "example_column",
                "source": "IBCS",
                "title": "Column example",
                "family_id": "column_bar",
                "variant_ids": ["column"],
                "source_url": "https://example.test/source",
                "asset_url": "https://example.test/asset.png",
                "local_asset": str(asset_path),
                "asset_type": "image/png",
                "primary_use": "Column label reference.",
                "look_at": ["labels"],
                "avoid_using_for": ["tables"],
                "selection_tags": ["column"],
                "license_note": "Use with attribution.",
            }
        ],
    }


def test_validate_reporting_visual_references_accepts_valid_manifest(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "visual_reporting_references.json"
    _write_json(manifest_path, _valid_manifest(tmp_path))

    issues = validate_reporting_visual_references(manifest_path)

    assert issues == []


def test_validate_reporting_visual_references_allows_empty_family_lists(
    tmp_path: Path,
) -> None:
    payload = _valid_manifest(tmp_path)
    family = payload["families"][0]
    family["match_terms"] = []
    family["default_variants"] = []
    family["review_focus"] = []
    family["reference_example_ids"] = []
    manifest_path = tmp_path / "visual_reporting_references.json"
    _write_json(manifest_path, payload)

    issues = validate_reporting_visual_references(manifest_path)

    assert issues == []


def test_validate_reporting_visual_references_rejects_unknown_reference_id(
    tmp_path: Path,
) -> None:
    payload = _valid_manifest(tmp_path)
    family = payload["families"][0]
    family["reference_example_ids"] = ["missing_example"]
    manifest_path = tmp_path / "visual_reporting_references.json"
    _write_json(manifest_path, payload)

    issues = validate_reporting_visual_references(manifest_path)

    assert any("unknown reference_example_id" in issue.message for issue in issues)


def test_validate_reporting_visual_references_rejects_missing_asset(
    tmp_path: Path,
) -> None:
    payload = _valid_manifest(tmp_path)
    example = payload["examples"][0]
    example["local_asset"] = str(tmp_path / "refs" / "missing.png")
    manifest_path = tmp_path / "visual_reporting_references.json"
    _write_json(manifest_path, payload)

    issues = validate_reporting_visual_references(manifest_path)

    assert any("local_asset missing" in issue.message for issue in issues)


def test_validate_reporting_visual_references_allows_external_only_examples(
    tmp_path: Path,
) -> None:
    payload = _valid_manifest(tmp_path)
    del payload["examples"][0]["local_asset"]
    manifest_path = tmp_path / "visual_reporting_references.json"
    _write_json(manifest_path, payload)

    issues = validate_reporting_visual_references(
        manifest_path,
        require_assets=False,
    )

    assert issues == []
