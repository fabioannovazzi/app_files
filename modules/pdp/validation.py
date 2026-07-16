from __future__ import annotations

from collections import Counter
from typing import Iterable, Sequence

from .models import ParentProduct, Variant
from .profile import PDPProfile


def validate_parent_and_variants(
    parent: ParentProduct | None,
    variants: Sequence[Variant],
    profile: PDPProfile,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return ``(errors, warnings)`` for the parsed entities."""

    errors: list[str] = []
    warnings: list[str] = []

    validation = profile.validation
    parent_rules = profile.parent_rules

    if parent is None:
        errors.append("parent_missing")
        return tuple(errors), tuple(warnings)

    if validation.require_brand and not parent.brand_raw:
        errors.append("missing_brand")
    if validation.require_title and not parent.title_raw:
        errors.append("missing_title")

    if validation.reject_if_zero_variants and not variants:
        errors.append("no_variants")

    variant_ids = [variant.variant_id for variant in variants if variant.variant_id]
    duplicates = {variant_id for variant_id, count in Counter(variant_ids).items() if count > 1}
    if duplicates:
        warnings.append(f"duplicate_variant_ids:{','.join(sorted(duplicates))}")

    has_shade_name = any(variant.shade_name_raw for variant in variants)
    if parent.has_color_selector and not has_shade_name:
        warnings.append("color_axis_flagged_but_no_shade_names")

    if parent.has_color_selector and len(variants) < parent_rules.min_color_variants:
        warnings.append("color_selector_below_threshold")

    return tuple(errors), tuple(warnings)


__all__ = ["validate_parent_and_variants"]
