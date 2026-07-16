from __future__ import annotations

import pytest

from modules.pdp.profile_loader import load_profile


@pytest.mark.parametrize(
    "profile_name",
    [
        "ulta_lipstick",
        "ulta_foundation",
        "ulta_bb_cc_creams",
        "ulta_tinted_moisturizer",
        "ulta_lip_gloss",
        "ulta_lip_oil",
        "ulta_bronzer",
        "ulta_blush",
        "ulta_color_correct",
        "ulta_contour",
        "ulta_liquid_lipstick",
    ],
)
def test_load_profile_returns_expected_configuration(profile_name: str) -> None:
    profile = load_profile(profile_name)
    assert profile.profile_name == profile_name
    assert profile.retailer == "ulta"
    assert profile.category_urls
    assert profile.parent_rules.min_color_variants == 3
    assert profile.field_paths.variant_fields["variant_id"]
    assert profile.claim_mapping is not None
    assert (
        profile.claim_mapping.get("highlights", {}).get("cruelty free")
        == "cruelty_free"
    )


@pytest.mark.parametrize(
    "profile_name",
    [
        "sephora_lipstick",
        "sephora_liquid_lipstick",
        "sephora_lip_gloss",
        "sephora_lip_oil",
        "sephora_foundation",
        "sephora_blush",
        "sephora_bronzer",
    ],
)
def test_load_sephora_profiles(profile_name: str) -> None:
    profile = load_profile(profile_name)
    assert profile.profile_name == profile_name
    assert profile.retailer == "sephora"
    assert profile.category_urls
    assert profile.field_paths.variant_list
    assert profile.field_paths.variant_fields["variant_id"]
    assert profile.claim_mapping is None


def test_iter_profile_summaries_includes_saloncentric_permanent() -> None:
    from modules.pdp.profile_loader import iter_profile_summaries

    summaries = iter_profile_summaries()
    matches = [
        summary
        for summary in summaries
        if summary.profile_name == "saloncentric_permanent"
    ]

    assert matches
    assert matches[0].retailer == "saloncentric"


def test_iter_profile_summaries_includes_cosmoprofbeauty_permanent() -> None:
    from modules.pdp.profile_loader import iter_profile_summaries

    summaries = iter_profile_summaries()
    matches = [
        summary
        for summary in summaries
        if summary.profile_name == "cosmoprofbeauty_permanent"
    ]

    assert matches
    assert matches[0].retailer == "cosmoprofbeauty"


def test_iter_profile_summaries_includes_saksfifthavenue_low_top_sneakers() -> None:
    from modules.pdp.profile_loader import iter_profile_summaries

    summaries = iter_profile_summaries()
    matches = [
        summary
        for summary in summaries
        if summary.profile_name == "saksfifthavenue_low_top_sneakers"
    ]

    assert matches
    assert matches[0].retailer == "saksfifthavenue"


def test_iter_profile_summaries_includes_saksfifthavenue_cashmere_sweaters() -> None:
    from modules.pdp.profile_loader import iter_profile_summaries

    summaries = iter_profile_summaries()
    matches = [
        summary
        for summary in summaries
        if summary.profile_name == "saksfifthavenue_cashmere_sweaters"
    ]

    assert matches
    assert matches[0].retailer == "saksfifthavenue"


def test_iter_profile_summaries_includes_chewy_wet_cat_food() -> None:
    from modules.pdp.profile_loader import iter_profile_summaries

    summaries = iter_profile_summaries()
    matches = [
        summary for summary in summaries if summary.profile_name == "chewy_wet_cat_food"
    ]

    assert matches
    assert matches[0].retailer == "chewy"


def test_load_saloncentric_profile_contains_valid_discovery_and_paths() -> None:
    profile = load_profile("saloncentric_permanent")

    assert profile.retailer == "saloncentric"
    assert profile.category_urls
    assert all(
        url.startswith("https://www.saloncentric.com/") for url in profile.category_urls
    )
    assert profile.id_extractors.parent_from_url_regex is not None
    assert profile.id_extractors.parent_from_url_regex.pattern == "/([^/?#]+)\\.html"
    assert profile.field_paths.parent_title
    assert profile.field_paths.variant_list
    assert profile.field_paths.variant_fields["variant_id"]


def test_load_cosmoprofbeauty_profile_contains_valid_discovery_and_paths() -> None:
    profile = load_profile("cosmoprofbeauty_permanent")

    assert profile.retailer == "cosmoprofbeauty"
    assert profile.category_urls == (
        "https://www.cosmoprofbeauty.com/hair-color/permanent",
    )
    assert profile.id_extractors.parent_from_url_regex is not None
    assert profile.id_extractors.parent_from_url_regex.pattern == "/([^/?#]+)\\.html"
    assert profile.field_paths.parent_title
    assert profile.field_paths.variant_list
    assert profile.field_paths.variant_fields["variant_id"]


def test_load_saksfifthavenue_profile_contains_valid_discovery_and_paths() -> None:
    profile = load_profile("saksfifthavenue_low_top_sneakers")

    assert profile.retailer == "saksfifthavenue"
    assert profile.category_urls == (
        "https://www.saksfifthavenue.com/c/shoes/shoes/sneakers/low-tops",
    )
    assert profile.id_extractors.parent_from_url_regex is not None
    assert profile.id_extractors.parent_from_url_regex.pattern == (
        "/product/[^/?#]*?([0-9]{8,})\\.html"
    )
    assert profile.field_paths.parent_title
    assert profile.field_paths.variant_list
    assert profile.field_paths.variant_fields["variant_id"]


def test_load_saksfifthavenue_cashmere_profile_contains_valid_discovery_and_paths() -> (
    None
):
    profile = load_profile("saksfifthavenue_cashmere_sweaters")

    assert profile.retailer == "saksfifthavenue"
    assert profile.category_urls == (
        "https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere",
    )
    assert profile.id_extractors.parent_from_url_regex is not None
    assert profile.id_extractors.parent_from_url_regex.pattern == (
        "/product/[^/?#]*?([0-9]{8,})\\.html"
    )
    assert profile.field_paths.parent_title
    assert profile.field_paths.variant_list
    assert profile.field_paths.variant_fields["variant_id"]


def test_load_chewy_profile_contains_valid_discovery_and_paths() -> None:
    profile = load_profile("chewy_wet_cat_food")

    assert profile.retailer == "chewy"
    assert profile.category_urls == ("https://www.chewy.com/b/wet-food-389",)
    assert profile.id_extractors.parent_from_url_regex is not None
    assert profile.id_extractors.parent_from_url_regex.pattern == "/dp/(\\d+)"
    assert profile.field_paths.parent_title
    assert profile.field_paths.variant_list
    assert profile.field_paths.variant_fields["variant_id"]


def test_load_chewy_wet_cat_food_profile() -> None:
    profile = load_profile("chewy_wet_cat_food")

    assert profile.profile_name == "chewy_wet_cat_food"
    assert profile.retailer == "chewy"
