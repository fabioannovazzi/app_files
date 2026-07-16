from __future__ import annotations

import re
from collections.abc import Sequence
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from .cdp_listing_engine import CandidateLink, find_next_page_url
from .cdp_retailer_strategy import BaseCDPRetailerStrategy
from .chewy_filter_discovery import extract_chewy_filter_surfaces
from .models import FilterSurface
from .profile import PDPProfile

__all__ = ["ChewyCDPStrategy"]


_CHEWY_PRODUCT_ID_IN_PATH = re.compile(r"/dp/(\d+)", re.IGNORECASE)
_BROWSER_SORT_LABELS = {
    "newest": "Newest",
    "best_selling": "Bestselling",
    "best_sellers": "Bestselling",
    "bestselling": "Bestselling",
    "most_popular": "Bestselling",
}


class ChewyCDPStrategy(BaseCDPRetailerStrategy):
    """Chewy-specific CDP listing-discovery strategy."""

    def __init__(self) -> None:
        super().__init__(
            retailer="chewy",
            selector="a[href]",
            default_sort_modes=("newest", "best_selling"),
            filter_sort_modes=("newest", "best_selling"),
            recent_sort_mode="newest",
            popularity_sort_mode="best_selling",
            pagination_fallback_param=None,
            load_more_texts=(),
        )

    def apply_sort_mode(self, url: str, sort_mode: str) -> str:
        return _without_sort(url)

    def browser_sort_label(self, sort_mode: str) -> str | None:
        """Return the visible Chewy Sort By option for a ranked sort mode."""

        mode = str(sort_mode or "").strip().lower()
        if not mode or mode == "default":
            return None
        return _BROWSER_SORT_LABELS.get(mode)

    def canonicalize_pdp_url(self, url: str, *, profile: PDPProfile) -> str | None:
        match = _CHEWY_PRODUCT_ID_IN_PATH.search(url)
        if not match:
            return None
        normalized = url.split("?", 1)[0].split("#", 1)[0]
        parsed = urlparse(normalized)
        return urlunparse(("https", "www.chewy.com", parsed.path, "", "", ""))

    def is_valid_candidate(
        self,
        *,
        candidate: CandidateLink,
        canonical_url: str,
        category_key: str,
        profile: PDPProfile,
    ) -> bool:
        if candidate.is_sponsored or candidate.is_before_sort_control:
            return False
        if _is_non_product_candidate(candidate=candidate, canonical_url=canonical_url):
            return False
        return super().is_valid_candidate(
            candidate=candidate,
            canonical_url=canonical_url,
            category_key=category_key,
            profile=profile,
        )

    def extract_filter_surfaces(
        self,
        *,
        category_url: str,
        html: str,
        category_key: str,
        allowed_families: Sequence[str] | None = None,
    ) -> list[FilterSurface]:
        return extract_chewy_filter_surfaces(
            category_url=category_url,
            html=html,
            category_key=category_key,
            retailer=self.retailer,
            allowed_families=allowed_families,
        )

    def product_name(self, candidate: CandidateLink) -> str | None:
        if _is_noise_candidate_title(candidate.title):
            return None
        return super().product_name(candidate)

    def next_page_url(
        self, *, current_url: str, html: str, current_page: int
    ) -> str | None:
        candidate = find_next_page_url(
            current_url=current_url,
            html=html,
            current_page=current_page,
            fallback_page_param="page",
        )
        if candidate is None:
            return None
        if not _is_chewy_listing_pagination_url(current_url, candidate):
            return None
        return _preserve_current_sort(current_url, candidate)


def _is_noise_candidate_title(title: str | None) -> bool:
    normalized = " ".join(str(title or "").split()).casefold()
    return (
        not normalized
        or normalized.startswith("slide ")
        or normalized == "by"
        or normalized.startswith("by ")
        or normalized.startswith("image:")
    )


def _is_non_product_candidate(
    *,
    candidate: CandidateLink,
    canonical_url: str,
) -> bool:
    normalized_url = str(canonical_url or "").casefold()
    normalized_title = " ".join(str(candidate.title or "").split()).casefold()
    if "gift-card" in normalized_url or "egift-card" in normalized_url:
        return True
    return normalized_title in {"gift cards", "egift card", "chewy egift card"}


def _is_chewy_listing_pagination_url(current_url: str, next_url: str) -> bool:
    current = urlparse(current_url)
    candidate = urlparse(urljoin(current_url, next_url))
    if "chewy.com" not in candidate.netloc.lower():
        return False
    candidate_path = candidate.path.rstrip("/")
    if not candidate_path.startswith(("/b/", "/f/")):
        return False
    if candidate_path != (current.path.rstrip("/") or current.path):
        return False
    query = dict(parse_qsl(candidate.query, keep_blank_values=True))
    page_keys = {"page", "p", "pageNumber", "pageNum", "currentPage"}
    return any(key in query for key in page_keys)


def _preserve_current_sort(current_url: str, next_url: str) -> str:
    current = urlparse(current_url)
    current_query = dict(parse_qsl(current.query, keep_blank_values=True))
    sort_value = str(current_query.get("sort") or "").strip()
    if not sort_value:
        return next_url
    resolved_next_url = urljoin(current_url, next_url)
    next_query = dict(
        parse_qsl(urlparse(resolved_next_url).query, keep_blank_values=True)
    )
    if str(next_query.get("sort") or "").strip():
        return resolved_next_url
    return _set_query_param(resolved_next_url, "sort", sort_value)


def _without_sort(url: str) -> str:
    parsed = urlparse(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() != "sort"
    ]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def _set_query_param(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    query = [
        (name, item)
        for name, item in parse_qsl(parsed.query, keep_blank_values=True)
        if name.lower() != key.lower()
    ]
    query.append((key, value))
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
