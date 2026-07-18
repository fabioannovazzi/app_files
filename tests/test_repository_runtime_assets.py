from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_json(relative_path: str) -> Any:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def _load_taxonomy_snapshot(snapshot: str) -> tuple[dict[str, Any], list[Any]]:
    snapshot_root = ROOT / "config" / "legacy" / "taxonomy_snapshots" / snapshot
    manifest = json.loads((snapshot_root / "manifest.json").read_text(encoding="utf-8"))
    categories = [
        json.loads((snapshot_root / entry["file"]).read_text(encoding="utf-8"))
        for entry in manifest["category_files"]
    ]
    return manifest, categories


def test_brand_aliases_preserve_curated_canonicalization() -> None:
    aliases = _load_json("brand_aliases.json")

    assert isinstance(aliases, dict)
    assert len(aliases) >= 69
    assert all(
        isinstance(alias, str)
        and alias == alias.strip().lower()
        and isinstance(canonical, str)
        and canonical == canonical.strip().lower()
        for alias, canonical in aliases.items()
    )
    assert aliases["christian dior"] == "dior"
    assert aliases["lancôme"] == "lancome"
    assert aliases["m·a·c"] == "mac"


def test_merchant_brand_website_seed_preserves_production_catalog() -> None:
    websites = _load_json("config/merchant_brand_websites.json")

    assert isinstance(websites, dict)
    assert len(websites) >= 740
    assert sum(isinstance(website, str) for website in websites.values()) >= 564
    assert all(
        isinstance(name, str)
        and name == name.strip().lower()
        and (website is None or isinstance(website, str))
        for name, website in websites.items()
    )
    assert websites["dior"] == "https://www.dior.com/"
    assert websites["sephora"] == "https://www.sephora.com"
    assert websites["tom ford"] == "https://www.tomford.com"


def test_category_website_seed_preserves_production_catalog() -> None:
    websites = _load_json("config/category_websites.json")

    assert set(websites) == {"blush", "bronzer", "foundation", "lip gloss", "lipstick"}
    assert sum(len(category_websites) for category_websites in websites.values()) == 15
    assert all(
        website.startswith("https://")
        for category_websites in websites.values()
        for website in category_websites
    )


@pytest.mark.parametrize(
    ("snapshot", "expected_categories", "expected_attributes"),
    [
        ("pre_wipe_2025-08-21", 8, 36),
        ("production_backup_2025-10-06", 7, 56),
        ("pre_split_2026-04-03", 6, 69),
    ],
)
def test_preserved_taxonomy_snapshot_has_one_file_per_category(
    snapshot: str,
    expected_categories: int,
    expected_attributes: int,
) -> None:
    manifest, categories = _load_taxonomy_snapshot(snapshot)
    snapshot_root = ROOT / "config" / "legacy" / "taxonomy_snapshots" / snapshot
    referenced_files = {entry["file"] for entry in manifest["category_files"]}
    category_files = {
        path.relative_to(snapshot_root).as_posix()
        for path in (snapshot_root / "categories").glob("*.json")
    }

    assert len(categories) == expected_categories
    assert (
        sum(len(category["attributes"]) for category in categories)
        == expected_attributes
    )
    assert [category["id"] for category in categories] == [
        entry["id"] for entry in manifest["category_files"]
    ]
    assert all("categories" not in category for category in categories)
    assert category_files == referenced_files


def test_preserved_legacy_reference_catalogs_remain_available() -> None:
    product_lines = _load_json("config/legacy/product_line_catalog.json")
    legacy_websites = _load_json(
        "config/legacy/merchant_brand_websites_legacy_2026-05-10.json"
    )
    production_website_meta = _load_json(
        "config/legacy/merchant_brand_websites_meta_production_2026-02-14.json"
    )
    legacy_website_meta = _load_json(
        "config/legacy/merchant_brand_websites_meta_legacy_2026-05-10.json"
    )

    assert sum(len(lines) for lines in product_lines.values()) == 214
    assert len(legacy_websites) == 87
    assert len(production_website_meta) == 144
    assert len(legacy_website_meta) == 56
