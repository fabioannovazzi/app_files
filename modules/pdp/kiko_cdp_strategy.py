from __future__ import annotations

from collections.abc import Sequence

from .cdp_retailer_strategy import BaseCDPRetailerStrategy
from .kiko_filter_discovery import extract_kiko_filter_surfaces
from .models import FilterSurface

__all__ = ["KikoCDPStrategy"]


class KikoCDPStrategy(BaseCDPRetailerStrategy):
    """CDP listing-discovery strategy for Kiko category pages."""

    def __init__(self) -> None:
        super().__init__(
            retailer="kiko",
            selector='a[href*="/p/"]',
            default_sort_modes=(),
            filter_sort_modes=("default",),
            recent_sort_mode="",
            popularity_sort_mode="",
        )

    def extract_filter_surfaces(
        self,
        *,
        category_url: str,
        html: str,
        category_key: str,
        allowed_families: Sequence[str] | None = None,
    ) -> list[FilterSurface]:
        return extract_kiko_filter_surfaces(
            category_url=category_url,
            html=html,
            category_key=category_key,
            allowed_families=allowed_families,
        )
