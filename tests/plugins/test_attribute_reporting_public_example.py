from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import pytest

__all__: list[str] = []

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ROOT = (
    REPOSITORY_ROOT / "static" / "shared" / "attribute-reporting" / "cashmere"
)
EXAMPLE_PAGE = EXAMPLE_ROOT / "index.html"
EXPECTED_PRODUCT_IMAGES = (
    "assets/products/0400021837770.avif",
    "assets/products/0400022159374.avif",
    "assets/products/0400024692486.avif",
    "assets/products/0400025606068.avif",
)


class _ImageSourceParser(HTMLParser):
    """Collect local image sources from the published example page."""

    def __init__(self) -> None:
        super().__init__()
        self.sources: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        attributes = dict(attrs)
        source = attributes.get("src")
        if source:
            self.sources.add(source)


def test_cashmere_example_page_is_portable_public_html() -> None:
    page = EXAMPLE_PAGE.read_text(encoding="utf-8")
    parser = _ImageSourceParser()

    parser.feed(page)

    assert "<title>Saks Fifth Avenue cashmere sweaters</title>" in page
    assert (
        'data-report-id="saksfifthavenue--cashmere_sweaters--20260715T121611Z"' in page
    )
    assert (
        'data-source-report-sha256="239170ac5148e8a38c8217680e2fa44e2a0e39cbf60417bbb1f11df9e9ebec83"'
        in page
    )
    assert "Correct with caveats" in page
    assert "Clara · Retailer Signals · public example" in page
    assert "Published here as a curated example" in page
    assert "user reports remain local unless deliberately shared" not in page
    assert '<meta name="robots" content="noindex,nofollow">' in page
    assert "retailer pages remain the original source" in page
    assert parser.sources == set(EXPECTED_PRODUCT_IMAGES)
    assert "/private/tmp" not in page
    assert "/Users/" not in page
    assert "file://" not in page
    assert "private local report" not in page
    assert "This report is not stored on the server" not in page


@pytest.mark.parametrize("relative_path", EXPECTED_PRODUCT_IMAGES)
def test_cashmere_example_referenced_product_image_is_valid_avif(
    relative_path: str,
) -> None:
    image_path = EXAMPLE_ROOT / relative_path

    avif_signature = image_path.read_bytes()[:12]

    assert avif_signature[4:12] == b"ftypavif"
