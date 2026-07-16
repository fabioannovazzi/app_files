from __future__ import annotations

import re

from modules.pdp.models import FilterSurface
from modules.pdp.ulta_filter_discovery import (
    crawl_ulta_filter_observations,
    default_filter_families_for_category,
    extract_ulta_filter_surfaces,
)


class _FakeResult:
    def __init__(self, url: str, html: str) -> None:
        self.url = url
        self.html = html


class _FakeFetcher:
    def __init__(self, payloads: dict[str, str]) -> None:
        self.payloads = payloads
        self.calls: list[str] = []

    def fetch(self, url: str):
        self.calls.append(url)
        return _FakeResult(url=url, html=self.payloads[url])


def test_extract_ulta_filter_surfaces_keeps_only_allowed_unique_filters() -> None:
    category_url = "https://www.ulta.com/shop/makeup/lips/lipstick"
    html = """
        <html>
          <body>
            <a href="/shop/makeup/lips/lipstick?finish=matte">Matte 12 Products Available 12</a>
            <a href="/shop/makeup/lips/lipstick?finish=matte">Matte 12 Products Available 12</a>
            <a href="/shop/makeup/lips/lipstick?form=gloss">Gloss 5 Products Available 5</a>
            <a href="/shop/makeup/lips/lipstick?brand=KIKO+Milano">KIKO Milano 2 Products Available 2</a>
            <a href="/shop/makeup/lips/lipstick?price=0-25">Under $25 10 Products Available 10</a>
          </body>
        </html>
    """

    surfaces = extract_ulta_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key="lipstick",
        allowed_families=("finish", "form"),
    )

    assert [
        (item.filter_family, item.filter_value, item.filter_label) for item in surfaces
    ] == [
        ("finish", "matte", "Matte"),
        ("form", "gloss", "Gloss"),
    ]


def test_extract_ulta_filter_surfaces_uses_category_defaults_when_unspecified() -> None:
    category_url = "https://www.ulta.com/shop/makeup/lips/lipstick"
    html = """
        <html>
          <body>
            <a href="/shop/makeup/lips/lipstick?finish=matte">Matte</a>
            <a href="/shop/makeup/lips/lipstick?form=gloss">Gloss</a>
            <a href="/shop/makeup/lips/lipstick?color+lips=pink">Pink</a>
            <a href="/shop/makeup/lips/lipstick?preference=vegan">Vegan</a>
            <a href="/shop/makeup/lips/lipstick?benefit=hydrating">Hydrating</a>
          </body>
        </html>
    """

    surfaces = extract_ulta_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key="lipstick",
    )

    assert [(item.filter_family, item.filter_value) for item in surfaces] == [
        ("color lips", "pink"),
        ("finish", "matte"),
        ("form", "gloss"),
        ("preference", "vegan"),
    ]


def test_default_filter_families_for_category_returns_expected_lip_and_fallback_sets() -> (
    None
):
    assert default_filter_families_for_category("lipstick") == (
        "finish",
        "form",
        "coverage",
        "color lips",
        "preference",
    )
    assert default_filter_families_for_category("mascara") == (
        "benefit",
        "mascara type",
        "waterproof",
        "color eyes",
    )
    assert default_filter_families_for_category("unknown_category")
    assert "finish" in default_filter_families_for_category("unknown_category")


def test_default_filter_families_for_new_ulta_face_categories_use_bridge_defaults() -> (
    None
):
    assert default_filter_families_for_category("bb_cc_creams") == (
        "finish",
        "form",
        "coverage",
        "skin type",
        "spf",
        "color",
    )
    assert default_filter_families_for_category("tinted_moisturizer") == (
        "finish",
        "form",
        "coverage",
        "skin type",
        "concern",
        "spf",
        "color",
    )
    assert default_filter_families_for_category("color_correct") == (
        "finish",
        "form",
        "coverage",
        "skin type",
        "spf",
        "color",
    )
    assert default_filter_families_for_category("contour") == (
        "finish",
        "form",
    )


def test_crawl_ulta_filter_observations_records_memberships() -> None:
    payloads = {
        "https://www.ulta.com/shop/makeup/lips/lipstick?finish=matte&sort=best_sellers": """
            <html>
              <body>
                <ul>
                  <li class="ProductListingResults__productCard">
                    <a href="https://www.ulta.com/p/matte-one-pimprod1">Matte One</a>
                  </li>
                  <li class="ProductListingResults__productCard">
                    <a href="https://www.ulta.com/p/matte-two-pimprod2">Matte Two</a>
                  </li>
                </ul>
              </body>
            </html>
        """
    }
    fetcher = _FakeFetcher(payloads)
    surfaces = [
        FilterSurface(
            retailer="ulta",
            category_key="lipstick",
            filter_family="finish",
            filter_value="matte",
            filter_url="https://www.ulta.com/shop/makeup/lips/lipstick?finish=matte",
            filter_label="Matte",
        )
    ]

    observations = crawl_ulta_filter_observations(
        surfaces,
        fetcher=fetcher,  # type: ignore[arg-type]
        max_pages=0,
        delay_seconds=0.0,
        allowed_patterns=(re.compile(r"(pimprod\d+)"),),
        parent_id_pattern=re.compile(r"((?:pimprod|mkt|xlsImpprod)[0-9A-Za-z]+)"),
        canonical_base_url=None,
    )

    assert [
        (item.filter_family, item.filter_value, item.parent_product_id)
        for item in observations
    ] == [
        ("finish", "matte", "pimprod1"),
        ("finish", "matte", "pimprod2"),
    ]
