from __future__ import annotations

from collections.abc import Sequence

from .cdp_retailer_strategy import BaseCDPRetailerStrategy
from .models import FilterSurface
from .saloncentric_filter_discovery import extract_saloncentric_filter_surfaces

__all__ = ["SaloncentricCDPStrategy"]


class SaloncentricCDPStrategy(BaseCDPRetailerStrategy):
    """SalonCentric-specific CDP listing-discovery strategy."""

    def __init__(self) -> None:
        super().__init__(
            retailer="saloncentric",
            selector=(
                "div.product_tile[data-itemid] a[href$='.html'], "
                "div.product_tile[data-itemid] a[href*='.html?']"
            ),
            default_sort_modes=("newest", "most_popular"),
            filter_sort_modes=("default",),
            pagination_fallback_param=None,
            load_more_texts=("load more",),
        )

    def extract_filter_surfaces(
        self,
        *,
        category_url: str,
        html: str,
        category_key: str,
        allowed_families: Sequence[str] | None = None,
    ) -> list[FilterSurface]:
        return extract_saloncentric_filter_surfaces(
            category_url=category_url,
            html=html,
            category_key=category_key,
            retailer=self.retailer,
            allowed_families=allowed_families,
        )
