from __future__ import annotations

"""Shared PDP attribute enrichment and mapped-cache utilities."""

import base64
import datetime as dt
import hashlib
import json
import logging
import mimetypes
import unicodedata
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

import polars as pl
from json_repair import repair_json

from modules.add_attributes.attribute_fill import (
    fill_missing_attribute_values,
    map_attribute_conflicts,
    map_attribute_na_fill_candidates,
    meaningful_value_expr,
    resolve_attribute_conflicts,
)
from modules.add_attributes.attribute_taxonomy import get_attribute_taxonomy
from modules.add_attributes.pdp_attribute_export import (
    _ATTRIBUTE_PLACEHOLDERS,
    load_pdp_attribute_mapping_inputs,
    load_persisted_pdp_attributes,
)
from modules.add_attributes.tool_utils import build_web_search_request
from modules.llm.batch_runner import run_step_json
from modules.llm.llm_call_wrapper import init_llm_wrapper
from modules.pdp import attribute_resolution_history
from modules.pdp.attribute_mapping_paths import get_attribute_mapping_dir
from modules.pdp.attribute_mapping_scope import (
    filter_frame_by_retailers,
    normalize_retailer_scope,
)
from modules.pdp.attribute_review_logic import (
    build_column_aliases,
    repair_text_encoding,
    resolve_attribute_column,
)
from modules.pdp.canonical import compute_canonical_values
from modules.pdp.hybrid_overlay import annotate_market_hybrid_claims
from modules.pdp.image_cache import (
    DEFAULT_IMAGE_ROOT,
    build_image_cache,
    find_local_image,
)
from modules.pdp.review_constants import DEFAULT_PDP_STORE_PATH, enforce_default_pdp_store_path
from modules.pdp.store import (
    AttributeAuditRecord,
    AttributeValueRecord,
    PDPStore,
)
from modules.utilities.config import get_naming_params
from modules.utilities.session_context import SessionContext
from modules.utilities.utils import get_schema_and_column_names
from src.merchant_brand_lookup import lookup_websites, set_lookup_market_context

APP_ROOT = Path(__file__).resolve().parents[2]

MAPPING_DIR = get_attribute_mapping_dir()
POSTFILL_ATTRIBUTE_CACHE_DIR = MAPPING_DIR / "postfill_attribute_cache"
POSTFILL_PARENTS_OUTPUT = POSTFILL_ATTRIBUTE_CACHE_DIR / "parents.parquet"
POSTFILL_VARIANTS_OUTPUT = POSTFILL_ATTRIBUTE_CACHE_DIR / "variants.parquet"
POSTFILL_PARENTS_ALL_OUTPUT = POSTFILL_ATTRIBUTE_CACHE_DIR / "parents_all.parquet"
POSTFILL_COMBINED_OUTPUT = POSTFILL_ATTRIBUTE_CACHE_DIR / "combined.parquet"
VISION_FILL_AUDIT_CHECKPOINT_DIR = MAPPING_DIR / "attribute_vision_fill_audit_chunks"
WEB_FILL_AUDIT_CHECKPOINT_DIR = MAPPING_DIR / "attribute_web_fill_audit_chunks"
ATTRIBUTE_FILL_STATE_PATH = MAPPING_DIR / "attribute_fill_state.json"
VISION_CONFIDENCE_THRESHOLD = 0.8
VISION_SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}
VISION_IMAGE_DOWNLOAD_LIMIT_BYTES = 12_000_000
WEB_CONFIDENCE_THRESHOLD = 0.8
NO_VALUE_SUPPRESSION_RUNS = 2
MIN_LLM_ATTRIBUTE_COVERAGE = 0.7

BRAND_ALIASES_PATH = APP_ROOT / "brand_aliases.json"

ATTRIBUTE_PLACEHOLDER_VALUES: list[str] = sorted(
    {
        str(item).strip().casefold()
        for item in _ATTRIBUTE_PLACEHOLDERS
        if isinstance(item, str)
    }
)

REQUIRED_SALES_COLUMNS = [
    "month",
    "merchant",
    "category",
    "brand",
    "sku",
    "product_description",
    "sales",
    "units",
]
OPTIONAL_SALES_COLUMNS = [
    "period",
    "product_collection",
    "line",
]
SALES_COLUMN_RENAMES = {
    "time": "month",
    "l3": "category",
    "sku_number": "sku",
    "product_name": "product_description",
    "gmv": "sales",
}
ALLOWED_SALES_COLUMNS = set(REQUIRED_SALES_COLUMNS + OPTIONAL_SALES_COLUMNS)

# Some sales sources split "setting spray" and "setting powder" while the taxonomy treats them
# as one category. Normalize to the taxonomy label so category selection is consistent even
# when SKU→catalog joins are unavailable.
_CATEGORY_NORMALIZATION_MAP: dict[str, str] = {
    "blushes": "blush",
    "bronzers": "bronzer",
    "concealers": "concealer",
    "eyebrows": "eyebrow",
    "eyeshadows": "eyeshadow",
    "highlighters face": "highlighter",
    "mascaras": "mascara",
    "primers and fixers face": "face primer",
    "primers face": "face primer",
    "powders": "setting spray & powder",
    "setting spray": "setting spray & powder",
    "setting powder": "setting spray & powder",
    "automatic eye pencil": "eyeliner",
    "face make up kit": "palette",
    "face make-up kit": "palette",
    "eyes make up kit": "palette",
    "eyes make-up kit": "palette",
    "lips make up kit": "palette",
    "lips make-up kit": "palette",
    "lip marker": "lipstick",
    "contouring": "contour",
    "stick contouring": "contour",
    "wood eye pencil": "wood eye pencils",
}

# Kiko uses "wood eye pencils" as a catalog class that spans multiple taxonomy buckets
# (eyeliner / eyebrow / highlighter). Treat these as category-compatible during joins.
_CATEGORY_MATCH_COMPATIBILITY: dict[str, tuple[str, ...]] = {
    "wood eye pencils": ("eyeliner", "eyebrow", "highlighter"),
    "eyeliner": ("wood eye pencils",),
    "eyebrow": ("wood eye pencils",),
    "highlighter": ("wood eye pencils",),
}

_CATEGORY_SOURCE_PRIORITY: tuple[str, ...] = (
    "prodlast_lev4",
    "prodlast_lev3",
    "prodlast_lev2",
    "prodlast_lev1",
)
_CATEGORY_EXACT_MAP: dict[str, str] = {
    "blush": "blush",
    "blushes": "blush",
    "foundation": "foundation",
    "bronzers": "bronzer",
    "bronzer": "bronzer",
    "lipstick": "lipstick",
    "fluid lipstick": "liquid lipstick",
    "liquid lipstick": "liquid lipstick",
    "lip gloss": "lip gloss",
    "concealers": "concealer",
    "concealer": "concealer",
    "highlighters face": "highlighter",
    "highlighter": "highlighter",
    "mascaras": "mascara",
    "mascara": "mascara",
    "eyeshadows": "eyeshadow",
    "eyeshadow": "eyeshadow",
    "eyeliner": "eyeliner",
    "eyebrows": "eyebrow",
    "eyebrow": "eyebrow",
    "primers and fixers face": "face primer",
    "primers face": "face primer",
    "face primer": "face primer",
    "powders": "setting spray & powder",
    "eyes make-up kit": "palette",
    "face make-up kit": "palette",
    "lips make up kit": "palette",
    "blush face palette": "palette",
    "eyeshadow palette": "palette",
    "concealers palette": "palette",
    "contouring palette": "palette",
    "contouring": "contour",
    "stick contouring": "contour",
    "wood eye pencils": "wood eye pencils",
    "wood eye pencil": "wood eye pencils",
}
_DATASET_DEFAULT_BRANDS: dict[str, str] = {
    "guestinresidence": "guest in residence",
    "kiko": "kiko milano",
    "lorealparis": "loreal paris",
    "tikicat": "tiki cat",
    "vince": "vince",
}

_VARIANT_SEPARATOR_REGEX = r"^(.*)\s[-–—]\s(.+)$"

ATTRIBUTE_RETAILER_PRIORITY: list[str] = [
    "ulta",
    "lorealparis",
    "kiko",
    "vince",
    "guestinresidence",
    "tikicat",
    "saksfifthavenue",
    "sephora",
    "amazon",
]


def _write_audit_checkpoint_chunk(
    rows: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    chunk_index: int,
    output_dir: Path,
) -> Path | None:
    """Persist a durable parquet checkpoint for an LLM audit response batch."""
    if not rows:
        return None
    frame = pl.from_dicts(
        list(rows),
        strict=False,
        infer_schema_length=None,
    )
    if frame.is_empty():
        return None
    frame = frame.with_columns(
        [
            pl.lit(run_id).alias("run_id"),
            pl.lit(chunk_index).cast(pl.Int64).alias("chunk_index"),
            pl.lit(dt.datetime.now(dt.timezone.utc).isoformat()).alias(
                "checkpointed_at"
            ),
        ]
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    chunk_name = (
        f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        f"_{chunk_index:05d}.parquet"
    )
    chunk_path = output_dir / chunk_name
    frame.write_parquet(chunk_path)
    return chunk_path


def _write_web_audit_checkpoint_chunk(
    rows: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    chunk_index: int,
    output_dir: Path | None = None,
) -> Path | None:
    if output_dir is None:
        output_dir = WEB_FILL_AUDIT_CHECKPOINT_DIR
    return _write_audit_checkpoint_chunk(
        rows,
        run_id=run_id,
        chunk_index=chunk_index,
        output_dir=output_dir,
    )


def _write_vision_audit_checkpoint_chunk(
    rows: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    chunk_index: int,
    output_dir: Path | None = None,
) -> Path | None:
    if output_dir is None:
        output_dir = VISION_FILL_AUDIT_CHECKPOINT_DIR
    return _write_audit_checkpoint_chunk(
        rows,
        run_id=run_id,
        chunk_index=chunk_index,
        output_dir=output_dir,
    )


def _parse_iso_datetime(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _read_attribute_fill_state(
    state_path: Path | None = None,
) -> dict[str, Any]:
    path = state_path or ATTRIBUTE_FILL_STATE_PATH
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def _write_attribute_fill_state(
    *,
    status: str,
    run_id: str,
    state_path: Path | None = None,
) -> None:
    path = state_path or ATTRIBUTE_FILL_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_attribute_fill_state(path)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    status_norm = str(status or "").strip().lower()
    existing["status"] = status_norm
    existing["updated_at"] = now_iso
    if status_norm == "running":
        existing["active_run_id"] = run_id
        existing["last_started_at"] = now_iso
    elif status_norm == "success":
        existing["last_success_run_id"] = run_id
        existing["last_success_at"] = now_iso
        existing["active_run_id"] = ""
    path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _latest_success_epoch_seconds(state_path: Path | None = None) -> float | None:
    state = _read_attribute_fill_state(state_path)
    parsed = _parse_iso_datetime(state.get("last_success_at"))
    if parsed is None:
        return None
    return parsed.timestamp()


def _read_checkpoint_rows_since_success(
    checkpoint_dir: Path,
    *,
    success_epoch_seconds: float | None,
) -> pl.DataFrame:
    if not checkpoint_dir.exists():
        return pl.DataFrame()
    frames: list[pl.DataFrame] = []
    for path in sorted(checkpoint_dir.glob("*.parquet")):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if success_epoch_seconds is not None and mtime <= success_epoch_seconds:
            continue
        try:
            frames.append(pl.read_parquet(path))
        except Exception:
            logging.warning("Skipping unreadable checkpoint chunk: %s", path)
    if not frames:
        return pl.DataFrame()
    merged = pl.concat(frames, how="diagonal_relaxed")
    return merged


def _parse_checkpoint_response_json(value: Any) -> object:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except ValueError:
        try:
            repaired = repair_json(text)
            return json.loads(repaired)
        except (TypeError, ValueError):
            return text


def _checkpoint_response_map(frame: object) -> dict[str, object]:
    if not isinstance(frame, pl.DataFrame):
        return {}
    if frame.is_empty():
        return {}
    columns, _ = get_schema_and_column_names(frame)
    if "request_key" not in columns or "response_json" not in columns:
        return {}
    response_map: dict[str, object] = {}
    rows = frame.select(["request_key", "response_json"]).iter_rows(named=True)
    for row in rows:
        request_key = str(row.get("request_key") or "").strip()
        if not request_key:
            continue
        response_map[request_key] = _parse_checkpoint_response_json(
            row.get("response_json")
        )
    return response_map


def _request_key(payload: Mapping[str, Any]) -> str:
    text = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _vision_request_key(
    *,
    group_info: Mapping[str, Any],
    category_key: str,
    source_retailer: str,
    source_parent_product_id: str,
    missing_attrs: Sequence[str],
) -> str:
    payload = {
        "group_info": dict(group_info),
        "category_key": category_key,
        "source_retailer": source_retailer,
        "source_parent_product_id": source_parent_product_id,
        "missing_attrs": sorted({str(attr).strip() for attr in missing_attrs if attr}),
    }
    return _request_key(payload)


def _web_request_key(
    *,
    group_info: Mapping[str, Any],
    category_key: str,
    source_retailer: str,
    source_parent_product_id: str,
    domains: Sequence[str],
    missing_parent_attrs: Sequence[str],
    variant_missing_map: Mapping[str, Sequence[str]],
) -> str:
    payload = {
        "group_info": dict(group_info),
        "category_key": category_key,
        "source_retailer": source_retailer,
        "source_parent_product_id": source_parent_product_id,
        "domains": sorted({str(item).strip() for item in domains if str(item).strip()}),
        "missing_parent_attrs": sorted(
            {str(item).strip() for item in missing_parent_attrs if str(item).strip()}
        ),
        "variant_missing_map": {
            str(key): sorted(
                {
                    str(attr).strip()
                    for attr in attrs
                    if isinstance(attr, str) and str(attr).strip()
                }
            )
            for key, attrs in sorted(variant_missing_map.items())
        },
    }
    return _request_key(payload)


def _clear_checkpoint_dir(checkpoint_dir: Path) -> int:
    if not checkpoint_dir.exists():
        return 0
    removed = 0
    for path in checkpoint_dir.glob("*.parquet"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            logging.warning("Failed to remove checkpoint chunk: %s", path)
    return removed


def _non_replayed_audit_rows(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df
    columns, _ = get_schema_and_column_names(df)
    if "replayed_from_checkpoint" not in columns:
        return df
    return df.filter(~pl.col("replayed_from_checkpoint").fill_null(False))


def _append_attribute_audit(records: Sequence[AttributeAuditRecord]) -> None:
    if not records:
        return
    pdp_store_path = enforce_default_pdp_store_path(DEFAULT_PDP_STORE_PATH)
    store = PDPStore(pdp_store_path)
    value_records: list[AttributeValueRecord] = []
    for record in records:
        source = str(record.source or record.decision_rule or "").strip()
        retailer = str(record.retailer or "").strip()
        row_type = str(record.row_type or "").strip()
        parent_id = str(record.parent_product_id or "").strip()
        attribute_id = str(record.attribute_id or "").strip()
        if (
            not source
            or not retailer
            or not row_type
            or not parent_id
            or not attribute_id
        ):
            continue
        value = None if record.value is None else str(record.value)
        value_records.append(
            AttributeValueRecord(
                retailer=retailer,
                row_type=row_type,
                parent_product_id=parent_id,
                variant_id=str(record.variant_id or "").strip(),
                category_key=str(record.category_key or "").strip(),
                attribute_id=attribute_id,
                attribute_label=None,
                value=value,
                oov_candidate=None,
                note="no_value" if value is None else None,
                source=source,
                updated_at=str(record.timestamp or ""),
            )
        )
    store.upsert_attribute_values(value_records)
    store.append_attribute_audit(records)


def _coerce_optional_float(value: object | None) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _build_resolution_context_maps(
    parents_df: pl.DataFrame,
    variants_df: pl.DataFrame,
) -> tuple[
    dict[tuple[str, str], dict[str, str]],
    dict[tuple[str, str], dict[str, str]],
]:
    parent_lookup: dict[tuple[str, str], dict[str, str]] = {}
    variant_lookup: dict[tuple[str, str], dict[str, str]] = {}

    if not parents_df.is_empty():
        parent_cols = [
            col
            for col in ("retailer", "parent_product_id", "canonical_id", "category_key")
            if col in parents_df.columns
        ]
        if {"retailer", "parent_product_id"}.issubset(set(parent_cols)):
            for row in parents_df.select(parent_cols).to_dicts():
                retailer = str(row.get("retailer") or "").strip()
                parent_id = str(row.get("parent_product_id") or "").strip()
                if not retailer or not parent_id:
                    continue
                parent_lookup[(retailer, parent_id)] = {
                    "canonical_id": str(row.get("canonical_id") or "").strip(),
                    "category_key": str(row.get("category_key") or "").strip(),
                }

    if not variants_df.is_empty():
        variant_cols = [
            col
            for col in (
                "retailer",
                "variant_id",
                "parent_product_id",
                "canonical_id",
                "category_key",
            )
            if col in variants_df.columns
        ]
        if {"retailer", "variant_id"}.issubset(set(variant_cols)):
            for row in variants_df.select(variant_cols).to_dicts():
                retailer = str(row.get("retailer") or "").strip()
                variant_id = str(row.get("variant_id") or "").strip()
                if not retailer or not variant_id:
                    continue
                variant_lookup[(retailer, variant_id)] = {
                    "parent_product_id": str(
                        row.get("parent_product_id") or ""
                    ).strip(),
                    "canonical_id": str(row.get("canonical_id") or "").strip(),
                    "category_key": str(row.get("category_key") or "").strip(),
                }

    return parent_lookup, variant_lookup


def _resolution_step_from_audit(record: AttributeAuditRecord) -> str:
    source = str(record.source or "").strip().lower()
    decision_rule = str(record.decision_rule or "").strip().lower()
    if source == "cross_retailer_fill" or decision_rule.startswith(
        "cross_retailer_fill"
    ):
        return "cross_retailer_fill"
    if source == "parent_propagation" or decision_rule.startswith("parent_propagation"):
        return "parent_propagation"
    if source == "vision" or decision_rule.startswith("vision"):
        return "vision"
    if source == "web" or decision_rule.startswith("web"):
        return "brand_web_search"
    if source == "llm" or decision_rule.startswith("llm"):
        return "llm_pdp_lookup"
    return "deterministic"


def _collect_resolution_history_rows(
    records: Sequence[AttributeAuditRecord],
    *,
    parents_df: pl.DataFrame,
    variants_df: pl.DataFrame,
    run_id: str,
) -> list[dict[str, Any]]:
    if not records:
        return []
    parent_lookup, variant_lookup = _build_resolution_context_maps(
        parents_df, variants_df
    )
    rows: list[dict[str, Any]] = []
    for record in records:
        retailer = str(record.retailer or "").strip()
        parent_id = str(record.parent_product_id or "").strip()
        variant_id = str(record.variant_id or "").strip()
        attr_id = str(record.attribute_id or "").strip()
        if not retailer or not parent_id or not attr_id:
            continue

        row_type = str(record.row_type or "").strip().lower()
        if row_type not in {"parent", "variant"}:
            row_type = "variant" if variant_id else "parent"

        context: Mapping[str, str] = {}
        if row_type == "variant" and variant_id:
            context = variant_lookup.get((retailer, variant_id), {})
            if not parent_id:
                parent_id = str(context.get("parent_product_id") or "").strip()
        if not context:
            context = parent_lookup.get((retailer, parent_id), {})

        evidence: Mapping[str, object] = {}
        raw_evidence = record.evidence_json
        if isinstance(raw_evidence, str) and raw_evidence.strip():
            try:
                parsed = json.loads(raw_evidence)
                if isinstance(parsed, Mapping):
                    evidence = parsed
            except json.JSONDecodeError:
                evidence = {}
        evidence_url_obj = evidence.get("evidence_url")
        evidence_url = None
        if isinstance(evidence_url_obj, str):
            cleaned_url = evidence_url_obj.strip()
            if cleaned_url:
                evidence_url = cleaned_url

        rows.append(
            {
                "run_id": run_id,
                "recorded_at": str(record.timestamp or ""),
                "step": _resolution_step_from_audit(record),
                "source": str(record.source or ""),
                "decision_rule": str(record.decision_rule or ""),
                "row_type": row_type,
                "retailer": retailer,
                "parent_product_id": parent_id,
                "variant_id": variant_id,
                "canonical_id": str(context.get("canonical_id") or ""),
                "category_key": str(
                    record.category_key or context.get("category_key") or ""
                ),
                "attribute_id": attr_id,
                "value": None if record.value is None else str(record.value),
                "confidence": _coerce_optional_float(evidence.get("confidence")),
                "evidence_url": evidence_url,
            }
        )
    return rows


def _resolution_row_key(
    row: Mapping[str, Any],
) -> tuple[str, str, str, str, str, str, str]:
    return (
        str(row.get("row_type") or "").strip().lower(),
        str(row.get("retailer") or "").strip(),
        str(row.get("parent_product_id") or "").strip(),
        str(row.get("variant_id") or "").strip(),
        str(row.get("canonical_id") or "").strip(),
        str(row.get("category_key") or "").strip(),
        str(row.get("attribute_id") or "").strip(),
    )


def _resolution_row_has_meaningful_value(row: Mapping[str, Any]) -> bool:
    return not _is_placeholder_value(row.get("value"))


def _load_resolution_keys(
    run_id: str | None = None,
) -> set[tuple[str, str, str, str, str, str, str]]:
    try:
        ledger = attribute_resolution_history.read_resolution_ledger()
    except TypeError:
        # Test doubles may not accept keyword arguments.
        ledger = attribute_resolution_history.read_resolution_ledger()
    if ledger.is_empty():
        return set()

    required_cols = {
        "run_id",
        "row_type",
        "retailer",
        "parent_product_id",
        "variant_id",
        "canonical_id",
        "category_key",
        "attribute_id",
        "value",
    }
    columns, _ = get_schema_and_column_names(ledger)
    if not required_cols.issubset(set(columns)):
        return set()

    run_id_text = str(run_id or "").strip()
    if run_id_text:
        ledger = ledger.filter(pl.col("run_id") == run_id_text)
        if ledger.is_empty():
            return set()

    rows = ledger.select(list(required_cols)).to_dicts()
    keys: set[tuple[str, str, str, str, str, str, str]] = set()
    for row in rows:
        if not _resolution_row_has_meaningful_value(row):
            continue
        key = _resolution_row_key(row)
        row_type, retailer, parent_id, variant_id, _, _, attr_id = key
        if row_type not in {"parent", "variant"}:
            continue
        if not retailer or not parent_id or not attr_id:
            continue
        if row_type == "variant" and not variant_id:
            continue
        keys.add(key)
    return keys


def _load_existing_resolution_run_keys(
    run_id: str,
) -> set[tuple[str, str, str, str, str, str, str]]:
    return _load_resolution_keys(run_id=run_id)


def _load_resolution_tracked_keys() -> set[tuple[str, str, str, str, str, str, str]]:
    return _load_resolution_keys(run_id=None)


def _collect_resolution_snapshot_rows_for_frame(
    *,
    df: pl.DataFrame,
    row_type: str,
    attribute_map: Mapping[str, str],
    run_id: str,
    recorded_at: str,
    skip_keys: set[tuple[str, str, str, str, str, str, str]],
    allowed_keys: set[tuple[str, str, str, str, str, str, str]] | None = None,
) -> list[dict[str, Any]]:
    if df.is_empty() or not attribute_map:
        return []

    if row_type == "parent":
        key_cols = ["retailer", "parent_product_id"]
    elif row_type == "variant":
        key_cols = ["retailer", "parent_product_id", "variant_id"]
    else:
        return []

    columns, _ = get_schema_and_column_names(df)
    column_set = set(columns)
    if any(col not in column_set for col in key_cols):
        return []

    allowed_attr_ids: set[str] | None = None
    if allowed_keys is not None:
        allowed_attr_ids = {
            attr_id
            for (
                row_type_key,
                retailer_key,
                parent_key,
                variant_key,
                _canonical_key,
                _category_key,
                attr_id,
            ) in allowed_keys
            if row_type_key == row_type
            and retailer_key
            and parent_key
            and (row_type != "variant" or variant_key)
            and attr_id
        }
        if not allowed_attr_ids:
            return []

        if row_type == "parent":
            allowed_entity_rows = [
                {
                    "retailer": retailer_key,
                    "parent_product_id": parent_key,
                }
                for (
                    row_type_key,
                    retailer_key,
                    parent_key,
                    _variant_key,
                    _canonical_key,
                    _category_key,
                    _attr_id,
                ) in allowed_keys
                if row_type_key == "parent" and retailer_key and parent_key
            ]
        else:
            allowed_entity_rows = [
                {
                    "retailer": retailer_key,
                    "parent_product_id": parent_key,
                    "variant_id": variant_key,
                }
                for (
                    row_type_key,
                    retailer_key,
                    parent_key,
                    variant_key,
                    _canonical_key,
                    _category_key,
                    _attr_id,
                ) in allowed_keys
                if row_type_key == "variant"
                and retailer_key
                and parent_key
                and variant_key
            ]
        if not allowed_entity_rows:
            return []
        entity_frame = pl.from_dicts(allowed_entity_rows, strict=False).unique(
            subset=key_cols
        )
        df = df.join(entity_frame, on=key_cols, how="inner")
        if df.is_empty():
            return []
        columns, _ = get_schema_and_column_names(df)
        column_set = set(columns)

    context_cols = [
        col for col in ("canonical_id", "category_key") if col in column_set
    ]
    column_to_attr: dict[str, str] = {}
    for attr_id, column_name in attribute_map.items():
        attr_id_text = str(attr_id or "").strip()
        if not attr_id_text:
            continue
        if allowed_attr_ids is not None and attr_id_text not in allowed_attr_ids:
            continue
        col = str(column_name or "").strip()
        if not col or col not in column_set or col in column_to_attr:
            continue
        column_to_attr[col] = attr_id_text
    if not column_to_attr:
        return []

    melted = df.select([*key_cols, *context_cols, *column_to_attr.keys()]).unpivot(
        index=[*key_cols, *context_cols],
        on=list(column_to_attr.keys()),
        variable_name="attribute_column",
        value_name="value",
    )
    if melted.is_empty():
        return []

    melted = melted.with_columns(
        pl.col("attribute_column")
        .replace(column_to_attr)
        .cast(pl.Utf8, strict=False)
        .fill_null("")
        .alias("attribute_id")
    ).filter(pl.col("attribute_id") != "")
    if melted.is_empty():
        return []

    selected_cols = [*key_cols, *context_cols, "attribute_id", "value"]
    rows: list[dict[str, Any]] = []
    for row in melted.select(selected_cols).to_dicts():
        value = row.get("value")
        if _is_placeholder_value(value):
            continue
        result = {
            "run_id": run_id,
            "recorded_at": recorded_at,
            "step": "run_snapshot",
            "source": "snapshot",
            "decision_rule": "snapshot_current_value",
            "row_type": row_type,
            "retailer": str(row.get("retailer") or "").strip(),
            "parent_product_id": str(row.get("parent_product_id") or "").strip(),
            "variant_id": (
                str(row.get("variant_id") or "").strip()
                if row_type == "variant"
                else ""
            ),
            "canonical_id": str(row.get("canonical_id") or "").strip(),
            "category_key": str(row.get("category_key") or "").strip(),
            "attribute_id": str(row.get("attribute_id") or "").strip(),
            "value": str(value),
            "confidence": None,
            "evidence_url": None,
        }
        key = _resolution_row_key(result)
        if key in skip_keys:
            continue
        row_type_key, retailer_key, parent_id_key, variant_id_key, _, _, attr_id_key = (
            key
        )
        if not retailer_key or not parent_id_key or not attr_id_key:
            continue
        if row_type_key == "variant" and not variant_id_key:
            continue
        if allowed_keys is not None and key not in allowed_keys:
            continue
        skip_keys.add(key)
        rows.append(result)
    return rows


def _collect_resolution_snapshot_rows(
    *,
    parents_df: pl.DataFrame,
    variants_df: pl.DataFrame,
    meta_by_id: Mapping[str, Mapping[str, object]],
    run_id: str,
    skip_keys: set[tuple[str, str, str, str, str, str, str]] | None = None,
    allowed_keys: set[tuple[str, str, str, str, str, str, str]] | None = None,
) -> list[dict[str, Any]]:
    run_id = str(run_id or "").strip()
    if not run_id:
        return []

    seen_keys = set(skip_keys or set())
    recorded_at = dt.datetime.now(dt.timezone.utc).isoformat()

    parent_product_map, _ = _taxonomy_attribute_column_maps_by_scope(
        parents_df, meta_by_id
    )
    variant_product_map, variant_scope_map = _taxonomy_attribute_column_maps_by_scope(
        variants_df, meta_by_id
    )
    variant_combined_map = dict(variant_product_map)
    variant_combined_map.update(variant_scope_map)

    rows: list[dict[str, Any]] = []
    rows.extend(
        _collect_resolution_snapshot_rows_for_frame(
            df=parents_df,
            row_type="parent",
            attribute_map=parent_product_map,
            run_id=run_id,
            recorded_at=recorded_at,
            skip_keys=seen_keys,
            allowed_keys=allowed_keys,
        )
    )
    rows.extend(
        _collect_resolution_snapshot_rows_for_frame(
            df=variants_df,
            row_type="variant",
            attribute_map=variant_combined_map,
            run_id=run_id,
            recorded_at=recorded_at,
            skip_keys=seen_keys,
            allowed_keys=allowed_keys,
        )
    )
    return rows


def _load_sure_resolution_consensus() -> pl.DataFrame:
    try:
        consensus = attribute_resolution_history.read_resolution_consensus()
    except TypeError:
        # Test doubles may not accept keyword arguments.
        consensus = attribute_resolution_history.read_resolution_consensus()
    if consensus.is_empty():
        return pl.DataFrame()
    return consensus.filter(
        (pl.col("certainty_class") == "sure")
        & pl.col("consensus_value").is_not_null()
        & (pl.col("consensus_value").cast(pl.Utf8).str.strip_chars() != "")
    )


def _load_no_value_query_suppression(
    *,
    step: str,
    min_runs: int = NO_VALUE_SUPPRESSION_RUNS,
) -> tuple[set[tuple[str, str, str]], set[tuple[str, str, str]]]:
    if min_runs <= 0:
        return set(), set()

    try:
        ledger = attribute_resolution_history.read_resolution_ledger()
    except TypeError:
        # Test doubles may not accept keyword arguments.
        ledger = attribute_resolution_history.read_resolution_ledger()
    if ledger.is_empty():
        return set(), set()

    required_columns = {
        "run_id",
        "recorded_at",
        "step",
        "row_type",
        "retailer",
        "parent_product_id",
        "variant_id",
        "attribute_id",
        "value",
    }
    if not required_columns.issubset(set(ledger.columns)):
        return set(), set()

    placeholders = ATTRIBUTE_PLACEHOLDER_VALUES + [""]
    prepared = (
        ledger.filter(pl.col("step") == step)
        .with_columns(
            [
                pl.col("run_id")
                .cast(pl.Utf8, strict=False)
                .fill_null("")
                .alias("run_id"),
                pl.col("recorded_at")
                .cast(pl.Utf8, strict=False)
                .fill_null("")
                .alias("recorded_at"),
                pl.col("row_type")
                .cast(pl.Utf8, strict=False)
                .fill_null("")
                .str.to_lowercase()
                .alias("row_type"),
                pl.col("retailer")
                .cast(pl.Utf8, strict=False)
                .fill_null("")
                .alias("retailer"),
                pl.col("parent_product_id")
                .cast(pl.Utf8, strict=False)
                .fill_null("")
                .alias("parent_product_id"),
                pl.col("variant_id")
                .cast(pl.Utf8, strict=False)
                .fill_null("")
                .alias("variant_id"),
                pl.col("attribute_id")
                .cast(pl.Utf8, strict=False)
                .fill_null("")
                .alias("attribute_id"),
                pl.col("value")
                .cast(pl.Utf8, strict=False)
                .str.strip_chars()
                .alias("_value_norm"),
            ]
        )
        .with_columns(
            (
                pl.col("_value_norm").is_not_null()
                & (pl.col("_value_norm") != "")
                & (~pl.col("_value_norm").str.to_lowercase().is_in(placeholders))
                & (
                    ~pl.col("_value_norm")
                    .str.to_lowercase()
                    .str.starts_with("not in taxonomy")
                )
            )
            .fill_null(False)
            .alias("_has_value")
        )
        .filter(
            (pl.col("run_id") != "")
            & (pl.col("retailer") != "")
            & (pl.col("attribute_id") != "")
            & pl.col("row_type").is_in(["parent", "variant"])
        )
    )
    if prepared.is_empty():
        return set(), set()

    key_cols = [
        "row_type",
        "retailer",
        "parent_product_id",
        "variant_id",
        "attribute_id",
    ]
    latest_per_run = prepared.group_by([*key_cols, "run_id"], maintain_order=True).agg(
        [
            pl.col("recorded_at").max().alias("recorded_at"),
            pl.col("_has_value").max().alias("has_value"),
        ]
    )
    if latest_per_run.is_empty():
        return set(), set()

    recent = (
        latest_per_run.sort(
            [*key_cols, "recorded_at"],
            descending=[False] * len(key_cols) + [True],
        )
        .group_by(key_cols, maintain_order=True)
        .agg(
            [
                pl.col("run_id").head(min_runs).alias("run_id"),
                pl.col("has_value").head(min_runs).alias("has_value"),
            ]
        )
        .explode(["run_id", "has_value"])
    )
    if recent.is_empty():
        return set(), set()

    suppressed = (
        recent.group_by(key_cols)
        .agg(
            [
                pl.col("run_id").n_unique().alias("recent_runs"),
                pl.col("has_value").cast(pl.Int64).sum().alias("recent_value_runs"),
            ]
        )
        .filter(
            (pl.col("recent_runs") >= min_runs) & (pl.col("recent_value_runs") == 0)
        )
    )
    if suppressed.is_empty():
        return set(), set()

    parent_rows = suppressed.filter(
        (pl.col("row_type") == "parent") & (pl.col("parent_product_id") != "")
    )
    variant_rows = suppressed.filter(
        (pl.col("row_type") == "variant") & (pl.col("variant_id") != "")
    )
    parent_blocked = {
        (
            str(row.get("retailer") or ""),
            str(row.get("parent_product_id") or ""),
            str(row.get("attribute_id") or ""),
        )
        for row in parent_rows.select(
            ["retailer", "parent_product_id", "attribute_id"]
        ).to_dicts()
    }
    variant_blocked = {
        (
            str(row.get("retailer") or ""),
            str(row.get("variant_id") or ""),
            str(row.get("attribute_id") or ""),
        )
        for row in variant_rows.select(
            ["retailer", "variant_id", "attribute_id"]
        ).to_dicts()
    }
    return parent_blocked, variant_blocked


def _load_sure_query_suppression() -> (
    tuple[set[tuple[str, str, str]], set[tuple[str, str, str]]]
):
    """Return query keys that should be skipped because consensus is already sure."""

    sure_consensus = _load_sure_resolution_consensus()
    if sure_consensus.is_empty():
        return set(), set()

    required_columns = {
        "row_type",
        "retailer",
        "parent_product_id",
        "variant_id",
        "attribute_id",
    }
    if not required_columns.issubset(set(sure_consensus.columns)):
        return set(), set()

    normalized = sure_consensus.with_columns(
        [
            pl.col("row_type")
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .str.to_lowercase()
            .alias("row_type"),
            pl.col("retailer")
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .alias("retailer"),
            pl.col("parent_product_id")
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .alias("parent_product_id"),
            pl.col("variant_id")
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .alias("variant_id"),
            pl.col("attribute_id")
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .alias("attribute_id"),
        ]
    ).filter(
        (pl.col("retailer") != "")
        & (pl.col("attribute_id") != "")
        & pl.col("row_type").is_in(["parent", "variant"])
    )
    if normalized.is_empty():
        return set(), set()

    parent_rows = normalized.filter(
        (pl.col("row_type") == "parent") & (pl.col("parent_product_id") != "")
    )
    variant_rows = normalized.filter(
        (pl.col("row_type") == "variant") & (pl.col("variant_id") != "")
    )
    parent_blocked = {
        (
            str(row.get("retailer") or ""),
            str(row.get("parent_product_id") or ""),
            str(row.get("attribute_id") or ""),
        )
        for row in parent_rows.select(
            ["retailer", "parent_product_id", "attribute_id"]
        ).to_dicts()
    }
    variant_blocked = {
        (
            str(row.get("retailer") or ""),
            str(row.get("variant_id") or ""),
            str(row.get("attribute_id") or ""),
        )
        for row in variant_rows.select(
            ["retailer", "variant_id", "attribute_id"]
        ).to_dicts()
    }
    return parent_blocked, variant_blocked


def _apply_sure_consensus_to_frame(
    df: pl.DataFrame,
    *,
    row_type: str,
    sure_consensus: pl.DataFrame,
    meta_by_id: Mapping[str, Mapping[str, object]],
) -> tuple[pl.DataFrame, int]:
    if df.is_empty() or sure_consensus.is_empty():
        return df, 0

    if row_type == "parent":
        key_cols = ["retailer", "parent_product_id"]
    elif row_type == "variant":
        key_cols = ["retailer", "parent_product_id", "variant_id"]
    else:
        return df, 0

    if any(col not in df.columns for col in key_cols):
        return df, 0

    consensus_slice = sure_consensus.filter(pl.col("row_type") == row_type)
    if consensus_slice.is_empty():
        return df, 0

    columns, _ = get_schema_and_column_names(df)
    aliases = build_column_aliases(columns)
    normalized_column_lookup: dict[str, str] = {}
    for col in columns:
        normalized_column_lookup.setdefault(_normalize_key(col), col)

    def _resolve_column(attribute_id: str) -> str | None:
        if attribute_id in columns:
            return attribute_id
        normalized = _normalize_key(attribute_id)
        if normalized and normalized in normalized_column_lookup:
            return normalized_column_lookup[normalized]
        meta = meta_by_id.get(attribute_id)
        if not meta:
            return None
        label = str(meta["label"] if "label" in meta else attribute_id).strip()
        resolved = resolve_attribute_column(attribute_id, label, aliases)
        if resolved and resolved in columns:
            return resolved
        return None

    updates: list[dict[str, str]] = []
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
    merged_columns, _ = get_schema_and_column_names(merged)
    merged_column_set = set(merged_columns)
    for key in update_cols:
        sure_col = f"{key}__sure"
        if sure_col not in merged_column_set or key not in merged_column_set:
            continue
        merged = merged.with_columns(
            pl.when(_placeholder_expr(key) & pl.col(sure_col).is_not_null())
            .then(pl.col(sure_col))
            .otherwise(pl.col(key))
            .alias(key)
        ).drop(sure_col)
        merged_column_set.discard(sure_col)

    return merged, len(updates)


def _apply_sure_consensus_values(
    parents_df: pl.DataFrame,
    variants_df: pl.DataFrame,
    *,
    meta_by_id: Mapping[str, Mapping[str, object]],
) -> tuple[pl.DataFrame, pl.DataFrame, int, int]:
    sure_consensus = _load_sure_resolution_consensus()
    if sure_consensus.is_empty():
        return parents_df, variants_df, 0, 0

    parents_df, parent_updates = _apply_sure_consensus_to_frame(
        parents_df,
        row_type="parent",
        sure_consensus=sure_consensus,
        meta_by_id=meta_by_id,
    )
    variants_df, variant_updates = _apply_sure_consensus_to_frame(
        variants_df,
        row_type="variant",
        sure_consensus=sure_consensus,
        meta_by_id=meta_by_id,
    )
    return parents_df, variants_df, parent_updates, variant_updates


def _collect_variant_fill_audit(
    before_df: pl.DataFrame,
    after_df: pl.DataFrame,
    attribute_columns: Sequence[str],
    *,
    decision_rule: str,
    evidence: dict[str, Any] | None = None,
) -> list[AttributeAuditRecord]:
    if before_df.is_empty() or after_df.is_empty() or not attribute_columns:
        return []
    keys = [
        col
        for col in ("retailer", "variant_id", "parent_product_id")
        if col in before_df.columns and col in after_df.columns
    ]
    if not keys:
        return []
    cols = [
        col
        for col in attribute_columns
        if col in before_df.columns and col in after_df.columns
    ]
    if not cols:
        return []
    joined = before_df.select([*keys, *cols]).join(
        after_df.select([*keys, *cols]), on=keys, how="inner", suffix="__after"
    )
    if joined.is_empty():
        return []
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    evidence_json = json.dumps(evidence) if evidence else None
    records: list[AttributeAuditRecord] = []
    for attr in cols:
        after_col = f"{attr}__after"
        if after_col not in joined.columns:
            continue
        changes = joined.filter(_placeholder_expr(attr) & ~_placeholder_expr(after_col))
        if changes.is_empty():
            continue
        for row in changes.select([*keys, after_col]).to_dicts():
            records.append(
                AttributeAuditRecord(
                    timestamp=timestamp,
                    source=decision_rule,
                    row_type="variant",
                    retailer=str(row.get("retailer") or ""),
                    parent_product_id=str(row.get("parent_product_id") or ""),
                    variant_id=str(row.get("variant_id") or ""),
                    attribute_id=attr,
                    value=str(row.get(after_col) or ""),
                    decision_rule=decision_rule,
                    evidence_json=evidence_json,
                    category_key=None,
                )
            )
    return records


def _collect_parent_fill_audit(
    before_df: pl.DataFrame,
    after_df: pl.DataFrame,
    attribute_columns: Sequence[str],
    *,
    decision_rule: str,
    evidence: dict[str, Any] | None = None,
) -> list[AttributeAuditRecord]:
    if before_df.is_empty() or after_df.is_empty() or not attribute_columns:
        return []
    keys = [
        col
        for col in ("retailer", "parent_product_id")
        if col in before_df.columns and col in after_df.columns
    ]
    if not keys:
        return []
    cols = [
        col
        for col in attribute_columns
        if col in before_df.columns and col in after_df.columns
    ]
    if not cols:
        return []
    joined = before_df.select([*keys, *cols]).join(
        after_df.select([*keys, *cols]), on=keys, how="inner", suffix="__after"
    )
    if joined.is_empty():
        return []
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    evidence_json = json.dumps(evidence) if evidence else None
    records: list[AttributeAuditRecord] = []
    for attr in cols:
        after_col = f"{attr}__after"
        if after_col not in joined.columns:
            continue
        changes = joined.filter(_placeholder_expr(attr) & ~_placeholder_expr(after_col))
        if changes.is_empty():
            continue
        for row in changes.select([*keys, after_col]).to_dicts():
            records.append(
                AttributeAuditRecord(
                    timestamp=timestamp,
                    source=decision_rule,
                    row_type="parent",
                    retailer=str(row.get("retailer") or ""),
                    parent_product_id=str(row.get("parent_product_id") or ""),
                    variant_id="",
                    attribute_id=attr,
                    value=str(row.get(after_col) or ""),
                    decision_rule=decision_rule,
                    evidence_json=evidence_json,
                    category_key=None,
                )
            )
    return records


def _collect_vision_audit(audit_df: pl.DataFrame) -> list[AttributeAuditRecord]:
    if audit_df.is_empty():
        return []
    records: list[AttributeAuditRecord] = []
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    for row in audit_df.to_dicts():
        filled_raw = row.get("filled_attributes") or "{}"
        try:
            filled = json.loads(filled_raw) if isinstance(filled_raw, str) else {}
        except json.JSONDecodeError:
            filled = {}
        if not isinstance(filled, dict):
            filled = {}
        requested = [
            item.strip()
            for item in str(row.get("requested_attributes") or "").split(",")
            if item.strip()
        ]
        if not requested:
            requested = [
                str(attr_id).strip()
                for attr_id in filled.keys()
                if str(attr_id).strip()
            ]
        category_key = str(row.get("category_key") or "") or None
        retailer = str(row.get("source_retailer") or "")
        parent_product_id = str(row.get("source_parent_product_id") or "")
        for attr_id in requested:
            payload = filled.get(attr_id)
            value = payload.get("value") if isinstance(payload, dict) else None
            confidence = (
                payload.get("confidence") if isinstance(payload, dict) else None
            )
            evidence = {
                "confidence": confidence,
                "hero_image_url": row.get("hero_image_url"),
                "image_source": row.get("image_source"),
                "image_path": row.get("image_path"),
            }
            records.append(
                AttributeAuditRecord(
                    timestamp=timestamp,
                    source="vision",
                    row_type="parent",
                    retailer=retailer,
                    parent_product_id=parent_product_id,
                    variant_id="",
                    attribute_id=str(attr_id),
                    value=None if value is None else str(value),
                    decision_rule=(
                        "vision_confident" if value is not None else "vision_no_value"
                    ),
                    evidence_json=json.dumps(evidence),
                    category_key=category_key,
                )
            )
    return records


def _collect_web_audit(audit_df: pl.DataFrame) -> list[AttributeAuditRecord]:
    if audit_df.is_empty():
        return []
    records: list[AttributeAuditRecord] = []
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    for row in audit_df.to_dicts():
        cat_key = str(row.get("category_key") or "") or None
        source_retailer = str(row.get("source_retailer") or "")
        source_parent_product_id = str(row.get("source_parent_product_id") or "")
        parent_raw = row.get("filled_parent_attributes") or "{}"
        variant_raw = row.get("filled_variant_attributes") or "{}"
        requested_parent_raw = row.get("requested_parent_attributes") or ""
        requested_variant_raw = row.get("requested_variant_attributes") or "{}"
        try:
            parent_filled = (
                json.loads(parent_raw) if isinstance(parent_raw, str) else {}
            )
        except json.JSONDecodeError:
            parent_filled = {}
        if not isinstance(parent_filled, dict):
            parent_filled = {}
        requested_parent_attrs = [
            item.strip()
            for item in str(requested_parent_raw).split(",")
            if item.strip()
        ]
        if not requested_parent_attrs:
            requested_parent_attrs = [
                str(attr_id).strip()
                for attr_id in parent_filled.keys()
                if str(attr_id).strip()
            ]
        for attr_id in requested_parent_attrs:
            payload = parent_filled.get(attr_id)
            value = payload.get("value") if isinstance(payload, dict) else None
            evidence = {
                "confidence": (
                    payload.get("confidence") if isinstance(payload, dict) else None
                ),
                "evidence_url": (
                    payload.get("evidence_url") if isinstance(payload, dict) else None
                ),
            }
            records.append(
                AttributeAuditRecord(
                    timestamp=timestamp,
                    source="web",
                    row_type="parent",
                    retailer=source_retailer,
                    parent_product_id=source_parent_product_id,
                    variant_id="",
                    attribute_id=str(attr_id),
                    value=None if value is None else str(value),
                    decision_rule=(
                        "web_confident" if value is not None else "web_no_value"
                    ),
                    evidence_json=json.dumps(evidence),
                    category_key=cat_key,
                )
            )

        try:
            variant_filled = (
                json.loads(variant_raw) if isinstance(variant_raw, str) else {}
            )
        except json.JSONDecodeError:
            variant_filled = {}
        if not isinstance(variant_filled, dict):
            variant_filled = {}
        try:
            requested_variant_map = (
                json.loads(requested_variant_raw)
                if isinstance(requested_variant_raw, str)
                else {}
            )
        except json.JSONDecodeError:
            requested_variant_map = {}
        if not isinstance(requested_variant_map, dict):
            requested_variant_map = {}
        if not requested_variant_map:
            requested_variant_map = {
                str(variant_key): [
                    str(attr_id).strip()
                    for attr_id in attrs.keys()
                    if isinstance(attrs, dict) and str(attr_id).strip()
                ]
                for variant_key, attrs in variant_filled.items()
                if isinstance(variant_key, str) and isinstance(attrs, dict)
            }

        for variant_key, requested_attrs_raw in requested_variant_map.items():
            if not isinstance(variant_key, str):
                continue
            if not isinstance(requested_attrs_raw, list):
                continue
            retailer = source_retailer
            variant_id = variant_key
            if ":" in variant_key:
                retailer_part, variant_part = variant_key.split(":", 1)
                retailer = retailer_part.strip() or source_retailer
                variant_id = variant_part.strip()
            variant_id = str(variant_id or "").strip()
            if not variant_id:
                continue
            attrs = variant_filled.get(variant_key)
            attrs_map = attrs if isinstance(attrs, dict) else {}
            requested_attrs = [
                str(attr_id).strip()
                for attr_id in requested_attrs_raw
                if str(attr_id).strip()
            ]
            for attr_id in requested_attrs:
                payload = attrs_map.get(attr_id)
                value = payload.get("value") if isinstance(payload, dict) else None
                evidence = {
                    "confidence": (
                        payload.get("confidence") if isinstance(payload, dict) else None
                    ),
                    "evidence_url": (
                        payload.get("evidence_url")
                        if isinstance(payload, dict)
                        else None
                    ),
                }
                records.append(
                    AttributeAuditRecord(
                        timestamp=timestamp,
                        source="web",
                        row_type="variant",
                        retailer=retailer,
                        parent_product_id=source_parent_product_id,
                        variant_id=variant_id,
                        attribute_id=str(attr_id),
                        value=None if value is None else str(value),
                        decision_rule=(
                            "web_confident" if value is not None else "web_no_value"
                        ),
                        evidence_json=json.dumps(evidence),
                        category_key=cat_key,
                    )
                )
    return records


def _load_brand_aliases(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logging.warning("Failed to load brand aliases from %s", path)
        return {}
    if not isinstance(data, dict):
        return {}
    aliases: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, str):
            aliases[key.strip().lower()] = value.strip()
    return aliases


def _normalize_domains(domains: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for raw in domains:
        if not raw:
            continue
        text = str(raw).strip()
        if not text:
            continue
        candidate = text if "://" in text else f"https://{text}"
        parsed = urlparse(candidate)
        host = parsed.netloc or parsed.path
        host = host.strip().lstrip("/")
        if host:
            normalized.append(host.lower())
    seen: set[str] = set()
    unique: list[str] = []
    for host in normalized:
        if host not in seen:
            seen.add(host)
            unique.append(host)
    return unique


def _normalize_brand_lookup_key(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    ascii_text = text.encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in ascii_text.lower() if ch.isalnum())


def _taxonomy_attribute_meta_by_id(
    taxonomy: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    meta_by_id: dict[str, Mapping[str, object]] = {}
    for cat in taxonomy.get("categories", []) or []:
        if not isinstance(cat, Mapping):
            continue
        for attr in cat.get("attributes", []) or []:
            if not isinstance(attr, Mapping):
                continue
            attr_id = str(attr.get("id") or "").strip()
            if not attr_id:
                continue
            meta_by_id.setdefault(attr_id, attr)
    return meta_by_id


def _taxonomy_attribute_columns_by_scope(
    df: pl.DataFrame,
    meta_by_id: Mapping[str, Mapping[str, object]],
) -> tuple[list[str], list[str]]:
    columns, _ = get_schema_and_column_names(df)
    if not columns:
        return [], []
    aliases = build_column_aliases(columns)

    product_scope: list[str] = []
    variant_scope: list[str] = []
    seen: set[str] = set()
    for attr_id, meta in meta_by_id.items():
        label = str(meta.get("label") or attr_id).strip()
        scope = str(meta.get("scope") or "").strip().lower()
        column_name = resolve_attribute_column(attr_id, label, aliases)
        if not column_name or column_name not in columns or column_name in seen:
            continue
        seen.add(column_name)
        if scope == "variant":
            variant_scope.append(column_name)
        elif scope == "product":
            product_scope.append(column_name)
    return product_scope, variant_scope


def _taxonomy_attribute_column_maps_by_scope(
    df: pl.DataFrame,
    meta_by_id: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, str], dict[str, str]]:
    columns, _ = get_schema_and_column_names(df)
    if not columns:
        return {}, {}
    aliases = build_column_aliases(columns)

    product_scope: dict[str, str] = {}
    variant_scope: dict[str, str] = {}
    seen: set[str] = set()
    for attr_id, meta in meta_by_id.items():
        label = str(meta.get("label") or attr_id).strip()
        scope = str(meta.get("scope") or "").strip().lower()
        column_name = resolve_attribute_column(attr_id, label, aliases)
        if not column_name or column_name not in columns or column_name in seen:
            continue
        seen.add(column_name)
        if scope == "variant":
            variant_scope[attr_id] = column_name
        elif scope == "product":
            product_scope[attr_id] = column_name
    return product_scope, variant_scope


def _taxonomy_variant_columns_any_category(
    df: pl.DataFrame,
    taxonomy: Mapping[str, object],
) -> list[str]:
    """Resolve variant-scoped attribute columns using all category definitions.

    Some attribute ids appear with different scopes across categories (for
    example ``finish`` can be product-scoped in one category and variant-scoped
    in another). For variant cross-retailer fill we treat an attribute column as
    eligible when *any* taxonomy category marks that attribute as ``variant``.
    """
    columns, _ = get_schema_and_column_names(df)
    if not columns:
        return []
    aliases = build_column_aliases(columns)
    variant_columns: set[str] = set()
    for category in taxonomy.get("categories", []) or []:
        if not isinstance(category, Mapping):
            continue
        for attr in category.get("attributes", []) or []:
            if not isinstance(attr, Mapping):
                continue
            scope = str(attr.get("scope") or "").strip().lower()
            if scope != "variant":
                continue
            attr_id = str(attr.get("id") or "").strip()
            if not attr_id:
                continue
            label = str(attr.get("label") or attr_id).strip()
            column_name = resolve_attribute_column(attr_id, label, aliases)
            if column_name and column_name in columns:
                variant_columns.add(column_name)
    return sorted(variant_columns)


def _normalize_key(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "_")


def _leaf_labels(nodes: Sequence[Mapping[str, object]] | None) -> list[str]:
    labels: list[str] = []
    if not nodes:
        return labels
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        children = node.get("children")
        if isinstance(children, list) and children:
            labels.extend(_leaf_labels(children))
            continue
        label = node.get("label")
        if label:
            labels.append(str(label).strip().lower())
    return labels


def _allowed_image_values(nodes: Sequence[Mapping[str, object]] | None) -> list[str]:
    placeholders = set(ATTRIBUTE_PLACEHOLDER_VALUES)
    values: list[str] = []
    for label in _leaf_labels(nodes):
        normalized = label.strip().casefold()
        if not normalized:
            continue
        if normalized in placeholders:
            continue
        if normalized.startswith("not in taxonomy"):
            continue
        values.append(label)
    return sorted(set(values))


def _build_image_attribute_meta(
    taxonomy: Mapping[str, object],
) -> dict[str, dict[str, dict[str, object]]]:
    """Return per-category image attribute metadata for parent-only fills."""
    meta: dict[str, dict[str, dict[str, object]]] = {}
    for category in taxonomy.get("categories", []) or []:
        if not isinstance(category, Mapping):
            continue
        allowlist_raw = category.get("image_allowlist", [])
        if not isinstance(allowlist_raw, list):
            continue
        allowlist = {
            str(item).strip()
            for item in allowlist_raw
            if isinstance(item, (str, int, float)) and str(item).strip()
        }
        if not allowlist:
            continue
        attr_meta: dict[str, dict[str, object]] = {}
        for attr in category.get("attributes", []) or []:
            if not isinstance(attr, Mapping):
                continue
            attr_id = str(attr.get("id") or "").strip()
            if not attr_id or attr_id not in allowlist:
                continue
            scope = str(attr.get("scope") or "").strip().lower()
            if scope and scope != "product":
                logging.info(
                    "Skipping image attribute %s for category %s (scope=%s).",
                    attr_id,
                    category.get("id"),
                    scope,
                )
                continue
            allowed_values_raw = _allowed_image_values(attr.get("nodes"))
            if not allowed_values_raw:
                continue
            allowed_values = sorted(
                {
                    str(value).strip().lower()
                    for value in allowed_values_raw
                    if isinstance(value, (str, int, float)) and str(value).strip()
                }
            )
            if not allowed_values:
                continue
            attr_meta[attr_id] = {
                "label": str(attr.get("label") or attr_id).strip(),
                "allowed_values": allowed_values,
            }
        if not attr_meta:
            continue
        keys = set()
        cid = _normalize_key(category.get("id"))
        clabel = _normalize_key(category.get("label"))
        if cid:
            keys.add(cid)
        if clabel:
            keys.add(clabel)
        for key in keys:
            if key:
                meta[key] = attr_meta
    return meta


def _build_web_attribute_meta(
    taxonomy: Mapping[str, object],
    *,
    parent_columns: Sequence[str],
    variant_columns: Sequence[str],
    parent_aliases: Mapping[str, str],
    variant_aliases: Mapping[str, str],
) -> dict[str, dict[str, dict[str, object]]]:
    """Return per-category web attribute metadata for parent + variant fills."""
    parent_cols = set(parent_columns)
    variant_cols = set(variant_columns)
    meta: dict[str, dict[str, dict[str, object]]] = {}
    for category in taxonomy.get("categories", []) or []:
        if not isinstance(category, Mapping):
            continue
        attr_meta: dict[str, dict[str, object]] = {}
        for attr in category.get("attributes", []) or []:
            if not isinstance(attr, Mapping):
                continue
            attr_id = str(attr.get("id") or "").strip()
            if not attr_id:
                continue
            label = str(attr.get("label") or attr_id).strip()
            scope = str(attr.get("scope") or "").strip().lower() or "product"
            if scope not in {"product", "variant"}:
                continue
            allowed_values_raw = _allowed_image_values(attr.get("nodes"))
            if not allowed_values_raw:
                continue
            allowed_values = sorted(
                {
                    str(value).strip().lower()
                    for value in allowed_values_raw
                    if isinstance(value, (str, int, float)) and str(value).strip()
                }
            )
            if not allowed_values:
                continue
            aliases = parent_aliases if scope == "product" else variant_aliases
            col = resolve_attribute_column(attr_id, label, aliases)
            if not col:
                continue
            if scope == "product" and col not in parent_cols:
                continue
            if scope == "variant" and col not in variant_cols:
                continue
            attr_meta[attr_id] = {
                "label": label,
                "allowed_values": allowed_values,
                "scope": scope,
                "column": col,
            }
        if not attr_meta:
            continue
        keys = set()
        cid = _normalize_key(category.get("id"))
        clabel = _normalize_key(category.get("label"))
        if cid:
            keys.add(cid)
        if clabel:
            keys.add(clabel)
        for key in keys:
            if key:
                meta[key] = attr_meta
    return meta


def _variant_display_name(row: Mapping[str, Any]) -> str:
    for key in ("variant_description", "shade_name_normalized", "shade_name_raw"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _build_web_prompt(
    *,
    category_label: str | None,
    brand: str | None,
    product_name: str | None,
    domains: Sequence[str],
    parent_attrs: Mapping[str, Mapping[str, object]],
    variant_attrs: Mapping[str, Mapping[str, object]],
    variants: Sequence[Mapping[str, Any]],
) -> str:
    parent_allowed = {
        attr_id: meta.get("allowed_values", [])
        for attr_id, meta in parent_attrs.items()
    }
    variant_allowed = {
        attr_id: meta.get("allowed_values", [])
        for attr_id, meta in variant_attrs.items()
    }
    allowed_json = json.dumps(
        {"parent": parent_allowed, "variant": variant_allowed}, ensure_ascii=False
    )
    variants_json = json.dumps(list(variants), ensure_ascii=False)
    domain_txt = ", ".join(domains)
    product_bits = [str(item).strip() for item in (brand, product_name) if item]
    product = " ".join(product_bits).strip()
    prompt_lines = [
        "Find the official brand product page using web search.",
        "Search ONLY within the allowed domains.",
        "Return JSON only.",
        "If you are not confident you found the exact product, return null values.",
        f"Allowed domains: {domain_txt or '(none)'}",
        f"Category: {category_label or '(unknown)'}",
        f"Product: {product or '(unknown)'}",
        "Variants (JSON):```json\n" + variants_json + "\n```",
        "Allowed values (json):```json\n" + allowed_json + "\n```",
        (
            "Return JSON with this shape:\n"
            "{\n"
            '  "parent_attributes": { "<attr_id>": {"value": <value|null>, "confidence": <0-1>, "evidence_url": <url|null>} },\n'
            '  "variants": { "<variant_key>": { "<attr_id>": {"value": <value|null>, "confidence": <0-1>, "evidence_url": <url|null>} } }\n'
            "}\n"
            "Always include an evidence_url from the allowed domains when returning a value; "
            "if you cannot provide evidence_url, return null for that attribute.\n"
            f"Only output values when confidence >= {WEB_CONFIDENCE_THRESHOLD:.2f} and the value is in the allowed list (lowercase)."
        ),
    ]
    return "\n".join(prompt_lines)


def _resolve_image_category_key(
    group_df: pl.DataFrame,
    *,
    image_meta: Mapping[str, Mapping[str, object]],
) -> str:
    columns, _ = get_schema_and_column_names(group_df)
    candidates = ("category_key", "category_id", "category_label", "category")
    for col in candidates:
        if col not in columns:
            continue
        raw = str(group_df.get_column(col)[0] or "").strip()
        if not raw:
            continue
        raw_lc = raw.lower()
        if raw_lc in _CATEGORY_NORMALIZATION_MAP:
            raw_lc = _CATEGORY_NORMALIZATION_MAP[raw_lc]
        norm = _normalize_key(raw_lc)
        if norm in image_meta:
            return norm
    return ""


def _normalize_coverage_threshold(value: float) -> float:
    try:
        threshold = float(value)
    except (TypeError, ValueError):
        return 0.0
    if threshold < 0.0:
        return 0.0
    if threshold > 1.0:
        return 1.0
    return threshold


def _update_attribute_coverage_counts(
    counts: MutableMapping[tuple[str, str], list[int]],
    *,
    category_key: str,
    attribute_id: str,
    has_value: bool,
) -> None:
    key = (category_key, attribute_id)
    bucket = counts.get(key)
    if bucket is None:
        bucket = [0, 0]
        counts[key] = bucket
    if has_value:
        bucket[0] += 1
    bucket[1] += 1


def _eligible_attributes_by_coverage(
    counts: Mapping[tuple[str, str], Sequence[int]],
    *,
    min_coverage: float,
) -> dict[str, set[str]]:
    threshold = _normalize_coverage_threshold(min_coverage)
    if threshold <= 0.0:
        return {}
    eligible: dict[str, set[str]] = {}
    for (category_key, attribute_id), values in counts.items():
        if len(values) < 2:
            continue
        filled = int(values[0])
        total = int(values[1])
        if total <= 0:
            continue
        if (filled / total) >= threshold:
            eligible.setdefault(category_key, set()).add(attribute_id)
    return eligible


def _is_placeholder_value(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    lowered = text.casefold()
    if lowered in ATTRIBUTE_PLACEHOLDER_VALUES:
        return True
    return lowered.startswith("not in taxonomy")


def _is_valid_image_url(url: str | None) -> bool:
    if not url:
        return False
    if _is_placeholder_value(url):
        return False
    text = str(url).strip()
    if not text:
        return False
    lowered = text.lower()
    if "undefined" in lowered:
        return False
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return False
    return True


def _normalize_evidence_url(url: str | None, domains: Sequence[str]) -> str | None:
    if not url:
        return None
    text = str(url).strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.netloc or "").strip().lower()
    if not host:
        return None
    for domain in domains:
        dom = str(domain).strip().lower()
        if not dom:
            continue
        if host == dom or host.endswith(f".{dom}"):
            return text
    return None


def _normalize_llm_attribute_value(value_raw: Any) -> str | None:
    """Normalize an LLM attribute value to a lower-cased taxonomy id."""
    if isinstance(value_raw, str):
        value_norm = value_raw.strip().lower()
        return value_norm or None
    if isinstance(value_raw, Sequence) and not isinstance(
        value_raw, (str, bytes, bytearray)
    ):
        candidates = [
            str(item).strip().lower()
            for item in value_raw
            if isinstance(item, str) and str(item).strip()
        ]
        if len(candidates) == 1:
            return candidates[0]
    return None


def _parse_web_response_object(raw_text: str) -> Mapping[str, object] | None:
    text = str(raw_text or "").strip()
    if not text:
        return None
    if "```" in text:
        text = (
            text.replace("```json", "```")
            .replace("```JSON", "```")
            .replace("```", "")
            .strip()
        )
    candidates = [text]
    fragment = text.strip().strip(",")
    if fragment and not (fragment.startswith("{") and fragment.endswith("}")):
        if '"parent_attributes"' in fragment or '"variants"' in fragment:
            candidates.append("{" + fragment + "}")
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            try:
                repaired = repair_json(candidate)
                parsed = json.loads(repaired)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        if isinstance(parsed, Mapping):
            return parsed
    return None


def _coerce_web_fill_response(resp: object) -> Mapping[str, object]:
    if isinstance(resp, Mapping):
        if isinstance(resp.get("parent_attributes"), Mapping) or isinstance(
            resp.get("variants"), Mapping
        ):
            return resp
        raw_response = resp.get("raw_response")
        if isinstance(raw_response, str):
            parsed = _parse_web_response_object(raw_response)
            if parsed is not None:
                return parsed
        raw = resp.get("raw")
        if isinstance(raw, str):
            parsed = _parse_web_response_object(raw)
            if parsed is not None:
                return parsed
    if isinstance(resp, str):
        parsed = _parse_web_response_object(resp)
        if parsed is not None:
            return parsed
    return {}


def _normalized_image_mime_type(value: str | None) -> str | None:
    mime = str(value or "").split(";", 1)[0].strip().lower()
    if mime == "image/jpg":
        return "image/jpeg"
    return mime or None


def _data_url_from_image_bytes(payload: bytes, mime: str) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _pil_format_to_supported_mime_type(image_format: str | None) -> str | None:
    format_key = str(image_format or "").strip().upper()
    return {
        "JPEG": "image/jpeg",
        "JPG": "image/jpeg",
        "PNG": "image/png",
        "GIF": "image/gif",
        "WEBP": "image/webp",
    }.get(format_key)


def _convert_image_bytes_to_png_data_url(payload: bytes, *, source: str) -> str | None:
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        logging.warning("Pillow is unavailable; cannot convert image at %s.", source)
        return None
    try:
        import pillow_avif  # noqa: F401
    except ImportError:
        pass

    try:
        with Image.open(BytesIO(payload)) as img:
            converted = img.copy()
    except UnidentifiedImageError as exc:
        logging.warning(
            "Failed to decode image at %s for VLM conversion: %s", source, exc
        )
        return None
    except OSError as exc:
        logging.warning(
            "Failed to decode image at %s for VLM conversion: %s", source, exc
        )
        return None

    if converted.mode not in {"RGB", "RGBA"}:
        converted = converted.convert("RGBA" if "A" in converted.getbands() else "RGB")
    out = BytesIO()
    try:
        converted.save(out, format="PNG")
    except OSError as exc:
        logging.warning("Failed to convert image at %s to PNG for VLM: %s", source, exc)
        return None
    return _data_url_from_image_bytes(out.getvalue(), "image/png")


def _image_bytes_to_vlm_data_url(
    payload: bytes,
    *,
    source: str,
    declared_mime: str | None = None,
) -> str | None:
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        if declared_mime in VISION_SUPPORTED_IMAGE_MIME_TYPES:
            return _data_url_from_image_bytes(payload, declared_mime)
        logging.warning("Pillow is unavailable; cannot verify image at %s.", source)
        return None
    try:
        import pillow_avif  # noqa: F401
    except ImportError:
        pass

    try:
        with Image.open(BytesIO(payload)) as img:
            detected_mime = _pil_format_to_supported_mime_type(img.format)
            if detected_mime in VISION_SUPPORTED_IMAGE_MIME_TYPES:
                return _data_url_from_image_bytes(payload, detected_mime)
    except UnidentifiedImageError as exc:
        logging.warning("Failed to decode image at %s for VLM: %s", source, exc)
        return None
    except OSError as exc:
        logging.warning("Failed to decode image at %s for VLM: %s", source, exc)
        return None

    return _convert_image_bytes_to_png_data_url(payload, source=source)


def _force_supported_image_format_url(url: str) -> str:
    parsed = urlparse(url)
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() != "fmt"
    ]
    query_items.append(("fmt", "jpg"))
    return urlunparse(parsed._replace(query=urlencode(query_items)))


def _vision_image_url_candidates(url: str | None) -> list[str]:
    text = str(url or "").strip()
    if not _is_valid_image_url(text):
        return []
    candidates = [text, _force_supported_image_format_url(text)]
    seen: set[str] = set()
    out: list[str] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        out.append(candidate)
    return out


def _download_image_data_url(url: str | None) -> str | None:
    for candidate_url in _vision_image_url_candidates(url):
        request = Request(
            candidate_url,
            headers={
                "Accept": "image/jpeg,image/png,image/webp,image/gif,*/*;q=0.5",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36"
                ),
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read(VISION_IMAGE_DOWNLOAD_LIMIT_BYTES + 1)
                content_type = _normalized_image_mime_type(
                    response.headers.get_content_type()
                    if hasattr(response.headers, "get_content_type")
                    else response.headers.get("Content-Type")
                )
        except OSError as exc:
            logging.warning(
                "Failed to download image for VLM conversion from %s: %s",
                candidate_url,
                exc,
            )
            continue

        if len(payload) > VISION_IMAGE_DOWNLOAD_LIMIT_BYTES:
            logging.warning(
                "Downloaded image exceeds VLM conversion limit from %s.",
                candidate_url,
            )
            continue

        data_url = _image_bytes_to_vlm_data_url(
            payload,
            source=candidate_url,
            declared_mime=content_type,
        )
        if data_url:
            return data_url
    return None


def _image_path_to_data_url(
    path: Path, *, fallback_url: str | None = None
) -> str | None:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        logging.warning("Failed to read image at %s: %s", path, exc)
        return None

    mime, _ = mimetypes.guess_type(path.name)
    normalized_mime = _normalized_image_mime_type(mime)
    data_url = _image_bytes_to_vlm_data_url(
        payload,
        source=str(path),
        declared_mime=normalized_mime,
    )
    if data_url:
        return data_url

    downloaded = _download_image_data_url(fallback_url)
    if downloaded:
        return downloaded

    logging.warning(
        "Failed to convert local image %s into a VLM-supported format.",
        path,
    )
    return None


def _placeholder_expr(column: str) -> pl.Expr:
    placeholders = ATTRIBUTE_PLACEHOLDER_VALUES + [""]
    value = pl.col(column).cast(pl.Utf8).str.strip_chars()
    lowered = value.str.to_lowercase()
    return (
        value.is_null()
        | (lowered == "")
        | lowered.is_in(placeholders)
        | lowered.str.starts_with("not in taxonomy")
    )


def _pick_parent_image_source(
    group_df: pl.DataFrame,
    *,
    retailer_priority: Sequence[str],
) -> dict[str, Any] | None:
    if group_df.is_empty():
        return None
    priority_map = {retailer: idx for idx, retailer in enumerate(retailer_priority)}
    best: tuple[tuple[int, str], dict[str, Any]] | None = None
    for row in group_df.iter_rows(named=True):
        hero = row.get("hero_image_url")
        if not _is_valid_image_url(str(hero or "").strip()):
            continue
        retailer = str(row.get("retailer") or "").strip().lower()
        rank = priority_map.get(retailer, len(priority_map))
        key = (rank, retailer)
        if best is None or key < best[0]:
            best = (key, row)
    return best[1] if best else None


def _iter_rows_by_priority(
    group_df: pl.DataFrame,
    retailer_priority: Sequence[str],
) -> Iterable[dict[str, Any]]:
    priority_map = {retailer: idx for idx, retailer in enumerate(retailer_priority)}
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for row in group_df.iter_rows(named=True):
        retailer = str(row.get("retailer") or "").strip().lower()
        rank = priority_map.get(retailer, len(priority_map))
        ranked.append((rank, retailer, row))
    ranked.sort(key=lambda item: (item[0], item[1]))
    for _, _, row in ranked:
        yield row


def _pick_parent_source(
    group_df: pl.DataFrame,
    *,
    retailer_priority: Sequence[str],
) -> dict[str, Any] | None:
    for row in _iter_rows_by_priority(group_df, retailer_priority):
        return row
    return None


def _pick_local_image_source(
    group_df: pl.DataFrame,
    image_cache: Mapping[str, list],
    *,
    retailer_priority: Sequence[str],
) -> tuple[dict[str, Any], Path] | None:
    if not image_cache or group_df.is_empty():
        return None
    for row in _iter_rows_by_priority(group_df, retailer_priority):
        parent_id = str(row.get("parent_product_id") or "").strip()
        if not parent_id:
            continue
        local_path = find_local_image(image_cache, parent_id)
        if local_path and local_path.exists():
            return row, local_path
    return None


def _build_vision_prompt(
    *,
    category_label: str | None,
    brand: str | None,
    product_name: str | None,
    attr_meta: Mapping[str, Mapping[str, object]],
) -> str:
    product_bits = [str(item).strip() for item in (brand, product_name) if item]
    product = " ".join(product_bits).strip()
    allowed_payload = {
        attr_id: meta.get("allowed_values", []) for attr_id, meta in attr_meta.items()
    }
    allowed_json = json.dumps(allowed_payload, ensure_ascii=False)
    prompt_lines = [
        "Extract product attributes from the image only.",
        'Return json with a single top-level key: "attributes".',
        'For each attribute, return {"value": <value|null>, "confidence": <0-1>}.',
        "Use only the allowed values list (lowercase).",
        (
            "Only output a value if you are highly confident it is visible in the image "
            f"and confidence >= {VISION_CONFIDENCE_THRESHOLD:.2f}; otherwise output null."
        ),
        f"Category: {category_label or '(unknown)'}",
        f"Product: {product or '(unknown)'}",
        "Allowed values (json):```json\n" + allowed_json + "\n```",
        'Output example: {"attributes": {"form": {"value": "powder", "confidence": 0.9}}}',
    ]
    return "\n".join(prompt_lines)


def _fill_parent_attributes_from_images(
    parents_df: pl.DataFrame,
    *,
    taxonomy: Mapping[str, object],
    llm_wrapper: object | None,
    retailer_priority: Sequence[str],
    min_attribute_coverage: float = 0.0,
    checkpoint_response_by_key: Mapping[str, object] | None = None,
    audit_checkpoint_callback: Callable[[Sequence[dict[str, Any]]], None] | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Fill remaining parent-level N/A values using image-only LLM calls."""
    if parents_df.is_empty():
        return parents_df, pl.DataFrame()
    if llm_wrapper is None:
        logging.info("Skipping image attribute fill: llm_wrapper not provided.")
        return parents_df, pl.DataFrame()
    columns, _ = get_schema_and_column_names(parents_df)
    if "hero_image_url" not in columns:
        logging.info("Skipping image attribute fill: hero_image_url missing.")
        return parents_df, pl.DataFrame()

    group_cols = _attribute_group_cols(parents_df)
    if not group_cols:
        logging.info("Skipping image attribute fill: canonical_id missing.")
        return parents_df, pl.DataFrame()
    vision_parent_no_value_suppressed, _ = _load_no_value_query_suppression(
        step="vision"
    )
    sure_parent_suppressed, _ = _load_sure_query_suppression()
    suppressed_no_value_attributes = 0
    suppressed_sure_attributes = 0

    image_meta = _build_image_attribute_meta(taxonomy)
    if not image_meta:
        logging.info("Skipping image attribute fill: no image allowlist configured.")
        return parents_df, pl.DataFrame()
    coverage_threshold = _normalize_coverage_threshold(min_attribute_coverage)
    low_coverage_attributes = 0
    eligible_attrs_by_category: dict[str, set[str]] = {}
    if coverage_threshold > 0.0:
        coverage_counts: dict[tuple[str, str], list[int]] = {}
        for _group_key, group_df in parents_df.partition_by(
            group_cols, as_dict=True
        ).items():
            group_columns, _ = get_schema_and_column_names(group_df)
            category_norm = _resolve_image_category_key(group_df, image_meta=image_meta)
            category_meta = image_meta.get(category_norm)
            if not category_meta:
                continue
            candidate_attrs = [a for a in category_meta.keys() if a in group_columns]
            for attr in candidate_attrs:
                has_value = not any(
                    _is_placeholder_value(v)
                    for v in group_df.get_column(attr).to_list()
                )
                _update_attribute_coverage_counts(
                    coverage_counts,
                    category_key=category_norm,
                    attribute_id=attr,
                    has_value=has_value,
                )
        eligible_attrs_by_category = _eligible_attributes_by_coverage(
            coverage_counts,
            min_coverage=coverage_threshold,
        )

    image_cache = build_image_cache(DEFAULT_IMAGE_ROOT)
    if not image_cache:
        logging.info("No local image cache found; falling back to hero_image_url only.")

    checkpoint_map = dict(checkpoint_response_by_key or {})
    requests: list[dict[str, Any]] = []
    for key, group_df in parents_df.partition_by(group_cols, as_dict=True).items():
        group_key = key if isinstance(key, tuple) else (key,)
        group_info = dict(zip(group_cols, group_key))
        group_columns, _ = get_schema_and_column_names(group_df)
        category_norm = _resolve_image_category_key(group_df, image_meta=image_meta)
        category_meta = image_meta.get(category_norm)
        if not category_meta:
            continue
        candidate_attrs = [a for a in category_meta.keys() if a in group_columns]
        if not candidate_attrs:
            continue
        missing_attrs = []
        for attr in candidate_attrs:
            series = group_df.get_column(attr)
            if any(_is_placeholder_value(v) for v in series.to_list()):
                missing_attrs.append(attr)
        if not missing_attrs:
            continue
        if coverage_threshold > 0.0:
            eligible_attrs = eligible_attrs_by_category.get(category_norm, set())
            coverage_filtered = [
                attr for attr in missing_attrs if attr in eligible_attrs
            ]
            low_coverage_attributes += len(missing_attrs) - len(coverage_filtered)
            missing_attrs = coverage_filtered
        if not missing_attrs:
            continue
        source: dict[str, Any] | None = None
        image_payload: dict[str, Any] | None = None
        image_source = "none"
        image_path = ""

        local_source = _pick_local_image_source(
            group_df,
            image_cache,
            retailer_priority=retailer_priority,
        )
        if local_source:
            source, local_path = local_source
            data_url = _image_path_to_data_url(
                local_path,
                fallback_url=str(source.get("hero_image_url") or ""),
            )
            if data_url:
                image_payload = {"type": "input_image", "image_url": data_url}
                image_source = "local"
                image_path = str(local_path)

        if image_payload is None:
            source = _pick_parent_image_source(
                group_df, retailer_priority=retailer_priority
            )
            if not source:
                continue
            hero_url = str(source.get("hero_image_url") or "").strip()
            if not _is_valid_image_url(hero_url):
                continue
            image_payload = {"type": "input_image", "image_url": hero_url}
            image_source = "url"
        source_retailer = str(source.get("retailer") or "").strip()
        source_parent_product_id = str(source.get("parent_product_id") or "").strip()
        unresolved_filtered: list[str] = []
        for attr in missing_attrs:
            key_tuple = (source_retailer, source_parent_product_id, attr)
            if key_tuple in sure_parent_suppressed:
                suppressed_sure_attributes += 1
                continue
            if key_tuple in vision_parent_no_value_suppressed:
                suppressed_no_value_attributes += 1
                continue
            unresolved_filtered.append(attr)
        if not unresolved_filtered:
            continue
        missing_attrs = unresolved_filtered
        attr_meta = {attr: category_meta[attr] for attr in missing_attrs}
        request_key = _vision_request_key(
            group_info=group_info,
            category_key=category_norm,
            source_retailer=source_retailer,
            source_parent_product_id=source_parent_product_id,
            missing_attrs=missing_attrs,
        )
        prompt_text = _build_vision_prompt(
            category_label=str(
                source.get("category_label") or source.get("category_id") or ""
            ),
            brand=str(source.get("brand") or ""),
            product_name=str(source.get("product_name") or ""),
            attr_meta=attr_meta,
        )
        user_content = [
            {"type": "input_text", "text": prompt_text},
            image_payload,
        ]
        requests.append(
            {
                "group_info": group_info,
                "category_key": category_norm,
                "missing_attrs": missing_attrs,
                "attr_meta": attr_meta,
                "hero_image_url": str(source.get("hero_image_url") or ""),
                "image_source": image_source,
                "image_path": image_path,
                "source_retailer": source_retailer,
                "source_parent_product_id": source_parent_product_id,
                "request_key": request_key,
                "prompt": {"user_content": user_content},
            }
        )

    if not requests:
        if suppressed_no_value_attributes:
            logging.info(
                "Vision attribute fill skipped %s attributes due to repeated no-value history.",
                suppressed_no_value_attributes,
            )
        if suppressed_sure_attributes:
            logging.info(
                "Vision attribute fill skipped %s attributes due to sure consensus lock.",
                suppressed_sure_attributes,
            )
        if low_coverage_attributes:
            logging.info(
                "Vision attribute fill skipped %s attributes below %.0f%% coverage.",
                low_coverage_attributes,
                coverage_threshold * 100,
            )
        return parents_df, pl.DataFrame()

    naming = get_naming_params()
    vision_step = naming["pdpVisionAttributeQuery"]
    system_prompt = "You are a vision model. Respond in json."
    responses: list[object] = [{} for _ in requests]
    uncached_prompts: list[dict[str, Any]] = []
    uncached_indices: list[int] = []
    replayed_request_count = 0
    for idx, req in enumerate(requests):
        cached = checkpoint_map.get(str(req.get("request_key") or ""))
        if cached is None:
            uncached_indices.append(idx)
            uncached_prompts.append(req["prompt"])
        else:
            replayed_request_count += 1
            responses[idx] = cached
    if uncached_prompts:
        try:
            uncached_responses = run_step_json(
                llm_wrapper,
                vision_step,
                system_prompt,
                uncached_prompts,
                retry_missing=2,
            )
        except Exception:
            logging.exception(
                "Vision attribute fill failed; proceeding without image fills."
            )
            return parents_df, pl.DataFrame()
        if len(uncached_responses) != len(uncached_prompts):
            logging.warning(
                "Vision attribute fill response count mismatch: requests=%s responses=%s",
                len(uncached_prompts),
                len(uncached_responses),
            )
        for pos, idx in enumerate(uncached_indices):
            responses[idx] = (
                uncached_responses[pos] if pos < len(uncached_responses) else {}
            )
    else:
        logging.info(
            "Vision attribute fill replayed %s requests from checkpoints; no API calls made.",
            replayed_request_count,
        )

    updates: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    filled_request_count = 0
    filled_value_count = 0
    checkpoint_batch_rows: list[dict[str, Any]] = []
    for idx, req in enumerate(requests):
        resp = responses[idx] if idx < len(responses) else None
        replayed_from_checkpoint = str(req.get("request_key") or "") in checkpoint_map
        attr_meta = req["attr_meta"]
        allowed_map = {
            attr: set(meta.get("allowed_values", []) or [])
            for attr, meta in attr_meta.items()
        }
        attrs_section: Mapping[str, object] = {}
        if isinstance(resp, Mapping):
            attrs = resp.get("attributes")
            if isinstance(attrs, Mapping):
                attrs_section = attrs
        filled: dict[str, dict[str, Any]] = {}
        for attr in req["missing_attrs"]:
            entry = attrs_section.get(attr) if attrs_section else None
            value_raw = None
            confidence = None
            if isinstance(entry, Mapping):
                value_raw = entry.get("value")
                confidence = entry.get("confidence")
            else:
                value_raw = entry
            if isinstance(confidence, (int, float)):
                confidence = float(confidence)
            elif isinstance(confidence, str):
                try:
                    confidence = float(confidence.strip())
                except ValueError:
                    confidence = None
            else:
                confidence = None
            value_norm = _normalize_llm_attribute_value(value_raw)
            if confidence is None or confidence < VISION_CONFIDENCE_THRESHOLD:
                continue
            if value_norm and value_norm in allowed_map.get(attr, set()):
                if not _is_placeholder_value(value_norm):
                    filled[attr] = {"value": value_norm, "confidence": confidence}
        if filled:
            update_row = dict(req["group_info"])
            for attr, payload in filled.items():
                update_row[attr] = payload.get("value")
            updates.append(update_row)
            filled_request_count += 1
            filled_value_count += len(filled)
        audit_rows.append(
            {
                **req["group_info"],
                "category_key": req["category_key"],
                "source_retailer": req["source_retailer"],
                "source_parent_product_id": req["source_parent_product_id"],
                "hero_image_url": req["hero_image_url"],
                "image_source": req.get("image_source", ""),
                "image_path": req.get("image_path", ""),
                "request_key": req.get("request_key", ""),
                "replayed_from_checkpoint": replayed_from_checkpoint,
                "requested_attributes": ", ".join(req["missing_attrs"]),
                "filled_attributes": json.dumps(filled, ensure_ascii=False),
                "response_json": json.dumps(resp, ensure_ascii=False),
            }
        )
        if not replayed_from_checkpoint:
            checkpoint_batch_rows.append(audit_rows[-1])
            if audit_checkpoint_callback and len(checkpoint_batch_rows) >= 100:
                audit_checkpoint_callback(checkpoint_batch_rows)
                checkpoint_batch_rows = []

    if audit_checkpoint_callback and checkpoint_batch_rows:
        audit_checkpoint_callback(checkpoint_batch_rows)

    if updates:
        update_keys = sorted({key for row in updates for key in row.keys()})
        update_schema = {key: pl.Utf8 for key in update_keys}
        update_df = pl.DataFrame(updates, schema=update_schema)
        suffix = "__vision"
        merged = parents_df.join(update_df, on=group_cols, how="left", suffix=suffix)
        merged_columns, _ = get_schema_and_column_names(merged)
        for attr in {k for row in updates for k in row.keys()}:
            if attr in group_cols:
                continue
            vision_col = f"{attr}{suffix}"
            if vision_col not in merged_columns or attr not in merged_columns:
                continue
            merged = merged.with_columns(
                pl.when(_placeholder_expr(attr) & pl.col(vision_col).is_not_null())
                .then(pl.col(vision_col))
                .otherwise(pl.col(attr))
                .alias(attr)
            ).drop(vision_col)
            merged_columns = [col for col in merged_columns if col != vision_col]
        parents_df = merged

    audit_df = pl.DataFrame(audit_rows) if audit_rows else pl.DataFrame()
    logging.info(
        "Vision attribute fill summary: requests=%s replayed_requests=%s filled_requests=%s filled_values=%s",
        len(requests),
        replayed_request_count,
        filled_request_count,
        filled_value_count,
    )
    if suppressed_no_value_attributes:
        logging.info(
            "Vision attribute fill skipped %s attributes due to repeated no-value history.",
            suppressed_no_value_attributes,
        )
    if suppressed_sure_attributes:
        logging.info(
            "Vision attribute fill skipped %s attributes due to sure consensus lock.",
            suppressed_sure_attributes,
        )
    if low_coverage_attributes:
        logging.info(
            "Vision attribute fill skipped %s attributes below %.0f%% coverage.",
            low_coverage_attributes,
            coverage_threshold * 100,
        )
    return parents_df, audit_df


def _fill_attributes_from_web(
    parents_df: pl.DataFrame,
    variants_df: pl.DataFrame,
    *,
    taxonomy: Mapping[str, object],
    llm_wrapper: object | None,
    retailer_priority: Sequence[str],
    min_attribute_coverage: float = 0.0,
    checkpoint_response_by_key: Mapping[str, object] | None = None,
    audit_checkpoint_callback: Callable[[Sequence[dict[str, Any]]], None] | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Fill remaining parent + variant attributes using web search on brand sites."""
    if parents_df.is_empty():
        return parents_df, variants_df, pl.DataFrame()
    if llm_wrapper is None:
        logging.info("Skipping web attribute fill: llm_wrapper not provided.")
        return parents_df, variants_df, pl.DataFrame()

    parent_columns, _ = get_schema_and_column_names(parents_df)
    variant_columns, _ = get_schema_and_column_names(variants_df)
    if not parent_columns:
        logging.info("Skipping web attribute fill: parent columns unavailable.")
        return parents_df, variants_df, pl.DataFrame()

    group_cols = _attribute_group_cols(parents_df)
    if not group_cols:
        logging.info("Skipping web attribute fill: canonical_id missing.")
        return parents_df, variants_df, pl.DataFrame()
    web_parent_no_value_suppressed, web_variant_no_value_suppressed = (
        _load_no_value_query_suppression(step="brand_web_search")
    )
    sure_parent_suppressed, sure_variant_suppressed = _load_sure_query_suppression()
    suppressed_parent_no_value_attributes = 0
    suppressed_variant_no_value_attributes = 0
    suppressed_parent_sure_attributes = 0
    suppressed_variant_sure_attributes = 0
    coverage_threshold = _normalize_coverage_threshold(min_attribute_coverage)
    low_coverage_parent_attributes = 0
    low_coverage_variant_attributes = 0

    no_web = {
        _normalize_key(item)
        for item in (taxonomy.get("no_web_categories") or [])
        if isinstance(item, str)
    }
    parent_aliases = build_column_aliases(parent_columns)
    variant_aliases = (
        build_column_aliases(variant_columns) if variant_columns else parent_aliases
    )
    web_meta = _build_web_attribute_meta(
        taxonomy,
        parent_columns=parent_columns,
        variant_columns=variant_columns,
        parent_aliases=parent_aliases,
        variant_aliases=variant_aliases,
    )
    if not web_meta:
        logging.info("Skipping web attribute fill: no eligible web attributes found.")
        return parents_df, variants_df, pl.DataFrame()

    brand_aliases = _load_brand_aliases(BRAND_ALIASES_PATH)

    brands: set[str] = set()
    for row in (
        parents_df.select(["brand"]).to_dicts() if "brand" in parent_columns else []
    ):
        raw = row.get("brand")
        if isinstance(raw, str) and raw.strip():
            brands.add(raw.strip())
    if brands:
        set_lookup_market_context(
            industry="beauty",
            industry_description="cosmetics and personal care products",
        )
        try:
            brand_sites = lookup_websites(
                llm_wrapper,
                brands,
                aliases=brand_aliases,
                service_tier="flex",
            )
        except Exception as exc:
            logging.warning("Brand website lookup failed: %s", exc)
            brand_sites = {}
    else:
        brand_sites = {}

    def _build_relaxed_brand_sites(mapping: Mapping[str, object]) -> dict[str, object]:
        relaxed: dict[str, object] = {}
        for key, value in mapping.items():
            if not isinstance(key, str):
                continue
            normalized = _normalize_brand_lookup_key(key)
            if not normalized or normalized in relaxed:
                continue
            relaxed[normalized] = value
        return relaxed

    relaxed_brand_sites = _build_relaxed_brand_sites(brand_sites)

    def _brand_domains(brand: str | None) -> list[str]:
        if not brand:
            return []
        norm = brand.strip().lower()
        canon = brand_aliases.get(norm, norm)
        raw_site = brand_sites.get(canon)
        if raw_site is None:
            raw_site = relaxed_brand_sites.get(_normalize_brand_lookup_key(canon))
        if isinstance(raw_site, str) and raw_site.strip():
            return [raw_site.strip()]
        if isinstance(raw_site, list):
            return [
                str(item).strip()
                for item in raw_site
                if isinstance(item, str) and str(item).strip()
            ]
        return []

    if brands:
        missing_domains = {b for b in brands if not _brand_domains(b)}
        if missing_domains:
            logging.info(
                "Retrying website lookup for %s brands with missing domains.",
                len(missing_domains),
            )
            try:
                brand_sites = lookup_websites(
                    llm_wrapper,
                    missing_domains,
                    aliases=brand_aliases,
                    service_tier="flex",
                    force_refresh=True,
                )
            except Exception as exc:
                logging.warning("Brand website lookup retry failed: %s", exc)
            relaxed_brand_sites = _build_relaxed_brand_sites(brand_sites)

    variants_by_group: dict[Any, pl.DataFrame] = {}
    if not variants_df.is_empty() and group_cols:
        variants_by_group = variants_df.partition_by(group_cols, as_dict=True)
    eligible_parent_attrs_by_category: dict[str, set[str]] = {}
    eligible_variant_attrs_by_category: dict[str, set[str]] = {}
    if coverage_threshold > 0.0:
        parent_coverage_counts: dict[tuple[str, str], list[int]] = {}
        variant_coverage_counts: dict[tuple[str, str], list[int]] = {}
        for key, group_df in parents_df.partition_by(group_cols, as_dict=True).items():
            group_key = key if isinstance(key, tuple) else (key,)
            category_norm = _resolve_image_category_key(group_df, image_meta=web_meta)
            if not category_norm or category_norm in no_web:
                continue
            category_meta = web_meta.get(category_norm)
            if not category_meta:
                continue
            parent_attr_meta = {
                attr_id: meta
                for attr_id, meta in category_meta.items()
                if meta.get("scope") == "product"
            }
            for attr_id, meta in parent_attr_meta.items():
                col = str(meta.get("column") or "")
                if not col or col not in group_df.columns:
                    continue
                has_value = not any(
                    _is_placeholder_value(v) for v in group_df.get_column(col).to_list()
                )
                _update_attribute_coverage_counts(
                    parent_coverage_counts,
                    category_key=category_norm,
                    attribute_id=attr_id,
                    has_value=has_value,
                )
            variant_attr_meta = {
                attr_id: meta
                for attr_id, meta in category_meta.items()
                if meta.get("scope") == "variant"
            }
            variant_group = variants_by_group.get(group_key)
            if (
                variant_group is None
                or variant_group.is_empty()
                or not variant_attr_meta
            ):
                continue
            for row in variant_group.iter_rows(named=True):
                for attr_id, meta in variant_attr_meta.items():
                    col = str(meta.get("column") or "")
                    if not col:
                        continue
                    _update_attribute_coverage_counts(
                        variant_coverage_counts,
                        category_key=category_norm,
                        attribute_id=attr_id,
                        has_value=not _is_placeholder_value(row.get(col)),
                    )
        eligible_parent_attrs_by_category = _eligible_attributes_by_coverage(
            parent_coverage_counts,
            min_coverage=coverage_threshold,
        )
        eligible_variant_attrs_by_category = _eligible_attributes_by_coverage(
            variant_coverage_counts,
            min_coverage=coverage_threshold,
        )

    requests_by_domain: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for key, group_df in parents_df.partition_by(group_cols, as_dict=True).items():
        group_key = key if isinstance(key, tuple) else (key,)
        group_info = dict(zip(group_cols, group_key))
        category_norm = _resolve_image_category_key(group_df, image_meta=web_meta)
        if not category_norm or category_norm in no_web:
            continue
        category_meta = web_meta.get(category_norm)
        if not category_meta:
            continue

        parent_attr_meta = {
            attr_id: meta
            for attr_id, meta in category_meta.items()
            if meta.get("scope") == "product"
        }
        variant_attr_meta = {
            attr_id: meta
            for attr_id, meta in category_meta.items()
            if meta.get("scope") == "variant"
        }

        missing_parent_attrs: list[str] = []
        for attr_id, meta in parent_attr_meta.items():
            col = str(meta.get("column") or "")
            if not col or col not in group_df.columns:
                continue
            series = group_df.get_column(col)
            if any(_is_placeholder_value(v) for v in series.to_list()):
                missing_parent_attrs.append(attr_id)

        variant_missing_map: dict[str, list[str]] = {}
        variants_payload: list[dict[str, Any]] = []
        variant_key_map: dict[str, dict[str, Any]] = {}
        variant_id_lookup: dict[str, list[str]] = {}
        requested_variant_attrs: set[str] = set()
        variant_group = variants_by_group.get(group_key)
        if (
            variant_group is not None
            and not variant_group.is_empty()
            and variant_attr_meta
        ):
            eligible_variant_attrs = (
                eligible_variant_attrs_by_category.get(category_norm, set())
                if coverage_threshold > 0.0
                else set()
            )
            for row in variant_group.iter_rows(named=True):
                variant_id = str(row.get("variant_id") or "").strip()
                retailer = str(row.get("retailer") or "").strip()
                if not variant_id:
                    continue
                missing_attrs: list[str] = []
                for attr_id, meta in variant_attr_meta.items():
                    col = str(meta.get("column") or "")
                    if not col:
                        continue
                    if _is_placeholder_value(row.get(col)):
                        if (
                            coverage_threshold > 0.0
                            and attr_id not in eligible_variant_attrs
                        ):
                            low_coverage_variant_attributes += 1
                            continue
                        if (retailer, variant_id, attr_id) in sure_variant_suppressed:
                            suppressed_variant_sure_attributes += 1
                            continue
                        if (
                            retailer,
                            variant_id,
                            attr_id,
                        ) in web_variant_no_value_suppressed:
                            suppressed_variant_no_value_attributes += 1
                            continue
                        missing_attrs.append(attr_id)
                if not missing_attrs:
                    continue
                variant_key = f"{retailer}:{variant_id}" if retailer else variant_id
                variant_missing_map[variant_key] = missing_attrs
                requested_variant_attrs.update(missing_attrs)
                variant_id_lookup.setdefault(variant_id, []).append(variant_key)
                variant_key_map[variant_key] = {
                    "retailer": retailer,
                    "variant_id": variant_id,
                    "missing_attrs": missing_attrs,
                }
                variants_payload.append(
                    {
                        "variant_key": variant_key,
                        "variant_id": variant_id,
                        "retailer": retailer,
                        "name": _variant_display_name(row),
                        "size": row.get("size_text_raw"),
                        "missing_attributes": missing_attrs,
                    }
                )

        source = (
            _pick_parent_source(group_df, retailer_priority=retailer_priority) or {}
        )
        source_retailer = str(source.get("retailer") or "").strip()
        source_parent_product_id = str(source.get("parent_product_id") or "").strip()
        filtered_parent_attrs: list[str] = []
        for attr_id in missing_parent_attrs:
            key_tuple = (source_retailer, source_parent_product_id, attr_id)
            if key_tuple in sure_parent_suppressed:
                suppressed_parent_sure_attributes += 1
                continue
            if key_tuple in web_parent_no_value_suppressed:
                suppressed_parent_no_value_attributes += 1
                continue
            filtered_parent_attrs.append(attr_id)
        missing_parent_attrs = filtered_parent_attrs
        if coverage_threshold > 0.0:
            eligible_parent_attrs = eligible_parent_attrs_by_category.get(
                category_norm, set()
            )
            coverage_filtered = [
                attr_id
                for attr_id in missing_parent_attrs
                if attr_id in eligible_parent_attrs
            ]
            low_coverage_parent_attributes += len(missing_parent_attrs) - len(
                coverage_filtered
            )
            missing_parent_attrs = coverage_filtered
        if not missing_parent_attrs and not variants_payload:
            continue

        brand = str(source.get("brand") or "").strip()
        product_name = str(source.get("product_name") or "").strip()
        domains = _brand_domains(brand)
        normalized_domains = _normalize_domains(domains)
        if not normalized_domains:
            logging.info(
                "Skipping web attribute fill for %s/%s: no brand domains.",
                brand or "(unknown)",
                product_name or "(unknown)",
            )
            continue

        prompt_text = _build_web_prompt(
            category_label=str(
                source.get("category_label") or source.get("category_id") or ""
            ),
            brand=brand,
            product_name=product_name,
            domains=normalized_domains,
            parent_attrs={
                k: v for k, v in parent_attr_meta.items() if k in missing_parent_attrs
            },
            variant_attrs={
                k: v
                for k, v in variant_attr_meta.items()
                if k in requested_variant_attrs
            },
            variants=variants_payload,
        )
        request_key = _web_request_key(
            group_info=group_info,
            category_key=category_norm,
            source_retailer=source_retailer,
            source_parent_product_id=source_parent_product_id,
            domains=normalized_domains,
            missing_parent_attrs=missing_parent_attrs,
            variant_missing_map=variant_missing_map,
        )
        req = {
            "group_info": group_info,
            "category_key": category_norm,
            "source_retailer": source_retailer,
            "source_parent_product_id": source_parent_product_id,
            "brand": brand,
            "product_name": product_name,
            "domains": normalized_domains,
            "missing_parent_attrs": missing_parent_attrs,
            "variant_missing_map": variant_missing_map,
            "variant_key_map": variant_key_map,
            "variant_id_lookup": variant_id_lookup,
            "parent_attr_meta": parent_attr_meta,
            "variant_attr_meta": variant_attr_meta,
            "request_key": request_key,
            "prompt": prompt_text,
        }
        domain_key = tuple(normalized_domains)
        requests_by_domain.setdefault(domain_key, []).append(req)

    if not requests_by_domain:
        logging.info(
            "Web attribute fill: no requests built (no missing attributes or domains)."
        )
        if (
            suppressed_parent_no_value_attributes
            or suppressed_variant_no_value_attributes
        ):
            logging.info(
                "Web attribute fill skipped attributes due to repeated no-value history: parent=%s variant=%s",
                suppressed_parent_no_value_attributes,
                suppressed_variant_no_value_attributes,
            )
        if suppressed_parent_sure_attributes or suppressed_variant_sure_attributes:
            logging.info(
                "Web attribute fill skipped attributes due to sure consensus lock: parent=%s variant=%s",
                suppressed_parent_sure_attributes,
                suppressed_variant_sure_attributes,
            )
        if low_coverage_parent_attributes or low_coverage_variant_attributes:
            logging.info(
                "Web attribute fill skipped attributes below %.0f%% coverage: parent=%s variant=%s",
                coverage_threshold * 100,
                low_coverage_parent_attributes,
                low_coverage_variant_attributes,
            )
        return parents_df, variants_df, pl.DataFrame()

    naming = get_naming_params()
    web_step = naming["pdpWebAttributeQuery"]
    system_prompt = "You are a careful web research assistant. Return JSON only."
    total_requests = sum(len(reqs) for reqs in requests_by_domain.values())
    logging.info(
        "Web attribute fill: built %s requests across %s domain groups.",
        total_requests,
        len(requests_by_domain),
    )

    parent_updates: list[dict[str, Any]] = []
    variant_updates: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    checkpoint_map = dict(checkpoint_response_by_key or {})
    filled_parent_values = 0
    filled_variant_values = 0
    filled_request_count = 0
    replayed_request_count = 0

    for domain_key, requests in requests_by_domain.items():
        batch_audit_rows: list[dict[str, Any]] = []
        tools, extra_body = build_web_search_request(domain_key)
        responses: list[object] = [{} for _ in requests]
        uncached_prompts: list[str] = []
        uncached_indices: list[int] = []
        for idx, req in enumerate(requests):
            cached = checkpoint_map.get(str(req.get("request_key") or ""))
            if cached is None:
                uncached_indices.append(idx)
                uncached_prompts.append(req["prompt"])
            else:
                replayed_request_count += 1
                responses[idx] = cached
        if uncached_prompts:
            try:
                uncached_responses = run_step_json(
                    llm_wrapper,
                    web_step,
                    system_prompt,
                    uncached_prompts,
                    tools=tools,
                    tool_choice="required",
                    service_tier="flex",
                    extra_body=extra_body,
                )
            except Exception:
                logging.exception(
                    "Web attribute fill failed for domains=%s", domain_key
                )
                uncached_responses = [{} for _ in uncached_prompts]

            if len(uncached_responses) != len(uncached_prompts):
                logging.warning(
                    "Web attribute fill response count mismatch: requests=%s responses=%s domains=%s",
                    len(uncached_prompts),
                    len(uncached_responses),
                    domain_key,
                )
            for pos, idx in enumerate(uncached_indices):
                responses[idx] = (
                    uncached_responses[pos] if pos < len(uncached_responses) else {}
                )

        for idx, req in enumerate(requests):
            resp = responses[idx] if idx < len(responses) else None
            replayed_from_checkpoint = (
                str(req.get("request_key") or "") in checkpoint_map
            )
            resp_map = _coerce_web_fill_response(resp)
            parent_attr_meta = req["parent_attr_meta"]
            variant_attr_meta = req["variant_attr_meta"]
            missing_parent = req["missing_parent_attrs"]
            variant_missing_map = req["variant_missing_map"]
            variant_key_map = req["variant_key_map"]
            variant_id_lookup = req["variant_id_lookup"]

            parent_allowed = {
                attr_id: set(meta.get("allowed_values", []) or [])
                for attr_id, meta in parent_attr_meta.items()
            }
            variant_allowed = {
                attr_id: set(meta.get("allowed_values", []) or [])
                for attr_id, meta in variant_attr_meta.items()
            }

            parent_section: Mapping[str, object] = {}
            variant_section: Mapping[str, object] = {}
            if isinstance(resp_map, Mapping):
                parent_section = resp_map.get("parent_attributes") or {}
                variant_section = resp_map.get("variants") or {}

            filled_parent: dict[str, dict[str, Any]] = {}
            for attr_id in missing_parent:
                entry = (
                    parent_section.get(attr_id)
                    if isinstance(parent_section, Mapping)
                    else None
                )
                value_raw = None
                confidence = None
                evidence_url = None
                if isinstance(entry, Mapping):
                    value_raw = entry.get("value")
                    confidence = entry.get("confidence")
                    evidence_url = entry.get("evidence_url")
                else:
                    value_raw = entry
                if isinstance(confidence, (int, float)):
                    confidence = float(confidence)
                elif isinstance(confidence, str):
                    try:
                        confidence = float(confidence.strip())
                    except ValueError:
                        confidence = None
                else:
                    confidence = None
                value_norm = _normalize_llm_attribute_value(value_raw)
                if confidence is None or confidence < WEB_CONFIDENCE_THRESHOLD:
                    continue
                if value_norm and value_norm in parent_allowed.get(attr_id, set()):
                    if not _is_placeholder_value(value_norm):
                        evidence_norm = _normalize_evidence_url(
                            evidence_url, req["domains"]
                        )
                        if not evidence_norm:
                            continue
                        filled_parent[attr_id] = {
                            "value": value_norm,
                            "confidence": confidence,
                            "evidence_url": evidence_norm,
                        }

            if filled_parent:
                update_row = dict(req["group_info"])
                for attr_id, payload in filled_parent.items():
                    col = parent_attr_meta.get(attr_id, {}).get("column")
                    if isinstance(col, str) and col:
                        update_row[col] = payload.get("value")
                parent_updates.append(update_row)
                filled_parent_values += len(filled_parent)

            filled_variants: dict[str, dict[str, dict[str, Any]]] = {}
            if isinstance(variant_section, Mapping):
                for variant_key, attrs in variant_section.items():
                    if not isinstance(attrs, Mapping):
                        continue
                    key = str(variant_key)
                    resolved_key = None
                    if key in variant_key_map:
                        resolved_key = key
                    elif key in variant_id_lookup and len(variant_id_lookup[key]) == 1:
                        resolved_key = variant_id_lookup[key][0]
                    if not resolved_key:
                        continue
                    requested_attrs = variant_missing_map.get(resolved_key, [])
                    if not requested_attrs:
                        continue
                    per_variant: dict[str, dict[str, Any]] = {}
                    for attr_id in requested_attrs:
                        entry = attrs.get(attr_id)
                        value_raw = None
                        confidence = None
                        evidence_url = None
                        if isinstance(entry, Mapping):
                            value_raw = entry.get("value")
                            confidence = entry.get("confidence")
                            evidence_url = entry.get("evidence_url")
                        else:
                            value_raw = entry
                        if isinstance(confidence, (int, float)):
                            confidence = float(confidence)
                        elif isinstance(confidence, str):
                            try:
                                confidence = float(confidence.strip())
                            except ValueError:
                                confidence = None
                        else:
                            confidence = None
                        value_norm = _normalize_llm_attribute_value(value_raw)
                        if confidence is None or confidence < WEB_CONFIDENCE_THRESHOLD:
                            continue
                        if value_norm and value_norm in variant_allowed.get(
                            attr_id, set()
                        ):
                            if not _is_placeholder_value(value_norm):
                                evidence_norm = _normalize_evidence_url(
                                    evidence_url, req["domains"]
                                )
                                if not evidence_norm:
                                    continue
                                per_variant[attr_id] = {
                                    "value": value_norm,
                                    "confidence": confidence,
                                    "evidence_url": evidence_norm,
                                }
                    if per_variant:
                        filled_variants[resolved_key] = per_variant

            if filled_variants:
                for variant_key, payload in filled_variants.items():
                    info = variant_key_map.get(variant_key)
                    if not info:
                        continue
                    update_row = {
                        "retailer": info.get("retailer"),
                        "variant_id": info.get("variant_id"),
                    }
                    for attr_id, entry in payload.items():
                        col = variant_attr_meta.get(attr_id, {}).get("column")
                        if isinstance(col, str) and col:
                            update_row[col] = entry.get("value")
                    if update_row.get("variant_id"):
                        variant_updates.append(update_row)
                        filled_variant_values += len(payload)

            if filled_parent or filled_variants:
                filled_request_count += 1

            audit_row = {
                **req["group_info"],
                "category_key": req["category_key"],
                "source_retailer": req["source_retailer"],
                "source_parent_product_id": req["source_parent_product_id"],
                "brand": req["brand"],
                "product_name": req["product_name"],
                "domains": ", ".join(req["domains"]),
                "request_key": req.get("request_key", ""),
                "replayed_from_checkpoint": replayed_from_checkpoint,
                "requested_parent_attributes": ", ".join(missing_parent),
                "requested_variant_attributes": json.dumps(
                    req["variant_missing_map"], ensure_ascii=False
                ),
                "filled_parent_attributes": json.dumps(
                    filled_parent, ensure_ascii=False
                ),
                "filled_variant_attributes": json.dumps(
                    filled_variants, ensure_ascii=False
                ),
                "response_json": json.dumps(resp, ensure_ascii=False),
            }
            audit_rows.append(audit_row)
            if not replayed_from_checkpoint:
                batch_audit_rows.append(audit_row)

        if audit_checkpoint_callback and batch_audit_rows:
            audit_checkpoint_callback(batch_audit_rows)

    if parent_updates:
        update_keys = sorted({key for row in parent_updates for key in row.keys()})
        update_schema = {key: pl.Utf8 for key in update_keys}
        update_df = pl.DataFrame(parent_updates, schema=update_schema)
        merged = parents_df.join(update_df, on=group_cols, how="left", suffix="__web")
        merged_columns, _ = get_schema_and_column_names(merged)
        for key in update_keys:
            if key in group_cols:
                continue
            web_col = f"{key}__web"
            if web_col not in merged_columns or key not in merged_columns:
                continue
            merged = merged.with_columns(
                pl.when(_placeholder_expr(key) & pl.col(web_col).is_not_null())
                .then(pl.col(web_col))
                .otherwise(pl.col(key))
                .alias(key)
            ).drop(web_col)
            merged_columns = [col for col in merged_columns if col != web_col]
        parents_df = merged

    if variant_updates:
        update_keys = sorted({key for row in variant_updates for key in row.keys()})
        update_schema = {key: pl.Utf8 for key in update_keys}
        update_df = pl.DataFrame(variant_updates, schema=update_schema)
        merge_keys = ["retailer", "variant_id"]
        if not all(key in variants_df.columns for key in merge_keys):
            logging.warning("Skipping web variant updates: variant keys missing.")
        else:
            merged = variants_df.join(
                update_df, on=merge_keys, how="left", suffix="__web"
            )
            merged_columns, _ = get_schema_and_column_names(merged)
            for key in update_keys:
                if key in merge_keys:
                    continue
                web_col = f"{key}__web"
                if web_col not in merged_columns or key not in merged_columns:
                    continue
                merged = merged.with_columns(
                    pl.when(_placeholder_expr(key) & pl.col(web_col).is_not_null())
                    .then(pl.col(web_col))
                    .otherwise(pl.col(key))
                    .alias(key)
                ).drop(web_col)
                merged_columns = [col for col in merged_columns if col != web_col]
            variants_df = merged

    audit_df = pl.DataFrame(audit_rows) if audit_rows else pl.DataFrame()
    logging.info(
        "Web attribute fill summary: requests=%s replayed_requests=%s filled_requests=%s filled_parent_values=%s filled_variant_values=%s",
        sum(len(reqs) for reqs in requests_by_domain.values()),
        replayed_request_count,
        filled_request_count,
        filled_parent_values,
        filled_variant_values,
    )
    if suppressed_parent_no_value_attributes or suppressed_variant_no_value_attributes:
        logging.info(
            "Web attribute fill skipped attributes due to repeated no-value history: parent=%s variant=%s",
            suppressed_parent_no_value_attributes,
            suppressed_variant_no_value_attributes,
        )
    if suppressed_parent_sure_attributes or suppressed_variant_sure_attributes:
        logging.info(
            "Web attribute fill skipped attributes due to sure consensus lock: parent=%s variant=%s",
            suppressed_parent_sure_attributes,
            suppressed_variant_sure_attributes,
        )
    if low_coverage_parent_attributes or low_coverage_variant_attributes:
        logging.info(
            "Web attribute fill skipped attributes below %.0f%% coverage: parent=%s variant=%s",
            coverage_threshold * 100,
            low_coverage_parent_attributes,
            low_coverage_variant_attributes,
        )
    return parents_df, variants_df, audit_df


def _variant_match_key_expr(df: pl.DataFrame) -> pl.Expr | None:
    columns, _ = get_schema_and_column_names(df)
    if not columns:
        return None

    barcode_expr: pl.Expr | None = None
    if "barcode" in columns:
        barcode = pl.col("barcode").cast(pl.Utf8).str.strip_chars()
        barcode_expr = pl.when(barcode.is_not_null() & (barcode != "")).then(
            pl.concat_str([pl.lit("barcode:"), barcode])
        )

    shade_expr: pl.Expr | None = None
    shade_candidates: list[pl.Expr] = []
    if "shade_name_normalized" in columns:
        shade_candidates.append(pl.col("shade_name_normalized"))
    if "shade_name_raw" in columns:
        shade_candidates.append(pl.col("shade_name_raw"))
    if shade_candidates:
        shade = pl.coalesce(shade_candidates).cast(pl.Utf8).str.strip_chars()
        shade = pl.when(shade.is_not_null() & (shade != "")).then(
            shade.str.to_lowercase()
        )

        size_expr: pl.Expr | None = None
        if "size_text_raw" in columns:
            size = pl.col("size_text_raw").cast(pl.Utf8).str.strip_chars()
            size = pl.when(size.is_not_null() & (size != "")).then(
                size.str.to_lowercase()
            )
            size_expr = (
                pl.when(size.is_not_null())
                .then(pl.concat_str([pl.lit("|size:"), size]))
                .otherwise(pl.lit(""))
            )
        else:
            size_expr = pl.lit("")

        shade_expr = pl.when(shade.is_not_null()).then(
            pl.concat_str([pl.lit("shade:"), shade, size_expr])
        )

    if barcode_expr is None and shade_expr is None:
        return None

    candidates: list[pl.Expr] = []
    if barcode_expr is not None:
        candidates.append(barcode_expr)
    if shade_expr is not None:
        candidates.append(shade_expr)
    return pl.coalesce(candidates).alias("variant_match_key")


def _attribute_group_cols(df: pl.DataFrame) -> list[str]:
    columns, _ = get_schema_and_column_names(df)
    if "canonical_id" not in columns:
        return []
    group_cols = ["canonical_id"]
    if "category_key" in columns:
        group_cols.append("category_key")
    return group_cols


def _fill_variant_product_attributes_from_parents(
    variants_df: pl.DataFrame,
    parents_df: pl.DataFrame,
    *,
    product_scope_columns: Sequence[str],
) -> pl.DataFrame:
    """Propagate filled product-scoped attributes from parents to variants (within retailer)."""
    if variants_df.is_empty() or parents_df.is_empty():
        return variants_df
    if not {"retailer", "parent_product_id"}.issubset(set(variants_df.columns)):
        return variants_df
    if not {"retailer", "parent_product_id"}.issubset(set(parents_df.columns)):
        return variants_df

    available_columns = [
        col
        for col in product_scope_columns
        if col in variants_df.columns and col in parents_df.columns
    ]
    if not available_columns:
        return variants_df

    parent_lookup = parents_df.select(
        ["retailer", "parent_product_id", *available_columns]
    ).unique(subset=["retailer", "parent_product_id"])
    result = variants_df.join(
        parent_lookup,
        on=["retailer", "parent_product_id"],
        how="left",
        suffix="__parent",
    )
    placeholders = ATTRIBUTE_PLACEHOLDER_VALUES + [""]
    for attr in available_columns:
        parent_col = f"{attr}__parent"
        value = pl.col(attr).cast(pl.Utf8).str.strip_chars()
        lowered = value.str.to_lowercase()
        is_placeholder = (
            value.is_null()
            | (lowered == "")
            | lowered.is_in(placeholders)
            | lowered.str.starts_with("not in taxonomy")
        )
        if parent_col in result.columns:
            result = result.with_columns(
                pl.when(is_placeholder)
                .then(pl.col(parent_col))
                .otherwise(pl.col(attr))
                .alias(attr)
            ).drop(parent_col)
    return result


def _write_postfill_attribute_cache(
    *,
    parents_df: pl.DataFrame,
    variants_df: pl.DataFrame,
    parents_all_df: pl.DataFrame | None = None,
) -> None:
    parents_df = annotate_market_hybrid_claims(parents_df, record_type="parent")
    variants_df = annotate_market_hybrid_claims(variants_df, record_type="variant")
    if parents_all_df is not None:
        parents_all = annotate_market_hybrid_claims(
            parents_all_df, record_type="parent"
        )
    else:
        parents_all = parents_df

    POSTFILL_ATTRIBUTE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    parents_df.write_parquet(POSTFILL_PARENTS_OUTPUT)
    variants_df.write_parquet(POSTFILL_VARIANTS_OUTPUT)
    parents_all.write_parquet(POSTFILL_PARENTS_ALL_OUTPUT)

    parent_final = parents_df.with_columns(
        pl.lit("parent").alias("record_type"),
        pl.col("parent_product_id").alias("product"),
        pl.lit("").alias("variant"),
    )
    variant_final = variants_df.with_columns(
        pl.lit("variant").alias("record_type"),
        pl.col("parent_product_id").alias("product"),
        pl.col("variant_id").alias("variant"),
    )
    pl.concat([parent_final, variant_final], how="diagonal_relaxed").write_parquet(
        POSTFILL_COMBINED_OUTPUT
    )


def _merge_cache_with_base_delta(
    preferred: pl.DataFrame,
    fallback: pl.DataFrame,
    *,
    key_columns: Sequence[str],
    label: str,
) -> pl.DataFrame:
    """Append fallback rows missing from preferred cache by normalized key."""

    if preferred.is_empty():
        return fallback
    if fallback.is_empty():
        return preferred

    missing = [
        col
        for col in key_columns
        if col not in preferred.columns or col not in fallback.columns
    ]
    if missing:
        logging.warning(
            "Join cache merge skipped for %s; missing key columns=%s",
            label,
            missing,
        )
        return preferred

    key_aliases = [f"__merge_key_{idx}" for idx, _ in enumerate(key_columns)]

    def _with_keys(df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns(
            [
                pl.col(column)
                .cast(pl.Utf8)
                .fill_null("")
                .str.strip_chars()
                .alias(alias)
                for alias, column in zip(key_aliases, key_columns)
            ]
        )

    preferred_keys = _with_keys(preferred).select(key_aliases).unique()
    fallback_with_keys = _with_keys(fallback)
    delta = fallback_with_keys.join(preferred_keys, on=key_aliases, how="anti").drop(
        key_aliases
    )
    if delta.is_empty():
        return preferred

    merged = pl.concat([preferred, delta], how="diagonal_relaxed")
    logging.info(
        "Join cache merge (%s): preferred=%s fallback=%s added=%s merged=%s",
        label,
        preferred.height,
        fallback.height,
        delta.height,
        merged.height,
    )
    return merged


def _load_base_attribute_cache_for_join() -> (
    tuple[pl.DataFrame, pl.DataFrame, list[Path]]
):
    """Load the persisted catalog attribute cache as a join-time fallback."""

    pdp_store_path = enforce_default_pdp_store_path(DEFAULT_PDP_STORE_PATH)
    try:
        (
            parents_df,
            variants_df,
            _combined_df,
            _unmatched,
            parents_all_df,
            _unmatched_examples,
            _metadata,
        ) = load_persisted_pdp_attributes(pdp_store_path)
    except FileNotFoundError as exc:
        raise SystemExit(
            "Persisted PDP attribute cache not found in database."
        ) from exc

    parent_source = parents_all_df if not parents_all_df.is_empty() else parents_df
    variants_df = _normalize_catalog_variants(variants_df)
    parents_df = _normalize_catalog_parents(parent_source)
    logging.info(
        "Loaded persisted PDP attribute cache from database for join fallback "
        "(parents=%s variants=%s).",
        parents_df.height,
        variants_df.height,
    )
    return parents_df, variants_df, []


def _load_postfill_attribute_cache() -> (
    tuple[pl.DataFrame, pl.DataFrame, list[Path], str]
):
    """Load attribute cache for join stage, preferring mapped cache and falling back safely."""

    parents_path = POSTFILL_PARENTS_OUTPUT
    variants_path = POSTFILL_VARIANTS_OUTPUT
    if parents_path.is_file() and variants_path.is_file():
        parents_df = _normalize_catalog_parents(pl.read_parquet(parents_path))
        variants_df = _normalize_catalog_variants(pl.read_parquet(variants_path))
        base_parents_df, base_variants_df, base_variant_paths = (
            _load_base_attribute_cache_for_join()
        )
        merged_parents_df = _merge_cache_with_base_delta(
            parents_df,
            base_parents_df,
            key_columns=("retailer", "parent_product_id"),
            label="parents",
        )
        merged_variants_df = _merge_cache_with_base_delta(
            variants_df,
            base_variants_df,
            key_columns=("retailer", "variant_id"),
            label="variants",
        )
        source = (
            "shared_mapped_plus_base_delta"
            if (
                merged_parents_df.height != parents_df.height
                or merged_variants_df.height != variants_df.height
            )
            else "shared_mapped"
        )
        return (
            merged_parents_df,
            merged_variants_df,
            [variants_path, *base_variant_paths],
            source,
        )

    parents_df, variants_df, variant_paths = _load_base_attribute_cache_for_join()
    logging.warning(
        (
            "Shared mapped cache not found at %s. "
            "Falling back to the persisted PDP attribute cache in the database. "
            "Join will run, but attributes may be less complete."
        ),
        POSTFILL_ATTRIBUTE_CACHE_DIR,
    )
    return parents_df, variants_df, variant_paths, "base_cache"


def _fill_variant_attributes_from_other_retailers(
    variants_df: pl.DataFrame,
    *,
    retailer_priority: Sequence[str],
) -> pl.DataFrame:
    """Fill variant-scoped attributes across retailers during the pre-join pipeline.

    - For products where an attribute is stable across variants (<=1 meaningful value per retailer),
      resolve conflicts/fill using canonical_id grouping.
    - For products where an attribute varies by variant, only resolve/fill rows that have a
      non-ambiguous cross-retailer match key (barcode preferred, else shade+size).
    """

    if variants_df.is_empty() or "retailer" not in variants_df.columns:
        return variants_df

    group_cols = _attribute_group_cols(variants_df)
    if not group_cols or "variant_id" not in variants_df.columns:
        logging.info(
            "Skipping variant attribute fill: required keys missing from variant cache."
        )
        return variants_df

    taxonomy = get_attribute_taxonomy()
    variant_scope_cols = _taxonomy_variant_columns_any_category(variants_df, taxonomy)
    if not variant_scope_cols:
        return variants_df

    match_key_expr = _variant_match_key_expr(variants_df)

    result = variants_df
    for attribute in variant_scope_cols:
        meaningful = meaningful_value_expr(attribute).alias("__meaningful")
        per_retailer = (
            result.select([*group_cols, pl.col("retailer"), meaningful])
            .filter(pl.col("__meaningful").is_not_null())
            .group_by([*group_cols, "retailer"])
            .agg(pl.col("__meaningful").n_unique().alias("__distinct_meaningful"))
            .group_by(group_cols)
            .agg(pl.col("__distinct_meaningful").max().alias("__max_distinct"))
        )
        if per_retailer.is_empty():
            continue

        stable_groups = per_retailer.filter(pl.col("__max_distinct") <= 1).select(
            group_cols
        )
        varying_groups = per_retailer.filter(pl.col("__max_distinct") > 1).select(
            group_cols
        )

        if not stable_groups.is_empty():
            stable_subset = result.join(stable_groups, on=group_cols, how="inner")
            stable_subset = resolve_attribute_conflicts(
                stable_subset,
                retailer_priority=retailer_priority,
                group_cols=group_cols,
                attribute_columns=[attribute],
            )
            stable_subset = fill_missing_attribute_values(
                stable_subset,
                retailer_priority=retailer_priority,
                group_cols=group_cols,
                attribute_columns=[attribute],
            )
            stable_updates = stable_subset.select(
                ["retailer", "variant_id", pl.col(attribute).alias("__updated")]
            ).unique(subset=["retailer", "variant_id"])
            result = (
                result.join(stable_updates, on=["retailer", "variant_id"], how="left")
                .with_columns(
                    pl.coalesce([pl.col("__updated"), pl.col(attribute)]).alias(
                        attribute
                    )
                )
                .drop("__updated")
            )

        if (
            match_key_expr is None
            or varying_groups.is_empty()
            or not {"barcode", "shade_name_normalized", "shade_name_raw"}.intersection(
                result.columns
            )
        ):
            continue

        varying_subset = result.join(
            varying_groups, on=group_cols, how="inner"
        ).with_columns(match_key_expr)
        varying_subset = varying_subset.filter(
            pl.col("variant_match_key").is_not_null()
            & (pl.col("variant_match_key") != "")
        )
        if varying_subset.is_empty():
            continue

        ambiguous = (
            varying_subset.group_by([*group_cols, "retailer", "variant_match_key"])
            .agg(pl.len().alias("__rows"))
            .filter(pl.col("__rows") > 1)
            .select([*group_cols, "retailer", "variant_match_key"])
        )
        matchable = (
            varying_subset.join(
                ambiguous, on=[*group_cols, "retailer", "variant_match_key"], how="anti"
            )
            if not ambiguous.is_empty()
            else varying_subset
        )
        if matchable.is_empty():
            continue

        matchable = resolve_attribute_conflicts(
            matchable,
            retailer_priority=retailer_priority,
            group_cols=[*group_cols, "variant_match_key"],
            exclude_columns={"variant_match_key"},
            attribute_columns=[attribute],
        )
        matchable = fill_missing_attribute_values(
            matchable,
            retailer_priority=retailer_priority,
            group_cols=[*group_cols, "variant_match_key"],
            exclude_columns={"variant_match_key"},
            attribute_columns=[attribute],
        )
        match_updates = matchable.select(
            ["retailer", "variant_id", pl.col(attribute).alias("__updated")]
        ).unique(subset=["retailer", "variant_id"])
        result = (
            result.join(match_updates, on=["retailer", "variant_id"], how="left")
            .with_columns(
                pl.coalesce([pl.col("__updated"), pl.col(attribute)]).alias(attribute)
            )
            .drop("__updated")
        )

    return result


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return repair_text_encoding(str(value)).strip()


def _normalize_catalog_variants(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df
    columns, _ = get_schema_and_column_names(df)
    df = df.with_columns(
        [
            pl.col("retailer")
            .cast(pl.Utf8)
            .map_elements(_normalize_text)
            .str.to_lowercase()
            .alias("retailer"),
            pl.col("variant_id")
            .cast(pl.Utf8)
            .map_elements(_normalize_text)
            .alias("variant_id"),
            pl.col("parent_product_id")
            .cast(pl.Utf8)
            .map_elements(_normalize_text)
            .alias("parent_product_id"),
            pl.col("category_label")
            .cast(pl.Utf8)
            .map_elements(_normalize_text)
            .str.to_lowercase()
            .alias("category_label"),
            pl.col("brand").cast(pl.Utf8).map_elements(_normalize_text).alias("brand"),
            pl.col("product_name")
            .cast(pl.Utf8)
            .map_elements(_normalize_text)
            .alias("product_name"),
            (
                pl.col("backend_id")
                .cast(pl.Utf8)
                .map_elements(_normalize_text)
                .alias("backend_id")
                if "backend_id" in columns
                else pl.lit(None).cast(pl.Utf8).alias("backend_id")
            ),
            (
                pl.col("backend_parent_id")
                .cast(pl.Utf8)
                .map_elements(_normalize_text)
                .alias("backend_parent_id")
                if "backend_parent_id" in columns
                else pl.lit(None).cast(pl.Utf8).alias("backend_parent_id")
            ),
        ]
    )
    df = df.with_columns(
        [
            pl.when(
                pl.col("backend_id").is_not_null()
                & (pl.col("backend_id").cast(pl.Utf8).str.strip_chars() != "")
            )
            .then(pl.col("backend_id"))
            .otherwise(pl.col("variant_id"))
            .alias("variant_id_or_backend_id"),
            pl.when(
                pl.col("backend_parent_id").is_not_null()
                & (pl.col("backend_parent_id").cast(pl.Utf8).str.strip_chars() != "")
            )
            .then(pl.col("backend_parent_id"))
            .otherwise(pl.col("parent_product_id"))
            .alias("parent_product_id_or_backend_id"),
        ]
    )
    # Recompute canonical fields to keep join logic aligned with sales normalization.
    df = df.with_columns(
        [
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
        ]
    )
    df = df.with_columns(
        [
            pl.col("_canonical_struct")
            .struct.field("canonical_id")
            .alias("canonical_id"),
            pl.col("_canonical_struct").struct.field("brand_norm").alias("brand_norm"),
            pl.col("_canonical_struct")
            .struct.field("product_name_norm")
            .alias("product_name_norm"),
        ]
    ).drop("_canonical_struct")
    # Drop duplicate attribute columns that normalize to the same key (e.g., "free from" vs "free_from").
    seen_norm: set[str] = set()
    keep_cols: list[str] = []
    for col in df.columns:
        norm = col.strip().lower().replace(" ", "_")
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        keep_cols.append(col)
    return df.select(keep_cols)


def _normalize_catalog_parents(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df
    df = df.with_columns(
        [
            pl.col("retailer")
            .cast(pl.Utf8)
            .map_elements(_normalize_text)
            .str.to_lowercase()
            .alias("retailer"),
            pl.col("parent_product_id")
            .cast(pl.Utf8)
            .map_elements(_normalize_text)
            .alias("parent_product_id"),
            (
                pl.col("brand")
                .cast(pl.Utf8)
                .map_elements(_normalize_text)
                .alias("brand")
                if "brand" in df.columns
                else pl.lit(None).alias("brand")
            ),
            (
                pl.col("product_name")
                .cast(pl.Utf8)
                .map_elements(_normalize_text)
                .alias("product_name")
                if "product_name" in df.columns
                else pl.lit(None).alias("product_name")
            ),
            (
                pl.col("pdp_url")
                .cast(pl.Utf8)
                .map_elements(_normalize_text)
                .alias("pdp_url")
                if "pdp_url" in df.columns
                else pl.lit(None).alias("pdp_url")
            ),
        ]
    )
    if "brand" in df.columns and "product_name" in df.columns:
        df = df.with_columns(
            [
                pl.struct(["brand", "product_name"])
                .map_elements(
                    lambda row: (
                        lambda triple: {
                            "canonical_id": triple[0],
                            "brand_norm": triple[1],
                            "product_name_norm": triple[2],
                        }
                    )(
                        compute_canonical_values(
                            row.get("brand"), row.get("product_name")
                        )
                    ),
                    return_dtype=pl.Struct(
                        {
                            "canonical_id": pl.Utf8,
                            "brand_norm": pl.Utf8,
                            "product_name_norm": pl.Utf8,
                        }
                    ),
                )
                .alias("_canonical_struct")
            ]
        )
        df = df.with_columns(
            [
                pl.col("_canonical_struct")
                .struct.field("canonical_id")
                .alias("canonical_id"),
                pl.col("_canonical_struct")
                .struct.field("brand_norm")
                .alias("brand_norm"),
                pl.col("_canonical_struct")
                .struct.field("product_name_norm")
                .alias("product_name_norm"),
            ]
        ).drop("_canonical_struct")
    return df


def _log_duplicate_keys(df: pl.DataFrame, *, subset: Iterable[str], label: str) -> None:
    if df.is_empty():
        logging.info("%s: no rows to check for duplicates.", label)
        return
    subset_cols = [col for col in subset]
    missing = [col for col in subset_cols if col not in df.columns]
    if missing:
        logging.warning(
            "%s: cannot check duplicates; missing columns=%s", label, missing
        )
        return
    duplicate_rows = df.height - df.unique(subset=subset_cols).height
    if duplicate_rows <= 0:
        logging.info("%s: no duplicate keys on %s", label, subset_cols)
        return
    top_groups = (
        df.group_by(subset_cols)
        .len()
        .filter(pl.col("len") > 1)
        .sort("len", descending=True)
        .head(10)
        .to_dicts()
    )
    logging.warning(
        "%s: duplicate keys detected on %s (duplicate_rows=%s top=%s)",
        label,
        subset_cols,
        duplicate_rows,
        top_groups,
    )


__all__ = [
    "run_attribute_mapping",
    "run_attribute_mapping_vlm",
    "run_attribute_mapping_web",
]


def _normalize_attribute_mapping_steps(
    mapping_steps: Sequence[str] | str | None,
) -> tuple[str, ...]:
    if mapping_steps is None:
        return ("vision",)
    if isinstance(mapping_steps, str):
        raw_steps = [item.strip() for item in mapping_steps.split(",")]
    else:
        raw_steps = [str(item).strip() for item in mapping_steps]
    normalized: list[str] = []
    for raw_step in raw_steps:
        step = raw_step.lower()
        if not step:
            continue
        if step == "all":
            for candidate in ("vision", "web"):
                if candidate not in normalized:
                    normalized.append(candidate)
            continue
        if step == "vlm":
            step = "vision"
        if step not in {"vision", "web"}:
            raise SystemExit(f"Unsupported attribute mapping step: {raw_step}")
        if step not in normalized:
            normalized.append(step)
    if not normalized:
        raise SystemExit("At least one attribute mapping step is required.")
    return tuple(normalized)


def _normalize_attribute_mapping_categories(
    categories: Sequence[str] | str | None,
) -> tuple[str, ...]:
    if categories is None:
        return ()
    raw_values = [categories] if isinstance(categories, str) else list(categories)
    normalized: list[str] = []
    for value in raw_values:
        text = _normalize_key(value)
        if text and text not in normalized:
            normalized.append(text)
    return tuple(normalized)


def _load_attribute_mapping_inputs(
    *,
    active_mapping_steps: tuple[str, ...],
    retailer_scope: Sequence[str] | None = None,
    category_scope: Sequence[str] | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    parents_df, variants_df = load_pdp_attribute_mapping_inputs(
        DEFAULT_PDP_STORE_PATH,
        retailers=retailer_scope,
        categories=category_scope,
    )
    logging.info(
        (
            "Loaded PDP attribute mapping input from database: "
            "steps=%s parent_rows=%s variant_rows=%s retailers=%s categories=%s"
        ),
        ",".join(active_mapping_steps),
        parents_df.height,
        variants_df.height,
        ",".join(retailer_scope or ()) if retailer_scope else "all",
        ",".join(category_scope or ()) if category_scope else "all",
    )
    variants_df = _normalize_catalog_variants(variants_df)
    _log_duplicate_keys(
        variants_df,
        subset=("retailer", "variant_id"),
        label="Catalog variants from PDP database",
    )
    parents_df = _normalize_catalog_parents(parents_df)
    return parents_df, variants_df


def run_attribute_mapping(
    mapping_steps: Sequence[str] | str | None = None,
    retailers: Sequence[str] | str | None = None,
    categories: Sequence[str] | str | None = None,
) -> None:
    """Run shared PDP attribute enrichment without loading or joining sales CSVs."""

    active_mapping_steps = _normalize_attribute_mapping_steps(mapping_steps)
    run_vision_step = "vision" in active_mapping_steps
    run_web_step = "web" in active_mapping_steps
    retailer_scope = normalize_retailer_scope(retailers)
    category_scope = _normalize_attribute_mapping_categories(categories)
    logging.info(
        (
            "Running PDP database attribute mapping without loading sales data. "
            "steps=%s retailers=%s categories=%s db_output=%s"
        ),
        ",".join(active_mapping_steps),
        ",".join(retailer_scope) if retailer_scope else "all",
        ",".join(category_scope) if category_scope else "all",
        MAPPING_DIR,
    )

    parents_df, variants_df = _load_attribute_mapping_inputs(
        active_mapping_steps=active_mapping_steps,
        retailer_scope=retailer_scope,
        category_scope=category_scope,
    )

    if retailer_scope:
        parents_df = filter_frame_by_retailers(parents_df, retailer_scope)
        variants_df = filter_frame_by_retailers(variants_df, retailer_scope)
        logging.info(
            "Scoped attribute mapping to retailers=%s parent_rows=%s variant_rows=%s",
            ",".join(retailer_scope),
            parents_df.height,
            variants_df.height,
        )
    if parents_df.is_empty() and variants_df.is_empty():
        scope_parts = []
        if retailer_scope:
            scope_parts.append("retailers=" + ",".join(retailer_scope))
        if category_scope:
            scope_parts.append("categories=" + ",".join(category_scope))
        scope_text = " ".join(scope_parts) if scope_parts else "all"
        raise SystemExit("No PDP database rows found for mapping scope: " + scope_text)

    taxonomy = get_attribute_taxonomy()
    meta_by_id = _taxonomy_attribute_meta_by_id(taxonomy)
    parent_product_scope_cols, _ = _taxonomy_attribute_columns_by_scope(
        parents_df, meta_by_id
    )

    conflicts_df = map_attribute_conflicts(
        parents_df,
        retailer_priority=ATTRIBUTE_RETAILER_PRIORITY,
        attribute_columns=parent_product_scope_cols,
    )
    logging.info("Mapped attribute conflicts rows=%s.", conflicts_df.height)

    parents_df = resolve_attribute_conflicts(
        parents_df,
        retailer_priority=ATTRIBUTE_RETAILER_PRIORITY,
        attribute_columns=parent_product_scope_cols,
    )

    na_fill_df = map_attribute_na_fill_candidates(
        parents_df,
        retailer_priority=ATTRIBUTE_RETAILER_PRIORITY,
        attribute_columns=parent_product_scope_cols,
    )
    logging.info("Mapped attribute N/A fill candidate rows=%s.", na_fill_df.height)

    audit_records: list[AttributeAuditRecord] = []
    resolution_run_id = attribute_resolution_history.build_run_id(
        "attribute-mapping-" + "-".join(active_mapping_steps)
    )
    vision_checkpoint_rows = 0
    vision_checkpoint_chunks = 0
    vision_checkpoint_paths: list[Path] = []
    vision_checkpoint_audit_records = 0
    web_checkpoint_rows = 0
    web_checkpoint_chunks = 0
    web_checkpoint_paths: list[Path] = []
    web_checkpoint_audit_records = 0
    fill_state = _read_attribute_fill_state()
    resume_from_checkpoints = (
        str(fill_state.get("status") or "").strip().lower() == "running"
    )
    last_success_epoch = _latest_success_epoch_seconds()
    vision_checkpoint_response_map: dict[str, object] = {}
    web_checkpoint_response_map: dict[str, object] = {}
    if resume_from_checkpoints:
        vision_resume_rows = (
            _read_checkpoint_rows_since_success(
                VISION_FILL_AUDIT_CHECKPOINT_DIR,
                success_epoch_seconds=last_success_epoch,
            )
            if run_vision_step
            else pl.DataFrame()
        )
        web_resume_rows = (
            _read_checkpoint_rows_since_success(
                WEB_FILL_AUDIT_CHECKPOINT_DIR,
                success_epoch_seconds=last_success_epoch,
            )
            if run_web_step
            else pl.DataFrame()
        )
        vision_checkpoint_response_map = _checkpoint_response_map(vision_resume_rows)
        web_checkpoint_response_map = _checkpoint_response_map(web_resume_rows)
        logging.info(
            "Resuming from pending checkpoints: vision_requests=%s web_requests=%s",
            len(vision_checkpoint_response_map),
            len(web_checkpoint_response_map),
        )
    else:
        stale_vision_chunks = (
            _clear_checkpoint_dir(VISION_FILL_AUDIT_CHECKPOINT_DIR)
            if run_vision_step
            else 0
        )
        stale_web_chunks = (
            _clear_checkpoint_dir(WEB_FILL_AUDIT_CHECKPOINT_DIR) if run_web_step else 0
        )
        if stale_vision_chunks or stale_web_chunks:
            logging.info(
                "Discarded stale checkpoint chunks before fresh mapping run: "
                "vision_chunks=%s web_chunks=%s",
                stale_vision_chunks,
                stale_web_chunks,
            )
    _write_attribute_fill_state(status="running", run_id=resolution_run_id)

    def _persist_vision_audit_checkpoint(rows: Sequence[dict[str, Any]]) -> None:
        nonlocal vision_checkpoint_rows
        nonlocal vision_checkpoint_chunks
        nonlocal vision_checkpoint_audit_records
        if not rows:
            return
        vision_checkpoint_chunks += 1
        chunk_path = _write_vision_audit_checkpoint_chunk(
            rows,
            run_id=resolution_run_id,
            chunk_index=vision_checkpoint_chunks,
        )
        if chunk_path is not None:
            vision_checkpoint_paths.append(chunk_path)
        vision_checkpoint_rows += len(rows)
        rows_df = pl.from_dicts(
            rows,
            strict=False,
            infer_schema_length=None,
        )
        records = _collect_vision_audit(rows_df)
        if not records:
            return
        _append_attribute_audit(records)
        vision_checkpoint_audit_records += len(records)
        resolution_rows = _collect_resolution_history_rows(
            records,
            parents_df=parents_df,
            variants_df=variants_df,
            run_id=resolution_run_id,
        )
        if resolution_rows:
            attribute_resolution_history.append_resolution_ledger_rows(resolution_rows)

    def _persist_web_audit_checkpoint(rows: Sequence[dict[str, Any]]) -> None:
        nonlocal web_checkpoint_rows
        nonlocal web_checkpoint_chunks
        nonlocal web_checkpoint_audit_records
        if not rows:
            return
        web_checkpoint_chunks += 1
        chunk_path = _write_web_audit_checkpoint_chunk(
            rows,
            run_id=resolution_run_id,
            chunk_index=web_checkpoint_chunks,
        )
        if chunk_path is not None:
            web_checkpoint_paths.append(chunk_path)
        web_checkpoint_rows += len(rows)
        rows_df = pl.from_dicts(
            rows,
            strict=False,
            infer_schema_length=None,
        )
        records = _collect_web_audit(rows_df)
        if not records:
            return
        _append_attribute_audit(records)
        web_checkpoint_audit_records += len(records)
        resolution_rows = _collect_resolution_history_rows(
            records,
            parents_df=parents_df,
            variants_df=variants_df,
            run_id=resolution_run_id,
        )
        if resolution_rows:
            attribute_resolution_history.append_resolution_ledger_rows(resolution_rows)

    before_parents = parents_df.clone()
    parents_df = fill_missing_attribute_values(
        parents_df,
        retailer_priority=ATTRIBUTE_RETAILER_PRIORITY,
        attribute_columns=parent_product_scope_cols,
    )
    audit_records.extend(
        _collect_parent_fill_audit(
            before_parents,
            parents_df,
            parent_product_scope_cols,
            decision_rule="cross_retailer_fill",
            evidence={"retailer_priority": ATTRIBUTE_RETAILER_PRIORITY},
        )
    )

    product_scope_cols, variant_scope_cols = _taxonomy_attribute_columns_by_scope(
        variants_df, meta_by_id
    )

    before_variants = variants_df.clone()
    variants_df = _fill_variant_attributes_from_other_retailers(
        variants_df, retailer_priority=ATTRIBUTE_RETAILER_PRIORITY
    )
    audit_records.extend(
        _collect_variant_fill_audit(
            before_variants,
            variants_df,
            variant_scope_cols,
            decision_rule="cross_retailer_fill",
            evidence={"retailer_priority": ATTRIBUTE_RETAILER_PRIORITY},
        )
    )

    before_variants = variants_df.clone()
    variants_df = _fill_variant_product_attributes_from_parents(
        variants_df,
        parents_df,
        product_scope_columns=product_scope_cols,
    )
    audit_records.extend(
        _collect_variant_fill_audit(
            before_variants,
            variants_df,
            product_scope_cols,
            decision_rule="parent_propagation",
            evidence={"rule": "parent_to_variant"},
        )
    )
    parents_df, variants_df, sure_parent_updates, sure_variant_updates = (
        _apply_sure_consensus_values(
            parents_df,
            variants_df,
            meta_by_id=meta_by_id,
        )
    )
    logging.info(
        "Consensus prefill before vision/web: parent_updates=%s variant_updates=%s",
        sure_parent_updates,
        sure_variant_updates,
    )
    session = SessionContext.from_state({})
    init_llm_wrapper("", session=session)
    llm_wrapper = session.state["llm_wrapper"]

    if run_vision_step:
        parents_df, vision_audit_df = _fill_parent_attributes_from_images(
            parents_df,
            taxonomy=taxonomy,
            llm_wrapper=llm_wrapper,
            retailer_priority=ATTRIBUTE_RETAILER_PRIORITY,
            min_attribute_coverage=MIN_LLM_ATTRIBUTE_COVERAGE,
            checkpoint_response_by_key=vision_checkpoint_response_map,
            audit_checkpoint_callback=_persist_vision_audit_checkpoint,
        )
        logging.info(
            "Collected vision attribute fill audit rows=%s.", vision_audit_df.height
        )
        vision_new_audit_df = _non_replayed_audit_rows(vision_audit_df)
        if vision_checkpoint_rows:
            if vision_new_audit_df.height != vision_checkpoint_rows:
                logging.warning(
                    "Vision audit checkpoint row mismatch: "
                    "checkpointed=%s final_csv_rows=%s",
                    vision_checkpoint_rows,
                    vision_new_audit_df.height,
                )
            logging.info(
                "Persisted vision audit checkpoints: "
                "rows=%s chunks=%s audit_records=%s",
                vision_checkpoint_rows,
                vision_checkpoint_chunks,
                vision_checkpoint_audit_records,
            )
        elif not vision_new_audit_df.is_empty():
            audit_records.extend(_collect_vision_audit(vision_new_audit_df))

    before_variants = variants_df.clone()
    variants_df = _fill_variant_product_attributes_from_parents(
        variants_df,
        parents_df,
        product_scope_columns=product_scope_cols,
    )
    audit_records.extend(
        _collect_variant_fill_audit(
            before_variants,
            variants_df,
            product_scope_cols,
            decision_rule="parent_propagation",
            evidence={"rule": "parent_to_variant"},
        )
    )
    if run_web_step:
        parents_df, variants_df, web_audit_df = _fill_attributes_from_web(
            parents_df,
            variants_df,
            taxonomy=taxonomy,
            llm_wrapper=llm_wrapper,
            retailer_priority=ATTRIBUTE_RETAILER_PRIORITY,
            min_attribute_coverage=MIN_LLM_ATTRIBUTE_COVERAGE,
            checkpoint_response_by_key=web_checkpoint_response_map,
            audit_checkpoint_callback=_persist_web_audit_checkpoint,
        )
        logging.info("Collected web attribute fill audit rows=%s.", web_audit_df.height)
        web_new_audit_df = _non_replayed_audit_rows(web_audit_df)
        if web_checkpoint_rows:
            if web_new_audit_df.height != web_checkpoint_rows:
                logging.warning(
                    "Web audit checkpoint row mismatch: "
                    "checkpointed=%s final_csv_rows=%s",
                    web_checkpoint_rows,
                    web_new_audit_df.height,
                )
            logging.info(
                "Persisted web audit checkpoints: rows=%s chunks=%s audit_records=%s",
                web_checkpoint_rows,
                web_checkpoint_chunks,
                web_checkpoint_audit_records,
            )
        elif not web_new_audit_df.is_empty():
            audit_records.extend(_collect_web_audit(web_new_audit_df))

    before_variants = variants_df.clone()
    variants_df = _fill_variant_product_attributes_from_parents(
        variants_df,
        parents_df,
        product_scope_columns=product_scope_cols,
    )
    audit_records.extend(
        _collect_variant_fill_audit(
            before_variants,
            variants_df,
            product_scope_cols,
            decision_rule="parent_propagation",
            evidence={"rule": "parent_to_variant"},
        )
    )
    _append_attribute_audit(audit_records)
    resolution_rows = _collect_resolution_history_rows(
        audit_records,
        parents_df=parents_df,
        variants_df=variants_df,
        run_id=resolution_run_id,
    )
    current_meaningful_keys = {
        _resolution_row_key(row)
        for row in resolution_rows
        if _resolution_row_has_meaningful_value(row)
    }
    existing_run_keys = _load_existing_resolution_run_keys(resolution_run_id)
    existing_run_keys.update(current_meaningful_keys)
    snapshot_rows = _collect_resolution_snapshot_rows(
        parents_df=parents_df,
        variants_df=variants_df,
        meta_by_id=meta_by_id,
        run_id=resolution_run_id,
        skip_keys=existing_run_keys,
        allowed_keys=None,
    )
    if snapshot_rows:
        resolution_rows.extend(snapshot_rows)
    resolution_consensus_rows = 0
    if resolution_rows:
        attribute_resolution_history.append_resolution_ledger_rows(resolution_rows)
        resolution_consensus_df = (
            attribute_resolution_history.write_resolution_consensus()
        )
        resolution_consensus_rows = resolution_consensus_df.height
    logging.info(
        "Wrote attribute resolution history rows=%s snapshot_rows=%s "
        "consensus_rows=%s",
        len(resolution_rows),
        len(snapshot_rows),
        resolution_consensus_rows,
    )
    _write_attribute_fill_state(status="success", run_id=resolution_run_id)
    cleared_vision_chunks = (
        _clear_checkpoint_dir(VISION_FILL_AUDIT_CHECKPOINT_DIR)
        if run_vision_step
        else 0
    )
    cleared_web_chunks = (
        _clear_checkpoint_dir(WEB_FILL_AUDIT_CHECKPOINT_DIR) if run_web_step else 0
    )
    if cleared_vision_chunks or cleared_web_chunks:
        logging.info(
            "Cleared attribute fill checkpoints after successful mapping: "
            "vision_chunks=%s web_chunks=%s",
            cleared_vision_chunks,
            cleared_web_chunks,
        )

    logging.info(
        "Completed shared attribute mapping stage. Outputs at %s",
        MAPPING_DIR,
    )


def run_attribute_mapping_vlm(
    retailers: Sequence[str] | str | None = None,
    categories: Sequence[str] | str | None = None,
) -> None:
    """Run only the image/VLM PDP attribute enrichment step."""
    run_attribute_mapping(
        mapping_steps="vision", retailers=retailers, categories=categories
    )


def run_attribute_mapping_web(
    retailers: Sequence[str] | str | None = None,
    categories: Sequence[str] | str | None = None,
) -> None:
    """Run only the web-search PDP attribute enrichment step."""
    run_attribute_mapping(
        mapping_steps="web", retailers=retailers, categories=categories
    )
