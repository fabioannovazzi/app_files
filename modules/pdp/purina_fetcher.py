from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

import requests

from .fetcher import HTMLFetcher
from .models import FetchResult
from .pacing import HumanPacingController
from .purina_catalog import (
    purina_fetch_result_from_api_product,
    purina_parent_id_from_url,
    purina_semantic_attribute_hints,
)
from .purina_catalog import fetch_purina_wet_cat_food_products
from .purina_filter_discovery import (
    fetch_purina_filter_memberships,
    purina_api_filters_from_search_payload,
)

__all__ = ["PurinaFetcher"]

LOGGER = logging.getLogger(__name__)


class PurinaFetcher(HTMLFetcher):
    """Purina API-backed fetcher for official US Purina PDP rows.

    Purina's public HTML pages block plain ``requests`` in this environment,
    but the official product-search API is directly accessible and contains
    the product rows used by the rendered wet-cat-food catalog. This fetcher
    returns small synthetic HTML documents that embed that official API row so
    the standard PDP parser/storage flow can persist evidence and rows.
    """

    def __init__(
        self,
        *,
        headers: Mapping[str, str] | None = None,
        proxies: Mapping[str, str] | None = None,
        pacing: HumanPacingController | None = None,
        cache_path: Path | None = None,
    ) -> None:
        super().__init__(headers=headers, proxies=proxies, pacing=pacing)
        self._cache_path = cache_path
        self._products_by_parent_id: dict[str, Mapping[str, object]] | None = None

    def fetch(
        self,
        url: str,
        *,
        timeout: float | tuple[float, float] = 20.0,
    ) -> FetchResult:
        if self._pacing is not None:
            self._pacing.wait_before_request()

        parent_id = purina_parent_id_from_url(url)
        if not parent_id:
            response = requests.Response()
            response.status_code = 404
            response.url = url
            raise requests.HTTPError(
                f"Purina parent id not found in URL: {url}", response=response
            )

        products = self._load_products(timeout=timeout)
        product = products.get(parent_id)
        if product is None:
            response = requests.Response()
            response.status_code = 404
            response.url = url
            raise requests.HTTPError(
                f"Purina API product not found: {url}", response=response
            )
        return purina_fetch_result_from_api_product(product, requested_url=url)

    def _load_products(
        self,
        *,
        timeout: float | tuple[float, float],
    ) -> dict[str, Mapping[str, object]]:
        if self._products_by_parent_id is not None:
            return self._products_by_parent_id

        products, first_payload = fetch_purina_wet_cat_food_products(
            self._session,
            timeout=timeout,
        )
        api_filters = purina_api_filters_from_search_payload(first_payload)
        memberships = fetch_purina_filter_memberships(
            self._session,
            api_filters,
            timeout=timeout,
        )
        products_by_parent_id: dict[str, Mapping[str, object]] = {}
        for product in products:
            parent_id = purina_parent_id_from_url(str(product.get("url") or ""))
            if not parent_id:
                continue
            site_filters = memberships.get(parent_id, [])
            enriched = dict(product)
            enriched["site_filters"] = site_filters
            enriched["site_attributes"] = purina_semantic_attribute_hints(
                enriched,
                site_filters=site_filters,
            )
            products_by_parent_id[parent_id] = enriched

        LOGGER.info(
            "Loaded Purina API catalog for parser: products=%d filters=%d",
            len(products_by_parent_id),
            len(api_filters),
        )
        self._products_by_parent_id = products_by_parent_id
        return products_by_parent_id
