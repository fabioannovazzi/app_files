from __future__ import annotations

from modules.pdp.chewy_filter_discovery import (
    extract_chewy_filter_surfaces,
    normalize_chewy_filter_family,
)


def test_extract_chewy_filter_surfaces_keeps_requested_food_attributes() -> None:
    category_url = "https://www.chewy.com/b/wet-food-389"
    html = """
        <html>
          <body>
            <h2>Brand</h2>
            <a href="/b/9-lives-384">9 Lives</a>
            <h2>Lifestage</h2>
            <a href="/f/canned-adult-cat-food_c389_f5v9060">Adult</a>
            <h2>Food Texture</h2>
            <a href="/b/pate-cat-food-274">Pate (151)</a>
            <h2>Flavor</h2>
            <a href="/b/chicken-wet-cat-food-300">Chicken</a>
            <h2>Special Diet</h2>
            <a href="/b/chicken-free-wet-cat-food-142398">Chicken-Free</a>
            <h2>Health Feature</h2>
            <a href="/f/sensitive-digestion-wet-cat-food_c389_f102v110">
              Sensitive Digestion
            </a>
            <h2>Package Count</h2>
            <a href="/f/7-12-count-wet-cat-food_c389_f113v456">7-12 count</a>
            <h2>Price</h2>
            <a href="/f/wet-cat-food-under-10_c389_f99v10">Less than $10</a>
          </body>
        </html>
    """

    surfaces = extract_chewy_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key="wet_cat_food",
    )

    assert [
        (item.filter_family, item.filter_value, item.filter_url) for item in surfaces
    ] == [
        (
            "flavor",
            "Chicken",
            "https://www.chewy.com/b/chicken-wet-cat-food-300",
        ),
        (
            "food texture",
            "Pate",
            "https://www.chewy.com/b/pate-cat-food-274",
        ),
        (
            "health feature",
            "Sensitive Digestion",
            "https://www.chewy.com/f/sensitive-digestion-wet-cat-food_c389_f102v110",
        ),
        (
            "lifestage",
            "Adult",
            "https://www.chewy.com/f/canned-adult-cat-food_c389_f5v9060",
        ),
        (
            "package count",
            "7-12 count",
            "https://www.chewy.com/f/7-12-count-wet-cat-food_c389_f113v456",
        ),
        (
            "special diet",
            "Chicken-Free",
            "https://www.chewy.com/b/chicken-free-wet-cat-food-142398",
        ),
    ]


def test_extract_chewy_filter_surfaces_uses_package_count_for_packaging_allowlist() -> (
    None
):
    category_url = "https://www.chewy.com/b/wet-food-389"
    html = """
        <html>
          <body>
            <h2>Package Count</h2>
            <a href="/f/13-24-count-wet-cat-food_c389_f113v789">13-24 count</a>
            <h2>Flavor</h2>
            <a href="/b/chicken-wet-cat-food-300">Chicken</a>
          </body>
        </html>
    """

    surfaces = extract_chewy_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key="wet_cat_food",
        allowed_families=("packaging",),
    )

    assert [(item.filter_family, item.filter_value) for item in surfaces] == [
        ("package count", "13-24 count"),
    ]


def test_extract_chewy_filter_surfaces_uses_tracked_facet_metadata() -> None:
    category_url = "https://www.chewy.com/b/wet-food-389"
    html = """
        <html>
          <body>
            <div class="js-tracked-facet" data-facet-category="Lifestage" data-facet-group-id="5">
              <div>
                <input type="checkbox" aria-label="Adult" data-facet-id="9060" />
                <a href="/f/canned-adult-cat-food_c389_f5v9060">Adult</a>
              </div>
              <div>
                <input type="checkbox" aria-label="Senior" data-facet-id="9063" />
                <a>Senior</a>
              </div>
            </div>
            <div class="js-tracked-facet" data-facet-category="Package Count" data-facet-group-id="194">
              <div>
                <input type="checkbox" aria-label="6 count or less" data-facet-id="19633414" />
                <a>6 count or less</a>
              </div>
              <div>
                <input type="checkbox" aria-label="25 count &amp; above" data-facet-id="19633390" />
                <a>25 count &amp; above</a>
              </div>
            </div>
            <div class="js-tracked-facet" data-facet-category="Price" data-facet-group-id="99">
              <input type="checkbox" aria-label="Less than $10" data-facet-id="10" />
            </div>
          </body>
        </html>
    """

    surfaces = extract_chewy_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key="wet_cat_food",
    )

    assert [
        (item.filter_family, item.filter_value, item.filter_url) for item in surfaces
    ] == [
        (
            "lifestage",
            "Adult",
            "https://www.chewy.com/f/canned-adult-cat-food_c389_f5v9060",
        ),
        (
            "lifestage",
            "Senior",
            "https://www.chewy.com/f/senior-wet-cat-food_c389_f5v9063",
        ),
        (
            "package count",
            "25 count & above",
            "https://www.chewy.com/f/25-count-above-wet-cat-food_c389_f194v19633390",
        ),
        (
            "package count",
            "6 count or less",
            "https://www.chewy.com/f/6-count-or-less-wet-cat-food_c389_f194v19633414",
        ),
    ]


def test_normalize_chewy_filter_family_aliases_flavour() -> None:
    assert normalize_chewy_filter_family("Flavour") == "flavor"
