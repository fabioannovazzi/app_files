from __future__ import annotations

from unittest.mock import patch

from modules.pdp.adapters.cosmoprofbeauty import CosmoprofbeautyAdapter
from modules.pdp.engine import PDPParser
from modules.pdp.models import ParentProduct
from modules.pdp.profile_loader import load_profile

HTML = """
<html>
  <head>
    <title>Example Permanent Color - Example Brand | CosmoProf</title>
    <meta itemprop="brand" content="Example Brand" />
    <meta
      name="description"
      content="Synthetic permanent color fixture for adapter tests."
    />
  </head>
  <body>
    <div class="breadcrumb">
      <a href="/hair-color">Hair Color</a>
      <a href="/hair-color/permanent">Permanent Hair Color</a>
    </div>
    <div class="h5">
      <a href="/search-show?q=Example" class="pdp-brand">Example Series</a>
      <meta itemprop="brand" content="Example Brand" />
      <span class="pdp-by">by</span>
      <a href="/shop-by-brand/example" class="pdp-brand">Example Brand</a>
    </div>
    <div class="text-align-center">
      <div data-bv-show="rating_summary" data-bv-product-id="TEST-PARENT-001"></div>
    </div>
    <div>
      <div data-bv-show="reviews" data-bv-product-id="TEST-PARENT-001"></div>
    </div>
    <h1 class="product-name" itemprop="name">Example Permanent Color</h1>
    <div class="owl-carousel owl-theme pdp-carousel">
      <div class="item zoom">
        <img src="https://example.com/images/example-main.jpg" itemprop="image" />
      </div>
      <div class="item zoom">
        <img src="https://example.com/images/example-alt.jpg" itemprop="image" />
      </div>
    </div>
    <div class="swatch-line" data-filter-item data-filter-name="1-0 natural|test-variant-001|000000000001" data-pid="TEST-VARIANT-001">
      <div class="swatch-line-inner-wrapper">
        <div class="swatch-and-info-wrapper">
          <div class="swatch-circle-container" data-pid="TEST-VARIANT-001" data-attr="color" title="1-0 Natural">
            <a href="#" data-pid="TEST-VARIANT-001" data-attrurl="/on/demandware.store/Sites-CosmoProf-Site/default/Product-Variation?pid=TEST-VARIANT-001&amp;quantity=1">
              <span
                data-attr-value="1-0_Natural"
                class="color-value swatch-value"
                style="background-image: url(https://example.com/images/variant-001.png?sw=60&amp;sh=60); background-size: cover;"
              ></span>
            </a>
          </div>
          <div class="swatch-name-container">
            <span class="variation-name">1-0 Natural</span>
            <span class="variation-pid">TEST-VARIANT-001</span>
          </div>
        </div>
        <input
          id="quantity-input-TEST-VARIANT-001"
          data-pid="TEST-VARIANT-001"
          data-url="/on/demandware.store/Sites-CosmoProf-Site/default/Product-AvailabilityJson?pids=TEST-VARIANT-001"
        />
      </div>
    </div>
    <div class="swatch-line" data-filter-item data-filter-name="1-1 ash|test-variant-002|000000000002" data-pid="TEST-VARIANT-002">
      <div class="swatch-line-inner-wrapper">
        <div class="swatch-and-info-wrapper">
          <div class="swatch-circle-container" data-pid="TEST-VARIANT-002" data-attr="color" title="1-1 Ash">
            <a href="#" data-pid="TEST-VARIANT-002" data-attrurl="/on/demandware.store/Sites-CosmoProf-Site/default/Product-Variation?pid=TEST-VARIANT-002&amp;quantity=1">
              <span
                data-attr-value="1-1_Ash"
                class="color-value swatch-value"
                style="background-image: url(https://example.com/images/variant-002.png?sw=60&amp;sh=60); background-size: cover;"
              ></span>
            </a>
          </div>
          <div class="swatch-name-container">
            <span class="variation-name">1-1 Ash</span>
            <span class="variation-pid">TEST-VARIANT-002</span>
          </div>
        </div>
      </div>
    </div>
    <div class="tab-content d-none d-lg-block" id="nav-tabContent">
      <div class="tab-pane fade show active" id="detailstab-TEST-PARENT-001" role="tabpanel">
        <div>
          <b>EXAMPLE</b> permanent color by Example Brand.
          <ul>
            <li><b>PPD and Resorcinol Free</b> without sacrificing color vibrancy and longevity</li>
            <li><b>Creamy Consistency</b> easier to control for a seamless application</li>
          </ul>
        </div>
      </div>
      <div class="tab-pane fade" id="directionstab-TEST-PARENT-001" role="tabpanel">
        <div>
          <ol>
            <li>Mix 1:1 with developer.</li>
            <li>Process 35 minutes at room temperature.</li>
          </ol>
        </div>
      </div>
      <div class="tab-pane fade" id="featuresbenefitstab-TEST-PARENT-001" role="tabpanel">
        <div>
          <ul>
            <li>100% grey coverage</li>
            <li>Plant-based keratin alternative</li>
          </ul>
        </div>
      </div>
      <div class="tab-pane fade" id="ingredientstab-TEST-PARENT-001" role="tabpanel">
        <div>See individual colors for ingredients.</div>
      </div>
    </div>
  </body>
</html>
"""


def test_cosmoprofbeauty_parser_extracts_parent_variants_and_details() -> None:
    profile = load_profile("cosmoprofbeauty_permanent")
    parser = PDPParser(profile=profile, adapter=CosmoprofbeautyAdapter(), fetcher=None)

    with patch(
        "modules.pdp.adapters.cosmoprofbeauty._extract_bazaarvoice_reviews",
        return_value=(
            4.333333333333333,
            3,
            [
                {
                    "review_id": "TEST-REVIEW-001",
                    "headline": "Useful color feedback",
                    "comment": "The synthetic fixture provides representative review text.",
                    "rating": 4.0,
                    "created_date": "2026-04-04T19:09:46.000+00:00",
                    "author": "Reviewer One",
                }
            ],
        ),
    ):
        result = parser.parse_url(
            "https://www.cosmoprofbeauty.com/TEST-PARENT-001.html",
            html=HTML,
        )

    assert result.errors == ()
    assert result.parent is not None
    assert result.parent.parent_product_id == "TEST-PARENT-001"
    assert result.parent.brand_raw == "Example Brand"
    assert result.parent.title_raw == "Example Permanent Color"
    assert result.parent.category_path == ("Hair Color", "Permanent Hair Color")
    assert (
        result.parent.extras["hero_image_url"]
        == "https://example.com/images/example-main.jpg"
    )
    assert result.parent.extras["gallery_images"] == [
        "https://example.com/images/example-main.jpg",
        "https://example.com/images/example-alt.jpg",
    ]
    assert result.parent.extras["rating"] == 4.333333333333333
    assert result.parent.extras["review_count"] == 3
    assert result.parent.extras["reviews_meta"] == {
        "provider": "bazaarvoice",
        "product_id": "TEST-PARENT-001",
    }
    assert result.parent.extras["reviews"] == [
        {
            "review_id": "TEST-REVIEW-001",
            "headline": "Useful color feedback",
            "comment": "The synthetic fixture provides representative review text.",
            "rating": 4.0,
            "created_date": "2026-04-04T19:09:46.000+00:00",
            "author": "Reviewer One",
        }
    ]

    details = result.parent.extras["details"]
    assert "Example Brand" in details["description_markdown"]
    assert details["usage"].startswith("Mix 1:1")
    assert details["features"] == [
        "100% grey coverage",
        "Plant-based keratin alternative",
    ]
    assert details["ingredients"] == "See individual colors for ingredients."

    assert len(result.variants) == 2
    variant_map = {variant.variant_id: variant for variant in result.variants}

    first = variant_map["TEST-VARIANT-001"]
    assert first.shade_name_raw == "1-0 Natural"
    assert first.barcode == "000000000001"
    assert (
        first.swatch_image_url
        == "https://example.com/images/variant-001.png?sw=60&sh=60"
    )
    assert first.hero_image_url == first.swatch_image_url
    assert first.extras["attributes"]["attr_value"] == "1-0_Natural"
    assert (
        "Product-Variation?pid=TEST-VARIANT-001"
        in first.extras["attributes"]["attr_url"]
    )


def test_cosmoprofbeauty_retailer_specific_fixes_overrides_generic_title_placeholder() -> (
    None
):
    adapter = CosmoprofbeautyAdapter()
    adapter.extra_blobs(HTML)

    parent = ParentProduct(
        retailer="cosmoprofbeauty",
        parent_product_id="TEST-PARENT-001",
        pdp_url="https://www.cosmoprofbeauty.com/TEST-PARENT-001.html",
        brand_raw="",
        brand_normalized="",
        title_raw="CosmoProf",
        title_normalized="cosmoprof",
        series_label_raw=None,
        category_path=tuple(),
        has_color_selector=False,
        qa_flags=tuple(),
        extras={},
    )

    adapter.retailer_specific_fixes(parent, [])

    assert parent.title_raw == "Example Permanent Color"
    assert parent.title_normalized == "Example Permanent Color"
    assert parent.brand_raw == "Example Brand"
    assert parent.brand_normalized == "Example Brand"
    assert parent.category_path == ("Hair Color", "Permanent Hair Color")
    assert (
        parent.extras["summary"]
        == "Synthetic permanent color fixture for adapter tests."
    )


def test_cosmoprofbeauty_adapter_skips_review_request_without_env_passkey() -> None:
    adapter = CosmoprofbeautyAdapter()

    with (
        patch("modules.pdp.adapters.cosmoprofbeauty._BV_PASSKEY", ""),
        patch("modules.pdp.adapters.cosmoprofbeauty.urlopen") as urlopen_mock,
    ):
        blobs = adapter.extra_blobs(HTML)

    assert blobs
    urlopen_mock.assert_not_called()
