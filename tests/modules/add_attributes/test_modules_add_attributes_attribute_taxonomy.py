from __future__ import annotations

import json
from pathlib import Path

import pytest

import modules.add_attributes.attribute_taxonomy as attr_tax
from modules.add_attributes.attribute_taxonomy import (
    aggregate_pending_values,
    get_attribute_taxonomy,
    get_taxonomy_storage_mtime,
    get_runtime_attribute_taxonomy,
    save_attribute_taxonomy,
    select_top_candidates,
)


@pytest.fixture(autouse=True)
def _isolate_taxonomy_file_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    missing_path = Path("/tmp/nonexistent-taxonomy-fixture.json")
    monkeypatch.setattr(attr_tax, "TAXONOMY_TEMPLATE_PATH", missing_path)
    monkeypatch.setattr(attr_tax, "VISION_ALLOWLIST_PATH", missing_path)
    monkeypatch.setattr(attr_tax, "WEB_ALLOWLIST_PATH", missing_path)
    attr_tax._load_vision_allowlist.cache_clear()
    attr_tax._load_web_allowlist.cache_clear()
    attr_tax.get_category_alias_map.cache_clear()
    yield
    attr_tax._load_vision_allowlist.cache_clear()
    attr_tax._load_web_allowlist.cache_clear()
    attr_tax.get_category_alias_map.cache_clear()


def test_get_attribute_taxonomy_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    tmp_json = tmp_path / "taxonomy.json"
    expected = {"group": {"name": "size", "values": ["S", "M", "L"]}}
    tmp_json.write_text(json.dumps(expected), encoding="utf-8")
    monkeypatch.setattr(attr_tax, "TAXONOMY_PATH", tmp_json)

    # Act
    result = get_attribute_taxonomy()

    # Assert
    assert result == expected


def test_category_aliases_include_kiko_ulta_comparable_categories() -> None:
    # Arrange
    expected_aliases = {
        "automatic_eye_pencil": "eyeliner",
        "automatic_lip_pencil": "lip_liner",
        "coloured_lip_balm": "lip_balms",
        "lip_marker": "lip_stain",
        "lip_treatment": "lip_treatments",
        "primers_face": "face_primer",
        "primers_lips": "lip_treatments",
        "stick_contouring": "contour",
        "wood_eye_pencils": "eyeliner",
        "wood_lip_pencils": "lip_liner",
    }

    # Act
    aliases = attr_tax.get_category_alias_map()

    # Assert
    for source_category, canonical_category in expected_aliases.items():
        assert aliases[source_category] == canonical_category


def test_vision_allowlist_includes_image_eligible_categories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setattr(
        attr_tax,
        "VISION_ALLOWLIST_PATH",
        attr_tax.APP_ROOT / "config" / "vision_allowlist.json",
    )
    attr_tax._load_vision_allowlist.cache_clear()
    expected_allowlist = {
        "bb_cc_creams": {"product_type", "form"},
        "color_correct": {"form", "color_corrector_shade"},
        "contour": {"form"},
        "lip_balms": {"form", "product_type"},
        "lip_liner": {"form"},
        "lip_plumpers": {"form", "product_type"},
        "lip_stain": {"form", "applicator_type", "formula_base"},
        "lip_treatments": {"form", "treatment_type", "finish_effect"},
        "mascara": {"effect", "water_resistance", "bristle_material"},
        "permanent": {"form"},
        "tinted_moisturizer": {"product_type", "form"},
        "wet_cat_food": {
            "flavor",
            "food_texture",
            "lifestage",
            "special_diet",
            "health_feature",
            "product_assortment",
            "prescription_status",
        },
    }

    # Act
    taxonomy = get_runtime_attribute_taxonomy()
    categories = {
        str(category["id"]): set(category.get("image_allowlist", []))
        for category in taxonomy["categories"]
    }

    # Assert
    for category_id, attributes in expected_allowlist.items():
        assert attributes <= categories[category_id]
    assert "mascara" not in set(taxonomy.get("no_image_categories", []))


def test_vision_allowlist_covers_every_taxonomy_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setattr(
        attr_tax,
        "VISION_ALLOWLIST_PATH",
        attr_tax.APP_ROOT / "config" / "vision_allowlist.json",
    )
    attr_tax._load_vision_allowlist.cache_clear()

    # Act
    taxonomy = get_runtime_attribute_taxonomy()
    no_image_categories = set(taxonomy.get("no_image_categories", []))
    uncovered = [
        str(category["id"])
        for category in taxonomy["categories"]
        if not category.get("image_allowlist")
        and str(category["id"]) not in no_image_categories
    ]

    # Assert
    assert uncovered == []


def test_get_attribute_taxonomy_missing_file_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    missing = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(attr_tax, "TAXONOMY_PATH", missing)

    # Act / Assert
    with pytest.raises(FileNotFoundError) as exc:
        get_attribute_taxonomy()
    # Error message should include the path for diagnostics
    assert str(missing) in str(exc.value)


def test_get_attribute_taxonomy_invalid_json_raises_value_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{", encoding="utf-8")  # invalid JSON
    monkeypatch.setattr(attr_tax, "TAXONOMY_PATH", bad_json)

    # Act / Assert
    with pytest.raises(ValueError) as exc:
        get_attribute_taxonomy()
    assert str(bad_json) in str(exc.value)


def test_save_attribute_taxonomy_writes_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    out_json = tmp_path / "out.json"
    monkeypatch.setattr(attr_tax, "TAXONOMY_PATH", out_json)
    data = {"category": "material", "options": ["cotton", "wool"]}

    # Act
    save_attribute_taxonomy(data)

    # Assert
    assert out_json.is_file()
    loaded = json.loads(out_json.read_text(encoding="utf-8"))
    assert loaded == data


def test_save_and_load_attribute_taxonomy_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    taxonomy_dir = tmp_path / "attribute_taxonomy"
    monkeypatch.setattr(attr_tax, "TAXONOMY_PATH", taxonomy_dir)
    data = {
        "version": "2026.04.03",
        "no_image_categories": ["palette"],
        "categories": [
            {"id": "lip_gloss", "label": "Lip gloss", "attributes": []},
            {"id": "lipstick", "label": "Lipstick", "attributes": []},
        ],
    }

    save_attribute_taxonomy(data)
    loaded = get_attribute_taxonomy()

    assert (taxonomy_dir / "manifest.json").is_file()
    assert (taxonomy_dir / "categories" / "lip_gloss.json").is_file()
    assert (taxonomy_dir / "categories" / "lipstick.json").is_file()
    assert loaded == data


def test_save_attribute_taxonomy_replaces_readonly_backup_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    taxonomy_dir = tmp_path / "attribute_taxonomy"
    backup_dir = tmp_path / "attribute_taxonomy.bak"
    backup_categories = backup_dir / "categories"
    backup_categories.mkdir(parents=True)
    stale_file = backup_categories / "stale.json"
    stale_file.write_text("{}", encoding="utf-8")
    stale_file.chmod(0o400)
    monkeypatch.setattr(attr_tax, "TAXONOMY_PATH", taxonomy_dir)

    save_attribute_taxonomy(
        {
            "categories": [
                {"id": "lip_gloss", "label": "Lip gloss", "attributes": []},
            ]
        }
    )

    assert not backup_dir.exists()
    assert (taxonomy_dir / "categories" / "lip_gloss.json").is_file()


def test_get_taxonomy_storage_mtime_reads_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    taxonomy_dir = tmp_path / "attribute_taxonomy"
    monkeypatch.setattr(attr_tax, "TAXONOMY_PATH", taxonomy_dir)
    save_attribute_taxonomy(
        {
            "categories": [
                {"id": "lip_gloss", "label": "Lip gloss", "attributes": []},
            ]
        }
    )

    mtime = get_taxonomy_storage_mtime()

    assert mtime is not None
    assert mtime > 0


def test_select_top_candidates_returns_top_n() -> None:
    aggregated = [
        {"category": "c", "attribute": "a", "value": "v1", "count": 5},
        {"category": "c", "attribute": "a", "value": "v2", "count": 2},
    ]
    result = select_top_candidates(aggregated, top_k=1)
    assert result == [aggregated[0]]


def test_aggregate_pending_values_groups_and_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue_file = tmp_path / "queue.json"
    monkeypatch.setattr(attr_tax, "REVIEW_QUEUE_PATH", queue_file)
    entries = [
        {"category": "cat", "attribute": "attr", "value": "A"},
        {"category": "cat", "attribute": "attr", "value": "A"},
        {"category": "cat", "attribute": "attr", "value": "B"},
        {"category": "cat", "attribute": "attr", "value": "C", "count": 2},
    ]
    queue_file.write_text(json.dumps(entries), encoding="utf-8")

    result = aggregate_pending_values(top_k=10)
    # Ensure counts are aggregated correctly
    assert {r["value"]: r["count"] for r in result} == {"A": 2, "B": 1, "C": 2}
    # Respect top_k
    top = aggregate_pending_values(top_k=2)
    assert len(top) == 2


def test_get_runtime_attribute_taxonomy_filters_non_active_leaves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    tmp_json = tmp_path / "taxonomy.json"
    taxonomy = {
        "categories": [
            {
                "id": "face_primer",
                "label": "Face primer",
                "attributes": [
                    {
                        "id": "form",
                        "label": "Format",
                        "hierarchical": True,
                        "levels": 2,
                        "nodes": [
                            {
                                "id": "liquid",
                                "label": "Liquid",
                                "children": [
                                    {
                                        "id": "lotion",
                                        "label": "Lotion",
                                        "status": "deprecated",
                                    },
                                    {"id": "serum", "label": "Serum"},
                                ],
                            },
                            {"id": "oil", "label": "Oil", "status": "needs_review"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                            {"id": "other", "label": "not in taxonomy"},
                        ],
                    }
                ],
            }
        ]
    }
    tmp_json.write_text(json.dumps(taxonomy), encoding="utf-8")
    monkeypatch.setattr(attr_tax, "TAXONOMY_PATH", tmp_json)

    # Act
    runtime_taxonomy = get_runtime_attribute_taxonomy()

    # Assert
    nodes = runtime_taxonomy["categories"][0]["attributes"][0]["nodes"]
    assert [node["id"] for node in nodes] == ["liquid", "unknown", "other"]
    assert [child["id"] for child in nodes[0]["children"]] == ["serum"]
