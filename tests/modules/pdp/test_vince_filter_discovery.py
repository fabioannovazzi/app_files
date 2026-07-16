from __future__ import annotations

from modules.pdp.models import FilterSurface
from modules.pdp.vince_catalog import vince_parent_id_from_url
from modules.pdp.vince_filter_discovery import (
    build_vince_filter_records,
    extract_vince_filter_observations_from_html,
    extract_vince_filter_surfaces,
    vince_site_filters_from_values,
)


def test_extract_vince_filter_surfaces_from_category_html() -> None:
    html = """
    <div class="refinement refinement-new-+-now">
      <button data-href="/on/demandware.store/Sites-vince-Site/default/Search-ShowAjax?cgid=sneakers-for-women&prefn1=badge&prefv1=New">
        New <span>Refine by New + Now: New</span>
      </button>
    </div>
    <div class="refinement refinement-color">
      <button data-href="/on/demandware.store/Sites-vince-Site/default/Search-ShowAjax?cgid=sneakers-for-women&prefn1=refinementColor&prefv1=Black">
        Black <span>Refine by Color: Black</span>
      </button>
    </div>
    <div class="refinement refinement-size">
      <button data-href="/on/demandware.store/Sites-vince-Site/default/Search-ShowAjax?cgid=sneakers-for-women&prefn1=size&prefv1=8">
        8 <span>Refine by Size: 8</span>
      </button>
    </div>
    <div class="refinement refinement-price">
      <div class="price-slider js-price-ref-slider">
        <input class="js-price-ref-min" data-full-min="235.0" value="235.0"
               data-href="/on/demandware.store/Sites-vince-Site/default/Search-ShowAjax?cgid=sneakers-for-women&pmin=9998&pmax=9999">
        <input class="js-price-ref-max" data-full-max="300.0" value="300.0"
               data-href="/on/demandware.store/Sites-vince-Site/default/Search-ShowAjax?cgid=sneakers-for-women&pmin=9998&pmax=9999">
      </div>
    </div>
    """

    surfaces = extract_vince_filter_surfaces(
        category_url="https://www.vince.com/sneakers-for-women/",
        html=html,
    )

    assert {(item.filter_family, item.filter_value) for item in surfaces} == {
        ("color_family", "Black"),
        ("new_now", "New"),
        ("price", "235.0-300.0"),
        ("size", "8"),
    }


def test_vince_site_filters_from_product_values() -> None:
    filters = vince_site_filters_from_values(
        color="NIGHT BLUE/MOONLIGHT",
        sizes=("8", "10"),
        is_new=True,
    )

    assert {(item["filter_family"], item["filter_value"]) for item in filters} == {
        ("color_family", "Beige"),
        ("color_family", "Blue"),
        ("color_family", "Multicolor"),
        ("new_now", "New"),
        ("size", "10"),
        ("size", "8"),
    }


def test_build_vince_filter_records_from_parent_extras() -> None:
    surfaces, observations = build_vince_filter_records(
        [
            {
                "parent_product_id": "J8129L2INDIGOFLAX",
                "pdp_url": "https://www.vince.com/product/oasis-contrast-edge-suede-sneaker-J8129L2INDIGOFLAX.html",
                "category_key": "low_top_sneakers",
                "extras": {
                    "site_filters": [
                        {
                            "filter_family": "color_family",
                            "filter_value": "Blue",
                            "filter_label": "Blue",
                            "filter_url": "https://www.vince.com/sneakers-for-women/?prefn1=refinementColor&prefv1=Blue",
                        }
                    ]
                },
            }
        ]
    )

    assert [(item.filter_family, item.filter_value) for item in surfaces] == [
        ("color_family", "Blue")
    ]
    assert [
        (item.parent_product_id, item.filter_family, item.filter_value)
        for item in observations
    ] == [("J8129L2INDIGOFLAX", "color_family", "Blue")]


def test_extract_vince_filter_observations_from_filter_html() -> None:
    surface = FilterSurface(
        retailer="vince",
        category_key="low_top_sneakers",
        filter_family="size",
        filter_value="8",
        filter_url="https://www.vince.com/on/demandware.store/Sites-vince-Site/default/Search-ShowAjax?cgid=sneakers-for-women&prefn1=size&prefv1=8",
        filter_label="8",
    )
    html = """
    <a href="/product/oasis-contrast-edge-suede-sneaker-J8129L2INDIGOFLAX.html">
      Oasis Contrast-Edge Suede Sneaker
    </a>
    """

    observations = extract_vince_filter_observations_from_html(
        filter_surface=surface,
        html=html,
        parent_id_from_url=vince_parent_id_from_url,
    )

    assert [
        (item.parent_product_id, item.filter_family, item.filter_value)
        for item in observations
    ] == [("J8129L2INDIGOFLAX", "size", "8")]
