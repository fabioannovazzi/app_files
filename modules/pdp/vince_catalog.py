from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urljoin, urlparse

__all__ = [
    "VINCE_BASE_URL",
    "VINCE_BRAND_NAME",
    "VINCE_CATEGORY_KEY",
    "VINCE_CATEGORY_PATH",
    "VINCE_CATEGORY_URL",
    "VINCE_RETAILER",
    "vince_category_from_url",
    "vince_category_path",
    "vince_color_families",
    "vince_parent_id_from_url",
    "vince_product_url",
    "vince_semantic_attribute_hints",
    "vince_style_id_from_parent_id",
]

VINCE_BASE_URL = "https://www.vince.com"
VINCE_BRAND_NAME = "Vince"
VINCE_RETAILER = "vince"
VINCE_CATEGORY_KEY = "low_top_sneakers"
VINCE_CATEGORY_URL = f"{VINCE_BASE_URL}/sneakers-for-women/"
VINCE_CATEGORY_PATH = ("Women", "Shoes", "Sneakers")

_PDP_PATH_RE = re.compile(
    r"(?:^|/)product/(?P<slug>[a-z0-9][a-z0-9-]*)-(?P<pid>[A-Z0-9]+)\.html$",
    re.IGNORECASE,
)
_COLOR_FAMILY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Multicolor", ("combo", "multi", "stripe", "gingham", "plaid", "/")),
    ("Black", ("black", "night star")),
    ("Blue", ("blue", "celeste", "coastal", "indigo", "uniform blue")),
    ("Green", ("green", "kalamata", "olive", "palm", "pistachio", "sap")),
    ("Grey", ("charcoal", "flint", "grey", "gray", "haze", "smoke")),
    ("Brown", ("brown", "camel", "cocoa", "clove", "molton", "taupe")),
    (
        "Beige",
        ("beige", "birch", "desert", "flax", "koala", "moonlight", "sand", "straw"),
    ),
    ("White", ("ivory", "optic white", "shell", "white")),
    ("Orange", ("ember", "orange")),
    ("Pink", ("blush", "pink", "rose")),
    ("Purple", ("purple", "violet")),
    ("Red", ("red", "rouge")),
    ("Yellow", ("yellow",)),
)


def _clean_text(value: object | None) -> str:
    return " ".join(str(value or "").split())


def vince_parent_id_from_url(url: str) -> str | None:
    """Extract the Vince PDP id from a canonical product URL."""

    parsed = urlparse(str(url or ""))
    match = _PDP_PATH_RE.search(parsed.path)
    if not match:
        return None
    parent_id = match.group("pid").strip().upper()
    return parent_id or None


def vince_style_id_from_parent_id(parent_id: object | None) -> str | None:
    """Return the base style id when a Vince parent id includes color text."""

    text = _clean_text(parent_id).upper()
    if not text:
        return None
    match = re.match(r"^([A-Z][0-9]{4}[A-Z][A-Z0-9]?)", text)
    if match:
        return match.group(1)
    return text


def vince_product_url(parent_id: str, slug: str | None = None) -> str:
    """Build a Vince product URL for a known parent id and optional slug."""

    normalized_id = _clean_text(parent_id).upper()
    normalized_slug = _clean_text(slug).lower().strip("-")
    if not normalized_slug:
        normalized_slug = "product"
    return urljoin(VINCE_BASE_URL, f"/product/{normalized_slug}-{normalized_id}.html")


def vince_category_from_url(url: str) -> str | None:
    """Return the supported category key for Vince sneaker category/PDP URLs."""

    parsed = urlparse(str(url or ""))
    path = parsed.path.rstrip("/").lower()
    if path == "/sneakers-for-women":
        return VINCE_CATEGORY_KEY
    if vince_parent_id_from_url(url):
        return VINCE_CATEGORY_KEY
    return None


def vince_category_path(
    category_key: str | None = VINCE_CATEGORY_KEY,
) -> tuple[str, ...]:
    """Return the normalized category path stored on parsed Vince products."""

    normalized = str(category_key or "").strip().lower()
    if normalized == VINCE_CATEGORY_KEY:
        return VINCE_CATEGORY_PATH
    return ("Women", "Shoes")


def vince_color_families(raw_color: object) -> tuple[str, ...]:
    """Map a Vince color label to the broad color filters exposed by the site."""

    color = _clean_text(raw_color).casefold()
    if not color:
        return ()
    families: list[str] = []
    for family, needles in _COLOR_FAMILY_RULES:
        if any(needle in color for needle in needles) and family not in families:
            families.append(family)
    return tuple(families or ("Multicolor",))


def _values_from_mapping(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    raw_value = payload.get(key)
    if isinstance(raw_value, str):
        text = _clean_text(raw_value)
        return (text,) if text else ()
    if isinstance(raw_value, list):
        return tuple(text for item in raw_value if (text := _clean_text(item)))
    return ()


def vince_semantic_attribute_hints(
    *,
    title: object | None = None,
    description: object | None = None,
    material: object | None = None,
    detail_lines: tuple[str, ...] = (),
) -> dict[str, list[str]]:
    """Return deterministic sneaker taxonomy hints from Vince PDP text."""

    haystack = " ".join(
        [
            _clean_text(title),
            _clean_text(description),
            _clean_text(material),
            " ".join(_clean_text(line) for line in detail_lines),
        ]
    ).casefold()
    hints: dict[str, list[str]] = {}

    def add(attribute: str, value: str) -> None:
        values = hints.setdefault(attribute, [])
        if value not in values:
            values.append(value)

    material_rules = (
        ("canvas", "canvas"),
        ("denim", "denim"),
        ("embellished", "embellished"),
        ("leather", "leather"),
        ("mesh", "mesh"),
        ("netting", "mesh"),
        ("patent", "patent_leather"),
        ("raffia", "raffia"),
        ("satin", "satin"),
        ("shearling", "shearling"),
        ("suede", "suede"),
    )
    for needle, value in material_rules:
        if needle in haystack:
            add("material", value)

    if "lace-up" in haystack or "lace up" in haystack:
        add("closure", "lace_up")
    if "slip-on" in haystack or "slip on" in haystack:
        add("closure", "slip_on")
    if "rounded toe" in haystack or "round toe" in haystack:
        add("toe_shape", "round_toe")
    if "cap toe" in haystack or "toe cap" in haystack:
        add("toe_shape", "cap_toe")
    if "rubber sole" in haystack or "rubber outsole" in haystack:
        add("sole_type", "rubber_sole")
    if "platform" in haystack:
        add("sole_type", "platform_sole")
    if "lug sole" in haystack or "lugged sole" in haystack:
        add("sole_type", "lug_sole")

    if "logo" in haystack or "logo-stamped" in haystack:
        add("design_detail", "logo_detail")
    if "contrast" in haystack or "colorblock" in haystack or "color block" in haystack:
        add("design_detail", "colorblock")
    if "perforated" in haystack:
        add("design_detail", "perforated")
    if "metallic" in haystack:
        add("design_detail", "metallic")
    if "snake" in haystack or "gingham" in haystack or "pattern" in haystack:
        add("design_detail", "patterned")

    if "runner" in haystack or "running" in haystack:
        add("silhouette", "runner_inspired")
    if "court" in haystack:
        add("silhouette", "court_inspired")
    if "low profile" in haystack or "minimal" in haystack:
        add("silhouette", "minimal")
    return hints
