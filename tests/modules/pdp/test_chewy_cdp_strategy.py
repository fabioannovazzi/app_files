from __future__ import annotations

import re
from types import SimpleNamespace

from modules.pdp.cdp_listing_engine import CandidateLink
from modules.pdp.chewy_cdp_strategy import ChewyCDPStrategy


def test_chewy_cdp_strategy_uses_browser_widget_for_ranked_sorts() -> None:
    strategy = ChewyCDPStrategy()
    base_url = "https://www.chewy.com/b/wet-food-389"

    assert strategy.selector == "a[href]"
    assert strategy.apply_sort_mode(base_url, "newest") == base_url
    assert strategy.apply_sort_mode(base_url, "best_selling") == base_url
    assert strategy.browser_sort_label("newest") == "Newest"
    assert strategy.browser_sort_label("best_selling") == "Bestselling"


def test_chewy_cdp_strategy_derives_wet_cat_food_category_key() -> None:
    strategy = ChewyCDPStrategy()

    assert strategy.profile_to_category_key("chewy_wet_cat_food") == "wet_cat_food"


def test_chewy_cdp_strategy_keeps_slide_links_with_blank_product_name() -> None:
    strategy = ChewyCDPStrategy()
    profile = SimpleNamespace(
        base_url="https://www.chewy.com",
        id_extractors=SimpleNamespace(parent_from_url_regex=re.compile(r"/dp/(\d+)")),
    )

    observations = strategy.build_observations(
        candidates=(
            CandidateLink(
                url="https://www.chewy.com/fancy-feast-gravy-lovers/dp/103856",
                title="Slide 1 of 8",
            ),
            CandidateLink(
                url="https://www.chewy.com/fancy-feast-gravy-lovers/dp/103856",
                title="Fancy Feast Gravy Lovers Variety Pack",
            ),
        ),
        category_key="wet_cat_food",
        source_surface="category",
        sort_mode="newest",
        page_number=1,
        listing_url="https://www.chewy.com/b/wet-food-389?sort=newest",
        profile=profile,
        seen_urls=set(),
    )

    assert len(observations) == 1
    assert observations[0].parent_product_id == "103856"
    assert observations[0].product_name is None


def test_chewy_cdp_strategy_keeps_product_title_when_title_anchor_is_first() -> None:
    strategy = ChewyCDPStrategy()
    profile = SimpleNamespace(
        base_url="https://www.chewy.com",
        id_extractors=SimpleNamespace(parent_from_url_regex=re.compile(r"/dp/(\d+)")),
    )

    observations = strategy.build_observations(
        candidates=(
            CandidateLink(
                url="https://www.chewy.com/fancy-feast-gravy-lovers/dp/103856",
                title="Fancy Feast Gravy Lovers Variety Pack",
            ),
        ),
        category_key="wet_cat_food",
        source_surface="category",
        sort_mode="newest",
        page_number=1,
        listing_url="https://www.chewy.com/b/wet-food-389?sort=newest",
        profile=profile,
        seen_urls=set(),
    )

    assert len(observations) == 1
    assert observations[0].parent_product_id == "103856"
    assert observations[0].product_name == "Fancy Feast Gravy Lovers Variety Pack"


def test_chewy_cdp_strategy_rejects_sitewide_gift_card_pdp() -> None:
    strategy = ChewyCDPStrategy()
    profile = SimpleNamespace(
        base_url="https://www.chewy.com",
        id_extractors=SimpleNamespace(parent_from_url_regex=re.compile(r"/dp/(\d+)")),
    )

    observations = strategy.build_observations(
        candidates=(
            CandidateLink(
                url="https://www.chewy.com/chewy-egift-card/dp/226306",
                title="Gift Cards",
            ),
            CandidateLink(
                url="https://www.chewy.com/fancy-feast-gravy-lovers/dp/103856",
                title="Fancy Feast Gravy Lovers Variety Pack",
            ),
        ),
        category_key="wet_cat_food",
        source_surface="category",
        sort_mode="newest",
        page_number=1,
        listing_url="https://www.chewy.com/b/wet-food-389?sort=newest",
        profile=profile,
        seen_urls=set(),
    )

    assert len(observations) == 1
    assert observations[0].parent_product_id == "103856"


def test_chewy_cdp_strategy_rejects_sponsored_candidates() -> None:
    strategy = ChewyCDPStrategy()
    profile = SimpleNamespace(
        base_url="https://www.chewy.com",
        id_extractors=SimpleNamespace(parent_from_url_regex=re.compile(r"/dp/(\d+)")),
    )

    observations = strategy.build_observations(
        candidates=(
            CandidateLink(
                url="https://www.chewy.com/sponsored-product/dp/111111",
                title="Sponsored Product",
                is_sponsored=True,
            ),
            CandidateLink(
                url="https://www.chewy.com/fancy-feast-gravy-lovers/dp/103856",
                title="Fancy Feast Gravy Lovers Variety Pack",
            ),
        ),
        category_key="wet_cat_food",
        source_surface="category",
        sort_mode="best_selling",
        page_number=1,
        listing_url="https://www.chewy.com/b/wet-food-389?sort=bestselling",
        profile=profile,
        seen_urls=set(),
    )

    assert len(observations) == 1
    assert observations[0].parent_product_id == "103856"


def test_chewy_cdp_strategy_rejects_candidates_before_sort_control() -> None:
    strategy = ChewyCDPStrategy()
    profile = SimpleNamespace(
        base_url="https://www.chewy.com",
        id_extractors=SimpleNamespace(parent_from_url_regex=re.compile(r"/dp/(\d+)")),
    )

    observations = strategy.build_observations(
        candidates=(
            CandidateLink(
                url="https://www.chewy.com/promo-carousel-product/dp/111111",
                title="Promo Carousel Product",
                is_before_sort_control=True,
            ),
            CandidateLink(
                url="https://www.chewy.com/fancy-feast-gravy-lovers/dp/103856",
                title="Fancy Feast Gravy Lovers Variety Pack",
            ),
        ),
        category_key="wet_cat_food",
        source_surface="category",
        sort_mode="newest",
        page_number=1,
        listing_url="https://www.chewy.com/b/wet-food-389?sort=newest",
        profile=profile,
        seen_urls=set(),
    )

    assert len(observations) == 1
    assert observations[0].parent_product_id == "103856"


def test_chewy_cdp_strategy_rejects_carousel_next_shop_link() -> None:
    strategy = ChewyCDPStrategy()
    html = """
    <html><body>
      <a aria-label="Next" href="/shops/nexgard-heartgard-brand-products-3395942#rh=PetType:Cat">
        Next
      </a>
    </body></html>
    """

    next_url = strategy.next_page_url(
        current_url="https://www.chewy.com/b/wet-food-389?sort=newest",
        html=html,
        current_page=1,
    )

    assert next_url is None


def test_chewy_cdp_strategy_keeps_same_category_page_link() -> None:
    strategy = ChewyCDPStrategy()
    html = """
    <html><body>
      <a aria-label="Next page" href="/b/wet-food-389?sort=newest&page=2">
        Next
      </a>
    </body></html>
    """

    next_url = strategy.next_page_url(
        current_url="https://www.chewy.com/b/wet-food-389?sort=newest",
        html=html,
        current_page=1,
    )

    assert next_url == "https://www.chewy.com/b/wet-food-389?sort=newest&page=2"


def test_chewy_cdp_strategy_preserves_sort_when_next_link_omits_it() -> None:
    strategy = ChewyCDPStrategy()
    html = """
    <html><body>
      <a aria-label="Next page" href="/b/wet-food-389?page=2">Next</a>
    </body></html>
    """

    next_url = strategy.next_page_url(
        current_url="https://www.chewy.com/b/wet-food-389?sort=bestselling",
        html=html,
        current_page=1,
    )

    assert next_url == "https://www.chewy.com/b/wet-food-389?page=2&sort=bestselling"


def test_chewy_cdp_strategy_uses_page_fallback_without_sort() -> None:
    strategy = ChewyCDPStrategy()

    next_url = strategy.next_page_url(
        current_url="https://www.chewy.com/b/wet-food-389?page=2",
        html="<html><body></body></html>",
        current_page=2,
    )

    assert next_url == "https://www.chewy.com/b/wet-food-389?page=3"
