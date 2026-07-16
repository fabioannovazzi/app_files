from __future__ import annotations

from modules.pdp.cdp_listing_engine import CandidateLink
from modules.pdp.guestinresidence_cdp_strategy import GuestInResidenceCDPStrategy
from modules.pdp.profile_loader import load_profile


def test_guestinresidence_strategy_canonicalizes_collection_product_links(
    monkeypatch,
) -> None:
    profile = load_profile("guestinresidence_cashmere_sweaters")
    strategy = GuestInResidenceCDPStrategy()
    monkeypatch.setattr(
        strategy,
        "_allowed_handles",
        lambda _profile: {"compass-sweater-tee-sorbet"},
    )

    observations = strategy.build_observations(
        candidates=[
            CandidateLink(
                url=(
                    "https://guestinresidence.com/collections/womens-sweaters/"
                    "products/compass-sweater-tee-sorbet?variant=1"
                ),
                title="Compass Sweater Tee - Sorbet",
            ),
            CandidateLink(
                url=(
                    "https://guestinresidence.com/collections/100-cashmere/products/"
                    "tailored-trouser-charcoal"
                ),
                title="Tailored Trouser - Charcoal",
            ),
        ],
        category_key="cashmere_sweaters",
        source_surface="category",
        sort_mode="default",
        page_number=1,
        listing_url="https://guestinresidence.com/collections/womens-sweaters",
        profile=profile,
        seen_urls=set(),
    )

    assert len(observations) == 1
    assert observations[0].parent_product_id == "compass-sweater-tee-sorbet"
    assert observations[0].pdp_url == (
        "https://guestinresidence.com/products/compass-sweater-tee-sorbet"
    )
