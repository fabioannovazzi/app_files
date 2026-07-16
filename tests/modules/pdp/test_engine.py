from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from modules.pdp.adapters.amazon import AmazonAdapter
from modules.pdp.adapters.sephora import SephoraAdapter
from modules.pdp.adapters.ulta import UltaAdapter
from modules.pdp.engine import PDPParser
from modules.pdp.profile import (
    BlobSource,
    FieldNormalizationSpec,
    FieldPaths,
    IdExtractors,
    NormalizationConfig,
    ParentRules,
    PDPProfile,
    ValidationRules,
)
from modules.pdp.profile_loader import load_profile


def _minimal_brand_guard_profile() -> PDPProfile:
    normalization = FieldNormalizationSpec(trim=True, collapse_spaces=True)
    return PDPProfile(
        profile_name="generic_brand_guard",
        retailer="generic",
        base_url="https://example.com",
        display_name="Generic Brand Guard",
        category_hints=(),
        category_urls=(),
        parent_rules=ParentRules(
            min_color_variants=2,
            disallow_kits_pattern=None,
            finish_split_tokens=(),
        ),
        id_extractors=IdExtractors(
            parent_from_url_regex=None,
            parent_json_paths=("$.sku", "$.productID"),
            variant_id_fields=("$.id",),
        ),
        blob_sources=(
            BlobSource(
                type="script_jsonld",
                selector="script[type='application/ld+json']",
            ),
        ),
        field_paths=FieldPaths(
            brand=("$.brand.name", "$.brand"),
            parent_title=("$.name",),
            parent_summary=("$.description",),
            series_label=(),
            category_path=(),
            variant_list=(),
            variant_fields={"variant_id": ("$.id",)},
        ),
        normalization=NormalizationConfig(
            brand=normalization,
            shade_name=normalization,
            title=normalization,
        ),
        validation=ValidationRules(
            require_brand=True,
            require_title=True,
            price_must_be_numeric=False,
            reject_if_zero_variants=False,
        ),
    )


def load_fixture(name: str, retailer: str = "ulta") -> str:
    fixture_path = (
        Path(__file__).resolve().parents[3]
        / "tests"
        / "fixtures"
        / "pdp"
        / retailer
        / name
    )
    return fixture_path.read_text(encoding="utf-8")


def test_parser_brand_guard_prefers_product_context_over_weak_brand() -> None:
    parser = PDPParser(
        _minimal_brand_guard_profile(),
        fetcher=None,
        storage=None,
    )
    html = """
    <html>
      <head>
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Ace Monogram Sneakers",
            "brand": {"@type": "Brand", "name": "Akris punto"},
            "sku": "0400020062502",
            "description": "Gucci Ace Monogram Sneakers at Example Store."
          }
        </script>
      </head>
      <body></body>
    </html>
    """

    result = parser.parse_url(
        "https://example.com/product/gucci-ace-monogram-sneakers-0400020062502.html",
        html=html,
    )

    assert result.parent is not None
    assert result.parent.brand_raw == "Gucci"
    assert "brand_guard_context_override" in result.parent.qa_flags


def test_parser_extracts_parent_and_variants() -> None:
    profile = load_profile("ulta_lipstick")
    parser = PDPParser(profile, adapter=UltaAdapter(), fetcher=None, storage=None)

    html = load_fixture("sample_pdp.html")
    result = parser.parse_url(
        "https://www.ulta.com/p/example-lip-color-pimprod123456", html=html
    )

    assert result.parent is not None
    assert result.parent.parent_product_id == "pimprod123456"
    assert result.parent.brand_raw == "Example Brand"
    assert result.parent.title_raw == "Example Brand Matte Lip Color"
    assert result.parent.has_color_selector is True

    assert not result.errors
    assert not result.warnings

    variants = result.variants
    assert len(variants) >= 3

    variant_map = {variant.variant_id: variant for variant in variants}

    first_variant = variant_map["sku101"]
    assert first_variant.variant_id == "sku101"
    assert first_variant.shade_name_normalized == "Classic Red 01"
    assert first_variant.price == Decimal("19.00")
    assert first_variant.barcode == "0001122334455"
    assert (
        first_variant.swatch_image_url == "https://example.com/images/sku101-swatch.jpg"
    )

    third_variant = variant_map["sku103"]
    assert third_variant.variant_id == "sku103"
    assert third_variant.price is None
    assert "price_not_numeric" in third_variant.qa_flags
    assert third_variant.availability == "OutOfStock"

    dom_variant = variant_map.get("sku104")
    assert dom_variant is not None
    assert dom_variant.source_index is not None
    assert variant_map["sku101"].extras["shade_description"] == "Bold red"
    assert "badges" in variant_map["sku101"].extras
    assert variant_map["sku101"].extras["list_price"] == "24.00"
    assert (
        result.parent.extras.get("summary")
        == "Example Brand Matte Lip Color is a synthetic product used to exercise parser behavior."
    )

    details = result.parent.extras.get("details", {})
    assert "description_markdown" in details
    assert details["usage"].startswith("Apply")
    assert details["ingredients"].startswith("Dimethicone")
    assert "features" in details and "Bold color payoff" in details["features"]
    assert result.parent.extras.get("rating") == 4.8
    assert result.parent.extras.get("review_count") == 120
    assert result.parent.extras.get("highlights")


def test_sephora_lipstick_parser() -> None:
    profile = load_profile("sephora_lipstick")
    parser = PDPParser(profile, adapter=SephoraAdapter(), fetcher=None, storage=None)

    html = load_fixture("sample_lipstick.html", retailer="sephora")
    result = parser.parse_url(
        "https://www.sephora.com/product/example-lip-color-P123456?skuId=6020001",
        html=html,
    )

    assert result.errors == ()
    assert result.warnings == ()

    parent = result.parent
    assert parent is not None
    assert parent.parent_product_id == "P123456"
    assert parent.brand_raw == "Example Brand"
    assert parent.title_raw == "Example Brand Satin Lip Color"
    assert parent.has_color_selector is True
    assert parent.category_path == ("Makeup", "Lips", "Lipstick")

    parent_extras = parent.extras
    assert parent_extras.get("rating") == pytest.approx(4.7)
    assert parent_extras.get("review_count") == 248
    assert parent_extras["reviews_positive"]["headline"] == "Love this lipstick"
    assert "Glides on smoothly" in parent_extras["reviews_positive"]["comment"]
    assert parent_extras["reviews_negative"]["headline"] == "Not for me"

    reviews = parent_extras.get("reviews")
    assert isinstance(reviews, list) and len(reviews) == 2
    assert reviews[0]["headline"] == "Amazing formula"
    assert reviews[0]["author"] == "Reviewer One"
    assert reviews[0]["rating"] == 5.0

    details = parent_extras.get("details", {})
    assert details["description_markdown"].startswith("This luxe lipstick delivers")
    assert details["usage"].startswith("Apply directly to lips")
    assert "Dimethicone" in details["ingredients"]
    assert "Longwear" in details["features"]

    variants = result.variants
    assert len(variants) == 3
    variant_map = {variant.variant_id: variant for variant in variants}

    red = variant_map["6020001"]
    assert red.price == Decimal("18.00")
    assert red.currency == "USD"
    assert red.swatch_image_url.endswith("6020001-swatch.jpg")
    assert red.hero_image_url.endswith("6020001-hero.jpg")
    assert red.extras["list_price"] == "21.00"
    assert red.extras["promotion_tags"] == ["Clean"]
    assert red.extras["shade_description"] == "Bold classic red"

    rosewood = variant_map["6020002"]
    assert rosewood.availability == "Limited"
    assert rosewood.price == Decimal("18.00")
    assert rosewood.extras["badges"] == ["Online Only"]

    nude = variant_map["6020003"]
    assert nude.availability == "OutOfStock"
    assert nude.price == Decimal("18.00")
    assert nude.extras["promotion_tags"] == ["Vegan"]
    assert nude.barcode == "000999888777"


def test_sephora_link_store_parser_single_variant() -> None:
    profile = load_profile("sephora_face_primer")
    parser = PDPParser(profile, adapter=SephoraAdapter(), fetcher=None, storage=None)

    html = load_fixture("sample_link_store_single_variant.html", retailer="sephora")
    result = parser.parse_url(
        "https://www.sephora.com/product/example-primer-P441813?skuId=2850402",
        html=html,
    )

    assert result.errors == ()
    assert result.warnings == ()

    parent = result.parent
    assert parent is not None
    assert parent.parent_product_id == "P441813"
    assert parent.brand_raw == "Example Brand"
    assert parent.title_raw == "Example Face Primer"

    variants = result.variants
    assert len(variants) == 1
    assert variants[0].variant_id == "2850402"


def test_sephora_url_fallback_sets_variant_id_to_sku_id() -> None:
    profile = load_profile("sephora_face_primer")
    parser = PDPParser(profile, adapter=SephoraAdapter(), fetcher=None, storage=None)

    html = load_fixture(
        "sample_jsonld_single_variant_missing_sku.html", retailer="sephora"
    )
    result = parser.parse_url(
        "https://www.sephora.com/product/example-primer-P441813?skuId=2850402",
        html=html,
    )

    assert result.errors == ()
    assert result.warnings == ()

    variants = result.variants
    assert len(variants) == 1
    assert variants[0].variant_id == "2850402"


def test_amazon_lipstick_parser() -> None:
    profile = load_profile("amazon_lipstick")
    parser = PDPParser(profile, adapter=AmazonAdapter(), fetcher=None, storage=None)

    html = load_fixture("lipstick_pdp.html", retailer="amazon")
    result = parser.parse_url("https://www.amazon.com/dp/B0AMAZON01", html=html)

    assert result.errors == ()
    assert result.warnings == ()

    parent = result.parent
    assert parent is not None
    assert parent.parent_product_id == "B0AMAZON01"
    assert parent.brand_raw == "Example Brand"
    assert parent.title_raw == "Example Brand Satin Lip Color"
    assert parent.category_path == ("Beauty", "Lips", "Lipstick")

    parent_extras = parent.extras
    assert parent_extras.get("rating") == pytest.approx(4.6)
    assert parent_extras.get("review_count") == 1345
    assert parent_extras.get("summary", "").startswith("Swipe on cushiony")
    details = parent_extras.get("details", {})
    features = details.get("features")
    assert isinstance(features, list) and len(features) == 2
    assert "satin finish" in features[0].lower()
    assert "vitamin e" in features[1].lower()
    assert parent_extras.get("reviews_meta") == {
        "provider": "amazon_pdp_embedded",
        "count": 2,
    }
    reviews = parent_extras.get("reviews")
    assert isinstance(reviews, list)
    assert reviews[0] == {
        "review_id": "R1AMAZONREVIEW",
        "headline": "Soft color, easy to wear",
        "comment": "The color is sheer but visible, and it feels comfortable for hours.",
        "author": "Reviewer One",
        "created_date": "April 5, 2026",
        "rating": 5.0,
        "verified_purchase": True,
        "variant_text": "Color: Crimson Kiss Size: 0.12 oz",
        "asin": "B0AMAZON01",
        "locale": "en-US",
        "source_language": "en-US",
    }
    assert reviews[1]["headline"] == "Nice everyday lipstick"
    assert reviews[1]["rating"] == 4.0

    variants = result.variants
    assert len(variants) == 3
    variant_map = {variant.variant_id: variant for variant in variants}
    assert set(variant_map) == {"B0AMZNCRIM", "B0AMZNNDE", "B0AMZNCOPA"}

    crimson = variant_map["B0AMZNCRIM"]
    assert crimson.shade_name_normalized == "Crimson Kiss"
    assert crimson.price == Decimal("12.99")
    assert crimson.price_raw == "12.99"
    assert crimson.currency == "USD"
    assert crimson.size_text_raw == "0.12 oz"
    assert crimson.availability == "InStock"
    assert crimson.hero_image_url.endswith("B0AMZNCRIM-hero.jpg")
    assert crimson.swatch_image_url.endswith("B0AMZNCRIM-swatch.jpg")
    assert crimson.extras.get("badges") == ["Vegan"]
    assert crimson.extras.get("promotion_tags") == ["Prime"]

    rose = variant_map["B0AMZNNDE"]
    assert rose.price == Decimal("11.99")
    assert rose.availability == "Limited"
    assert rose.hero_image_url.endswith("B0AMZNNDE-hero.jpg")
    assert rose.swatch_image_url.endswith("B0AMZNNDE-swatch.jpg")

    copper = variant_map["B0AMZNCOPA"]
    assert copper.price == Decimal("16.99")
    assert copper.extras.get("list_price") == "16.99"
    assert copper.availability == "OutOfStock"
    assert copper.swatch_image_url.endswith("B0AMZNCOPA-swatch.jpg")


def test_amazon_wet_cat_food_profile_resolves_category() -> None:
    profile = load_profile("amazon_wet_cat_food")

    assert profile.retailer == "amazon"
    assert profile.category_urls == ("https://www.amazon.com/s?k=wet+cat+food&i=pets",)
    assert profile.validation.reject_if_zero_variants is False


def test_amazon_blush_parser_extracts_sorted_dimensions_script_body() -> None:
    profile = load_profile("amazon_blush")
    parser = PDPParser(profile, adapter=AmazonAdapter(), fetcher=None, storage=None)

    html = load_fixture("blush_sorted_dims_pdp.html", retailer="amazon")
    result = parser.parse_url("https://www.amazon.com/dp/B0TEST0001", html=html)

    assert result.errors == ()
    assert result.warnings == ()

    parent = result.parent
    assert parent is not None
    assert parent.parent_product_id == "B0TEST0001"
    assert parent.title_raw == "Example Brand Soft Blush"
    assert parent.brand_raw == "Example Brand"

    variants = result.variants
    assert len(variants) == 2
    variant_map = {variant.variant_id: variant for variant in variants}
    assert set(variant_map) == {"B0TEST0001", "B0TEST0002"}

    warm = variant_map["B0TEST0001"]
    assert warm.shade_name_raw == "Warm Rose"
    assert warm.size_text_raw == "0.2 Ounce (Pack of 1)"
    assert warm.availability == "InStock"
    assert warm.hero_image_url == "https://example.com/images/warm-rose.jpg"

    cool = variant_map["B0TEST0002"]
    assert cool.shade_name_raw == "Cool Pink"
    assert cool.availability == "InStock"
    assert cool.hero_image_url == "https://example.com/images/cool-pink.jpg"


def test_amazon_parent_asin_overrides_url_parent_and_variant_parent_ids() -> None:
    profile = load_profile("amazon_blush")
    parser = PDPParser(profile, adapter=AmazonAdapter(), fetcher=None, storage=None)

    html = """
    <html>
      <body>
        <script type="a-state">
          {
            "parentAsin": "B0PARENT00",
            "title": "Example Brand Soft Blush",
            "brand": "Example Brand",
            "dimensionValuesDisplayData": {
              "color_name": {
                "B0VAR00001": "Warm Rose",
                "B0VAR00002": "Cool Pink"
              }
            },
            "asinMetadata": {
              "B0VAR00001": {
                "variationValues": {"color_name": "Warm Rose"},
                "price": "12.99",
                "currency": "USD"
              },
              "B0VAR00002": {
                "variationValues": {"color_name": "Cool Pink"},
                "price": "13.99",
                "currency": "USD"
              }
            }
          }
        </script>
      </body>
    </html>
    """

    result = parser.parse_url("https://www.amazon.com/dp/B0VAR00001", html=html)

    assert result.errors == ()
    assert result.warnings == ()
    assert result.parent is not None
    assert result.parent.parent_product_id == "B0PARENT00"
    assert result.parent.extras.get("parent_asin") == "B0PARENT00"
    assert result.parent.extras.get("source_parent_id_from_url") == "B0VAR00001"
    assert len(result.variants) == 2
    assert {variant.parent_product_id for variant in result.variants} == {"B0PARENT00"}


def test_amazon_blush_parser_creates_single_variant_fallback_without_twister() -> None:
    profile = load_profile("amazon_blush")
    parser = PDPParser(profile, adapter=AmazonAdapter(), fetcher=None, storage=None)

    html = """
    <html>
      <body>
        <span id="productTitle">Fallback Blush</span>
        <a id="bylineInfo">Brand: Fallback Brand</a>
        <img id="landingImage" src="https://m.media-amazon.com/images/I/fallback-hero.jpg" />
      </body>
    </html>
    """
    result = parser.parse_url("https://www.amazon.com/dp/B0FBACK001", html=html)

    assert result.errors == ()
    assert result.warnings == ()
    assert result.parent is not None
    assert result.parent.brand_raw == "Fallback Brand"
    assert result.parent.title_raw == "Fallback Blush"
    assert len(result.variants) == 1
    assert result.variants[0].variant_id == "B0FBACK001"
    assert (
        result.variants[0].hero_image_url
        == "https://m.media-amazon.com/images/I/fallback-hero.jpg"
    )


def test_foundation_profile() -> None:
    profile = load_profile("ulta_foundation")
    parser = PDPParser(profile, adapter=UltaAdapter(), fetcher=None, storage=None)

    html = load_fixture("foundation_pdp.html")
    result = parser.parse_url(
        "https://www.ulta.com/p/example-soft-matte-foundation-pimprod7891011",
        html=html,
    )

    assert result.parent is not None
    assert result.parent.parent_product_id == "pimprod7891011"
    assert result.parent.brand_raw == "Example Brand"
    assert result.parent.title_raw == "Example Brand Soft Matte Foundation"

    variants = result.variants
    assert len(variants) >= 4

    variant_map = {variant.variant_id: variant for variant in variants}
    assert variant_map["foundation150"].price == Decimal("39.00")
    assert (
        variant_map["foundation150"]
        .extras["shade_description"]
        .startswith("For light skin")
    )
    assert variant_map["foundation150"].extras["badges"] == ["Best Seller"]

    foundation445 = variant_map["foundation445"]
    assert foundation445.availability == "OutOfStock"
    assert foundation445.extras["list_price"] == "42.00"

    parent_extras = result.parent.extras
    assert parent_extras.get("rating") == 4.6
    assert parent_extras.get("review_count") == 8200
    assert (
        parent_extras.get("summary")
        == "A synthetic soft matte foundation that builds medium-to-full coverage."
    )

    details = parent_extras.get("details", {})
    assert details.get("usage", "").startswith("Shake before use")
    assert details.get("ingredients", "").startswith("Water")
    assert "Soft matte finish" in details.get("features", [])

    highlights = parent_extras.get("highlights", [])
    highlight_labels = {entry.get("label") for entry in highlights}
    assert {"Longwear", "Oil Free"}.issubset(highlight_labels)

    summary_cards = parent_extras.get("summary_cards", [])
    assert summary_cards
    coverage_card = summary_cards[0]
    assert coverage_card.get("title") == "Coverage"
    assert any("Medium to Full" in item for item in coverage_card.get("items", []))


def test_bronzer_reviews_capture() -> None:
    profile = load_profile("ulta_bronzer")
    parser = PDPParser(profile, adapter=UltaAdapter(), fetcher=None, storage=None)

    html = load_fixture("sample_bronzer.html")
    result = parser.parse_url(
        "https://www.ulta.com/p/example-matte-bronzer-pimprod2043364",
        html=html,
    )

    parent = result.parent
    assert parent is not None
    reviews_meta = parent.extras.get("reviews_meta")
    assert reviews_meta["provider"] == "powerreviews"
    assert reviews_meta["merchant_group_id"] == "test-group"
    assert reviews_meta["merchant_id"] == "test-merchant"
    assert "api_key" not in reviews_meta

    positive = parent.extras.get("reviews_positive")
    assert positive == {
        "headline": "Easy to blend",
        "comment": "The powder blends evenly and wears well.",
    }

    negative = parent.extras.get("reviews_negative")
    assert negative == {
        "headline": "Shade was not right",
        "comment": "The undertone did not suit this reviewer.",
    }

    reviews = parent.extras.get("reviews")
    assert isinstance(reviews, list) and reviews
    first_review = reviews[0]
    assert first_review["headline"] == "Useful formula feedback"
    assert first_review["author"] == "Reviewer One"
    assert first_review["rating"] == 3.0
