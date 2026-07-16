from __future__ import annotations

import re
from collections.abc import Sequence

from .amazon_filter_discovery import extract_amazon_filter_surfaces
from .cdp_listing_engine import CandidateLink
from .cdp_retailer_strategy import BaseCDPRetailerStrategy
from .models import FilterSurface
from .profile import PDPProfile

__all__ = ["AmazonCDPStrategy"]

_AMAZON_ASIN_IN_PATH = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})", re.IGNORECASE)
_AMAZON_GLOBAL_TITLE_EXCLUDES: tuple[str, ...] = (
    "audio cd",
    "album",
    "single",
    "vinyl",
    "blu-ray",
    "dvd",
    "paperback",
    "hardcover",
    "kindle edition",
    "sheet music",
    "soundtrack",
    "format:",
)
_AMAZON_MEDIA_TERMS: tuple[str, ...] = (
    "music",
    "album",
    "soundtrack",
    "single",
    "audio cd",
    "vinyl",
    "blu-ray",
    "dvd",
    "kindle edition",
    "paperback",
    "hardcover",
    "format:",
)
_AMAZON_STRONG_COSMETIC_CONTEXT_TERMS: tuple[str, ...] = (
    "makeup",
    "cosmetic",
    "beauty",
    "face",
    "cheek",
    "lip",
    "eye",
    "powder",
    "cream",
    "liquid",
    "palette",
    "primer",
    "foundation",
    "concealer",
    "contour",
    "highlighter",
    "bronzer",
    "lipstick",
    "gloss",
    "mascara",
    "eyeliner",
    "eyeshadow",
    "brow",
    "setting spray",
    "setting powder",
    "rouge",
)
_AMAZON_CATEGORY_TITLE_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "wet_cat_food": {
        "include": (
            "cat food",
            "wet cat",
            "pate",
            "paté",
            "gravy",
            "canned cat",
            "cat food topper",
        ),
        "exclude": (
            "dry cat food",
            "dry food",
            "kibble",
            "cat litter",
            "cat toy",
            "dog food",
        ),
    },
    "blush": {
        "include": ("blush", "cheek color", "cheek tint", "cheek stain", "rouge"),
        "exclude": (),
    },
    "bronzer": {
        "include": ("bronzer", "bronzing"),
        "exclude": (),
    },
    "color_corrector": {
        "include": (
            "color corrector",
            "color correcting",
            "corrector",
            "correcting palette",
        ),
        "exclude": ("hair color",),
    },
    "concealer": {
        "include": ("concealer",),
        "exclude": (),
    },
    "contour": {
        "include": ("contour", "contouring"),
        "exclude": (),
    },
    "eyebrow": {
        "include": ("eyebrow", "brow", "brow pomade", "brow pencil", "brow gel"),
        "exclude": (),
    },
    "eyeliner": {
        "include": ("eyeliner", "eye liner", "kajal", "kohl liner"),
        "exclude": (),
    },
    "eyeshadow": {
        "include": ("eyeshadow", "eye shadow", "shadow palette", "eye palette"),
        "exclude": (),
    },
    "face_primer": {
        "include": ("primer", "face primer", "makeup primer", "pore primer"),
        "exclude": ("eyelash primer", "lash primer", "mascara primer", "eye primer"),
    },
    "foundation": {
        "include": ("foundation", "skin tint", "bb cream", "cc cream"),
        "exclude": (),
    },
    "highlighter": {
        "include": ("highlighter", "illuminator", "luminizer", "strobe"),
        "exclude": (),
    },
    "lip_gloss": {
        "include": ("lip gloss", "gloss"),
        "exclude": (),
    },
    "lip_oil": {
        "include": ("lip oil",),
        "exclude": (),
    },
    "lipstick": {
        "include": ("lipstick", "lip stick", "lip color"),
        "exclude": (),
    },
    "mascara": {
        "include": ("mascara",),
        "exclude": (),
    },
    "setting_spray_powder": {
        "include": (
            "setting spray",
            "setting powder",
            "finishing powder",
            "fixing spray",
            "makeup setting",
        ),
        "exclude": (),
    },
}


class AmazonCDPStrategy(BaseCDPRetailerStrategy):
    """Amazon-specific CDP listing-discovery strategy."""

    def __init__(self) -> None:
        super().__init__(
            retailer="amazon",
            selector="a[href*='/dp/'], a[href*='/gp/product/']",
            default_sort_modes=("newest", "best_selling"),
            filter_sort_modes=("default",),
            popularity_sort_mode="best_selling",
            pagination_fallback_param="page",
        )

    def canonicalize_pdp_url(self, url: str, *, profile: PDPProfile) -> str | None:
        match = _AMAZON_ASIN_IN_PATH.search(url)
        if not match:
            return None
        return f"https://www.amazon.com/dp/{match.group(1).upper()}"

    def is_valid_candidate(
        self,
        *,
        candidate: CandidateLink,
        canonical_url: str,
        category_key: str,
        profile: PDPProfile,
    ) -> bool:
        if not super().is_valid_candidate(
            candidate=candidate,
            canonical_url=canonical_url,
            category_key=category_key,
            profile=profile,
        ):
            return False
        return _amazon_title_matches_category(candidate.title or "", category_key)

    def extract_filter_surfaces(
        self,
        *,
        category_url: str,
        html: str,
        category_key: str,
        allowed_families: Sequence[str] | None = None,
    ) -> list[FilterSurface]:
        return extract_amazon_filter_surfaces(
            category_url=category_url,
            html=html,
            category_key=category_key,
            retailer=self.retailer,
            allowed_families=allowed_families,
        )


def _normalize_category_key(raw: str | None) -> str:
    if not raw:
        return ""
    return raw.strip().lower().replace("-", "_").replace(" ", "_")


def _amazon_title_matches_category(title: str, category_key: str | None) -> bool:
    normalized_category = _normalize_category_key(category_key)
    if not normalized_category:
        return True
    if normalized_category == "setting_spray_powder":
        return True
    rules = _AMAZON_CATEGORY_TITLE_RULES.get(normalized_category)
    if not rules:
        return True
    normalized_title = " ".join(title.lower().split())
    if not normalized_title:
        return True
    has_media_term = any(term in normalized_title for term in _AMAZON_MEDIA_TERMS)
    has_strong_cosmetic_context = any(
        term in normalized_title for term in _AMAZON_STRONG_COSMETIC_CONTEXT_TERMS
    )
    if has_media_term and not has_strong_cosmetic_context:
        return False
    if any(term in normalized_title for term in _AMAZON_GLOBAL_TITLE_EXCLUDES):
        return False
    excludes = rules.get("exclude", ())
    if excludes and any(term in normalized_title for term in excludes):
        return False
    includes = rules.get("include", ())
    if not includes:
        return True
    return any(term in normalized_title for term in includes)
