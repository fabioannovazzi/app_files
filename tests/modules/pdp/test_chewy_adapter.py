from __future__ import annotations

from modules.pdp.adapters.chewy import ChewyAdapter
from modules.pdp.engine import PDPParser
from modules.pdp.profile_loader import load_profile

HTML = """
<html>
  <head>
    <title>Fancy Feast Gravy Lovers Poultry & Beef Feast Variety Pack Canned Cat Food, 3-oz, case of 24 - Chewy.com</title>
    <meta property="og:title" content="Fancy Feast Gravy Lovers Poultry & Beef Feast Variety Pack Canned Cat Food, 3-oz, case of 24" />
  </head>
  <body>
    <nav aria-label="Breadcrumb">
      <a href="/">Home</a>
      <a href="/b/cat-325">Cat</a>
      <a href="/b/wet-food-389">Wet Food</a>
    </nav>
    <main>
      <h1>Fancy Feast Gravy Lovers Poultry &amp; Beef Feast Variety Pack Canned Cat Food, 3-oz, case of 24</h1>
      <div class="product-brand">By <a href="/b/fancy-feast-716">Fancy Feast</a></div>
      <img
        alt="Fancy Feast Gravy Lovers Poultry &amp; Beef Feast Variety Pack Canned Cat Food, 3-oz, case of 24 slide 1 of 9"
        src="https://image.chewy.com/is/image/catalog/103856_MAIN._AC_SL600_V1_.jpg"
      />
      <section data-testid="variation-flavor">
        <h2>Flavor</h2>
        <button aria-pressed="true">Poultry &amp; Beef</button>
      </section>
      <section data-testid="variation-size">
        <h2>Size</h2>
        <button aria-pressed="true">3-oz, case of 24</button>
      </section>
      <div data-testid="price">
        <span>$23.86 Chewy Price</span>
      </div>
      <div class="list-price">
        <span>$26.16 List Price</span>
      </div>
      <div data-testid="availability">In Stock</div>
      <div>Rated 4.6 out of 5 stars 4.6 20,413 Ratings</div>
      <section>
        <h2>Details</h2>
        <ul>
          <li>Crafted with chicken, turkey and beef in savory gravy.</li>
          <li>Complete and balanced nutrition for adult cats.</li>
        </ul>
      </section>
      <section>
        <h2>Ingredients</h2>
        <p>Fish Broth, Turkey, Wheat Gluten, Chicken.</p>
      </section>
      <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "__APOLLO_CHEWY_API_STATE__": {
                "Review:{\\"id\\":\\"15775184\\",\\"reviewText\\":\\"This is the only wet food that all 3 of our cats can agree on.\\",\\"title\\":\\"Well-liked by all 3 cats\\",\\"rating\\":5}": {
                  "__typename": "Review",
                  "contentId": "274080330",
                  "helpfulness": 1,
                  "id": "15775184",
                  "isIncentivized": false,
                  "isVerified": true,
                  "paginatedPhotos": {"__typename": "ReviewPhotosPage", "results": []},
                  "rating": 5,
                  "reviewText": "This is the only wet food that all 3 of our cats can agree on.",
                  "submittedAt": "2026-02-22T21:29:07.000Z",
                  "submittedBy": "JEFF",
                  "title": "Well-liked by all 3 cats"
                },
                "Review:{\\"id\\":\\"15992732\\",\\"reviewText\\":\\"Kiwi finishes 2 cans a day with no spillage on the mat.\\",\\"title\\":\\"Kiwi cleaned her bowl twice\\",\\"rating\\":5}": {
                  "__typename": "Review",
                  "contentId": "274609028",
                  "helpfulness": 2,
                  "id": "15992732",
                  "isIncentivized": false,
                  "isVerified": true,
                  "paginatedPhotos": {
                    "__typename": "ReviewPhotosPage",
                    "results": [{"thumbnailUrl": "https://photos.example/review.jpg"}]
                  },
                  "rating": 5,
                  "reviewText": "Kiwi finishes 2 cans a day with no spillage on the mat.",
                  "submittedAt": "2026-03-12T20:37:48.000Z",
                  "submittedBy": "Lorrie",
                  "title": "Kiwi cleaned her bowl twice"
                }
              }
            }
          }
        }
      </script>
    </main>
  </body>
</html>
"""


ACCORDION_HTML = """
<html>
  <head>
    <title>9 Lives Pate Favorites Variety Pack Canned Cat Food, 5.5-oz, case of 24 - Chewy.com</title>
    <meta property="og:title" content="9 Lives Pate Favorites Variety Pack Canned Cat Food, 5.5-oz, case of 24" />
  </head>
  <body>
    <nav aria-label="Breadcrumb">
      <a href="/b/cat-325">Cat Supplies</a>
      <a href="/b/food-387">Cat Food</a>
      <a href="/b/wet-food-389">Wet Cat Food</a>
    </nav>
    <main>
      <h1>9 Lives Pate Favorites Variety Pack Canned Cat Food, 5.5-oz, case of 24</h1>
      <div class="product-brand">By <a href="/brands/9-lives">9 Lives</a></div>
      <img
        alt="9 Lives Pate Favorites Variety Pack Canned Cat Food, 5.5-oz, case of 24 slide 1 of 12"
        src="https://image.chewy.com/catalog/general/images/moe/0691f1f2-2981-71e2-8000-42e041aa48ff._AC_SX500_SY400_QL75_V1_.jpg"
      />
      <section data-testid="variation-size">
        <h2>Size</h2>
        <button aria-pressed="true">5.5-oz, case of 24</button>
      </section>
      <div data-testid="price"><span>$6.19 Chewy Price</span></div>
      <div class="list-price"><span>$7.88 List Price</span></div>
      <div data-testid="availability">In Stock</div>
      <div>Rated 4.3 out of 5 stars 4.3 2,002 Ratings</div>

      <div data-testid="ftas-message">
        <span>Save 35% today</span>
        <button data-testid="promotion-details-button">Details</button>
      </div>

      <div class="kib-accordion-new-item kib-accordion-new-item--open styles_accordion__UgvJk">
        <div class="kib-accordion-new-item__header-content">
          <div><div class="kib-accordion-new-item__header-title-wrapper"><h3 class="kib-accordion-new-item__title">Details</h3></div></div>
        </div>
        <div class="kib-accordion-new-item__content">
          <div class="kib-accordion-new-item__content-transition">
            <div class="kib-truncation-content">
              <section class="styles_infoGroupSection__bFZf8" id="KEY_BENEFITS-section">
                <ul>
                  <li>This variety pack features 3 recipes.</li>
                  <li>Provides 100% complete and balanced nutrition for adult cats.</li>
                </ul>
              </section>
              <div style="display:none">
                <section class="styles_infoGroupSection__bFZf8" id="KEY_BENEFITS-section">
                  <ul>
                    <li>This variety pack features 3 recipes.</li>
                    <li>Provides 100% complete and balanced nutrition for adult cats.</li>
                  </ul>
                </section>
                <section class="styles_infoGroupSection__bFZf8">
                  <p>Keep your kitty interested in mealtime with 9 Lives Pate Favorites Variety Pack Canned Cat Food.</p>
                </section>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="kib-accordion-new-item styles_accordion__UgvJk">
        <div class="kib-accordion-new-item__header-content">
          <div><div class="kib-accordion-new-item__header-title-wrapper"><h3 class="kib-accordion-new-item__title">Ingredient Information</h3></div></div>
        </div>
        <div class="kib-accordion-new-item__content">
          <div class="kib-accordion-new-item__content-transition">
            <section class="styles_infoGroupSection__bFZf8" id="INGREDIENTS-section">
              <div class="styles_infoGroupSectionTitle___9Hld">Ingredients</div>
              <div>
                <p>Meaty Paté Super Supper Ingredients: Meat By-Products, Water Sufficient for Processing.</p>
                <p>Meaty Paté With Real Chicken Ingredients: Meat By-products, Water Sufficient for Processing, Chicken.</p>
              </div>
            </section>
          </div>
        </div>
      </div>

      <div class="kib-accordion-new-item styles_accordion__UgvJk">
        <div class="kib-accordion-new-item__header-content">
          <div><div class="kib-accordion-new-item__header-title-wrapper"><h3 class="kib-accordion-new-item__title">Feeding Instructions</h3></div></div>
        </div>
        <div class="kib-accordion-new-item__content">
          <div class="kib-accordion-new-item__content-transition">
            <section class="styles_infoGroupSection__bFZf8" id="FEEDING_INSTRUCTIONS-section">
              <p>Feed an Adult 8 - 10 lb cat, or a 3 lb kitten, 1 can twice a day.</p>
            </section>
            <section class="styles_infoGroupSection__bFZf8" id="TRANSITION_INSTRUCTIONS-section">
              <div class="styles_infoGroupSectionTitle___9Hld">Transition Instructions</div>
              <p>Transition over 5-7 days.</p>
            </section>
          </div>
        </div>
      </div>
    </main>
  </body>
</html>
"""


FAMILY_HTML = """
<html>
  <head>
    <title>Tiki Cat After Dark Velvet Mousse Variety Pack Grain-Free Wet Cat Food, 2.8-oz pouch, case of 12 - Chewy.com</title>
    <meta property="og:title" content="Tiki Cat After Dark Velvet Mousse Variety Pack Grain-Free Wet Cat Food, 2.8-oz pouch, case of 12" />
    <meta property="og:url" content="https://www.chewy.com/tiki-cat-after-dark-velvet-mousse/dp/883622" />
    <link rel="canonical" href="https://www.chewy.com/tiki-cat-after-dark-velvet-mousse/dp/883622" />
  </head>
  <body>
    <main>
      <h1>Tiki Cat After Dark Velvet Mousse Variety Pack Grain-Free Wet Cat Food, 2.8-oz pouch, case of 12</h1>
      <div class="product-brand">By <a href="/b/tiki-cat-7617">Tiki Cat</a></div>
      <img
        alt="Tiki Cat After Dark Velvet Mousse Variety Pack Grain-Free Wet Cat Food, 2.8-oz pouch, case of 12 slide 1 of 5"
        src="https://image.chewy.com/catalog/general/images/tiki/img-341524._AC_SS300_V1_.jpg"
      />
      <div data-testid="text-swatch-selector">
        <div class="kib-swatch">
          <div aria-live="polite">
            <h2 class="kib-swatch__heading" aria-label="Flavor: Variety Pack , Current Selection">
              <span aria-hidden="true"><span id="kib-swatch-flavor-title">Flavor</span>: <strong>Variety Pack</strong></span>
            </h2>
          </div>
          <div class="kib-swatch__group kib-swatch__group--multiline" role="group" aria-labelledby="kib-swatch-flavor-title">
            <button class="kib-swatch__text-swatch" aria-current="false">
              <div class="kib-swatch__text-swatch-header">Chicken</div>
              <div class="kib-swatch__text-swatch-details">$26.28</div>
            </button>
            <button class="kib-swatch__text-swatch" aria-current="false">
              <div class="kib-swatch__text-swatch-header">Chicken &amp; Beef</div>
              <div class="kib-swatch__text-swatch-details">$27.48</div>
            </button>
            <button class="kib-swatch__text-swatch" aria-current="false">
              <div class="kib-swatch__text-swatch-header">Chicken &amp; Duck</div>
              <div class="kib-swatch__text-swatch-details">$27.48</div>
            </button>
            <button class="kib-swatch__text-swatch" aria-current="false">
              <div class="kib-swatch__text-swatch-header">Chicken &amp; Quail Egg</div>
              <div class="kib-swatch__text-swatch-details">$27.48</div>
            </button>
            <button class="kib-swatch__text-swatch kib-swatch__text-swatch--selected" aria-current="true">
              <div class="kib-swatch__text-swatch-header">Variety Pack</div>
              <div class="kib-swatch__text-swatch-details">$27.11</div>
            </button>
          </div>
        </div>
      </div>
      <section data-testid="variation-size">
        <h2>Size</h2>
        <button aria-pressed="true">2.8-oz pouch, case of 12</button>
      </section>
      <div data-testid="price"><span>$27.11 Chewy Price</span></div>
      <div class="list-price"><span>$29.18 List Price</span></div>
      <div data-testid="availability">In Stock</div>

      <td class="kib-table-new__cell ws-row-header ws-table-cell js-tracked-product bigNumber" data-name="Tiki Cat After Dark Velvet Mousse Variety Pack Grain-Free Wet Cat Food, 2.8-oz pouch, case of 12" data-id="883622" data-price="$27.11">
        <a class="kib-product-image" href="https://www.chewy.com/tiki-cat-after-dark-velvet-mousse/dp/883622">
          <img alt="Tiki Cat After Dark Velvet Mousse Variety Pack Grain-Free Wet Cat Food, 2.8-oz pouch, case of 12" src="https://image.chewy.com/catalog/general/images/tiki/img-341524._AC_SS300_V1_.jpg" />
        </a>
      </td>
      <td class="kib-table-new__cell ws-row-header ws-table-cell js-tracked-product bigNumber" data-name="Tiki Cat After Dark Velvet Mousse Chicken Grain-Free Wet Cat Food, 2.8-oz pouch, case of 12" data-id="883910" data-price="$26.28">
        <a class="kib-product-image" href="https://www.chewy.com/tiki-cat-after-dark-velvet-mousse/dp/883910">
          <img alt="Tiki Cat After Dark Velvet Mousse Chicken Grain-Free Wet Cat Food, 2.8-oz pouch, case of 12" src="https://image.chewy.com/catalog/general/images/tiki/img-149307._AC_SS300_V1_.jpg" />
        </a>
      </td>
      <td class="kib-table-new__cell ws-row-header ws-table-cell js-tracked-product bigNumber" data-name="Tiki Cat After Dark Velvet Mousse Chicken &amp; Beef Grain-Free Wet Cat Food, 2.8-oz pouch, case of 12" data-id="883942" data-price="$27.48">
        <a class="kib-product-image" href="https://www.chewy.com/tiki-cat-after-dark-velvet-mousse/dp/883942">
          <img alt="Tiki Cat After Dark Velvet Mousse Chicken &amp; Beef Grain-Free Wet Cat Food, 2.8-oz pouch, case of 12" src="https://image.chewy.com/catalog/general/images/tiki/img-340490._AC_SS300_V1_.jpg" />
        </a>
      </td>
      <td class="kib-table-new__cell ws-row-header ws-table-cell js-tracked-product bigNumber" data-name="Tiki Cat After Dark Velvet Mousse Chicken &amp; Duck Grain-Free Wet Cat Food, 2.8-oz pouch, case of 12" data-id="883958" data-price="$27.48">
        <a class="kib-product-image" href="https://www.chewy.com/tiki-cat-after-dark-velvet-mousse/dp/883958">
          <img alt="Tiki Cat After Dark Velvet Mousse Chicken &amp; Duck Grain-Free Wet Cat Food, 2.8-oz pouch, case of 12" src="https://image.chewy.com/catalog/general/images/tiki/img-474462._AC_SS300_V1_.jpg" />
        </a>
      </td>
      <td class="kib-table-new__cell ws-row-header ws-table-cell js-tracked-product bigNumber" data-name="Tiki Cat After Dark Velvet Mousse Chicken &amp; Quail Egg Grain-Free Wet Cat Food, 2.8-oz pouch, case of 12" data-id="883926" data-price="$27.48">
        <a class="kib-product-image" href="https://www.chewy.com/tiki-cat-after-dark-velvet-mousse/dp/883926">
          <img alt="Tiki Cat After Dark Velvet Mousse Chicken &amp; Quail Egg Grain-Free Wet Cat Food, 2.8-oz pouch, case of 12" src="https://image.chewy.com/catalog/general/images/tiki/img-340508._AC_SS300_V1_.jpg" />
        </a>
      </td>
    </main>
  </body>
</html>
"""


def test_chewy_parser_extracts_parent_and_selected_variant_from_dom() -> None:
    profile = load_profile("chewy_wet_cat_food")
    parser = PDPParser(profile=profile, adapter=ChewyAdapter(), fetcher=None)

    result = parser.parse_url(
        "https://www.chewy.com/fancy-feast-gravy-lovers-poultry-beef/dp/103856",
        html=HTML,
    )

    assert result.errors == ()
    assert result.parent is not None
    assert result.parent.parent_product_id == "103856"
    assert result.parent.brand_raw == "Fancy Feast"
    assert (
        result.parent.title_raw
        == "Fancy Feast Gravy Lovers Poultry & Beef Feast Variety Pack Canned Cat Food, 3-oz, case of 24"
    )
    assert result.parent.category_path == ("Cat", "Wet Food")
    assert result.parent.extras["hero_image_url"] == (
        "https://image.chewy.com/is/image/catalog/103856_MAIN._AC_SL600_V1_.jpg"
    )
    assert result.parent.extras["rating"] == 4.6
    assert result.parent.extras["review_count"] == 20413
    assert result.parent.extras["details"]["details"] == [
        "Crafted with chicken, turkey and beef in savory gravy.",
        "Complete and balanced nutrition for adult cats.",
    ]
    assert result.parent.extras["details"]["ingredients"] == (
        "Fish Broth, Turkey, Wheat Gluten, Chicken."
    )
    assert result.parent.extras["reviews_meta"] == {
        "provider": "chewy_apollo",
        "source": "embedded_app_state",
        "limit": 5,
    }
    assert result.parent.extras["reviews"] == [
        {
            "review_id": "15775184",
            "headline": "Well-liked by all 3 cats",
            "comment": "This is the only wet food that all 3 of our cats can agree on.",
            "created_date": "2026-02-22T21:29:07.000Z",
            "author": "JEFF",
            "rating": 5.0,
            "helpfulness": 1,
            "is_verified": True,
            "is_incentivized": False,
            "photo_count": 0,
        },
        {
            "review_id": "15992732",
            "headline": "Kiwi cleaned her bowl twice",
            "comment": "Kiwi finishes 2 cans a day with no spillage on the mat.",
            "created_date": "2026-03-12T20:37:48.000Z",
            "author": "Lorrie",
            "rating": 5.0,
            "helpfulness": 2,
            "is_verified": True,
            "is_incentivized": False,
            "photo_count": 1,
        },
    ]

    assert len(result.variants) == 1
    variant = result.variants[0]
    assert variant.variant_id == "103856"
    assert variant.shade_name_raw == "Poultry & Beef"
    assert variant.size_text_raw == "3-oz, case of 24"
    assert variant.price_raw == "23.86"
    assert variant.currency == "USD"
    assert variant.availability == "InStock"
    assert variant.extras["list_price"] == "26.16"
    assert variant.hero_image_url == (
        "https://image.chewy.com/is/image/catalog/103856_MAIN._AC_SL600_V1_.jpg"
    )


def test_chewy_parser_extracts_current_accordion_details_sections() -> None:
    profile = load_profile("chewy_wet_cat_food")
    parser = PDPParser(profile=profile, adapter=ChewyAdapter(), fetcher=None)

    result = parser.parse_url(
        "https://www.chewy.com/9-lives-pate-favorites-variety-pack/dp/3678510",
        html=ACCORDION_HTML,
    )

    assert result.errors == ()
    assert result.parent is not None
    details = result.parent.extras["details"]
    assert details["details"] == [
        "This variety pack features 3 recipes.",
        "Provides 100% complete and balanced nutrition for adult cats.",
        "Keep your kitty interested in mealtime with 9 Lives Pate Favorites Variety Pack Canned Cat Food.",
    ]
    assert details["ingredients"] == [
        "Meaty Paté Super Supper Ingredients: Meat By-Products, Water Sufficient for Processing.",
        "Meaty Paté With Real Chicken Ingredients: Meat By-products, Water Sufficient for Processing, Chicken.",
    ]
    assert (
        details["feeding_instructions"]
        == "Feed an Adult 8 - 10 lb cat, or a 3 lb kitten, 1 can twice a day."
    )
    assert details["transition_instructions"] == "Transition over 5-7 days."
    assert "Keep your kitty interested in mealtime" in result.parent.extras["summary"]


def test_chewy_parser_keeps_selected_variant_even_with_same_slug_cards() -> None:
    profile = load_profile("chewy_wet_cat_food")
    parser = PDPParser(profile=profile, adapter=ChewyAdapter(), fetcher=None)

    result = parser.parse_url(
        "https://www.chewy.com/tiki-cat-after-dark-velvet-mousse/dp/883622",
        html=FAMILY_HTML,
    )

    assert result.errors == ()
    assert result.parent is not None
    assert result.parent.parent_product_id == "883622"
    assert len(result.variants) == 1
    variant = result.variants[0]
    assert variant.variant_id == "883622"
    assert variant.shade_name_raw is None
    assert variant.size_text_raw == "2.8-oz pouch, case of 12"
    assert variant.price_raw == "27.11"
    assert variant.availability == "InStock"
    assert variant.extras["list_price"] == "29.18"


def test_chewy_adapter_extracts_parent_id_from_dp_url() -> None:
    adapter = ChewyAdapter()

    parent_id = adapter.primary_id_from_url(
        "https://www.chewy.com/example-product/dp/3996614?query=wet"
    )

    assert parent_id == "3996614"
