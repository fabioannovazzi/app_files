from __future__ import annotations

from modules.pdp.amazon_filter_discovery import (
    extract_amazon_filter_surfaces,
    normalize_amazon_filter_family,
)


def test_extract_amazon_filter_surfaces_reads_heading_and_canonicalizes_url() -> None:
    html = """
    <html><body>
      <div aria-label="Brand">
        <a href="/s?k=lipstick&i=beauty&rh=n%3A3760911%2Cp_89%3AMaybelline&page=2">
          Maybelline (12)
        </a>
      </div>
    </body></html>
    """

    surfaces = extract_amazon_filter_surfaces(
        category_url="https://www.amazon.com/s?k=lipstick&i=beauty",
        html=html,
        category_key="lipstick",
    )

    assert len(surfaces) == 1
    surface = surfaces[0]
    assert surface.filter_family == "brand"
    assert surface.filter_value == "Maybelline"
    assert surface.filter_url == (
        "https://www.amazon.com/s?k=lipstick&i=beauty&rh=n%3A3760911%2Cp_89%3AMaybelline"
    )


def test_extract_amazon_filter_surfaces_respects_allowed_families() -> None:
    html = """
    <html><body>
      <section>
        <h2>Brand</h2>
        <a href="/s?k=lipstick&i=beauty&rh=p_89%3AMaybelline">Maybelline</a>
      </section>
      <section>
        <h2>Department</h2>
        <a href="/s?k=lipstick&i=beauty&rh=n%3A11058281">Beauty &amp; Personal Care</a>
      </section>
    </body></html>
    """

    surfaces = extract_amazon_filter_surfaces(
        category_url="https://www.amazon.com/s?k=lipstick&i=beauty",
        html=html,
        category_key="lipstick",
        allowed_families=("brand",),
    )

    assert [(surface.filter_family, surface.filter_value) for surface in surfaces] == [
        ("brand", "Maybelline")
    ]


def test_normalize_amazon_filter_family_cleans_text() -> None:
    assert normalize_amazon_filter_family("Beauty & Personal Care") == (
        "beauty and personal care"
    )


def test_normalize_amazon_filter_family_maps_pet_filter_aliases() -> None:
    assert normalize_amazon_filter_family("Brands") == "brand"
    assert normalize_amazon_filter_family("Container Type") == "packaging type"
    assert normalize_amazon_filter_family("Count") == "package count"
    assert normalize_amazon_filter_family("Lifestage") == "life stage"
    assert normalize_amazon_filter_family("Age Range Description") == "life stage"
    assert normalize_amazon_filter_family("Diet Type") == "special diet"
    assert normalize_amazon_filter_family("Animal Food Diet Type") == "special diet"
    assert normalize_amazon_filter_family("Item Form") == "food texture"


def test_extract_amazon_filter_surfaces_prioritizes_pet_food_attributes() -> None:
    html = """
    <html><body>
      <section>
        <h2>Brands</h2>
        <a href="/s?k=wet+cat+food&i=pets&rh=p_89%3AFancy+Feast">Fancy Feast</a>
      </section>
      <section>
        <h2>Container Type</h2>
        <a href="/s?k=wet+cat+food&i=pets&rh=p_n_feature_browse-bin%3ACan">Can</a>
      </section>
      <section>
        <h2>Flavor</h2>
        <a href="/s?k=wet+cat+food&i=pets&rh=p_n_feature_browse-bin%3AChicken">Chicken</a>
        <a href="/s?k=wet+cat+food&i=pets&rh=p_n_feature_browse-bin%3ADry+Kibble">Dry Kibble</a>
        <a href="/s?k=wet+cat+food&i=pets&rh=p_n_feature_browse-bin%3APate">Pate</a>
      </section>
    </body></html>
    """

    surfaces = extract_amazon_filter_surfaces(
        category_url="https://www.amazon.com/s?k=wet+cat+food&i=pets",
        html=html,
        category_key="wet_cat_food",
    )

    assert [(surface.filter_family, surface.filter_value) for surface in surfaces] == [
        ("flavor", "Chicken"),
        ("packaging type", "Can"),
        ("food texture", "Pate"),
        ("brand", "Fancy Feast"),
    ]
