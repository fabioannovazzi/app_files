from __future__ import annotations

import json
from decimal import Decimal

from modules.pdp.adapters.vince import VinceAdapter
from modules.pdp.engine import PDPParser
from modules.pdp.profile_loader import load_profile


def _product_html() -> str:
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Oasis Contrast-Edge Suede Sneaker",
        "description": "Soft suede sneaker with contrasting trim.",
        "mpn": "J8129L2INDIGOFLAX",
        "sku": "J8129L2INDIGOFLAX",
        "productCategory": "Sneakers",
        "size": ["8", "10"],
        "color": "INDIGO/FLAX",
        "material": "100% Suede.",
        "image": ["https://cdn.example.com/oasis.webp"],
        "offers": {
            "@type": "Offer",
            "priceCurrency": "CHF",
            "price": "269.0",
            "availability": "http://schema.org/InStock",
        },
        "isVariantOf": {
            "@type": "ProductGroup",
            "name": "Oasis Contrast-Edge Suede Sneaker",
            "sku": "J8129L2",
        },
    }
    return f"""
    <html>
      <head>
        <link rel="canonical"
              href="https://www.vince.com/product/oasis-contrast-edge-suede-sneaker-J8129L2INDIGOFLAX.html">
        <meta property="product:price.amount" content="275.00">
        <meta property="product:price.currency" content="USD">
        <script type="application/ld+json">{json.dumps(product)}</script>
      </head>
      <body>
        <div class="container product-detail" data-pid="J8129L2INDIGOFLAX">
          <div class="product-badges">NEW</div>
          <h1 class="product-name">Oasis Contrast-Edge Suede Sneaker</h1>
          <span class="product-id">J8129L2INDIGOFLAX</span>
          <div class="color-selected-value">indigo/flax</div>
          <div class="attribute-container" data-attr="size">
            <span class="size-value selectable" data-attr-value="8">8</span>
            <span class="size-value unselectable" data-attr-value="9">9</span>
            <span class="size-value selectable" data-attr-value="10">10</span>
          </div>
          <div class="product-info-details">
            Soft suede sneaker with contrasting trim.
          </div>
          <div id="collapsible-product-details">
            <ul><li>Lace-up closure.</li><li>Rounded toe.</li></ul>
          </div>
          <div id="collapsible-product-fabric-care">
            <p>100% Suede.</p>
          </div>
        </div>
      </body>
    </html>
    """


def test_vince_parser_builds_color_parent_and_size_variants() -> None:
    profile = load_profile("vince_low_top_sneakers")
    parser = PDPParser(profile=profile, adapter=VinceAdapter(), fetcher=None)

    result = parser.parse_url(
        "https://www.vince.com/product/oasis-contrast-edge-suede-sneaker-J8129L2INDIGOFLAX.html",
        html=_product_html(),
    )

    assert result.errors == ()
    parent = result.parent
    assert parent is not None
    assert parent.parent_product_id == "J8129L2INDIGOFLAX"
    assert parent.brand_normalized == "Vince"
    assert parent.category_path == ("Women", "Shoes", "Sneakers")
    assert parent.extras["category_key"] == "low_top_sneakers"
    assert parent.extras["style_id"] == "J8129L2"
    assert parent.extras["is_new"] is True
    assert parent.extras["site_filters"]
    assert "material: suede" in parent.extras["features"]

    variants = {variant.variant_id: variant for variant in result.variants}
    assert set(variants) == {"J8129L2INDIGOFLAX-8", "J8129L2INDIGOFLAX-10"}
    assert variants["J8129L2INDIGOFLAX-8"].shade_name_raw == "INDIGO/FLAX"
    assert variants["J8129L2INDIGOFLAX-8"].size_text_raw == "8"
    assert variants["J8129L2INDIGOFLAX-8"].price == Decimal("275.00")
    assert variants["J8129L2INDIGOFLAX-8"].currency == "USD"
    assert variants["J8129L2INDIGOFLAX-8"].availability == "in_stock"


def test_vince_parser_preserves_requested_color_id_when_site_serves_default() -> None:
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Blair Gingham Sneaker",
        "description": "A gingham sneaker.",
        "mpn": "J9265F1PISTACHIOFLAX",
        "sku": "J9265F1PISTACHIOFLAX",
        "size": ["6"],
        "color": "PISTACHIO/FLAX",
        "image": "https://cdn.example.com/blair.webp",
        "offers": {"price": "235.00", "priceCurrency": "USD"},
    }
    html = f"""
    <html>
      <head>
        <link rel="canonical"
              href="https://www.vince.com/product/blair-gingham-sneaker-J9265F1PISTACHIOFLAX.html">
        <script type="application/ld+json">{json.dumps(product)}</script>
      </head>
      <body>
        <h1 class="product-name">Blair Gingham Sneaker</h1>
        <button class="color-swatch" title="PISTACHIO/FLAX"></button>
        <button class="color-swatch" title="DESERT SAND/FLAX"></button>
      </body>
    </html>
    """
    profile = load_profile("vince_low_top_sneakers")
    parser = PDPParser(profile=profile, adapter=VinceAdapter(), fetcher=None)

    result = parser.parse_url(
        "https://www.vince.com/product/blair-gingham-sneaker-J9265F1DESERTSANDFLAX.html",
        html=html,
    )

    assert result.errors == ()
    assert result.parent is not None
    assert result.parent.parent_product_id == "J9265F1DESERTSANDFLAX"
    assert result.parent.pdp_url.endswith(
        "/product/blair-gingham-sneaker-J9265F1DESERTSANDFLAX.html"
    )
    assert result.variants[0].shade_name_raw == "DESERT SAND/FLAX"
