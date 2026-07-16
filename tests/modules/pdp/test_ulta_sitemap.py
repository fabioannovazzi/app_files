from __future__ import annotations

from modules.pdp.ulta_sitemap import crawl_ulta_sitemap_observations


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


def test_crawl_ulta_sitemap_observations_reads_product_sitemap_index() -> None:
    payloads = {
        "https://www.ulta.com/sitemap/p.xml": """
            <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <sitemap><loc>https://www.ulta.com/sitemap/p-0.xml</loc></sitemap>
              <sitemap><loc>https://www.ulta.com/sitemap/p-1.xml</loc></sitemap>
            </sitemapindex>
        """,
        "https://www.ulta.com/sitemap/p-0.xml": """
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url>
                <loc>https://www.ulta.com/p/test-one-pimprod1?sku=1</loc>
                <lastmod>2026-04-01</lastmod>
              </url>
              <url>
                <loc>https://www.ulta.com/p/test-two-pimprod2</loc>
              </url>
            </urlset>
        """,
    }
    fetcher = _FakeFetcher(payloads)

    observations = crawl_ulta_sitemap_observations(
        fetcher=fetcher,  # type: ignore[arg-type]
        sources=("product",),
        max_product_sitemaps=1,
    )

    assert [
        (item.sitemap_source, item.url, item.lastmod, item.url_type)
        for item in observations
    ] == [
        (
            "https://www.ulta.com/sitemap/p-0.xml",
            "https://www.ulta.com/p/test-one-pimprod1",
            "2026-04-01",
            "product",
        ),
        (
            "https://www.ulta.com/sitemap/p-0.xml",
            "https://www.ulta.com/p/test-two-pimprod2",
            None,
            "product",
        ),
    ]


def test_crawl_ulta_sitemap_observations_reads_direct_urlset_sources() -> None:
    payloads = {
        "https://www.ulta.com/l/category_filter_sitemap.xml": """
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url>
                <loc>https://www.ulta.com/shop/makeup/lips/lipstick?finish=matte</loc>
                <lastmod>2026-04-01</lastmod>
              </url>
            </urlset>
        """
    }
    fetcher = _FakeFetcher(payloads)

    observations = crawl_ulta_sitemap_observations(
        fetcher=fetcher,  # type: ignore[arg-type]
        sources=("category_filter",),
    )

    assert [
        (item.sitemap_source, item.url, item.url_type) for item in observations
    ] == [
        (
            "https://www.ulta.com/l/category_filter_sitemap.xml",
            "https://www.ulta.com/shop/makeup/lips/lipstick?finish=matte",
            "category_filter",
        )
    ]
