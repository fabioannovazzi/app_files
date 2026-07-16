from __future__ import annotations

from modules.pdp.service import build_parser
from modules.pdp.tikicat_catalog import (
    TIKICAT_CATEGORY_KEY,
    tikicat_is_wet_cat_food_product,
    tikicat_parent_id_from_url,
    tikicat_semantic_attribute_hints,
    tikicat_term_values_for_product,
)
from modules.pdp.tikicat_filter_discovery import build_tikicat_filter_records


def _term_lookup() -> dict[int, dict[str, object]]:
    return {
        29: {
            "id": 29,
            "name": "Tiki Cat",
            "slug": "tiki-cat",
            "parent": 0,
            "link": "https://tikipets.com/product-category/tiki-cat/",
        },
        222: {
            "id": 222,
            "name": "Wet Food",
            "slug": "tiki-cat-wet-food",
            "parent": 29,
            "link": "https://tikipets.com/product-category/tiki-cat/tiki-cat-wet-food/",
        },
        233: {
            "id": 233,
            "name": "Minced",
            "slug": "shredded-cat",
            "parent": 222,
            "link": "https://tikipets.com/product-category/tiki-cat/tiki-cat-wet-food/shredded-cat/",
        },
        79: {
            "id": 79,
            "name": "Luau",
            "slug": "luau",
            "parent": 233,
            "link": "https://tikipets.com/product-category/tiki-cat/tiki-cat-wet-food/shredded-cat/luau/",
        },
    }


def _wp_product() -> dict[str, object]:
    return {
        "id": 123,
        "link": "https://tikipets.com/product/tiki-cat/tiki-cat-wet-food/shredded-cat/luau/ahi-tuna-chicken/",
        "title": {"rendered": "Ahi Tuna & Chicken"},
        "excerpt": {
            "rendered": (
                "<p>Tender ahi tuna and shredded chicken.</p>"
                "<ul><li>High-protein nutrition</li><li>Grain free</li></ul>"
            )
        },
        "product_cat": [79, 29],
    }


def test_tikicat_catalog_derives_wet_cat_food_terms_and_hints() -> None:
    product = _wp_product()
    terms = _term_lookup()

    values = tikicat_term_values_for_product(product, term_lookup=terms)
    hints = tikicat_semantic_attribute_hints(product, term_lookup=terms)

    assert tikicat_parent_id_from_url(str(product["link"])) == "ahi-tuna-chicken"
    assert tikicat_is_wet_cat_food_product(product, term_lookup=terms)
    assert values["texture"] == "Minced"
    assert values["product_lines"] == ["Luau"]
    assert hints["food_texture"] == ["Minced"]
    assert "Tuna" in hints["animal_protein_source"]
    assert "Chicken" in hints["animal_protein_source"]
    assert "Grain-Free" in hints["special_diet"]


def test_tikicat_filter_records_use_product_site_filters() -> None:
    product = _wp_product()
    terms = _term_lookup()
    hints = tikicat_semantic_attribute_hints(product, term_lookup=terms)
    parent_rows = [
        {
            "parent_product_id": "ahi-tuna-chicken",
            "pdp_url": product["link"],
            "category_key": TIKICAT_CATEGORY_KEY,
            "extras": {
                "site_filters": [
                    {
                        "filter_family": "food_texture",
                        "filter_value": "Minced",
                        "filter_label": "Minced",
                        "filter_url": "https://tikipets.com/product-category/tiki-cat/tiki-cat-wet-food/shredded-cat/",
                    },
                    {
                        "filter_family": "lifestage",
                        "filter_value": hints["lifestage"][0],
                        "filter_label": hints["lifestage"][0],
                        "filter_url": "https://tikipets.com/product-category/tiki-cat/tiki-cat-wet-food/?lifestage=Adult",
                    },
                ]
            },
        }
    ]

    surfaces, observations = build_tikicat_filter_records(parent_rows)

    assert [surface.filter_family for surface in surfaces] == [
        "food_texture",
        "lifestage",
    ]
    assert len(observations) == 2
    assert observations[0].parent_product_id == "ahi-tuna-chicken"


def test_tikicat_adapter_parses_visible_pdp_fields() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://tikipets.com/product/tiki-cat/tiki-cat-wet-food/shredded-cat/luau/ahi-tuna-chicken/" />
        <meta property="og:image" content="https://tikipets.com/image.png" />
      </head>
      <body>
        <main>
          <h6>Tiki Cat Hookena Luau</h6>
          <h1>Ahi Tuna & Chicken</h1>
          <p>Available in: 2.8 oz. can | 6 oz. can</p>
          <p>Tender, flaked ahi tuna and shredded chicken.</p>
          <ul>
            <li>Grain & Potato Free</li>
            <li>High-protein complete meal</li>
          </ul>
          <h3>Nutritional Facts</h3>
        </main>
      </body>
    </html>
    """
    parser = build_parser("tikicat_wet_cat_food", fetcher=None)

    result = parser.parse_url(
        "https://tikipets.com/product/tiki-cat/tiki-cat-wet-food/shredded-cat/luau/ahi-tuna-chicken/",
        html=html,
    )

    assert result.errors == ()
    assert result.parent is not None
    assert result.parent.parent_product_id == "ahi-tuna-chicken"
    assert result.parent.brand_raw == "Tiki Cat"
    assert result.parent.extras["category_key"] == TIKICAT_CATEGORY_KEY
    assert result.parent.extras["texture"] == "Minced"
    assert len(result.variants) == 2
    assert result.variants[0].size_text_raw == "2.8 oz. can"
