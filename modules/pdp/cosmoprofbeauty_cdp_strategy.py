from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .cdp_retailer_strategy import BaseCDPRetailerStrategy
from .cosmoprofbeauty_filter_discovery import (
    extract_cosmoprofbeauty_filter_surfaces,
)
from .models import FilterSurface

__all__ = ["CosmoprofbeautyCDPStrategy"]


_JUST_ARRIVED_PERMANENT_URL = (
    "https://www.cosmoprofbeauty.com/just-arrived"
    "?prefn1=type&prefv1=Permanent%20Hair%20Color&start=0&sz=24"
)


class CosmoprofbeautyCDPStrategy(BaseCDPRetailerStrategy):
    """CosmoProf Beauty-specific CDP listing-discovery strategy."""

    def __init__(self) -> None:
        super().__init__(
            retailer="cosmoprofbeauty",
            selector=(
                ".product-grid .grid-tile .pdp-link__name[href$='.html'], "
                ".product-grid .grid-tile .pdp-link__name[href*='.html?']"
            ),
            default_sort_modes=("new_arrivals", "top_sellers"),
            filter_sort_modes=(),
            recent_sort_mode="new_arrivals",
            popularity_sort_mode="top_sellers",
            pagination_fallback_param="start",
            load_more_texts=(),
        )

    def apply_sort_mode(self, url: str, sort_mode: str) -> str:
        mode = str(sort_mode or "").strip().lower()
        if mode in {"new_arrivals", "newest"}:
            # CosmoProf does not expose a category "newest" sort. The new
            # surface is a separate filtered just-arrived page.
            return _JUST_ARRIVED_PERMANENT_URL
        if mode == "most_popular":
            mode = "top_sellers"
        if mode == "top_sellers":
            return super().apply_sort_mode(url, mode)
        return super().apply_sort_mode(url, sort_mode)

    def extract_filter_surfaces(
        self,
        *,
        category_url: str,
        html: str,
        category_key: str,
        allowed_families: Sequence[str] | None = None,
    ) -> list[FilterSurface]:
        return extract_cosmoprofbeauty_filter_surfaces(
            category_url=category_url,
            html=html,
            category_key=category_key,
            retailer=self.retailer,
            allowed_families=allowed_families,
        )

    def next_page_url(
        self, *, current_url: str, html: str, current_page: int
    ) -> str | None:
        parsed = urlparse(current_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        page_size = int(query.get("sz", "24") or "24")
        current_start = int(query.get("start", "0") or "0")
        next_start = current_start + page_size
        query["start"] = str(next_start)
        query.setdefault("sz", str(page_size))
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
