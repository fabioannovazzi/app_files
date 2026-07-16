from __future__ import annotations

from modules.pdp.cosmoprofbeauty_filter_discovery import (
    extract_cosmoprofbeauty_filter_surfaces,
)


def test_extract_cosmoprofbeauty_filter_surfaces_keeps_same_path_unique_filters() -> None:
    category_url = "https://www.cosmoprofbeauty.com/hair-color/permanent"
    html = """
        <html>
          <body>
            <a href="/hair-color/permanent?issearchresultfilter=true&prefn1=benefit&prefv1=Grey+Coverage&start=0&sz=24">
              Grey Coverage 12
            </a>
            <a href="/hair-color/permanent?issearchresultfilter=true&prefn1=benefit&prefv1=Grey+Coverage&start=0&sz=24">
              Grey Coverage 12
            </a>
            <a href="/hair-color/permanent?prefn1=type&prefv1=Permanent+Hair+Color">
              Permanent Hair Color
            </a>
            <a href="/customer-appreciation-sale?prefn1=brandcustom&prefv1=Wella">
              Wella
            </a>
          </body>
        </html>
    """

    surfaces = extract_cosmoprofbeauty_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key="permanent",
    )

    assert [
        (item.filter_family, item.filter_value, item.filter_url)
        for item in surfaces
    ] == [
        (
            "benefit",
            "Grey Coverage",
            "https://www.cosmoprofbeauty.com/hair-color/permanent"
            "?issearchresultfilter=true&prefn1=benefit&prefv1=Grey+Coverage",
        ),
        (
            "type",
            "Permanent Hair Color",
            "https://www.cosmoprofbeauty.com/hair-color/permanent"
            "?prefn1=type&prefv1=Permanent+Hair+Color",
        ),
    ]


def test_extract_cosmoprofbeauty_filter_surfaces_uses_last_pref_pair_and_family_filter() -> None:
    category_url = "https://www.cosmoprofbeauty.com/hair-color/permanent"
    html = """
        <html>
          <body>
            <a href="/hair-color/permanent?prefn1=type&prefv1=Permanent+Hair+Color&prefn2=benefit&prefv2=Grey+Coverage">
              Grey Coverage
            </a>
            <a href="/hair-color/permanent?prefn1=brandcustom&prefv1=Wella">
              Wella Professionals
            </a>
          </body>
        </html>
    """

    benefit_surfaces = extract_cosmoprofbeauty_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key="permanent",
        allowed_families=("benefit",),
    )
    brand_surfaces = extract_cosmoprofbeauty_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key="permanent",
        allowed_families=("brand",),
    )

    assert [(item.filter_family, item.filter_value) for item in benefit_surfaces] == [
        ("benefit", "Grey Coverage")
    ]
    assert [(item.filter_family, item.filter_value) for item in brand_surfaces] == [
        ("brand", "Wella")
    ]
