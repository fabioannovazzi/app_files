from __future__ import annotations

import html
import json
import re
import datetime as dt
from collections.abc import Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup  # type: ignore[import]

from .models import FetchResult

__all__ = [
    "PURINA_API_BASE_URL",
    "PURINA_BASE_URL",
    "PURINA_BRAND_NAME",
    "PURINA_CATEGORY_KEY",
    "PURINA_RETAILER",
    "PURINA_SEARCH_API_URL",
    "PURINA_WET_CAT_FOOD_URL",
    "fetch_purina_products_for_api_url",
    "fetch_purina_wet_cat_food_products",
    "purina_brand_from_product",
    "purina_category_path",
    "purina_fetch_result_from_api_product",
    "purina_image_url",
    "purina_lifestage_from_text",
    "purina_parent_id_from_url",
    "purina_product_text",
    "purina_product_url",
    "purina_semantic_attribute_hints",
    "purina_synthetic_product_html",
    "purina_variant_payloads",
    "purina_variant_size_text",
]

PURINA_BASE_URL = "https://www.purina.com"
PURINA_API_BASE_URL = "https://live.purina.com"
PURINA_SEARCH_API_URL = f"{PURINA_API_BASE_URL}/api/search/products"
PURINA_BRAND_NAME = "Purina"
PURINA_RETAILER = "purina"
PURINA_CATEGORY_KEY = "wet_cat_food"
PURINA_WET_CAT_FOOD_URL = f"{PURINA_BASE_URL}/cats/cat-food/wet"
PURINA_API_SPECIES_ID = "1120"
PURINA_API_CATEGORY_ID = "24"
PURINA_SEARCH_ITEMS_PER_PAGE = 50

PURINA_REQUEST_HEADERS: Mapping[str, str] = {
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147 Safari/537.36"
    ),
}

_PRODUCT_PATH_RE = re.compile(
    r"(?:^|/)cats/shop/(?P<slug>[a-z0-9][a-z0-9-]*)(?:$|[/?#])",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")
_COUNT_RE = re.compile(
    r"\b(?P<count>\d+)\s*(?:ct|count|pack|cans?)\b",
    re.IGNORECASE,
)
_PACKAGING_RE = re.compile(
    r"\b(?:can|cup|pouch|tray|tub|box|bag)\b",
    re.IGNORECASE,
)
_UNIT_LABELS = {
    "count": "ct",
    "ounce(s)": "oz",
    "ounces": "oz",
    "oz": "oz",
}
_BRAND_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Purina Pro Plan Veterinary Diets",
        ("purina pro plan veterinary diets", "pro plan veterinary diets"),
    ),
    ("Purina Pro Plan", ("purina pro plan", "pro plan")),
    ("Purina ONE", ("purina one",)),
    ("Fancy Feast", ("fancy feast",)),
    ("Friskies", ("friskies",)),
)
_PROTEIN_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Chicken", ("chicken",)),
    ("Turkey", ("turkey",)),
    ("Tuna", ("tuna",)),
    ("Salmon", ("salmon",)),
    ("Ocean Whitefish", ("ocean whitefish", "whitefish")),
    ("Ocean Fish", ("ocean fish",)),
    ("Fish", ("fish",)),
    ("Seafood", ("seafood",)),
    ("Beef", ("beef",)),
    ("Liver", ("liver",)),
    ("Duck", ("duck",)),
    ("Pork", ("pork",)),
    ("Shrimp", ("shrimp",)),
    ("Cod", ("cod",)),
    ("Sole", ("sole",)),
    ("Arctic Char", ("arctic char",)),
    ("Mackerel", ("mackerel",)),
    ("Sardines", ("sardine", "sardines")),
    ("Giblets", ("giblet", "giblets")),
)
_SPECIAL_DIET_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Grain-Free", ("grain free", "grain-free")),
    ("High-Protein", ("high protein", "high-protein")),
    ("Low Calorie", ("low calorie", "low-calorie")),
    ("Low Protein", ("low protein", "low-protein")),
    ("Natural", ("natural",)),
    ("No Artificial Flavors or Preservatives", ("no artificial", "preservatives")),
    ("No Corn No Wheat No Soy", ("no corn", "no wheat", "no soy")),
    ("Prebiotics", ("prebiotic", "prebiotics")),
    ("Probiotics", ("probiotic", "probiotics")),
)
_HEALTH_FEATURE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Urinary Tract Health", ("urinary tract", "urinary")),
    ("Hairball Control", ("hairball",)),
    ("Digestive Health", ("digestive", "digestion", "gastroenteric")),
    ("Sensitive Digestion", ("sensitive", "sensitive system")),
    ("Skin & Coat Health", ("skin", "coat")),
    ("Weight Management", ("weight management", "healthy metabolism")),
    ("Immune Support", ("immune",)),
    ("Cognitive Health Support", ("cognitive",)),
    ("Dental Care", ("dental",)),
    ("Indoor", ("indoor",)),
    ("Critical Nutrition", ("critical nutrition",)),
    ("Dietetic Management", ("dietetic management",)),
)


def _clean_text(value: object | None) -> str:
    text = html.unescape(str(value or ""))
    return _WHITESPACE_RE.sub(" ", text).strip()


def _normalize_text(value: object | None) -> str:
    return _clean_text(value).casefold()


def _strip_html(value: object | None) -> str:
    soup = BeautifulSoup(str(value or ""), "lxml")
    return _clean_text(soup.get_text(" ", strip=True))


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _format_number(value: object | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        return text
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:g}"


def _slug(value: object | None) -> str:
    text = _normalize_text(value)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "default"


def purina_parent_id_from_url(url: str) -> str | None:
    """Extract the Purina `/cats/shop/{slug}` parent id from a PDP URL."""

    parsed = urlparse(str(url or ""))
    match = _PRODUCT_PATH_RE.search(parsed.path.rstrip("/") + "/")
    if not match:
        return None
    return match.group("slug").strip().lower() or None


def purina_product_url(parent_id: str, fallback_url: str | None = None) -> str:
    """Return the canonical Purina US PDP URL for a parent id."""

    if fallback_url and purina_parent_id_from_url(fallback_url):
        parsed = urlparse(fallback_url)
        return urlunparse(
            parsed._replace(
                scheme="https", netloc="www.purina.com", query="", fragment=""
            )
        )
    slug = str(parent_id or "").strip().strip("/").lower()
    return urljoin(PURINA_BASE_URL, f"/cats/shop/{slug}")


def purina_image_url(value: object | None) -> str | None:
    """Return a downloadable Purina image URL, preferring the live asset host."""

    text = _clean_text(value)
    if not text:
        return None
    if text.startswith("//"):
        text = f"https:{text}"
    if text.startswith("/"):
        return urljoin(PURINA_API_BASE_URL, text)
    parsed = urlparse(text)
    if parsed.netloc == "www.purina.com":
        return urlunparse(parsed._replace(netloc="live.purina.com"))
    return text


def purina_product_text(product: Mapping[str, object]) -> str:
    """Return text fields from one Purina product API row."""

    variation_text: list[str] = []
    raw_variations = product.get("product_variations")
    if _is_sequence(raw_variations):
        for variation in raw_variations:
            if not isinstance(variation, Mapping):
                continue
            variation_text.extend(
                _clean_text(variation.get(key))
                for key in ("short_description", "item_description", "item_size")
                if _clean_text(variation.get(key))
            )
    parts = [
        _clean_text(product.get("title")),
        _strip_html(product.get("description")),
        " ".join(variation_text),
    ]
    return _clean_text(" ".join(part for part in parts if part))


def _site_filter_values(
    site_filters: Sequence[Mapping[str, object]] | None,
    family: str,
) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for item in site_filters or ():
        if _normalize_text(item.get("filter_family")).replace(" ", "_") != family:
            continue
        value = _clean_text(item.get("filter_value"))
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            values.append(value)
    return values


def purina_brand_from_product(product: Mapping[str, object]) -> str:
    """Return the official Purina sub-brand for one product when available."""

    raw_filters = product.get("site_filters")
    if _is_sequence(raw_filters):
        brand_values = _site_filter_values(  # type: ignore[arg-type]
            [item for item in raw_filters if isinstance(item, Mapping)],
            "brand",
        )
        if brand_values:
            return brand_values[0]
    text = _normalize_text(product.get("title"))
    for label, needles in _BRAND_RULES:
        if any(needle in text for needle in needles):
            return label
    return PURINA_BRAND_NAME


def purina_lifestage_from_text(text: object | None) -> str:
    """Return a broad lifestage label from Purina product copy."""

    normalized = _normalize_text(text)
    if "all life stages" in normalized:
        return "All Life Stages"
    if "kitten" in normalized:
        return "Kitten"
    if "senior" in normalized or re.search(r"\b(?:7\+|11\+)\b", normalized):
        return "Senior"
    return "Adult"


def purina_category_path(
    product: Mapping[str, object],
    *,
    site_filters: Sequence[Mapping[str, object]] | None = None,
) -> tuple[str, ...]:
    """Return the normalized category path stored on parsed Purina products."""

    filters = list(site_filters or ())
    path = ["Pet", "Cat", "Wet Cat Food"]
    brand = purina_brand_from_product({**dict(product), "site_filters": filters})
    if brand and brand not in path:
        path.append(brand)
    for value in _site_filter_values(filters, "food_texture")[:1]:
        if value and value not in path:
            path.append(value)
    return tuple(path)


def _values_from_rules(
    text: str,
    rules: Sequence[tuple[str, Sequence[str]]],
) -> list[str]:
    normalized = _normalize_text(text)
    values: list[str] = []
    seen: set[str] = set()
    for label, needles in rules:
        if any(needle in normalized for needle in needles):
            key = label.casefold()
            if key not in seen:
                seen.add(key)
                values.append(label)
    return values


def _packaging_types_from_text(text: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for match in _PACKAGING_RE.finditer(text):
        value = match.group(0).title()
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        values.append(value)
    return values


def _package_count_from_text(text: str) -> str | None:
    match = _COUNT_RE.search(text)
    if not match:
        return None
    count = int(match.group("count"))
    if count <= 6:
        return "6 count or less"
    if count <= 12:
        return "7-12 count"
    if count <= 24:
        return "13-24 count"
    return "25 count & above"


def purina_semantic_attribute_hints(
    product: Mapping[str, object],
    *,
    site_filters: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, list[str]]:
    """Return deterministic wet-cat-food taxonomy hints from Purina API data."""

    filters = list(site_filters or ())
    text = " ".join(
        [
            purina_product_text(product),
            " ".join(
                _clean_text(item.get("filter_value"))
                for item in filters
                if isinstance(item, Mapping)
            ),
        ]
    )
    brand = purina_brand_from_product({**dict(product), "site_filters": filters})
    prescription = (
        "prescription"
        if "veterinary diets" in _normalize_text(" ".join([brand, text]))
        else "non-prescription"
    )
    hints: dict[str, list[str]] = {
        "brand": [brand],
        "prescription_status": [prescription],
    }
    family_to_attribute = {
        "animal_protein_source": "animal_protein_source",
        "flavor": "flavor",
        "food_texture": "food_texture",
        "health_feature": "health_feature",
        "lifestage": "lifestage",
        "product_assortment": "product_assortment",
        "special_diet": "special_diet",
    }
    for family, attribute in family_to_attribute.items():
        values = _site_filter_values(filters, family)
        if values:
            hints[attribute] = values

    if "lifestage" not in hints:
        hints["lifestage"] = [purina_lifestage_from_text(text)]
    if "product_assortment" not in hints:
        product_type = _clean_text(product.get("type")).casefold()
        if "bundle" in product_type or "variety" in _normalize_text(text):
            hints["product_assortment"] = ["Variety Pack"]
        else:
            hints["product_assortment"] = ["Single Recipe"]
    if "animal_protein_source" not in hints:
        proteins = _values_from_rules(text, _PROTEIN_RULES)
        if proteins:
            hints["animal_protein_source"] = proteins
    if "flavor" not in hints and "animal_protein_source" in hints:
        hints["flavor"] = hints["animal_protein_source"][:]
    if "special_diet" not in hints:
        special_diets = _values_from_rules(text, _SPECIAL_DIET_RULES)
        if special_diets:
            hints["special_diet"] = special_diets
    if "health_feature" not in hints:
        health_features = _values_from_rules(text, _HEALTH_FEATURE_RULES)
        if health_features:
            hints["health_feature"] = health_features
    packaging = _packaging_types_from_text(text)
    if packaging:
        hints["packaging_type"] = packaging[:1]
    package_count = _package_count_from_text(text)
    if package_count:
        hints["package_count"] = [package_count]
    return {key: values for key, values in hints.items() if values}


def purina_variant_size_text(variation: Mapping[str, object]) -> str | None:
    """Return normalized size text from a Purina API variation payload."""

    short_description = _clean_text(variation.get("short_description"))
    if short_description:
        return short_description
    size = _format_number(variation.get("item_size"))
    if not size:
        return None
    unit = _normalize_text(variation.get("item_description"))
    label = _UNIT_LABELS.get(unit, unit.replace("(s)", "s"))
    if label:
        return f"{size} {label}"
    return size


def purina_variant_payloads(product: Mapping[str, object]) -> list[dict[str, object]]:
    """Build generic parser variant payloads from Purina API variations."""

    parent_id = purina_parent_id_from_url(str(product.get("url") or ""))
    if not parent_id:
        parent_id = _slug(product.get("title"))
    title = _clean_text(product.get("title")) or parent_id.replace("-", " ").title()
    hero_image_url = purina_image_url(product.get("product_image"))
    raw_variations = product.get("product_variations")
    variations = (
        [item for item in raw_variations if isinstance(item, Mapping)]
        if _is_sequence(raw_variations)
        else []
    )
    if not variations:
        variations = [{"short_description": None, "upc_code": product.get("upc")}]

    payloads: list[dict[str, object]] = []
    for index, variation in enumerate(variations, start=1):
        size_text = purina_variant_size_text(variation)
        barcode = _clean_text(variation.get("upc_code")) or _clean_text(
            product.get("upc")
        )
        variant_id = barcode or (
            parent_id if len(variations) == 1 else f"{parent_id}--{index}"
        )
        payloads.append(
            {
                "id": variant_id,
                "sku": variant_id,
                "name": title,
                "size": size_text,
                "barcode": barcode,
                "availability": "in_stock",
                "image": hero_image_url,
                "attributes": {
                    "size": size_text,
                    "item_description": variation.get("item_description"),
                    "item_quantity": variation.get("item_quantity"),
                    "item_size": variation.get("item_size"),
                },
            }
        )
    return payloads


def _synthetic_script_json(product: Mapping[str, object]) -> str:
    return json.dumps(dict(product), ensure_ascii=False, sort_keys=True).replace(
        "</", "<\\/"
    )


def purina_synthetic_product_html(product: Mapping[str, object]) -> str:
    """Return a small HTML document containing official Purina API product data."""

    parent_id = purina_parent_id_from_url(str(product.get("url") or "")) or _slug(
        product.get("title")
    )
    product_url = purina_product_url(parent_id, str(product.get("url") or ""))
    title = _clean_text(product.get("title")) or parent_id.replace("-", " ").title()
    brand = purina_brand_from_product(product)
    description = _strip_html(product.get("description"))
    script_json = _synthetic_script_json(product)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <link rel="canonical" href="{html.escape(product_url, quote=True)}">
    <script id="purina-api-product" type="application/json">{script_json}</script>
  </head>
  <body>
    <main>
      <h1>{html.escape(title)}</h1>
      <p>By {html.escape(brand)}</p>
      <section>{html.escape(description)}</section>
    </main>
  </body>
</html>
"""


def _search_params(
    *,
    page: int,
    items_per_page: int = PURINA_SEARCH_ITEMS_PER_PAGE,
    sort_by: str = "relevance",
) -> dict[str, str]:
    return {
        "category": PURINA_API_CATEGORY_ID,
        "items_per_page": str(items_per_page),
        "page": str(max(0, page)),
        "sort_by": sort_by,
        "species": PURINA_API_SPECIES_ID,
    }


def _api_url_with_page(
    api_url: str,
    *,
    page: int,
    items_per_page: int = PURINA_SEARCH_ITEMS_PER_PAGE,
) -> str:
    parsed = urlparse(api_url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params["items_per_page"] = str(items_per_page)
    params["page"] = str(max(0, page))
    return urlunparse(parsed._replace(query=urlencode(params)))


def _fetch_search_payload(
    session: requests.Session,
    *,
    url: str | None = None,
    params: Mapping[str, str] | None = None,
    timeout: float | tuple[float, float] = 30.0,
) -> Mapping[str, object]:
    response = session.get(
        url or PURINA_SEARCH_API_URL,
        params=params,
        headers=dict(PURINA_REQUEST_HEADERS),
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, Mapping):
        raise RuntimeError("Purina product search API did not return an object.")
    return payload


def _products_from_payload(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw_results = payload.get("search_results")
    if not _is_sequence(raw_results):
        return []
    return [item for item in raw_results if isinstance(item, Mapping)]


def fetch_purina_products_for_api_url(
    session: requests.Session,
    api_url: str,
    *,
    timeout: float | tuple[float, float] = 30.0,
    items_per_page: int = PURINA_SEARCH_ITEMS_PER_PAGE,
) -> list[Mapping[str, object]]:
    """Fetch every product row returned by one Purina product-search API URL."""

    rows: list[Mapping[str, object]] = []
    page = 0
    while True:
        payload = _fetch_search_payload(
            session,
            url=_api_url_with_page(api_url, page=page, items_per_page=items_per_page),
            timeout=timeout,
        )
        products = _products_from_payload(payload)
        rows.extend(products)
        pager = payload.get("pager")
        total_pages = 1
        current_page = page
        if isinstance(pager, Mapping):
            try:
                total_pages = int(pager.get("total_pages") or 1)
                current_page = int(pager.get("current_page") or page)
            except (TypeError, ValueError):
                total_pages = 1
        if not products or current_page >= total_pages - 1:
            break
        page = current_page + 1
    return rows


def fetch_purina_wet_cat_food_products(
    session: requests.Session,
    *,
    timeout: float | tuple[float, float] = 30.0,
    items_per_page: int = PURINA_SEARCH_ITEMS_PER_PAGE,
) -> tuple[list[Mapping[str, object]], Mapping[str, object]]:
    """Fetch all official Purina US wet-cat-food products and the first payload."""

    first_payload = _fetch_search_payload(
        session,
        params=_search_params(page=0, items_per_page=items_per_page),
        timeout=timeout,
    )
    rows: list[Mapping[str, object]] = []
    seen: set[str] = set()

    def add_page(payload: Mapping[str, object], page_index: int) -> None:
        for position, item in enumerate(_products_from_payload(payload), start=1):
            parent_id = purina_parent_id_from_url(str(item.get("url") or ""))
            if not parent_id or parent_id in seen:
                continue
            seen.add(parent_id)
            row = dict(item)
            row["_listing_page"] = page_index + 1
            row["_listing_position"] = position
            rows.append(row)

    add_page(first_payload, 0)
    pager = first_payload.get("pager")
    total_pages = 1
    if isinstance(pager, Mapping):
        try:
            total_pages = int(pager.get("total_pages") or 1)
        except (TypeError, ValueError):
            total_pages = 1
    for page in range(1, total_pages):
        payload = _fetch_search_payload(
            session,
            params=_search_params(page=page, items_per_page=items_per_page),
            timeout=timeout,
        )
        add_page(payload, page)
    return rows, first_payload


def purina_fetch_result_from_api_product(
    product: Mapping[str, object],
    *,
    requested_url: str | None = None,
) -> FetchResult:
    """Build a FetchResult from official Purina API data for parser use."""

    parent_id = purina_parent_id_from_url(
        str(requested_url or product.get("url") or "")
    ) or _slug(product.get("title"))
    return FetchResult(
        url=purina_product_url(
            parent_id, requested_url or str(product.get("url") or "")
        ),
        status_code=200,
        headers={"content-type": "text/html; source=purina-api"},
        html=purina_synthetic_product_html(product),
        fetched_at=dt.datetime.now(dt.timezone.utc),
    )
