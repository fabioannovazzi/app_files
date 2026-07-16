from __future__ import annotations

from modules.pdp.adapters.saloncentric import SaloncentricAdapter
from modules.pdp.engine import PDPParser
from modules.pdp.profile_loader import load_profile


HTML = """
<html>
  <head>
    <meta itemprop="brand" content="L'Oréal Professionnel" />
    <meta
      name="description"
      content="Majirel permanent color for professional salon use."
    />
  </head>
  <body>
    <h1>NEW! Majirel Permanent Color 2oz.</h1>
    <div class="product-gallery">
      <img
        class="productthumbnail c-image"
        data-twic-src="image:/dw/image/v2/BJRM_PRD/on/demandware.static/-/Sites-salon-centric-master-catalog/default/dw29465f01/large/884486538611_5.jpg"
        data-large-img='{"url":"https://media.saloncentric.com/dw/image/v2/BJRM_PRD/on/demandware.static/-/Sites-salon-centric-master-catalog/default/dw29465f01/large/884486538611_5.jpg?twic=v1/quality=100","hires":"https://media.saloncentric.com/dw/image/v2/BJRM_PRD/on/demandware.static/-/Sites-salon-centric-master-catalog/default/dw29465f01/large/884486538611_5.jpg?twic=v1/quality=100/refit=auto(2p)/max=1000x1000"}'
        alt="Preview image 7 of NEW! Majirel Permanent Color 2oz."
        title="NEW! Majirel Permanent Color 2oz."
      />
      <img
        class="productthumbnail c-image"
        data-twic-src="image:/dw/image/v2/BJRM_PRD/on/demandware.static/-/Sites-salon-centric-master-catalog/default/dw1cb5825e/large/884486538611.jpg"
        data-large-img='{"url":"https://media.saloncentric.com/dw/image/v2/BJRM_PRD/on/demandware.static/-/Sites-salon-centric-master-catalog/default/dw1cb5825e/large/884486538611.jpg?twic=v1/quality=100","hires":"https://media.saloncentric.com/dw/image/v2/BJRM_PRD/on/demandware.static/-/Sites-salon-centric-master-catalog/default/dw1cb5825e/large/884486538611.jpg?twic=v1/quality=100/refit=auto(2p)/max=1000x1000"}'
        alt="Preview image 1 of NEW! Majirel Permanent Color 2oz."
        title="NEW! Majirel Permanent Color 2oz."
      />
    </div>
    <div
      id="product-dynamic-tracking-loreal-professionnel-majirel-permanent-color"
      data-category-breakout="Hair > Hair Color"
      data-fromated-price="11.34"
      data-product-brand="L'Oréal Professionnel"
      data-product-number-reviews="205"
      data-product-number-stars="4.4927"
    ></div>
    <ul class="product-variations">
      <li
        class="product_shade_item in_stock"
        data-product-id="884486538321"
        data-product-collection="Majirel"
        data-product-level="01"
        data-product-information='{"masterProductID":"loreal-professionnel-majirel-permanent-color"}'
        data-product-search-query='["NEW! Majirel Permanent Color 2oz.","01","1/1N","884486538321","P2812600","Majirel"]'
      >
        <div class="variant_image" data-itemid="884486538321">
          <img
            src="https://media.saloncentric.com/small/884486538321.jpg"
            alt="NEW! Majirel Permanent Color 2oz."
          />
        </div>
        <span>Majirel 1/1N #P2812600</span>
      </li>
      <li
        class="product_shade_item out_of_stock"
        data-product-id="884486538383"
        data-product-collection="Majirel"
        data-product-level="10"
        data-product-information='{"masterProductID":"loreal-professionnel-majirel-permanent-color"}'
        data-product-search-query='["NEW! Majirel Permanent Color 2oz.","10","10.1/10B","884486538383","P2813200","Majirel"]'
      >
        <div class="variant_image" data-itemid="884486538383">
          <img
            src="https://media.saloncentric.com/small/884486538383.jpg"
            alt="NEW! Majirel Permanent Color 2oz."
          />
        </div>
        <span>Majirel 10.1/10B #P2813200</span>
      </li>
    </ul>
    <div
      id="product-dynamic-tracking-884486538321"
      data-fromated-price="11.34"
      data-product-status="7432 Item(s) In Stock"
      data-product-brand="L'Oréal Professionnel"
    ></div>
    <div
      id="product-dynamic-tracking-884486538383"
      data-fromated-price="11.34"
      data-product-status="Out of Stock"
      data-product-brand="L'Oréal Professionnel"
    ></div>
    <div id="bvseo-reviewsSection" style="display: none;">
      <div
        class="bvseo-review"
        itemprop="review"
        itemscope
        itemtype="https://schema.org/Review"
        data-reviewid="180199551"
      >
        <span itemprop="reviewRating" itemscope itemtype="https://schema.org/Rating">
          Rated <span itemprop="ratingValue">5</span> out of
          <span itemprop="bestRating">5</span>
        </span>
        by
        <span itemprop="author" itemtype="https://schema.org/Person" itemscope>
          <span itemprop="name">R Oliveira</span>
        </span>
        from
        <span itemprop="name">L'Oreal's color is long lasting</span>
        <span itemprop="description">
          I've been using MAJIREL from L'Oreal Professional for over 35 years and it's the best one yet!
        </span>
        <div class="bvseo-pubdate">Date published: 2026-03-09</div>
        <meta itemprop="datePublished" content="2026-03-09" />
      </div>
      <div
        class="bvseo-review"
        itemprop="review"
        itemscope
        itemtype="https://schema.org/Review"
        data-reviewid="179532191"
      >
        <span itemprop="reviewRating" itemscope itemtype="https://schema.org/Rating">
          Rated <span itemprop="ratingValue">4</span> out of
          <span itemprop="bestRating">5</span>
        </span>
        by
        <span itemprop="author" itemtype="https://schema.org/Person" itemscope>
          <span itemprop="name">cpbostonhair</span>
        </span>
        from
        <span itemprop="name">great finish</span>
        <span itemprop="description">
          The coverage/grey coverage with this product is fantastic and the finish has a beautiful shine.
        </span>
        <div class="bvseo-pubdate">Date published: 2026-02-02</div>
        <meta itemprop="datePublished" content="2026-02-02" />
      </div>
    </div>
  </body>
</html>
"""


def test_saloncentric_parser_extracts_parent_and_variants_from_dom_state() -> None:
    profile = load_profile("saloncentric_permanent")
    parser = PDPParser(profile=profile, adapter=SaloncentricAdapter(), fetcher=None)

    result = parser.parse_url(
        "https://www.saloncentric.com/loreal-professionnel-majirel-permanent-color.html",
        html=HTML,
    )

    assert result.parent is not None
    assert result.parent.parent_product_id == "loreal-professionnel-majirel-permanent-color"
    assert result.parent.brand_raw == "L'Oréal Professionnel"
    assert result.parent.title_raw == "NEW! Majirel Permanent Color 2oz."
    assert result.parent.category_path == ("Hair", "Hair Color")
    assert result.parent.extras["review_count"] == 205
    assert result.parent.extras["review_rating"] == 4.4927
    assert result.parent.extras["reviews_meta"] == {"provider": "bazaarvoice"}
    assert (
        result.parent.extras["hero_image_url"]
        == "https://media.saloncentric.com/dw/image/v2/BJRM_PRD/on/demandware.static/-/Sites-salon-centric-master-catalog/default/dw1cb5825e/large/884486538611.jpg?twic=v1/quality=100/refit=auto(2p)/max=1000x1000"
    )
    assert result.parent.extras["gallery_images"] == [
        "https://media.saloncentric.com/dw/image/v2/BJRM_PRD/on/demandware.static/-/Sites-salon-centric-master-catalog/default/dw1cb5825e/large/884486538611.jpg?twic=v1/quality=100/refit=auto(2p)/max=1000x1000",
        "https://media.saloncentric.com/dw/image/v2/BJRM_PRD/on/demandware.static/-/Sites-salon-centric-master-catalog/default/dw29465f01/large/884486538611_5.jpg?twic=v1/quality=100/refit=auto(2p)/max=1000x1000",
    ]
    reviews = result.parent.extras["reviews"]
    assert isinstance(reviews, list)
    assert reviews == [
        {
            "review_id": "180199551",
            "headline": "L'Oreal's color is long lasting",
            "comment": "I've been using MAJIREL from L'Oreal Professional for over 35 years and it's the best one yet!",
            "author": "R Oliveira",
            "created_date": "2026-03-09",
            "rating": 5.0,
        },
        {
            "review_id": "179532191",
            "headline": "great finish",
            "comment": "The coverage/grey coverage with this product is fantastic and the finish has a beautiful shine.",
            "author": "cpbostonhair",
            "created_date": "2026-02-02",
            "rating": 4.0,
        },
    ]
    assert len(result.variants) == 2
    assert result.errors == ()

    first = result.variants[0]
    assert first.variant_id == "884486538321"
    assert first.shade_name_raw == "1/1N"
    assert first.price_raw == "11.34"
    assert first.currency == "USD"
    assert first.availability == "InStock"
    assert first.hero_image_url == "https://media.saloncentric.com/small/884486538321.jpg"
    assert first.swatch_image_url == "https://media.saloncentric.com/small/884486538321.jpg"
    assert first.size_text_raw == "2oz."

    second = result.variants[1]
    assert second.variant_id == "884486538383"
    assert second.shade_name_raw == "10.1/10B"
    assert second.availability == "OutOfStock"


def test_saloncentric_parser_prefers_real_image_over_data_placeholder() -> None:
    html = HTML.replace(
        'src="https://media.saloncentric.com/small/884486538321.jpg"',
        (
            'src="data:image/png;base64,ZmFrZQ==" '
            'data-src="https://media.saloncentric.com/small/884486538321.jpg"'
        ),
        1,
    )
    profile = load_profile("saloncentric_permanent")
    parser = PDPParser(profile=profile, adapter=SaloncentricAdapter(), fetcher=None)

    result = parser.parse_url(
        "https://www.saloncentric.com/loreal-professionnel-majirel-permanent-color.html",
        html=html,
    )

    assert result.parent is not None
    first = result.variants[0]
    assert first.hero_image_url == "https://media.saloncentric.com/small/884486538321.jpg"
    assert first.swatch_image_url == "https://media.saloncentric.com/small/884486538321.jpg"


def test_saloncentric_parser_converts_twic_image_source() -> None:
    html = HTML.replace(
        'src="https://media.saloncentric.com/small/884486538321.jpg"',
        (
            'src="data:image/png;base64,ZmFrZQ==" '
            'data-twic-src="image:/dw/image/v2/BJRM_PRD/on/demandware.static/-/Sites-salon-centric-master-catalog/default/dw8d28c74f/small/884486538321.jpg" '
            'data-twic-transform="quality=100/cover=120x120"'
        ),
        1,
    )
    profile = load_profile("saloncentric_permanent")
    parser = PDPParser(profile=profile, adapter=SaloncentricAdapter(), fetcher=None)

    result = parser.parse_url(
        "https://www.saloncentric.com/loreal-professionnel-majirel-permanent-color.html",
        html=html,
    )

    assert result.parent is not None
    first = result.variants[0]
    assert (
        first.hero_image_url
        == "https://media.saloncentric.com/dw/image/v2/BJRM_PRD/on/demandware.static/-/Sites-salon-centric-master-catalog/default/dw8d28c74f/small/884486538321.jpg?twic=v1/quality=100/cover=120x120"
    )
    assert first.swatch_image_url == first.hero_image_url
