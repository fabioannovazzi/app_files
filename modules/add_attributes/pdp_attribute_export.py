from __future__ import annotations

import datetime as dt
import json
import logging
import re
import zlib
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Sequence
from urllib.parse import urlparse

import polars as pl
import requests

from modules.add_attributes.attribute_classification import (
    NOT_IN_TAXONOMY_VALUE,
    _leaf_synonym_map,
    _normalize_for_allowed,
    _parse_spf_value,
    _strip_annotations_for_unknowns,
    classify_attributes_for_products,
    classify_product_attributes,
)
from modules.add_attributes.attribute_taxonomy import (
    get_attribute_taxonomy,
    get_category_alias_map,
    get_runtime_attribute_taxonomy,
)
from modules.add_attributes.explicit_declaration_classifier import (
    classify_explicit_declarations_with_evidence,
    load_explicit_declaration_rules,
)
from modules.add_attributes.explicit_precision_metrics import (
    compute_explicit_precision_metrics,
)
from modules.pdp.attribute_resolution_history import (
    append_resolution_ledger_rows,
)
from modules.pdp.attribute_resolution_history import (
    build_run_id as build_resolution_run_id,
)
from modules.pdp.attribute_resolution_history import (
    read_resolution_consensus,
    write_resolution_consensus,
)
from modules.pdp.canonical import compute_canonical_values
from modules.pdp.hybrid_overlay import annotate_market_hybrid_claims
from modules.pdp.postgres_compat import connect_pdp_database, pdp_database_exists
from modules.pdp.review_constants import DEFAULT_PDP_STORE_PATH
from modules.pdp.store import (
    AttributeAuditRecord,
    AttributeValueRecord,
    CanonicalProductRecord,
    PDPStore,
)
from modules.pdp.ulta_taxonomy_bridge import (
    ULTA_TAXONOMY_BRIDGES,
    attribute_labels_for_filter_family,
    bridged_ulta_category_keys,
    canonicalize_ulta_category_key,
    claim_only_filter_families_for_category,
    get_ulta_taxonomy_bridge,
)
from modules.utilities.config import get_naming_params
from modules.utilities.utils import get_schema_and_column_names

LOGGER = logging.getLogger(__name__)
_DEFAULT_LINKS_PATH = Path("data/pdp/links.json")
ATTRIBUTE_LIST_SEPARATOR = " | "

_PDP_REVIEW_KEYS = {"reviews_positive", "reviews_negative"}
_DETERMINISTIC_PARENT_SOURCE_CHANNELS = (
    "summary",
    "features",
    "description_short",
)
_DETERMINISTIC_VARIANT_SOURCE_CHANNELS = ("variant_name",)
_PDP_SOURCE_SEGMENT_SCHEMA: dict[str, pl.DataType] = {
    "retailer": pl.Utf8,
    "row_type": pl.Utf8,
    "parent_product_id": pl.Utf8,
    "variant_id": pl.Utf8,
    "category_key": pl.Utf8,
    "source_channel": pl.Utf8,
    "segment_id": pl.Utf8,
    "segment_order": pl.Int64,
    "source_path": pl.Utf8,
    "segment_text": pl.Utf8,
    "normalized_text": pl.Utf8,
    "label": pl.Utf8,
    "subtype": pl.Utf8,
}
_PDP_SEGMENT_WHITESPACE_RE = re.compile(r"\s+")
_ATTRIBUTE_PLACEHOLDERS = {
    "",
    "n/a",
    "na",
    "none",
    "unknown",
    "n/a (not stated)",
    "not stated",
    NOT_IN_TAXONOMY_VALUE,
}
_ATTRIBUTE_PLACEHOLDER_CANONICAL = {
    str(item).strip().casefold()
    for item in _ATTRIBUTE_PLACEHOLDERS
    if isinstance(item, str)
}
ATTRIBUTE_VALUE_SOURCE_PRIORITY = (
    "deterministic_explicit",
    "retailer_filter",
    "codex",
    "vision",
    "web",
    "llm",
    "deterministic",
    "cross_retailer_fill",
    "parent_propagation",
)
_ATTRIBUTE_VALUE_SOURCE_RANK = {
    source: index for index, source in enumerate(ATTRIBUTE_VALUE_SOURCE_PRIORITY)
}
_LOW_COVERAGE_EXTRA_INVALID_RATE = 0.30
_LLM_VARIANT_CONTEXT_LIMIT = 20
_ULTA_BRIDGED_RETAILER_CATEGORY_KEYS = frozenset(ULTA_TAXONOMY_BRIDGES)
_ULTA_BRIDGED_EXPORT_CATEGORY_KEYS = frozenset(
    {bridge.category_key for bridge in ULTA_TAXONOMY_BRIDGES.values()}
    | {bridge.canonical_category for bridge in ULTA_TAXONOMY_BRIDGES.values()}
)
_ULTA_PRIMARY_TARGET_COLUMNS = {
    "finish": "finish",
    "form": "form",
    "coverage": "coverage",
    "color": "color family",
    "color_lips": "color family",
    "spf": "spf",
    "skin_type": "skin type",
    "concern": "skin concern",
}

ValueKind = Literal["meaningful", "placeholder", "taxonomy_miss"]


def _expanded_requested_category_keys(
    categories: Sequence[str] | None,
) -> set[str] | None:
    if not categories:
        return None
    expanded: set[str] = set()
    for category in categories:
        normalized = _normalize_key(str(category))
        if not normalized:
            continue
        expanded.update(bridged_ulta_category_keys(normalized))
    return expanded or None


def _canonicalize_category_key_value(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return text
    canonical = canonicalize_ulta_category_key(text)
    return canonical or text


def _canonicalize_category_key_columns(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df
    columns_to_update = [
        column for column in ("category_key", "category_id") if column in df.columns
    ]
    if not columns_to_update:
        return df
    return df.with_columns(
        [
            pl.col(column)
            .cast(pl.Utf8, strict=False)
            .map_elements(_canonicalize_category_key_value, return_dtype=pl.Utf8)
            .alias(column)
            for column in columns_to_update
        ]
    )


def _normalize_stage_value(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.casefold()
    placeholder_aliases = {
        "n/a",
        "n/a (not stated)",
        "na",
        "none",
        "unknown",
        "not stated",
    }
    if lowered in placeholder_aliases:
        return "N/A"
    if lowered == NOT_IN_TAXONOMY_VALUE.casefold():
        return NOT_IN_TAXONOMY_VALUE
    return text


def _ulta_authority_token(column_name: str) -> str:
    return _normalize_key(column_name).replace(" ", "_")


def _ulta_authority_column_names(target_column: str) -> tuple[str, str, str]:
    token = _ulta_authority_token(target_column)
    return (f"our_{token}", f"ulta_{token}", f"{token}_authority_source")


def _ulta_filter_column_name(filter_family: str) -> str:
    return f"ulta_filter_{_ulta_authority_token(filter_family)}"


def _is_obviously_invalid_ulta_filter_value(value: object | None) -> bool:
    text = _normalize_stage_value(value)
    if text is None:
        return True
    lowered = text.casefold()
    if lowered in _ATTRIBUTE_PLACEHOLDER_CANONICAL:
        return True
    if any(
        marker in text
        for marker in ("http://", "https://", "<", ">", "{", "}", "[", "]")
    ):
        return True
    return re.search(r"[0-9A-Za-z]", text) is None


def _normalized_ulta_filter_value(value: object | None) -> str | None:
    if _is_obviously_invalid_ulta_filter_value(value):
        return None
    return _normalize_stage_value(value)


def _is_meaningful_text_expr(column_name: str) -> pl.Expr:
    placeholders = list(_ATTRIBUTE_PLACEHOLDER_CANONICAL) + [""]
    return pl.col(column_name).is_not_null() & ~pl.col(column_name).cast(
        pl.Utf8, strict=False
    ).fill_null("").str.strip_chars().str.to_lowercase().is_in(placeholders)


def _empty_ulta_authority_overrides_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "retailer": pl.Utf8,
            "parent_product_id": pl.Utf8,
            "category_key": pl.Utf8,
        }
    )


@lru_cache(maxsize=1)
def _taxonomy_attribute_labels_by_category() -> dict[str, dict[str, str]]:
    taxonomy = get_attribute_taxonomy()
    categories = taxonomy.get("categories")
    if not isinstance(categories, list):
        return {}

    out: dict[str, dict[str, str]] = {}
    for category in categories:
        if not isinstance(category, Mapping):
            continue
        category_key = _normalize_key(category.get("id")).replace(" ", "_")
        if not category_key:
            continue
        labels: dict[str, str] = {}
        for attribute in category.get("attributes") or []:
            if not isinstance(attribute, Mapping):
                continue
            label = _normalize_stage_value(attribute.get("label"))
            if label is None:
                continue
            labels.setdefault(_normalize_key(label), label)
        out[category_key] = labels
    return out


def _resolve_ulta_target_column(
    *,
    category_key: str,
    filter_family: str,
    available_columns: Sequence[str],
) -> str | None:
    available_map = {_normalize_key(column): column for column in available_columns}
    normalized_family = _normalize_key(filter_family)

    explicit_target = _ULTA_PRIMARY_TARGET_COLUMNS.get(normalized_family)
    if explicit_target is not None:
        resolved = available_map.get(_normalize_key(explicit_target))
        if resolved is not None:
            return resolved

    bridge = get_ulta_taxonomy_bridge(category_key)
    canonical_category = (
        bridge.canonical_category
        if bridge is not None
        else _normalize_key(category_key).replace(" ", "_")
    )
    category_labels = _taxonomy_attribute_labels_by_category().get(
        canonical_category, {}
    )
    candidate_columns: list[str] = []
    for label in attribute_labels_for_filter_family(
        filter_family,
        category_key=category_key,
    ):
        normalized_label = _normalize_key(label)
        actual_label = category_labels.get(normalized_label)
        if actual_label is None:
            continue
        actual_column = available_map.get(normalized_label)
        if actual_column and actual_column not in candidate_columns:
            candidate_columns.append(actual_column)
    if len(candidate_columns) == 1:
        return candidate_columns[0]
    return None


def _load_latest_ulta_authority_overrides(
    pdp_store_path: Path | str,
    *,
    category_keys: Sequence[str],
) -> pl.DataFrame:
    requested_bridges = {
        bridge.category_key: bridge
        for category in category_keys
        if (bridge := get_ulta_taxonomy_bridge(category)) is not None
    }
    if not requested_bridges:
        return _empty_ulta_authority_overrides_frame()
    requested_retailer_categories = sorted(requested_bridges)

    path = Path(pdp_store_path)
    if not pdp_database_exists(path):
        raise FileNotFoundError(f"PDP database not found: {path}")

    placeholders = ",".join("?" for _ in requested_retailer_categories)
    query = f"""
        WITH latest AS (
            SELECT category_key, MAX(crawl_ts) AS latest_crawl_ts
            FROM retailer_filter_observations
            WHERE retailer = 'ulta'
              AND category_key IN ({placeholders})
            GROUP BY category_key
        )
        SELECT
            observation.retailer,
            observation.parent_product_id,
            observation.category_key,
            observation.filter_family,
            observation.filter_value
        FROM retailer_filter_observations AS observation
        INNER JOIN latest
            ON latest.category_key = observation.category_key
           AND latest.latest_crawl_ts = observation.crawl_ts
        WHERE observation.retailer = 'ulta'
          AND observation.category_key IN ({placeholders})
          AND COALESCE(TRIM(observation.parent_product_id), '') != ''
    """
    params = [*requested_retailer_categories, *requested_retailer_categories]

    with connect_pdp_database(path) as conn:
        try:
            rows = conn.execute(query, params).fetchall()
        except Exception:
            return _empty_ulta_authority_overrides_frame()

    grouped: dict[tuple[str, str, str], dict[str, set[str]]] = {}
    for retailer, parent_product_id, category_key, filter_family, filter_value in rows:
        normalized_category = _normalize_key(category_key).replace(" ", "_")
        bridge = requested_bridges.get(normalized_category)
        if bridge is None:
            continue
        normalized_family = _normalize_key(filter_family)
        if normalized_family not in bridge.filter_families:
            continue
        normalized_value = _normalized_ulta_filter_value(filter_value)
        if normalized_value is None:
            continue
        group_key = (
            str(retailer or "").strip().lower(),
            str(parent_product_id or "").strip(),
            bridge.category_key,
        )
        family_values = grouped.setdefault(group_key, {})
        family_values.setdefault(normalized_family, set()).add(normalized_value)

    if not grouped:
        return _empty_ulta_authority_overrides_frame()

    rows_out: list[dict[str, str]] = []
    for (
        retailer,
        parent_product_id,
        retailer_category_key,
    ), family_values in grouped.items():
        bridge = requested_bridges[retailer_category_key]
        alias_categories = {bridge.category_key, bridge.canonical_category}
        for export_category_key in sorted(alias_categories):
            out = {
                "retailer": retailer,
                "parent_product_id": parent_product_id,
                "category_key": export_category_key,
            }
            for filter_family, values in family_values.items():
                out[_ulta_filter_column_name(filter_family)] = " | ".join(
                    sorted(values)
                )
            rows_out.append(out)

    return pl.DataFrame(rows_out, strict=False, infer_schema_length=None)


def _apply_ulta_face_authority_to_export_frame(
    df: pl.DataFrame,
    *,
    authority_df: pl.DataFrame,
) -> pl.DataFrame:
    if df.is_empty():
        return df
    columns, _ = get_schema_and_column_names(df)
    required = {"retailer", "parent_product_id", "category_key"}
    if any(column not in columns for column in required):
        return df

    frame = df
    normalized_categories = sorted(_ULTA_BRIDGED_EXPORT_CATEGORY_KEYS)
    face_scope = pl.col("retailer").cast(pl.Utf8, strict=False).fill_null(
        ""
    ).str.to_lowercase().eq("ulta") & pl.col("category_key").cast(
        pl.Utf8, strict=False
    ).fill_null(
        ""
    ).map_elements(
        _normalize_key, return_dtype=pl.Utf8
    ).is_in(
        normalized_categories
    )

    if not authority_df.is_empty():
        frame = frame.join(
            authority_df,
            on=["retailer", "parent_product_id", "category_key"],
            how="left",
        )

    frame_columns, _ = get_schema_and_column_names(frame)
    active_categories = {
        _normalize_key(row.get("category_key")).replace(" ", "_")
        for row in frame.select(["retailer", "category_key"]).to_dicts()
        if _normalize_key(row.get("retailer")) == "ulta"
        and get_ulta_taxonomy_bridge(row.get("category_key")) is not None
    }
    target_specs: dict[str, list[tuple[str, str]]] = {}
    for category_key in sorted(active_categories):
        bridge = get_ulta_taxonomy_bridge(category_key)
        if bridge is None:
            continue
        for filter_family in bridge.filter_families:
            raw_column = _ulta_filter_column_name(filter_family)
            target_column = _resolve_ulta_target_column(
                category_key=category_key,
                filter_family=filter_family,
                available_columns=frame_columns,
            )
            if target_column is None:
                continue
            target_specs.setdefault(target_column, []).append(
                (category_key, raw_column)
            )

    for target_column in sorted(target_specs):
        our_column, ulta_column, source_column = _ulta_authority_column_names(
            target_column
        )
        category_specs = target_specs[target_column]
        mapped_scope = face_scope & pl.col("category_key").cast(
            pl.Utf8, strict=False
        ).fill_null("").map_elements(
            lambda value: _normalize_key(value).replace(" ", "_"),
            return_dtype=pl.Utf8,
        ).is_in(
            sorted({category for category, _ in category_specs})
        )
        original_expr = (
            pl.col(target_column).cast(pl.Utf8, strict=False)
            if target_column in frame_columns
            else pl.lit(None, dtype=pl.Utf8)
        )
        frame = frame.with_columns(
            pl.when(mapped_scope)
            .then(original_expr)
            .otherwise(pl.lit(None, dtype=pl.Utf8))
            .alias(our_column)
        )

        ulta_expr = pl.lit(None, dtype=pl.Utf8)
        for category_key, raw_column in category_specs:
            raw_expr = (
                pl.col(raw_column).cast(pl.Utf8, strict=False)
                if raw_column in frame_columns
                else pl.lit(None, dtype=pl.Utf8)
            )
            category_scope = (
                pl.col("category_key")
                .cast(pl.Utf8, strict=False)
                .fill_null("")
                .map_elements(
                    lambda value: _normalize_key(value).replace(" ", "_"),
                    return_dtype=pl.Utf8,
                )
                .eq(category_key)
            )
            ulta_expr = pl.when(category_scope).then(raw_expr).otherwise(ulta_expr)

        frame = frame.with_columns(ulta_expr.alias(ulta_column))

        ulta_has_value = face_scope & _is_meaningful_text_expr(ulta_column)
        our_has_value = mapped_scope & _is_meaningful_text_expr(our_column)
        frame = frame.with_columns(
            [
                pl.when(ulta_has_value)
                .then(pl.col(ulta_column).cast(pl.Utf8, strict=False))
                .when(our_has_value)
                .then(pl.col(our_column).cast(pl.Utf8, strict=False))
                .otherwise(original_expr)
                .alias(target_column),
                pl.when(ulta_has_value)
                .then(pl.lit("ulta"))
                .when(our_has_value)
                .then(pl.lit("ours"))
                .when(mapped_scope)
                .then(pl.lit("missing"))
                .otherwise(pl.lit(None, dtype=pl.Utf8))
                .alias(source_column),
            ]
        )
    return frame


def _apply_ulta_face_authority_to_exports(
    pdp_store_path: Path | str,
    *,
    parents_df: pl.DataFrame,
    variants_df: pl.DataFrame,
    combined_df: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    category_keys: set[str] = set()
    for frame in (parents_df, variants_df, combined_df):
        if frame.is_empty():
            continue
        columns, _ = get_schema_and_column_names(frame)
        if "category_key" not in columns or "retailer" not in columns:
            continue
        category_keys.update(
            {
                _normalize_key(row["category_key"]).replace(" ", "_")
                for row in frame.select(["retailer", "category_key"]).to_dicts()
                if _normalize_key(row.get("retailer")) == "ulta"
                and get_ulta_taxonomy_bridge(row.get("category_key")) is not None
            }
        )
    if not category_keys:
        return parents_df, variants_df, combined_df

    authority_df = _load_latest_ulta_authority_overrides(
        pdp_store_path,
        category_keys=sorted(category_keys),
    )
    return (
        _apply_ulta_face_authority_to_export_frame(
            parents_df, authority_df=authority_df
        ),
        _apply_ulta_face_authority_to_export_frame(
            variants_df, authority_df=authority_df
        ),
        _apply_ulta_face_authority_to_export_frame(
            combined_df, authority_df=authority_df
        ),
    )


def _classify_stage_value(value: str | None) -> ValueKind:
    if value is None:
        return "placeholder"
    lowered = value.strip().casefold()
    if lowered == NOT_IN_TAXONOMY_VALUE.casefold():
        return "taxonomy_miss"
    if lowered in _ATTRIBUTE_PLACEHOLDER_CANONICAL:
        return "placeholder"
    return "meaningful"


def _choose_stage_value(det_value: str | None, llm_value: str | None) -> str | None:
    det_kind = _classify_stage_value(det_value)
    llm_kind = _classify_stage_value(llm_value)

    if llm_kind == "meaningful":
        return llm_value

    if llm_kind == "taxonomy_miss":
        if det_kind == "meaningful":
            return det_value
        if det_kind == "placeholder":
            return llm_value
        return llm_value if llm_value is not None else det_value

    # LLM returned a placeholder (including null/empty)
    if det_kind == "meaningful":
        return det_value
    if det_kind == "taxonomy_miss":
        return det_value
    return llm_value if llm_value is not None else det_value


def _choose_stage_value_with_explicit(
    explicit_value: str | None,
    det_value: str | None,
    llm_value: str | None,
) -> str | None:
    explicit_kind = _classify_stage_value(explicit_value)
    if explicit_kind == "meaningful":
        return explicit_value
    if explicit_kind == "taxonomy_miss":
        return (
            explicit_value
            if explicit_value is not None
            else _choose_stage_value(det_value, llm_value)
        )
    return _choose_stage_value(det_value, llm_value)


def _choose_canonical_attribute_value_and_source(
    values_by_source: Mapping[str, str | None],
) -> tuple[str | None, str | None]:
    """Choose one value and retain the exact source that won precedence."""

    explicit_value = values_by_source.get("deterministic_explicit")
    explicit_kind = _classify_stage_value(explicit_value)
    if explicit_kind in {"meaningful", "taxonomy_miss"}:
        return explicit_value, "deterministic_explicit"

    retailer_value = values_by_source.get("retailer_filter")
    retailer_kind = _classify_stage_value(retailer_value)
    if retailer_kind in {"meaningful", "taxonomy_miss"}:
        return retailer_value, "retailer_filter"

    # A Codex mapping is an explicit semantic decision. Its negative and
    # uncertain outcomes intentionally suppress retained Vision/Web/LLM values
    # so an old model claim is not presented as newly verified.
    if "codex" in values_by_source:
        return values_by_source["codex"], "codex"

    ranked_values = sorted(
        (
            (source, value)
            for source, value in values_by_source.items()
            if source not in {"deterministic_explicit", "retailer_filter", "codex"}
        ),
        key=lambda item: (_ATTRIBUTE_VALUE_SOURCE_RANK.get(item[0], 100), item[0]),
    )
    for desired_kind in ("meaningful", "taxonomy_miss", "placeholder"):
        for source, value in ranked_values:
            if _classify_stage_value(value) == desired_kind and value is not None:
                return value, source
    return (
        explicit_value,
        (
            "deterministic_explicit"
            if "deterministic_explicit" in values_by_source
            else None
        ),
    )


def _choose_canonical_attribute_value(
    values_by_source: Mapping[str, str | None],
) -> str | None:
    """Choose one value while honoring authoritative explicit negative decisions."""

    return _choose_canonical_attribute_value_and_source(values_by_source)[0]


def _apply_llm_choice(
    row: dict[str, object], column_name: str, llm_value: object | None
) -> bool:
    existing_raw = row.get(column_name)
    det_normalized = _normalize_stage_value(existing_raw)
    llm_normalized = _normalize_stage_value(llm_value)
    chosen = _choose_stage_value(det_normalized, llm_normalized)
    selected_from_llm = (
        llm_normalized is not None
        and llm_normalized == chosen
        and _classify_stage_value(llm_normalized) != "placeholder"
        and llm_normalized != det_normalized
    )
    LOGGER.debug(
        "LLM choice column=%s existing=%s llm=%s -> chosen=%s",
        column_name,
        det_normalized,
        llm_normalized,
        chosen,
    )
    if chosen is None:
        row[column_name] = None
        return
    if det_normalized == chosen and existing_raw is not None:
        existing_clean = str(existing_raw).strip()
        if existing_clean == chosen:
            row[column_name] = existing_raw
            return selected_from_llm
        # fall through so canonicalized placeholders like "n/a (not stated)"
        # replace the raw value with their normalized form (e.g., "n/a")
    if llm_normalized == chosen and llm_value is not None:
        llm_clean = str(llm_value).strip()
        if llm_clean == chosen:
            row[column_name] = llm_value
            return selected_from_llm
    row[column_name] = chosen
    return selected_from_llm


def _serialize_frame(df: pl.DataFrame) -> bytes:
    payload = {
        "columns": df.columns,
        "rows": df.to_dicts(),
    }
    return zlib.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def _deserialize_frame(payload: bytes) -> pl.DataFrame:
    try:
        raw = zlib.decompress(payload)
    except zlib.error:
        raw = payload
    data = json.loads(raw.decode("utf-8"))
    rows = data.get("rows") or []
    columns = data.get("columns") or []
    if rows:
        sanitized_rows = []
        for row in rows:
            if not isinstance(row, Mapping):
                sanitized_rows.append(row)
                continue
            cleaned: dict[str, Any] = {}
            for key, value in row.items():
                if isinstance(value, str):
                    stripped = value.strip()
                    if not stripped:
                        cleaned[key] = None
                        continue
                    if stripped.casefold() in _ATTRIBUTE_PLACEHOLDER_CANONICAL:
                        cleaned[key] = None
                        continue
                    cleaned[key] = stripped
                else:
                    cleaned[key] = value
            for missing in columns:
                cleaned.setdefault(missing, None)
            sanitized_rows.append(cleaned)
        try:
            frame = pl.DataFrame(
                sanitized_rows, infer_schema_length=len(sanitized_rows)
            )
        except Exception as exc:  # pragma: no cover - defensive deserialization
            LOGGER.warning(
                "Failed to infer schema for cached frame; coercing values to Utf8 (error=%s)",
                exc,
            )
            coerced_rows: list[dict[str, Any]] = []
            for row in sanitized_rows:
                if not isinstance(row, Mapping):
                    continue
                coerced: dict[str, Any] = {}
                for col in columns:
                    value = row.get(col)
                    if value is None:
                        coerced[col] = None
                        continue
                    if isinstance(value, (list, dict, tuple)):
                        try:
                            coerced[col] = json.dumps(value, ensure_ascii=False)
                        except TypeError:
                            coerced[col] = str(value)
                        continue
                    coerced[col] = str(value)
                coerced_rows.append(coerced)
            schema = {col: pl.Utf8 for col in columns}
            frame = pl.DataFrame(coerced_rows, schema=schema)

        if columns:
            missing_cols = [col for col in columns if col not in frame.columns]
            if missing_cols:
                frame = frame.with_columns(
                    [pl.lit(None).alias(col) for col in missing_cols]
                )
            frame = frame.select(columns)
        return frame
    if columns:
        return pl.DataFrame({col: [] for col in columns})
    return pl.DataFrame()


def _serialize_metadata(metadata: Mapping[str, Any]) -> bytes:
    return zlib.compress(json.dumps(metadata, ensure_ascii=False).encode("utf-8"))


def _deserialize_metadata(payload: bytes) -> dict[str, Any]:
    try:
        raw = zlib.decompress(payload)
    except zlib.error:
        raw = payload
    return json.loads(raw.decode("utf-8"))


def _annotate_pareto_and_price(
    parent_df: pl.DataFrame,
    variant_df: pl.DataFrame,
    retailers: Sequence[str] | None,
) -> tuple[pl.DataFrame, dict[str, dict[str, object]]]:
    """Enrich parent_df with sales-based Pareto buckets and price bands."""
    # Lazy import to avoid circular dependency at module load time.
    from modules.pdp.sales_join import load_sales_data

    if parent_df.is_empty():
        return parent_df, {}

    # Normalize retailer scope for filtering and sales lookups.
    retailer_scope = (
        {str(r).strip().lower() for r in retailers if str(r).strip()}
        if retailers
        else None
    )

    # Build a lookup of median variant price per parent.
    price_lookup: dict[tuple[str, str], float] = {}
    if not variant_df.is_empty() and "price_raw" in variant_df.columns:
        price_df = variant_df.with_columns(
            pl.col("retailer")
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("retailer_norm"),
            pl.col("parent_product_id")
            .cast(pl.Utf8)
            .str.strip_chars()
            .alias("parent_id_norm"),
            pl.col("price_raw")
            .map_elements(_parse_price_to_float, return_dtype=pl.Float64)
            .alias("price_numeric"),
        ).drop_nulls(subset=["price_numeric"])
        if retailer_scope:
            price_df = price_df.filter(
                pl.col("retailer_norm").is_in(list(retailer_scope))
            )
        if not price_df.is_empty():
            price_stats = price_df.group_by(["retailer_norm", "parent_id_norm"]).agg(
                pl.col("price_numeric").median().alias("price_value")
            )
            for row in price_stats.iter_rows(named=True):
                price_lookup[(row["retailer_norm"], row["parent_id_norm"])] = float(
                    row["price_value"]
                )

    annotations: list[dict[str, object]] = []
    category_meta: dict[str, dict[str, object]] = {}

    parent_df_work = parent_df.with_columns(
        pl.col("retailer")
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.to_lowercase()
        .alias("retailer_norm"),
        pl.col("parent_product_id")
        .cast(pl.Utf8)
        .str.strip_chars()
        .alias("parent_id_norm"),
        pl.col("category_key")
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.to_lowercase()
        .alias("category_norm"),
    )

    # Preload sales once per retailer.
    sales_cache: dict[str, pl.DataFrame] = {}

    for retailer_val in sorted(
        parent_df_work.get_column("retailer_norm").unique().to_list()
    ):
        if not retailer_val:
            continue
        if retailer_scope and retailer_val not in retailer_scope:
            continue

        parents_r = parent_df_work.filter(pl.col("retailer_norm") == retailer_val)
        categories_r = parents_r.get_column("category_norm").unique().to_list()

        # Load and aggregate sales for this retailer.
        sales_df = load_sales_data(retailer_val)
        if not sales_df.is_empty():
            sales_df = sales_df.filter(pl.col("merchant") == retailer_val)
            sales_by_sku = (
                sales_df.group_by("sku")
                .agg(pl.col("sales").sum().alias("sales"))
                .with_columns(
                    pl.col("sku").cast(pl.Utf8).str.strip_chars().alias("sku_norm")
                )
            )
        else:
            sales_by_sku = pl.DataFrame({"sku_norm": [], "sales": []})
        sales_cache[retailer_val] = sales_by_sku

        variants_r = variant_df
        if not variants_r.is_empty():
            variants_r = variants_r.with_columns(
                pl.col("retailer")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_lowercase()
                .alias("retailer_norm"),
                pl.col("variant_id")
                .cast(pl.Utf8)
                .str.strip_chars()
                .alias("variant_id_norm"),
                pl.col("parent_product_id")
                .cast(pl.Utf8)
                .str.strip_chars()
                .alias("parent_id_norm"),
                pl.col("category_key")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_lowercase()
                .alias("category_norm"),
            ).filter(pl.col("retailer_norm") == retailer_val)
        sales_joined = pl.DataFrame()
        if not variants_r.is_empty() and not sales_by_sku.is_empty():
            sales_joined = variants_r.join(
                sales_by_sku,
                left_on="variant_id_norm",
                right_on="sku_norm",
                how="left",
            ).with_columns(pl.col("sales").fill_null(0.0))

        sales_by_parent = (
            sales_joined.group_by(["parent_id_norm", "category_norm"]).agg(
                pl.col("sales").sum().alias("sales")
            )
            if not sales_joined.is_empty()
            else pl.DataFrame({"parent_id_norm": [], "category_norm": [], "sales": []})
        )

        # Precompute price list per category for band thresholds.
        price_per_parent = {}
        if price_lookup:
            for row in parents_r.iter_rows(named=True):
                pid = row["parent_id_norm"]
                price = price_lookup.get((retailer_val, pid))
                if price is not None:
                    price_per_parent[pid] = price

        for category_val in categories_r:
            parents_cat = parents_r.filter(pl.col("category_norm") == category_val)
            parent_ids_cat = parents_cat.get_column("parent_id_norm").to_list()
            # Sales per parent (default 0).
            sales_map: dict[str, float] = {pid: 0.0 for pid in parent_ids_cat}
            if not sales_by_parent.is_empty():
                for row in sales_by_parent.filter(
                    pl.col("category_norm") == category_val
                ).iter_rows(named=True):
                    sales_map[str(row["parent_id_norm"])] = float(
                        row.get("sales") or 0.0
                    )

            total_sales = sum(sales_map.values())
            ordered_ids = sorted(
                parent_ids_cat,
                key=lambda pid: (-sales_map.get(pid, 0.0), pid),
            )

            # Price thresholds for this category.
            prices_cat = [
                price_per_parent.get(pid)
                for pid in parent_ids_cat
                if price_per_parent.get(pid) is not None
            ]
            thresholds: tuple[float | None, float | None] = (None, None)

            # Metadata accumulators
            meta_counts = {"A": 0, "B": 0, "C": 0}
            meta_sales = {"A": 0.0, "B": 0.0, "C": 0.0}
            price_band_counts: dict[str, int] = {"premium": 0, "mid": 0, "value": 0}

            cumulative = 0.0
            for rank, pid in enumerate(ordered_ids, start=1):
                sales_val = sales_map.get(pid, 0.0)
                share = (sales_val / total_sales) if total_sales > 0 else None
                cumulative = (
                    cumulative + (share or 0.0) if share is not None else cumulative
                )
                bucket: str | None
                if share is None:
                    bucket = None
                elif cumulative <= 0.80 + 1e-9:
                    bucket = "A"
                elif cumulative <= 0.95 + 1e-9:
                    bucket = "B"
                else:
                    bucket = "C"

                price_val = price_per_parent.get(pid)
                band, thresholds = _assign_price_band(prices_cat, price_val)

                if bucket in meta_counts:
                    meta_counts[bucket] += 1
                    if sales_val:
                        meta_sales[bucket] += sales_val
                if band in price_band_counts:
                    price_band_counts[band] += 1

                annotations.append(
                    {
                        "retailer_norm": retailer_val,
                        "parent_id_norm": pid,
                        "category_norm": category_val,
                        "sales_share": share,
                        "cumulative_sales_share": (
                            cumulative if share is not None else None
                        ),
                        "pareto_rank": rank if share is not None else None,
                        "pareto_bucket": bucket,
                        "price_band": band,
                    }
                )

            # Capture metadata per (retailer, category)
            total_count = len(parent_ids_cat)
            total_sales_safe = total_sales or 0.0
            if total_count > 0:
                key = f"{retailer_val}:{category_val}"
                category_meta[key] = {
                    "pareto_shares": {
                        "A": (
                            meta_sales["A"] / total_sales_safe
                            if total_sales_safe
                            else 0.0
                        ),
                        "B": (
                            meta_sales["B"] / total_sales_safe
                            if total_sales_safe
                            else 0.0
                        ),
                        "C": (
                            meta_sales["C"] / total_sales_safe
                            if total_sales_safe
                            else 0.0
                        ),
                    },
                    "pareto_counts": meta_counts,
                    "price_band_shares": {
                        "premium": price_band_counts["premium"] / total_count,
                        "mid": price_band_counts["mid"] / total_count,
                        "value": price_band_counts["value"] / total_count,
                    },
                }

    if not annotations:
        return parent_df, {}

    try:
        annot_df = pl.DataFrame(
            annotations,
            schema={
                "retailer_norm": pl.Utf8,
                "parent_id_norm": pl.Utf8,
                "category_norm": pl.Utf8,
                "sales_share": pl.Float64,
                "cumulative_sales_share": pl.Float64,
                "pareto_rank": pl.Int64,
                "pareto_bucket": pl.Utf8,
                "price_band": pl.Utf8,
            },
        )
    except Exception:
        # Fallback: let Polars infer with full length to avoid mixed-type failures.
        try:
            annot_df = pl.DataFrame(annotations, infer_schema_length=len(annotations))
        except Exception:
            LOGGER.exception(
                "Failed to build pareto/price annotations; skipping enrichment"
            )
            return parent_df, category_meta

    enriched = parent_df_work.join(
        annot_df,
        on=["retailer_norm", "parent_id_norm", "category_norm"],
        how="left",
    )
    enriched = enriched.drop(["retailer_norm", "parent_id_norm", "category_norm"])
    return enriched, category_meta


def _prune_empty_columns(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df
    keep_cols: list[str] = []
    height = df.height
    for column in df.columns:
        series = df.get_column(column)
        if series.null_count() == height:
            continue
        if series.dtype in (pl.Utf8, pl.Categorical):
            stripped = series.cast(pl.Utf8).fill_null("").str.strip_chars()
            if stripped.eq("").all():
                continue
        keep_cols.append(column)
    if not keep_cols:
        return df
    if len(keep_cols) == len(df.columns):
        return df
    return df.select(keep_cols)


def _normalize_key(value: str | None) -> str:
    if not value:
        return ""
    compact = " ".join(value.strip().split())
    return compact.lower().replace(" ", "_")


def _normalize_links_lookup_url(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(str(url).strip())
    path = parsed.path or ""
    if not path:
        return ""
    return parsed._replace(query="", fragment="", params="").geturl()


def _load_links_category_lookup(
    links_path: Path | None = None,
) -> dict[tuple[str, str], str]:
    memberships = _load_links_category_memberships(links_path)
    return {key: categories[0] for key, categories in memberships.items() if categories}


def _load_links_category_memberships(
    links_path: Path | None = None,
) -> dict[tuple[str, str], tuple[str, ...]]:
    path = links_path or _DEFAULT_LINKS_PATH
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        LOGGER.exception("Failed to load links category lookup from %s", path)
        return {}
    if not isinstance(payload, Mapping):
        return {}

    membership_lookup: dict[tuple[str, str], list[str]] = {}
    for retailer, retailer_payload in payload.items():
        retailer_key = _normalize_key(str(retailer))
        if not retailer_key or not isinstance(retailer_payload, Mapping):
            continue
        for category_key, links in retailer_payload.items():
            normalized_category = _normalize_key(str(category_key))
            if not normalized_category or not isinstance(links, Sequence):
                continue
            for link in links:
                normalized_url = _normalize_links_lookup_url(str(link))
                if not normalized_url:
                    continue
                key = (retailer_key, normalized_url)
                memberships = membership_lookup.setdefault(key, [])
                if normalized_category not in memberships:
                    memberships.append(normalized_category)
    return {key: tuple(categories) for key, categories in membership_lookup.items()}


def _category_path_example(value: object) -> str:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return " > ".join(str(item).strip() for item in value if str(item).strip())
    return ""


def _taxonomy_real_node_labels(attr: Mapping[str, object]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for node in attr.get("nodes", []) or []:
        if not isinstance(node, Mapping):
            continue
        node_id = _normalize_key(str(node.get("id") or ""))
        node_label = _normalize_stage_value(node.get("label"))
        if node_id in {"unknown", "other"} or node_label is None:
            continue
        label_text = str(node_label).strip()
        if not label_text or label_text.casefold() in _ATTRIBUTE_PLACEHOLDER_CANONICAL:
            continue
        labels.setdefault(_normalize_key(label_text), label_text)
    return labels


def _load_discovery_filter_surfaces(
    run_dir: Path,
    *,
    retailer: str,
    category_key: str,
) -> dict[str, dict[str, str]]:
    filter_path = run_dir / "retailer_filter_surfaces.csv"
    if not filter_path.is_file():
        return {}
    try:
        frame = pl.read_csv(filter_path)
    except (OSError, pl.exceptions.PolarsError):
        LOGGER.exception(
            "Failed to read discovery filter surfaces from %s", filter_path
        )
        return {}
    family_col = "filter_family" if "filter_family" in frame.columns else "family"
    value_col = "filter_value" if "filter_value" in frame.columns else "value"
    if family_col not in frame.columns or value_col not in frame.columns:
        return {}
    filtered = frame
    if "retailer" in filtered.columns:
        filtered = filtered.filter(
            pl.col("retailer")
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .str.to_lowercase()
            == retailer
        )
    if "category_key" in filtered.columns:
        filtered = filtered.filter(
            pl.col("category_key")
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .map_elements(_normalize_key, return_dtype=pl.Utf8)
            == category_key
        )
    observed: dict[str, dict[str, str]] = {}
    for row in filtered.select([family_col, value_col]).to_dicts():
        family_text = str(row.get(family_col) or "").strip()
        value_text = str(row.get(value_col) or "").strip()
        family_key = _normalize_key(family_text)
        value_key = _normalize_key(value_text)
        if not family_key or not value_key:
            continue
        observed.setdefault(family_key, {"label": family_text, "values": {}})
        family_values = observed[family_key]["values"]
        if isinstance(family_values, dict):
            family_values.setdefault(value_key, value_text)
    return observed


def _build_filter_alignment_report(
    category_branch: Mapping[str, object],
    observed_filters: Mapping[str, Mapping[str, object]],
    *,
    retailer: str | None = None,
    category_key: str | None = None,
) -> dict[str, object]:
    taxonomy_attrs: dict[str, dict[str, object]] = {}
    for attr in category_branch.get("attributes", []) or []:
        if not isinstance(attr, Mapping):
            continue
        label = str(attr.get("label") or "").strip()
        attr_key = _normalize_key(label)
        if not attr_key:
            continue
        taxonomy_attrs[attr_key] = {
            "label": label,
            "values": _taxonomy_real_node_labels(attr),
        }

    observed_keys = sorted(observed_filters)
    taxonomy_keys = sorted(taxonomy_attrs)
    normalized_retailer = _normalize_key(retailer or "")
    claim_only_families = (
        {
            _normalize_key(value)
            for value in claim_only_filter_families_for_category(category_key or "")
        }
        if normalized_retailer == "ulta"
        else set()
    )

    matched: list[str] = []
    missing: list[str] = []
    ignored: list[str] = []
    bridged_taxonomy_keys: set[str] = set()
    family_to_taxonomy_keys: dict[str, list[str]] = {}

    for family_key in observed_keys:
        if family_key in claim_only_families:
            ignored.append(family_key)
            continue

        matched_taxonomy_keys: list[str] = []
        if normalized_retailer == "ulta":
            candidate_labels = attribute_labels_for_filter_family(
                family_key,
                category_key=category_key,
            )
            for label in candidate_labels:
                candidate_key = _normalize_key(label)
                if (
                    candidate_key in taxonomy_attrs
                    and candidate_key not in matched_taxonomy_keys
                ):
                    matched_taxonomy_keys.append(candidate_key)
        elif family_key in taxonomy_attrs:
            matched_taxonomy_keys.append(family_key)

        if matched_taxonomy_keys:
            matched.append(family_key)
            family_to_taxonomy_keys[family_key] = matched_taxonomy_keys
            bridged_taxonomy_keys.update(matched_taxonomy_keys)
        else:
            missing.append(family_key)

    extras = sorted(set(taxonomy_keys) - bridged_taxonomy_keys)

    value_alignment: dict[str, dict[str, object]] = {}
    for family_key in matched:
        observed_meta = observed_filters[family_key]
        observed_values = observed_meta.get("values")
        observed_dict = observed_values if isinstance(observed_values, dict) else {}
        taxonomy_dict: dict[str, str] = {}
        for taxonomy_key in family_to_taxonomy_keys.get(family_key, []):
            taxonomy_values = taxonomy_attrs[taxonomy_key].get("values")
            if not isinstance(taxonomy_values, dict):
                continue
            for value_key, value_label in taxonomy_values.items():
                taxonomy_dict.setdefault(value_key, value_label)
        missing_values = sorted(set(observed_dict) - set(taxonomy_dict))
        extra_values = sorted(set(taxonomy_dict) - set(observed_dict))
        value_alignment[str(observed_meta.get("label") or family_key)] = {
            "filter_value_count": len(observed_dict),
            "taxonomy_value_count": len(taxonomy_dict),
            "missing_filter_values": [observed_dict[key] for key in missing_values],
            "extra_taxonomy_values": [taxonomy_dict[key] for key in extra_values],
        }

    return {
        "observed_filter_families": [
            str(observed_filters[key].get("label") or key) for key in observed_keys
        ],
        "taxonomy_attribute_labels": [
            str(taxonomy_attrs[key].get("label") or key) for key in taxonomy_keys
        ],
        "matched_filter_dimensions": [
            str(observed_filters[key].get("label") or key) for key in matched
        ],
        "missing_filter_dimensions": [
            str(observed_filters[key].get("label") or key) for key in missing
        ],
        "ignored_filter_dimensions": [
            str(observed_filters[key].get("label") or key) for key in ignored
        ],
        "bridged_taxonomy_dimensions": [
            str(taxonomy_attrs[key].get("label") or key)
            for key in sorted(bridged_taxonomy_keys)
        ],
        "extra_taxonomy_dimensions": [
            str(taxonomy_attrs[key].get("label") or key) for key in extras
        ],
        "value_alignment": value_alignment,
    }


def _load_taxonomy_cache_coverage(
    pdp_store_path: Path | str,
    *,
    retailer: str,
    category_key: str,
    category_branch: Mapping[str, object],
) -> dict[str, object] | None:
    parent_cache_path = _attribute_cache_paths(pdp_store_path, retailer=retailer)[
        "parent"
    ]
    if not parent_cache_path.is_file():
        return None
    try:
        frame = pl.read_parquet(parent_cache_path)
    except (OSError, pl.exceptions.PolarsError):
        LOGGER.exception(
            "Failed to read parent attribute cache from %s", parent_cache_path
        )
        return None
    if "category_key" not in frame.columns:
        return None
    category_keys = tuple(bridged_ulta_category_keys(category_key))
    filtered = frame.filter(
        pl.col("category_key")
        .cast(pl.Utf8, strict=False)
        .fill_null("")
        .map_elements(_normalize_key, return_dtype=pl.Utf8)
        .is_in(category_keys)
    )
    coverage: dict[str, dict[str, object]] = {}
    if filtered.is_empty():
        return {
            "rows": 0,
            "threshold_invalid_rate": _LOW_COVERAGE_EXTRA_INVALID_RATE,
            "attributes": coverage,
            "low_coverage_extras": [],
        }

    attr_labels = {
        _normalize_key(str(attr.get("label") or "").strip()): str(
            attr.get("label") or ""
        ).strip()
        for attr in category_branch.get("attributes", []) or []
        if isinstance(attr, Mapping) and str(attr.get("label") or "").strip()
    }
    for attr_key, label in attr_labels.items():
        if label not in filtered.columns:
            coverage[label] = {
                "column_present": False,
                "invalid_rate": None,
                "valid_rate": None,
            }
            continue
        values = filtered.get_column(label).cast(pl.Utf8, strict=False)
        invalid = values.is_null() | values.fill_null("").map_elements(
            lambda item: _classify_stage_value(_normalize_stage_value(item))
            != "meaningful",
            return_dtype=pl.Boolean,
        )
        invalid_rate = float(invalid.mean())
        coverage[label] = {
            "column_present": True,
            "invalid_rate": invalid_rate,
            "valid_rate": 1.0 - invalid_rate,
        }

    return {
        "rows": filtered.height,
        "threshold_invalid_rate": _LOW_COVERAGE_EXTRA_INVALID_RATE,
        "attributes": coverage,
        "low_coverage_extras": [],
    }


def validate_category_setup(
    pdp_store_path: Path | str,
    *,
    retailer: str,
    category_key: str,
    links_path: Path | str | None = None,
    run_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Validate retailer/category setup before a full attribute export.

    The check compares three layers:
    - links manifest membership (`links.json`)
    - persisted PDP rows in the PDP store
    - normalized category resolution used by `compute_pdp_attributes`
    """

    normalized_retailer = _normalize_key(retailer)
    normalized_category = _normalize_key(category_key)
    acceptable_category_keys = set(bridged_ulta_category_keys(normalized_category))
    resolved_links_path = (
        Path(links_path) if links_path is not None else _DEFAULT_LINKS_PATH
    )
    links_lookup = _load_links_category_lookup(resolved_links_path)
    category_links = sorted(
        {
            url
            for (retailer_key, url), mapped_category in links_lookup.items()
            if retailer_key == normalized_retailer
            and mapped_category in acceptable_category_keys
        }
    )

    path = Path(pdp_store_path)
    if not pdp_database_exists(path):
        raise FileNotFoundError(f"PDP database not found: {path}")

    query = """
        SELECT
            parent_product_id,
            pdp_url,
            category_path,
            extras
        FROM parent_products
        WHERE LOWER(retailer) = ?
    """
    with connect_pdp_database(path) as conn:
        raw_rows = conn.execute(query, (normalized_retailer,)).fetchall()

    linked_parent_count = 0
    linked_with_persisted_category_key = 0
    linked_missing_persisted_category_key = 0
    linked_category_path_examples: set[str] = set()
    linked_parent_ids: set[str] = set()
    for parent_id, pdp_url, category_path_raw, extras_raw in raw_rows:
        normalized_url = _normalize_links_lookup_url(pdp_url)
        if normalized_url not in category_links:
            continue
        linked_parent_count += 1
        linked_parent_ids.add(str(parent_id or "").strip())
        extras: Mapping[str, object] | None = None
        if extras_raw:
            try:
                parsed = json.loads(extras_raw)
                if isinstance(parsed, Mapping):
                    extras = parsed
            except json.JSONDecodeError:
                extras = None
        persisted_category_key = _normalize_key(
            str((extras or {}).get("category_key") or "")
        )
        if persisted_category_key in acceptable_category_keys:
            linked_with_persisted_category_key += 1
        else:
            linked_missing_persisted_category_key += 1
        try:
            parsed_path = json.loads(category_path_raw) if category_path_raw else []
        except json.JSONDecodeError:
            parsed_path = []
        example = _category_path_example(parsed_path)
        if example:
            linked_category_path_examples.add(example)

    taxonomy = get_runtime_attribute_taxonomy()
    category_alias_map = get_category_alias_map()
    resolved_df, unmatched_categories, unmatched_examples, _ = _load_parent_products(
        pdp_store_path,
        taxonomy,
        [normalized_retailer],
        category_aliases=category_alias_map,
    )
    available_category_keys = (
        sorted(
            {
                _normalize_key(value)
                for value in resolved_df.get_column("category_key")
                .drop_nulls()
                .to_list()
                if _normalize_key(value)
            }
        )
        if not resolved_df.is_empty() and "category_key" in resolved_df.columns
        else []
    )

    resolved_rows = (
        resolved_df.filter(
            pl.col("category_key").is_in(sorted(acceptable_category_keys))
        )
        if not resolved_df.is_empty() and "category_key" in resolved_df.columns
        else pl.DataFrame()
    )
    linked_resolved_parent_count = 0
    if not resolved_rows.is_empty():
        linked_resolved_parent_count = resolved_rows.filter(
            pl.col("parent_product_id").is_in(sorted(linked_parent_ids))
        ).height

    status = "ok"
    errors: list[str] = []
    warnings: list[str] = []
    if not category_links:
        status = "error"
        errors.append(
            f"No links.json entries found for retailer={normalized_retailer} category={normalized_category}."
        )
    if not raw_rows:
        status = "error"
        errors.append(
            f"No parent_products rows found for retailer={normalized_retailer}."
        )
    if category_links and linked_parent_count == 0:
        status = "error"
        errors.append(
            "Links exist, but no PDP database parent rows matched the linked PDP URLs."
        )
    if linked_parent_count > 0 and linked_resolved_parent_count == 0:
        status = "error"
        errors.append(
            "Linked PDP database parents exist, but category resolution mapped 0 of them to the requested normalized category key."
        )
    elif 0 < linked_resolved_parent_count < linked_parent_count:
        if status != "error":
            status = "warning"
        warnings.append(
            f"Only {linked_resolved_parent_count} of {linked_parent_count} linked parent rows resolved to category={normalized_category}."
        )
    if linked_missing_persisted_category_key > 0:
        if status == "ok":
            status = "warning"
        warnings.append(
            f"{linked_missing_persisted_category_key} linked parent rows are missing persisted extras.category_key={normalized_category}; resolution relies on fallback mapping."
        )

    discovery_report: dict[str, Any] | None = None
    taxonomy_report: dict[str, Any] | None = None
    filter_alignment_report: dict[str, Any] | None = None
    cache_coverage_report: dict[str, Any] | None = None
    category_branch: Mapping[str, object] | None = None
    for item in taxonomy.get("categories", []) or []:
        if not isinstance(item, Mapping):
            continue
        item_id = _normalize_key(str(item.get("id") or ""))
        item_label = _normalize_key(str(item.get("label") or ""))
        if (
            item_id in acceptable_category_keys
            or item_label in acceptable_category_keys
        ):
            category_branch = item
            break
    if category_branch is None:
        if status == "ok":
            status = "warning"
        warnings.append(
            f"Taxonomy branch for category={normalized_category} is missing."
        )
        taxonomy_report = {
            "branch_found": False,
            "attribute_count": 0,
            "placeholder_only_attributes": [],
            "real_node_counts": {},
        }
    else:
        placeholder_only_attributes: list[str] = []
        real_node_counts: dict[str, int] = {}
        for attr in category_branch.get("attributes", []) or []:
            if not isinstance(attr, Mapping):
                continue
            attr_id = str(attr.get("id") or "").strip()
            if not attr_id:
                continue
            real_nodes = 0
            for node in attr.get("nodes", []) or []:
                if not isinstance(node, Mapping):
                    continue
                node_id = _normalize_key(str(node.get("id") or ""))
                node_label = _normalize_stage_value(node.get("label"))
                if node_id in {"unknown", "other"}:
                    continue
                if node_label is None:
                    continue
                if (
                    str(node_label).strip().casefold()
                    in _ATTRIBUTE_PLACEHOLDER_CANONICAL
                ):
                    continue
                real_nodes += 1
            real_node_counts[attr_id] = real_nodes
            if real_nodes == 0:
                placeholder_only_attributes.append(attr_id)
        if placeholder_only_attributes:
            if (
                len(placeholder_only_attributes) == len(real_node_counts)
                and status != "error"
            ):
                status = "error"
            elif status == "ok":
                status = "warning"
            warnings.append(
                "Taxonomy branch has placeholder-only attributes: "
                + ", ".join(sorted(placeholder_only_attributes))
            )
        taxonomy_report = {
            "branch_found": True,
            "attribute_count": len(real_node_counts),
            "placeholder_only_attributes": sorted(placeholder_only_attributes),
            "real_node_counts": real_node_counts,
        }
    if run_dir is not None:
        resolved_run_dir = Path(run_dir)
        discovery_report = {
            "run_dir": str(resolved_run_dir),
            "summary_exists": False,
            "listing_rows_summary": None,
            "filter_surface_rows_summary": None,
            "filter_observation_rows_summary": None,
            "listing_rows_csv": None,
            "filter_surface_rows_csv": None,
            "filter_observation_rows_csv": None,
        }
        summary_path = resolved_run_dir / "summary.json"
        if summary_path.is_file():
            discovery_report["summary_exists"] = True
            try:
                summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                summary_payload = {}
            if isinstance(summary_payload, Mapping):
                discovery_report["listing_rows_summary"] = summary_payload.get(
                    "listing_rows"
                )
                discovery_report["filter_surface_rows_summary"] = summary_payload.get(
                    "filter_surface_rows"
                )
                discovery_report["filter_observation_rows_summary"] = (
                    summary_payload.get("filter_observation_rows")
                )
        for name, key in (
            ("retailer_listing_observations.csv", "listing_rows_csv"),
            ("retailer_filter_surfaces.csv", "filter_surface_rows_csv"),
            ("retailer_filter_observations.csv", "filter_observation_rows_csv"),
        ):
            csv_path = resolved_run_dir / name
            if csv_path.is_file():
                try:
                    discovery_report[key] = pl.read_csv(csv_path).height
                except Exception:
                    discovery_report[key] = None
        listing_rows = discovery_report["listing_rows_csv"]
        filter_rows = discovery_report["filter_observation_rows_csv"]
        if isinstance(listing_rows, int) and listing_rows > 0 and filter_rows == 0:
            if status == "ok":
                status = "warning"
            warnings.append(
                "Discovery run has listing rows but 0 captured filter observations; filter discovery/capture likely failed for this retailer/category."
            )
        if category_branch is not None:
            observed_filters = _load_discovery_filter_surfaces(
                resolved_run_dir,
                retailer=normalized_retailer,
                category_key=normalized_category,
            )
            if observed_filters:
                filter_alignment_report = _build_filter_alignment_report(
                    category_branch,
                    observed_filters,
                    retailer=normalized_retailer,
                    category_key=normalized_category,
                )
                missing_dimensions = filter_alignment_report[
                    "missing_filter_dimensions"
                ]
                if missing_dimensions:
                    if status == "ok":
                        status = "warning"
                    warnings.append(
                        "Taxonomy is missing retailer filter dimensions: "
                        + ", ".join(str(item) for item in missing_dimensions)
                    )
                value_alignment = filter_alignment_report["value_alignment"]
                if isinstance(value_alignment, Mapping):
                    for family_label, family_report in value_alignment.items():
                        if not isinstance(family_report, Mapping):
                            continue
                        missing_values = (
                            family_report.get("missing_filter_values") or []
                        )
                        extra_values = family_report.get("extra_taxonomy_values") or []
                        if missing_values or extra_values:
                            if status == "ok":
                                status = "warning"
                            warnings.append(
                                f"Taxonomy/filter value mismatch for {family_label}: "
                                f"missing filter values={missing_values} extra taxonomy values={extra_values}"
                            )

    if category_branch is not None:
        cache_coverage_report = _load_taxonomy_cache_coverage(
            pdp_store_path,
            retailer=normalized_retailer,
            category_key=normalized_category,
            category_branch=category_branch,
        )
        if (
            cache_coverage_report is not None
            and filter_alignment_report is not None
            and isinstance(cache_coverage_report.get("attributes"), Mapping)
        ):
            core_dimensions = {
                _normalize_key(str(item))
                for item in (
                    filter_alignment_report.get("bridged_taxonomy_dimensions")
                    or filter_alignment_report.get("matched_filter_dimensions")
                    or []
                )
            }
            low_coverage_extras: list[str] = []
            for attr_label, attr_report in cache_coverage_report["attributes"].items():
                if not isinstance(attr_report, Mapping):
                    continue
                attr_key = _normalize_key(str(attr_label))
                if attr_key in core_dimensions:
                    continue
                invalid_rate = attr_report.get("invalid_rate")
                if invalid_rate is None:
                    continue
                try:
                    invalid_rate_float = float(invalid_rate)
                except (TypeError, ValueError):
                    continue
                if invalid_rate_float > _LOW_COVERAGE_EXTRA_INVALID_RATE:
                    low_coverage_extras.append(str(attr_label))
            cache_coverage_report["low_coverage_extras"] = sorted(low_coverage_extras)
            if low_coverage_extras:
                if status == "ok":
                    status = "warning"
                warnings.append(
                    "Low-coverage extra taxonomy dimensions exceed the invalid-value threshold: "
                    + ", ".join(sorted(low_coverage_extras))
                )

    report = {
        "status": status,
        "retailer": normalized_retailer,
        "category_key": normalized_category,
        "links_path": str(resolved_links_path),
        "links_count": len(category_links),
        "store_parent_count": len(raw_rows),
        "linked_parent_count": linked_parent_count,
        "linked_resolved_parent_count": linked_resolved_parent_count,
        "linked_with_persisted_category_key_count": linked_with_persisted_category_key,
        "linked_missing_persisted_category_key_count": linked_missing_persisted_category_key,
        "available_category_keys": available_category_keys,
        "linked_category_path_examples": sorted(linked_category_path_examples)[:5],
        "unmatched_categories": sorted(unmatched_categories),
        "unmatched_examples": {
            key: sorted(values)[:5] for key, values in unmatched_examples.items()
        },
        "errors": errors,
        "warnings": warnings,
    }
    if taxonomy_report is not None:
        if filter_alignment_report is not None:
            taxonomy_report["filter_alignment"] = filter_alignment_report
        if cache_coverage_report is not None:
            taxonomy_report["cache_coverage"] = cache_coverage_report
        report["taxonomy"] = taxonomy_report
    if discovery_report is not None:
        report["discovery"] = discovery_report
    return report


def _parse_price_to_float(value: object | None) -> float | None:
    """Best-effort price parser; returns None when no numeric fragment is found."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Strip common currency symbols and separators.
    cleaned = text.replace(",", "")
    # Extract the first numeric run (supports decimals).
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def _assign_price_band(
    prices: list[float], value: float | None
) -> tuple[str | None, tuple[float | None, float | None]]:
    """Assign premium/mid/value based on 35/85 percentiles."""
    if value is None or not prices:
        return None, (None, None)
    series = pl.Series(prices)
    try:
        low = float(series.quantile(0.35, interpolation="nearest"))
        high = float(series.quantile(0.85, interpolation="nearest"))
    except Exception:
        return None, (None, None)
    band: str | None
    if value > high:
        band = "premium"
    elif value < low:
        band = "value"
    else:
        band = "mid"
    return band, (low, high)


def _attribute_cache_dir(pdp_store_path: Path | str) -> Path:
    path = Path(pdp_store_path)
    name = f"{path.stem}_attribute_cache"
    return path.parent / name


def _attribute_cache_paths(
    pdp_store_path: Path | str, retailer: str | None = None
) -> dict[str, Path]:
    base = _attribute_cache_dir(pdp_store_path)
    if retailer:
        base = base / retailer
    return {
        "parent": base / "parents.parquet",
        "variant": base / "variants.parquet",
        "segments": base / "segments.parquet",
        "combined": base / "combined.parquet",
        "parents_all": base / "parents_all.parquet",
        "metadata": base / "metadata.json",
    }


def get_attribute_cache_mtime(pdp_store_path: Path | str) -> float | None:
    root = _attribute_cache_dir(pdp_store_path)
    newest: float | None = None
    if root.exists():
        for path in root.rglob("combined.parquet"):
            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                continue
            if newest is None or mtime > newest:
                newest = mtime
    return newest


def _build_attribute_id_lookup(taxonomy: Mapping[str, object]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for category in taxonomy.get("categories", []) or []:
        if not isinstance(category, Mapping):
            continue
        for attr in category.get("attributes", []) or []:
            if not isinstance(attr, Mapping):
                continue
            attr_id_raw = str(attr.get("id", "")).strip()
            label = str(attr.get("label", "")).strip()
            if not attr_id_raw:
                continue
            lookup[attr_id_raw] = label or attr_id_raw
            lookup[attr_id_raw.lower()] = label or attr_id_raw
    return lookup


def _attach_canonical_columns(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df.with_columns(
            pl.lit("").alias("canonical_id"),
            pl.lit("").alias("brand_norm"),
            pl.lit("").alias("product_name_norm"),
        )

    return (
        df.with_columns(
            pl.struct(["brand", "product_name"])
            .map_elements(
                lambda row: (
                    lambda triple: {
                        "canonical_id": triple[0],
                        "brand_norm": triple[1],
                        "product_name_norm": triple[2],
                    }
                )(compute_canonical_values(row.get("brand"), row.get("product_name"))),
                return_dtype=pl.Struct(
                    {
                        "canonical_id": pl.Utf8,
                        "brand_norm": pl.Utf8,
                        "product_name_norm": pl.Utf8,
                    }
                ),
            )
            .alias("_canonical_struct")
        )
        .with_columns(
            pl.col("_canonical_struct").struct.field("canonical_id"),
            pl.col("_canonical_struct").struct.field("brand_norm"),
            pl.col("_canonical_struct").struct.field("product_name_norm"),
        )
        .drop("_canonical_struct")
    )


def _collect_attribute_records(
    df: pl.DataFrame,
    *,
    row_type: str,
    attr_labels: Mapping[str, str],
    source: str,
    timestamp: str,
    allowed_columns: set[str] | None = None,
    attribute_metadata: (
        Mapping[_AttributeRecordKey, _AttributeRecordMeta] | None
    ) = None,
) -> list[AttributeValueRecord]:
    if df.is_empty():
        return []
    base_columns = PARENT_BASE_COLUMNS if row_type == "parent" else VARIANT_BASE_COLUMNS
    attr_columns = [col for col in df.columns if col not in base_columns]
    if allowed_columns is not None:
        attr_columns = [col for col in attr_columns if col in allowed_columns]
    if not attr_columns:
        return []
    records: list[AttributeValueRecord] = []
    processed_rows = 0
    for row in df.to_dicts():
        processed_rows += 1
        retailer = str(row.get("retailer") or "").strip()
        parent_id = str(row.get("parent_product_id") or "").strip()
        category_key = str(row.get("category_key") or "").strip()
        if not retailer or not parent_id:
            continue
        variant_id = ""
        if row_type == "variant":
            variant_id = str(row.get("variant_id") or "").strip()
            if not variant_id:
                continue
        for attr_col in attr_columns:
            attribute_id = str(attr_col).strip()
            label = (
                attr_labels.get(attribute_id)
                or attr_labels.get(attribute_id.lower())
                or attribute_id
            )
            value_obj = row.get(attr_col)
            if value_obj is None:
                continue
            value_text = str(value_obj)
            meta = None
            if attribute_metadata is not None:
                meta_key: _AttributeRecordKey = (
                    retailer,
                    row_type,
                    parent_id,
                    variant_id,
                    category_key,
                    attribute_id,
                )
                meta = attribute_metadata.get(meta_key)
            records.append(
                AttributeValueRecord(
                    retailer=retailer,
                    row_type=row_type,
                    parent_product_id=parent_id,
                    variant_id=variant_id if row_type == "variant" else "",
                    attribute_id=attribute_id,
                    attribute_label=label,
                    value=value_text,
                    oov_candidate=meta.oov_candidate if meta else None,
                    note=meta.note if meta else None,
                    source=source,
                    updated_at=timestamp,
                    category_key=category_key,
                )
            )
    if LOGGER.isEnabledFor(logging.INFO) and records:
        non_placeholder = sum(
            1
            for record in records
            if record.value not in {None, "", "N/A", NOT_IN_TAXONOMY_VALUE}
        )
        LOGGER.info(
            "Prepared %s attribute records (row_type=%s, source=%s, non_placeholder=%s, rows=%s)",
            len(records),
            row_type,
            source,
            non_placeholder,
            processed_rows,
        )
        LOGGER.debug(
            "Sample attribute records (row_type=%s, source=%s): %s",
            row_type,
            source,
            records[:3],
        )
    return records


def _should_write_resolution_history(pdp_store_path: Path | str) -> bool:
    try:
        return Path(pdp_store_path).resolve() == DEFAULT_PDP_STORE_PATH.resolve()
    except OSError:
        return False


def _build_resolution_context_maps(
    parent_df: pl.DataFrame,
    variant_df: pl.DataFrame,
) -> tuple[
    dict[tuple[str, str, str], dict[str, str]],
    dict[tuple[str, str, str], dict[str, str]],
]:
    parent_lookup: dict[tuple[str, str, str], dict[str, str]] = {}
    variant_lookup: dict[tuple[str, str, str], dict[str, str]] = {}

    if not parent_df.is_empty():
        parent_cols = {
            "retailer",
            "parent_product_id",
            "canonical_id",
            "category_key",
        }
        select_cols = [col for col in parent_cols if col in parent_df.columns]
        if {"retailer", "parent_product_id"}.issubset(set(select_cols)):
            for row in parent_df.select(select_cols).to_dicts():
                retailer = str(row.get("retailer") or "").strip()
                parent_id = str(row.get("parent_product_id") or "").strip()
                category_key = str(row.get("category_key") or "").strip()
                if not retailer or not parent_id:
                    continue
                parent_lookup[(retailer, parent_id, category_key)] = {
                    "canonical_id": str(row.get("canonical_id") or "").strip(),
                }

    if not variant_df.is_empty():
        variant_cols = {
            "retailer",
            "variant_id",
            "parent_product_id",
            "canonical_id",
            "category_key",
        }
        select_cols = [col for col in variant_cols if col in variant_df.columns]
        if {"retailer", "variant_id"}.issubset(set(select_cols)):
            for row in variant_df.select(select_cols).to_dicts():
                retailer = str(row.get("retailer") or "").strip()
                variant_id = str(row.get("variant_id") or "").strip()
                category_key = str(row.get("category_key") or "").strip()
                if not retailer or not variant_id:
                    continue
                variant_lookup[(retailer, variant_id, category_key)] = {
                    "parent_product_id": str(
                        row.get("parent_product_id") or ""
                    ).strip(),
                    "canonical_id": str(row.get("canonical_id") or "").strip(),
                }

    return parent_lookup, variant_lookup


def _attribute_records_to_resolution_rows(
    records: Sequence[AttributeValueRecord],
    *,
    run_id: str,
    step: str,
    decision_rule: str,
    parent_lookup: Mapping[tuple[str, str, str], Mapping[str, str]],
    variant_lookup: Mapping[tuple[str, str, str], Mapping[str, str]],
) -> list[dict[str, Any]]:
    if not records:
        return []
    rows: list[dict[str, Any]] = []
    for record in records:
        retailer = str(record.retailer or "").strip()
        parent_id = str(record.parent_product_id or "").strip()
        variant_id = str(record.variant_id or "").strip()
        category_key = str(record.category_key or "").strip()
        attr_id = str(record.attribute_id or "").strip()
        if not retailer or not parent_id or not attr_id:
            continue

        context: Mapping[str, str] = {}
        if record.row_type == "variant" and variant_id:
            context = variant_lookup.get((retailer, variant_id, category_key), {})
        if not context:
            context = parent_lookup.get((retailer, parent_id, category_key), {})
        if not context and record.row_type == "variant" and variant_id:
            context = variant_lookup.get((retailer, variant_id, ""), {})
        if not context:
            context = parent_lookup.get((retailer, parent_id, ""), {})

        rows.append(
            {
                "run_id": run_id,
                "recorded_at": str(record.updated_at or ""),
                "step": step,
                "source": str(record.source or ""),
                "decision_rule": decision_rule,
                "row_type": str(record.row_type or ""),
                "retailer": retailer,
                "parent_product_id": parent_id,
                "variant_id": variant_id,
                "canonical_id": str(context.get("canonical_id") or ""),
                "category_key": category_key,
                "attribute_id": attr_id,
                "value": None if record.value is None else str(record.value),
                "confidence": None,
                "evidence_url": None,
            }
        )
    return rows


def _load_sure_resolution_consensus() -> pl.DataFrame:
    consensus = read_resolution_consensus()
    if consensus.is_empty():
        return pl.DataFrame()
    return consensus.filter(
        (pl.col("certainty_class") == "sure")
        & pl.col("consensus_value").is_not_null()
        & (pl.col("consensus_value").cast(pl.Utf8).str.strip_chars() != "")
    )


def _apply_sure_consensus_to_frame(
    df: pl.DataFrame,
    *,
    row_type: str,
    sure_consensus: pl.DataFrame,
) -> tuple[pl.DataFrame, int]:
    if df.is_empty() or sure_consensus.is_empty():
        return df, 0

    if row_type == "parent":
        key_cols = ["retailer", "parent_product_id"]
    elif row_type == "variant":
        key_cols = ["retailer", "parent_product_id", "variant_id"]
    else:
        return df, 0
    if "category_key" in df.columns and "category_key" in sure_consensus.columns:
        key_cols = [*key_cols, "category_key"]

    if any(col not in df.columns for col in key_cols):
        return df, 0

    consensus_slice = sure_consensus.filter(pl.col("row_type") == row_type)
    if consensus_slice.is_empty():
        return df, 0

    columns = list(df.columns)
    normalized_column_lookup: dict[str, str] = {}
    for col in columns:
        normalized_column_lookup.setdefault(_normalize_key(col), col)

    def _resolve_column(attribute_id: str) -> str | None:
        if attribute_id in columns:
            return attribute_id
        normalized = _normalize_key(attribute_id)
        if normalized and normalized in normalized_column_lookup:
            return normalized_column_lookup[normalized]
        return None

    updates: list[dict[str, str]] = []
    category_lookup: dict[tuple[str, ...], str] = {}
    if "category_key" in df.columns and "category_key" not in key_cols:
        for row in df.select([*key_cols, "category_key"]).to_dicts():
            key = tuple(str(row.get(col) or "").strip() for col in key_cols)
            category_lookup[key] = _normalize_key(str(row.get("category_key") or ""))
    for row in consensus_slice.select(
        [*key_cols, "attribute_id", "consensus_value"]
    ).to_dicts():
        attr_id = str(row.get("attribute_id") or "").strip()
        value = str(row.get("consensus_value") or "").strip()
        if not attr_id or _is_placeholder_value(value):
            continue
        target_col = _resolve_column(attr_id)
        if not target_col:
            continue
        update: dict[str, str] = {}
        valid = True
        for key in key_cols:
            key_value = str(row.get(key) or "").strip()
            if not key_value:
                valid = False
                break
            update[key] = key_value
        if not valid:
            continue
        category_key = (
            _normalize_key(update.get("category_key"))
            if "category_key" in key_cols
            else category_lookup.get(tuple(update[key] for key in key_cols))
        )
        if not _attribute_enabled_for_category(
            category_key,
            attr_id,
            row_scope=row_type,
        ):
            continue
        update[target_col] = value
        updates.append(update)

    if not updates:
        return df, 0

    update_keys = sorted({key for row in updates for key in row.keys()})
    update_schema = {key: pl.Utf8 for key in update_keys}
    update_df = pl.DataFrame(updates, schema=update_schema)
    update_cols = [col for col in update_df.columns if col not in key_cols]
    if update_cols:
        update_df = update_df.group_by(key_cols, maintain_order=True).agg(
            [pl.col(col).drop_nulls().first().alias(col) for col in update_cols]
        )
    else:
        update_df = update_df.unique(subset=key_cols, keep="first")

    merged = df.join(update_df, on=key_cols, how="left", suffix="__sure")
    placeholders = list(_ATTRIBUTE_PLACEHOLDER_CANONICAL) + [""]
    merged_columns = set(merged.columns)
    for key in update_cols:
        sure_col = f"{key}__sure"
        if sure_col not in merged_columns or key not in merged_columns:
            continue
        base_is_placeholder = pl.col(key).is_null() | pl.col(key).cast(
            pl.Utf8
        ).str.strip_chars().str.to_lowercase().is_in(placeholders)
        merged = merged.with_columns(
            pl.when(base_is_placeholder & pl.col(sure_col).is_not_null())
            .then(pl.col(sure_col))
            .otherwise(pl.col(key))
            .alias(key)
        ).drop(sure_col)
        merged_columns.discard(sure_col)

    return merged, len(updates)


def _collect_pdp_text_segments(
    extras: Mapping[str, object] | None,
) -> list[tuple[str, str]]:
    """Return ordered (path, text) segments extracted from PDP extras.

    The traversal is recursive so every textual field is preserved for downstream
    deterministic matching (and, later, possible LLM fallbacks). Review fields
    are intentionally skipped to keep customer quotes out of the signal.
    """

    if not extras:
        return []

    segments: list[tuple[str, str]] = []

    def _visit(value: object, path: str) -> None:
        if isinstance(value, str):
            text = value.strip()
            if text:
                segments.append((path or "text", text))
            return

        if isinstance(value, Mapping):
            for key, nested in value.items():
                normalized_key = str(key).strip().lower()
                if normalized_key in _PDP_REVIEW_KEYS:
                    continue
                next_path = (
                    normalized_key
                    if not path
                    else f"{path}.{normalized_key}" if normalized_key else path
                )
                _visit(nested, next_path)
            return

        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            for idx, item in enumerate(value):
                if isinstance(item, str):
                    _visit(item, path)
                else:
                    next_path = f"{path}[{idx}]" if path else f"[{idx}]"
                    _visit(item, next_path)
            return

    _visit(extras, "")
    return segments


def _empty_pdp_source_segments_df() -> pl.DataFrame:
    return pl.DataFrame(schema=_PDP_SOURCE_SEGMENT_SCHEMA)


def _clean_pdp_segment_text(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None
    text = _PDP_SEGMENT_WHITESPACE_RE.sub(" ", value.strip())
    return text if text else None


def _normalize_pdp_segment_text(text: str) -> str:
    return text.lower()


def _looks_like_measurement_only(text: str | None) -> bool:
    cleaned = _clean_pdp_segment_text(text)
    if not cleaned or not any(char.isdigit() for char in cleaned):
        return False
    tokens = (
        cleaned.lower().replace("/", " ").replace("-", " ").replace(".", " ").split()
    )
    if not tokens:
        return False
    allowed_units = {
        "oz",
        "floz",
        "fl",
        "ml",
        "l",
        "cl",
        "g",
        "kg",
        "lb",
        "lbs",
        "ct",
        "count",
        "pack",
        "packs",
        "pc",
        "pcs",
        "piece",
        "pieces",
        "ea",
        "each",
        "x",
    }
    for token in tokens:
        if any(char.isdigit() for char in token):
            continue
        if token not in allowed_units:
            return False
    return True


def _append_pdp_source_segment(
    rows: list[dict[str, object]],
    *,
    path_counts: Counter[str],
    retailer: str,
    row_type: str,
    parent_product_id: str,
    variant_id: str,
    category_key: str,
    source_channel: str,
    source_path: str,
    segment_text: object | None,
    label: object | None = None,
    subtype: object | None = None,
) -> None:
    cleaned_text = _clean_pdp_segment_text(segment_text)
    if not cleaned_text:
        return

    cleaned_label = _clean_pdp_segment_text(label)
    cleaned_subtype = _clean_pdp_segment_text(subtype)
    duplicate_index = int(path_counts.get(source_path, 0))
    path_counts[source_path] += 1
    segment_id = (
        source_path if duplicate_index == 0 else f"{source_path}#{duplicate_index}"
    )

    rows.append(
        {
            "retailer": retailer,
            "row_type": row_type,
            "parent_product_id": parent_product_id,
            "variant_id": variant_id,
            "category_key": category_key,
            "source_channel": source_channel,
            "segment_id": segment_id,
            "segment_order": len(rows),
            "source_path": source_path,
            "segment_text": cleaned_text,
            "normalized_text": _normalize_pdp_segment_text(cleaned_text),
            "label": cleaned_label,
            "subtype": cleaned_subtype,
        }
    )


def _collect_all_text_segments(
    value: object,
    *,
    path: str = "",
) -> list[tuple[str, str]]:
    segments: list[tuple[str, str]] = []

    def _visit(nested: object, current_path: str) -> None:
        text = _clean_pdp_segment_text(nested)
        if text is not None:
            segments.append((current_path or "text", text))
            return
        if isinstance(nested, Mapping):
            for key, child in nested.items():
                key_text = str(key).strip().lower()
                if key_text in _PDP_REVIEW_KEYS or key_text == "reviews":
                    continue
                next_path = (
                    key_text
                    if not current_path
                    else f"{current_path}.{key_text}" if key_text else current_path
                )
                _visit(child, next_path)
            return
        if isinstance(nested, Sequence) and not isinstance(
            nested, (str, bytes, bytearray)
        ):
            for idx, child in enumerate(nested):
                next_path = f"{current_path}[{idx}]" if current_path else f"[{idx}]"
                if isinstance(child, str):
                    _visit(child, next_path)
                else:
                    _visit(child, next_path)

    _visit(value, path)
    return segments


def _append_feature_list_segments(
    rows: list[dict[str, object]],
    *,
    path_counts: Counter[str],
    retailer: str,
    row_type: str,
    parent_product_id: str,
    variant_id: str,
    category_key: str,
    source_channel: str,
    values: object | None,
    path_prefix: str,
) -> None:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return
    for idx, item in enumerate(values):
        _append_pdp_source_segment(
            rows,
            path_counts=path_counts,
            retailer=retailer,
            row_type=row_type,
            parent_product_id=parent_product_id,
            variant_id=variant_id,
            category_key=category_key,
            source_channel=source_channel,
            source_path=f"{path_prefix}[{idx}]",
            segment_text=item,
        )


def _append_highlight_segments(
    rows: list[dict[str, object]],
    *,
    path_counts: Counter[str],
    retailer: str,
    row_type: str,
    parent_product_id: str,
    variant_id: str,
    category_key: str,
    source_channel: str,
    highlights: object | None,
) -> None:
    if not isinstance(highlights, Sequence) or isinstance(
        highlights, (str, bytes, bytearray)
    ):
        return
    for idx, item in enumerate(highlights):
        path = f"highlights[{idx}]"
        if isinstance(item, Mapping):
            label = _clean_pdp_segment_text(item.get("label"))
            description = _clean_pdp_segment_text(item.get("description"))
            text = description or label
            if label and description:
                text = f"{label}: {description}"
            _append_pdp_source_segment(
                rows,
                path_counts=path_counts,
                retailer=retailer,
                row_type=row_type,
                parent_product_id=parent_product_id,
                variant_id=variant_id,
                category_key=category_key,
                source_channel=source_channel,
                source_path=path,
                segment_text=text,
                label=label,
            )
            continue
        _append_pdp_source_segment(
            rows,
            path_counts=path_counts,
            retailer=retailer,
            row_type=row_type,
            parent_product_id=parent_product_id,
            variant_id=variant_id,
            category_key=category_key,
            source_channel=source_channel,
            source_path=path,
            segment_text=item,
        )


def _append_summary_card_segments(
    rows: list[dict[str, object]],
    *,
    path_counts: Counter[str],
    retailer: str,
    row_type: str,
    parent_product_id: str,
    variant_id: str,
    category_key: str,
    source_channel: str,
    summary_cards: object | None,
) -> None:
    if not isinstance(summary_cards, Sequence) or isinstance(
        summary_cards, (str, bytes, bytearray)
    ):
        return
    for card_idx, card in enumerate(summary_cards):
        if not isinstance(card, Mapping):
            continue
        card_label = _clean_pdp_segment_text(card.get("title"))
        items = card.get("items")
        if not isinstance(items, Sequence) or isinstance(
            items, (str, bytes, bytearray)
        ):
            continue
        for item_idx, item in enumerate(items):
            item_text = None
            if isinstance(item, Mapping):
                item_text = _clean_pdp_segment_text(
                    item.get("text")
                ) or _clean_pdp_segment_text(item.get("title"))
            else:
                item_text = _clean_pdp_segment_text(item)
            _append_pdp_source_segment(
                rows,
                path_counts=path_counts,
                retailer=retailer,
                row_type=row_type,
                parent_product_id=parent_product_id,
                variant_id=variant_id,
                category_key=category_key,
                source_channel=source_channel,
                source_path=f"summary_cards[{card_idx}].items[{item_idx}]",
                segment_text=item_text,
                label=card_label,
            )


def _append_review_segments(
    rows: list[dict[str, object]],
    *,
    path_counts: Counter[str],
    retailer: str,
    row_type: str,
    parent_product_id: str,
    variant_id: str,
    category_key: str,
    source_channel: str,
    reviews: object | None,
    positive_summary: object | None,
    negative_summary: object | None,
) -> None:
    if isinstance(reviews, Sequence) and not isinstance(
        reviews, (str, bytes, bytearray)
    ):
        for review_idx, review in enumerate(reviews):
            if not isinstance(review, Mapping):
                continue
            for field, subtype in (
                ("headline", "raw_headline"),
                ("comment", "raw_comment"),
            ):
                _append_pdp_source_segment(
                    rows,
                    path_counts=path_counts,
                    retailer=retailer,
                    row_type=row_type,
                    parent_product_id=parent_product_id,
                    variant_id=variant_id,
                    category_key=category_key,
                    source_channel=source_channel,
                    source_path=f"reviews[{review_idx}].{field}",
                    segment_text=review.get(field),
                    subtype=subtype,
                )

    for summary_key, summary_value, prefix in (
        ("reviews_positive", positive_summary, "positive"),
        ("reviews_negative", negative_summary, "negative"),
    ):
        if not isinstance(summary_value, Mapping):
            continue
        for field in ("headline", "comment"):
            _append_pdp_source_segment(
                rows,
                path_counts=path_counts,
                retailer=retailer,
                row_type=row_type,
                parent_product_id=parent_product_id,
                variant_id=variant_id,
                category_key=category_key,
                source_channel=source_channel,
                source_path=f"{summary_key}.{field}",
                segment_text=summary_value.get(field),
                subtype=f"{prefix}_{field}",
            )


def _build_parent_source_segment_rows(
    *,
    retailer: str,
    parent_product_id: str,
    category_key: str,
    title_raw: object | None,
    extras: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    path_counts: Counter[str] = Counter()

    _append_pdp_source_segment(
        rows,
        path_counts=path_counts,
        retailer=retailer,
        row_type="parent",
        parent_product_id=parent_product_id,
        variant_id="",
        category_key=category_key,
        source_channel="title",
        source_path="title_raw",
        segment_text=title_raw,
    )

    if not extras:
        return rows

    details = (
        extras.get("details") if isinstance(extras.get("details"), Mapping) else {}
    )
    if not isinstance(details, Mapping):
        details = {}

    for source_path, channel in (
        ("summary", "summary"),
        ("description_markdown", "description_markdown"),
        ("short_description", "description_short"),
        ("long_description", "description_long"),
    ):
        _append_pdp_source_segment(
            rows,
            path_counts=path_counts,
            retailer=retailer,
            row_type="parent",
            parent_product_id=parent_product_id,
            variant_id="",
            category_key=category_key,
            source_channel=channel,
            source_path=source_path,
            segment_text=extras.get(source_path),
        )

    for source_path, channel in (
        ("details.description_markdown", "description_markdown"),
        ("details.short_description", "description_short"),
        ("details.long_description", "description_long"),
        ("details.ingredients", "ingredients"),
        ("details.usage", "usage"),
        ("details.restrictions", "restrictions"),
    ):
        _, field = source_path.split(".", 1)
        _append_pdp_source_segment(
            rows,
            path_counts=path_counts,
            retailer=retailer,
            row_type="parent",
            parent_product_id=parent_product_id,
            variant_id="",
            category_key=category_key,
            source_channel=channel,
            source_path=source_path,
            segment_text=details.get(field),
        )

    for source_path, channel in (
        ("ingredients", "ingredients"),
        ("usage", "usage"),
        ("restrictions", "restrictions"),
    ):
        _append_pdp_source_segment(
            rows,
            path_counts=path_counts,
            retailer=retailer,
            row_type="parent",
            parent_product_id=parent_product_id,
            variant_id="",
            category_key=category_key,
            source_channel=channel,
            source_path=source_path,
            segment_text=extras.get(source_path),
        )

    _append_feature_list_segments(
        rows,
        path_counts=path_counts,
        retailer=retailer,
        row_type="parent",
        parent_product_id=parent_product_id,
        variant_id="",
        category_key=category_key,
        source_channel="features",
        values=extras.get("features"),
        path_prefix="features",
    )
    _append_feature_list_segments(
        rows,
        path_counts=path_counts,
        retailer=retailer,
        row_type="parent",
        parent_product_id=parent_product_id,
        variant_id="",
        category_key=category_key,
        source_channel="features",
        values=details.get("features"),
        path_prefix="details.features",
    )
    _append_highlight_segments(
        rows,
        path_counts=path_counts,
        retailer=retailer,
        row_type="parent",
        parent_product_id=parent_product_id,
        variant_id="",
        category_key=category_key,
        source_channel="features",
        highlights=extras.get("highlights"),
    )
    _append_summary_card_segments(
        rows,
        path_counts=path_counts,
        retailer=retailer,
        row_type="parent",
        parent_product_id=parent_product_id,
        variant_id="",
        category_key=category_key,
        source_channel="features",
        summary_cards=extras.get("summary_cards"),
    )
    _append_review_segments(
        rows,
        path_counts=path_counts,
        retailer=retailer,
        row_type="parent",
        parent_product_id=parent_product_id,
        variant_id="",
        category_key=category_key,
        source_channel="reviews",
        reviews=extras.get("reviews"),
        positive_summary=extras.get("reviews_positive"),
        negative_summary=extras.get("reviews_negative"),
    )
    return rows


def _build_variant_source_segment_rows(
    *,
    retailer: str,
    parent_product_id: str,
    variant_id: str,
    category_key: str,
    shade_name_raw: object | None,
    size_text_raw: object | None,
    extras: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    path_counts: Counter[str] = Counter()

    _append_pdp_source_segment(
        rows,
        path_counts=path_counts,
        retailer=retailer,
        row_type="variant",
        parent_product_id=parent_product_id,
        variant_id=variant_id,
        category_key=category_key,
        source_channel="variant_name",
        source_path="shade_name_raw",
        segment_text=shade_name_raw,
    )
    cleaned_size = _clean_pdp_segment_text(size_text_raw)
    if cleaned_size and not _looks_like_measurement_only(cleaned_size):
        _append_pdp_source_segment(
            rows,
            path_counts=path_counts,
            retailer=retailer,
            row_type="variant",
            parent_product_id=parent_product_id,
            variant_id=variant_id,
            category_key=category_key,
            source_channel="variant_name",
            source_path="size_text_raw",
            segment_text=cleaned_size,
        )

    if not extras:
        return rows

    for source_path, segment_text in _collect_all_text_segments(extras):
        _append_pdp_source_segment(
            rows,
            path_counts=path_counts,
            retailer=retailer,
            row_type="variant",
            parent_product_id=parent_product_id,
            variant_id=variant_id,
            category_key=category_key,
            source_channel="variant_description",
            source_path=source_path,
            segment_text=segment_text,
        )
    return rows


def _rows_to_pdp_source_segments_dataframe(
    rows: list[dict[str, object]],
) -> pl.DataFrame:
    if not rows:
        return _empty_pdp_source_segments_df()
    return pl.DataFrame(rows, schema_overrides=_PDP_SOURCE_SEGMENT_SCHEMA)


def _match_category_value(
    value: str,
    category_index: Mapping[str, tuple[str, str]],
    aliases: Mapping[str, str] | None = None,
) -> tuple[str, str, str] | None:
    normalized = _normalize_key(value)
    canonical_normalized = canonicalize_ulta_category_key(normalized)

    alias_tokens: list[str] = []
    if aliases:
        alias_target = aliases.get(normalized)
        if alias_target:
            alias_normalized = _normalize_key(alias_target)
            if alias_normalized:
                alias_tokens.append(alias_normalized)

    def _candidates(token: str) -> list[str]:
        items = [token]
        if token.endswith("ies") and len(token) > 3:
            items.append(token[:-3] + "y")
        if token.endswith("es") and len(token) > 2:
            items.append(token[:-2])
        if token.endswith("s") and len(token) > 1:
            items.append(token[:-1])
        return items

    search_tokens = list(alias_tokens)
    if canonical_normalized and canonical_normalized not in search_tokens:
        search_tokens.append(canonical_normalized)
    if normalized not in search_tokens:
        search_tokens.append(normalized)
    for token in search_tokens:
        for candidate in _candidates(token):
            if candidate in category_index:
                cid, label = category_index[candidate]
                return cid, label, candidate
    return None


def _flatten_description(extras: Mapping[str, object] | None) -> str:
    segments = _collect_pdp_text_segments(extras)
    if not segments:
        return ""
    return " ".join(text for _, text in segments)


def _join_segment_texts(values: Sequence[object] | None) -> str:
    """Join text segments once, preserving order and dropping exact duplicates."""

    if isinstance(values, pl.Series):
        iterable: Sequence[object] | None = values.to_list()
    else:
        iterable = values
    seen: set[str] = set()
    ordered: list[str] = []
    for value in iterable or []:
        text = _clean_pdp_segment_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return " ".join(ordered).strip()


def _build_deterministic_description_lookup(
    segment_df: pl.DataFrame,
    *,
    key_columns: Sequence[str],
    source_channels: Sequence[str],
    output_column: str,
) -> pl.DataFrame:
    """Aggregate a strict deterministic text slice from selected PDP sources."""

    schema = {column: pl.Utf8 for column in [*key_columns, output_column]}
    if segment_df.is_empty():
        return pl.DataFrame(schema=schema)
    filtered = segment_df.filter(pl.col("source_channel").is_in(list(source_channels)))
    if filtered.is_empty():
        return pl.DataFrame(schema=schema)
    return (
        filtered.sort([*key_columns, "segment_order"])
        .group_by(list(key_columns), maintain_order=True)
        .agg(pl.col("segment_text").alias("_segment_texts"))
        .with_columns(
            pl.col("_segment_texts")
            .map_elements(_join_segment_texts, return_dtype=pl.Utf8)
            .alias(output_column)
        )
        .select([*key_columns, output_column])
    )


def _rows_to_dataframe(
    rows: list[dict[str, object]],
    columns: Sequence[str],
    base_schema: Mapping[str, pl.DataType],
) -> pl.DataFrame:
    ordered_columns = list(columns)
    if rows:
        for row in rows:
            for key in row.keys():
                if key not in ordered_columns:
                    ordered_columns.append(str(key))
    schema_items: list[tuple[str, pl.DataType]] = []
    for col in ordered_columns:
        dtype = base_schema.get(col, pl.Utf8)
        if dtype == pl.Null:
            dtype = pl.Utf8
        schema_items.append((col, dtype))
    if not rows:
        return pl.DataFrame(schema=schema_items)
    schema: dict[str, pl.DataType] = dict(schema_items)
    return pl.DataFrame(rows, schema=schema, orient="row")


def _normalize_allowed_lookup(
    allowed_values: Mapping[str, Sequence[str]],
) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for attr, values in allowed_values.items():
        mapping: dict[str, str] = {}
        for label in values:
            text = str(label)
            mapping[text.strip().lower()] = text
        lookup[attr] = mapping
    return lookup


def _attribute_key_variants(key: object | None) -> list[str]:
    if key is None:
        return []
    text = str(key).strip()
    if not text:
        return []

    variants: list[str] = []

    def _add(candidate: str | None) -> None:
        if not candidate:
            return
        normalized = candidate.strip()
        if normalized and normalized not in variants:
            variants.append(normalized)

    _add(text)
    lowered = text.lower()
    _add(lowered)
    normalized = _normalize_key(text)
    _add(normalized)

    def _expand(forms: list[str]) -> None:
        for form in forms:
            _add(form)

    replacements = [
        lowered.replace(" ", "_"),
        lowered.replace("-", "_"),
        lowered.replace("/", "_"),
        lowered.replace("_", " "),
        lowered.replace("_", "-"),
        lowered.replace("_", "/"),
    ]
    if normalized:
        replacements.extend(
            [
                normalized.replace("_", " "),
                normalized.replace("_", "-"),
                normalized.replace("_", "/"),
            ]
        )
    _expand(replacements)
    return variants


@dataclass
class _VariantLLMRequest:
    row_index: int
    variant_id: str
    variant_key: str
    display_name: str
    context_text: str
    missing_attrs: list[str]
    allowed_values: dict[str, list[str]]
    nodes_by_label: dict[str, list[Mapping[str, object]]]
    attr_column_map: dict[str, str]


@dataclass
class _ParentLLMRequest:
    row_index: int
    parent_product_id: str
    display_name: str
    category_label: str | None
    category_path: str
    deterministic_text: str
    pdp_text: str
    missing_attrs: list[str]
    allowed_values: dict[str, list[str]]
    nodes_by_label: dict[str, list[Mapping[str, object]]]
    attr_column_map: dict[str, str]
    variants: list[_VariantLLMRequest]


@dataclass(slots=True)
class _AttributeLLMResult:
    value: str
    oov_candidate: str | None = None
    note: str | None = None


@dataclass(slots=True)
class _AttributeRecordMeta:
    oov_candidate: str | None = None
    note: str | None = None


_AttributeRecordKey = tuple[str, str, str, str, str, str]
_ParsedVariantLLMMap = dict[str, dict[str, _AttributeLLMResult]]
_ParsedPdpLLMResponse = dict[str, dict[str, _AttributeLLMResult] | _ParsedVariantLLMMap]


def _normalize_optional_llm_text(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, (str, int, float)):
        return None
    text = str(value).strip()
    return text or None


def _coerce_llm_result(entry: object) -> _AttributeLLMResult:
    if isinstance(entry, _AttributeLLMResult):
        return entry
    if isinstance(entry, Mapping):
        value_obj = entry.get("value")
        value_text = _normalize_optional_llm_text(value_obj) or "N/A"
        return _AttributeLLMResult(
            value=value_text,
            oov_candidate=_normalize_optional_llm_text(entry.get("oov_candidate")),
            note=_normalize_optional_llm_text(entry.get("note")),
        )
    value_text = _normalize_optional_llm_text(entry)
    return _AttributeLLMResult(value=value_text or "N/A")


def _canonicalize_attribute_map(
    payload: Mapping[str, object] | None,
    request_attrs: list[str],
    allowed_values: dict[str, list[str]],
    nodes_by_label: dict[str, list[Mapping[str, object]]],
    attr_alias_map: dict[str, dict[str, str]] | None = None,
) -> dict[str, _AttributeLLMResult]:
    results: dict[str, _AttributeLLMResult] = {}
    if not request_attrs:
        return results
    response_entries: dict[str, object] = {}
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            for variant in _attribute_key_variants(key):
                response_entries.setdefault(variant, value)
    allowed_lookup = _normalize_allowed_lookup(allowed_values)
    for attr in request_attrs:
        entry = None
        oov_candidate: str | None = None
        note: str | None = None
        for candidate in _attribute_key_variants(attr):
            if candidate in response_entries:
                entry = response_entries[candidate]
                break
        if isinstance(entry, Mapping):
            value_field = entry.get("value")
            if value_field is not None:
                value_obj: object | None = value_field
            else:
                value_obj = entry
            oov_candidate = _normalize_optional_llm_text(entry.get("oov_candidate"))
            note = _normalize_optional_llm_text(entry.get("note"))
        elif entry is None:
            value_obj = "n/a (not stated)"
        else:
            value_obj = entry
        if not isinstance(value_obj, (str, int, float)):
            results[attr] = _AttributeLLMResult(
                value="N/A", oov_candidate=oov_candidate, note=note
            )
            continue
        value_text = str(value_obj).strip()
        value_lower = value_text.lower()
        value_clean = _strip_annotations_for_unknowns(value_lower)
        if attr in {"spf", "spf_value"}:
            parsed = _parse_spf_value(value_lower)
            results[attr] = _AttributeLLMResult(
                value=str(parsed) if parsed is not None else "N/A",
                oov_candidate=oov_candidate,
                note=note,
            )
            continue
        allowed = allowed_values.get(attr)
        if allowed:
            lookup = allowed_lookup.get(attr, {})
            alias_map: dict[str, str] = {}
            nodes = nodes_by_label.get(attr)
            if nodes:
                for alias_key, canonical in _leaf_synonym_map(nodes).items():
                    alias_map[alias_key] = canonical
            if attr_alias_map and attr in attr_alias_map:
                for alias_key, canonical in attr_alias_map[attr].items():
                    alias_map[alias_key.strip().lower()] = canonical
            chosen = None
            if value_lower in lookup:
                chosen = lookup[value_lower]
            else:
                mapped = alias_map.get(value_lower)
                if mapped:
                    chosen = lookup.get(str(mapped).strip().lower(), mapped)
                else:
                    normalized_candidate = _normalize_for_allowed(value_lower)
                    chosen = lookup.get(normalized_candidate)
            results[attr] = _AttributeLLMResult(
                value=chosen if chosen else NOT_IN_TAXONOMY_VALUE,
                oov_candidate=oov_candidate,
                note=note,
            )
            continue
        if value_clean in {"no idea", "unknown", "n/a", "na", "", "n/a (not stated)"}:
            results[attr] = _AttributeLLMResult(
                value="N/A", oov_candidate=oov_candidate, note=note
            )
        elif value_clean in {
            "other",
            "other (not in list)",
            NOT_IN_TAXONOMY_VALUE.lower(),
        }:
            results[attr] = _AttributeLLMResult(
                value=NOT_IN_TAXONOMY_VALUE,
                oov_candidate=oov_candidate,
                note=note,
            )
        else:
            results[attr] = _AttributeLLMResult(
                value=value_text, oov_candidate=oov_candidate, note=note
            )
    return results


def _variants_payload_to_map(payload: object) -> dict[str, object]:
    if isinstance(payload, Mapping):
        return {str(k): v for k, v in payload.items()}
    if isinstance(payload, Sequence) and not isinstance(
        payload, (str, bytes, bytearray)
    ):
        mapping: dict[str, object] = {}
        for item in payload:
            if isinstance(item, Mapping):
                identifier = (
                    item.get("variant_id")
                    or item.get("id")
                    or item.get("variantKey")
                    or item.get("variant_key")
                )
                if identifier:
                    mapping[str(identifier)] = item.get("attributes") or item
        return mapping
    return {}


def _summarize_variant(row: Mapping[str, object]) -> str:
    parts: list[str] = []
    shade = str(row.get("shade_name_raw") or "").strip()
    size = str(row.get("size_text_raw") or "").strip()
    variant_desc = str(row.get("variant_description") or "").strip()
    if shade:
        parts.append(f"Shade: {shade}")
    if size:
        parts.append(f"Size: {size}")
    if variant_desc:
        parts.append(f"Details: {variant_desc}")
    return "; ".join(parts) or "No additional details provided."


def _build_pdp_prompt(request: _ParentLLMRequest) -> str:
    parent_attrs = ", ".join(request.missing_attrs) if request.missing_attrs else "none"
    variant_lines: list[str] = []
    for variant in request.variants:
        target = ", ".join(variant.missing_attrs) if variant.missing_attrs else "none"
        identifier = variant.variant_id or variant.variant_key
        details = variant.context_text or "No variant-specific context."
        variant_lines.append(
            "\n".join(
                [
                    f"- variant_id: {identifier}",
                    f"  Target attributes: {target}",
                    f"  Name: {variant.display_name or '(unknown)'}",
                    f"  PDP text: {details}",
                ]
            )
        )
    variant_section = "\n".join(variant_lines) if variant_lines else "- none"
    parent_allowed = json.dumps(request.allowed_values or {}, ensure_ascii=False)
    variant_allowed = json.dumps(
        {(v.variant_id or v.variant_key): v.allowed_values for v in request.variants},
        ensure_ascii=False,
    )
    output_contract = (
        "{\n"
        '  "parent": {\n'
        '    "ATTRIBUTE_ID": {"value": str, "oov_candidate": str|null, "note": str|null}\n'
        "  },\n"
        '  "variants": {\n'
        '    "VARIANT_ID": {\n'
        '      "ATTRIBUTE_ID": {"value": str, "oov_candidate": str|null, "note": str|null}\n'
        "    }\n"
        "  }\n"
        "}"
    )
    example_payload = (
        "{\n"
        '  "parent": {\n'
        '    "finish": {"value": "matte", "oov_candidate": null, "note": null}\n'
        "  },\n"
        '  "variants": {\n'
        '    "VARIANT123": {\n'
        '      "finish": {"value": "radiant/luminous", "oov_candidate": null, "note": "Variant marketing copy calls this radiant."}\n'
        "    }\n"
        "  }\n"
        "}"
    )
    output_schema = (
        "{\n"
        '  "parent": {\n'
        '    "Attribute": {"value": str, "oov_candidate": str|null, "note": str|null}\n'
        "  },\n"
        '  "variants": {\n'
        '    "VARIANT_ID": {\n'
        '      "Attribute": {"value": str, "oov_candidate": str|null, "note": str|null}\n'
        "    }\n"
        "  }\n"
        "}"
    )
    prompt_parts = [
        "You are mapping cosmetic product attributes from PDP data.",
        'Return JSON with exactly two top-level keys: "parent" and "variants".',
        'Do NOT return a root object called "values"; that format is invalid.',
        'For each variant we list, use its exact variant_id as the key under "variants" and capture any differences from the parent.',
        'Select canonical labels from the options we provide; if a value is unstated, output "N/A".',
    ]
    prompt_parts.extend(
        [
            "",
            "Parent context:",
            f"- Category: {request.category_label or '(unknown)'}",
            f"- Category path: {request.category_path or '(unknown)'}",
            f"- Product: {request.display_name}",
            f"- Target attributes: {parent_attrs}",
        ]
    )
    if request.deterministic_text:
        summary = re.sub(r"\s+", " ", request.deterministic_text.strip())
        prompt_parts.append(f"- Summary: {summary}")
    prompt_parts.extend(
        [
            "",
            "Parent PDP text:",
            request.pdp_text or "No parent PDP context.",
            "",
            "Variants (evaluate each independently and record their own attribute values):",
            variant_section,
            "",
            "Output must use this contract:",
            output_contract,
            "",
            "Example of a correct response when a variant differs from the parent:",
            example_payload,
            "",
            "Allowed values for parent attributes (JSON):```json\n"
            + parent_allowed
            + "\n```",
            "Allowed values for variant attributes keyed by variant_id (JSON):```json\n"
            + variant_allowed
            + "\n```",
            "",
            "Output JSON schema example:",
            output_schema,
        ]
    )
    return "\n".join(prompt_parts)


def _parse_pdp_response(
    response: object,
    request: _ParentLLMRequest,
) -> _ParsedPdpLLMResponse:
    def _decode_jsonish(value: object) -> Mapping[str, object] | None:
        """Best-effort decode of JSON-ish payloads (text, mappings, or lists)."""
        if isinstance(value, Mapping):
            if "parent" in value or "variants" in value:
                return value
            for key in (
                "json",
                "text",
                "output_text",
                "output",
                "body",
                "response",
                "content",
            ):
                if key in value:
                    decoded = _decode_jsonish(value.get(key))
                    if decoded is not None:
                        return decoded
            for item in value.values():
                decoded = _decode_jsonish(item)
                if decoded is not None:
                    return decoded
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(
                    r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE
                ).strip()
                cleaned = re.sub(r"```$", "", cleaned).strip()
            try:
                decoded, _ = json.JSONDecoder().raw_decode(cleaned)
                if isinstance(decoded, Mapping):
                    return decoded
            except Exception:
                pass
            try:
                decoded = json.loads(cleaned)
                if isinstance(decoded, Mapping):
                    return decoded
            except Exception:
                return None
        if isinstance(value, Sequence):
            for item in value:
                decoded = _decode_jsonish(item)
                if decoded is not None:
                    return decoded
        return None

    def _coerce_response(resp: object) -> Mapping[str, object] | None:
        """Normalize response shapes from batch/sequential LLM calls."""
        if isinstance(resp, Mapping) and ("parent" in resp or "variants" in resp):
            return resp

        # content items shaped like {"type": "...", "text": "..."} from batch
        if isinstance(resp, Mapping) and "text" in resp and "type" in resp:
            decoded = _decode_jsonish(resp.get("text"))
            if decoded is not None:
                return decoded

        # OpenAI Responses API: {response: {body: {output: [{content: [{json|text|output_text: ...}]}]}}}
        if isinstance(resp, Mapping):
            payload = resp.get("response", resp)
            if isinstance(payload, Mapping):
                body = payload.get("body", payload)
                output = body.get("output")
                if isinstance(output, Sequence):
                    for entry in output:
                        if not isinstance(entry, Mapping):
                            continue
                        content = entry.get("content")
                        if not isinstance(content, Sequence):
                            continue
                        for part in content:
                            if not isinstance(part, Mapping):
                                continue
                            if "json" in part:
                                decoded = _decode_jsonish(part.get("json"))
                                if decoded is not None:
                                    return decoded
                            if "text" in part:
                                decoded = _decode_jsonish(part.get("text"))
                                if decoded is not None:
                                    return decoded
                            if part.get("type") == "output_text" and "text" in part:
                                decoded = _decode_jsonish(part.get("text"))
                                if decoded is not None:
                                    return decoded
                        decoded = _decode_jsonish(content)
                        if decoded is not None:
                            return decoded
            raw_payload = resp.get("raw")
            decoded = _decode_jsonish(raw_payload)
            if decoded is not None:
                return decoded

        decoded = _decode_jsonish(resp)
        if decoded is not None:
            return decoded
        return None

    normalized = _coerce_response(response)
    if normalized is None:
        return {"parent": {}, "variants": {}}
    response = normalized

    parent_payload = response.get("parent")
    if parent_payload is None and request.missing_attrs:
        parent_payload = response
    parent_results = _canonicalize_attribute_map(
        parent_payload if isinstance(parent_payload, Mapping) else {},
        request.missing_attrs,
        request.allowed_values,
        request.nodes_by_label,
    )
    variants_payload_raw = response.get("variants")
    variants_payload = _variants_payload_to_map(variants_payload_raw)
    variant_results: dict[str, dict[str, str]] = {}
    for variant in request.variants:
        identifier = variant.variant_id or variant.variant_key
        payload = variants_payload.get(identifier, {})
        variant_results[identifier] = _canonicalize_attribute_map(
            payload if isinstance(payload, Mapping) else {},
            variant.missing_attrs,
            variant.allowed_values,
            variant.nodes_by_label,
        )
    return {"parent": parent_results, "variants": variant_results}


def _collect_missing_attributes(
    row: dict[str, object],
    attr_meta: dict[str, tuple[str, Mapping[str, object]]],
    rows: list[dict[str, object]],
    column_names: list[str],
    column_map: dict[str, str],
    scope_whitelist: set[str],
    *,
    category_key: str | None,
    row_scope: str,
) -> tuple[list[str], dict[str, list[str]], dict[str, list[Mapping[str, object]]]]:
    missing_attrs: list[str] = []
    allowed_values: dict[str, list[str]] = {}
    nodes_by_label: dict[str, list[Mapping[str, object]]] = {}
    lower_column_lookup: dict[str, str] = {
        str(col).lower(): col for col in column_names
    }
    for attr_label, (label_text, info) in attr_meta.items():
        attr_id = str(info.get("id") or attr_label).strip()
        if not _attribute_matches_row_scope(info, row_scope=row_scope):
            continue
        if not _attribute_enabled_for_category(
            category_key,
            attr_id,
            row_scope=row_scope,
        ):
            continue
        column_name = column_map.get(attr_label)
        if not column_name:
            candidates: list[str] = []
            if attr_id:
                candidates.append(attr_id)
                normalized_id = _normalize_key(attr_id)
                if normalized_id and normalized_id != attr_id:
                    candidates.append(normalized_id)
            if label_text:
                label_clean = str(label_text).strip()
                if label_clean:
                    candidates.append(label_clean)
                    lower_label = label_clean.lower()
                    if lower_label != label_clean:
                        candidates.append(lower_label)
                    normalized_label = _normalize_key(label_clean)
                    if normalized_label and normalized_label not in candidates:
                        candidates.append(normalized_label)
            candidates.append(attr_label)

            resolved_name: str | None = None
            for candidate in candidates:
                if not candidate:
                    continue
                if candidate in column_names:
                    resolved_name = candidate
                    break
                lower_candidate = candidate.lower()
                if lower_candidate in lower_column_lookup:
                    resolved_name = lower_column_lookup[lower_candidate]
                    break

            if not resolved_name:
                fallback = (
                    attr_id or _normalize_key(str(label_text or "")) or attr_label
                )
                resolved_name = fallback or attr_label

            column_name = resolved_name
            if column_name not in column_names:
                column_names.append(column_name)
                lower_column_lookup[column_name.lower()] = column_name
                for existing in rows:
                    existing.setdefault(column_name, None)
        column_map[attr_label] = column_name
        value = row.get(column_name)
        is_placeholder = _is_placeholder_value(value)
        if not is_placeholder:
            continue
        scope = str(info.get("scope", "product")).strip().lower()
        if scope_whitelist and scope not in scope_whitelist:
            continue
        missing_attrs.append(attr_label)
        nodes = info.get("nodes") or []
        nodes_by_label[attr_label] = nodes if isinstance(nodes, list) else []
        leaves = _leaf_labels(nodes)
        if leaves:
            allowed_values[attr_label] = leaves
    return missing_attrs, allowed_values, nodes_by_label


def _run_pdp_llm_batch(
    llm_wrapper: Any,
    requests: Sequence[_ParentLLMRequest],
    query_step: str,
    *,
    extra_body: dict | None = None,
    llm_dump_path: Path | None = None,
) -> list[_ParsedPdpLLMResponse]:
    if not requests:
        return [{} for _ in requests]

    from modules.llm.batch_runner import run_step_json

    prompts = [_build_pdp_prompt(req) for req in requests]
    system_prompt = "You are an expert category product analyst. Return JSON only."

    responses = run_step_json(
        llm_wrapper,
        query_step,
        system_prompt,
        prompts,
        extra_body=extra_body,
    )
    if llm_dump_path:
        try:
            with Path(llm_dump_path).open("a", encoding="utf-8") as fh:
                for req, resp in zip(requests, responses):
                    record = {
                        "parent_product_id": req.parent_product_id,
                        "missing_attrs": req.missing_attrs,
                        "response": resp,
                    }
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:
            LOGGER.warning("Failed to dump LLM response to %s: %s", llm_dump_path, exc)

    results: list[_ParsedPdpLLMResponse] = []
    if len(responses) != len(requests):  # pragma: no cover - safety
        LOGGER.warning(
            "LLM batch returned mismatched response count (expected %s, got %s)",
            len(requests),
            len(responses),
        )
        responses = responses[: len(requests)]
    for resp, req in zip(responses, requests):
        results.append(_parse_pdp_response(resp, req))
    return results


def _leaf_labels(nodes: Sequence[Mapping[str, object]] | None) -> list[str]:
    labels: list[str] = []
    if not nodes:
        return labels
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        children = node.get("children")
        if isinstance(children, Sequence) and not isinstance(
            children, (str, bytes, bytearray)
        ):
            labels.extend(_leaf_labels(children))  # type: ignore[arg-type]
        else:
            label = node.get("label")
            if label:
                labels.append(str(label).strip().lower())
    return labels


def _is_placeholder_value(value: object | None) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    return text.lower() in _ATTRIBUTE_PLACEHOLDERS


def _build_category_attribute_lookup(
    taxonomy: Mapping[str, object],
) -> dict[str, dict[str, tuple[str, Mapping[str, object]]]]:
    lookup: dict[str, dict[str, tuple[str, Mapping[str, object]]]] = {}
    for cat in taxonomy.get("categories", []) or []:
        if not isinstance(cat, Mapping):
            continue
        attr_map: dict[str, tuple[str, Mapping[str, object]]] = {}
        for attr in cat.get("attributes", []) or []:
            if not isinstance(attr, Mapping):
                continue
            raw_label = str(attr.get("label", "")).strip()
            label = _normalize_key(raw_label)
            if label:
                attr_map[label] = (raw_label or label, attr)
        if not attr_map:
            continue
        for key in (
            str(cat.get("id", "")).strip().lower(),
            str(cat.get("label", "")).strip().lower(),
        ):
            normalized = _normalize_key(key)
            if normalized:
                lookup[normalized] = attr_map
    return lookup


def _describe_variant_for_llm(row: Mapping[str, object]) -> str:
    parts: list[str] = []
    shade = row.get("shade_name_raw")
    if isinstance(shade, str) and shade.strip():
        parts.append(f"shade '{shade.strip()}'")
    size = row.get("size_text_raw")
    if isinstance(size, str) and size.strip():
        parts.append(size.strip())
    desc = ""
    variant_desc = row.get("variant_description")
    if isinstance(variant_desc, str) and variant_desc.strip():
        desc = variant_desc.strip()
    elif isinstance(row.get("description"), str) and row["description"].strip():
        desc = row["description"].strip()
    summary = ", ".join(parts) if parts else ""
    if desc:
        return f"{summary}: {desc}" if summary else desc
    return summary


_CATEGORY_ATTRIBUTE_SUPPRESSION: dict[str, dict[str, set[str]]] = {
    "permanent": {
        # Product type is redundant with the category itself, and shade-level
        # tone/level belongs to the retailer filter/shade universe, not to PDP
        # classification. Suppress these attributes for permanent across all
        # retailers so we do not classify 100+ shade SKUs.
        "all": {"category", "haircolor_tone", "haircolor_level"},
    }
}


def _attribute_enabled_for_category(
    category_key: str | None,
    attribute_id: str | None,
    *,
    row_scope: str | None,
) -> bool:
    normalized_category = _normalize_key(category_key)
    normalized_attr = _normalize_key(attribute_id)
    if not normalized_category or not normalized_attr:
        return True
    policy = _CATEGORY_ATTRIBUTE_SUPPRESSION.get(normalized_category)
    if not policy:
        return True
    scope_key = _normalize_key(row_scope)
    blocked = set(policy.get("all", set()))
    if scope_key:
        blocked.update(policy.get(scope_key, set()))
    return normalized_attr not in blocked


def _attribute_matches_row_scope(
    info: Mapping[str, object],
    *,
    row_scope: str | None,
) -> bool:
    normalized_scope = _normalize_key(row_scope)
    if not normalized_scope:
        return True
    attr_scope = _normalize_key(str(info.get("scope") or ""))
    if not attr_scope:
        return True
    if normalized_scope == "parent":
        return attr_scope in {"product", "parent", "all"}
    if normalized_scope == "variant":
        return attr_scope in {"variant", "all"}
    return True


def _build_variant_context_map(variant_df: pl.DataFrame) -> dict[tuple[str, str], str]:
    if variant_df.is_empty() or "parent_product_id" not in variant_df.columns:
        return {}
    rows = variant_df.select(
        [
            "parent_product_id",
            "category_key",
            "shade_name_raw",
            "size_text_raw",
            "variant_description",
            "description",
        ]
    ).to_dicts()
    mapping: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        parent_id = row.get("parent_product_id")
        if not isinstance(parent_id, str) or not parent_id.strip():
            continue
        category_key = _normalize_key(str(row.get("category_key") or ""))
        snippet = _describe_variant_for_llm(row)
        if not snippet:
            continue
        mapping.setdefault((parent_id.strip(), category_key), []).append(snippet)
    summary: dict[tuple[str, str], str] = {}
    for parent_key, snippets in mapping.items():
        limited = snippets[:_LLM_VARIANT_CONTEXT_LIMIT]
        summary[parent_key] = "; ".join(limited)
    return summary


def _llm_fill_pdp_attributes(
    llm_wrapper: Any,
    parent_df: pl.DataFrame,
    variant_df: pl.DataFrame,
    taxonomy: Mapping[str, object],
    *,
    llm_dump_path: Path | None = None,
) -> tuple[
    pl.DataFrame,
    pl.DataFrame,
    dict[str, set[str]],
    dict[_AttributeRecordKey, _AttributeRecordMeta],
]:
    if llm_wrapper is None or parent_df.is_empty():
        return parent_df, variant_df, {"parent": set(), "variant": set()}, {}

    attr_lookup = _build_category_attribute_lookup(taxonomy)
    parent_rows = parent_df.to_dicts()
    variant_rows = variant_df.to_dicts()
    touched: dict[str, set[str]] = {"parent": set(), "variant": set()}
    llm_attribute_meta: dict[_AttributeRecordKey, _AttributeRecordMeta] = {}
    parent_columns = list(parent_df.columns)
    variant_columns = list(variant_df.columns)
    variant_context_summary = _build_variant_context_map(variant_df)

    variants_by_parent: dict[tuple[str, str], list[int]] = {}
    for idx, variant_row in enumerate(variant_rows):
        parent_id = str(variant_row.get("parent_product_id") or "").strip()
        category_key = _normalize_key(str(variant_row.get("category_key") or ""))
        if parent_id:
            variants_by_parent.setdefault((parent_id, category_key), []).append(idx)

    requests: list[_ParentLLMRequest] = []
    for parent_index, parent_row in enumerate(parent_rows):
        category_key = _normalize_key(str(parent_row.get("category_key", "")))
        attr_meta = attr_lookup.get(category_key)
        if not attr_meta:
            continue

        parent_attr_map: dict[str, str] = {}
        missing_parent, allowed_parent, nodes_parent = _collect_missing_attributes(
            parent_row,
            attr_meta,
            parent_rows,
            parent_columns,
            parent_attr_map,
            {"product", "parent", "all"},
            category_key=category_key,
            row_scope="parent",
        )

        variant_requests: list[_VariantLLMRequest] = []
        parent_id = str(parent_row.get("parent_product_id") or "").strip()
        for variant_index in variants_by_parent.get((parent_id, category_key), []):
            variant_row = variant_rows[variant_index]
            variant_attr_map: dict[str, str] = {}
            missing_variant, allowed_variant, nodes_variant = (
                _collect_missing_attributes(
                    variant_row,
                    attr_meta,
                    variant_rows,
                    variant_columns,
                    variant_attr_map,
                    {"product", "variant", "all"},
                    category_key=category_key,
                    row_scope="variant",
                )
            )
            if not missing_variant:
                continue
            variant_context = str(variant_row.get("variant_description") or "").strip()
            if not variant_context:
                variant_context = str(variant_row.get("description") or "").strip()
            if variant_context:
                variant_context = re.sub(r"\s+", " ", variant_context)
            if not variant_context:
                variant_context = _summarize_variant(variant_row)
            variant_requests.append(
                _VariantLLMRequest(
                    row_index=variant_index,
                    variant_id=str(variant_row.get("variant_id") or ""),
                    variant_key=str(variant_row.get("variant_key") or ""),
                    display_name=_summarize_variant(variant_row),
                    context_text=variant_context,
                    missing_attrs=missing_variant,
                    allowed_values=allowed_variant,
                    nodes_by_label=nodes_variant,
                    attr_column_map=variant_attr_map,
                )
            )

        if not missing_parent and not variant_requests:
            continue

        brand = str(parent_row.get("brand") or "").strip()
        product_name = str(parent_row.get("product_name") or "").strip()
        display_name = (
            " ".join(part for part in (brand, product_name) if part)
            or parent_id
            or "product"
        )
        raw_category_path = parent_row.get("raw_category_path")
        if isinstance(raw_category_path, Sequence) and not isinstance(
            raw_category_path, (str, bytes, bytearray)
        ):
            category_path = " > ".join(
                str(item).strip()
                for item in raw_category_path
                if isinstance(item, (str, int, float))
            ).strip()
        else:
            category_path = ""
        description = str(parent_row.get("description") or "").strip()
        variant_summary = variant_context_summary.get(
            (parent_id, category_key),
            "",
        ).strip()
        deterministic_lines: list[str] = []
        if brand:
            deterministic_lines.append(f"Brand: {brand}")
        if product_name:
            deterministic_lines.append(f"Product name: {product_name}")
        if variant_summary:
            deterministic_lines.append(f"Variant summary: {variant_summary}")
        deterministic_text = "\n".join(deterministic_lines).strip()
        if description and variant_summary:
            parent_pdp_text = f"{description}\nVariant highlights: {variant_summary}"
        elif description:
            parent_pdp_text = description
        elif variant_summary:
            parent_pdp_text = f"Variant highlights: {variant_summary}"
        else:
            parent_pdp_text = ""
        parent_pdp_text = parent_pdp_text.strip()

        requests.append(
            _ParentLLMRequest(
                row_index=parent_index,
                parent_product_id=parent_id,
                display_name=display_name,
                category_label=str(
                    parent_row.get("category_label")
                    or parent_row.get("category_id")
                    or ""
                ),
                category_path=category_path or "",
                deterministic_text=deterministic_text,
                pdp_text=parent_pdp_text,
                missing_attrs=missing_parent,
                allowed_values=allowed_parent,
                nodes_by_label=nodes_parent,
                attr_column_map=parent_attr_map,
                variants=variant_requests,
            )
        )

    if not requests:
        LOGGER.info("LLM fill: no queued parents (nothing missing).")
        return parent_df, variant_df, touched, llm_attribute_meta

    LOGGER.info("LLM fill: queued %s parent requests", len(requests))

    naming = get_naming_params()
    query_step = naming.get(
        "pdpClassificationQuery",
        naming.get(
            "classifyPdpAttributesQuery", naming["attributeClassificationQuery"]
        ),
    )
    response_schema = {
        "text": {
            "format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "pdp_classification",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "parent": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "object",
                                    "properties": {
                                        "value": {"type": ["string", "number", "null"]},
                                        "oov_candidate": {"type": ["string", "null"]},
                                        "note": {"type": ["string", "null"]},
                                    },
                                    "required": ["value"],
                                    "additionalProperties": False,
                                },
                            },
                            "variants": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "object",
                                    "additionalProperties": {
                                        "type": "object",
                                        "properties": {
                                            "value": {
                                                "type": ["string", "number", "null"]
                                            },
                                            "oov_candidate": {
                                                "type": ["string", "null"]
                                            },
                                            "note": {"type": ["string", "null"]},
                                        },
                                        "required": ["value"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                        },
                        "required": ["parent", "variants"],
                        "additionalProperties": False,
                    },
                },
            }
        }
    }
    responses = _run_pdp_llm_batch(
        llm_wrapper,
        requests,
        query_step,
        extra_body=response_schema,
        llm_dump_path=llm_dump_path,
    )

    for request, parsed in zip(requests, responses):
        parent_values_raw = (
            parsed.get("parent", {}) if isinstance(parsed, Mapping) else {}
        )
        parent_values = (
            parent_values_raw if isinstance(parent_values_raw, Mapping) else {}
        )
        if LOGGER.isEnabledFor(logging.INFO):
            LOGGER.info(
                "LLM parent %s applied attributes: %s",
                request.parent_product_id,
                {
                    request.attr_column_map.get(attr): _coerce_llm_result(value).value
                    for attr, value in parent_values.items()
                },
            )
        parent_row = parent_rows[request.row_index]
        parent_retailer = str(parent_row.get("retailer") or "").strip()
        parent_product_id = str(
            parent_row.get("parent_product_id") or request.parent_product_id
        ).strip()
        parent_category_key = _normalize_key(str(parent_row.get("category_key") or ""))
        for attr_label, value in parent_values.items():
            column_name = request.attr_column_map.get(attr_label)
            if column_name:
                llm_result = _coerce_llm_result(value)
                llm_selected = _apply_llm_choice(
                    parent_row, column_name, llm_result.value
                )
                if llm_selected:
                    touched["parent"].add(column_name)
                    if (
                        (
                            llm_result.oov_candidate is not None
                            or llm_result.note is not None
                        )
                        and parent_retailer
                        and parent_product_id
                    ):
                        meta_key: _AttributeRecordKey = (
                            parent_retailer,
                            "parent",
                            parent_product_id,
                            "",
                            parent_category_key,
                            column_name,
                        )
                        llm_attribute_meta[meta_key] = _AttributeRecordMeta(
                            oov_candidate=llm_result.oov_candidate,
                            note=llm_result.note,
                        )
        variant_maps_raw = (
            parsed.get("variants", {}) if isinstance(parsed, Mapping) else {}
        )
        variant_maps = variant_maps_raw if isinstance(variant_maps_raw, Mapping) else {}
        for variant_request in request.variants:
            identifier = variant_request.variant_id or variant_request.variant_key
            values_map = (
                variant_maps.get(identifier, {})
                if isinstance(variant_maps, Mapping)
                else {}
            )
            variant_row = variant_rows[variant_request.row_index]
            variant_retailer = str(
                variant_row.get("retailer") or parent_retailer
            ).strip()
            variant_parent_id = str(
                variant_row.get("parent_product_id") or parent_product_id
            ).strip()
            variant_id = str(variant_row.get("variant_id") or identifier).strip()
            variant_category_key = _normalize_key(
                str(variant_row.get("category_key") or parent_category_key)
            )
            for attr_label, value in values_map.items():
                column_name = variant_request.attr_column_map.get(attr_label)
                if column_name:
                    llm_result = _coerce_llm_result(value)
                    llm_selected = _apply_llm_choice(
                        variant_row, column_name, llm_result.value
                    )
                    if llm_selected:
                        touched["variant"].add(column_name)
                        if (
                            (
                                llm_result.oov_candidate is not None
                                or llm_result.note is not None
                            )
                            and variant_retailer
                            and variant_parent_id
                            and variant_id
                        ):
                            meta_key = (
                                variant_retailer,
                                "variant",
                                variant_parent_id,
                                variant_id,
                                variant_category_key,
                                column_name,
                            )
                            llm_attribute_meta[meta_key] = _AttributeRecordMeta(
                                oov_candidate=llm_result.oov_candidate,
                                note=llm_result.note,
                            )
            if LOGGER.isEnabledFor(logging.INFO):
                LOGGER.info(
                    "LLM variant %s applied attributes: %s",
                    identifier,
                    {
                        variant_request.attr_column_map.get(attr): _coerce_llm_result(
                            value
                        ).value
                        for attr, value in values_map.items()
                    },
                )

    parent_out = _rows_to_dataframe(parent_rows, parent_columns, parent_df.schema)
    parent_extra_cols = [col for col in parent_out.columns if col not in parent_columns]
    if parent_extra_cols:
        parent_columns = list(parent_columns) + parent_extra_cols
    parent_out = parent_out.select(
        [col for col in parent_columns if col in parent_out.columns]
    )

    variant_out = _rows_to_dataframe(variant_rows, variant_columns, variant_df.schema)
    variant_extra_cols = [
        col for col in variant_out.columns if col not in variant_columns
    ]
    if variant_extra_cols:
        variant_columns = list(variant_columns) + variant_extra_cols
    variant_out = variant_out.select(
        [col for col in variant_columns if col in variant_out.columns]
    )

    if LOGGER.isEnabledFor(logging.INFO):
        for req, parsed in zip(requests, responses):
            parent_applied: dict[str, str] = {}
            variant_applied: dict[str, dict[str, str]] = {}
            parent_values = (
                parsed.get("parent", {}) if isinstance(parsed, Mapping) else {}
            )
            for attr_label, value in parent_values.items():
                column_name = req.attr_column_map.get(attr_label)
                llm_value = _coerce_llm_result(value).value
                if column_name and not _is_placeholder_value(llm_value):
                    parent_applied[column_name] = str(llm_value)
            variants_payload = (
                parsed.get("variants", {}) if isinstance(parsed, Mapping) else {}
            )
            for variant_request in req.variants:
                identifier = variant_request.variant_id or variant_request.variant_key
                applied: dict[str, str] = {}
                raw_values = variants_payload.get(identifier, {})
                if isinstance(raw_values, Mapping):
                    for attr_label, value in raw_values.items():
                        column_name = variant_request.attr_column_map.get(attr_label)
                        llm_value = _coerce_llm_result(value).value
                        if column_name and not _is_placeholder_value(llm_value):
                            applied[column_name] = str(llm_value)
                if applied:
                    variant_applied[identifier] = applied
            if parent_applied or variant_applied:
                parent_count = len(parent_applied)
                variant_total = sum(len(vals) for vals in variant_applied.values())
                LOGGER.info(
                    "LLM applied attributes for parent %s: parent_fields=%s variant_fields=%s (variants=%s)",
                    req.parent_product_id,
                    parent_count,
                    variant_total,
                    len(variant_applied),
                )
            else:
                LOGGER.info(
                    "LLM response produced no attribute overrides for parent %s (requested=%s variants=%s)",
                    req.parent_product_id,
                    req.missing_attrs,
                    [v.variant_id or v.variant_key for v in req.variants],
                )

    return parent_out, variant_out, touched, llm_attribute_meta


def _harmonize_parent_variant_attributes(
    parent_df: pl.DataFrame,
    variant_df: pl.DataFrame,
) -> pl.DataFrame:
    if parent_df.is_empty() or variant_df.is_empty():
        return parent_df

    attr_cols = [col for col in variant_df.columns if col not in VARIANT_BASE_COLUMNS]
    if not attr_cols:
        return parent_df

    parent_rows = parent_df.to_dicts()
    parent_columns = list(parent_df.columns)
    parent_index: dict[tuple[str, str], dict[str, object]] = {}
    for row in parent_rows:
        parent_id = row.get("parent_product_id")
        if isinstance(parent_id, str):
            category_key = _normalize_key(str(row.get("category_key") or ""))
            key = (parent_id.strip(), category_key)
            if key[0]:
                parent_index[key] = row

    if not parent_index:
        return parent_df

    variant_rows = variant_df.to_dicts()
    parent_schema = parent_df.schema
    variant_schema = variant_df.schema
    for attr in attr_cols:
        per_parent: dict[tuple[str, str], dict[str, object]] = {}
        attr_dtype = parent_schema.get(attr) or variant_schema.get(attr)
        for row in variant_rows:
            parent_id = row.get("parent_product_id")
            if not isinstance(parent_id, str):
                continue
            category_key = _normalize_key(str(row.get("category_key") or ""))
            key = (parent_id.strip(), category_key)
            if not key[0]:
                continue
            value = row.get(attr)
            if _is_placeholder_value(value):
                continue
            if value is None:
                continue
            try:
                serialized = json.dumps(value, sort_keys=True, default=str)
            except TypeError:
                serialized = repr(value)
            per_parent.setdefault(key, {})
            per_parent[key][serialized] = value

        for parent_key, value_map in per_parent.items():
            parent_row = parent_index.get(parent_key)
            if parent_row is None:
                continue
            category_key = _normalize_key(str(parent_row.get("category_key") or ""))
            if not _attribute_enabled_for_category(
                category_key,
                attr,
                row_scope="parent",
            ):
                continue
            values = list(value_map.values())
            if len(values) == 1:
                if _is_placeholder_value(parent_row.get(attr)):
                    parent_row[attr] = values[0]
            elif len(values) > 1:
                if attr_dtype == pl.Boolean:
                    parent_row[attr] = None
                else:
                    parent_row[attr] = "N/A"

    refreshed = _rows_to_dataframe(parent_rows, parent_columns, parent_df.schema)
    for attr in attr_cols:
        if attr in refreshed.columns and attr not in parent_columns:
            parent_columns.append(attr)
    return refreshed.select([col for col in parent_columns if col in refreshed.columns])


def _load_parent_products(
    pdp_store_path: Path | str,
    taxonomy: Mapping[str, object],
    retailers: Sequence[str] | None = None,
    *,
    category_aliases: Mapping[str, str] | None = None,
    requested_categories: Sequence[str] | None = None,
) -> tuple[pl.DataFrame, set[str], dict[str, set[str]], pl.DataFrame]:
    path = Path(pdp_store_path)
    if not pdp_database_exists(path):
        raise FileNotFoundError(f"PDP database not found: {path}")

    query = """
        SELECT
            retailer,
            parent_product_id,
            pdp_url,
            brand_raw,
            title_raw,
            category_path,
            extras
        FROM parent_products
    """
    params: list[str] = []
    if retailers:
        placeholders = ",".join("?" for _ in retailers)
        query += f" WHERE LOWER(retailer) IN ({placeholders})"
        params = [r.lower() for r in retailers]

    with connect_pdp_database(path) as conn:
        try:
            rows = conn.execute(query, params).fetchall()
        except Exception:
            return pl.DataFrame(), set(), {}, _empty_pdp_source_segments_df()

    if not rows:
        return pl.DataFrame(), set(), {}, _empty_pdp_source_segments_df()

    category_index: dict[str, tuple[str, str]] = {}
    links_category_lookup = _load_links_category_lookup()
    links_category_memberships = _load_links_category_memberships()
    for item in taxonomy.get("categories", []) or []:
        if not isinstance(item, Mapping):
            continue
        cid = str(item.get("id", "")).strip()
        clabel = str(item.get("label", "")).strip()
        key_id = _normalize_key(cid)
        key_label = _normalize_key(clabel)
        if cid and key_id and key_id not in category_index:
            category_index[key_id] = (cid, clabel)
        if clabel and key_label and key_label not in category_index:
            category_index[key_label] = (cid or clabel, clabel or cid)

    records: list[dict[str, object]] = []
    segment_rows: list[dict[str, object]] = []
    unmatched_categories: set[str] = set()
    unmatched_examples: dict[str, set[str]] = {}

    for row in rows:
        retailer, parent_id, url, brand, title, category_path_raw, extras_raw = row
        extras: Mapping[str, object] | None = None
        if extras_raw:
            try:
                parsed = json.loads(extras_raw)
                if isinstance(parsed, Mapping):
                    extras = parsed
            except json.JSONDecodeError:
                extras = None
        category_path_pretty = ""
        try:
            categories = json.loads(category_path_raw) if category_path_raw else []
        except json.JSONDecodeError:
            categories = []
        if isinstance(categories, list):
            parts: list[str] = []
            for value in categories:
                if isinstance(value, str):
                    cleaned = value.strip()
                    if cleaned:
                        parts.append(cleaned)
            category_path_pretty = " > ".join(parts)

        matched_category_id = ""
        matched_category_label = ""
        matched_key = ""
        category_key_override = ""
        link_categories = links_category_memberships.get(
            (_normalize_key(str(retailer or "")), _normalize_links_lookup_url(url)),
            (),
        )
        if extras:
            category_key_override = str(extras.get("category_key") or "").strip()
        if category_key_override:
            match = _match_category_value(
                category_key_override, category_index, category_aliases
            )
            if match:
                matched_category_id, matched_category_label, matched_key = match
        if isinstance(categories, list):
            for value in reversed(categories):
                if not isinstance(value, str):
                    continue
                if matched_category_id:
                    break
                match = _match_category_value(value, category_index, category_aliases)
                if match:
                    matched_category_id, matched_category_label, matched_key = match
                    break
        if not matched_category_id:
            links_category_key = links_category_lookup.get(
                (_normalize_key(str(retailer or "")), _normalize_links_lookup_url(url))
            )
            if links_category_key:
                match = _match_category_value(
                    links_category_key, category_index, category_aliases
                )
                if match:
                    matched_category_id, matched_category_label, matched_key = match

        if not matched_category_id and categories:
            raw = categories[-1]
            matched_category_id = str(raw)
            matched_category_label = str(raw)
            matched_key = _normalize_key(str(raw))

        if not matched_category_id:
            if categories:
                last_value = str(categories[-1])
                normalized = _normalize_key(last_value)
                unmatched_categories.add(normalized or "")
                example = category_path_pretty or last_value
                unmatched_examples.setdefault(normalized or "", set()).add(example)
            else:
                unmatched_categories.add("")
                unmatched_examples.setdefault("", set()).add("(no category path)")

        description = _flatten_description(extras)
        membership_keys: list[str] = []
        for link_category in link_categories:
            normalized_link_category = _normalize_key(link_category)
            if (
                normalized_link_category
                and normalized_link_category not in membership_keys
            ):
                membership_keys.append(normalized_link_category)
        if matched_key and matched_key not in membership_keys:
            if not membership_keys or category_key_override:
                membership_keys.append(matched_key)

        if not membership_keys:
            membership_keys = [matched_key] if matched_key else [""]

        for membership_key in membership_keys:
            category_id = matched_category_id
            category_label = matched_category_label
            if membership_key and membership_key != matched_key:
                membership_match = _match_category_value(
                    membership_key,
                    category_index,
                    category_aliases,
                )
                if membership_match:
                    category_id, category_label, _ = membership_match
                else:
                    category_id = membership_key
                    category_label = membership_key.replace("_", " ")

            segment_rows.extend(
                _build_parent_source_segment_rows(
                    retailer=str(retailer or "").strip(),
                    parent_product_id=str(parent_id or "").strip(),
                    category_key=membership_key,
                    title_raw=title,
                    extras=extras,
                )
            )

            records.append(
                {
                    "retailer": str(retailer or "").strip(),
                    "parent_product_id": str(parent_id or "").strip(),
                    "pdp_url": str(url or "").strip(),
                    "brand": str(brand or "").strip(),
                    "product_name": str(title or "").strip(),
                    "category_key": membership_key,
                    "category_id": category_id,
                    "category_label": category_label,
                    # Preserve the raw breadcrumb separately from listing memberships.
                    "category_path": categories if isinstance(categories, list) else [],
                    "raw_category_path": (
                        categories if isinstance(categories, list) else []
                    ),
                    "description": description,
                    "hero_image_url": None,
                }
            )

    return (
        pl.DataFrame(records),
        unmatched_categories,
        unmatched_examples,
        _rows_to_pdp_source_segments_dataframe(segment_rows),
    )


def _load_variants(
    pdp_store_path: Path | str,
    parent_df: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    path = Path(pdp_store_path)
    with connect_pdp_database(path) as conn:
        rows = conn.execute("""
            SELECT
                retailer,
                variant_id,
                parent_product_id,
                shade_name_raw,
                shade_name_normalized,
                size_text_raw,
                price_raw,
                currency,
                barcode,
                availability,
                swatch_image_url,
                hero_image_url,
                extras
            FROM variants
            """).fetchall()

    if not rows:
        return pl.DataFrame(), _empty_pdp_source_segments_df()

    lookup = parent_df.select(
        [
            "retailer",
            "parent_product_id",
            "product_name",
            "brand",
            "category_key",
            "category_id",
            "category_label",
            "description",
        ]
    ).unique()

    records: list[dict[str, object]] = []
    segment_rows: list[dict[str, object]] = []

    def _coerce_text(value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    def _coerce_text_list(value: object | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            cleaned = _coerce_text(value)
            return [cleaned] if cleaned else []
        if not isinstance(value, Sequence):
            return []
        items: list[str] = []
        for item in value:
            cleaned = _coerce_text(item)
            if cleaned:
                items.append(cleaned)
        return items

    for row in rows:
        (
            retailer,
            variant_id,
            parent_product_id,
            shade_name_raw,
            shade_name_normalized,
            size_text_raw,
            price_raw,
            currency,
            barcode,
            availability,
            swatch_url,
            hero_url,
            extras_raw,
        ) = row
        extras: Mapping[str, object] | None = None
        if extras_raw:
            try:
                parsed = json.loads(extras_raw)
                if isinstance(parsed, Mapping):
                    extras = parsed
            except json.JSONDecodeError:
                extras = None
        retailer_text = _coerce_text(retailer) or ""
        parent_product_id_text = _coerce_text(parent_product_id) or ""

        variant_segments = _collect_pdp_text_segments(extras)
        variant_description = " ".join(text for _, text in variant_segments)
        extra_backend_id = _coerce_text(
            extras.get("backend_id") if isinstance(extras, Mapping) else None
        )
        extra_backend_parent_id = _coerce_text(
            extras.get("backend_parent_id") if isinstance(extras, Mapping) else None
        )
        extra_barcodes = _coerce_text_list(
            extras.get("barcodes") if isinstance(extras, Mapping) else None
        )
        barcode_value = _coerce_text(barcode) or (
            extra_barcodes[0] if extra_barcodes else None
        )
        segment_rows.extend(
            _build_variant_source_segment_rows(
                retailer=retailer_text,
                parent_product_id=parent_product_id_text,
                variant_id=_coerce_text(variant_id) or "",
                category_key="",
                shade_name_raw=shade_name_raw,
                size_text_raw=size_text_raw,
                extras=extras,
            )
        )

        records.append(
            {
                "retailer": _coerce_text(retailer) or "",
                "parent_product_id": parent_product_id_text,
                "variant_id": _coerce_text(variant_id) or "",
                "variant_key": f"{parent_product_id}:{variant_id}",
                "shade_name_raw": _coerce_text(shade_name_raw),
                "shade_name_normalized": _coerce_text(shade_name_normalized),
                "size_text_raw": _coerce_text(size_text_raw),
                "price_raw": _coerce_text(price_raw),
                "currency": _coerce_text(currency),
                "barcode": barcode_value,
                "backend_id": extra_backend_id,
                "backend_parent_id": extra_backend_parent_id,
                "availability": _coerce_text(availability),
                "swatch_image_url": _coerce_text(swatch_url),
                "hero_image_url": _coerce_text(hero_url),
                "variant_description": _coerce_text(variant_description),
            }
        )

    schema_overrides = {
        "retailer": pl.Utf8,
        "parent_product_id": pl.Utf8,
        "variant_id": pl.Utf8,
        "variant_key": pl.Utf8,
        "shade_name_raw": pl.Utf8,
        "shade_name_normalized": pl.Utf8,
        "size_text_raw": pl.Utf8,
        "price_raw": pl.Utf8,
        "currency": pl.Utf8,
        "barcode": pl.Utf8,
        "backend_id": pl.Utf8,
        "backend_parent_id": pl.Utf8,
        "availability": pl.Utf8,
        "swatch_image_url": pl.Utf8,
        "hero_image_url": pl.Utf8,
        "variant_description": pl.Utf8,
    }
    variants_df = pl.DataFrame(records, schema_overrides=schema_overrides)
    if variants_df.is_empty():
        return variants_df, _rows_to_pdp_source_segments_dataframe(segment_rows)

    augmented = variants_df.join(
        lookup,
        on=["retailer", "parent_product_id"],
        how="left",
    )
    segment_df = _rows_to_pdp_source_segments_dataframe(segment_rows)
    if not segment_df.is_empty():
        segment_df = segment_df.join(
            augmented.select(
                ["retailer", "parent_product_id", "variant_id", "category_key"]
            ).unique(),
            on=["retailer", "parent_product_id", "variant_id"],
            how="inner",
        )
        if "category_key_right" in segment_df.columns:
            segment_df = segment_df.drop("category_key").rename(
                {"category_key_right": "category_key"}
            )
        elif "category_key" not in segment_df.columns:
            segment_df = segment_df.with_columns(pl.lit("").alias("category_key"))
    return augmented, segment_df


def _build_attribute_map(
    taxonomy: Mapping[str, object],
    categories: Iterable[str],
    *,
    row_scope: str | None = None,
) -> dict[str, list[str]]:
    keys = {_normalize_key(cat) for cat in categories if cat}
    if not keys:
        return {}

    attr_map: dict[str, list[str]] = {}
    for item in taxonomy.get("categories", []) or []:
        if not isinstance(item, Mapping):
            continue
        cid = str(item.get("id", "")).strip()
        clabel = str(item.get("label", "")).strip()
        normalized_id = _normalize_key(cid)
        normalized_label = _normalize_key(clabel)
        if normalized_id not in keys and normalized_label not in keys:
            continue
        attr_ids: list[str] = []
        for attr in item.get("attributes", []) or []:
            if not isinstance(attr, Mapping):
                continue
            attr_id = str(attr.get("id", "")).strip()
            if not _attribute_matches_row_scope(attr, row_scope=row_scope):
                continue
            if not _attribute_enabled_for_category(
                normalized_id or normalized_label,
                attr_id,
                row_scope=row_scope,
            ):
                continue
            if attr_id:
                attr_ids.append(attr_id)
        if attr_ids:
            key = normalized_id or normalized_label
            attr_map[key] = attr_ids
    return attr_map


PARENT_BASE_COLUMNS = {
    "retailer",
    "parent_product_id",
    "pdp_url",
    "brand",
    "product_name",
    "hero_image_url",
    "category_key",
    "category_id",
    "category_label",
    "category_path",
    "raw_category_path",
    "description",
}

VARIANT_BASE_COLUMNS = PARENT_BASE_COLUMNS | {
    "variant_id",
    "shade_name_raw",
    "shade_name_normalized",
    "size_text_raw",
    "price_raw",
    "currency",
    "barcode",
    "availability",
    "swatch_image_url",
    "hero_image_url",
    "variant_description",
}


_PARENT_HERO_CACHE: dict[str, str | None] = {}
_PDP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
_HERO_META_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        re.IGNORECASE,
    ),
    re.compile(
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        re.IGNORECASE,
    ),
)
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _fetch_parent_hero_url(pdp_url: str | None) -> str | None:
    if not pdp_url:
        return None
    cached = _PARENT_HERO_CACHE.get(pdp_url)
    if cached is not None:
        return cached
    try:
        response = requests.get(pdp_url, headers=_PDP_HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        LOGGER.debug("Failed fetching hero for %s: %s", pdp_url, exc)
        _PARENT_HERO_CACHE[pdp_url] = None
        return None
    text = response.text
    for candidate in _images_from_ld_json(text, pdp_url):
        candidate = _normalize_candidate_url(candidate, pdp_url)
        if _is_valid_image_url(candidate):
            _PARENT_HERO_CACHE[pdp_url] = candidate
            return candidate
    for pattern in _HERO_META_PATTERNS:
        match = pattern.search(text)
        if match:
            url = _normalize_candidate_url(match.group(1).strip(), pdp_url)
            if _is_valid_image_url(url):
                _PARENT_HERO_CACHE[pdp_url] = url
                return url
    parsed = urlparse(pdp_url)
    domain = parsed.netloc.lower()
    if "kikocosmetics.com" in domain:
        kiko_url = _extract_kiko_primary_image(text, pdp_url)
        if kiko_url:
            _PARENT_HERO_CACHE[pdp_url] = kiko_url
            return kiko_url
    generic_matches = re.findall(
        r"https://[^'\" ]+?\.(?:jpg|jpeg|png|webp|avif)", text, flags=re.IGNORECASE
    )
    for candidate in generic_matches:
        candidate = candidate.strip()
        if _is_valid_image_url(candidate):
            _PARENT_HERO_CACHE[pdp_url] = candidate
            return candidate
    _PARENT_HERO_CACHE[pdp_url] = None
    return None


def _normalize_candidate_url(url: str, base_url: str) -> str:
    if not url:
        return url
    if url.startswith("//"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}:{url}"
    if url.startswith("/"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{url}"
    return url


def _is_valid_image_url(url: str | None) -> bool:
    if not url:
        return False
    lower = url.lower()
    if not lower.startswith(("http://", "https://")):
        return False
    if "wlwmanifest" in lower or lower.endswith(".xml"):
        return False
    if "virtualtryon" in lower or "foundationfinder" in lower:
        return False
    if "/blob/" in lower:
        return True
    if lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".avif")):
        return True
    parsed = urlparse(url)
    return parsed.path.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".avif"))


def _images_from_ld_json(text: str, base_url: str) -> list[str]:
    matches = re.findall(
        r'<script[^>]*type=["\u201c\u201d\'"]application/ld\+json["\u201c\u201d\'"][^>]*>(.*?)</script>',
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    urls: list[str] = []
    for block in matches:
        block = block.strip()
        if not block:
            continue
        try:
            data = json.loads(block)
        except Exception:
            continue
        candidates: list[Mapping[str, object]] = []
        if isinstance(data, dict):
            candidates.append(data)
        elif isinstance(data, list):
            candidates.extend(item for item in data if isinstance(item, dict))
        for candidate in candidates:
            if candidate.get("@type") in ("Product", "ImageObject"):
                image = candidate.get("image")
                if isinstance(image, str):
                    urls.append(image)
                elif isinstance(image, list):
                    for item in image:
                        if isinstance(item, str):
                            urls.append(item)
    return urls


def _extract_kiko_primary_image(html: str, base_url: str) -> str | None:
    match = _NEXT_DATA_RE.search(html)
    if not match:
        return None
    payload_raw = match.group(1)
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        return None
    props = payload.get("props")
    if isinstance(props, Mapping):
        page_props = props.get("pageProps")
    else:
        page_props = None
    if not isinstance(page_props, Mapping):
        return None

    def _candidate_nodes() -> Iterable[Mapping[str, object]]:
        root = page_props.get("root")
        if isinstance(root, Mapping):
            yield root
        children = page_props.get("children")
        if isinstance(children, Sequence):
            for child in children:
                if isinstance(child, Mapping):
                    yield child

    for node in _candidate_nodes():
        url = _kiko_media_url_from_node(node)
        if url:
            return _normalize_candidate_url(url, base_url)
    return None


def _kiko_media_url_from_node(node: Mapping[str, object]) -> str | None:
    media = node.get("product_media")
    if not isinstance(media, Mapping):
        return None
    primary = media.get("primary_image")
    if isinstance(primary, Mapping):
        primary_url = _extract_url_from_mapping(primary)
        if primary_url:
            return primary_url
    for key in ("media", "gallery"):
        collection = media.get(key)
        url = _extract_url_from_collection(collection)
        if url:
            return url
    return None


def _extract_url_from_mapping(value: Mapping[str, object]) -> str | None:
    url = value.get("url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    return None


def _extract_url_from_collection(value: object) -> str | None:
    if isinstance(value, Mapping):
        direct = _extract_url_from_mapping(value)
        if direct:
            return direct
        for item in value.values():
            nested = _extract_url_from_collection(item)
            if nested:
                return nested
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            nested = _extract_url_from_collection(item)
            if nested:
                return nested
    elif isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _populate_parent_hero_urls(
    parent_df: pl.DataFrame, variants_df: pl.DataFrame
) -> pl.DataFrame:
    if parent_df.is_empty():
        return parent_df

    hero_lookup: dict[tuple[str, str], str] = {}
    if not variants_df.is_empty() and "hero_image_url" in variants_df.columns:
        variant_heroes = (
            variants_df.select(["retailer", "parent_product_id", "hero_image_url"])
            .drop_nulls()
            .filter(pl.col("hero_image_url") != "")
        )
        for row in variant_heroes.iter_rows(named=True):
            key = (row["retailer"], row["parent_product_id"])
            if key not in hero_lookup:
                hero_lookup[key] = str(row["hero_image_url"])

    missing_keys: list[tuple[str, str]] = []
    pdp_urls: dict[tuple[str, str], str] = {}
    for row in parent_df.iter_rows(named=True):
        key = (row["retailer"], row["parent_product_id"])
        if hero_lookup.get(key):
            continue
        pdp_url = str(row.get("pdp_url") or "").strip()
        if not pdp_url:
            continue
        missing_keys.append(key)
        pdp_urls[key] = pdp_url

    for key in missing_keys:
        url = pdp_urls.get(key)
        hero = _fetch_parent_hero_url(url)
        if hero:
            hero_lookup[key] = hero

    heroes = [
        hero_lookup.get((row["retailer"], row["parent_product_id"]))
        for row in parent_df.iter_rows(named=True)
    ]
    return parent_df.with_columns(pl.Series("hero_image_url", heroes))


def _ensure_columns(df: pl.DataFrame, columns: Iterable[str]) -> pl.DataFrame:
    for col in columns:
        if col not in df.columns:
            df = df.with_columns(pl.lit(None).alias(col))
    return df


def _iter_attribute_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, pl.Series):
        return _iter_attribute_values(value.to_list())
    if isinstance(value, (list, tuple, set)):
        out: list[Any] = []
        for item in value:
            out.extend(_iter_attribute_values(item))
        return out
    return [value]


def _join_attribute_values(value: Any) -> str | None:
    values: list[str] = []
    seen: set[str] = set()
    for item in _iter_attribute_values(value):
        text = _normalize_stage_value(item)
        if text is None or text.casefold() in _ATTRIBUTE_PLACEHOLDER_CANONICAL:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        values.append(text)
    return ATTRIBUTE_LIST_SEPARATOR.join(values) if values else None


def _clean_attribute_columns(df: pl.DataFrame, columns: Iterable[str]) -> pl.DataFrame:
    if df.is_empty():
        return df
    _columns, schema = get_schema_and_column_names(df)
    attribute_columns = set(columns)
    list_columns = [
        column
        for column, dtype in schema.items()
        if column in attribute_columns
        and getattr(dtype, "base_type", lambda: None)() == pl.List
    ]
    if not list_columns:
        return df
    return df.with_columns(
        [
            pl.col(column)
            .map_elements(_join_attribute_values, return_dtype=pl.Utf8)
            .alias(column)
            for column in list_columns
        ]
    )


def _normalize_cache_merge_key_columns(
    df: pl.DataFrame, key_cols: Sequence[str]
) -> pl.DataFrame:
    if df.is_empty():
        return df
    updates = [
        pl.coalesce(pl.col(col).cast(pl.Utf8), pl.lit("")).alias(col)
        for col in key_cols
        if col in df.columns
    ]
    return df.with_columns(updates) if updates else df


def _finalize_attribute_views(
    parent_df: pl.DataFrame,
    variant_df: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, list[str]]:
    parent_work = _harmonize_parent_variant_attributes(parent_df, variant_df)
    parent_work = _populate_parent_hero_urls(parent_work, variant_df)
    parent_complete = parent_work.clone()

    parent_attr_cols = [c for c in parent_work.columns if c not in PARENT_BASE_COLUMNS]
    variant_attr_cols = [c for c in variant_df.columns if c not in VARIANT_BASE_COLUMNS]
    attr_cols = sorted({*parent_attr_cols, *variant_attr_cols})

    parent_work = _ensure_columns(parent_work, attr_cols)
    variant_work = _ensure_columns(variant_df, attr_cols)

    parent_work = _clean_attribute_columns(parent_work, attr_cols)
    variant_work = _clean_attribute_columns(variant_work, attr_cols)

    if attr_cols:
        parent_attr_lookup = parent_work.select(
            ["retailer", "parent_product_id", "category_key", *attr_cols]
        )
        variant_work = variant_work.join(
            parent_attr_lookup,
            on=["retailer", "parent_product_id", "category_key"],
            how="left",
            suffix="_parent",
        )
        placeholders = list(_ATTRIBUTE_PLACEHOLDER_CANONICAL) + [""]
        for attr in attr_cols:
            parent_col = f"{attr}_parent"
            if parent_col in variant_work.columns:
                variant_work = variant_work.with_columns(
                    pl.when(
                        pl.col(attr).is_null()
                        | pl.col(attr)
                        .cast(pl.Utf8)
                        .str.to_lowercase()
                        .is_in(placeholders)
                    )
                    .then(pl.col(parent_col))
                    .otherwise(pl.col(attr))
                    .alias(attr)
                ).drop(parent_col)

    variant_final = variant_work.with_columns(
        pl.lit("variant").alias("record_type"),
        pl.col("parent_product_id").alias("product"),
        pl.col("variant_id").alias("variant"),
    )

    # Keep parent rows even when variants exist; the parent view drives the UI selection.
    parent_filtered = parent_work

    parent_final = parent_filtered.with_columns(
        pl.lit("parent").alias("record_type"),
        pl.col("parent_product_id").alias("product"),
        pl.lit("").alias("variant"),
    )

    combined = pl.concat([parent_final, variant_final], how="diagonal_relaxed")

    ordered_columns = (
        ["record_type", "retailer", "product", "variant", "product_name", "brand"]
        + [
            col
            for col in (
                "shade_name_raw",
                "shade_name_normalized",
                "size_text_raw",
                "price_raw",
                "currency",
                "barcode",
                "availability",
                "swatch_image_url",
                "hero_image_url",
            )
            if col in combined.columns
        ]
        + ["category_key", "category_id", "category_label", "description"]
        + attr_cols
    )

    combined = combined.select(
        [col for col in ordered_columns if col in combined.columns]
    )

    return parent_filtered, variant_work, combined, parent_complete, attr_cols


def _load_attribute_value_frame(
    pdp_store_path: Path | str,
    *,
    row_type: str,
    retailers: Sequence[str] | None = None,
) -> pl.DataFrame:
    path = Path(pdp_store_path)
    if not pdp_database_exists(path):
        return pl.DataFrame()
    stage_tables = [
        ("deterministic_explicit", "pdp_attributes_deterministic_explicit"),
        ("deterministic", "pdp_attributes_deterministic"),
        ("llm", "pdp_attributes_llm"),
    ]
    normalized_retailers: list[str] | None = None
    if retailers:
        normalized = [str(ret).strip() for ret in retailers if str(ret).strip()]
        normalized_retailers = normalized or None

    entity_map: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    stage_counts: Counter[str] = Counter()

    def _add_value_row(
        *,
        source: str,
        retailer_val: object,
        parent_id: object,
        variant_id: object,
        category_key: object,
        attr_id: object,
        value: object,
        replace: bool = True,
    ) -> None:
        source_key = str(source or "").strip()
        retailer_key = str(retailer_val or "").strip()
        parent_key = str(parent_id or "").strip()
        variant_key = str(variant_id or "").strip() if row_type == "variant" else ""
        category_text = str(category_key or "").strip()
        category_text = _canonicalize_category_key_value(category_text) or ""
        attribute_key = str(attr_id or "").strip()
        if not source_key or not retailer_key or not parent_key or not attribute_key:
            return
        base_key = (
            retailer_key,
            parent_key,
            variant_key if row_type == "variant" else "",
            category_text,
        )
        entity = entity_map.setdefault(
            base_key,
            {
                "meta": {
                    "retailer": retailer_key,
                    "parent_product_id": parent_key,
                    "category_key": category_text,
                }
                | ({"variant_id": variant_key} if row_type == "variant" else {}),
                "values": {},
            },
        )
        normalized_value = _normalize_stage_value(value)
        values_by_source = entity["values"].setdefault(attribute_key, {})
        if replace or source_key not in values_by_source:
            values_by_source[source_key] = normalized_value
        stage_counts[source_key] += 1

    with connect_pdp_database(path) as conn:
        conditions = ["row_type = ?"]
        params: list[str] = [row_type]
        if normalized_retailers:
            placeholders = ",".join("?" for _ in normalized_retailers)
            conditions.append(f"retailer IN ({placeholders})")
            params.extend(normalized_retailers)
        where_clause = " AND ".join(conditions)
        try:
            canonical_rows = conn.execute(
                """
                SELECT
                    source,
                    retailer,
                    parent_product_id,
                    variant_id,
                    category_key,
                    attribute_id,
                    value
                FROM pdp_attribute_values
                WHERE """ + where_clause,
                params,
            ).fetchall()
        except Exception:
            canonical_rows = []
        for (
            source,
            retailer_val,
            parent_id,
            variant_id,
            category_key,
            attr_id,
            value,
        ) in canonical_rows:
            _add_value_row(
                source=str(source or ""),
                retailer_val=retailer_val,
                parent_id=parent_id,
                variant_id=variant_id,
                category_key=category_key,
                attr_id=attr_id,
                value=value,
            )

        for stage, table in stage_tables:
            conditions = ["row_type = ?"]
            params: list[str] = [row_type]
            if normalized_retailers:
                placeholders = ",".join("?" for _ in normalized_retailers)
                conditions.append(f"retailer IN ({placeholders})")
                params.extend(normalized_retailers)
            where_clause = " AND ".join(conditions)
            query = (
                f"SELECT retailer, row_type, parent_product_id, variant_id, category_key, attribute_id, value "
                f"FROM {table} WHERE {where_clause}"
            )
            try:
                rows = conn.execute(query, params).fetchall()
            except Exception:
                rows = []

            if not rows:
                continue

            for (
                retailer_val,
                _row_type_val,
                parent_id,
                variant_id,
                category_key,
                attr_id,
                value,
            ) in rows:
                _add_value_row(
                    source=stage,
                    retailer_val=retailer_val,
                    parent_id=parent_id,
                    variant_id=variant_id,
                    category_key=category_key,
                    attr_id=attr_id,
                    value=value,
                    replace=False,
                )

    if not entity_map:
        if LOGGER.isEnabledFor(logging.INFO):
            LOGGER.info(
                "PDP database attribute rows for %s: sources=%s merged_entities=0",
                row_type,
                dict(sorted(stage_counts.items())),
            )
        return pl.DataFrame()

    rows_data: list[dict[str, Any]] = []
    for payload in entity_map.values():
        meta = dict(payload["meta"])
        attribute_values: dict[str, dict[str, str | None]] = payload["values"]
        attribute_ids = sorted(attribute_values.keys())
        for attr_id in attribute_ids:
            chosen, effective_source = _choose_canonical_attribute_value_and_source(
                attribute_values[attr_id]
            )
            if chosen is not None:
                meta[attr_id] = chosen
            if effective_source is not None:
                # This is mechanical provenance, not semantic source selection:
                # it records the winner already selected by the established
                # precedence contract so downstream correction cannot target a
                # value that a rebuilt package would ignore.
                meta[f"{attr_id}_effective_source"] = effective_source
        rows_data.append(meta)

    if LOGGER.isEnabledFor(logging.INFO):
        LOGGER.info(
            "PDP database attribute rows for %s: sources=%s merged_entities=%s",
            row_type,
            dict(sorted(stage_counts.items())),
            len(entity_map),
        )

    try:
        return pl.DataFrame(rows_data, infer_schema_length=None)
    except Exception:  # pragma: no cover - defensive
        LOGGER.exception(
            "Failed to normalize attribute value frame; retrying with relaxed schema."
        )
        return pl.DataFrame(rows_data, infer_schema_length=len(rows_data))


def _merge_attribute_values(
    base_df: pl.DataFrame,
    values_df: pl.DataFrame,
    *,
    left_on: Sequence[str],
    right_on: Sequence[str],
) -> pl.DataFrame:
    if base_df.is_empty() or values_df.is_empty():
        return base_df

    def _flatten_lists(df: pl.DataFrame) -> pl.DataFrame:
        if df.is_empty():
            return df

        def _flatten(val: object) -> str | object:
            if isinstance(val, list):
                if all(isinstance(item, str) for item in val):
                    # For list-of-strings columns (e.g., category_path), join with ' > '.
                    joined = " > ".join(
                        item.strip() for item in val if str(item).strip()
                    )
                    return joined or None
                # For other list types, serialize to JSON to keep structure without nesting.
                return json.dumps(val, ensure_ascii=False)
            return val

        exprs = []
        for col, dtype in df.schema.items():
            try:
                is_list = dtype.is_list()
            except AttributeError:
                is_list = False
            if not is_list:
                continue
            exprs.append(
                pl.when(pl.col(col).is_null())
                .then(None)
                .otherwise(pl.col(col).map_elements(_flatten, return_dtype=pl.Utf8))
                .alias(col)
            )
        return df.with_columns(exprs) if exprs else df

    base_df = _flatten_lists(base_df)
    values_df = _flatten_lists(values_df)

    suffix = "__persisted"
    right_keys = set(right_on)
    value_columns = [col for col in values_df.columns if col not in right_keys]
    if not value_columns:
        return base_df

    merged = base_df.join(
        values_df,
        how="left",
        left_on=left_on,
        right_on=right_on,
        suffix=suffix,
    )

    updates: list[pl.Expr] = []
    for column in value_columns:
        persisted_col = f"{column}{suffix}"
        if persisted_col not in merged.columns:
            continue
        if column in merged.columns:
            # Coerce both sides to Utf8 before coalescing to avoid dtype mismatches
            updates.append(
                pl.coalesce(
                    pl.col(persisted_col).cast(pl.Utf8),
                    pl.col(column).cast(pl.Utf8),
                ).alias(column)
            )
        else:
            updates.append(pl.col(persisted_col).alias(column))

    if updates:
        merged = merged.with_columns(updates)

    drop_cols = [col for col in merged.columns if col.endswith(suffix)]
    if drop_cols:
        merged = merged.drop(drop_cols)

    return merged


def _load_attribute_cache_from_store(
    pdp_store_path: Path | str,
) -> (
    tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, dict[str, Any]] | None
):
    try:
        store = PDPStore(pdp_store_path)
        entries = store.read_attribute_cache_entries()
    except Exception:  # pragma: no cover - defensive
        LOGGER.exception("Unable to read attribute cache from the PDP database")
        return None

    if not entries:
        return None

    def _fetch_frame(name: str) -> pl.DataFrame:
        payload = entries.get(name)
        if not payload:
            return pl.DataFrame()
        blob, _generated = payload
        try:
            return _deserialize_frame(blob)
        except Exception:  # pragma: no cover - defensive
            LOGGER.exception(
                "Failed to deserialize frame '%s' from PDP database cache", name
            )
            return pl.DataFrame()

    parent_df = _fetch_frame("parent_filtered")
    variant_df = _fetch_frame("variant_result")
    combined_df = _fetch_frame("combined")
    parents_all_df = _fetch_frame("parents_all")

    metadata_blob = entries.get("metadata")
    metadata: dict[str, Any] = {}
    if metadata_blob:
        try:
            metadata = _deserialize_metadata(metadata_blob[0])
        except Exception:  # pragma: no cover - defensive
            LOGGER.exception("Failed to deserialize attribute cache metadata")
            metadata = {}

    if parent_df.is_empty() and combined_df.is_empty() and parents_all_df.is_empty():
        return None

    return parent_df, variant_df, combined_df, parents_all_df, metadata


def _list_cached_retailers(pdp_store_path: Path | str) -> list[str]:
    root = _attribute_cache_dir(pdp_store_path)
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def _load_attribute_cache_from_files(
    pdp_store_path: Path | str,
    retailers: Sequence[str] | None = None,
) -> (
    tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, dict[str, Any]] | None
):
    available = _list_cached_retailers(pdp_store_path)
    if retailers:
        targets = [r for r in retailers if r in available]
    else:
        targets = available

    if not targets:
        return None

    parent_frames: list[pl.DataFrame] = []
    variant_frames: list[pl.DataFrame] = []
    combined_frames: list[pl.DataFrame] = []
    parents_all_frames: list[pl.DataFrame] = []
    unmatched_categories: set[str] = set()
    unmatched_examples: dict[str, set[str]] = {}
    for retailer in targets:
        paths = _attribute_cache_paths(pdp_store_path, retailer)
        required = [
            paths["parent"],
            paths["combined"],
            paths["parents_all"],
            paths["metadata"],
        ]
        if not all(path.exists() for path in required):
            continue
        parent_frames.append(pl.read_parquet(paths["parent"]))
        if paths["variant"].exists():
            variant_frames.append(pl.read_parquet(paths["variant"]))
        combined_frames.append(pl.read_parquet(paths["combined"]))
        parents_all_frames.append(pl.read_parquet(paths["parents_all"]))
        try:
            with paths["metadata"].open("r", encoding="utf-8") as fh:
                meta = json.load(fh)
            unmatched_categories.update(meta.get("unmatched_categories", []) or [])
            for key, values in (meta.get("unmatched_examples", {}) or {}).items():
                unmatched_examples.setdefault(str(key), set()).update(values or [])
        except Exception:
            continue

    def _concat(frames: list[pl.DataFrame]) -> pl.DataFrame:
        if not frames:
            return pl.DataFrame()
        if len(frames) == 1:
            return frames[0]
        return pl.concat(frames, how="diagonal_relaxed")

    parent_df = _concat(parent_frames)
    if parent_df.is_empty():
        return None
    variant_df = _concat(variant_frames)
    combined_df = _concat(combined_frames)
    parents_all_df = _concat(parents_all_frames)
    metadata: dict[str, Any] = {
        "unmatched_categories": sorted(unmatched_categories),
        "unmatched_examples": {
            key: sorted(vals) for key, vals in unmatched_examples.items()
        },
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    return parent_df, variant_df, combined_df, parents_all_df, metadata


def _first_category_key(value: object) -> str | None:
    if isinstance(value, (list, tuple)) and value:
        return _normalize_key(str(value[0]))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list) and parsed:
                    return _normalize_key(str(parsed[0]))
            except Exception:
                pass
        return _normalize_key(text)
    return None


def _ensure_category_key_column(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df
    has_category_path = "category_path" in df.columns
    path_expr = (
        pl.col("category_path").map_elements(_first_category_key, return_dtype=pl.Utf8)
        if has_category_path
        else None
    )
    if "category_key" in df.columns:
        if path_expr is None:
            return df
        return df.with_columns(
            pl.when(pl.col("category_key").is_null() | (pl.col("category_key") == ""))
            .then(path_expr)
            .otherwise(pl.col("category_key"))
            .alias("category_key")
        )
    if path_expr is not None:
        return df.with_columns(path_expr.alias("category_key"))
    return df.with_columns(pl.lit(None).alias("category_key"))


def load_persisted_pdp_attributes(
    pdp_store_path: Path | str,
    retailers: Sequence[str] | None = None,
    *,
    categories: Sequence[str] | None = None,
) -> tuple[
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
    set[str],
    pl.DataFrame,
    dict[str, set[str]],
    dict[str, Any],
]:
    # Ensure the database schema (including stage tables) is available even when
    # this code runs before a fresh compute pass.
    PDPStore(pdp_store_path)
    cache_result = _load_attribute_cache_from_store(pdp_store_path)
    if cache_result is None:
        cache_result = _load_attribute_cache_from_files(pdp_store_path, retailers)

    if cache_result is None:
        paths = _attribute_cache_paths(pdp_store_path)
        parent_path = paths["parent"]
        variant_path = paths["variant"]
        combined_path = paths["combined"]
        parents_all_path = paths["parents_all"]
        metadata_path = paths["metadata"]

        required = [parent_path, combined_path, parents_all_path, metadata_path]
        if not all(path.exists() for path in required):
            raise FileNotFoundError("Persisted PDP attribute cache not found.")

        parent_df = pl.read_parquet(parent_path)
        variant_df = (
            pl.read_parquet(variant_path) if variant_path.exists() else pl.DataFrame()
        )
        combined_df = pl.read_parquet(combined_path)
        parents_all_df = pl.read_parquet(parents_all_path)

        with metadata_path.open("r", encoding="utf-8") as fh:
            metadata = json.load(fh)
    else:
        parent_df, variant_df, combined_df, parents_all_df, metadata = cache_result
    unmatched_categories = set(metadata.get("unmatched_categories", []))
    unmatched_examples_raw = metadata.get("unmatched_examples", {})
    unmatched_examples: dict[str, set[str]] = {
        str(key): set(value or []) for key, value in unmatched_examples_raw.items()
    }

    parent_df = _ensure_category_key_column(parent_df)
    variant_df = _ensure_category_key_column(variant_df)
    combined_df = _ensure_category_key_column(combined_df)
    parents_all_df = _ensure_category_key_column(parents_all_df)
    parent_df = _canonicalize_category_key_columns(parent_df)
    variant_df = _canonicalize_category_key_columns(variant_df)
    combined_df = _canonicalize_category_key_columns(combined_df)
    parents_all_df = _canonicalize_category_key_columns(parents_all_df)

    parent_values = _load_attribute_value_frame(
        pdp_store_path,
        row_type="parent",
        retailers=retailers,
    )
    variant_values = _load_attribute_value_frame(
        pdp_store_path,
        row_type="variant",
        retailers=retailers,
    )
    parent_values = _canonicalize_category_key_columns(parent_values)
    variant_values = _canonicalize_category_key_columns(variant_values)

    if LOGGER.isEnabledFor(logging.INFO):
        LOGGER.info(
            "Merged stage attribute frames: parent_entities=%s variant_entities=%s",
            parent_values.height,
            variant_values.height,
        )

    parent_df = _merge_attribute_values(
        parent_df,
        parent_values,
        left_on=["retailer", "parent_product_id", "category_key"],
        right_on=["retailer", "parent_product_id", "category_key"],
    )
    parents_all_df = _merge_attribute_values(
        parents_all_df,
        parent_values,
        left_on=["retailer", "parent_product_id", "category_key"],
        right_on=["retailer", "parent_product_id", "category_key"],
    )
    variant_df = _merge_attribute_values(
        variant_df,
        variant_values,
        left_on=["retailer", "parent_product_id", "variant_id", "category_key"],
        right_on=["retailer", "parent_product_id", "variant_id", "category_key"],
    )
    combined_df = _merge_attribute_values(
        combined_df,
        parent_values,
        left_on=["retailer", "product", "category_key"],
        right_on=["retailer", "parent_product_id", "category_key"],
    )
    combined_df = _merge_attribute_values(
        combined_df,
        variant_values,
        left_on=["retailer", "product", "variant", "category_key"],
        right_on=["retailer", "parent_product_id", "variant_id", "category_key"],
    )

    if LOGGER.isEnabledFor(logging.INFO):
        LOGGER.info(
            "Applied stage overlays to cached frames: parent_rows=%s variant_rows=%s combined_rows=%s parents_all_rows=%s",
            parent_df.height,
            variant_df.height,
            combined_df.height,
            parents_all_df.height,
        )

    if retailers:
        normalized_retailers = [
            str(ret).strip() for ret in retailers if str(ret).strip()
        ]
        if normalized_retailers:
            filt = pl.col("retailer").is_in(normalized_retailers)
            parent_df = parent_df.filter(filt)
            variant_df = (
                variant_df.filter(filt) if not variant_df.is_empty() else variant_df
            )
            combined_df = combined_df.filter(filt)
            parents_all_df = parents_all_df.filter(filt)

    normalized_categories: set[str] | None = None
    if categories:
        normalized_categories = _expanded_requested_category_keys(categories)
        if normalized_categories:
            category_filter = pl.col("category_key").is_in(normalized_categories)
            parent_df = parent_df.filter(category_filter)
            variant_df = (
                variant_df.filter(category_filter)
                if not variant_df.is_empty()
                else variant_df
            )
            combined_df = combined_df.filter(category_filter)
            parents_all_df = parents_all_df.filter(category_filter)
            unmatched_categories = {
                cat for cat in unmatched_categories if cat in normalized_categories
            }
            unmatched_examples = {
                cat: values
                for cat, values in unmatched_examples.items()
                if cat in unmatched_categories
            }

    # Drop rows without a usable category key so the UI doesn't show null categories.
    def _drop_null_categories(df: pl.DataFrame) -> pl.DataFrame:
        if df.is_empty() or "category_key" not in df.columns:
            return df
        return df.filter(
            pl.col("category_key").is_not_null() & (pl.col("category_key") != "")
        )

    parent_df = _drop_null_categories(parent_df)
    variant_df = _drop_null_categories(variant_df)
    combined_df = _drop_null_categories(combined_df)
    parents_all_df = _drop_null_categories(parents_all_df)

    return (
        parent_df,
        variant_df,
        combined_df,
        unmatched_categories,
        parents_all_df,
        unmatched_examples,
        metadata,
    )


def load_pdp_attribute_mapping_inputs(
    pdp_store_path: Path | str,
    retailers: Sequence[str] | None = None,
    categories: Sequence[str] | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Load PDP attribute mapper inputs directly from the PDP database."""

    taxonomy = get_runtime_attribute_taxonomy()
    category_alias_map = get_category_alias_map()
    parents_df, _, _, _ = _load_parent_products(
        pdp_store_path,
        taxonomy,
        retailers,
        category_aliases=category_alias_map,
    )
    if parents_df.is_empty():
        return parents_df, pl.DataFrame()
    normalized_categories = (
        _expanded_requested_category_keys(categories) if categories else set()
    )
    if normalized_categories:
        parents_df = parents_df.filter(
            pl.col("category_key").is_in(normalized_categories)
        )
        if parents_df.is_empty():
            return parents_df, pl.DataFrame()

    variants_df, _ = _load_variants(pdp_store_path, parents_df)
    parents_df = _canonicalize_category_key_columns(
        _ensure_category_key_column(parents_df)
    )
    variants_df = _canonicalize_category_key_columns(
        _ensure_category_key_column(variants_df)
    )
    parent_values = _canonicalize_category_key_columns(
        _load_attribute_value_frame(
            pdp_store_path,
            row_type="parent",
            retailers=retailers,
        )
    )
    variant_values = _canonicalize_category_key_columns(
        _load_attribute_value_frame(
            pdp_store_path,
            row_type="variant",
            retailers=retailers,
        )
    )

    parents_df = _merge_attribute_values(
        parents_df,
        parent_values,
        left_on=["retailer", "parent_product_id", "category_key"],
        right_on=["retailer", "parent_product_id", "category_key"],
    )
    variants_df = _merge_attribute_values(
        variants_df,
        variant_values,
        left_on=["retailer", "parent_product_id", "variant_id", "category_key"],
        right_on=["retailer", "parent_product_id", "variant_id", "category_key"],
    )
    return parents_df, variants_df


def _merge_fill_only_classifications(
    preferred_df: pl.DataFrame,
    fallback_df: pl.DataFrame,
    *,
    key_columns: Sequence[str],
) -> pl.DataFrame:
    """Merge two classification frames while preserving non-placeholder preferred values."""
    if preferred_df.is_empty():
        return fallback_df
    if fallback_df.is_empty():
        return preferred_df
    if any(column not in preferred_df.columns for column in key_columns):
        return fallback_df
    if any(column not in fallback_df.columns for column in key_columns):
        return preferred_df

    preferred_attrs = [
        column for column in preferred_df.columns if column not in set(key_columns)
    ]
    fallback_attrs = [
        column for column in fallback_df.columns if column not in set(key_columns)
    ]
    attr_columns = preferred_attrs + [
        column for column in fallback_attrs if column not in preferred_attrs
    ]
    if not attr_columns:
        return preferred_df

    preferred_rows = preferred_df.to_dicts()
    fallback_rows = fallback_df.to_dicts()

    def _row_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
        return tuple(row.get(column) for column in key_columns)

    preferred_index: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in preferred_rows:
        key = _row_key(row)
        if key not in preferred_index:
            preferred_index[key] = dict(row)

    fallback_index: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in fallback_rows:
        key = _row_key(row)
        if key not in fallback_index:
            fallback_index[key] = dict(row)

    ordered_keys: list[tuple[Any, ...]] = []
    for row in preferred_rows:
        key = _row_key(row)
        if key not in ordered_keys:
            ordered_keys.append(key)
    for row in fallback_rows:
        key = _row_key(row)
        if key not in ordered_keys:
            ordered_keys.append(key)

    merged_rows: list[dict[str, Any]] = []
    for key in ordered_keys:
        preferred_row = preferred_index.get(key)
        fallback_row = fallback_index.get(key)
        if preferred_row is None and fallback_row is None:
            continue
        output: dict[str, Any] = {}
        for idx, column in enumerate(key_columns):
            output[column] = key[idx]
        for attr in attr_columns:
            preferred_has = preferred_row is not None and attr in preferred_row
            fallback_has = fallback_row is not None and attr in fallback_row
            preferred_val = preferred_row.get(attr) if preferred_row else None
            fallback_val = fallback_row.get(attr) if fallback_row else None
            if preferred_has:
                if (
                    _is_placeholder_value(preferred_val)
                    and fallback_has
                    and not _is_placeholder_value(fallback_val)
                ):
                    output[attr] = fallback_val
                else:
                    output[attr] = preferred_val
            elif fallback_has:
                output[attr] = fallback_val
        merged_rows.append(output)

    if not merged_rows:
        return pl.DataFrame()
    return pl.DataFrame(merged_rows, strict=False, infer_schema_length=None)


def _join_classification_overrides(
    base_df: pl.DataFrame,
    classification_df: pl.DataFrame,
    *,
    key_columns: Sequence[str],
) -> pl.DataFrame:
    """Join classification results while replacing stale attribute columns.

    ``base_df`` can already carry persisted attribute columns from older cache
    blobs. When the same attribute is reclassified in ``classification_df``,
    Polars would normally keep the existing column and suffix the fresh one with
    ``_right``. For deterministic refreshes we want the new classification to
    win, so drop overlapping non-key columns from ``base_df`` before joining.
    """

    if base_df.is_empty() or classification_df.is_empty():
        return base_df
    overlap_columns = [
        column
        for column in classification_df.columns
        if column not in set(key_columns) and column in base_df.columns
    ]
    join_base = base_df.drop(overlap_columns) if overlap_columns else base_df
    return join_base.join(
        classification_df,
        on=list(key_columns),
        how="left",
    )


def _collect_explicit_attribute_locks(
    explicit_df: pl.DataFrame,
    *,
    key_columns: Sequence[str],
    category_column: str,
    attr_map: Mapping[str, Sequence[str]],
    evidence_map: (
        Mapping[tuple[Any, ...], Mapping[str, Mapping[str, object]]] | None
    ) = None,
) -> dict[tuple[Any, ...], set[str]]:
    """Return per-row attributes that deterministic should not reclassify.

    Attributes are locked when explicit stage already produced a non-placeholder
    value, and also when explicit stage marked them as conflict
    (multiple explicit values matched), so deterministic cannot override that
    ambiguity.
    """
    if explicit_df.is_empty():
        return {}
    if any(column not in explicit_df.columns for column in key_columns):
        return {}
    if category_column not in explicit_df.columns:
        return {}

    locks: dict[tuple[Any, ...], set[str]] = {}
    for row in explicit_df.to_dicts():
        category_key = _normalize_key(row.get(category_column))
        category_attrs = attr_map.get(category_key, ())
        if not category_attrs:
            continue
        key = tuple(row.get(column) for column in key_columns)
        evidence_for_row = evidence_map.get(key, {}) if evidence_map else {}
        locked_attrs = locks.setdefault(key, set())
        for attr_id in category_attrs:
            if attr_id not in row:
                continue
            attr_token = str(attr_id).strip()
            if not attr_token:
                continue
            if not _is_placeholder_value(row.get(attr_id)):
                locked_attrs.add(attr_token)
                continue
            decision = str(
                (evidence_for_row.get(attr_token) or {}).get("decision") or ""
            ).strip()
            if decision == "conflict":
                locked_attrs.add(attr_token)
    return locks


def _classify_deterministic_unresolved_attributes(
    *,
    classification_df: pl.DataFrame,
    key_columns: Sequence[str],
    category_column: str,
    product_column: str,
    attr_map: Mapping[str, Sequence[str]],
    explicit_locks: Mapping[tuple[Any, ...], set[str]],
    brand_col: str | None = None,
    desc_col: str | None = None,
) -> pl.DataFrame:
    """Run deterministic classification only for attributes unresolved upstream."""
    if classification_df.is_empty() or not attr_map:
        return pl.DataFrame()
    required_cols = {product_column, category_column, *key_columns}
    if any(column not in classification_df.columns for column in required_cols):
        return pl.DataFrame()

    bucket_rows: dict[tuple[str, tuple[str, ...]], list[dict[str, object]]] = {}
    for row in classification_df.to_dicts():
        category_key = _normalize_key(row.get(category_column))
        category_attrs = [str(attr).strip() for attr in attr_map.get(category_key, ())]
        if not category_attrs:
            continue
        row_key = tuple(row.get(column) for column in key_columns)
        locked_attrs = explicit_locks.get(row_key, set())
        unresolved_attrs = tuple(
            attr for attr in category_attrs if attr and attr not in locked_attrs
        )
        if not unresolved_attrs:
            continue
        bucket_rows.setdefault((category_key, unresolved_attrs), []).append(row)

    if not bucket_rows:
        return pl.DataFrame()

    deterministic_frames: list[pl.DataFrame] = []
    for (category_key, unresolved_attrs), rows in bucket_rows.items():
        bucket_df = pl.DataFrame(rows, strict=False, infer_schema_length=None)
        if bucket_df.is_empty():
            continue
        deterministic_frame = classify_attributes_for_products(
            llm_wrapper=None,
            df=bucket_df,
            product_col=product_column,
            products=bucket_df.get_column(product_column).to_list(),
            attr_map={category_key: list(unresolved_attrs)},
            group_col=category_column,
            groups=bucket_df.get_column(category_column).to_list(),
            deterministic_only=True,
            brand_col=brand_col,
            desc_col=desc_col,
        )
        if not deterministic_frame.is_empty():
            deterministic_frames.append(deterministic_frame)

    if not deterministic_frames:
        return pl.DataFrame()

    combined = pl.concat(deterministic_frames, how="diagonal_relaxed")
    dedupe_subset = [column for column in key_columns if column in combined.columns]
    if dedupe_subset:
        combined = combined.unique(subset=dedupe_subset, keep="first")
    return combined


def _build_explicit_record_evidence(
    *,
    stage_df: pl.DataFrame,
    row_type: str,
    key_columns: Sequence[str],
    category_column: str,
    attr_map: Mapping[str, Sequence[str]],
    evidence_map: Mapping[tuple[Any, ...], Mapping[str, Mapping[str, object]]],
) -> dict[_AttributeRecordKey, dict[str, object]]:
    """Build evidence payloads keyed by persisted attribute-record key."""
    if stage_df.is_empty():
        return {}
    required = {"retailer", "parent_product_id", *key_columns, category_column}
    if row_type == "variant":
        required.add("variant_id")
    if any(column not in stage_df.columns for column in required):
        return {}

    record_evidence: dict[_AttributeRecordKey, dict[str, object]] = {}
    for row in stage_df.to_dicts():
        retailer = str(row.get("retailer") or "").strip()
        parent_id = str(row.get("parent_product_id") or "").strip()
        if not retailer or not parent_id:
            continue
        variant_id = ""
        if row_type == "variant":
            variant_id = str(row.get("variant_id") or "").strip()
            if not variant_id:
                continue

        key = tuple(row.get(column) for column in key_columns)
        evidence_for_row = evidence_map.get(key, {})
        category_key = _normalize_key(row.get(category_column))
        category_attrs = [str(attr).strip() for attr in attr_map.get(category_key, ())]
        for attr_id in category_attrs:
            if attr_id not in row:
                continue
            value = row.get(attr_id)
            if value is None:
                continue
            payload = dict(evidence_for_row.get(attr_id, {"decision": "no_match"}))
            record_key: _AttributeRecordKey = (
                retailer,
                row_type,
                parent_id,
                variant_id if row_type == "variant" else "",
                category_key,
                attr_id,
            )
            record_evidence[record_key] = payload
    return record_evidence


def compute_pdp_attributes(
    pdp_store_path: Path | str,
    retailers: Sequence[str] | None = None,
    *,
    llm_wrapper: Any | None = None,
    categories: Sequence[str] | None = None,
    parent_ids: Sequence[str] | None = None,
    llm_dump_path: Path | None = None,
    persist: bool = True,
    clear_retailer: bool = False,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, set[str], pl.DataFrame]:
    taxonomy = get_runtime_attribute_taxonomy()
    category_alias_map = get_category_alias_map()
    explicit_rules = load_explicit_declaration_rules()
    store = PDPStore(pdp_store_path)
    attr_labels = _build_attribute_id_lookup(taxonomy)
    cache_metadata: dict[str, Any] | None = None
    (
        base_df,
        unmatched_categories,
        unmatched_examples,
        parent_segment_df,
    ) = _load_parent_products(
        pdp_store_path,
        taxonomy,
        retailers,
        category_aliases=category_alias_map,
        requested_categories=categories,
    )

    normalized: set[str] | None = None
    parent_filter_ids: set[str] | None = None
    pre_category_parent_count = base_df.height
    available_category_keys_before_filter: list[str] = []
    available_category_examples: dict[str, list[str]] = {}
    if not base_df.is_empty() and "category_key" in base_df.columns:
        available_category_keys_before_filter = sorted(
            {
                _normalize_key(value)
                for value in base_df.get_column("category_key").drop_nulls().to_list()
                if _normalize_key(value)
            }
        )
        if "raw_category_path" in base_df.columns:
            example_buckets: dict[str, set[str]] = {}
            for row in base_df.select(["category_key", "raw_category_path"]).to_dicts():
                key = _normalize_key(row.get("category_key"))
                if not key:
                    continue
                raw_path = row.get("raw_category_path")
                if isinstance(raw_path, Sequence) and not isinstance(
                    raw_path, (str, bytes, bytearray)
                ):
                    pretty = " > ".join(
                        str(item).strip() for item in raw_path if str(item).strip()
                    )
                    if pretty:
                        example_buckets.setdefault(key, set()).add(pretty)
            available_category_examples = {
                key: sorted(values)[:3] for key, values in example_buckets.items()
            }
    if categories:
        normalized = _expanded_requested_category_keys(categories)
        if normalized:
            base_df = base_df.filter(pl.col("category_key").is_in(normalized))
            if not parent_segment_df.is_empty():
                parent_segment_df = parent_segment_df.filter(
                    pl.col("category_key").is_in(normalized)
                )
            unmatched_categories = {
                cat for cat in unmatched_categories if cat in normalized
            }
            if pre_category_parent_count > 0 and base_df.is_empty():
                LOGGER.warning(
                    "Category filter resolved to 0 parent rows for retailers=%s requested_categories=%s. "
                    "Available category keys before filtering=%s. Example source category paths=%s. "
                    "This usually means retailer-native category labels did not map to the normalized category key; "
                    "add category aliases or persist category_key / links.json membership.",
                    retailers,
                    sorted(normalized),
                    available_category_keys_before_filter,
                    available_category_examples,
                )

    if parent_ids:
        parent_filter_ids = {str(pid).strip() for pid in parent_ids if str(pid).strip()}
        if parent_filter_ids:
            base_df = base_df.filter(
                pl.col("parent_product_id").is_in(parent_filter_ids)
            )
            if not parent_segment_df.is_empty():
                parent_segment_df = parent_segment_df.filter(
                    pl.col("parent_product_id").is_in(parent_filter_ids)
                )

    if LOGGER.isEnabledFor(logging.INFO):
        LOGGER.info(
            "Deterministic pass: starting with %s parents (retailers=%s, categories=%s, parent_filter=%s)",
            base_df.height,
            retailers,
            categories,
            parent_filter_ids,
        )

    if base_df.is_empty():
        return (
            base_df,
            pl.DataFrame(),
            pl.DataFrame(),
            unmatched_categories,
            pl.DataFrame(),
            unmatched_examples,
        )

    base_df = _attach_canonical_columns(base_df)
    # Allow multiple retailers to share a canonical_id; surface the owner for later unification.
    canonical_map = store.get_canonical_owners(
        base_df.get_column("canonical_id").to_list()
    )
    canonical_map = {
        key: (val or "").strip().lower() for key, val in canonical_map.items()
    }
    base_df = base_df.with_columns(
        pl.col("canonical_id")
        .map_elements(
            lambda cid: canonical_map.get(cid, "") if cid is not None else "",
            return_dtype=pl.Utf8,
        )
        .alias("canonical_owner")
    ).with_columns(
        pl.lit(True).alias("canonical_accept"),
        pl.col("canonical_id").alias("canonical_id_export"),
    )

    if base_df.is_empty():
        return (
            base_df,
            pl.DataFrame(),
            pl.DataFrame(),
            unmatched_categories,
            pl.DataFrame(),
            unmatched_examples,
        )

    canonical_rows = (
        base_df.select(
            [
                "canonical_id",
                "brand_norm",
                "product_name_norm",
                "retailer",
                "parent_product_id",
            ]
        )
        .unique()
        .to_dicts()
    )

    classification_input = (
        base_df.filter(pl.col("category_key") != "")
        .select(
            "retailer",
            "parent_product_id",
            "product_name",
            "category_key",
            "brand",
            "description",
        )
        .unique()
    )
    parent_deterministic_lookup = _build_deterministic_description_lookup(
        parent_segment_df,
        key_columns=["retailer", "parent_product_id", "category_key"],
        source_channels=_DETERMINISTIC_PARENT_SOURCE_CHANNELS,
        output_column="deterministic_description",
    )
    if parent_deterministic_lookup.is_empty():
        classification_input = classification_input.with_columns(
            pl.lit("").alias("deterministic_description")
        )
    else:
        classification_input = classification_input.join(
            parent_deterministic_lookup,
            on=["retailer", "parent_product_id", "category_key"],
            how="left",
        ).with_columns(pl.col("deterministic_description").fill_null(""))

    attr_map = _build_attribute_map(
        taxonomy,
        base_df["category_key"],
        row_scope="parent",
    )

    if LOGGER.isEnabledFor(logging.INFO):
        LOGGER.info(
            "Deterministic pass: starting parent classification for %s parents (categories=%s)",
            base_df.height,
            len(attr_map),
        )

    explicit_parent_evidence: dict[tuple[Any, ...], dict[str, dict[str, object]]] = {}
    if classification_input.is_empty() or not attr_map:
        explicit_parent_classification = pl.DataFrame()
        deterministic_parent_classification = pl.DataFrame()
    else:
        (
            explicit_parent_classification,
            explicit_parent_evidence,
        ) = classify_explicit_declarations_with_evidence(
            classification_input,
            key_columns=["product_name", "category_key"],
            category_column="category_key",
            text_columns=["description"],
            attr_map=attr_map,
            taxonomy=taxonomy,
            rules=explicit_rules,
        )
        explicit_parent_locks = _collect_explicit_attribute_locks(
            explicit_parent_classification,
            key_columns=["product_name", "category_key"],
            category_column="category_key",
            attr_map=attr_map,
            evidence_map=explicit_parent_evidence,
        )
        deterministic_parent_classification = (
            _classify_deterministic_unresolved_attributes(
                classification_df=classification_input,
                key_columns=["product_name", "category_key"],
                category_column="category_key",
                product_column="product_name",
                attr_map=attr_map,
                explicit_locks=explicit_parent_locks,
                brand_col="brand",
                desc_col="deterministic_description",
            )
        )
        drop_cols = [
            col
            for col in (
                "brand",
                "description",
                "retailer",
                "parent_product_id",
                "deterministic_description",
            )
            if col in deterministic_parent_classification.columns
        ]
        if drop_cols:
            deterministic_parent_classification = (
                deterministic_parent_classification.drop(drop_cols)
            )

    parent_classification = _merge_fill_only_classifications(
        explicit_parent_classification,
        deterministic_parent_classification,
        key_columns=["product_name", "category_key"],
    )

    if parent_classification.is_empty():
        parent_result = base_df
    else:
        parent_result = _join_classification_overrides(
            base_df,
            parent_classification,
            key_columns=["product_name", "category_key"],
        )
    explicit_parent_stage = (
        _join_classification_overrides(
            base_df,
            explicit_parent_classification,
            key_columns=["product_name", "category_key"],
        )
        if not explicit_parent_classification.is_empty()
        else pl.DataFrame()
    )
    explicit_parent_columns = {
        column
        for column in explicit_parent_classification.columns
        if column not in {"product_name", "category_key"}
    }
    deterministic_parent_stage = (
        _join_classification_overrides(
            base_df,
            deterministic_parent_classification,
            key_columns=["product_name", "category_key"],
        )
        if not deterministic_parent_classification.is_empty()
        else pl.DataFrame()
    )
    deterministic_parent_columns = {
        column
        for column in deterministic_parent_classification.columns
        if column not in {"product_name", "category_key"}
    }
    explicit_parent_record_evidence = _build_explicit_record_evidence(
        stage_df=explicit_parent_stage,
        row_type="parent",
        key_columns=["product_name", "category_key"],
        category_column="category_key",
        attr_map=attr_map,
        evidence_map=explicit_parent_evidence,
    )

    if LOGGER.isEnabledFor(logging.INFO):
        LOGGER.info(
            "Deterministic pass: finished parent classification (rows=%s)",
            parent_result.height,
        )

    variant_df, variant_segment_df = _load_variants(pdp_store_path, base_df)
    if parent_filter_ids:
        variant_df = variant_df.filter(
            pl.col("parent_product_id").is_in(parent_filter_ids)
        )
        if not variant_segment_df.is_empty():
            variant_segment_df = variant_segment_df.filter(
                pl.col("parent_product_id").is_in(parent_filter_ids)
            )
    if categories and normalized:
        variant_df = variant_df.filter(pl.col("category_key").is_in(normalized))
        if not variant_segment_df.is_empty():
            variant_segment_df = variant_segment_df.filter(
                pl.col("category_key").is_in(normalized)
            )
    if not variant_df.is_empty():
        canonical_lookup = base_df.select(
            [
                "retailer",
                "parent_product_id",
                "category_key",
                "canonical_id",
                "brand_norm",
                "product_name_norm",
            ]
        )
        variant_df = variant_df.join(
            canonical_lookup,
            on=["retailer", "parent_product_id", "category_key"],
            how="inner",
        )
        if not variant_segment_df.is_empty():
            variant_segment_df = variant_segment_df.join(
                variant_df.select(
                    ["retailer", "parent_product_id", "variant_id", "category_key"]
                ).unique(),
                on=["retailer", "parent_product_id", "variant_id", "category_key"],
                how="inner",
            )

    variant_input = (
        variant_df.filter(pl.col("category_key") != "")
        .select(
            "retailer",
            "parent_product_id",
            "variant_id",
            pl.concat_str(
                [
                    pl.col("product_name").fill_null(""),
                    pl.lit(" "),
                    pl.col("shade_name_raw").fill_null(""),
                    pl.lit(" "),
                    pl.col("size_text_raw").fill_null(""),
                ]
            )
            .str.strip_chars()
            .alias("variant_product_name"),
            pl.concat_str(
                [
                    pl.col("description").fill_null(""),
                    pl.lit(" "),
                    pl.col("variant_description").fill_null(""),
                ]
            )
            .str.strip_chars()
            .alias("variant_description"),
            "category_key",
            "brand",
            pl.col("variant_key"),
        )
        .unique()
    )
    variant_deterministic_lookup = _build_deterministic_description_lookup(
        variant_segment_df,
        key_columns=["retailer", "parent_product_id", "variant_id", "category_key"],
        source_channels=_DETERMINISTIC_VARIANT_SOURCE_CHANNELS,
        output_column="deterministic_variant_description",
    )
    if variant_deterministic_lookup.is_empty():
        variant_input = variant_input.with_columns(
            pl.lit("").alias("deterministic_variant_description")
        )
    else:
        variant_input = variant_input.join(
            variant_deterministic_lookup,
            on=["retailer", "parent_product_id", "variant_id", "category_key"],
            how="left",
        ).with_columns(pl.col("deterministic_variant_description").fill_null(""))

    variant_result = variant_df
    explicit_variant_classification = pl.DataFrame()
    explicit_variant_evidence: dict[tuple[Any, ...], dict[str, dict[str, object]]] = {}
    deterministic_variant_classification = pl.DataFrame()
    variant_attr_map: dict[str, list[str]] = {}
    if not variant_input.is_empty():
        variant_attr_map = _build_attribute_map(
            taxonomy,
            variant_df["category_key"],
            row_scope="variant",
        )
        if variant_attr_map:
            if LOGGER.isEnabledFor(logging.INFO):
                LOGGER.info(
                    "Deterministic pass: starting variant classification for %s variants (categories=%s)",
                    variant_df.height,
                    len(variant_attr_map),
                )

            (
                explicit_variant_classification,
                explicit_variant_evidence,
            ) = classify_explicit_declarations_with_evidence(
                variant_input,
                key_columns=["variant_key", "category_key"],
                category_column="category_key",
                text_columns=["variant_description"],
                attr_map=variant_attr_map,
                taxonomy=taxonomy,
                rules=explicit_rules,
            )
            explicit_variant_locks = _collect_explicit_attribute_locks(
                explicit_variant_classification,
                key_columns=["variant_key", "category_key"],
                category_column="category_key",
                attr_map=variant_attr_map,
                evidence_map=explicit_variant_evidence,
            )
            deterministic_variant_classification = (
                _classify_deterministic_unresolved_attributes(
                    classification_df=variant_input,
                    key_columns=["variant_key", "category_key"],
                    category_column="category_key",
                    product_column="variant_key",
                    attr_map=variant_attr_map,
                    explicit_locks=explicit_variant_locks,
                    brand_col="brand",
                    desc_col="deterministic_variant_description",
                )
            )
            if not deterministic_variant_classification.is_empty():
                drop_cols = [
                    col
                    for col in (
                        "brand",
                        "variant_description",
                        "retailer",
                        "parent_product_id",
                        "variant_id",
                        "deterministic_variant_description",
                    )
                    if col in deterministic_variant_classification.columns
                ]
                if drop_cols:
                    deterministic_variant_classification = (
                        deterministic_variant_classification.drop(drop_cols)
                    )

            variant_classification = _merge_fill_only_classifications(
                explicit_variant_classification,
                deterministic_variant_classification,
                key_columns=["variant_key", "category_key"],
            )

            if not variant_classification.is_empty():
                variant_result = _join_classification_overrides(
                    variant_df,
                    variant_classification,
                    key_columns=["variant_key", "category_key"],
                )

            if LOGGER.isEnabledFor(logging.INFO):
                LOGGER.info(
                    "Deterministic pass: finished variant classification (rows=%s)",
                    variant_result.height,
                )

    explicit_variant_stage = (
        _join_classification_overrides(
            variant_df,
            explicit_variant_classification,
            key_columns=["variant_key", "category_key"],
        )
        if not explicit_variant_classification.is_empty()
        else pl.DataFrame()
    )
    explicit_variant_columns = {
        column
        for column in explicit_variant_classification.columns
        if column not in {"variant_key", "category_key"}
    }
    deterministic_variant_stage = (
        _join_classification_overrides(
            variant_df,
            deterministic_variant_classification,
            key_columns=["variant_key", "category_key"],
        )
        if not deterministic_variant_classification.is_empty()
        else pl.DataFrame()
    )
    deterministic_variant_columns = {
        column
        for column in deterministic_variant_classification.columns
        if column not in {"variant_key", "category_key"}
    }
    explicit_variant_record_evidence = _build_explicit_record_evidence(
        stage_df=explicit_variant_stage,
        row_type="variant",
        key_columns=["variant_key", "category_key"],
        category_column="category_key",
        attr_map=variant_attr_map,
        evidence_map=explicit_variant_evidence,
    )

    parent_result = annotate_market_hybrid_claims(parent_result, record_type="parent")
    variant_result = annotate_market_hybrid_claims(
        variant_result,
        record_type="variant",
    )

    if llm_wrapper is not None:
        sure_consensus = _load_sure_resolution_consensus()
        if not sure_consensus.is_empty():
            parent_result, parent_prefill = _apply_sure_consensus_to_frame(
                parent_result,
                row_type="parent",
                sure_consensus=sure_consensus,
            )
            variant_result, variant_prefill = _apply_sure_consensus_to_frame(
                variant_result,
                row_type="variant",
                sure_consensus=sure_consensus,
            )
            if LOGGER.isEnabledFor(logging.INFO):
                LOGGER.info(
                    "Consensus prefill before LLM: parent_updates=%s variant_updates=%s",
                    parent_prefill,
                    variant_prefill,
                )

        if LOGGER.isEnabledFor(logging.INFO):
            LOGGER.info(
                "LLM pass: starting fill for %s parents and %s variants",
                parent_result.height,
                variant_result.height,
            )

        (
            parent_result,
            variant_result,
            llm_touched,
            llm_attribute_meta,
        ) = _llm_fill_pdp_attributes(
            llm_wrapper,
            parent_result,
            variant_result,
            taxonomy,
            llm_dump_path=llm_dump_path,
        )
        if LOGGER.isEnabledFor(logging.INFO):
            LOGGER.info(
                "LLM pass: finished fill (touched: parent=%s variant=%s)",
                len(llm_touched.get("parent", [])),
                len(llm_touched.get("variant", [])),
            )
    else:
        llm_touched = {"parent": set(), "variant": set()}
        llm_attribute_meta = {}

    if LOGGER.isEnabledFor(logging.INFO):
        LOGGER.info("Finalize: building attribute views")
    parent_result, category_meta = _annotate_pareto_and_price(
        parent_result,
        variant_result,
        retailers=retailers,
    )
    parent_filtered, variant_result, combined, parent_complete, attr_cols = (
        _finalize_attribute_views(
            parent_result,
            variant_result,
        )
    )
    if LOGGER.isEnabledFor(logging.INFO):
        LOGGER.info(
            "Finalize: complete (parent_filtered=%s variant_result=%s combined=%s)",
            parent_filtered.height,
            variant_result.height,
            combined.height,
        )

    parent_ids_scope: set[str] = set()
    try:
        if not parent_result.is_empty():
            parent_ids_scope = set(
                parent_result.get_column("parent_product_id").to_list()
            )
    except Exception:
        parent_ids_scope = set()

    def _dedupe_attribute_columns(df: pl.DataFrame) -> pl.DataFrame:
        """Coalesce duplicate/near-duplicate attribute columns that normalize to the same key."""
        if df.is_empty():
            return df
        norms: dict[str, str] = {}
        coalesce_exprs: list[pl.Expr] = []
        drop_cols: list[str] = []
        for col in df.columns:
            norm = col.strip().lower().replace(" ", "_")
            if norm not in norms:
                norms[norm] = col
                continue
            keeper = norms[norm]
            coalesce_exprs.append(
                pl.when(
                    pl.col(keeper).is_null()
                    | (pl.col(keeper).cast(pl.Utf8).str.strip_chars() == "")
                )
                .then(pl.col(col))
                .otherwise(pl.col(keeper))
                .alias(keeper)
            )
            drop_cols.append(col)
        if coalesce_exprs:
            df = df.with_columns(coalesce_exprs)
        if drop_cols:
            df = df.drop(drop_cols)
        return df

    if persist:
        retailer_scope = sorted(
            {
                str(value).strip()
                for value in base_df.get_column("retailer").unique().to_list()
                if isinstance(value, str) and str(value).strip()
            }
        )
        history_enabled = _should_write_resolution_history(pdp_store_path)
        history_run_id = (
            build_resolution_run_id("pdp-attribute-export") if history_enabled else ""
        )
        history_rows: list[dict[str, Any]] = []
        parent_history_lookup: dict[tuple[str, str], dict[str, str]] = {}
        variant_history_lookup: dict[tuple[str, str], dict[str, str]] = {}
        if history_enabled:
            parent_history_lookup, variant_history_lookup = (
                _build_resolution_context_maps(
                    parent_complete,
                    variant_result,
                )
            )

        existing_parent_filtered: pl.DataFrame | None = None
        existing_variant_result: pl.DataFrame | None = None
        existing_combined: pl.DataFrame | None = None
        existing_parent_complete: pl.DataFrame | None = None

        existing_source = "none"
        cache_result = _load_attribute_cache_from_store(pdp_store_path)
        if cache_result is not None:
            existing_source = "database"

        if cache_result is not None:
            (
                existing_parent_filtered,
                existing_variant_result,
                existing_combined,
                existing_parent_complete,
                _,
            ) = cache_result

        if LOGGER.isEnabledFor(logging.INFO):
            LOGGER.info("Persist: loaded existing cache source=%s", existing_source)

        placeholders = list(_ATTRIBUTE_PLACEHOLDER_CANONICAL) + [""]

        def _dtype_is_list(dtype: object | None) -> bool:
            try:
                return dtype is not None and dtype.is_list()
            except AttributeError:
                return False

        def _meaningful_expr(column: str, dtype: object | None) -> pl.Expr:
            col = pl.col(column)
            if dtype == pl.Utf8:
                cleaned = col.cast(pl.Utf8).str.strip_chars().str.to_lowercase()
                return col.is_not_null() & cleaned.is_in(placeholders).not_()
            if _dtype_is_list(dtype):
                return col.is_not_null() & (col.list.len() > 0)
            return col.is_not_null()

        def _collapse_duplicates(
            df: pl.DataFrame, key_cols: Sequence[str], label: str
        ) -> pl.DataFrame:
            if df.is_empty():
                return df
            missing = [col for col in key_cols if col not in df.columns]
            if missing:
                LOGGER.warning(
                    "Persist: cannot collapse duplicates for %s; missing keys=%s",
                    label,
                    missing,
                )
                return df

            df = _normalize_cache_merge_key_columns(df, key_cols)
            duplicate_rows = df.height - df.unique(subset=list(key_cols)).height
            if duplicate_rows <= 0:
                return df

            if LOGGER.isEnabledFor(logging.WARNING):
                LOGGER.warning(
                    "Persist: collapsing %s duplicate rows in %s (keys=%s)",
                    duplicate_rows,
                    label,
                    list(key_cols),
                )

            agg_exprs: list[pl.Expr] = []
            for col in df.columns:
                if col in key_cols:
                    continue
                dtype = df.schema.get(col)
                if dtype == pl.Utf8 or _dtype_is_list(dtype):
                    cond = _meaningful_expr(col, dtype)
                    agg_exprs.append(
                        pl.coalesce(
                            pl.col(col).filter(cond).first(),
                            pl.col(col).drop_nulls().first(),
                            pl.col(col).first(),
                        ).alias(col)
                    )
                else:
                    agg_exprs.append(
                        pl.coalesce(
                            pl.col(col).drop_nulls().first(), pl.col(col).first()
                        ).alias(col)
                    )

            collapsed = df.group_by(list(key_cols), maintain_order=True).agg(agg_exprs)
            ordered = list(key_cols) + [
                col for col in df.columns if col not in key_cols
            ]
            return collapsed.select(
                [col for col in ordered if col in collapsed.columns]
            )

        def _merge_frames(
            existing_df: pl.DataFrame | None,
            new_df: pl.DataFrame,
            *,
            key_cols: Sequence[str],
            label: str,
        ) -> pl.DataFrame:
            if new_df.is_empty() and (existing_df is None or existing_df.is_empty()):
                return pl.DataFrame()

            existing = pl.DataFrame() if existing_df is None else existing_df
            if not existing.is_empty():
                filtered = existing
                if clear_retailer and retailer_scope and "retailer" in filtered.columns:
                    filtered = filtered.filter(
                        ~pl.col("retailer").is_in(retailer_scope)
                    )
                if parent_filter_ids:
                    if "parent_product_id" in filtered.columns:
                        filtered = filtered.filter(
                            ~pl.col("parent_product_id").is_in(list(parent_filter_ids))
                        )
                    elif "product" in filtered.columns:
                        filtered = filtered.filter(
                            ~pl.col("product").is_in(list(parent_filter_ids))
                        )
                existing = filtered

            existing = _collapse_duplicates(existing, key_cols, f"{label} existing")
            new_df = _collapse_duplicates(new_df, key_cols, f"{label} new")

            if existing.is_empty():
                return new_df
            if new_df.is_empty():
                return existing

            missing_existing = [col for col in key_cols if col not in existing.columns]
            missing_new = [col for col in key_cols if col not in new_df.columns]
            if missing_existing or missing_new:
                LOGGER.warning(
                    "Persist: falling back to concat for %s (missing_existing=%s missing_new=%s)",
                    label,
                    missing_existing,
                    missing_new,
                )
                return pl.concat([existing, new_df], how="diagonal_relaxed")

            suffix = "__new"
            joined = existing.join(new_df, on=list(key_cols), how="full", suffix=suffix)

            key_exprs = [
                pl.coalesce(pl.col(col), pl.col(f"{col}{suffix}")).alias(col)
                for col in key_cols
            ]

            existing_cols = set(existing.columns)
            new_cols = set(new_df.columns)
            ordered_non_keys = [
                col for col in new_df.columns if col not in key_cols
            ] + [
                col
                for col in existing.columns
                if col not in key_cols and col not in new_cols
            ]

            merged_exprs: list[pl.Expr] = []
            for col in ordered_non_keys:
                if col in existing_cols and col in new_cols:
                    new_col = f"{col}{suffix}"
                    dtype = new_df.schema.get(col) or existing.schema.get(col)
                    if new_col in joined.columns:
                        merged_exprs.append(
                            pl.when(_meaningful_expr(new_col, dtype))
                            .then(pl.col(new_col))
                            .otherwise(pl.col(col))
                            .alias(col)
                        )
                    else:
                        merged_exprs.append(pl.col(col).alias(col))
                else:
                    merged_exprs.append(pl.col(col).alias(col))

            merged = joined.select(key_exprs + merged_exprs)
            duplicate_rows = merged.height - merged.unique(subset=list(key_cols)).height
            if duplicate_rows > 0:
                LOGGER.error(
                    "Persist: duplicate keys remain after merge for %s (dupes=%s keys=%s)",
                    label,
                    duplicate_rows,
                    list(key_cols),
                )
            return merged

        merged_parent_filtered = _merge_frames(
            existing_parent_filtered,
            parent_filtered,
            key_cols=["retailer", "parent_product_id", "category_key"],
            label="parent_filtered",
        )
        merged_variant_result = _merge_frames(
            existing_variant_result,
            variant_result,
            key_cols=["retailer", "variant_id", "category_key"],
            label="variant_result",
        )
        merged_combined = _merge_frames(
            existing_combined,
            combined,
            key_cols=["record_type", "retailer", "product", "variant", "category_key"],
            label="combined",
        )
        merged_parent_complete = _merge_frames(
            existing_parent_complete,
            parent_complete,
            key_cols=["retailer", "parent_product_id", "category_key"],
            label="parents_all",
        )

        if LOGGER.isEnabledFor(logging.INFO):
            LOGGER.info(
                "Persist: merged frames (parent_filtered=%s variant_result=%s combined=%s parents_all=%s)",
                merged_parent_filtered.height,
                merged_variant_result.height,
                merged_combined.height,
                merged_parent_complete.height,
            )

        sources_to_clear = (
            ["deterministic_explicit", "deterministic", "llm"]
            if llm_wrapper is not None
            else ["deterministic_explicit", "deterministic"]
        )
        backfilled_snapshot_rows = store.backfill_attribute_audit_from_values(
            sources=sources_to_clear,
            retailers=retailer_scope,
            parent_ids=parent_ids_scope,
        )
        if LOGGER.isEnabledFor(logging.INFO):
            target_desc = (
                f"{len(parent_ids_scope)} parents"
                if parent_ids_scope
                else (retailer_scope or "(all)")
            )
            LOGGER.info(
                "Persist: backfilled audit rows from attribute_values snapshot (rows=%s target=%s sources=%s)",
                backfilled_snapshot_rows,
                target_desc,
                sources_to_clear,
            )
        scoped_parent_clear = bool(parent_ids_scope) and (
            bool(parent_filter_ids) or bool(categories)
        )
        category_scope = sorted(normalized) if normalized else None

        if scoped_parent_clear:
            store.clear_attribute_values_for_parents(
                parent_ids_scope,
                retailers=retailer_scope,
                sources=sources_to_clear,
                category_keys=category_scope,
            )
        elif clear_retailer and retailer_scope:
            store.clear_attribute_values(
                retailers=retailer_scope,
                sources=sources_to_clear,
            )
        elif clear_retailer:
            store.clear_attribute_values(sources=sources_to_clear)
        elif retailer_scope:
            store.clear_attribute_values(
                retailers=retailer_scope,
                sources=sources_to_clear,
            )
        else:
            store.clear_attribute_values(sources_to_clear)

        if LOGGER.isEnabledFor(logging.INFO):
            target_desc = (
                f"{len(parent_ids_scope)} parents"
                if scoped_parent_clear
                else (retailer_scope or "(all)")
            )
            LOGGER.info(
                "Persist: cleared attribute_values for %s sources=%s",
                target_desc,
                sources_to_clear,
            )

        if scoped_parent_clear:
            store.clear_stage_attribute_values_for_parents(
                "deterministic_explicit",
                parent_ids_scope,
                retailers=retailer_scope,
                category_keys=category_scope,
            )
            store.clear_stage_attribute_values_for_parents(
                "deterministic",
                parent_ids_scope,
                retailers=retailer_scope,
                category_keys=category_scope,
            )
            if llm_wrapper is not None:
                store.clear_stage_attribute_values_for_parents(
                    "llm",
                    parent_ids_scope,
                    retailers=retailer_scope,
                    category_keys=category_scope,
                )
        elif retailer_scope:
            store.clear_stage_attribute_values(
                "deterministic_explicit", retailers=retailer_scope
            )
            store.clear_stage_attribute_values(
                "deterministic", retailers=retailer_scope
            )
            if llm_wrapper is not None:
                store.clear_stage_attribute_values("llm", retailers=retailer_scope)
        else:
            store.clear_stage_attribute_values("deterministic_explicit")
            store.clear_stage_attribute_values("deterministic")
            if llm_wrapper is not None:
                store.clear_stage_attribute_values("llm")

        if LOGGER.isEnabledFor(logging.INFO):
            LOGGER.info(
                "Persist: cleared stage tables (deterministic_explicit + deterministic%s)",
                " + llm" if llm_wrapper is not None else "",
            )

        explicit_parent_for_store = explicit_parent_stage
        explicit_variant_for_store = explicit_variant_stage
        if retailer_scope and not explicit_parent_for_store.is_empty():
            explicit_parent_for_store = explicit_parent_for_store.filter(
                pl.col("retailer").is_in(retailer_scope)
            )
        if retailer_scope and not explicit_variant_for_store.is_empty():
            explicit_variant_for_store = explicit_variant_for_store.filter(
                pl.col("retailer").is_in(retailer_scope)
            )

        timestamp_explicit = dt.datetime.now(dt.timezone.utc).isoformat()
        explicit_records: list[AttributeValueRecord] = []
        explicit_records.extend(
            _collect_attribute_records(
                explicit_parent_for_store,
                row_type="parent",
                attr_labels=attr_labels,
                source="deterministic_explicit",
                timestamp=timestamp_explicit,
                allowed_columns=explicit_parent_columns,
            )
        )
        explicit_records.extend(
            _collect_attribute_records(
                explicit_variant_for_store,
                row_type="variant",
                attr_labels=attr_labels,
                source="deterministic_explicit",
                timestamp=timestamp_explicit,
                allowed_columns=explicit_variant_columns,
            )
        )
        if explicit_records:
            store.upsert_attribute_values(explicit_records)
            store.write_stage_attribute_values(
                "deterministic_explicit",
                explicit_records,
            )
            if history_enabled:
                history_rows.extend(
                    _attribute_records_to_resolution_rows(
                        explicit_records,
                        run_id=history_run_id,
                        step="deterministic_explicit",
                        decision_rule="explicit_declaration_match",
                        parent_lookup=parent_history_lookup,
                        variant_lookup=variant_history_lookup,
                    )
                )
            explicit_audit: list[AttributeAuditRecord] = []
            for record in explicit_records:
                evidence_key: _AttributeRecordKey = (
                    record.retailer,
                    record.row_type,
                    record.parent_product_id,
                    record.variant_id or "",
                    record.category_key or "",
                    record.attribute_id,
                )
                evidence_payload = (
                    explicit_parent_record_evidence.get(evidence_key)
                    or explicit_variant_record_evidence.get(evidence_key)
                    or {"decision": "no_match"}
                )
                decision = str(evidence_payload.get("decision") or "").strip().lower()
                if not _is_placeholder_value(record.value):
                    decision_rule = "explicit_declaration_match"
                elif decision == "conflict":
                    decision_rule = "explicit_declaration_conflict"
                else:
                    decision_rule = "explicit_declaration_no_match"
                explicit_audit.append(
                    AttributeAuditRecord(
                        timestamp=timestamp_explicit,
                        source="deterministic_explicit",
                        row_type=record.row_type,
                        retailer=record.retailer,
                        parent_product_id=record.parent_product_id,
                        variant_id=record.variant_id,
                        attribute_id=record.attribute_id,
                        value=record.value,
                        decision_rule=decision_rule,
                        evidence_json=json.dumps(evidence_payload, ensure_ascii=False),
                        category_key=record.category_key or None,
                    )
                )
            store.append_attribute_audit(explicit_audit)
            if LOGGER.isEnabledFor(logging.INFO):
                LOGGER.info(
                    "Persist: wrote explicit records (total=%s) for retailers=%s",
                    len(explicit_records),
                    retailer_scope if retailer_scope else "all",
                )

        det_parent_for_store = deterministic_parent_stage
        det_variant_for_store = deterministic_variant_stage

        LOGGER.info(
            "Persisting deterministic stage values (parents=%s variants=%s)",
            (
                det_parent_for_store.height
                if hasattr(det_parent_for_store, "height")
                else len(det_parent_for_store)
            ),
            (
                det_variant_for_store.height
                if hasattr(det_variant_for_store, "height")
                else len(det_variant_for_store)
            ),
        )

        if retailer_scope and "retailer" in det_parent_for_store.columns:
            det_parent_for_store = det_parent_for_store.filter(
                pl.col("retailer").is_in(retailer_scope)
            )
        if (
            retailer_scope
            and not det_variant_for_store.is_empty()
            and "retailer" in det_variant_for_store.columns
        ):
            det_variant_for_store = det_variant_for_store.filter(
                pl.col("retailer").is_in(retailer_scope)
            )

        timestamp_det = dt.datetime.now(dt.timezone.utc).isoformat()
        det_records: list[AttributeValueRecord] = []
        det_records.extend(
            _collect_attribute_records(
                det_parent_for_store,
                row_type="parent",
                attr_labels=attr_labels,
                source="deterministic",
                timestamp=timestamp_det,
                allowed_columns=deterministic_parent_columns,
            )
        )
        det_records.extend(
            _collect_attribute_records(
                det_variant_for_store,
                row_type="variant",
                attr_labels=attr_labels,
                source="deterministic",
                timestamp=timestamp_det,
                allowed_columns=deterministic_variant_columns,
            )
        )
        store.upsert_attribute_values(det_records)
        store.write_stage_attribute_values("deterministic", det_records)
        if history_enabled and det_records:
            history_rows.extend(
                _attribute_records_to_resolution_rows(
                    det_records,
                    run_id=history_run_id,
                    step="deterministic",
                    decision_rule="deterministic_text_match",
                    parent_lookup=parent_history_lookup,
                    variant_lookup=variant_history_lookup,
                )
            )
        if det_records:
            det_audit = [
                AttributeAuditRecord(
                    timestamp=timestamp_det,
                    source="deterministic",
                    row_type=record.row_type,
                    retailer=record.retailer,
                    parent_product_id=record.parent_product_id,
                    variant_id=record.variant_id,
                    attribute_id=record.attribute_id,
                    value=record.value,
                    decision_rule="deterministic_text_match",
                    evidence_json=json.dumps({"tiebreak": "taxonomy_order"}),
                    category_key=record.category_key or None,
                )
                for record in det_records
            ]
            store.append_attribute_audit(det_audit)
        if LOGGER.isEnabledFor(logging.INFO):
            LOGGER.info(
                "Persist: wrote deterministic records (total=%s) for retailers=%s",
                len(det_records),
                retailer_scope if retailer_scope else "all",
            )

        canonical_records = [
            CanonicalProductRecord(
                canonical_id=row["canonical_id"],
                brand_normalized=row["brand_norm"],
                name_normalized=row["product_name_norm"],
                retailer=row["retailer"],
                parent_product_id=row["parent_product_id"],
                captured_at=timestamp_det,
            )
            for row in canonical_rows
        ]
        store.claim_canonical_products(canonical_records)

        if llm_wrapper is not None and (
            llm_touched["parent"] or llm_touched["variant"]
        ):
            parent_llm_for_store = parent_complete
            variant_llm_for_store = variant_result
            if retailer_scope and "retailer" in parent_llm_for_store.columns:
                parent_llm_for_store = parent_llm_for_store.filter(
                    pl.col("retailer").is_in(retailer_scope)
                )
            if (
                retailer_scope
                and not variant_llm_for_store.is_empty()
                and "retailer" in variant_llm_for_store.columns
            ):
                variant_llm_for_store = variant_llm_for_store.filter(
                    pl.col("retailer").is_in(retailer_scope)
                )
            timestamp_llm = dt.datetime.now(dt.timezone.utc).isoformat()
            llm_records: list[AttributeValueRecord] = []
            if llm_touched["parent"]:
                parent_attr_labels = {
                    k: v
                    for k, v in attr_labels.items()
                    if (k in llm_touched["parent"] or v in llm_touched["parent"])
                }
                llm_records.extend(
                    _collect_attribute_records(
                        parent_llm_for_store,
                        row_type="parent",
                        attr_labels=parent_attr_labels,
                        source="llm",
                        timestamp=timestamp_llm,
                        allowed_columns=llm_touched["parent"],
                        attribute_metadata=llm_attribute_meta,
                    )
                )
            if llm_touched["variant"]:
                variant_attr_labels = {
                    k: v
                    for k, v in attr_labels.items()
                    if (k in llm_touched["variant"] or v in llm_touched["variant"])
                }
                llm_records.extend(
                    _collect_attribute_records(
                        variant_llm_for_store,
                        row_type="variant",
                        attr_labels=variant_attr_labels,
                        source="llm",
                        timestamp=timestamp_llm,
                        allowed_columns=llm_touched["variant"],
                        attribute_metadata=llm_attribute_meta,
                    )
                )
            if llm_records:
                LOGGER.info(
                    "LLM stage collected %s attribute records (retailers=%s)",
                    len(llm_records),
                    retailer_scope if retailer_scope else "all",
                )
                LOGGER.debug("LLM stage first records: %s", llm_records[:3])
                store.upsert_attribute_values(llm_records)
                store.write_stage_attribute_values("llm", llm_records)
                if history_enabled:
                    history_rows.extend(
                        _attribute_records_to_resolution_rows(
                            llm_records,
                            run_id=history_run_id,
                            step="llm_pdp_lookup",
                            decision_rule="llm_choice",
                            parent_lookup=parent_history_lookup,
                            variant_lookup=variant_history_lookup,
                        )
                    )
                llm_audit: list[AttributeAuditRecord] = []
                for record in llm_records:
                    evidence_payload: dict[str, str] = {"tiebreak": "taxonomy_order"}
                    if record.oov_candidate:
                        evidence_payload["oov_candidate"] = record.oov_candidate
                    if record.note:
                        evidence_payload["note"] = record.note
                    llm_audit.append(
                        AttributeAuditRecord(
                            timestamp=timestamp_llm,
                            source="llm",
                            row_type=record.row_type,
                            retailer=record.retailer,
                            parent_product_id=record.parent_product_id,
                            variant_id=record.variant_id,
                            attribute_id=record.attribute_id,
                            value=record.value,
                            decision_rule="llm_choice",
                            evidence_json=json.dumps(
                                evidence_payload, ensure_ascii=False
                            ),
                            category_key=record.category_key or None,
                        )
                    )
                store.append_attribute_audit(llm_audit)
                if LOGGER.isEnabledFor(logging.INFO):
                    LOGGER.info(
                        "Persist: wrote llm records (total=%s) for retailers=%s",
                        len(llm_records),
                        retailer_scope if retailer_scope else "all",
                    )

        metrics_run_id = history_run_id or build_resolution_run_id(
            "pdp-explicit-precision"
        )
        llm_parent_attributes = sorted(
            column
            for column in llm_touched["parent"]
            if column in parent_complete.columns
        )
        llm_variant_attributes = sorted(
            column
            for column in llm_touched["variant"]
            if column in variant_result.columns
        )
        llm_parent_stage = (
            parent_complete.select(
                [
                    column
                    for column in (
                        "retailer",
                        "parent_product_id",
                        "category_key",
                        *llm_parent_attributes,
                    )
                    if column in parent_complete.columns
                ]
            )
            if llm_parent_attributes
            else pl.DataFrame()
        )
        llm_variant_stage = (
            variant_result.select(
                [
                    column
                    for column in (
                        "retailer",
                        "variant_id",
                        "category_key",
                        *llm_variant_attributes,
                    )
                    if column in variant_result.columns
                ]
            )
            if llm_variant_attributes
            else pl.DataFrame()
        )
        explicit_metrics = compute_explicit_precision_metrics(
            run_id=metrics_run_id,
            explicit_parent_stage=explicit_parent_stage,
            explicit_variant_stage=explicit_variant_stage,
            explicit_parent_attributes=sorted(explicit_parent_columns),
            explicit_variant_attributes=sorted(explicit_variant_columns),
            deterministic_parent_stage=deterministic_parent_stage,
            deterministic_variant_stage=deterministic_variant_stage,
            deterministic_parent_attributes=sorted(deterministic_parent_columns),
            deterministic_variant_attributes=sorted(deterministic_variant_columns),
            llm_parent_stage=llm_parent_stage,
            llm_variant_stage=llm_variant_stage,
            llm_parent_attributes=llm_parent_attributes,
            llm_variant_attributes=llm_variant_attributes,
        )
        if explicit_metrics:
            metrics_timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
            store.upsert_explicit_precision_metrics(
                [
                    {
                        "run_id": metric.run_id,
                        "computed_at": metrics_timestamp,
                        "category_key": metric.category_key,
                        "attribute_id": metric.attribute_id,
                        "explicit_positive_count": metric.explicit_positive_count,
                        "deterministic_match_on_explicit": (
                            metric.deterministic_match_on_explicit
                        ),
                        "llm_match_on_explicit": metric.llm_match_on_explicit,
                        "deterministic_precision_proxy": (
                            metric.deterministic_precision_proxy
                        ),
                        "llm_precision_proxy": metric.llm_precision_proxy,
                    }
                    for metric in explicit_metrics
                ]
            )
            if LOGGER.isEnabledFor(logging.INFO):
                LOGGER.info(
                    "Persist: wrote explicit precision proxy metrics (run_id=%s rows=%s)",
                    metrics_run_id,
                    len(explicit_metrics),
                )

        if history_enabled and history_rows:
            try:
                ledger_chunk = append_resolution_ledger_rows(history_rows)
                consensus_df = write_resolution_consensus()
                if LOGGER.isEnabledFor(logging.INFO):
                    LOGGER.info(
                        "Persist: wrote resolution history rows=%s chunk=%s consensus_rows=%s",
                        len(history_rows),
                        str(ledger_chunk) if ledger_chunk else "",
                        consensus_df.height,
                    )
            except Exception:  # pragma: no cover - defensive persistence
                LOGGER.exception("Failed to persist attribute resolution history")

        generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
        cache_metadata = {
            "unmatched_categories": sorted(unmatched_categories),
            "unmatched_examples": {
                cat: sorted(values) for cat, values in unmatched_examples.items()
            },
            "category_meta": category_meta or {},
            "generated_at": generated_at,
        }
        if LOGGER.isEnabledFor(logging.INFO):
            LOGGER.info("Persist: prepared database attribute cache blobs")

        parent_filtered = merged_parent_filtered
        variant_result = merged_variant_result
        combined = merged_combined
        parent_complete = merged_parent_complete

    helper_cols = [
        "canonical_id",
        "brand_norm",
        "product_name_norm",
        "canonical_owner",
        "canonical_accept",
    ]

    def _drop_helper_columns(df: pl.DataFrame) -> pl.DataFrame:
        drop_cols = [col for col in helper_cols if col in df.columns]
        return df.drop(drop_cols) if drop_cols else df

    parent_filtered = _drop_helper_columns(parent_filtered)
    variant_result = _drop_helper_columns(variant_result)
    combined = _drop_helper_columns(combined)
    parent_complete = _drop_helper_columns(parent_complete)

    parent_filtered = _prune_empty_columns(parent_filtered)
    variant_result = _prune_empty_columns(variant_result)
    combined = _prune_empty_columns(combined)
    parent_complete = _prune_empty_columns(parent_complete)

    if cache_metadata is not None:
        try:
            if LOGGER.isEnabledFor(logging.INFO):
                LOGGER.info(
                    "Persist: writing attribute cache blobs to the PDP database"
                )
            cache_entries = {
                "parent_filtered": _serialize_frame(parent_filtered),
                "variant_result": _serialize_frame(variant_result),
                "combined": _serialize_frame(combined),
                "parents_all": _serialize_frame(parent_complete),
                "metadata": _serialize_metadata(cache_metadata),
            }
            store.write_attribute_cache_entries(
                cache_entries,
                generated_at=str(
                    cache_metadata.get(
                        "generated_at",
                        dt.datetime.now(dt.timezone.utc).isoformat(),
                    )
                ),
            )
            if LOGGER.isEnabledFor(logging.INFO):
                LOGGER.info(
                    "Persist: finished writing attribute cache blobs to the PDP database"
                )
        except Exception:  # pragma: no cover - defensive persistence
            LOGGER.exception("Failed to persist attribute cache to the PDP database")

    return (
        parent_filtered,
        variant_result,
        combined,
        unmatched_categories,
        parent_complete,
        unmatched_examples,
    )


def export_pdp_attributes(
    pdp_store_path: Path | str,
    *,
    retailers: Sequence[str] | None = None,
    categories: Sequence[str] | None = None,
    llm_wrapper: Any | None = None,
    parent_filter: Sequence[str] | None = None,
    llm_dump_path: Path | None = None,
    clear_retailer: bool = False,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, set[str], dict[str, set[str]]]:
    parents_df, variants_df, combined_df, unmatched, _, unmatched_examples = (
        compute_pdp_attributes(
            pdp_store_path,
            retailers,
            llm_wrapper=llm_wrapper,
            categories=categories,
            parent_ids=parent_filter,
            llm_dump_path=llm_dump_path,
            persist=True,
            clear_retailer=clear_retailer,
        )
    )
    parents_df, variants_df, combined_df = _apply_ulta_face_authority_to_exports(
        pdp_store_path,
        parents_df=parents_df,
        variants_df=variants_df,
        combined_df=combined_df,
    )

    # Warn when category keys are not in the taxonomy
    from .attribute_taxonomy import get_attribute_taxonomy

    taxonomy = get_attribute_taxonomy()
    taxonomy_keys = {
        str(cat.get("id") or cat.get("label")).strip().lower()
        for cat in taxonomy.get("categories", []) or []
        if isinstance(cat, dict)
    }
    unknown_keys = (
        {
            key
            for key in combined_df.get_column("category_key").unique().to_list()
            if isinstance(key, str)
            and key.strip()
            and key.strip().lower() not in taxonomy_keys
        }
        if not combined_df.is_empty() and "category_key" in combined_df.columns
        else set()
    )
    if unknown_keys:
        print(f"Warning: category keys not in taxonomy: {sorted(unknown_keys)}")

    if not parents_df.is_empty():
        parents_df = parents_df.filter(pl.col("category_key") != "")
        parents_df = _prune_empty_columns(parents_df)
    if not variants_df.is_empty():
        variants_df = variants_df.filter(pl.col("category_key") != "")
        variants_df = _prune_empty_columns(variants_df)
    if not combined_df.is_empty():
        combined_df = combined_df.filter(pl.col("category_key") != "")
        combined_df = _prune_empty_columns(combined_df)

    return parents_df, variants_df, combined_df, unmatched, unmatched_examples


__all__ = [
    "compute_pdp_attributes",
    "export_pdp_attributes",
    "validate_category_setup",
    "load_pdp_attribute_mapping_inputs",
    "load_persisted_pdp_attributes",
    "get_attribute_cache_mtime",
]
