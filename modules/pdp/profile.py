from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping, Sequence


@dataclass(slots=True)
class BlobSource:
    """Describe a source of JSON blobs within the HTML."""

    type: str
    selector: str


@dataclass(slots=True)
class ParentRules:
    """Retailer-specific parent heuristics."""

    min_color_variants: int
    disallow_kits_pattern: re.Pattern[str] | None
    finish_split_tokens: tuple[str, ...]


@dataclass(slots=True)
class IdExtractors:
    """Rules to determine parent and variant IDs."""

    parent_from_url_regex: re.Pattern[str] | None
    parent_json_paths: tuple[str, ...]
    variant_id_fields: tuple[str, ...]


@dataclass(slots=True)
class FieldNormalizationSpec:
    """Per-field normalization toggles."""

    trim: bool = False
    collapse_spaces: bool = False
    dedupe_symbols: bool = False
    normalize_number_position: bool = False
    strip_trailing_shade_tokens: bool = False
    strip_pack_counts: bool = False


@dataclass(slots=True)
class NormalizationConfig:
    """Container for normalization rules per field."""

    brand: FieldNormalizationSpec
    shade_name: FieldNormalizationSpec
    title: FieldNormalizationSpec


@dataclass(slots=True)
class ValidationRules:
    """Lightweight validation toggles."""

    require_brand: bool
    require_title: bool
    price_must_be_numeric: bool
    reject_if_zero_variants: bool


@dataclass(slots=True)
class FieldPaths:
    """JSON path instructions for parent and variants."""

    brand: tuple[str, ...]
    parent_title: tuple[str, ...]
    parent_summary: tuple[str, ...]
    series_label: tuple[str, ...]
    category_path: tuple[str, ...]
    variant_list: tuple[str, ...]
    variant_fields: Mapping[str, tuple[str, ...]]


@dataclass(slots=True)
class PDPProfile:
    """Retailer configuration."""

    profile_name: str
    retailer: str
    base_url: str
    display_name: str
    category_hints: tuple[str, ...]
    category_urls: tuple[str, ...]
    parent_rules: ParentRules
    id_extractors: IdExtractors
    blob_sources: tuple[BlobSource, ...]
    field_paths: FieldPaths
    normalization: NormalizationConfig
    validation: ValidationRules
    claim_mapping: Mapping[str, Mapping[str, Sequence[str | dict[str, str]]]] | None = None


def compile_optional_regex(pattern: str | None) -> re.Pattern[str] | None:
    if not pattern:
        return None
    return re.compile(pattern)


__all__ = [
    "BlobSource",
    "FieldNormalizationSpec",
    "FieldPaths",
    "IdExtractors",
    "NormalizationConfig",
    "PDPProfile",
    "ParentRules",
    "ValidationRules",
    "compile_optional_regex",
]
