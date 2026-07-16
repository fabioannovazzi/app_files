from __future__ import annotations

from modules.pdp.saksfifthavenue_filter_discovery import (
    extract_saksfifthavenue_filter_surfaces,
)


def test_extract_saksfifthavenue_filter_surfaces_keeps_color_and_material_paths() -> (
    None
):
    category_url = "https://www.saksfifthavenue.com/c/shoes/shoes/sneakers/low-tops"
    html = """
        <html>
          <body>
            <h2>Color</h2>
            <a href="/c/shoes/shoes/sneakers/low-tops/red">Red (14)</a>
            <a href="/c/shoes/shoes/sneakers/low-tops/red">Red (14)</a>
            <a href="/product/miu-miu-tyre-low-top-sneakers-0400022953591.html">
              Miu Miu Tyre Low-Top Sneakers
            </a>
            <h2>Designer</h2>
            <a href="/c/shoes/shoes/sneakers/low-tops/miu-miu">Miu Miu</a>
            <h2>Material</h2>
            <a href="/c/shoes/shoes/sneakers/low-tops/canvas">
              Refine by Material: Canvas
            </a>
          </body>
        </html>
    """

    surfaces = extract_saksfifthavenue_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key="low_top_sneakers",
    )

    assert [
        (item.filter_family, item.filter_value, item.filter_url) for item in surfaces
    ] == [
        (
            "color",
            "Red",
            "https://www.saksfifthavenue.com/c/shoes/shoes/sneakers/low-tops/red",
        ),
        (
            "material",
            "Canvas",
            "https://www.saksfifthavenue.com/c/shoes/shoes/sneakers/low-tops/canvas",
        ),
    ]


def test_extract_saksfifthavenue_filter_surfaces_supports_query_filters_and_family_allowlist() -> (
    None
):
    category_url = "https://www.saksfifthavenue.com/c/shoes/shoes/sneakers/low-tops"
    html = """
        <html>
          <body>
            <a href="/c/shoes/shoes/sneakers/low-tops?prefn1=color&prefv1=Pink">
              Pink
            </a>
            <a href="/c/shoes/shoes/sneakers/low-tops?prefn1=material&prefv1=Leather">
              Leather
            </a>
          </body>
        </html>
    """

    surfaces = extract_saksfifthavenue_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key="low_top_sneakers",
        allowed_families=("material",),
    )

    assert [(item.filter_family, item.filter_value) for item in surfaces] == [
        ("material", "Leather")
    ]


def test_extract_saksfifthavenue_filter_surfaces_supports_apparel_refine_text() -> None:
    category_url = (
        "https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere"
    )
    html = """
        <html>
          <body>
            <h2>Style</h2>
            <button>Graphic &amp; Logo (27) Refine by Style: Graphic &amp; Logo</button>
            <a href="/c/women-s-apparel/sweaters/cashmere/oversized">
              Oversized (144)
            </a>
            <h2>Sleeve Length</h2>
            <button>Long Sleeve (427) Refine by Sleeve Length: Long Sleeve</button>
            <h2>Lifestyle</h2>
            <button>
              Premier Designer (333) Refine by Lifestyle: Premier Designer
            </button>
          </body>
        </html>
    """

    surfaces = extract_saksfifthavenue_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key="cashmere_sweaters",
        allowed_families=("style", "sleeve length", "lifestyle"),
    )

    assert [
        (item.filter_family, item.filter_value, item.filter_url) for item in surfaces
    ] == [
        (
            "lifestyle",
            "Premier Designer",
            "https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere?prefn1=refLifestyle&prefv1=Premier+Designer",
        ),
        (
            "sleeve length",
            "Long Sleeve",
            "https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere?prefn1=refSleeveLength&prefv1=Long+Sleeve",
        ),
        (
            "style",
            "Graphic & Logo",
            "https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere?prefn1=style&prefv1=Graphic+%26+Logo",
        ),
        (
            "style",
            "Oversized",
            "https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere/oversized",
        ),
    ]


def test_extract_saksfifthavenue_filter_surfaces_supports_plain_apparel_buttons() -> (
    None
):
    category_url = (
        "https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere"
    )
    html = """
        <html>
          <body>
            <button>Sleeve Length</button>
            <button>View More</button>
            <button>Short Sleeve (31)</button>
            <button>Sleeveless (12)</button>
            <button>New</button>
            <button>Sale</button>
            <button>Lifestyle</button>
            <button>Previous</button>
            <button>Premier Designer (333)</button>
            <button>Next</button>
            <button>Clear Filters</button>
            <button>Customer Care</button>
          </body>
        </html>
    """

    surfaces = extract_saksfifthavenue_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key="cashmere_sweaters",
        allowed_families=("sleeve length", "lifestyle"),
    )

    assert [
        (item.filter_family, item.filter_value, item.filter_url) for item in surfaces
    ] == [
        (
            "lifestyle",
            "Premier Designer",
            "https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere?prefn1=refLifestyle&prefv1=Premier+Designer",
        ),
        (
            "sleeve length",
            "Short Sleeve",
            "https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere?prefn1=refSleeveLength&prefv1=Short+Sleeve",
        ),
        (
            "sleeve length",
            "Sleeveless",
            "https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere?prefn1=refSleeveLength&prefv1=Sleeveless",
        ),
    ]


def test_extract_saksfifthavenue_filter_surfaces_adds_cashmere_sleeve_fallback() -> (
    None
):
    category_url = (
        "https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere"
    )
    html = """
        <html>
          <body>
            <h2>Color</h2>
            <a href="/c/women-s-apparel/sweaters/cashmere/black">Black</a>
          </body>
        </html>
    """

    surfaces = extract_saksfifthavenue_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key="cashmere_sweaters",
        allowed_families=("color", "sleeve length"),
    )

    assert [(item.filter_family, item.filter_value) for item in surfaces] == [
        ("color", "Black"),
        ("sleeve length", "Long Sleeve"),
        ("sleeve length", "Short Sleeve"),
        ("sleeve length", "Sleeveless"),
    ]
    assert surfaces[1].filter_url == (
        "https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere"
        "?prefn1=refSleeveLength&prefv1=Long+Sleeve"
    )


def test_extract_saksfifthavenue_filter_surfaces_supports_refinement_query_keys() -> (
    None
):
    category_url = (
        "https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere"
    )
    html = """
        <html>
          <body>
            <button title="Sleeve Length">Sleeve Length</button>
            <button
              data-href="/c/women-s-apparel/sweaters/cashmere?prefn1=refSleeveLength&prefv1=Short%20Sleeve"
            >
              Short Sleeve86
            </button>
            <button title="Lifestyle">Lifestyle</button>
            <button
              data-href="/c/women-s-apparel/sweaters/cashmere?prefn1=refLifestyle&prefv1=Premier%20Designer"
            >
              Premier Designer314
            </button>
            <button title="Runway &amp; Exclusives">Runway &amp; Exclusives</button>
            <button
              data-href="/c/women-s-apparel/sweaters/cashmere?prefn1=featuredType&prefv1=Runway"
            >
              Runway
            </button>
          </body>
        </html>
    """

    surfaces = extract_saksfifthavenue_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key="cashmere_sweaters",
        allowed_families=("sleeve length", "lifestyle"),
    )

    assert [
        (item.filter_family, item.filter_value, item.filter_url) for item in surfaces
    ] == [
        (
            "lifestyle",
            "Premier Designer",
            "https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere?prefn1=refLifestyle&prefv1=Premier+Designer",
        ),
        (
            "sleeve length",
            "Short Sleeve",
            "https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere?prefn1=refSleeveLength&prefv1=Short+Sleeve",
        ),
    ]
