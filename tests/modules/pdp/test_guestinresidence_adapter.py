from __future__ import annotations

import json
from decimal import Decimal

from modules.pdp.adapters.guestinresidence import GuestInResidenceAdapter
from modules.pdp.engine import PDPParser
from modules.pdp.profile_loader import load_profile


def _product_html() -> str:
    product = {
        "id": 9828619387120,
        "title": "Compass Sweater Tee - Sorbet",
        "handle": "compass-sweater-tee-sorbet",
        "description": (
            "<ul><li>LIGHT-WEIGHT POPCORN STITCH TEE</li>"
            "<li>CREW NECK</li><li>RIB HEM, NECK, AND CUFF TRIM</li>"
            "<li>100% CASHMERE</li></ul>"
        ),
        "vendor": "Guest In Residence",
        "type": "PULLOVER",
        "tags": ["tops & sweaters", "womens"],
        "price": 24500,
        "available": True,
        "variants": [
            {
                "id": 48760100618480,
                "title": "SORBET / XS",
                "option1": "SORBET",
                "option2": "XS",
                "sku": "W40210PLSRBTXS",
                "available": True,
                "price": 24500,
                "barcode": "197053097085",
            },
            {
                "id": 48760100749552,
                "title": "SORBET / XL",
                "option1": "SORBET",
                "option2": "XL",
                "sku": "W40210PLSRBTXL",
                "available": False,
                "price": 24500,
                "barcode": "197053097047",
            },
        ],
        "images": [
            "//cdn.shopify.com/s/files/1/0641/5613/9760/files/COMPASSSWEATERTEE_SORBET.jpg"
        ],
        "featured_image": (
            "//cdn.shopify.com/s/files/1/0641/5613/9760/files/COMPASSSWEATERTEE_SORBET.jpg"
        ),
        "options": [
            {"name": "Color", "values": ["SORBET"]},
            {"name": "Size", "values": ["XS", "XL"]},
        ],
    }
    return f"""
    <html>
      <head>
        <link rel="canonical"
              href="https://guestinresidence.com/products/compass-sweater-tee-sorbet">
      </head>
      <body>
        <h1>Compass Sweater Tee - Sorbet</h1>
        <script>_BISConfig = {{}}; _BISConfig.product = {json.dumps(product)};</script>
      </body>
    </html>
    """


def test_guestinresidence_parser_builds_parent_and_size_variants() -> None:
    profile = load_profile("guestinresidence_cashmere_sweaters")
    parser = PDPParser(profile=profile, adapter=GuestInResidenceAdapter(), fetcher=None)

    result = parser.parse_url(
        "https://guestinresidence.com/products/compass-sweater-tee-sorbet",
        html=_product_html(),
    )

    assert result.errors == ()
    parent = result.parent
    assert parent is not None
    assert parent.parent_product_id == "compass-sweater-tee-sorbet"
    assert parent.brand_normalized == "Guest in Residence"
    assert parent.category_path == ("Women", "Clothing", "Cashmere Sweaters")
    assert parent.extras["category_key"] == "cashmere_sweaters"
    assert parent.extras["scope_included"] is True
    assert parent.extras["site_filters"]
    assert "garment_type: top" in parent.extras["features"]

    variants = {variant.variant_id: variant for variant in result.variants}
    assert set(variants) == {"48760100618480", "48760100749552"}
    assert variants["48760100618480"].shade_name_raw == "SORBET"
    assert variants["48760100618480"].size_text_raw == "XS"
    assert variants["48760100618480"].price == Decimal("245.00")
    assert variants["48760100618480"].availability == "in_stock"
    assert variants["48760100749552"].availability == "out_of_stock"
