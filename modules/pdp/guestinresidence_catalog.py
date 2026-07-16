from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup  # type: ignore[import]

__all__ = [
    "GUESTINRESIDENCE_BASE_URL",
    "GUESTINRESIDENCE_BRAND_NAME",
    "GUESTINRESIDENCE_CATEGORY_KEY",
    "GUESTINRESIDENCE_COLLECTION_PATHS",
    "GUESTINRESIDENCE_RETAILER",
    "guestinresidence_cashmere_scope_decision",
    "guestinresidence_category_from_url",
    "guestinresidence_category_path",
    "guestinresidence_color_families",
    "guestinresidence_feature_lines",
    "guestinresidence_parent_id_from_url",
    "guestinresidence_product_handle_from_url",
    "guestinresidence_product_option_values",
    "guestinresidence_product_text",
    "guestinresidence_product_url",
    "guestinresidence_semantic_attribute_hints",
]

GUESTINRESIDENCE_BASE_URL = "https://guestinresidence.com"
GUESTINRESIDENCE_BRAND_NAME = "Guest in Residence"
GUESTINRESIDENCE_RETAILER = "guestinresidence"
GUESTINRESIDENCE_CATEGORY_KEY = "cashmere_sweaters"
GUESTINRESIDENCE_COLLECTION_PATHS: Mapping[str, str] = {
    "womens_sweaters": "/collections/womens-sweaters",
    "womens_cardigans_jackets": "/collections/womens-cardigans-jackets",
    "100_cashmere": "/collections/100-cashmere",
}

_PRODUCT_PATH_RE = re.compile(
    r"(?:^|/)products/(?P<handle>[a-z0-9][a-z0-9-]*)(?:$|[/?#])",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")
_EXCLUDED_PRODUCT_TYPES = {
    "ACCESSORY",
    "BAG",
    "BEANIE",
    "CAP",
    "DRESS",
    "GLOVE",
    "GLOVES",
    "HAT",
    "MITTEN",
    "MITTENS",
    "PANT",
    "PANTS",
    "SCARF",
    "SHORT",
    "SHORTS",
    "SKIRT",
    "SOCK",
    "SOCKS",
    "TROUSER",
    "TROUSERS",
}
_EXCLUDED_TITLE_RE = re.compile(
    r"\b(?:bag|beanie|blanket|cap|dress|gloves?|hat|mittens?|pants?|scarf|"
    r"scrunchie|shorts?|skirt|socks?|trousers?|wild\s+rag|wrap)\b",
    re.IGNORECASE,
)
_INCLUDED_APPAREL_RE = re.compile(
    r"\b(?:cardigan|crew|full\s*zip|henley|hoodie|jacket|knit|polo|"
    r"pullover|rollneck|shirt|sweater|tank|tee|top|turtleneck|v[-\s]?neck|vest)\b",
    re.IGNORECASE,
)
_NON_CASHMERE_MATERIAL_RE = re.compile(
    r"\b(?:silk\s*[/&,+-]*\s*linen|linen\s*[/&,+-]*\s*silk|"
    r"100%\s*linen|[0-9]+%\s*linen[, ]+[0-9]+%\s*silk|"
    r"[0-9]+%\s*silk[, ]+[0-9]+%\s*linen)\b",
    re.IGNORECASE,
)
_COLOR_FAMILY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Multicolor", ("combo", "/", "stripe", "striped", "plaid", "check", "gingham")),
    ("Black", ("black",)),
    ("Navy", ("midnight", "navy")),
    ("Blue", ("blue", "chambray", "clear sky", "pool", "sky")),
    ("Green", ("cypress", "green", "limewash", "match point", "seaglass")),
    ("Gray", ("charcoal", "gray", "grey", "heather", "mist")),
    ("Brown", ("brown", "chestnut", "cinnamon", "cocoa", "taupe")),
    ("Beige", ("beige", "cream", "dune", "sand", "sandstone", "stone", "suede")),
    ("White", ("butter", "ivory", "sail", "white")),
    ("Orange", ("orange", "sorbet")),
    ("Pink", ("pink", "powder pink")),
    ("Purple", ("dusk", "plum", "purple", "violet")),
    ("Red", ("chili", "red", "ruby", "scarlet")),
    ("Yellow", ("daybreak", "sole", "yellow")),
)


def _clean_text(value: object | None) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "")).strip()


def _normalize_text(value: object | None) -> str:
    return _clean_text(value).casefold()


def guestinresidence_product_handle_from_url(url: str) -> str | None:
    """Extract a Shopify product handle from a Guest in Residence PDP URL."""

    parsed = urlparse(str(url or ""))
    match = _PRODUCT_PATH_RE.search(parsed.path)
    if not match:
        return None
    handle = match.group("handle").strip().lower()
    return handle or None


def guestinresidence_parent_id_from_url(url: str) -> str | None:
    """Return the stable parent product id used for GIR products."""

    return guestinresidence_product_handle_from_url(url)


def guestinresidence_product_url(handle: str) -> str:
    """Build the canonical product URL for one GIR Shopify handle."""

    normalized = str(handle or "").strip().strip("/").lower()
    return urljoin(GUESTINRESIDENCE_BASE_URL, f"/products/{normalized}")


def guestinresidence_category_from_url(url: str) -> str | None:
    """Return the local category key for supported GIR category/PDP URLs."""

    parsed = urlparse(str(url or ""))
    path = parsed.path.rstrip("/").lower()
    if guestinresidence_product_handle_from_url(url):
        return GUESTINRESIDENCE_CATEGORY_KEY
    if path in {
        value.rstrip("/").lower()
        for value in GUESTINRESIDENCE_COLLECTION_PATHS.values()
    }:
        return GUESTINRESIDENCE_CATEGORY_KEY
    return None


def guestinresidence_category_path(
    category_key: str | None = GUESTINRESIDENCE_CATEGORY_KEY,
) -> tuple[str, ...]:
    """Return the normalized category path stored on parsed parent products."""

    normalized = str(category_key or "").strip().lower()
    if normalized == GUESTINRESIDENCE_CATEGORY_KEY:
        return ("Women", "Clothing", "Cashmere Sweaters")
    return ("Women", "Clothing")


def guestinresidence_product_text(product: Mapping[str, object]) -> str:
    """Return visible PDP body text for a Shopify product payload."""

    raw_html = (
        product.get("body_html")
        or product.get("description")
        or product.get("content")
        or ""
    )
    soup = BeautifulSoup(str(raw_html or ""), "lxml")
    text = soup.get_text(" ", strip=True)
    return _clean_text(text)


def guestinresidence_feature_lines(product: Mapping[str, object]) -> list[str]:
    """Return ordered product-detail bullet lines from a Shopify product payload."""

    raw_html = (
        product.get("body_html")
        or product.get("description")
        or product.get("content")
        or ""
    )
    soup = BeautifulSoup(str(raw_html or ""), "lxml")
    lines: list[str] = []
    seen: set[str] = set()
    nodes = soup.select("li") or soup.select("p")
    for node in nodes:
        line = _clean_text(node.get_text(" ", strip=True))
        key = line.casefold()
        if line and key not in seen:
            seen.add(key)
            lines.append(line)
    if lines:
        return lines
    text = guestinresidence_product_text(product)
    return [text] if text else []


def _product_haystack(product: Mapping[str, object]) -> str:
    tags = product.get("tags")
    tag_text = (
        " ".join(str(item) for item in tags)
        if isinstance(tags, Sequence) and not isinstance(tags, (str, bytes))
        else ""
    )
    return " ".join(
        [
            _clean_text(product.get("title")),
            _clean_text(product.get("handle")),
            _clean_text(product.get("product_type") or product.get("type")),
            tag_text,
            guestinresidence_product_text(product),
        ]
    )


def guestinresidence_cashmere_scope_decision(
    product: Mapping[str, object],
) -> tuple[bool, str]:
    """Return whether a GIR product belongs in the Saks-like cashmere scope."""

    title = _clean_text(product.get("title"))
    product_type = _clean_text(product.get("product_type") or product.get("type"))
    type_key = product_type.upper()
    haystack = _product_haystack(product)
    haystack_lower = haystack.casefold()
    body_lower = guestinresidence_product_text(product).casefold()

    if type_key in _EXCLUDED_PRODUCT_TYPES or _EXCLUDED_TITLE_RE.search(title):
        return False, "excluded product type/title"
    if "cashmere" not in haystack_lower:
        return False, "no cashmere evidence"
    if _NON_CASHMERE_MATERIAL_RE.search(haystack) and "cashmere" not in body_lower:
        return False, "non-cashmere material"
    if not _INCLUDED_APPAREL_RE.search(haystack):
        return False, "not sweater/cardigan/top-like"
    return True, "cashmere-led sweater/cardigan/top scope"


def _option_index(product: Mapping[str, object], option_name: str) -> int | None:
    options = product.get("options")
    wanted = option_name.strip().casefold()
    if isinstance(options, Sequence) and not isinstance(options, (str, bytes)):
        for index, option in enumerate(options, start=1):
            if isinstance(option, Mapping):
                name = _clean_text(option.get("name")).casefold()
            else:
                name = _clean_text(option).casefold()
            if name == wanted:
                return index
    return None


def guestinresidence_product_option_values(
    product: Mapping[str, object],
    option_name: str,
) -> tuple[str, ...]:
    """Return distinct option values from a Shopify product payload."""

    wanted = option_name.strip().casefold()
    values: list[str] = []
    seen: set[str] = set()
    options = product.get("options")
    if isinstance(options, Sequence) and not isinstance(options, (str, bytes)):
        for option in options:
            if not isinstance(option, Mapping):
                continue
            if _clean_text(option.get("name")).casefold() != wanted:
                continue
            raw_values = option.get("values")
            if not isinstance(raw_values, Sequence) or isinstance(
                raw_values, (str, bytes)
            ):
                continue
            for raw_value in raw_values:
                value = _clean_text(raw_value)
                key = value.casefold()
                if value and key not in seen:
                    seen.add(key)
                    values.append(value)

    option_index = _option_index(product, option_name)
    variants = product.get("variants")
    if option_index is not None and isinstance(variants, Sequence):
        option_key = f"option{option_index}"
        for variant in variants:
            if not isinstance(variant, Mapping):
                continue
            value = _clean_text(variant.get(option_key))
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                values.append(value)
    return tuple(values)


def guestinresidence_color_families(raw_color: object) -> tuple[str, ...]:
    """Map a GIR color option into the site/Saks-level color families."""

    normalized = _normalize_text(raw_color).replace("-", " ")
    if not normalized:
        return ()
    families: list[str] = []
    for family, tokens in _COLOR_FAMILY_RULES:
        if any(token in normalized for token in tokens):
            families.append(family)
    if not families:
        return ()
    return tuple(dict.fromkeys(families))


def guestinresidence_semantic_attribute_hints(
    product: Mapping[str, object],
) -> dict[str, list[str]]:
    """Return deterministic text hints for the cashmere-sweater attribute mapper."""

    title = _normalize_text(product.get("title"))
    body = _normalize_text(guestinresidence_product_text(product))
    product_type = _normalize_text(product.get("product_type") or product.get("type"))
    haystack = " ".join([title, body, product_type])
    hints: dict[str, list[str]] = {}

    def add(attribute: str, value: str) -> None:
        hints.setdefault(attribute, [])
        if value not in hints[attribute]:
            hints[attribute].append(value)

    if "cardigan" in haystack:
        add("garment_type", "cardigan")
    elif "jacket" in haystack:
        add("garment_type", "jacket")
    elif "vest" in haystack:
        add("garment_type", "vest")
    elif "polo" in haystack:
        add("garment_type", "polo")
    elif "tee" in haystack or "tank" in haystack or "top" in product_type:
        add("garment_type", "top")
    elif "shirt" in haystack:
        add("garment_type", "shirt")
    elif "pullover" in product_type or "sweater" in haystack or "crew" in haystack:
        add("garment_type", "pullover")

    if "crew neck" in haystack or "crewneck" in haystack or " crew " in haystack:
        add("neckline", "crew neck")
    if "v neck" in haystack or "v-neck" in haystack:
        add("neckline", "v-neck")
    if "turtleneck" in haystack or "rollneck" in haystack or "roll neck" in haystack:
        add("neckline", "turtleneck")
    if "polo collar" in haystack or " polo " in haystack:
        add("neckline", "polo collar")
    if "half zip" in haystack or "half-zip" in haystack:
        add("neckline", "half zip")

    if "short sleeve" in haystack or "s/s" in haystack:
        add("sleeve_length", "short sleeve")
    elif "sleeveless" in haystack or "tank" in haystack or "vest" in haystack:
        add("sleeve_length", "sleeveless")
    elif "long sleeve" in haystack or "l/s" in haystack or "sleeve" in haystack:
        add("sleeve_length", "long sleeve")

    for token, value in (
        ("cable", "cable knit"),
        ("rib", "rib knit"),
        ("popcorn", "popcorn knit"),
        ("jersey", "jersey knit"),
        ("interlock", "interlock knit"),
        ("waffle", "waffle knit"),
    ):
        if token in haystack:
            add("knit_detail", value)

    for token, value in (
        ("cropped", "cropped"),
        ("oversized", "oversized"),
        ("plaid", "plaid"),
        ("shrunken", "shrunken"),
        ("stripe", "striped"),
        ("striped", "striped"),
    ):
        if token in haystack:
            add("style", value)

    return hints
