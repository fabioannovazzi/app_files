from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .profile import (
    BlobSource,
    FieldNormalizationSpec,
    FieldPaths,
    IdExtractors,
    NormalizationConfig,
    ParentRules,
    PDPProfile,
    ValidationRules,
    compile_optional_regex,
)

CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config" / "pdp_profiles"


@dataclass(slots=True)
class ProfileSummary:
    profile_name: str
    retailer: str
    display_name: str
    path: Path


def _to_tuple(strings: Sequence[str] | str | None) -> tuple[str, ...]:
    if strings is None:
        return ()
    if isinstance(strings, str):
        return (strings,)
    return tuple(str(item) for item in strings)


def _load_blob_sources(items: Iterable[Mapping[str, str]]) -> tuple[BlobSource, ...]:
    sources: list[BlobSource] = []
    for index, item in enumerate(items):
        source_type = item.get("type")
        selector = item.get("selector")
        if not source_type or not selector:
            raise ValueError(f"Blob source at index {index} is missing required keys.")
        sources.append(BlobSource(type=source_type, selector=selector))
    return tuple(sources)


def _load_normalization(
    payload: Mapping[str, Mapping[str, bool]],
) -> NormalizationConfig:
    brand_payload = payload.get("brand", {})
    shade_payload = payload.get("shade_name", {})
    title_payload = payload.get("title", {})
    brand = FieldNormalizationSpec(
        trim=bool(brand_payload.get("trim", True)),
        collapse_spaces=bool(brand_payload.get("collapse_spaces", True)),
        dedupe_symbols=bool(brand_payload.get("dedupe_symbols")),
        normalize_number_position=bool(brand_payload.get("normalize_number_position")),
    )
    shade = FieldNormalizationSpec(
        trim=bool(shade_payload.get("trim")),
        collapse_spaces=bool(shade_payload.get("collapse_spaces")),
        dedupe_symbols=bool(shade_payload.get("dedupe_symbols")),
        normalize_number_position=bool(shade_payload.get("normalize_number_position")),
    )
    title = FieldNormalizationSpec(
        trim=bool(title_payload.get("trim", True)),
        collapse_spaces=bool(title_payload.get("collapse_spaces", True)),
        dedupe_symbols=bool(title_payload.get("dedupe_symbols")),
        normalize_number_position=bool(title_payload.get("normalize_number_position")),
        strip_trailing_shade_tokens=bool(
            title_payload.get("strip_trailing_shade_tokens")
        ),
        strip_pack_counts=bool(title_payload.get("strip_pack_counts")),
    )
    return NormalizationConfig(brand=brand, shade_name=shade, title=title)


def _load_field_paths(payload: Mapping[str, object]) -> FieldPaths:
    variant_fields_raw = payload.get("variant_fields")
    if not isinstance(variant_fields_raw, Mapping):
        raise ValueError("Field paths require a `variant_fields` mapping.")

    variant_fields: dict[str, tuple[str, ...]] = {
        key: _to_tuple(value if isinstance(value, Sequence) else ())
        for key, value in variant_fields_raw.items()
    }

    return FieldPaths(
        brand=_to_tuple(payload.get("brand")),
        parent_title=_to_tuple(payload.get("parent_title")),
        parent_summary=_to_tuple(payload.get("parent_summary")),
        series_label=_to_tuple(payload.get("series_label")),
        category_path=_to_tuple(payload.get("category_path")),
        variant_list=_to_tuple(payload.get("variant_list")),
        variant_fields=variant_fields,
    )


def load_profile(profile: str, root: Path | None = None) -> PDPProfile:
    """Load a PDP profile by name or explicit path."""

    base_path = root or CONFIG_ROOT
    candidate = Path(profile)
    if candidate.suffix:
        path = candidate
    else:
        path = base_path / f"{profile}.json"

    if not path.exists():
        raise FileNotFoundError(f"PDP profile not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data: Mapping[str, object] = json.load(handle)

    profile_name = str(data.get("profile_name") or path.stem)
    retailer = str(data["retailer"])
    base_url = str(data.get("base_url") or "")
    display_name = str(data.get("display_name") or profile_name.title())

    parent_rules_payload = data.get("parent_rules")
    if not isinstance(parent_rules_payload, Mapping):
        raise ValueError("Profile must include parent_rules.")
    parent_rules = ParentRules(
        min_color_variants=int(parent_rules_payload.get("min_color_variants", 0)),
        disallow_kits_pattern=compile_optional_regex(parent_rules_payload.get("disallow_kits_regex")),  # type: ignore[arg-type]
        finish_split_tokens=_to_tuple(parent_rules_payload.get("finish_split_tokens")),
    )

    id_payload = data.get("id_extractors")
    if not isinstance(id_payload, Mapping):
        raise ValueError("Profile must include id_extractors.")
    parent_regex = id_payload.get("parent_from_url_regex")
    id_extractors = IdExtractors(
        parent_from_url_regex=compile_optional_regex(parent_regex),  # type: ignore[arg-type]
        parent_json_paths=_to_tuple(id_payload.get("parent_json_paths")),
        variant_id_fields=_to_tuple(id_payload.get("variant_id_fields")),
    )

    blob_sources_payload = data.get("blob_sources")
    if not isinstance(blob_sources_payload, Mapping):
        raise ValueError("Profile must include blob_sources.ordered.")
    ordered_sources = blob_sources_payload.get("ordered")
    if not isinstance(ordered_sources, Sequence):
        raise ValueError("blob_sources.ordered must be a list.")
    blob_sources = _load_blob_sources(ordered_sources)  # type: ignore[arg-type]

    field_paths_payload = data.get("field_paths")
    if not isinstance(field_paths_payload, Mapping):
        raise ValueError("Profile must include field_paths.")
    field_paths = _load_field_paths(field_paths_payload)

    normalization_payload = data.get("normalization")
    if isinstance(normalization_payload, Mapping):
        normalization = _load_normalization(normalization_payload)  # type: ignore[arg-type]
    else:
        normalization = _load_normalization({})

    validation_payload = data.get("validation")
    if not isinstance(validation_payload, Mapping):
        raise ValueError("Profile must include validation.")
    validation = ValidationRules(
        require_brand=bool(validation_payload.get("require_brand", True)),
        require_title=bool(validation_payload.get("require_title", True)),
        price_must_be_numeric=bool(
            validation_payload.get("price_must_be_numeric", True)
        ),
        reject_if_zero_variants=bool(
            validation_payload.get("reject_if_zero_variants", False)
        ),
    )

    category_hints = _to_tuple(data.get("category_hints"))
    category_urls = _to_tuple(data.get("category_urls"))
    raw_claim_mapping = data.get("claim_mapping")
    claim_mapping = (
        raw_claim_mapping if isinstance(raw_claim_mapping, Mapping) else None
    )

    return PDPProfile(
        profile_name=profile_name,
        retailer=retailer,
        base_url=base_url,
        display_name=display_name,
        category_hints=category_hints,
        category_urls=category_urls,
        parent_rules=parent_rules,
        id_extractors=id_extractors,
        blob_sources=blob_sources,
        field_paths=field_paths,
        normalization=normalization,
        validation=validation,
        claim_mapping=claim_mapping,
    )


def iter_profile_summaries(root: Path | None = None) -> tuple[ProfileSummary, ...]:
    """Return the available profile metadata."""

    base_path = root or CONFIG_ROOT
    if not base_path.exists():
        return ()

    summaries: list[ProfileSummary] = []
    for path in sorted(base_path.glob("*.json")):
        try:
            profile = load_profile(path, root=base_path)
        except Exception:
            continue
        summaries.append(
            ProfileSummary(
                profile_name=profile.profile_name,
                retailer=profile.retailer,
                display_name=profile.display_name,
                path=path,
            )
        )
    return tuple(summaries)


__all__ = ["CONFIG_ROOT", "ProfileSummary", "iter_profile_summaries", "load_profile"]
