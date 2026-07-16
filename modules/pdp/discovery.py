from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Iterable, Sequence
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup  # type: ignore[import]

from .fetcher import HTMLFetcher
from .models import ListingObservation

_logger = logging.getLogger(__name__)

KIKO_ALGOLIA_APP_ID = os.getenv("KIKO_ALGOLIA_APP_ID", "S6XPHBOA7P")
KIKO_ALGOLIA_API_KEY = os.getenv("KIKO_ALGOLIA_API_KEY", "").strip()

_RETAILER_SORT_QUERY_KEY: dict[str, str] = {
    "amazon": "s",
    "saloncentric": "srule",
    "cosmoprofbeauty": "srule",
}

_RETAILER_SORT_VALUE_MAP: dict[str, dict[str, str]] = {
    "amazon": {
        # Amazon does not expose a literal "most popular" sort in search, so
        # map the generic cohort concept to the closest stable browse sort.
        "most_popular": "review-rank",
        "best_selling": "exact-aware-popularity-rank",
        "best_sellers": "exact-aware-popularity-rank",
        "top_selling": "exact-aware-popularity-rank",
        "top_sellers": "exact-aware-popularity-rank",
        "newest": "date-desc-rank",
    },
    "ulta": {
        "best_sellers": "best_sellers",
        "new_arrivals": "new_arrivals",
        "top_rated": "top_rated",
    },
    "saloncentric": {
        "most_popular": "most-popular",
        "newest": "newest",
    },
    "cosmoprofbeauty": {
        "top_sellers": "top-sellers",
        "most_popular": "top-sellers",
    },
    "chewy": {
        "newest": "newest",
        "best_selling": "bestselling",
        "best_sellers": "bestselling",
        "bestselling": "bestselling",
        "most_popular": "bestselling",
    },
}


def discover_pdp_urls(
    category_urls: Iterable[str],
    *,
    max_pages: int = 200,
    fetcher: HTMLFetcher | None = None,
    delay_seconds: float = 2.0,
    allowed_patterns: Sequence[re.Pattern[str]] | None = None,
    raise_on_error: bool = False,
    retailer: str | None = None,
) -> list[str]:
    """Discover PDP URLs from one or more category/PLP URLs."""

    observations = discover_listing_observations(
        category_urls,
        category_key="",
        max_pages=max_pages,
        fetcher=fetcher,
        delay_seconds=delay_seconds,
        allowed_patterns=allowed_patterns,
        raise_on_error=raise_on_error,
        retailer=retailer,
    )
    return sorted({observation.pdp_url for observation in observations})


def discover_listing_observations(
    category_urls: Iterable[str],
    *,
    category_key: str,
    max_pages: int = 200,
    fetcher: HTMLFetcher | None = None,
    delay_seconds: float = 2.0,
    allowed_patterns: Sequence[re.Pattern[str]] | None = None,
    raise_on_error: bool = False,
    retailer: str | None = None,
    sort_modes: Sequence[str] | None = None,
    source_surface: str = "category",
    parent_id_pattern: re.Pattern[str] | None = None,
    canonical_base_url: str | None = None,
) -> list[ListingObservation]:
    """Discover structured listing observations from one or more category URLs."""

    fetcher = fetcher or HTMLFetcher()
    normalized_sorts = _normalize_sort_modes(sort_modes, retailer=retailer)
    retailer_lower = str(retailer or "").strip().lower()
    observations: list[ListingObservation] = []

    for category_url in category_urls:
        if not category_url:
            continue

        for sort_mode in normalized_sorts:
            listing_seen: set[str] = set()
            sorted_url = _apply_sort_mode_to_url(
                category_url,
                sort_mode,
                retailer=retailer,
            )

            try:
                result = fetcher.fetch(sorted_url)
            except Exception as exc:
                _logger.warning(
                    "Failed to fetch category URL %s (sort=%s): %s",
                    sorted_url,
                    sort_mode,
                    exc,
                )
                if raise_on_error:
                    raise RuntimeError(
                        f"Failed to fetch category URL {sorted_url}: {exc}"
                    ) from exc
                continue

            page_observations = _extract_listing_observations(
                html=result.html,
                listing_url=result.url,
                retailer=retailer,
                category_key=category_key,
                source_surface=source_surface,
                sort_mode=sort_mode,
                page=_initial_page_number(result.url),
                allowed_patterns=allowed_patterns,
                parent_id_pattern=parent_id_pattern,
                canonical_base_url=canonical_base_url,
                seen_urls=listing_seen,
            )
            observations.extend(page_observations)

            if retailer_lower == "kiko":
                try:
                    extra = _discover_kiko_algolia_urls(
                        category_url,
                        result,
                        fetcher,
                        allowed_patterns,
                        listing_seen,
                    )
                    for index, url in enumerate(
                        extra, start=len(page_observations) + 1
                    ):
                        observations.append(
                            ListingObservation(
                                retailer=str(retailer or ""),
                                category_key=category_key,
                                source_surface=source_surface,
                                sort_mode=sort_mode,
                                page=_initial_page_number(result.url),
                                position=index,
                                pdp_url=url,
                                parent_product_id=_extract_parent_id(
                                    url, parent_id_pattern
                                ),
                                product_name=None,
                                listing_url=result.url,
                            )
                        )
                except Exception as exc:  # noqa: BLE001 - defensive logging
                    _logger.debug(
                        "KIKO Algolia enrichment failed for %s: %s", category_url, exc
                    )
                # KIKO PLPs are backed by the Algolia payload embedded in the first
                # category response. Query-string pagination adds duplicate page
                # shell requests and can make full-retailer discovery needlessly slow.
                continue

            if retailer_lower == "chewy":
                visited_page_urls = {result.url}
                current_page = _initial_page_number(result.url) + 1
                next_url = _find_next_listing_page_url(result.html, result.url)
                while next_url and current_page <= max_pages:
                    if next_url in visited_page_urls:
                        break
                    visited_page_urls.add(next_url)
                    try:
                        page_result = fetcher.fetch(next_url)
                    except Exception as exc:
                        _logger.warning(
                            "Failed to fetch category page %s (sort=%s): %s",
                            next_url,
                            sort_mode,
                            exc,
                        )
                        if raise_on_error:
                            raise RuntimeError(
                                f"Failed to fetch category page {next_url}: {exc}"
                            ) from exc
                        break

                    page_observations = _extract_listing_observations(
                        html=page_result.html,
                        listing_url=page_result.url,
                        retailer=retailer,
                        category_key=category_key,
                        source_surface=source_surface,
                        sort_mode=sort_mode,
                        page=current_page,
                        allowed_patterns=allowed_patterns,
                        parent_id_pattern=parent_id_pattern,
                        canonical_base_url=canonical_base_url,
                        seen_urls=listing_seen,
                    )
                    observations.extend(page_observations)

                    if not page_observations:
                        break
                    if delay_seconds > 0:
                        time.sleep(delay_seconds)
                    current_page += 1
                    next_url = _find_next_listing_page_url(
                        page_result.html, page_result.url
                    )
                continue

            parsed = urlparse(result.url)
            base_query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            page_key = _detect_page_key(base_query)
            has_explicit_page = page_key in base_query
            current_page = int(base_query.get(page_key, "0")) + 1

            while current_page <= max_pages:
                page_url = _replace_query_param(parsed, page_key, str(current_page))
                try:
                    page_result = fetcher.fetch(page_url)
                except Exception as exc:
                    _logger.warning(
                        "Failed to fetch category page %s (sort=%s): %s",
                        page_url,
                        sort_mode,
                        exc,
                    )
                    if raise_on_error:
                        raise RuntimeError(
                            f"Failed to fetch category page {page_url}: {exc}"
                        ) from exc
                    break

                page_observations = _extract_listing_observations(
                    html=page_result.html,
                    listing_url=page_result.url,
                    retailer=retailer,
                    category_key=category_key,
                    source_surface=source_surface,
                    sort_mode=sort_mode,
                    page=current_page,
                    allowed_patterns=allowed_patterns,
                    parent_id_pattern=parent_id_pattern,
                    canonical_base_url=canonical_base_url,
                    seen_urls=listing_seen,
                )
                observations.extend(page_observations)

                if not page_observations:
                    # Some retailer PLPs treat the bare category URL and ``?page=1`` as the
                    # same first page. In that case the first paginated request adds no new
                    # links even though later pages still exist. Give the crawl one extra page
                    # before stopping.
                    if not has_explicit_page and current_page == 1:
                        if delay_seconds > 0:
                            time.sleep(delay_seconds)
                        current_page += 1
                        continue
                    break

                if delay_seconds > 0:
                    time.sleep(delay_seconds)
                current_page += 1

    return observations


__all__ = ["discover_listing_observations", "discover_pdp_urls"]


def _normalize_sort_modes(
    sort_modes: Sequence[str] | None,
    *,
    retailer: str | None = None,
) -> tuple[str, ...]:
    normalized_retailer = str(retailer or "").strip().lower()
    default_mode = (
        "best_sellers"
        if normalized_retailer == "ulta"
        else "newest" if normalized_retailer == "chewy" else "default"
    )
    if not sort_modes:
        return (default_mode,)
    normalized: list[str] = []
    seen: set[str] = set()
    for value in sort_modes:
        mode = str(value or "").strip().lower()
        if not mode:
            continue
        if normalized_retailer == "ulta" and mode == "default":
            mode = "best_sellers"
        if mode not in seen:
            normalized.append(mode)
            seen.add(mode)
    return tuple(normalized) or (default_mode,)


def _apply_sort_mode_to_url(
    url: str,
    sort_mode: str,
    *,
    retailer: str | None,
) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    retailer_key = str(retailer or "").strip().lower()
    sort_query_key = _RETAILER_SORT_QUERY_KEY.get(retailer_key, "sort")
    value_map = _RETAILER_SORT_VALUE_MAP.get(retailer_key, {})
    if sort_mode == "default":
        query.pop(sort_query_key, None)
        # Clean legacy default sort parameter key when using retailer-specific keys.
        if sort_query_key != "sort":
            query.pop("sort", None)
    else:
        mapped_value = value_map.get(sort_mode, sort_mode)
        query[sort_query_key] = mapped_value
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def _replace_query_param(parsed, key: str, value: str) -> str:
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query[key] = value
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def _detect_page_key(query: dict[str, str]) -> str:
    if "pageNumber" in query:
        return "pageNumber"
    if "page" in query:
        return "page"
    return "page"


def _initial_page_number(url: str) -> int:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    page_key = _detect_page_key(query)
    value = query.get(page_key)
    if value is None:
        return 1
    try:
        return int(value)
    except ValueError:
        return 1


def _find_next_listing_page_url(html: str, listing_url: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith("javascript:"):
            continue
        rel = " ".join(anchor.get("rel", []))
        text = " ".join(anchor.get_text(" ", strip=True).split()).casefold()
        aria = str(anchor.get("aria-label") or "").strip().casefold()
        title = str(anchor.get("title") or "").strip().casefold()
        if rel == "next" or text == "next" or "next" in aria or "next" in title:
            return urljoin(listing_url, href)
    return None


def _extract_listing_observations(
    *,
    html: str,
    listing_url: str,
    retailer: str | None,
    category_key: str,
    source_surface: str,
    sort_mode: str,
    page: int,
    allowed_patterns: Sequence[re.Pattern[str]] | None,
    parent_id_pattern: re.Pattern[str] | None,
    canonical_base_url: str | None,
    seen_urls: set[str],
) -> list[ListingObservation]:
    soup = BeautifulSoup(html, "lxml")
    observations: list[ListingObservation] = []
    position = 0
    retailer_lower = str(retailer or "").strip().lower()

    for anchor in _select_listing_anchors(soup, retailer):
        href = anchor.get("href")
        if not href:
            continue
        if _should_skip_listing_anchor(anchor, retailer):
            continue
        full_url = urljoin(listing_url, href)
        normalized = _normalize_listing_pdp_url(
            full_url,
            canonical_base_url=canonical_base_url,
        )
        if allowed_patterns:
            if not any(pattern.search(normalized) for pattern in allowed_patterns):
                continue
        elif "/p/" not in normalized and not (
            retailer_lower == "chewy" and "/dp/" in normalized
        ):
            continue
        if normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        position += 1
        observations.append(
            ListingObservation(
                retailer=str(retailer or ""),
                category_key=category_key,
                source_surface=source_surface,
                sort_mode=sort_mode,
                page=page,
                position=position,
                pdp_url=normalized,
                parent_product_id=_extract_parent_id(normalized, parent_id_pattern),
                product_name=_extract_anchor_label(anchor),
                has_new_badge=_extract_ulta_has_new_badge(anchor, retailer),
                listing_url=listing_url,
            )
        )
    return observations


def _select_listing_anchors(soup: BeautifulSoup, retailer: str | None):
    retailer_lower = str(retailer or "").strip().lower()
    if retailer_lower == "ulta":
        product_card_anchors = soup.select(
            'li.ProductListingResults__productCard a[href*="/p/"]'
        )
        return product_card_anchors
    if retailer_lower == "chewy":
        return soup.select('a[href*="/dp/"]')
    return soup.select("a[href]")


def _should_skip_listing_anchor(anchor, retailer: str | None) -> bool:
    retailer_lower = str(retailer or "").strip().lower()
    if retailer_lower != "chewy":
        return False
    label = _extract_anchor_label(anchor) or ""
    normalized = " ".join(label.split()).casefold()
    return (
        not normalized
        or normalized.startswith("slide ")
        or normalized == "by"
        or normalized.startswith("by ")
        or normalized.startswith("image:")
    )


def _normalize_listing_pdp_url(
    full_url: str,
    *,
    canonical_base_url: str | None,
) -> str:
    normalized = full_url.split("?")[0]
    if not canonical_base_url:
        return normalized
    path = urlparse(normalized).path
    return urljoin(canonical_base_url.rstrip("/") + "/", path.lstrip("/"))


def _extract_parent_id(
    url: str,
    pattern: re.Pattern[str] | None,
) -> str | None:
    if pattern is None:
        return None
    match = pattern.search(url)
    if not match:
        return None
    value = match.group(1) if match.groups() else match.group(0)
    cleaned = str(value or "").strip()
    return cleaned or None


def _extract_anchor_label(anchor) -> str | None:
    text = anchor.get_text(" ", strip=True)
    if text:
        return text
    aria_label = str(anchor.get("aria-label") or "").strip()
    if aria_label:
        return aria_label
    title = str(anchor.get("title") or "").strip()
    if title:
        return title
    return None


def _extract_ulta_has_new_badge(anchor, retailer: str | None) -> bool:
    retailer_lower = str(retailer or "").strip().lower()
    if retailer_lower != "ulta":
        return False

    card = anchor.find_parent("li", class_="ProductListingResults__productCard")
    if card is None:
        return False

    for tag in card.select(".pal-c-Tag__messageText"):
        text = str(tag.get_text(" ", strip=True) or "").strip().casefold()
        if text == "new":
            return True
    return False


def _discover_kiko_algolia_urls(
    category_url: str,
    result: object,
    fetcher: HTMLFetcher,
    allowed_patterns: Sequence[re.Pattern[str]] | None,
    seen: set[str],
) -> list[str]:
    if not KIKO_ALGOLIA_APP_ID:
        return []

    locale = _extract_locale_from_url(
        result.url if hasattr(result, "url") else category_url
    )
    soup = BeautifulSoup(result.html, "lxml")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return []

    try:
        page_props = json.loads(script.string)["props"]["pageProps"]
    except (KeyError, json.JSONDecodeError):
        return []

    server_state = page_props.get("serverState", {})
    initial_results = server_state.get("initialResults", {})
    if not isinstance(initial_results, dict):
        return []

    urls: list[str] = []
    session = getattr(fetcher, "_session", None)
    if session is None:
        import requests

        session = requests.Session()

    for index_name, payload in initial_results.items():
        if not isinstance(payload, dict):
            continue
        url_candidates = _kiko_urls_from_algolia_payload(
            session,
            index_name,
            payload,
            locale,
        )
        for canonical in url_candidates:
            normalized = canonical.split("?")[0]
            if allowed_patterns:
                if not any(pattern.search(normalized) for pattern in allowed_patterns):
                    continue
            elif "/p/" not in normalized:
                continue
            if normalized not in seen:
                seen.add(normalized)
                urls.append(normalized)
        break  # single index per category
    return urls


def _kiko_urls_from_algolia_payload(
    session, index_name: str, payload: dict, locale: str
) -> list[str]:
    results = payload.get("results") or []
    if not results:
        return []

    primary = results[0] or {}
    hits = primary.get("hits") or []
    params_str = primary.get("params")
    nb_pages = int(primary.get("nbPages") or 1)

    urls = [
        _kiko_slug_to_url(
            locale,
            hit.get("slug"),
            hit.get("product_id")
            or hit.get("productId")
            or hit.get("objectID")
            or hit.get("product_next_id"),
        )
        for hit in hits
    ]
    urls = [url for url in urls if url]

    if (
        nb_pages <= 1
        or not params_str
        or not KIKO_ALGOLIA_APP_ID
        or not KIKO_ALGOLIA_API_KEY
    ):
        return urls

    query_params = dict(parse_qsl(params_str, keep_blank_values=True))
    algolia_url = f"https://{KIKO_ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/*/queries"
    headers = {
        "X-Algolia-Application-Id": KIKO_ALGOLIA_APP_ID,
        "X-Algolia-API-Key": KIKO_ALGOLIA_API_KEY,
        "Content-Type": "application/json",
    }

    for page_number in range(1, nb_pages):
        query_params["page"] = str(page_number)
        encoded = urlencode(query_params, doseq=True)
        body = {"requests": [{"indexName": index_name, "params": encoded}]}
        response = session.post(algolia_url, headers=headers, json=body, timeout=15)
        if response.status_code != 200:
            _logger.debug(
                "Algolia request failed (%s - %s) for %s page %s",
                response.status_code,
                response.text[:200],
                index_name,
                page_number,
            )
            break
        try:
            payload_json = response.json()
        except json.JSONDecodeError:
            break
        page_hits = (payload_json.get("results") or [{}])[0].get("hits") or []
        page_urls = [
            _kiko_slug_to_url(
                locale,
                hit.get("slug"),
                hit.get("product_id")
                or hit.get("productId")
                or hit.get("objectID")
                or hit.get("product_next_id"),
            )
            for hit in page_hits
        ]
        urls.extend([url for url in page_urls if url])
    return urls


def _kiko_slug_to_url(
    locale: str, slug: str | None, product_id: str | None = None
) -> str | None:
    if not slug:
        return None
    slug = slug.strip("/")
    if not slug:
        return None
    product_id = str(product_id).strip() if product_id else ""
    if product_id.isdigit() and not slug.endswith(product_id):
        base = slug.rstrip("-")
        slug = f"{base}-{product_id}"
    return f"https://www.kikocosmetics.com/{locale}/p/{slug}/"


def _extract_locale_from_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [segment for segment in parsed.path.strip("/").split("/") if segment]
    if parts:
        return parts[0]
    return "en-us"
