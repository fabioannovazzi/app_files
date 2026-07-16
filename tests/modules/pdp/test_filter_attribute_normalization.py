from __future__ import annotations

from modules.pdp.store import (
    _canonical_filter_attribute_family,
    _filter_attribute_group_values,
    _normalize_filter_attribute_values,
)


def test_filter_attribute_family_normalization_maps_retailer_aliases() -> None:
    assert _canonical_filter_attribute_family("lifestage") == "lifestage"
    assert _canonical_filter_attribute_family("Age Range Description") == "lifestage"
    assert _canonical_filter_attribute_family("Container Type") == "packaging_type"
    assert _canonical_filter_attribute_family("Count") == "package_count"
    assert (
        _canonical_filter_attribute_family("Animal Food Diet Type")
        == "special_diet"
    )


def test_filter_attribute_values_normalize_across_amazon_and_chewy_terms() -> None:
    assert _normalize_filter_attribute_values(
        "Flavor",
        ["Poultry", "Chicken", "Meat"],
        category_key="wet_cat_food",
    ) == ["chicken"]
    assert _normalize_filter_attribute_values(
        "Container Type",
        ["Cans"],
        category_key="wet_cat_food",
    ) == ["can"]
    assert _normalize_filter_attribute_values(
        "Count",
        ["3 & above"],
        category_key="wet_cat_food",
    ) == ["count_6_or_less"]
    assert _normalize_filter_attribute_values(
        "Age Range Description",
        ["All Life Stages"],
        category_key="wet_cat_food",
    ) == ["all_lifestages"]


def test_amazon_health_feature_nutrient_claim_maps_to_special_diet() -> None:
    assert (
        _canonical_filter_attribute_family(
            "health feature",
            category_key="wet_cat_food",
            retailer="amazon",
        )
        == "special_diet"
    )
    assert _normalize_filter_attribute_values(
        "health feature",
        ["High Protein"],
        category_key="wet_cat_food",
        retailer="amazon",
    ) == ["high_protein"]


def test_wet_cat_food_filter_value_can_reroute_or_drop_bad_retailer_family() -> None:
    assert _filter_attribute_group_values(
        "Flavor",
        "Chunk",
        category_key="wet_cat_food",
        retailer="amazon",
    ) == [("food_texture", "Chunk")]
    assert _filter_attribute_group_values(
        "Flavor",
        "Dry Kibble",
        category_key="wet_cat_food",
        retailer="amazon",
    ) == []
    assert _filter_attribute_group_values(
        "Package Count",
        "3 & above",
        category_key="wet_cat_food",
        retailer="amazon",
    ) == []
    assert _normalize_filter_attribute_values(
        "Flavor",
        ["Seafood"],
        category_key="wet_cat_food",
    ) == ["seafood_fish"]
    assert _normalize_filter_attribute_values(
        "Packaging Type",
        ["Carton"],
        category_key="wet_cat_food",
    ) == ["box"]
