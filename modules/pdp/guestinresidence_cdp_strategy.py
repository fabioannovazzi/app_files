from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .cdp_listing_engine import CandidateLink
from .cdp_retailer_strategy import BaseCDPRetailerStrategy
from .guestinresidence_catalog import (
    GUESTINRESIDENCE_BASE_URL,
    GUESTINRESIDENCE_CATEGORY_KEY,
    GUESTINRESIDENCE_RETAILER,
    guestinresidence_cashmere_scope_decision,
    guestinresidence_parent_id_from_url,
    guestinresidence_product_url,
)
from .guestinresidence_filter_discovery import (
    extract_guestinresidence_filter_surfaces,
)
from .models import FilterSurface
from .profile import PDPProfile

__all__ = ["GuestInResidenceCDPStrategy"]

LOGGER = logging.getLogger(__name__)


class GuestInResidenceCDPStrategy(BaseCDPRetailerStrategy):
    """CDP listing-discovery strategy for Guest in Residence collection pages."""

    def __init__(self) -> None:
        super().__init__(
            retailer=GUESTINRESIDENCE_RETAILER,
            selector="a[href*='/products/']",
            default_sort_modes=("default",),
            filter_sort_modes=("default",),
            recent_sort_mode="",
            popularity_sort_mode="",
        )
        self._allowed_handles_by_profile: dict[str, set[str]] = {}

    def canonicalize_pdp_url(self, url: str, *, profile: PDPProfile) -> str | None:
        handle = guestinresidence_parent_id_from_url(
            urljoin(GUESTINRESIDENCE_BASE_URL, url)
        )
        if not handle:
            return None
        return guestinresidence_product_url(handle)

    def is_valid_candidate(
        self,
        *,
        candidate: CandidateLink,
        canonical_url: str,
        category_key: str,
        profile: PDPProfile,
    ) -> bool:
        if category_key != GUESTINRESIDENCE_CATEGORY_KEY:
            return False
        handle = guestinresidence_parent_id_from_url(canonical_url)
        if not handle:
            return False
        allowed = self._allowed_handles(profile)
        if allowed:
            return handle in allowed
        title = str(candidate.title or "").strip().casefold()
        url = str(canonical_url or "").casefold()
        return "cashmere" in title or "cashmere" in url

    def extract_parent_id(self, url: str, *, profile: PDPProfile) -> str | None:
        return guestinresidence_parent_id_from_url(url)

    def extract_filter_surfaces(
        self,
        *,
        category_url: str,
        html: str,
        category_key: str,
        allowed_families: Sequence[str] | None = None,
    ) -> list[FilterSurface]:
        return extract_guestinresidence_filter_surfaces(
            category_url=category_url,
            html=html,
            category_key=category_key,
            allowed_families=allowed_families,
        )

    def _allowed_handles(self, profile: PDPProfile) -> set[str]:
        profile_name = str(profile.profile_name or "")
        if profile_name not in self._allowed_handles_by_profile:
            self._allowed_handles_by_profile[profile_name] = _load_allowed_handles(
                profile.category_urls
            )
        return self._allowed_handles_by_profile[profile_name]


def _products_json_url(collection_url: str, page: int) -> str:
    base = str(collection_url or "").rstrip("/")
    return f"{base}/products.json?limit=250&page={page}"


def _fetch_products(url: str) -> list[Mapping[str, object]]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
            ),
        },
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    products = payload.get("products") if isinstance(payload, Mapping) else None
    if not isinstance(products, list):
        return []
    return [product for product in products if isinstance(product, Mapping)]


def _load_allowed_handles(category_urls: Sequence[str]) -> set[str]:
    allowed: set[str] = set()
    for category_url in category_urls:
        for page in range(1, 6):
            try:
                products = _fetch_products(_products_json_url(category_url, page))
            except Exception as exc:  # noqa: BLE001 - discovery can fall back to DOM.
                LOGGER.info(
                    "Unable to load GIR products.json for scope filtering at %s: %s",
                    category_url,
                    exc,
                )
                break
            if not products:
                break
            for product in products:
                include, _reason = guestinresidence_cashmere_scope_decision(product)
                handle = str(product.get("handle") or "").strip().lower()
                if include and handle:
                    allowed.add(handle)
            if len(products) < 250:
                break
    return allowed
