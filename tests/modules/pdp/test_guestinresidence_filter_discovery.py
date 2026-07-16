from __future__ import annotations

from modules.pdp.guestinresidence_filter_discovery import (
    build_guestinresidence_filter_records,
    extract_guestinresidence_filter_surfaces,
    guestinresidence_site_filters_for_product,
)


def test_extract_guestinresidence_filter_surfaces_from_collection_html() -> None:
    html = """
    <form class="filter-group-display__form">
      <label><input name="filter.v.t.shopify.color-pattern"
                    value="gid://shopify/TaxonomyValue/1">Black</label>
      <label><input name="filter.v.option.size" value="XS">XS</label>
      <label><input name="filter.v.availability" value="1">In Stock Only</label>
    </form>
    """

    surfaces = extract_guestinresidence_filter_surfaces(
        category_url="https://guestinresidence.com/collections/womens-sweaters",
        html=html,
    )

    assert {(item.filter_family, item.filter_value) for item in surfaces} == {
        ("availability", "in_stock"),
        ("color_family", "Black"),
        ("size", "XS"),
    }


def test_guestinresidence_site_filters_for_product_maps_options() -> None:
    product = {
        "options": [
            {"name": "Color", "values": ["SCARLET COMBO"]},
            {"name": "Size", "values": ["XS", "S"]},
        ],
        "variants": [
            {"option1": "SCARLET COMBO", "option2": "XS", "available": False},
            {"option1": "SCARLET COMBO", "option2": "S", "available": True},
        ],
    }

    filters = guestinresidence_site_filters_for_product(product)

    assert {(item["filter_family"], item["filter_value"]) for item in filters} == {
        ("availability", "in_stock"),
        ("color_family", "Multicolor"),
        ("color_family", "Red"),
        ("size", "S"),
        ("size", "XS"),
    }


def test_build_guestinresidence_filter_records_from_parent_extras() -> None:
    surfaces, observations = build_guestinresidence_filter_records(
        [
            {
                "parent_product_id": "compass-sweater-tee-sorbet",
                "pdp_url": "https://guestinresidence.com/products/compass-sweater-tee-sorbet",
                "category_key": "cashmere_sweaters",
                "extras": {
                    "site_filters": [
                        {
                            "filter_family": "color_family",
                            "filter_value": "Orange",
                            "filter_label": "Orange",
                            "filter_url": "https://guestinresidence.com/collections/womens-sweaters?filter.v.t.shopify.color-pattern=Orange",
                        }
                    ]
                },
            }
        ]
    )

    assert [(item.filter_family, item.filter_value) for item in surfaces] == [
        ("color_family", "Orange")
    ]
    assert [
        (item.parent_product_id, item.filter_family, item.filter_value)
        for item in observations
    ] == [("compass-sweater-tee-sorbet", "color_family", "Orange")]
