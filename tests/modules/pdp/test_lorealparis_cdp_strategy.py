from __future__ import annotations

from modules.pdp.cdp_listing_engine import CandidateLink
from modules.pdp.lorealparis_cdp_strategy import LorealParisCDPStrategy
from modules.pdp.profile_loader import load_profile


def test_lorealparis_strategy_canonicalizes_variant_links_to_family() -> None:
    strategy = LorealParisCDPStrategy()
    profile = load_profile("lorealparis_bronzer")
    family = "infallible-up-to-24h-fresh-wear-soft-matte-bronzer"

    observations = strategy.build_observations(
        candidates=[
            CandidateLink(
                url=(
                    "https://www.lorealparisusa.com/makeup/face/bronzer/"
                    f"{family}-light"
                ),
                title="Light",
            ),
            CandidateLink(
                url=(
                    "https://www.lorealparisusa.com/makeup/face/bronzer/"
                    f"{family}-medium"
                ),
                title="Medium",
            ),
            CandidateLink(
                url=(
                    "https://www.lorealparisusa.com/makeup/face/blush/"
                    "infallible-fresh-wear-blush"
                ),
                title="Wrong category",
            ),
        ],
        category_key="bronzer",
        source_surface="category",
        sort_mode="default",
        page_number=1,
        listing_url="https://www.lorealparisusa.com/makeup/face/bronzer",
        profile=profile,
        seen_urls=set(),
    )

    assert len(observations) == 1
    assert observations[0].parent_product_id == family
    assert observations[0].pdp_url == (
        "https://www.lorealparisusa.com/makeup/face/bronzer/" f"{family}"
    )
