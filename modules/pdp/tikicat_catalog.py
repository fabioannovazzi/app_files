from __future__ import annotations

import html
import re
from collections.abc import Mapping, Sequence
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup  # type: ignore[import]

__all__ = [
    "TIKICAT_BASE_URL",
    "TIKICAT_BRAND_NAME",
    "TIKICAT_CATEGORY_KEY",
    "TIKICAT_RETAILER",
    "TIKICAT_WET_CAT_FOOD_CATEGORY_ID",
    "TIKICAT_WET_CAT_FOOD_URL",
    "tikicat_available_sizes_from_text",
    "tikicat_category_path",
    "tikicat_feature_lines_from_product",
    "tikicat_is_wet_cat_food_product",
    "tikicat_lifestage_from_text",
    "tikicat_parent_id_from_url",
    "tikicat_product_category_terms",
    "tikicat_product_text",
    "tikicat_product_url",
    "tikicat_semantic_attribute_hints",
    "tikicat_term_values_for_product",
]

TIKICAT_BASE_URL = "https://tikipets.com"
TIKICAT_BRAND_NAME = "Tiki Cat"
TIKICAT_RETAILER = "tikicat"
TIKICAT_CATEGORY_KEY = "wet_cat_food"
TIKICAT_WET_CAT_FOOD_CATEGORY_ID = 222
TIKICAT_WET_CAT_FOOD_URL = (
    "https://tikipets.com/product-category/tiki-cat/tiki-cat-wet-food/"
)

_PRODUCT_PATH_RE = re.compile(
    r"(?:^|/)product/tiki-cat/tiki-cat-wet-food/.+/(?P<slug>[a-z0-9][a-z0-9-]*)(?:$|[/?#])",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")
_AVAILABLE_IN_RE = re.compile(
    r"available\s+in\s*:\s*(?P<sizes>.+?)(?:\n|$)",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(r"\b(?P<count>\d+)\s*(?:ct|count)\b", re.IGNORECASE)
_PACKAGING_RE = re.compile(
    r"\b(?:can|cup|pouch|tray|tub|box|bag)\b",
    re.IGNORECASE,
)
_PROTEIN_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Chicken", ("chicken",)),
    ("Tuna", ("tuna", "ahi")),
    ("Salmon", ("salmon",)),
    ("Duck", ("duck",)),
    ("Beef", ("beef",)),
    ("Liver", ("liver",)),
    ("Mackerel", ("mackerel",)),
    ("Sardine", ("sardine",)),
    ("Shrimp", ("shrimp", "prawn")),
    ("Turkey", ("turkey",)),
    ("Venison", ("venison",)),
    ("Lamb", ("lamb",)),
    ("Seabass", ("seabass", "sea bass")),
    ("Tilapia", ("tilapia",)),
    ("Crab", ("crab",)),
    ("Cod", ("cod",)),
    ("Seafood & Fish", ("fish", "seafood")),
)
_SPECIAL_DIET_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Grain-Free", ("grain free", "no grains")),
    ("Non-GMO", ("non gmo", "non-gmo")),
    ("High-Protein", ("high protein", "protein-rich", "protein rich")),
    ("Low Fat", ("low fat", "low-fat")),
    ("No Corn No Wheat No Soy", ("no corn", "no wheat", "no soy")),
    ("Natural", ("natural",)),
)
_HEALTH_FEATURE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Digestive Health", ("digestion", "digestive", "prebiotic", "pumpkin")),
    ("Skin & Coat Health", ("skin", "coat", "omega", "salmon oil")),
    ("Senior Care", ("senior", "silver")),
    ("Brain Health", ("dha", "brain")),
    ("Immune Support", ("immune",)),
    ("Weight Management", ("light", "weight")),
)


def _clean_text(value: object | None) -> str:
    text = html.unescape(str(value or ""))
    return _WHITESPACE_RE.sub(" ", text).strip()


def _normalize_text(value: object | None) -> str:
    return _clean_text(value).casefold()


def _strip_html(value: object | None) -> str:
    soup = BeautifulSoup(str(value or ""), "lxml")
    return _clean_text(soup.get_text(" ", strip=True))


def _html_lines(value: object | None) -> list[str]:
    soup = BeautifulSoup(str(value or ""), "lxml")
    lines: list[str] = []
    seen: set[str] = set()
    for node in soup.select("li") or soup.select("p"):
        line = _clean_text(node.get_text(" ", strip=True))
        key = line.casefold()
        if line and key not in seen:
            seen.add(key)
            lines.append(line)
    return lines


def _term_id(value: object | None) -> int | None:
    try:
        term_id = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return term_id if term_id > 0 else None


def _term_name(term: Mapping[str, object]) -> str:
    return _clean_text(term.get("name"))


def _term_link(term: Mapping[str, object]) -> str:
    link = _clean_text(term.get("link"))
    return link or TIKICAT_WET_CAT_FOOD_URL


def _embedded_product_terms(
    product: Mapping[str, object],
) -> list[Mapping[str, object]]:
    embedded = product.get("_embedded")
    if not isinstance(embedded, Mapping):
        return []
    raw_groups = embedded.get("wp:term")
    if not isinstance(raw_groups, Sequence) or isinstance(raw_groups, (str, bytes)):
        return []
    terms: list[Mapping[str, object]] = []
    for group in raw_groups:
        if not isinstance(group, Sequence) or isinstance(group, (str, bytes)):
            continue
        for item in group:
            if isinstance(item, Mapping) and item.get("taxonomy") == "product_cat":
                terms.append(item)
    return terms


def _ancestor_terms(
    term: Mapping[str, object],
    term_lookup: Mapping[int, Mapping[str, object]],
) -> list[Mapping[str, object]]:
    ancestors: list[Mapping[str, object]] = []
    seen: set[int] = set()
    current = term
    while True:
        parent_id = _term_id(current.get("parent"))
        if parent_id is None or parent_id in seen:
            break
        seen.add(parent_id)
        parent = term_lookup.get(parent_id)
        if parent is None:
            break
        ancestors.append(parent)
        current = parent
    return ancestors


def _term_is_or_has_ancestor(
    term: Mapping[str, object],
    ancestor_id: int,
    term_lookup: Mapping[int, Mapping[str, object]],
) -> bool:
    term_id = _term_id(term.get("id"))
    if term_id == ancestor_id:
        return True
    return any(
        _term_id(parent.get("id")) == ancestor_id
        for parent in _ancestor_terms(term, term_lookup)
    )


def tikicat_parent_id_from_url(url: str) -> str | None:
    """Extract the Tiki Cat PDP slug used as a stable parent id."""

    parsed = urlparse(str(url or ""))
    match = _PRODUCT_PATH_RE.search(parsed.path.rstrip("/") + "/")
    if not match:
        return None
    return match.group("slug").strip().lower() or None


def tikicat_product_url(parent_id: str, fallback_url: str | None = None) -> str:
    """Return a Tiki Cat PDP URL for a known parent id when possible."""

    if fallback_url and tikicat_parent_id_from_url(fallback_url):
        return fallback_url
    slug = str(parent_id or "").strip().strip("/").lower()
    return urljoin(TIKICAT_BASE_URL, f"/product/tiki-cat/tiki-cat-wet-food/{slug}/")


def tikicat_category_path(
    *,
    texture: str | None = None,
    product_lines: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Return the normalized category path stored on parsed Tiki Cat products."""

    path = ["Pet", "Cat", "Wet Cat Food"]
    if texture:
        path.append(texture)
    for line in product_lines or ():
        if line and line not in path:
            path.append(line)
    return tuple(path)


def tikicat_product_category_terms(
    product: Mapping[str, object],
    *,
    term_lookup: Mapping[int, Mapping[str, object]] | None = None,
) -> list[Mapping[str, object]]:
    """Return product category terms plus ancestors from a WP product payload."""

    lookup = term_lookup or {}
    terms: list[Mapping[str, object]] = []
    seen: set[int] = set()

    def add(term: Mapping[str, object]) -> None:
        term_id = _term_id(term.get("id"))
        if term_id is None or term_id in seen:
            return
        if term_id in lookup:
            term = lookup[term_id]
        seen.add(term_id)
        terms.append(term)

    for term in _embedded_product_terms(product):
        add(term)
        if lookup:
            for ancestor in _ancestor_terms(term, lookup):
                add(ancestor)

    raw_ids = product.get("product_cat")
    if isinstance(raw_ids, Sequence) and not isinstance(raw_ids, (str, bytes)):
        for raw_id in raw_ids:
            term_id = _term_id(raw_id)
            if term_id is None:
                continue
            term = lookup.get(term_id)
            if term is not None:
                add(term)
                for ancestor in _ancestor_terms(term, lookup):
                    add(ancestor)

    return sorted(terms, key=lambda item: (_term_id(item.get("id")) or 0))


def tikicat_is_wet_cat_food_product(
    product: Mapping[str, object],
    *,
    term_lookup: Mapping[int, Mapping[str, object]] | None = None,
) -> bool:
    """Return whether one WP product belongs to Tiki Cat wet cat food."""

    link = _clean_text(product.get("link"))
    parsed_path = urlparse(link).path.casefold()
    if "/product/tiki-cat/tiki-cat-wet-food/" in parsed_path:
        return True
    if not term_lookup:
        return False
    return any(
        _term_is_or_has_ancestor(term, TIKICAT_WET_CAT_FOOD_CATEGORY_ID, term_lookup)
        for term in tikicat_product_category_terms(product, term_lookup=term_lookup)
    )


def tikicat_term_values_for_product(
    product: Mapping[str, object],
    *,
    term_lookup: Mapping[int, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Derive texture, line, and lifestage labels from Tiki product categories."""

    lookup = term_lookup or {}
    terms = tikicat_product_category_terms(product, term_lookup=lookup)
    wet_terms = [
        term
        for term in terms
        if _term_id(term.get("id")) != TIKICAT_WET_CAT_FOOD_CATEGORY_ID
        and (
            not lookup
            or _term_is_or_has_ancestor(term, TIKICAT_WET_CAT_FOOD_CATEGORY_ID, lookup)
        )
    ]
    texture_terms: list[Mapping[str, object]] = []
    line_terms: list[Mapping[str, object]] = []
    for term in wet_terms:
        parent_id = _term_id(term.get("parent"))
        if parent_id == TIKICAT_WET_CAT_FOOD_CATEGORY_ID:
            texture_terms.append(term)
            continue
        term_id = _term_id(term.get("id"))
        if term_id is None:
            continue
        ancestors = _ancestor_terms(term, lookup) if lookup else []
        if any(
            _term_id(parent.get("parent")) == TIKICAT_WET_CAT_FOOD_CATEGORY_ID
            for parent in ancestors
        ):
            line_terms.append(term)

    texture = _term_name(texture_terms[0]) if texture_terms else None
    product_lines = [_term_name(term) for term in line_terms if _term_name(term)]
    title = _clean_text(
        (product.get("title") or {}).get("rendered")
        if isinstance(product.get("title"), Mapping)
        else product.get("title")
    )
    lifestage = tikicat_lifestage_from_text(" ".join([title, " ".join(product_lines)]))
    assortment = (
        "Variety Pack"
        if _COUNT_RE.search(title)
        or any("pack" in line.casefold() for line in product_lines)
        else "Single Recipe"
    )
    return {
        "terms": terms,
        "texture": texture,
        "product_lines": product_lines,
        "lifestage": lifestage,
        "product_assortment": assortment,
    }


def tikicat_product_text(product: Mapping[str, object]) -> str:
    """Return visible descriptive text from a Tiki Pets WP product payload."""

    title_payload = product.get("title")
    title = (
        _clean_text(title_payload.get("rendered"))
        if isinstance(title_payload, Mapping)
        else _clean_text(title_payload)
    )
    excerpt = product.get("excerpt")
    content = product.get("content")
    parts = [
        title,
        _strip_html(
            excerpt.get("rendered") if isinstance(excerpt, Mapping) else excerpt
        ),
        _strip_html(
            content.get("rendered") if isinstance(content, Mapping) else content
        ),
    ]
    return _clean_text(" ".join(part for part in parts if part))


def tikicat_feature_lines_from_product(product: Mapping[str, object]) -> list[str]:
    """Return ordered product-detail bullets from a Tiki WP product payload."""

    lines: list[str] = []
    seen: set[str] = set()
    for key in ("excerpt", "content"):
        raw = product.get(key)
        rendered = raw.get("rendered") if isinstance(raw, Mapping) else raw
        for line in _html_lines(rendered):
            line_key = line.casefold()
            if line_key in seen:
                continue
            seen.add(line_key)
            lines.append(line)
    if lines:
        return lines
    text = tikicat_product_text(product)
    return [text] if text else []


def tikicat_available_sizes_from_text(text: object | None) -> list[str]:
    """Extract sizes from visible PDP copy such as `Available in: 3 oz. can`."""

    raw_text = html.unescape(str(text or ""))
    normalized = "\n".join(
        line for raw_line in raw_text.splitlines() if (line := _clean_text(raw_line))
    )
    match = _AVAILABLE_IN_RE.search(normalized)
    if not match:
        return []
    raw_sizes = match.group("sizes")
    sizes: list[str] = []
    seen: set[str] = set()
    for value in re.split(r"\s*\|\s*|\s*,\s*", raw_sizes):
        size = _clean_text(value)
        if not size or size.casefold() in seen:
            continue
        seen.add(size.casefold())
        sizes.append(size)
    return sizes


def tikicat_lifestage_from_text(text: object | None) -> str:
    """Return the most specific lifestage label implied by Tiki copy."""

    normalized = _normalize_text(text)
    if re.search(r"\b(?:kitten|baby)\b", normalized):
        return "Kitten"
    if re.search(r"\b(?:senior|silver|11\+)\b", normalized):
        return "Senior"
    return "Adult"


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


def tikicat_semantic_attribute_hints(
    product: Mapping[str, object] | None = None,
    *,
    term_lookup: Mapping[int, Mapping[str, object]] | None = None,
    body_text: str | None = None,
    title: str | None = None,
    sizes: Sequence[str] | None = None,
    texture: str | None = None,
    product_lines: Sequence[str] | None = None,
) -> dict[str, list[str]]:
    """Return deterministic wet-cat-food taxonomy hints from Tiki site copy."""

    product = product or {}
    term_values = (
        tikicat_term_values_for_product(product, term_lookup=term_lookup)
        if product
        else {"texture": texture, "product_lines": list(product_lines or ())}
    )
    product_text = body_text if body_text is not None else tikicat_product_text(product)
    title_text = title or ""
    all_text = " ".join(
        [
            title_text,
            product_text,
            " ".join(str(item) for item in sizes or ()),
            str(term_values.get("texture") or ""),
            " ".join(str(item) for item in term_values.get("product_lines") or ()),
        ]
    )

    hints: dict[str, list[str]] = {
        "prescription_status": ["non-prescription"],
    }
    if term_values.get("texture"):
        hints["food_texture"] = [str(term_values["texture"])]
    if lines := [str(item) for item in term_values.get("product_lines") or () if item]:
        hints["brand_line"] = lines
    lifestage = tikicat_lifestage_from_text(all_text)
    if lifestage:
        hints["lifestage"] = [lifestage]
    assortment = term_values.get("product_assortment")
    if assortment:
        hints["product_assortment"] = [str(assortment)]
    proteins = _values_from_rules(all_text, _PROTEIN_RULES)
    if proteins:
        hints["animal_protein_source"] = proteins
        hints["flavor"] = proteins[:1]
    special_diets = _values_from_rules(all_text, _SPECIAL_DIET_RULES)
    if special_diets:
        hints["special_diet"] = special_diets
    health_features = _values_from_rules(all_text, _HEALTH_FEATURE_RULES)
    if health_features:
        hints["health_feature"] = health_features
    packaging = _packaging_types_from_text(all_text)
    if packaging:
        hints["packaging_type"] = packaging[:1]
    package_count = _package_count_from_text(all_text)
    if package_count:
        hints["package_count"] = [package_count]
    return {key: values for key, values in hints.items() if values}
