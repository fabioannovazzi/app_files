from __future__ import annotations

import json
from decimal import Decimal

from modules.pdp.adapters.kiko import KikoAdapter
from modules.pdp.engine import PDPParser
from modules.pdp.profile_loader import load_profile


def _next_data_html(page_props: dict[str, object]) -> str:
    payload = {"props": {"pageProps": page_props}}
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(payload)}"
        "</script></body></html>"
    )


def test_kiko_lipstick_parser() -> None:
    profile = load_profile("kiko_lipstick")
    parser = PDPParser(profile=profile, adapter=KikoAdapter(), fetcher=None)
    html = _next_data_html(
        {
            "root": {
                "product_id": "11120",
                "product_name": "3D Hydra Lipgloss",
                "primitive_name": "3D Hydra",
            },
            "selected": {
                "product_id": "11147",
                "product_class_lev1_desc": "MAKE-UP",
                "product_class_lev2_desc": "LIPS MAKE-UP",
                "product_class_lev3_desc": "LIP GLOSSES",
            },
            "children": [
                {
                    "product_id": "11147",
                    "slug": "3d-hydra-lipgloss-17",
                    "color": "17 Pearly Mauve",
                    "display_price": "14",
                    "currency_id": "USD",
                    "is_available": True,
                    "product_media": {
                        "primary_image": {
                            "url": "https://example.com/lipgloss-hero.webp"
                        },
                        "media": [
                            {
                                "name": "swatch",
                                "url": "https://example.com/lipgloss-swatch.webp",
                            }
                        ],
                    },
                },
                {
                    "product_id": "11148",
                    "slug": "3d-hydra-lipgloss-18",
                    "color": "18 Red",
                    "display_price": "14",
                    "currency_id": "USD",
                    "is_available": True,
                },
            ],
        }
    )

    result = parser.parse_url(
        "https://www.kikocosmetics.com/en-us/p/3d-hydra-lipgloss-17-11147/",
        html=html,
    )

    parent = result.parent
    assert parent is not None
    assert parent.parent_product_id == "11120"
    assert parent.brand_normalized == "KIKO Milano"
    assert parent.title_raw == "3D Hydra Lipgloss"
    assert parent.has_color_selector is True
    assert parent.category_path[:2] == ("MAKE-UP", "LIPS MAKE-UP")

    variants = {variant.variant_id: variant for variant in result.variants}
    assert variants
    assert "11147" in variants

    selected = variants["11147"]
    assert selected.shade_name_raw == "17 Pearly Mauve"
    assert selected.price == Decimal("14")
    assert selected.currency == "USD"
    assert selected.hero_image_url
    assert selected.swatch_image_url


def test_kiko_parser_handles_selected_single_sku_product() -> None:
    profile = load_profile("kiko_moisturizer")
    parser = PDPParser(profile=profile, adapter=KikoAdapter(), fetcher=None)
    payload = {
        "root": {
            "product_id": "45110",
            "backend_id": "KC000004510",
            "product_name": "Kind by Kiko Sorbet Hydra Face Cream",
            "primitive_name": "Kind by Kiko",
            "short_description": "Hydrating face cream.",
        },
        "selected": {
            "product_id": "45110",
            "slug": "kind-by-kiko-sorbet-hydra-face-cream",
            "product_class_lev1_desc": "SKINCARE",
            "product_class_lev2_desc": "FACE",
            "product_class_lev3_desc": "MOISTURIZERS",
            "display_price": 26,
            "currency_id": "USD",
            "is_sellable": True,
            "product_media": {
                "primary_image": {"url": "https://example.com/face-cream.webp"},
                "media": [
                    {
                        "name": "primary",
                        "url": "https://example.com/face-cream.webp",
                    }
                ],
            },
        },
        "children": [],
    }
    html = _next_data_html(payload)

    result = parser.parse_url(
        "https://www.kikocosmetics.com/en-us/p/kind-by-kiko-sorbet-hydra-face-cream-45110/",
        html=html,
    )

    assert result.errors == ()
    parent = result.parent
    assert parent is not None
    assert parent.parent_product_id == "45110"
    assert parent.category_path == ("SKINCARE", "FACE", "MOISTURIZERS")

    assert len(result.variants) == 1
    variant = result.variants[0]
    assert variant.variant_id == "45110"
    assert variant.price == Decimal("26")
    assert variant.currency == "USD"
    assert variant.availability == "in_stock"
    assert variant.hero_image_url == "https://example.com/face-cream.webp"
