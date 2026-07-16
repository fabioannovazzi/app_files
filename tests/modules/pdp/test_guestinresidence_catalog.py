from __future__ import annotations

from modules.pdp.guestinresidence_catalog import (
    guestinresidence_cashmere_scope_decision,
    guestinresidence_color_families,
    guestinresidence_parent_id_from_url,
    guestinresidence_semantic_attribute_hints,
)


def test_guestinresidence_scope_includes_cashmere_led_top() -> None:
    include, reason = guestinresidence_cashmere_scope_decision(
        {
            "title": "Compass Sweater Tee - Sorbet",
            "handle": "compass-sweater-tee-sorbet",
            "product_type": "PULLOVER",
            "tags": ["tops & sweaters", "womens"],
            "body_html": "<ul><li>CREW NECK</li><li>100% CASHMERE</li></ul>",
        }
    )

    assert include
    assert reason == "cashmere-led sweater/cardigan/top scope"


def test_guestinresidence_scope_excludes_cashmere_bottoms() -> None:
    include, reason = guestinresidence_cashmere_scope_decision(
        {
            "title": "Tailored Trouser - Charcoal",
            "handle": "tailored-trouser-charcoal",
            "product_type": "TROUSER",
            "tags": ["100% Cashmere"],
            "body_html": "<p>100% Cashmere</p>",
        }
    )

    assert not include
    assert reason == "excluded product type/title"


def test_guestinresidence_parent_id_from_collection_pdp_url() -> None:
    assert (
        guestinresidence_parent_id_from_url(
            "https://guestinresidence.com/collections/womens-sweaters/products/"
            "compass-sweater-tee-sorbet?variant=1"
        )
        == "compass-sweater-tee-sorbet"
    )


def test_guestinresidence_color_and_semantic_hints() -> None:
    product = {
        "title": "Collegiate Stripe Vest - Scarlet Combo",
        "product_type": "TOP",
        "body_html": (
            "<ul><li>LIGHT-WEIGHT SWEATER VEST</li>"
            "<li>V NECK</li><li>JERSEY STRIPE PATTERN</li>"
            "<li>100% CASHMERE</li></ul>"
        ),
    }

    assert guestinresidence_color_families("SCARLET COMBO") == (
        "Multicolor",
        "Red",
    )
    assert guestinresidence_semantic_attribute_hints(product) == {
        "garment_type": ["vest"],
        "neckline": ["v-neck"],
        "sleeve_length": ["sleeveless"],
        "knit_detail": ["jersey knit"],
        "style": ["striped"],
    }
