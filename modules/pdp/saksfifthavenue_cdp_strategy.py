from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .cdp_retailer_strategy import BaseCDPRetailerStrategy
from .models import FilterSurface
from .saksfifthavenue_filter_discovery import (
    extract_saksfifthavenue_filter_surfaces,
)

__all__ = ["SaksfifthavenueCDPStrategy"]


_SORT_VALUES = {
    "new_arrivals": "new-arrivals",
    "newest": "new-arrivals",
    "best_sellers": "best-sellers-dollars",
    "top_sellers": "best-sellers-dollars",
    "most_popular": "best-sellers-dollars",
    "sale_first": "sale-first",
    "sales_first": "sale-first",
    "sale": "sale-first",
}


class SaksfifthavenueCDPStrategy(BaseCDPRetailerStrategy):
    """Saks Fifth Avenue-specific CDP listing-discovery strategy."""

    def __init__(self) -> None:
        super().__init__(
            retailer="saksfifthavenue",
            selector=(
                "a[href*='/product/'][href$='.html'], "
                "a[href*='/product/'][href*='.html?']"
            ),
            default_sort_modes=("new_arrivals", "best_sellers", "sales_first"),
            filter_sort_modes=("default",),
            recent_sort_mode="new_arrivals",
            popularity_sort_mode="best_sellers",
            pagination_fallback_param="start",
            load_more_texts=(),
        )

    def apply_sort_mode(self, url: str, sort_mode: str) -> str:
        mode = str(sort_mode or "").strip().lower()
        if mode in {"", "default"}:
            return _without_sort(url)
        sort_value = _SORT_VALUES.get(mode)
        if not sort_value:
            return _without_sort(url)
        return _set_query_param(url, "srule", sort_value)

    def extract_filter_surfaces(
        self,
        *,
        category_url: str,
        html: str,
        category_key: str,
        allowed_families: Sequence[str] | None = None,
    ) -> list[FilterSurface]:
        return extract_saksfifthavenue_filter_surfaces(
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
        if "/product/" in parsed.path.lower():
            return None
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        page_size = int(query.get("sz", "24") or "24")
        current_start = int(query.get("start", "0") or "0")
        next_start = current_start + page_size
        query["start"] = str(next_start)
        query.setdefault("sz", str(page_size))
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def _without_sort(url: str) -> str:
    parsed = urlparse(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() != "srule"
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
