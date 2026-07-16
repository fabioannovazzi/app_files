from __future__ import annotations

from modules.pdp.purina_catalog import (
    PURINA_CATEGORY_KEY,
    purina_brand_from_product,
    purina_parent_id_from_url,
    purina_semantic_attribute_hints,
    purina_synthetic_product_html,
    purina_variant_payloads,
)
from modules.pdp.purina_filter_discovery import (
    build_purina_filter_records,
    purina_api_filters_from_search_payload,
)
from modules.pdp.service import build_parser


def _api_product() -> dict[str, object]:
    return {
        "title": "Purina Pro Plan Adult Chicken Entree in Gravy Wet Cat Food",
        "url": "/cats/shop/pro-plan-adult-chicken-gravy-wet-cat-food",
        "upc": "038100000001",
        "product_image": "/sites/default/files/products/pro-plan-chicken.png.webp",
        "description": (
            "<p>High protein wet cat food with real chicken in gravy for adult cats.</p>"
        ),
        "product_variations": [
            {
                "item_description": "ounce(s)",
                "item_quantity": "1",
                "item_size": "3.00",
                "short_description": None,
                "upc_code": "038100000001",
            }
        ],
        "type": "product",
    }


def _search_payload() -> dict[str, object]:
    return {
        "facets_metadata": {
            "products_brand": {
                "label": "Brand",
                "field_id": "field_brand",
                "url_alias": "brand",
            },
            "products_food_form": {
                "label": "Food Form",
                "field_id": "field_food_form",
                "url_alias": "food_form",
            },
            "products_special_diet": {
                "label": "Special Formula",
                "field_id": "field_special_formula",
                "url_alias": "special_diet",
            },
        },
        "facets": [
            [
                {
                    "field_brand": [
                        {
                            "url": "https://live.purina.com/api/search/products?f%5B0%5D=brand%3A1283",
                            "raw_value": "1283",
                            "values": {"value": "Purina Pro Plan", "count": 89},
                        }
                    ]
                }
            ],
            [
                {
                    "field_food_form": [
                        {
                            "url": "https://live.purina.com/api/search/products?f%5B0%5D=food_form%3A923",
                            "raw_value": "923",
                            "values": {"value": "Paté", "count": 100},
                        }
                    ]
                }
            ],
            [
                {
                    "field_special_formula": [
                        {
                            "url": "https://live.purina.com/api/search/products?f%5B0%5D=special_diet%3A1520",
                            "raw_value": "1520",
                            "values": {"value": "Grain Free", "count": 24},
                        }
                    ]
                }
            ],
        ],
    }


def test_purina_catalog_derives_parent_brand_and_hints() -> None:
    product = _api_product()
    site_filters = [
        {
            "filter_family": "brand",
            "filter_value": "Purina Pro Plan",
            "filter_label": "Purina Pro Plan",
            "filter_url": "https://live.purina.com/api/search/products?f%5B0%5D=brand%3A1283",
        },
        {
            "filter_family": "food_texture",
            "filter_value": "In Gravy",
            "filter_label": "In Gravy",
            "filter_url": "https://live.purina.com/api/search/products?f%5B0%5D=food_form%3A918",
        },
    ]
    enriched = {**product, "site_filters": site_filters}

    hints = purina_semantic_attribute_hints(enriched, site_filters=site_filters)
    variants = purina_variant_payloads(product)

    assert (
        purina_parent_id_from_url(str(product["url"]))
        == "pro-plan-adult-chicken-gravy-wet-cat-food"
    )
    assert purina_brand_from_product(enriched) == "Purina Pro Plan"
    assert hints["brand"] == ["Purina Pro Plan"]
    assert hints["food_texture"] == ["In Gravy"]
    assert "Chicken" in hints["animal_protein_source"]
    assert variants[0]["size"] == "3 oz"


def test_purina_api_filters_normalize_official_facets() -> None:
    filters = purina_api_filters_from_search_payload(_search_payload())

    assert [item["filter_family"] for item in filters] == [
        "brand",
        "food_texture",
        "special_diet",
    ]
    assert filters[1]["filter_value"] == "Pate"
    assert filters[2]["filter_value"] == "Grain-Free"


def test_purina_filter_records_use_product_site_filters() -> None:
    product = _api_product()
    parent_rows = [
        {
            "parent_product_id": "pro-plan-adult-chicken-gravy-wet-cat-food",
            "pdp_url": product["url"],
            "category_key": PURINA_CATEGORY_KEY,
            "extras": {
                "site_filters": [
                    {
                        "filter_family": "brand",
                        "filter_value": "Purina Pro Plan",
                        "filter_label": "Purina Pro Plan",
                        "filter_url": "https://live.purina.com/api/search/products?f%5B0%5D=brand%3A1283",
                    },
                    {
                        "filter_family": "special_diet",
                        "filter_value": "High Protein",
                        "filter_label": "High Protein",
                        "filter_url": "https://live.purina.com/api/search/products?f%5B0%5D=special_diet%3A1509",
                    },
                ]
            },
        }
    ]

    surfaces, observations = build_purina_filter_records(parent_rows)

    assert [surface.filter_family for surface in surfaces] == ["brand", "special_diet"]
    assert surfaces[1].filter_value == "High-Protein"
    assert len(observations) == 2
    assert (
        observations[0].parent_product_id == "pro-plan-adult-chicken-gravy-wet-cat-food"
    )


def test_purina_adapter_parses_api_product_payload() -> None:
    product = _api_product()
    product["site_filters"] = [
        {
            "filter_family": "brand",
            "filter_value": "Purina Pro Plan",
            "filter_label": "Purina Pro Plan",
            "filter_url": "https://live.purina.com/api/search/products?f%5B0%5D=brand%3A1283",
        }
    ]
    product["site_attributes"] = purina_semantic_attribute_hints(
        product,
        site_filters=product["site_filters"],  # type: ignore[arg-type]
    )
    html = purina_synthetic_product_html(product)
    parser = build_parser("purina_wet_cat_food", fetcher=None)

    result = parser.parse_url(
        "https://www.purina.com/cats/shop/pro-plan-adult-chicken-gravy-wet-cat-food",
        html=html,
    )

    assert result.errors == ()
    assert result.parent is not None
    assert (
        result.parent.parent_product_id == "pro-plan-adult-chicken-gravy-wet-cat-food"
    )
    assert result.parent.brand_raw == "Purina Pro Plan"
    assert result.parent.extras["category_key"] == PURINA_CATEGORY_KEY
    assert len(result.variants) == 1
    assert result.variants[0].size_text_raw == "3 oz"
