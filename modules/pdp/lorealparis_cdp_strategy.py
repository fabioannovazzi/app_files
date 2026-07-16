from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urljoin, urlparse

from .cdp_listing_engine import CandidateLink
from .cdp_retailer_strategy import BaseCDPRetailerStrategy
from .lorealparis_catalog import (
    LOREALPARIS_BASE_URL,
    LOREALPARIS_RETAILER,
    lorealparis_category_from_url,
    lorealparis_family_url,
    lorealparis_parent_id_from_url,
)
from .lorealparis_filter_discovery import extract_lorealparis_filter_surfaces
from .models import FilterSurface
from .profile import PDPProfile

__all__ = ["LorealParisCDPStrategy"]


class LorealParisCDPStrategy(BaseCDPRetailerStrategy):
    """CDP listing-discovery strategy for L'Oreal Paris USA face pages."""

    def __init__(self) -> None:
        super().__init__(
            retailer=LOREALPARIS_RETAILER,
            selector=(
                'a[href*="/makeup/face/blush/"], ' 'a[href*="/makeup/face/bronzer/"]'
            ),
            default_sort_modes=("default",),
            filter_sort_modes=("default",),
            recent_sort_mode="",
            popularity_sort_mode="",
        )

    def canonicalize_pdp_url(self, url: str, *, profile: PDPProfile) -> str | None:
        parsed = urlparse(urljoin(LOREALPARIS_BASE_URL, url))
        category_key = lorealparis_category_from_url(parsed.geturl())
        parent_id = lorealparis_parent_id_from_url(parsed.geturl())
        if not category_key or not parent_id:
            return None
        return lorealparis_family_url(category_key, parent_id)

    def is_valid_candidate(
        self,
        *,
        candidate: CandidateLink,
        canonical_url: str,
        category_key: str,
        profile: PDPProfile,
    ) -> bool:
        url_category = lorealparis_category_from_url(canonical_url)
        if url_category != category_key:
            return False
        title = str(candidate.title or "").strip().lower()
        return title not in {"try it", "buy online"}

    def extract_parent_id(self, url: str, *, profile: PDPProfile) -> str | None:
        return lorealparis_parent_id_from_url(url)

    def extract_filter_surfaces(
        self,
        *,
        category_url: str,
        html: str,
        category_key: str,
        allowed_families: Sequence[str] | None = None,
    ) -> list[FilterSurface]:
        return extract_lorealparis_filter_surfaces(
            category_url=category_url,
            html=html,
            category_key=category_key,
            allowed_families=allowed_families,
        )
