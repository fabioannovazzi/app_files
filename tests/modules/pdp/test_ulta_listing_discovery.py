from __future__ import annotations

from modules.pdp.models import ListingObservation
from modules.pdp.ulta_listing_discovery import (
    classify_listing_statuses,
    collect_unseen_pdp_urls,
    profile_to_category_key,
)


def _observation(
    *,
    category_key: str,
    sort_mode: str,
    page: int,
    position: int,
    parent_product_id: str,
    has_new_badge: bool = False,
    pdp_url: str | None = None,
) -> ListingObservation:
    parent_id = str(parent_product_id)
    return ListingObservation(
        retailer="ulta",
        category_key=category_key,
        source_surface="category",
        sort_mode=sort_mode,
        page=page,
        position=position,
        pdp_url=pdp_url or f"https://www.ulta.com/p/{parent_id}",
        parent_product_id=parent_id,
        product_name=parent_id,
        has_new_badge=has_new_badge,
    )


def test_profile_to_category_key_strips_ulta_prefix() -> None:
    assert profile_to_category_key("ulta_lipstick") == "lipstick"
    assert profile_to_category_key("lip_gloss") == "lip_gloss"


def test_classify_listing_statuses_marks_top_quintile_recent() -> None:
    observations = [
        _observation(
            category_key="lipstick",
            sort_mode="new_arrivals",
            page=1,
            position=1,
            parent_product_id="p-1",
        ),
        _observation(
            category_key="lipstick",
            sort_mode="new_arrivals",
            page=1,
            position=2,
            parent_product_id="p-2",
        ),
        _observation(
            category_key="lipstick",
            sort_mode="new_arrivals",
            page=1,
            position=3,
            parent_product_id="p-3",
        ),
        _observation(
            category_key="lipstick",
            sort_mode="new_arrivals",
            page=1,
            position=4,
            parent_product_id="p-4",
        ),
        _observation(
            category_key="lipstick",
            sort_mode="new_arrivals",
            page=1,
            position=5,
            parent_product_id="p-5",
        ),
    ]

    statuses = classify_listing_statuses(observations)

    assert statuses[("lipstick", "p-1")] == "recent"
    assert statuses[("lipstick", "p-2")] == "rest"
    assert statuses[("lipstick", "p-5")] == "rest"


def test_classify_listing_statuses_uses_ceiling_for_small_categories() -> None:
    observations = [
        _observation(
            category_key="lipstick",
            sort_mode="new_arrivals",
            page=1,
            position=1,
            parent_product_id="p-first",
        ),
        _observation(
            category_key="lipstick",
            sort_mode="new_arrivals",
            page=1,
            position=2,
            parent_product_id="p-second",
        ),
    ]

    statuses = classify_listing_statuses(observations)

    assert statuses[("lipstick", "p-first")] == "recent"
    assert statuses[("lipstick", "p-second")] == "rest"


def test_classify_listing_statuses_marks_rest_when_missing_from_new_arrivals() -> None:
    observations = [
        _observation(
            category_key="lip_gloss",
            sort_mode="best_sellers",
            page=1,
            position=1,
            parent_product_id="p-gloss",
        ),
    ]

    statuses = classify_listing_statuses(observations)

    assert statuses[("lip_gloss", "p-gloss")] == "rest"


def test_classify_listing_statuses_keeps_status_list_local_by_category() -> None:
    observations = [
        _observation(
            category_key="lipstick",
            sort_mode="new_arrivals",
            page=1,
            position=1,
            parent_product_id="shared-id",
        ),
        _observation(
            category_key="lipstick",
            sort_mode="new_arrivals",
            page=1,
            position=2,
            parent_product_id="lipstick-other",
        ),
        _observation(
            category_key="lip_gloss",
            sort_mode="new_arrivals",
            page=1,
            position=1,
            parent_product_id="gloss-1",
        ),
        _observation(
            category_key="lip_gloss",
            sort_mode="new_arrivals",
            page=1,
            position=2,
            parent_product_id="shared-id",
        ),
        _observation(
            category_key="lip_gloss",
            sort_mode="new_arrivals",
            page=1,
            position=3,
            parent_product_id="gloss-3",
        ),
        _observation(
            category_key="lip_gloss",
            sort_mode="new_arrivals",
            page=1,
            position=4,
            parent_product_id="gloss-4",
        ),
        _observation(
            category_key="lip_gloss",
            sort_mode="new_arrivals",
            page=1,
            position=5,
            parent_product_id="gloss-5",
        ),
    ]

    statuses = classify_listing_statuses(observations)

    assert statuses[("lipstick", "shared-id")] == "recent"
    assert statuses[("lipstick", "lipstick-other")] == "rest"
    assert statuses[("lip_gloss", "gloss-1")] == "recent"
    assert statuses[("lip_gloss", "shared-id")] == "rest"


def test_collect_unseen_pdp_urls_filters_existing_parent_ids() -> None:
    observations = [
        _observation(
            category_key="lipstick",
            sort_mode="best_sellers",
            page=1,
            position=1,
            parent_product_id="p-existing",
            pdp_url="https://www.ulta.com/p/existing",
        ),
        _observation(
            category_key="lipstick",
            sort_mode="best_sellers",
            page=1,
            position=2,
            parent_product_id="p-new",
            pdp_url="https://www.ulta.com/p/new",
        ),
    ]

    unseen = collect_unseen_pdp_urls(
        observations,
        existing_parent_ids={"p-existing"},
    )

    assert unseen == ["https://www.ulta.com/p/new"]
