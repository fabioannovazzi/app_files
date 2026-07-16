from __future__ import annotations

from modules.pdp.lorealparis_filter_discovery import (
    build_lorealparis_filter_records,
    extract_lorealparis_site_tags,
)


def _tag_html() -> str:
    return """
    <html>
      <body>
        <a href="/makeup/face?texture=powder">Powder</a>
        <a href="/makeup/face?look=matte">Matte</a>
        <a href="/makeup/face?color=pink">Pink</a>
        <a href="/makeup/face?skin-type=all-skin-types">All Skin Types</a>
        <a href="/makeup/face?topic=dermatologist-tested">Dermatologist Tested</a>
        <a href="/makeup/face?topic=water-resistant">Water Resistant</a>
        <a href="/skin-care/fragrance-free">Fragrance Free</a>
      </body>
    </html>
    """


def test_extract_lorealparis_site_tags_keeps_face_filter_links_only() -> None:
    tags = extract_lorealparis_site_tags(_tag_html())

    assert {(tag["query_key"], tag["query_value"]) for tag in tags} == {
        ("color", "pink"),
        ("look", "matte"),
        ("skin-type", "all-skin-types"),
        ("texture", "powder"),
        ("topic", "dermatologist-tested"),
        ("topic", "water-resistant"),
    }


def test_build_lorealparis_filter_records_maps_blush_tags_to_taxonomy() -> None:
    tags = extract_lorealparis_site_tags(_tag_html())
    surfaces, observations = build_lorealparis_filter_records(
        [
            {
                "parent_product_id": "infallible-fresh-wear-blush",
                "pdp_url": (
                    "https://www.lorealparisusa.com/makeup/face/blush/"
                    "infallible-fresh-wear-blush"
                ),
                "category_key": "blush",
                "extras": {"site_tags": tags},
            }
        ]
    )

    assert {(item.filter_family, item.filter_value) for item in surfaces} == {
        ("dermatology_claims", "dermatologist-tested"),
        ("finish", "matte"),
        ("form", "powder"),
        ("resistance_claims", "water resistant"),
        ("shade_family", "pink"),
    }
    assert {(item.filter_family, item.filter_value) for item in observations} == {
        ("dermatology_claims", "dermatologist-tested"),
        ("finish", "matte"),
        ("form", "powder"),
        ("resistance_claims", "water resistant"),
        ("shade_family", "pink"),
    }
    assert all(
        item.parent_product_id == "infallible-fresh-wear-blush" for item in observations
    )
