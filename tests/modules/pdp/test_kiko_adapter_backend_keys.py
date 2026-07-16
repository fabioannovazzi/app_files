from __future__ import annotations

from decimal import Decimal

from modules.pdp.adapters.kiko import KikoAdapter
from modules.pdp.models import ParentProduct, Variant


def test_kiko_adapter_sets_backend_ids_and_barcodes() -> None:
    adapter = KikoAdapter()
    adapter._page_props = {
        "root": {
            "product_id": "45123",
            "backend_id": "KC000001015",
            "custom_ids": [
                "KC000001015001B",
                "KC000001015002B",
                "KC000001015003B",
            ],
            "product_name": "Dreamphoria Heavenly Skin Blush",
        },
        "selected": {
            "product_class_lev1_desc": "MAKE-UP",
            "product_class_lev2_desc": "FACE MAKE-UP",
            "product_class_lev3_desc": "BLUSH",
        },
        "children": [
            {
                "product_id": "45115",
                "backend_id": "KC000001015001B",
                "barcodes": ["8059385030906"],
                "color": "01 Caramel Charm",
                "display_price": "24",
                "currency_id": "USD",
                "is_available": True,
                "product_media": {
                    "primary_image": {"url": "https://example.com/hero.webp"},
                    "media": [
                        {"name": "swatch", "url": "https://example.com/swatch.webp"}
                    ],
                },
            }
        ],
    }

    parent = ParentProduct(
        retailer="kiko",
        parent_product_id="45123",
        pdp_url="https://www.kikocosmetics.com/en-us/p/dreamphoria-heavenly-skin-blush-01-45115/",
        brand_raw="KIKO Milano",
        brand_normalized="KIKO Milano",
        title_raw="Dreamphoria Heavenly Skin Blush",
        title_normalized="Dreamphoria Heavenly Skin Blush",
        series_label_raw=None,
        category_path=(),
        has_color_selector=False,
    )
    variant = Variant(
        retailer="kiko",
        parent_product_id="45123",
        variant_id="45115",
        shade_name_raw=None,
        shade_name_normalized=None,
        size_text_raw=None,
        price_raw=None,
        price=Decimal("24"),
        currency=None,
        barcode=None,
        swatch_image_url=None,
        hero_image_url=None,
        availability=None,
    )

    adapter.retailer_specific_fixes(parent=parent, variants=[variant])

    assert parent.extras["backend_id"] == "KC000001015"
    assert parent.extras["custom_ids"] == [
        "KC000001015001B",
        "KC000001015002B",
        "KC000001015003B",
    ]
    assert variant.extras["backend_id"] == "KC000001015001B"
    assert variant.extras["backend_parent_id"] == "KC000001015"
    assert variant.barcode == "8059385030906"
    assert variant.price == Decimal("24")
    assert variant.currency == "USD"
