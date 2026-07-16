from __future__ import annotations

from modules.pdp.adapters.saksfifthavenue import SaksfifthavenueAdapter
from modules.pdp.engine import PDPParser
from modules.pdp.profile_loader import load_profile

HTML = """
<html>
  <head>
    <title>Miu Miu Tyre Low-Top Sneakers | Saks Fifth Avenue</title>
    <meta property="og:url" content="https://www.saksfifthavenue.com/product/miu-miu-tyre-low-top-sneakers-0400022953591.html" />
    <meta property="og:image" content="https://image.saks.com/is/image/saks/0400022953591_BEIGE" />
    <meta name="description" content="These Tyre sneakers from Miu Miu are designed in mixed nylon and leather." />
    <meta property="product:brand" content="Miu Miu" />
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Tyre Low-Top Sneakers",
        "brand": {"@type": "Brand", "name": "Miu Miu"},
        "sku": "0400022953591",
        "image": [
          "https://image.saks.com/is/image/saks/0400022953591_BEIGE",
          "https://image.saks.com/is/image/saks/0400022953591_GREY"
        ],
        "offers": {"@type": "Offer", "price": "1170", "priceCurrency": "USD"}
      }
    </script>
  </head>
  <body>
    <nav aria-label="breadcrumb">
      <a href="/c/shoes">Shoes</a>
      <a href="/c/shoes/shoes/sneakers">Sneakers</a>
      <a href="/c/shoes/shoes/sneakers/low-tops">Low-Tops</a>
    </nav>
    <span>BEST SELLER</span>
    <a href="/brand/miu-miu">Miu Miu</a>
    <h1>Tyre Low-Top Sneakers</h1>
    <div>
      <h2>Color</h2>
      <button class="color-option" data-color-name="Beige">BEIGE</button>
      <button class="color-option" data-color-name="Grey">GREY</button>
    </div>
    <section id="product-details">
      <h2>Details</h2>
      <p>These Tyre sneakers from Miu Miu are designed in mixed nylon and leather.</p>
      <ul>
        <li>Round toe</li>
        <li>Lace-up style</li>
        <li>Fabric/leather lining</li>
        <li>EVA/rubber sole</li>
        <li>Imported</li>
      </ul>
      <p>Please Note: This style runs large.</p>
      <p>Style Code: 0400022953591</p>
    </section>
  </body>
</html>
"""


def test_saksfifthavenue_parser_extracts_parent_variants_and_details() -> None:
    profile = load_profile("saksfifthavenue_low_top_sneakers")
    parser = PDPParser(
        profile=profile,
        adapter=SaksfifthavenueAdapter(),
        fetcher=None,
    )

    result = parser.parse_url(
        "https://www.saksfifthavenue.com/product/miu-miu-tyre-low-top-sneakers-0400022953591.html",
        html=HTML,
    )

    assert result.errors == ()
    assert result.parent is not None
    assert result.parent.parent_product_id == "0400022953591"
    assert result.parent.brand_raw == "Miu Miu"
    assert result.parent.title_raw == "Tyre Low-Top Sneakers"
    assert result.parent.category_path == ("Shoes", "Sneakers", "Low-Tops")
    assert result.parent.has_color_selector is True
    assert (
        result.parent.extras["hero_image_url"]
        == "https://image.saks.com/is/image/saks/0400022953591_BEIGE"
    )
    assert result.parent.extras["gallery_images"] == [
        "https://image.saks.com/is/image/saks/0400022953591_BEIGE",
        "https://image.saks.com/is/image/saks/0400022953591_GREY",
    ]
    assert result.parent.extras["style_code"] == "0400022953591"
    assert result.parent.extras["badges"] == ["BEST SELLER"]

    details = result.parent.extras["details"]
    assert "mixed nylon and leather" in details["description_markdown"]
    assert "Round toe" in details["features"]
    assert "Lace-up style" in details["features"]
    assert details["fit_notes"] == ["Please Note: This style runs large."]

    assert len(result.variants) == 2
    variant_map = {variant.shade_name_raw: variant for variant in result.variants}
    assert sorted(variant_map) == ["Beige", "Grey"]
    assert variant_map["Beige"].variant_id == "0400022953591-beige"
    assert variant_map["Beige"].price_raw == "1170"
    assert variant_map["Beige"].currency == "USD"


def test_saksfifthavenue_parser_rejects_unrelated_brand_candidate() -> None:
    html = """
    <html>
      <head>
        <title>Gucci Ace Monogram Sneakers | Saks Fifth Avenue</title>
        <meta property="og:url" content="https://www.saksfifthavenue.com/product/gucci-ace-monogram-sneakers-0400020062502.html" />
        <meta name="description" content="Gucci Ace Monogram Sneakers at Saks Fifth Avenue. Browse luxury Gucci Low-Tops and other new arrivals." />
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Ace Monogram Sneakers",
            "brand": {"@type": "Brand", "name": "Akris punto"},
            "sku": "0400020062502",
            "image": ["https://image.saks.com/is/image/saks/0400020062502"],
            "offers": {"@type": "Offer", "price": "300", "priceCurrency": "USD"}
          }
        </script>
      </head>
      <body>
        <a href="/brand/akris-punto">Akris punto</a>
        <h1>Ace Monogram Sneakers</h1>
        <section id="product-details">
          <h2>Details</h2>
          <p>Gucci Ace Monogram Sneakers at Saks Fifth Avenue.</p>
          <p>Style Code: 0400020062502</p>
        </section>
      </body>
    </html>
    """
    profile = load_profile("saksfifthavenue_low_top_sneakers")
    parser = PDPParser(
        profile=profile,
        adapter=SaksfifthavenueAdapter(),
        fetcher=None,
    )

    result = parser.parse_url(
        "https://www.saksfifthavenue.com/product/gucci-ace-monogram-sneakers-0400020062502.html",
        html=html,
    )

    assert result.errors == ()
    assert result.parent is not None
    assert result.parent.brand_raw == "Gucci"
    assert "Akris" not in result.parent.brand_raw


def test_saksfifthavenue_parser_ignores_waitlist_marketing_text_as_color() -> None:
    html = """
    <html>
      <head>
        <title>Cashmere Sweater | Saks Fifth Avenue</title>
        <meta property="og:url" content="https://www.saksfifthavenue.com/product/cashmere-sweater-0400026472358.html" />
        <meta property="og:image" content="https://image.saks.com/is/image/saks/0400026472358_CAMEL" />
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Cashmere Sweater",
            "brand": {"@type": "Brand", "name": "Theory"},
            "sku": "0400026472358",
            "image": ["https://image.saks.com/is/image/saks/0400026472358_CAMEL"],
            "offers": {"@type": "Offer", "price": "395", "priceCurrency": "USD"}
          }
        </script>
      </head>
      <body>
        <h1>Cashmere Sweater</h1>
        <button aria-label="By voluntarily opting in to Saks Fifth Avenue waitlist text alerts and or waitlist email alerts, in addition to hearing about your waitlist item, you agree that you voluntarily withdraw any past opt-outs of promotional marketing and you agree to receive marketing emails.">
          Notify me
        </button>
      </body>
    </html>
    """
    profile = load_profile("saksfifthavenue_cashmere_sweaters")
    parser = PDPParser(
        profile=profile,
        adapter=SaksfifthavenueAdapter(),
        fetcher=None,
    )

    result = parser.parse_url(
        "https://www.saksfifthavenue.com/product/cashmere-sweater-0400026472358.html",
        html=html,
    )

    assert result.errors == ()
    assert len(result.variants) == 1
    assert result.variants[0].variant_id == "0400026472358-default"
