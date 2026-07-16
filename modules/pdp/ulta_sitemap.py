from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urlparse, urlunparse
import xml.etree.ElementTree as ET

from .fetcher import HTMLFetcher
from .models import SitemapObservation

ULTA_SITEMAP_SOURCE_URLS: dict[str, str] = {
    "product": "https://www.ulta.com/sitemap/p.xml",
    "category_filter": "https://www.ulta.com/l/category_filter_sitemap.xml",
    "brand_filter": "https://www.ulta.com/l/brand_filter_sitemap.xml",
}

_SITEMAP_NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def crawl_ulta_sitemap_observations(
    *,
    fetcher: HTMLFetcher | None = None,
    sources: Sequence[str] | None = None,
    max_product_sitemaps: int | None = None,
) -> list[SitemapObservation]:
    """Crawl selected Ulta sitemap sources into structured observations."""

    fetcher = fetcher or HTMLFetcher()
    selected_sources = _normalize_sources(sources)
    observations: list[SitemapObservation] = []

    for source in selected_sources:
        if source == "product":
            observations.extend(
                _crawl_product_sitemaps(
                    fetcher=fetcher,
                    max_product_sitemaps=max_product_sitemaps,
                )
            )
            continue

        sitemap_url = ULTA_SITEMAP_SOURCE_URLS[source]
        observations.extend(
            _crawl_urlset_sitemap(
                fetcher=fetcher,
                sitemap_url=sitemap_url,
                url_type=source,
            )
        )

    return observations


def normalize_ulta_url(url: str | None, *, drop_query: bool = True) -> str:
    """Normalize a Ulta URL for stable comparisons across listing and sitemap sources."""

    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    normalized = urlunparse(
        parsed._replace(query="" if drop_query else parsed.query, fragment="")
    )
    if normalized.endswith("/") and parsed.path not in ("", "/"):
        return normalized[:-1]
    return normalized


def _crawl_product_sitemaps(
    *,
    fetcher: HTMLFetcher,
    max_product_sitemaps: int | None,
) -> list[SitemapObservation]:
    root_url = ULTA_SITEMAP_SOURCE_URLS["product"]
    root_result = fetcher.fetch(root_url)
    child_sitemap_urls = _parse_sitemap_index(root_result.html)
    if max_product_sitemaps is not None:
        child_sitemap_urls = child_sitemap_urls[: max(0, int(max_product_sitemaps))]

    observations: list[SitemapObservation] = []
    for sitemap_url in child_sitemap_urls:
        observations.extend(
            _crawl_urlset_sitemap(
                fetcher=fetcher,
                sitemap_url=sitemap_url,
                url_type="product",
            )
        )
    return observations


def _crawl_urlset_sitemap(
    *,
    fetcher: HTMLFetcher,
    sitemap_url: str,
    url_type: str,
) -> list[SitemapObservation]:
    result = fetcher.fetch(sitemap_url)
    entries = _parse_urlset(result.html)
    observations: list[SitemapObservation] = []
    for entry in entries:
        normalized_url = normalize_ulta_url(
            entry["url"],
            drop_query=(url_type == "product"),
        )
        if not normalized_url:
            continue
        observations.append(
            SitemapObservation(
                retailer="ulta",
                sitemap_source=sitemap_url,
                url=normalized_url,
                lastmod=entry["lastmod"],
                url_type=url_type,
            )
        )
    return observations


def _parse_sitemap_index(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    return [
        str(loc.text or "").strip()
        for loc in root.findall("sm:sitemap/sm:loc", _SITEMAP_NAMESPACE)
        if str(loc.text or "").strip()
    ]


def _parse_urlset(xml_text: str) -> list[dict[str, str | None]]:
    root = ET.fromstring(xml_text)
    rows: list[dict[str, str | None]] = []
    for url_node in root.findall("sm:url", _SITEMAP_NAMESPACE):
        loc = url_node.find("sm:loc", _SITEMAP_NAMESPACE)
        if loc is None or not str(loc.text or "").strip():
            continue
        lastmod = url_node.find("sm:lastmod", _SITEMAP_NAMESPACE)
        rows.append(
            {
                "url": str(loc.text or "").strip(),
                "lastmod": (
                    str(lastmod.text or "").strip() or None
                    if lastmod is not None
                    else None
                ),
            }
        )
    return rows


def _normalize_sources(sources: Sequence[str] | None) -> tuple[str, ...]:
    if not sources:
        return ("product",)
    normalized: list[str] = []
    seen: set[str] = set()
    for value in sources:
        source = str(value or "").strip().lower()
        if not source:
            continue
        if source not in ULTA_SITEMAP_SOURCE_URLS:
            raise ValueError(f"Unsupported Ulta sitemap source: {source}")
        if source in seen:
            continue
        normalized.append(source)
        seen.add(source)
    return tuple(normalized) or ("product",)


__all__ = [
    "ULTA_SITEMAP_SOURCE_URLS",
    "crawl_ulta_sitemap_observations",
    "normalize_ulta_url",
]
