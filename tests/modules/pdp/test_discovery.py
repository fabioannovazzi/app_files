from __future__ import annotations

import json
import re
from dataclasses import dataclass

from modules.pdp.discovery import discover_listing_observations, discover_pdp_urls


@dataclass
class _FakeResult:
    url: str
    html: str


class _FakeFetcher:
    def __init__(self, payloads: dict[str, str]) -> None:
        self.payloads = payloads
        self.calls: list[str] = []

    def fetch(self, url: str) -> _FakeResult:
        self.calls.append(url)
        return _FakeResult(url=url, html=self.payloads[url])


def test_discover_pdp_urls_continues_past_duplicate_page_one() -> None:
    base_url = "https://www.ulta.com/shop/makeup/lips/lip-oil"
    best_sellers_url = f"{base_url}?sort=best_sellers"
    page_one = f"{best_sellers_url}&page=1"
    page_two = f"{best_sellers_url}&page=2"

    payloads = {
        best_sellers_url: """
            <html>
              <body>
                <li class="ProductListingResults__productCard">
                  <a href="/p/base-product-pimprod1">Base product</a>
                </li>
              </body>
            </html>
        """,
        page_one: """
            <html>
              <body>
                <li class="ProductListingResults__productCard">
                  <a href="/p/base-product-pimprod1">Base product</a>
                </li>
              </body>
            </html>
        """,
        page_two: """
            <html>
              <body>
                <li class="ProductListingResults__productCard">
                  <a href="/p/base-product-pimprod1">Base product</a>
                </li>
                <li class="ProductListingResults__productCard">
                  <a href="/p/page-two-product-pimprod2">Second page product</a>
                </li>
              </body>
            </html>
        """,
    }

    fetcher = _FakeFetcher(payloads)

    # Act
    urls = discover_pdp_urls(
        [base_url],
        max_pages=2,
        fetcher=fetcher,
        delay_seconds=0.0,
        retailer="ulta",
    )

    # Assert
    assert page_one in fetcher.calls
    assert page_two in fetcher.calls
    assert urls == [
        "https://www.ulta.com/p/base-product-pimprod1",
        "https://www.ulta.com/p/page-two-product-pimprod2",
    ]


def test_discover_pdp_urls_uses_kiko_algolia_without_query_pagination() -> None:
    base_url = "https://www.kikocosmetics.com/en-us/c/skincare/face/moisturizing/"
    next_data = {
        "props": {
            "pageProps": {
                "serverState": {
                    "initialResults": {
                        "kiko_us_products": {
                            "results": [
                                {
                                    "hits": [
                                        {
                                            "slug": "kind-by-kiko-sorbet-hydra-face-cream",
                                            "product_id": "45110",
                                        }
                                    ],
                                    "nbPages": 1,
                                    "params": "",
                                }
                            ]
                        }
                    }
                }
            }
        }
    }
    payloads = {
        base_url: (
            '<html><body><script id="__NEXT_DATA__" type="application/json">'
            f"{json.dumps(next_data)}"
            "</script></body></html>"
        ),
    }
    fetcher = _FakeFetcher(payloads)

    urls = discover_pdp_urls(
        [base_url],
        max_pages=3,
        fetcher=fetcher,
        delay_seconds=0.0,
        retailer="kiko",
    )

    assert fetcher.calls == [base_url]
    assert urls == [
        "https://www.kikocosmetics.com/en-us/p/kind-by-kiko-sorbet-hydra-face-cream-45110/"
    ]


def test_discover_listing_observations_records_sort_modes_and_positions() -> None:
    base_url = "https://www.ulta.com/shop/makeup/lips/lipstick"
    best_sellers_url = f"{base_url}?sort=best_sellers"
    new_arrivals_url = f"{base_url}?sort=new_arrivals"
    payloads = {
        best_sellers_url: """
            <html>
              <body>
                <li class="ProductListingResults__productCard">
                  <a href="/p/matte-product-pimprod1">Matte Product</a>
                </li>
                <li class="ProductListingResults__productCard">
                  <a href="/p/glossy-product-pimprod2">Glossy Product</a>
                </li>
              </body>
            </html>
        """,
        new_arrivals_url: """
            <html>
              <body>
                <li class="ProductListingResults__productCard">
                  <a href="/p/new-product-pimprod3">New Product</a>
                </li>
              </body>
            </html>
        """,
    }
    fetcher = _FakeFetcher(payloads)

    observations = discover_listing_observations(
        [base_url],
        category_key="lipstick",
        max_pages=0,
        fetcher=fetcher,
        delay_seconds=0.0,
        retailer="ulta",
        sort_modes=("best_sellers", "new_arrivals"),
        parent_id_pattern=re.compile(r"(pimprod\d+)"),
    )

    assert [item.sort_mode for item in observations] == [
        "best_sellers",
        "best_sellers",
        "new_arrivals",
    ]
    assert [item.position for item in observations] == [1, 2, 1]
    assert [item.parent_product_id for item in observations] == [
        "pimprod1",
        "pimprod2",
        "pimprod3",
    ]
    assert [item.product_name for item in observations] == [
        "Matte Product",
        "Glossy Product",
        "New Product",
    ]


def test_discover_listing_observations_defaults_ulta_to_best_sellers() -> None:
    base_url = "https://www.ulta.com/shop/makeup/lips/lipstick"
    best_sellers_url = f"{base_url}?sort=best_sellers"
    payloads = {
        best_sellers_url: """
            <html>
              <body>
                <li class="ProductListingResults__productCard">
                  <a href="/p/best-seller-pimprod1">Best Seller</a>
                </li>
              </body>
            </html>
        """,
    }
    fetcher = _FakeFetcher(payloads)

    observations = discover_listing_observations(
        [base_url],
        category_key="lipstick",
        max_pages=0,
        fetcher=fetcher,
        delay_seconds=0.0,
        retailer="ulta",
        sort_modes=None,
        parent_id_pattern=re.compile(r"(pimprod\d+)"),
    )

    assert fetcher.calls == [best_sellers_url]
    assert [item.sort_mode for item in observations] == ["best_sellers"]


def test_discover_listing_observations_supports_chewy_sort_and_next_links() -> None:
    base_url = "https://www.chewy.com/b/wet-food-389"
    newest_url = f"{base_url}?sort=newest"
    best_selling_url = f"{base_url}?sort=bestselling"
    page_two_url = "https://www.chewy.com/b/wet-food_c389_p2?sort=newest"
    payloads = {
        newest_url: """
            <html>
              <body>
                <a href="/fancy-feast-gravy-lovers/dp/103856">Slide 1 of 8</a>
                <a href="/fancy-feast-gravy-lovers/dp/103856">
                  Fancy Feast Gravy Lovers Variety Pack
                </a>
                <a href="/b/wet-food_c389_p2?sort=newest">Next</a>
              </body>
            </html>
        """,
        page_two_url: """
            <html>
              <body>
                <a href="/friskies-shreds/dp/104001">Friskies Shreds</a>
              </body>
            </html>
        """,
        best_selling_url: """
            <html>
              <body>
                <a href="/sheba-perfect-portions/dp/222333">Sheba Perfect Portions</a>
              </body>
            </html>
        """,
    }
    fetcher = _FakeFetcher(payloads)

    observations = discover_listing_observations(
        [base_url],
        category_key="wet_cat_food",
        max_pages=2,
        fetcher=fetcher,
        delay_seconds=0.0,
        retailer="chewy",
        sort_modes=("newest", "best_selling"),
        parent_id_pattern=re.compile(r"/dp/(\d+)"),
    )

    assert fetcher.calls == [newest_url, page_two_url, best_selling_url]
    assert [item.sort_mode for item in observations] == [
        "newest",
        "newest",
        "best_selling",
    ]
    assert [item.parent_product_id for item in observations] == [
        "103856",
        "104001",
        "222333",
    ]
    assert [item.product_name for item in observations] == [
        "Fancy Feast Gravy Lovers Variety Pack",
        "Friskies Shreds",
        "Sheba Perfect Portions",
    ]


def test_discover_listing_observations_extracts_ulta_new_badge() -> None:
    base_url = "https://www.ulta.com/shop/makeup/face/foundation"
    payloads = {
        f"{base_url}?sort=new_arrivals": """
            <html>
              <body>
                <li class="ProductListingResults__productCard">
                  <a href="/p/new-product-pimprod3">New Product</a>
                  <div class="pal-c-ProductCardHeader__tags">
                    <span class="pal-c-Tag__messageText">New</span>
                  </div>
                </li>
                <li class="ProductListingResults__productCard">
                  <a href="/p/old-product-pimprod4">Old Product</a>
                </li>
              </body>
            </html>
        """,
    }
    fetcher = _FakeFetcher(payloads)

    observations = discover_listing_observations(
        [base_url],
        category_key="foundation",
        max_pages=0,
        fetcher=fetcher,
        delay_seconds=0.0,
        retailer="ulta",
        sort_modes=("new_arrivals",),
        parent_id_pattern=re.compile(r"(pimprod\d+)"),
    )

    assert [item.product_name for item in observations] == [
        "New Product",
        "Old Product",
    ]
    assert [item.has_new_badge for item in observations] == [True, False]


def test_discover_listing_observations_keeps_ulta_extended_product_ids() -> None:
    base_url = "https://www.ulta.com/shop/makeup/face/face-primer"
    payloads = {
        f"{base_url}?sort=new_arrivals": """
            <html>
              <body>
                <li class="ProductListingResults__productCard">
                  <a href="/p/primer-one-mkt77006099">Primer One</a>
                  <div class="pal-c-ProductCardHeader__tags">
                    <span class="pal-c-Tag__messageText">New</span>
                  </div>
                </li>
                <li class="ProductListingResults__productCard">
                  <a href="/p/quickliner-lips-lip-liner-xlsImpprod19091101">Quickliner</a>
                </li>
                <li class="ProductListingResults__productCard">
                  <a href="/p/primer-two-pimprod2058192">Primer Two</a>
                </li>
              </body>
            </html>
        """,
    }
    fetcher = _FakeFetcher(payloads)

    observations = discover_listing_observations(
        [base_url],
        category_key="face_primer",
        max_pages=0,
        fetcher=fetcher,
        delay_seconds=0.0,
        retailer="ulta",
        sort_modes=("new_arrivals",),
        parent_id_pattern=re.compile(r"((?:pimprod|mkt|xlsImpprod)[0-9A-Za-z]+)"),
    )

    assert [item.parent_product_id for item in observations] == [
        "mkt77006099",
        "xlsImpprod19091101",
        "pimprod2058192",
    ]
    assert [item.has_new_badge for item in observations] == [True, False, False]


def test_discover_listing_observations_does_not_fallback_to_all_anchors_for_ulta() -> (
    None
):
    base_url = "https://www.ulta.com/shop/makeup/face/face-primer"
    payloads = {
        f"{base_url}?sort=new_arrivals": """
            <html>
              <body>
                <a href="/p/not-a-product-card-pimprod1">Loose link</a>
              </body>
            </html>
        """,
    }
    fetcher = _FakeFetcher(payloads)

    observations = discover_listing_observations(
        [base_url],
        category_key="face_primer",
        max_pages=0,
        fetcher=fetcher,
        delay_seconds=0.0,
        retailer="ulta",
        sort_modes=("new_arrivals",),
        parent_id_pattern=re.compile(r"((?:pimprod|mkt|xlsImpprod)[0-9A-Za-z]+)"),
    )

    assert observations == []
