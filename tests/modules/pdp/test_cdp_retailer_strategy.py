from __future__ import annotations

from modules.pdp.amazon_cdp_strategy import AmazonCDPStrategy
from modules.pdp.cdp_listing_engine import CandidateLink
from modules.pdp.cdp_retailer_strategy import strategy_for_retailer
from modules.pdp.chewy_cdp_strategy import ChewyCDPStrategy
from modules.pdp.cosmoprofbeauty_cdp_strategy import CosmoprofbeautyCDPStrategy
from modules.pdp.discovery import _apply_sort_mode_to_url
from modules.pdp.kiko_cdp_strategy import KikoCDPStrategy
from modules.pdp.profile_loader import load_profile
from modules.pdp.saksfifthavenue_cdp_strategy import SaksfifthavenueCDPStrategy
from modules.pdp.saloncentric_cdp_strategy import SaloncentricCDPStrategy


def test_strategy_for_retailer_supports_known_cdp_retailers() -> None:
    assert isinstance(strategy_for_retailer("saloncentric"), SaloncentricCDPStrategy)
    assert isinstance(strategy_for_retailer("amazon"), AmazonCDPStrategy)
    assert isinstance(
        strategy_for_retailer("cosmoprofbeauty"), CosmoprofbeautyCDPStrategy
    )
    assert isinstance(
        strategy_for_retailer("saksfifthavenue"), SaksfifthavenueCDPStrategy
    )
    assert isinstance(strategy_for_retailer("chewy"), ChewyCDPStrategy)
    assert isinstance(strategy_for_retailer("kiko"), KikoCDPStrategy)


def test_apply_sort_mode_to_url_uses_amazon_sort_query_key() -> None:
    base = "https://www.amazon.com/s?k=lipstick&i=beauty"
    newest = _apply_sort_mode_to_url(base, "newest", retailer="amazon")
    assert "s=date-desc-rank" in newest
    best_selling = _apply_sort_mode_to_url(base, "best_selling", retailer="amazon")
    assert "s=exact-aware-popularity-rank" in best_selling
    popular = _apply_sort_mode_to_url(base, "most_popular", retailer="amazon")
    assert "s=review-rank" in popular
    restored = _apply_sort_mode_to_url(popular, "default", retailer="amazon")
    assert "s=" not in restored


def test_apply_sort_mode_to_url_uses_srule_for_cosmoprofbeauty() -> None:
    base = "https://www.cosmoprofbeauty.com/hair-color/permanent"
    popular = _apply_sort_mode_to_url(base, "top_sellers", retailer="cosmoprofbeauty")
    assert "srule=top-sellers" in popular
    restored = _apply_sort_mode_to_url(popular, "default", retailer="cosmoprofbeauty")
    assert "srule=" not in restored


def test_amazon_strategy_build_observations_filters_wrong_category_titles() -> None:
    strategy = AmazonCDPStrategy()
    profile = load_profile("amazon_lipstick")

    observations = strategy.build_observations(
        candidates=(
            CandidateLink(
                url="https://www.amazon.com/gp/product/B012345678",
                title="Brand Matte Lipstick",
            ),
            CandidateLink(
                url="https://www.amazon.com/gp/product/B012345679",
                title="Album Audio CD Soundtrack",
            ),
        ),
        category_key="lipstick",
        source_surface="category",
        sort_mode="default",
        page_number=1,
        listing_url="https://www.amazon.com/s?k=lipstick&i=beauty",
        profile=profile,
        seen_urls=set(),
    )

    assert [(item.parent_product_id, item.product_name) for item in observations] == [
        ("B012345678", "Brand Matte Lipstick")
    ]
    assert observations[0].pdp_url == "https://www.amazon.com/dp/B012345678"


def test_amazon_strategy_build_observations_filters_wet_cat_food_noise() -> None:
    strategy = AmazonCDPStrategy()
    profile = load_profile("amazon_wet_cat_food")

    observations = strategy.build_observations(
        candidates=(
            CandidateLink(
                url="https://www.amazon.com/dp/B012345678",
                title="Purina Fancy Feast Wet Cat Food Pate Variety Pack",
            ),
            CandidateLink(
                url="https://www.amazon.com/dp/B012345679",
                title="Premium Chicken Dry Cat Food Kibble",
            ),
            CandidateLink(
                url="https://www.amazon.com/dp/B012345680",
                title="Wet Dog Food Beef in Gravy",
            ),
        ),
        category_key="wet_cat_food",
        source_surface="category",
        sort_mode="best_selling",
        page_number=1,
        listing_url="https://www.amazon.com/s?k=wet+cat+food&i=pets",
        profile=profile,
        seen_urls=set(),
    )

    assert [(item.parent_product_id, item.product_name) for item in observations] == [
        ("B012345678", "Purina Fancy Feast Wet Cat Food Pate Variety Pack")
    ]


def test_saloncentric_strategy_build_observations_extracts_parent_ids() -> None:
    strategy = SaloncentricCDPStrategy()
    profile = load_profile("saloncentric_permanent")
    seen_urls: set[str] = set()

    observations = strategy.build_observations(
        candidates=(
            CandidateLink(
                url="https://www.saloncentric.com/ABC-123.html?dwvar_color=7N",
                title="Color Product",
            ),
        ),
        category_key="permanent",
        source_surface="category",
        sort_mode="default",
        page_number=1,
        listing_url="https://www.saloncentric.com/hair-color",
        profile=profile,
        seen_urls=seen_urls,
    )

    assert len(observations) == 1
    assert observations[0].parent_product_id == "ABC-123"
    assert observations[0].pdp_url == "https://www.saloncentric.com/ABC-123.html"


def test_saloncentric_strategy_uses_load_more_expansion() -> None:
    strategy = SaloncentricCDPStrategy()

    assert strategy.load_more_texts == ("load more",)


def test_cosmoprofbeauty_strategy_uses_explicit_surface_labels() -> None:
    strategy = CosmoprofbeautyCDPStrategy()

    new_arrivals = strategy.apply_sort_mode(
        "https://www.cosmoprofbeauty.com/hair-color/permanent",
        "new_arrivals",
    )
    top_sellers = strategy.apply_sort_mode(
        "https://www.cosmoprofbeauty.com/hair-color/permanent",
        "top_sellers",
    )

    assert strategy.default_sort_modes == ("new_arrivals", "top_sellers")
    assert new_arrivals.startswith("https://www.cosmoprofbeauty.com/just-arrived?")
    assert "prefv1=Permanent%20Hair%20Color" in new_arrivals
    assert "srule=top-sellers" in top_sellers


def test_saksfifthavenue_strategy_build_observations_extracts_product_ids() -> None:
    strategy = SaksfifthavenueCDPStrategy()
    profile = load_profile("saksfifthavenue_low_top_sneakers")

    observations = strategy.build_observations(
        candidates=(
            CandidateLink(
                url=(
                    "https://www.saksfifthavenue.com/product/"
                    "miu-miu-tyre-low-top-sneakers-0400022953591.html?site_refer=CSE"
                ),
                title="Miu Miu Tyre Low-Top Sneakers",
            ),
        ),
        category_key="low_top_sneakers",
        source_surface="category",
        sort_mode="default",
        page_number=1,
        listing_url="https://www.saksfifthavenue.com/c/shoes/shoes/sneakers/low-tops",
        profile=profile,
        seen_urls=set(),
    )

    assert len(observations) == 1
    assert observations[0].parent_product_id == "0400022953591"
    assert observations[0].pdp_url == (
        "https://www.saksfifthavenue.com/product/"
        "miu-miu-tyre-low-top-sneakers-0400022953591.html"
    )


def test_saksfifthavenue_strategy_maps_sort_modes_to_srule() -> None:
    strategy = SaksfifthavenueCDPStrategy()
    base = "https://www.saksfifthavenue.com/c/shoes/shoes/sneakers/low-tops"

    recent = strategy.apply_sort_mode(base, "new_arrivals")
    popular = strategy.apply_sort_mode(base, "best_sellers")
    sales_first = strategy.apply_sort_mode(base, "sales_first")
    restored = strategy.apply_sort_mode(popular, "default")

    assert strategy.default_sort_modes == (
        "new_arrivals",
        "best_sellers",
        "sales_first",
    )
    assert "srule=new-arrivals" in recent
    assert "srule=best-sellers" in popular
    assert "srule=sale-first" in sales_first
    assert "srule=" not in restored


def test_saksfifthavenue_strategy_does_not_paginate_product_urls() -> None:
    strategy = SaksfifthavenueCDPStrategy()

    next_url = strategy.next_page_url(
        current_url=(
            "https://www.saksfifthavenue.com/product/"
            "miu-miu-cashmere-polo-sweater-0400024848677.html"
        ),
        html="<html></html>",
        current_page=2,
    )

    assert next_url is None
