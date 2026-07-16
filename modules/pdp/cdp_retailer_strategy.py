from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, Sequence
from urllib.parse import urljoin, urlparse

from .category_keys import profile_category_key
from .cdp_listing_engine import CandidateLink, find_next_page_url
from .discovery import _apply_sort_mode_to_url
from .models import FilterSurface, ListingObservation
from .profile import PDPProfile

__all__ = [
    "BaseCDPRetailerStrategy",
    "CDPRetailerStrategy",
    "strategy_for_retailer",
]


class CDPRetailerStrategy(Protocol):
    """Describe retailer-specific CDP listing-discovery behavior."""

    retailer: str
    selector: str
    default_sort_modes: tuple[str, ...]
    filter_sort_modes: tuple[str, ...]
    recent_sort_mode: str
    popularity_sort_mode: str
    pagination_fallback_param: str | None
    load_more_texts: tuple[str, ...]

    def profile_to_category_key(self, profile_name: str) -> str: ...

    def apply_sort_mode(self, url: str, sort_mode: str) -> str: ...

    def build_observations(
        self,
        *,
        candidates: Sequence[CandidateLink],
        category_key: str,
        source_surface: str,
        sort_mode: str,
        page_number: int,
        listing_url: str,
        profile: PDPProfile,
        seen_urls: set[str],
    ) -> list[ListingObservation]: ...

    def extract_filter_surfaces(
        self,
        *,
        category_url: str,
        html: str,
        category_key: str,
        allowed_families: Sequence[str] | None = None,
    ) -> list[FilterSurface]: ...

    def next_page_url(
        self, *, current_url: str, html: str, current_page: int
    ) -> str | None: ...


@dataclass(slots=True)
class BaseCDPRetailerStrategy:
    """Provide common link-normalization and observation-building behavior."""

    retailer: str
    selector: str
    default_sort_modes: tuple[str, ...]
    filter_sort_modes: tuple[str, ...] = ("default",)
    recent_sort_mode: str = "newest"
    popularity_sort_mode: str = "most_popular"
    pagination_fallback_param: str | None = None
    load_more_texts: tuple[str, ...] = ()

    def profile_to_category_key(self, profile_name: str) -> str:
        return profile_category_key(self.retailer, profile_name)

    def apply_sort_mode(self, url: str, sort_mode: str) -> str:
        return _apply_sort_mode_to_url(url, sort_mode, retailer=self.retailer)

    def build_observations(
        self,
        *,
        candidates: Sequence[CandidateLink],
        category_key: str,
        source_surface: str,
        sort_mode: str,
        page_number: int,
        listing_url: str,
        profile: PDPProfile,
        seen_urls: set[str],
    ) -> list[ListingObservation]:
        observations: list[ListingObservation] = []
        position = 0
        for candidate in candidates:
            raw_url = str(candidate.url or "").strip()
            if not raw_url:
                continue
            canonical_url = self.canonicalize_pdp_url(raw_url, profile=profile)
            if not canonical_url:
                continue
            if not self.is_valid_candidate(
                candidate=candidate,
                canonical_url=canonical_url,
                category_key=category_key,
                profile=profile,
            ):
                continue
            if canonical_url in seen_urls:
                continue
            seen_urls.add(canonical_url)
            position += 1
            observations.append(
                ListingObservation(
                    retailer=self.retailer,
                    category_key=category_key,
                    source_surface=source_surface,
                    sort_mode=sort_mode,
                    page=page_number,
                    position=position,
                    pdp_url=canonical_url,
                    parent_product_id=self.extract_parent_id(
                        canonical_url, profile=profile
                    ),
                    product_name=self.product_name(candidate),
                    brand=None,
                    has_new_badge=False,
                    listing_url=listing_url,
                )
            )
        return observations

    def extract_filter_surfaces(
        self,
        *,
        category_url: str,
        html: str,
        category_key: str,
        allowed_families: Sequence[str] | None = None,
    ) -> list[FilterSurface]:
        return []

    def next_page_url(
        self, *, current_url: str, html: str, current_page: int
    ) -> str | None:
        return find_next_page_url(
            current_url=current_url,
            html=html,
            current_page=current_page,
            fallback_page_param=self.pagination_fallback_param,
        )

    def canonicalize_pdp_url(self, url: str, *, profile: PDPProfile) -> str | None:
        normalized = url.split("?", 1)[0]
        if not normalized:
            return None
        path = urlparse(normalized).path
        return urljoin(profile.base_url.rstrip("/") + "/", path.lstrip("/"))

    def is_valid_candidate(
        self,
        *,
        candidate: CandidateLink,
        canonical_url: str,
        category_key: str,
        profile: PDPProfile,
    ) -> bool:
        pattern = profile.id_extractors.parent_from_url_regex
        if pattern is None:
            return True
        return pattern.search(canonical_url) is not None

    def extract_parent_id(self, url: str, *, profile: PDPProfile) -> str | None:
        pattern = profile.id_extractors.parent_from_url_regex
        if pattern is None:
            return None
        match = pattern.search(url)
        if not match:
            return None
        value = match.group(1) if match.groups() else match.group(0)
        cleaned = str(value or "").strip()
        return cleaned or None

    def product_name(self, candidate: CandidateLink) -> str | None:
        title = " ".join(str(candidate.title or "").split())
        return title or None


def strategy_for_retailer(retailer: str) -> CDPRetailerStrategy:
    """Return the configured CDP strategy for one retailer."""

    retailer_lower = retailer.lower()
    if retailer_lower == "saloncentric":
        from .saloncentric_cdp_strategy import SaloncentricCDPStrategy

        return SaloncentricCDPStrategy()
    if retailer_lower == "amazon":
        from .amazon_cdp_strategy import AmazonCDPStrategy

        return AmazonCDPStrategy()
    if retailer_lower == "cosmoprofbeauty":
        from .cosmoprofbeauty_cdp_strategy import CosmoprofbeautyCDPStrategy

        return CosmoprofbeautyCDPStrategy()
    if retailer_lower == "saksfifthavenue":
        from .saksfifthavenue_cdp_strategy import SaksfifthavenueCDPStrategy

        return SaksfifthavenueCDPStrategy()
    if retailer_lower == "chewy":
        from .chewy_cdp_strategy import ChewyCDPStrategy

        return ChewyCDPStrategy()
    if retailer_lower == "kiko":
        from .kiko_cdp_strategy import KikoCDPStrategy

        return KikoCDPStrategy()
    if retailer_lower == "lorealparis":
        from .lorealparis_cdp_strategy import LorealParisCDPStrategy

        return LorealParisCDPStrategy()
    if retailer_lower == "guestinresidence":
        from .guestinresidence_cdp_strategy import GuestInResidenceCDPStrategy

        return GuestInResidenceCDPStrategy()
    raise ValueError(f"Unsupported CDP discovery retailer: {retailer}")
