from __future__ import annotations


import json
from pathlib import Path

from modules.pdp.discovery import _apply_sort_mode_to_url
from modules.pdp.discovery_classification import build_parent_discovery_classification
from modules.pdp.models import ListingObservation
from modules.pdp.saloncentric_filter_discovery import (
    SALONCENTRIC_CORE_DESCRIPTOR_FAMILIES,
    SALONCENTRIC_DESCRIPTOR_FAMILIES,
    SALONCENTRIC_SECONDARY_DESCRIPTOR_FAMILIES,
    crawl_saloncentric_filter_observations,
    default_filter_families_for_category,
    discover_saloncentric_filter_families,
    extract_saloncentric_filter_surfaces,
    map_saloncentric_families_to_taxonomy,
    normalize_saloncentric_filter_value,
)
from modules.pdp.models import FilterSurface


def test_apply_sort_mode_to_url_uses_srule_for_saloncentric() -> None:
    base = "https://www.saloncentric.com/hair-color?plp=true&prefn1=productTypeSc&prefv1=permanent"
    newest = _apply_sort_mode_to_url(base, "newest", retailer="saloncentric")
    assert "srule=newest" in newest
    restored = _apply_sort_mode_to_url(newest, "default", retailer="saloncentric")
    assert "srule=" not in restored


def test_extract_saloncentric_filter_surfaces_reads_pref_filters() -> None:
    html = """
    <html><body>
      <a href="/hair-color?plp=true&prefn1=family&prefv1=Permanent">Permanent</a>
      <a href="/hair-color?plp=true&prefn1=brand&prefv1=Redken">Redken</a>
    </body></html>
    """
    surfaces = extract_saloncentric_filter_surfaces(
        category_url="https://www.saloncentric.com/hair-color",
        html=html,
        category_key="permanent",
        allowed_families=("family",),
    )
    assert len(surfaces) == 1
    surface = surfaces[0]
    assert surface.filter_family == "family"
    assert surface.filter_value == "Permanent"


def test_discover_saloncentric_filter_families_reads_anchor_attr_and_script() -> None:
    html = """
    <html><body>
      <a href="/hair-color?prefn1=family&prefv1=Permanent">Permanent</a>
      <div data-filter-family="brand"></div>
      <script type="application/json">
        {"prefn2":"tone","prefv2":"cool"}
      </script>
    </body></html>
    """
    families = discover_saloncentric_filter_families(html)
    assert families == ("brand", "family", "tone")


def test_build_parent_discovery_classification_assigns_new_and_pareto() -> None:
    observations: list[ListingObservation] = []
    for idx in range(1, 11):
        parent = f"parent_{idx}"
        observations.append(
            ListingObservation(
                retailer="saloncentric",
                category_key="permanent",
                source_surface="category",
                sort_mode="newest",
                page=1,
                position=idx,
                pdp_url=f"https://www.saloncentric.com/p/{parent}",
                parent_product_id=parent,
                product_name=parent,
            )
        )
        observations.append(
            ListingObservation(
                retailer="saloncentric",
                category_key="permanent",
                source_surface="category",
                sort_mode="most_popular",
                page=1,
                position=idx,
                pdp_url=f"https://www.saloncentric.com/p/{parent}",
                parent_product_id=parent,
                product_name=parent,
            )
        )
    classified = build_parent_discovery_classification(observations)
    rows = classified.to_dicts()
    assert len(rows) == 10
    new_count = sum(1 for row in rows if row.get("new_rest_class") == "new")
    assert new_count == 2
    a_count = sum(1 for row in rows if row.get("pareto_class") == "A")
    b_count = sum(1 for row in rows if row.get("pareto_class") == "B")
    c_count = sum(1 for row in rows if row.get("pareto_class") == "C")
    assert a_count == 2
    assert b_count == 6
    assert c_count == 2


def test_extract_saloncentric_filter_surfaces_handles_multi_pref_pairs() -> None:
    html = """
    <html><body>
      <a href="/hair-color?prefn1=family&prefv1=Permanent&prefn2=brand&prefv2=Redken">Filter</a>
    </body></html>
    """
    surfaces = extract_saloncentric_filter_surfaces(
        category_url="https://www.saloncentric.com/hair-color",
        html=html,
        category_key="permanent",
        allowed_families=("family", "brand"),
    )
    assert {(s.filter_family, s.filter_value) for s in surfaces} == {
        ("family", "Permanent"),
        ("brand", "Redken"),
    }


def test_default_filter_families_for_category_uses_taxonomy_branch() -> None:
    assert default_filter_families_for_category("permanent") == (
        "product type",
        "product benefit",
        "product form",
        "ingredient preference",
        "haircolor tone",
        "haircolor level",
        "hair condition",
    )
    assert default_filter_families_for_category("unknown-category") == SALONCENTRIC_DESCRIPTOR_FAMILIES


def test_extract_saloncentric_filter_surfaces_defaults_to_category_allowlist() -> None:
    html = """
    <html><body>
      <a href="/hair-color?prefn1=Haircolor+Tone&prefv1=Cool">Tone</a>
      <a href="/hair-color?prefn1=Brand&prefv1=Redken">Brand</a>
    </body></html>
    """
    surfaces = extract_saloncentric_filter_surfaces(
        category_url=(
            "https://www.saloncentric.com/hair-color"
            "?plp=true&prefn1=productTypeSc&prefv1=permanent"
        ),
        html=html,
        category_key="permanent",
    )
    assert SALONCENTRIC_DESCRIPTOR_FAMILIES
    assert SALONCENTRIC_CORE_DESCRIPTOR_FAMILIES
    assert SALONCENTRIC_SECONDARY_DESCRIPTOR_FAMILIES == ("hair condition",)
    assert [(s.filter_family, s.filter_value) for s in surfaces] == [
        ("haircolor tone", "Cool")
    ]


def test_extract_saloncentric_filter_surfaces_maps_real_site_family_keys() -> None:
    html = """
    <html><body>
      <a href="/hair-color?prefn1=productBenefitHairSc&prefv1=greyCoverage&prefn2=productTypeSc&prefv2=permanent">
        Grey Coverage
      </a>
      <a href="/hair-color?prefn1=level&prefv1=level1&prefn2=productTypeSc&prefv2=permanent">
        Level 1
      </a>
    </body></html>
    """
    surfaces = extract_saloncentric_filter_surfaces(
        category_url=(
            "https://www.saloncentric.com/hair-color"
            "?plp=true&prefn1=productTypeSc&prefv1=permanent"
        ),
        html=html,
        category_key="permanent",
    )

    assert [(surface.filter_family, surface.filter_value) for surface in surfaces] == [
        ("haircolor level", "Level 01"),
        ("product benefit", "greyCoverage"),
    ]
    assert [surface.filter_url for surface in surfaces] == [
        "https://www.saloncentric.com/hair-color?prefn1=level&prefv1=level1&prefn2=productTypeSc&prefv2=permanent",
        "https://www.saloncentric.com/hair-color?prefn1=productBenefitHairSc&prefv1=greyCoverage&prefn2=productTypeSc&prefv2=permanent",
    ]


def test_map_saloncentric_families_to_taxonomy_uses_labels_ids_and_aliases() -> None:
    category_meta = {
        "attributes": [
            {"id": "coverage", "label": "Coverage"},
            {"id": "hair_tone", "label": "Tone"},
            {"id": "hair_level", "label": "Level"},
            {"id": "volume_ml", "label": "Volume"},
        ]
    }
    mapping = map_saloncentric_families_to_taxonomy(
        ["coverage", "tone family", "Haircolor Level", "Volume �", "unknown"],
        category_meta=category_meta,
        aliases={"tone family": "tone", "haircolor level": "level"},
    )
    assert mapping == {
        "coverage": "coverage",
        "tone family": "hair_tone",
        "Haircolor Level": "hair_level",
        "Volume �": "volume_ml",
    }


def test_normalize_saloncentric_filter_value_haircolor_level() -> None:
    assert normalize_saloncentric_filter_value("haircolor level", "level1") == "Level 01"
    assert normalize_saloncentric_filter_value("haircolor level", "Level 12") == "Level 12"
    assert normalize_saloncentric_filter_value("haircolor level", "No Level") == "No Level"


def test_permanent_taxonomy_branch_maps_discovery_families() -> None:
    branch_path = Path("config/attribute_taxonomy/categories/permanent.json")
    category_meta = json.loads(branch_path.read_text(encoding="utf-8"))

    attributes = category_meta.get("attributes", [])
    assert [attr["id"] for attr in attributes] == [
        "category",
        "benefit",
        "form",
        "ingredient_preference",
        "haircolor_tone",
        "haircolor_level",
        "hair_condition",
    ]
    assert [attr["label"] for attr in attributes] == [
        "product type",
        "product benefit",
        "product form",
        "ingredient preference",
        "haircolor tone",
        "haircolor level",
        "hair condition",
    ]

    mapping = map_saloncentric_families_to_taxonomy(
        [
            "product type",
            "product benefit",
            "product form",
            "ingredient preference",
            "haircolor tone",
            "haircolor level",
            "hair condition",
        ],
        category_meta=category_meta,
    )

    assert mapping == {
        "product type": "category",
        "product benefit": "benefit",
        "product form": "form",
        "ingredient preference": "ingredient_preference",
        "haircolor tone": "haircolor_tone",
        "haircolor level": "haircolor_level",
        "hair condition": "hair_condition",
    }


def test_crawl_filter_observations_forwards_parent_pattern_and_base_url(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_discover_listing_observations(*args, **kwargs):
        captured["parent_id_pattern"] = kwargs.get("parent_id_pattern")
        captured["canonical_base_url"] = kwargs.get("canonical_base_url")
        return []

    monkeypatch.setattr(
        "modules.pdp.saloncentric_filter_discovery.discover_listing_observations",
        _fake_discover_listing_observations,
    )

    surfaces = [
        FilterSurface(
            retailer="saloncentric",
            category_key="permanent",
            filter_family="haircolor tone",
            filter_value="Cool",
            filter_url="https://www.saloncentric.com/hair-color?prefn1=Haircolor+Tone&prefv1=Cool",
            filter_label="Cool",
        )
    ]
    parent_pattern = object()
    base_url = "https://www.saloncentric.com"

    crawl_saloncentric_filter_observations(
        surfaces,
        fetcher=object(),
        max_pages=1,
        delay_seconds=0.0,
        allowed_patterns=None,
        parent_id_pattern=parent_pattern,
        canonical_base_url=base_url,
    )

    assert captured == {
        "parent_id_pattern": parent_pattern,
        "canonical_base_url": base_url,
    }
