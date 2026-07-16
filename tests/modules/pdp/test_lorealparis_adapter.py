from __future__ import annotations

import json
from decimal import Decimal

from modules.pdp.adapters.lorealparis import LorealParisAdapter
from modules.pdp.engine import PDPParser
from modules.pdp.profile_loader import load_profile


def _product_html() -> str:
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Infallible Up to 24H Fresh Wear Soft Matte Bronzer",
        "description": "A lightweight soft matte bronzer.",
        "image": "https://example.com/bronzer.webp",
        "offers": {
            "@type": "Offer",
            "price": "15.99",
            "priceCurrency": "USD",
            "availability": "https://schema.org/InStock",
        },
    }
    family = "infallible-up-to-24h-fresh-wear-soft-matte-bronzer"
    return f"""
    <html>
      <head>
        <link rel="canonical"
              href="https://www.lorealparisusa.com/makeup/face/bronzer/{family}-deep-tan">
        <script type="application/ld+json">{json.dumps(product)}</script>
      </head>
      <body>
        <h1>Infallible Up to 24H Fresh Wear Soft Matte Bronzer</h1>
        <section>
          <h2>PRODUCT DETAILS</h2>
          <p>A waterproof, sweatproof, transfer-proof bronzer.</p>
          <p>Comes in lightweight shades for a variety of skin tones.</p>
          <h2>INGREDIENTS</h2>
        </section>
        <a href="/makeup/face/bronzer/{family}-medium" aria-label="Medium {family}">
          Medium {family}
        </a>
        <a href="/makeup/face/bronzer/{family}-deep-tan" aria-label="Deep Tan {family}">
          Deep Tan {family}
        </a>
        <a href="/makeup/face?texture=powder">Powder</a>
        <a href="/makeup/face?look=matte">Matte</a>
        <a href="/makeup/face?topic=water-resistant">Water Resistant</a>
        <a href="/makeup/face?topic=buildable">Buildable</a>
      </body>
    </html>
    """


def test_lorealparis_parser_builds_family_parent_and_variants() -> None:
    profile = load_profile("lorealparis_bronzer")
    parser = PDPParser(profile=profile, adapter=LorealParisAdapter(), fetcher=None)

    result = parser.parse_url(
        "https://www.lorealparisusa.com/makeup/face/bronzer/"
        "infallible-up-to-24h-fresh-wear-soft-matte-bronzer-medium",
        html=_product_html(),
    )

    assert result.errors == ()
    parent = result.parent
    assert parent is not None
    assert (
        parent.parent_product_id == "infallible-up-to-24h-fresh-wear-soft-matte-bronzer"
    )
    assert parent.pdp_url.endswith(
        "/makeup/face/bronzer/infallible-up-to-24h-fresh-wear-soft-matte-bronzer"
    )
    assert parent.brand_normalized == "L'Oreal Paris"
    assert parent.category_path == ("Makeup", "Face Makeup", "Bronzer")
    assert parent.extras["category_key"] == "bronzer"
    assert any(tag["label"] == "Water Resistant" for tag in parent.extras["site_tags"])

    variants = {variant.variant_id: variant for variant in result.variants}
    assert set(variants) == {
        "infallible-up-to-24h-fresh-wear-soft-matte-bronzer-deep-tan",
        "infallible-up-to-24h-fresh-wear-soft-matte-bronzer-medium",
    }
    assert (
        variants[
            "infallible-up-to-24h-fresh-wear-soft-matte-bronzer-medium"
        ].shade_name_raw
        == "Medium"
    )
    assert variants[
        "infallible-up-to-24h-fresh-wear-soft-matte-bronzer-medium"
    ].price == Decimal("15.99")
    assert (
        variants[
            "infallible-up-to-24h-fresh-wear-soft-matte-bronzer-medium"
        ].availability
        == "in_stock"
    )
