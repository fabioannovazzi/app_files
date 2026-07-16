from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import polars as pl

from modules.pdp.taxonomy_review_queue import candidate_run_root

__all__ = [
    "build_phase1_deterministic_policy_candidate_run",
    "build_policy_context",
    "load_deterministic_policy_aggregated_candidate_row",
]


_JSON_COLUMNS = {
    "evidence_summary_json",
    "current_allowed_sources_json",
    "current_blocked_sources_json",
    "conflicting_value_ids_json",
    "conflicting_terms_json",
}

_AGGREGATED_SCHEMA: dict[str, pl.DataType] = {
    "candidate_domain": pl.Utf8,
    "candidate_type": pl.Utf8,
    "candidate_key": pl.Utf8,
    "category_key": pl.Utf8,
    "attribute_id": pl.Utf8,
    "value_id": pl.Utf8,
    "support_product_count": pl.Int64,
    "support_retailer_count": pl.Int64,
    "confidence_level": pl.Utf8,
    "decision_ease": pl.Utf8,
    "evidence_summary_json": pl.Utf8,
    "created_from_run_id": pl.Utf8,
    "priority_score": pl.Float64,
    "label_text": pl.Utf8,
    "source_channel": pl.Utf8,
    "current_allowed_sources_json": pl.Utf8,
    "current_blocked_sources_json": pl.Utf8,
    "conflicting_value_ids_json": pl.Utf8,
    "conflicting_terms_json": pl.Utf8,
}

_SURFACED_SCHEMA: dict[str, pl.DataType] = {
    "candidate_domain": pl.Utf8,
    "candidate_type": pl.Utf8,
    "candidate_key": pl.Utf8,
    "aggregated_row_ref": pl.Utf8,
    "category_key": pl.Utf8,
    "attribute_id": pl.Utf8,
    "value_id": pl.Utf8,
    "title": pl.Utf8,
    "short_reason": pl.Utf8,
    "priority_score": pl.Float64,
    "confidence_level": pl.Utf8,
    "decision_ease": pl.Utf8,
    "support_product_count": pl.Int64,
    "support_retailer_count": pl.Int64,
    "evidence_signature": pl.Utf8,
    "run_id": pl.Utf8,
    "origin": pl.Utf8,
}

_RISKY_SOURCES = frozenset({"reviews", "ingredients", "usage", "restrictions"})
_PLACEHOLDER_VALUES = frozenset(
    {"", "n/a", "na", "none", "unknown", "n/a_(not_stated)", "not_stated"}
)
_PHRASE_MIN_SUPPORT_PRODUCTS = 8
_PHRASE_MIN_SUPPORT_RETAILERS = 2
_PHRASE_MIN_AGREEMENT_RATE = 0.9
_PHRASE_MAX_WORDS = 6
_PHRASE_MAX_CHARS = 80
_SEGMENT_SCHEMA: dict[str, pl.DataType] = {
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


def _normalize_key(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "_")


def _normalize_text(value: object | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _rows_to_frame(
    rows: list[dict[str, Any]],
    schema: Mapping[str, pl.DataType],
) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=list(schema.items()))
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized: dict[str, Any] = {}
        for key in schema:
            value = row.get(key)
            if key in _JSON_COLUMNS and value is not None and not isinstance(value, str):
                normalized[key] = _json_text(value)
            else:
                normalized[key] = value
        normalized_rows.append(normalized)
    return pl.DataFrame(normalized_rows, schema=dict(schema), orient="row")


def _write_frame(df: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)


def _attribute_cache_dir(pdp_store_path: Path | str) -> Path:
    path = Path(pdp_store_path)
    return path.parent / f"{path.stem}_attribute_cache"


def _empty_segment_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=list(_SEGMENT_SCHEMA.items()))


def _concat_frames(frames: list[pl.DataFrame]) -> pl.DataFrame:
    if not frames:
        return pl.DataFrame()
    if len(frames) == 1:
        return frames[0]
    return pl.concat(frames, how="diagonal_relaxed")


def _iter_cache_retailers(pdp_store_path: Path | str) -> list[str]:
    root = _attribute_cache_dir(pdp_store_path)
    if not root.exists():
        return []
    retailers = [path.name for path in root.iterdir() if path.is_dir()]
    return sorted(retailers)


def _load_segments(pdp_store_path: Path | str) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for retailer in _iter_cache_retailers(pdp_store_path):
        path = _attribute_cache_dir(pdp_store_path) / retailer / "segments.parquet"
        if not path.exists():
            continue
        frames.append(pl.read_parquet(path))
    if not frames:
        return _empty_segment_frame()
    return _concat_frames(frames)


def _load_assignment_rows(pdp_store_path: Path | str) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for retailer in _iter_cache_retailers(pdp_store_path):
        root = _attribute_cache_dir(pdp_store_path) / retailer
        parent_path = root / "parents.parquet"
        variant_path = root / "variants.parquet"
        if parent_path.exists():
            parent_df = pl.read_parquet(parent_path)
            if not parent_df.is_empty():
                frames.append(
                    parent_df.with_columns(
                        pl.lit("parent").alias("row_type"),
                        pl.lit("").alias("variant_id"),
                        pl.col("product_name").alias("display_name"),
                    )
                )
        if variant_path.exists():
            variant_df = pl.read_parquet(variant_path)
            if not variant_df.is_empty():
                frames.append(
                    variant_df.with_columns(
                        pl.lit("variant").alias("row_type"),
                        pl.concat_str(
                            [
                                pl.col("product_name").fill_null(""),
                                pl.when(pl.col("shade_name_raw").fill_null("") != "")
                                .then(pl.lit(" - "))
                                .otherwise(pl.lit("")),
                                pl.col("shade_name_raw").fill_null(""),
                            ]
                        )
                        .str.strip_chars()
                        .alias("display_name"),
                    )
                )
    return _concat_frames(frames)


def _normalize_assignment_value(value: object | None) -> str:
    normalized = _normalize_key(value)
    if not normalized or normalized in _PLACEHOLDER_VALUES:
        return ""
    if normalized.startswith("not_in_taxonomy"):
        return ""
    return normalized


def _is_candidate_phrase(text: object | None) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    if len(normalized) > _PHRASE_MAX_CHARS:
        return False
    if len(normalized.split()) > _PHRASE_MAX_WORDS:
        return False
    if any(mark in normalized for mark in ".!?"):
        return False
    if any(char.isdigit() for char in normalized):
        return False
    return True


def _iter_leaf_nodes(nodes: Iterable[Mapping[str, Any]]) -> Iterable[dict[str, Any]]:
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        children = node.get("children")
        if isinstance(children, list) and children:
            yield from _iter_leaf_nodes(children)
            continue
        value_id = _normalize_key(node.get("id") or node.get("label"))
        if not value_id:
            continue
        yield {
            "value_id": value_id,
            "label": str(node.get("label") or node.get("id") or "").strip(),
            "synonyms": [
                str(item).strip()
                for item in (node.get("synonyms") or [])
                if str(item).strip()
            ],
        }


def _taxonomy_attribute_terms(
    taxonomy: Mapping[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    attributes: dict[tuple[str, str], dict[str, Any]] = {}
    for category in taxonomy.get("categories") or []:
        if not isinstance(category, Mapping):
            continue
        category_key = _normalize_key(category.get("id") or category.get("label"))
        if not category_key:
            continue
        for attribute in category.get("attributes") or []:
            if not isinstance(attribute, Mapping):
                continue
            attribute_id = _normalize_key(attribute.get("id") or attribute.get("label"))
            if not attribute_id:
                continue
            leaves = list(_iter_leaf_nodes(attribute.get("nodes") or []))
            term_index: dict[str, list[dict[str, str]]] = {}
            value_map = {leaf["value_id"]: leaf for leaf in leaves}
            for leaf in leaves:
                if leaf["value_id"] in {"unknown", "other"}:
                    continue
                label_text = str(leaf["label"]).strip()
                normalized_label = _normalize_text(label_text)
                if normalized_label:
                    term_index.setdefault(normalized_label, []).append(
                        {
                            "value_id": leaf["value_id"],
                            "role": "label",
                            "text": label_text,
                        }
                    )
                for synonym in leaf["synonyms"]:
                    normalized_synonym = _normalize_text(synonym)
                    if normalized_synonym:
                        term_index.setdefault(normalized_synonym, []).append(
                            {
                                "value_id": leaf["value_id"],
                                "role": "synonym",
                                "text": synonym,
                            }
                        )
            attributes[(category_key, attribute_id)] = {
                "hierarchical": bool(attribute.get("hierarchical")),
                "selection": str(attribute.get("selection") or "single").strip(),
                "values": value_map,
                "term_index": term_index,
            }
    return attributes


def build_policy_context(
    config: Mapping[str, Any],
    *,
    category_key: str,
    attribute_id: str,
    value_id: str | None = None,
) -> dict[str, Any]:
    categories = config.get("categories") or {}
    if not isinstance(categories, Mapping):
        return {"category_key": category_key, "attribute_id": attribute_id, "value_id": value_id}
    category_block = categories.get(category_key) or {}
    if not isinstance(category_block, Mapping):
        return {"category_key": category_key, "attribute_id": attribute_id, "value_id": value_id}
    attributes = category_block.get("attributes") or {}
    if not isinstance(attributes, Mapping):
        return {"category_key": category_key, "attribute_id": attribute_id, "value_id": value_id}
    attribute_block = attributes.get(attribute_id) or {}
    if not isinstance(attribute_block, Mapping):
        return {"category_key": category_key, "attribute_id": attribute_id, "value_id": value_id}
    value_block: Mapping[str, Any] | None = None
    if value_id:
        raw_values = attribute_block.get("values") or {}
        if isinstance(raw_values, Mapping):
            candidate = raw_values.get(value_id)
            if isinstance(candidate, Mapping):
                value_block = candidate
    return {
        "category_key": category_key,
        "attribute_id": attribute_id,
        "value_id": value_id,
        "allowed_sources": list(attribute_block.get("allowed_sources") or []),
        "blocked_sources": list(attribute_block.get("blocked_sources") or []),
        "conflict_resolution": str(attribute_block.get("conflict_resolution") or "na"),
        "value_policy": dict(value_block or {}),
    }


def _disable_bare_label_rows(
    config: Mapping[str, Any],
    taxonomy: Mapping[str, Any],
    *,
    run_id: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    taxonomy_index = _taxonomy_attribute_terms(taxonomy)
    categories = config.get("categories") or {}
    if not isinstance(categories, Mapping):
        return rows
    for raw_category_key, raw_category_block in dict(categories).items():
        category_key = _normalize_key(raw_category_key)
        if not category_key or not isinstance(raw_category_block, Mapping):
            continue
        attributes = raw_category_block.get("attributes") or {}
        if not isinstance(attributes, Mapping):
            continue
        for raw_attribute_id, raw_attribute_block in dict(attributes).items():
            attribute_id = _normalize_key(raw_attribute_id)
            if not attribute_id or not isinstance(raw_attribute_block, Mapping):
                continue
            taxonomy_context = taxonomy_index.get((category_key, attribute_id))
            if not taxonomy_context:
                continue
            values = raw_attribute_block.get("values") or {}
            if not isinstance(values, Mapping):
                continue
            for raw_value_id, raw_value_block in dict(values).items():
                value_id = _normalize_key(raw_value_id)
                if not value_id or not isinstance(raw_value_block, Mapping):
                    continue
                if not bool(raw_value_block.get("allow_label")):
                    continue
                leaf = taxonomy_context["values"].get(value_id)
                if not isinstance(leaf, Mapping):
                    continue
                label_text = str(leaf.get("label") or value_id).strip()
                normalized_label = _normalize_text(label_text)
                if not normalized_label:
                    continue
                occurrences = [
                    occurrence
                    for occurrence in taxonomy_context["term_index"].get(normalized_label, [])
                    if _normalize_key(occurrence.get("value_id")) != value_id
                ]
                if not occurrences:
                    continue
                conflicting_value_ids = sorted(
                    {
                        _normalize_key(occurrence.get("value_id"))
                        for occurrence in occurrences
                        if _normalize_key(occurrence.get("value_id"))
                    }
                )
                candidate_key = (
                    f"disable_bare_label|{category_key}|{attribute_id}|{value_id}"
                )
                rows.append(
                    {
                        "candidate_domain": "deterministic_policy",
                        "candidate_type": "disable_bare_label",
                        "candidate_key": candidate_key,
                        "category_key": category_key,
                        "attribute_id": attribute_id,
                        "value_id": value_id,
                        "support_product_count": len(conflicting_value_ids),
                        "support_retailer_count": None,
                        "confidence_level": "high",
                        "decision_ease": "easy",
                        "evidence_summary_json": {
                            "label_text": label_text,
                            "conflicting_value_ids": conflicting_value_ids,
                            "conflicting_terms": occurrences,
                        },
                        "created_from_run_id": run_id,
                        "priority_score": 950.0,
                        "label_text": label_text,
                        "conflicting_value_ids_json": conflicting_value_ids,
                        "conflicting_terms_json": occurrences,
                    }
                )
    return rows


def _block_bad_source_rows(
    config: Mapping[str, Any],
    *,
    run_id: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    categories = config.get("categories") or {}
    if not isinstance(categories, Mapping):
        return rows
    for raw_category_key, raw_category_block in dict(categories).items():
        category_key = _normalize_key(raw_category_key)
        if not category_key or not isinstance(raw_category_block, Mapping):
            continue
        attributes = raw_category_block.get("attributes") or {}
        if not isinstance(attributes, Mapping):
            continue
        for raw_attribute_id, raw_attribute_block in dict(attributes).items():
            attribute_id = _normalize_key(raw_attribute_id)
            if not attribute_id or not isinstance(raw_attribute_block, Mapping):
                continue
            allowed_sources = [
                _normalize_text(item)
                for item in (raw_attribute_block.get("allowed_sources") or [])
                if _normalize_text(item)
            ]
            blocked_sources = [
                _normalize_text(item)
                for item in (raw_attribute_block.get("blocked_sources") or [])
                if _normalize_text(item)
            ]
            risky_allowed = [source for source in allowed_sources if source in _RISKY_SOURCES]
            for source_channel in risky_allowed:
                candidate_key = (
                    f"block_bad_source|{category_key}|{attribute_id}|{source_channel}"
                )
                rows.append(
                    {
                        "candidate_domain": "deterministic_policy",
                        "candidate_type": "block_bad_source",
                        "candidate_key": candidate_key,
                        "category_key": category_key,
                        "attribute_id": attribute_id,
                        "value_id": "",
                        "support_product_count": len(allowed_sources),
                        "support_retailer_count": None,
                        "confidence_level": "high",
                        "decision_ease": "easy",
                        "evidence_summary_json": {
                            "source_channel": source_channel,
                            "current_allowed_sources": allowed_sources,
                            "current_blocked_sources": blocked_sources,
                        },
                        "created_from_run_id": run_id,
                        "priority_score": 900.0,
                        "source_channel": source_channel,
                        "current_allowed_sources_json": allowed_sources,
                        "current_blocked_sources_json": blocked_sources,
                    }
                )
    return rows


def _add_deterministic_expression_rows(
    config: Mapping[str, Any],
    taxonomy: Mapping[str, Any],
    *,
    pdp_store_path: Path | str,
    run_id: str,
) -> list[dict[str, Any]]:
    segments = _load_segments(pdp_store_path)
    assignments = _load_assignment_rows(pdp_store_path)
    if segments.is_empty() or assignments.is_empty():
        return []

    joined = segments.join(
        assignments,
        on=["retailer", "row_type", "parent_product_id", "variant_id", "category_key"],
        how="inner",
    )
    if joined.is_empty():
        return []

    taxonomy_index = _taxonomy_attribute_terms(taxonomy)
    rows: list[dict[str, Any]] = []
    categories = config.get("categories") or {}
    if not isinstance(categories, Mapping):
        return rows

    for raw_category_key, raw_category_block in dict(categories).items():
        category_key = _normalize_key(raw_category_key)
        if not category_key or not isinstance(raw_category_block, Mapping):
            continue
        attributes = raw_category_block.get("attributes") or {}
        if not isinstance(attributes, Mapping):
            continue
        for raw_attribute_id, raw_attribute_block in dict(attributes).items():
            attribute_id = _normalize_key(raw_attribute_id)
            if (
                not attribute_id
                or not isinstance(raw_attribute_block, Mapping)
                or attribute_id not in joined.columns
            ):
                continue
            taxonomy_context = taxonomy_index.get((category_key, attribute_id))
            if not taxonomy_context:
                continue
            allowed_sources = [
                _normalize_text(item)
                for item in (raw_attribute_block.get("allowed_sources") or [])
                if _normalize_text(item)
            ]
            blocked_sources = {
                _normalize_text(item)
                for item in (raw_attribute_block.get("blocked_sources") or [])
                if _normalize_text(item)
            }
            trusted_sources = [
                source for source in allowed_sources if source and source not in blocked_sources
            ]
            if not trusted_sources:
                continue
            values = raw_attribute_block.get("values") or {}
            if not isinstance(values, Mapping):
                values = {}
            value_expression_map: dict[str, set[str]] = {}
            for raw_value_id, raw_value_block in dict(values).items():
                value_id = _normalize_key(raw_value_id)
                if not value_id or not isinstance(raw_value_block, Mapping):
                    continue
                value_expression_map[value_id] = {
                    _normalize_text(item)
                    for item in (raw_value_block.get("deterministic_expressions") or [])
                    if _normalize_text(item)
                }

            attribute_rows = joined.filter(
                (pl.col("category_key") == category_key)
                & (pl.col("source_channel").is_in(trusted_sources))
            )
            if attribute_rows.is_empty():
                continue

            phrase_total_products: dict[str, set[str]] = defaultdict(set)
            phrase_total_values: dict[str, set[str]] = defaultdict(set)
            phrase_value_products: dict[tuple[str, str], set[str]] = defaultdict(set)
            phrase_value_retailers: dict[tuple[str, str], set[str]] = defaultdict(set)
            phrase_value_sources: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
            phrase_value_samples: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

            for row in attribute_rows.iter_rows(named=True):
                value_id = _normalize_assignment_value(row.get(attribute_id))
                if not value_id or value_id not in taxonomy_context["values"]:
                    continue
                phrase = _normalize_text(row.get("normalized_text") or row.get("segment_text"))
                if not _is_candidate_phrase(phrase):
                    continue
                if phrase in taxonomy_context["term_index"]:
                    continue
                if phrase in value_expression_map.get(value_id, set()):
                    continue

                row_key = "|".join(
                    [
                        str(row.get("retailer") or ""),
                        str(row.get("row_type") or ""),
                        str(row.get("parent_product_id") or ""),
                        str(row.get("variant_id") or ""),
                    ]
                )
                phrase_total_products[phrase].add(row_key)
                phrase_total_values[phrase].add(value_id)
                group_key = (value_id, phrase)
                phrase_value_products[group_key].add(row_key)
                phrase_value_retailers[group_key].add(str(row.get("retailer") or ""))
                source_channel = _normalize_text(row.get("source_channel"))
                if source_channel:
                    phrase_value_sources[group_key][source_channel] += 1
                if len(phrase_value_samples[group_key]) < 3:
                    phrase_value_samples[group_key].append(
                        {
                            "retailer": str(row.get("retailer") or ""),
                            "row_type": str(row.get("row_type") or ""),
                            "display_name": str(row.get("display_name") or ""),
                            "source_channel": str(row.get("source_channel") or ""),
                            "source_path": str(row.get("source_path") or ""),
                            "segment_text": str(row.get("segment_text") or ""),
                        }
                    )

            for (value_id, phrase), product_keys in phrase_value_products.items():
                support_count = len(product_keys)
                retailer_count = len(
                    {
                        retailer
                        for retailer in phrase_value_retailers[(value_id, phrase)]
                        if retailer
                    }
                )
                total_products = len(phrase_total_products.get(phrase, set()))
                if not total_products:
                    continue
                agreement_rate = support_count / total_products
                if support_count < _PHRASE_MIN_SUPPORT_PRODUCTS:
                    continue
                if retailer_count < _PHRASE_MIN_SUPPORT_RETAILERS:
                    continue
                if agreement_rate < _PHRASE_MIN_AGREEMENT_RATE:
                    continue

                leaf = taxonomy_context["values"].get(value_id)
                label_text = str((leaf or {}).get("label") or value_id).strip()
                competing_value_ids = sorted(
                    value for value in phrase_total_values.get(phrase, set()) if value != value_id
                )
                source_distribution = dict(phrase_value_sources[(value_id, phrase)])
                candidate_key = (
                    f"add_deterministic_expression|{category_key}|{attribute_id}|{value_id}|"
                    f"{hashlib.sha1(phrase.encode('utf-8')).hexdigest()[:12]}"
                )
                rows.append(
                    {
                        "candidate_domain": "deterministic_policy",
                        "candidate_type": "add_deterministic_expression",
                        "candidate_key": candidate_key,
                        "category_key": category_key,
                        "attribute_id": attribute_id,
                        "value_id": value_id,
                        "support_product_count": support_count,
                        "support_retailer_count": retailer_count,
                        "confidence_level": "high" if agreement_rate == 1.0 else "medium",
                        "decision_ease": "medium",
                        "evidence_summary_json": {
                            "phrase": phrase,
                            "label_text": label_text,
                            "agreement_rate": agreement_rate,
                            "total_phrase_products": total_products,
                            "source_distribution": source_distribution,
                            "competing_value_ids": competing_value_ids,
                            "sample_snippets": phrase_value_samples[(value_id, phrase)],
                        },
                        "created_from_run_id": run_id,
                        "priority_score": 875.0 + min(float(support_count), 50.0),
                        "label_text": label_text,
                        "source_channel": max(
                            source_distribution.items(),
                            key=lambda item: item[1],
                        )[0]
                        if source_distribution
                        else "",
                    }
                )
    return rows


def _build_surfaced_rows(
    rows: list[dict[str, Any]],
    *,
    file_name: str,
    run_id: str,
) -> list[dict[str, Any]]:
    surfaced: list[dict[str, Any]] = []
    for row in rows:
        candidate_type = str(row.get("candidate_type") or "")
        candidate_key = str(row.get("candidate_key") or "")
        if not candidate_type or not candidate_key:
            continue
        title: str
        short_reason: str
        if candidate_type == "disable_bare_label":
            label_text = str(row.get("label_text") or row.get("value_id") or "").strip()
            title = f"Disable bare label for {label_text}"
            short_reason = (
                f"The bare label '{label_text}' also appears under another value in the same attribute."
            )
        elif candidate_type == "add_deterministic_expression":
            evidence = row.get("evidence_summary_json") or {}
            phrase = ""
            if isinstance(evidence, Mapping):
                phrase = str(evidence.get("phrase") or "").strip()
            label_text = str(row.get("label_text") or row.get("value_id") or "").strip()
            title = f"Add deterministic expression for {label_text}"
            short_reason = (
                f"The phrase '{phrase}' repeatedly aligns with {label_text} in trusted sources."
            )
        else:
            source_channel = str(row.get("source_channel") or "").strip()
            title = f"Block {source_channel} for {row.get('attribute_id')}"
            short_reason = (
                f"The attribute currently allows the risky source '{source_channel}'."
            )
        evidence_signature = hashlib.sha1(
            _json_text(
                {
                    "candidate_key": candidate_key,
                    "candidate_type": candidate_type,
                    "evidence": row.get("evidence_summary_json") or {},
                }
            ).encode("utf-8")
        ).hexdigest()
        surfaced.append(
            {
                "candidate_domain": row.get("candidate_domain"),
                "candidate_type": candidate_type,
                "candidate_key": candidate_key,
                "aggregated_row_ref": f"aggregated/{file_name}#{candidate_key}",
                "category_key": row.get("category_key"),
                "attribute_id": row.get("attribute_id"),
                "value_id": row.get("value_id"),
                "title": title,
                "short_reason": short_reason,
                "priority_score": row.get("priority_score"),
                "confidence_level": row.get("confidence_level"),
                "decision_ease": row.get("decision_ease"),
                "support_product_count": row.get("support_product_count"),
                "support_retailer_count": row.get("support_retailer_count"),
                "evidence_signature": evidence_signature,
                "run_id": run_id,
                "origin": "system_suggested",
            }
        )
    return surfaced


def build_phase1_deterministic_policy_candidate_run(
    config: Mapping[str, Any],
    taxonomy: Mapping[str, Any],
    *,
    pdp_store_path: Path | str,
    config_source: str,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    timestamp = now or dt.datetime.now(dt.timezone.utc)
    run_id = timestamp.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_root = candidate_run_root(pdp_store_path) / run_id
    aggregated_dir = run_root / "aggregated"
    surfaced_dir = run_root / "surfaced"

    add_expression_rows = _add_deterministic_expression_rows(
        config,
        taxonomy,
        pdp_store_path=pdp_store_path,
        run_id=run_id,
    )
    disable_bare_label_rows = _disable_bare_label_rows(config, taxonomy, run_id=run_id)
    block_bad_source_rows = _block_bad_source_rows(config, run_id=run_id)

    add_name = "deterministic_policy_add_deterministic_expression.parquet"
    disable_name = "deterministic_policy_disable_bare_label.parquet"
    block_name = "deterministic_policy_block_bad_source.parquet"
    add_df = _rows_to_frame(add_expression_rows, _AGGREGATED_SCHEMA)
    disable_df = _rows_to_frame(disable_bare_label_rows, _AGGREGATED_SCHEMA)
    block_df = _rows_to_frame(block_bad_source_rows, _AGGREGATED_SCHEMA)
    _write_frame(add_df, aggregated_dir / add_name)
    _write_frame(disable_df, aggregated_dir / disable_name)
    _write_frame(block_df, aggregated_dir / block_name)

    surfaced_rows = [
        *_build_surfaced_rows(add_expression_rows, file_name=add_name, run_id=run_id),
        *_build_surfaced_rows(disable_bare_label_rows, file_name=disable_name, run_id=run_id),
        *_build_surfaced_rows(block_bad_source_rows, file_name=block_name, run_id=run_id),
    ]
    surfaced_df = _rows_to_frame(surfaced_rows, _SURFACED_SCHEMA)
    _write_frame(surfaced_df, surfaced_dir / "surfaced_candidates.parquet")

    manifest = {
        "run_id": run_id,
        "created_at": timestamp.isoformat(),
        "taxonomy_version": str(taxonomy.get("version") or ""),
        "deterministic_policy_version": str(config.get("version") or ""),
        "explicit_rules_version": "",
        "stage_snapshot_id": "",
        "scope": {"retailers": [], "categories": [], "attributes": []},
        "generated_files": [
            f"aggregated/{add_name}",
            f"aggregated/{disable_name}",
            f"aggregated/{block_name}",
            "surfaced/surfaced_candidates.parquet",
        ],
        "generator_version": "deterministic-policy-phase1-v1",
        "config_source": config_source,
    }
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "run_id": run_id,
        "run_root": str(run_root),
        "manifest": manifest,
        "aggregated_counts": {
            "add_deterministic_expression": add_df.height,
            "disable_bare_label": disable_df.height,
            "block_bad_source": block_df.height,
        },
        "surfaced_count": surfaced_df.height,
        "config_source": config_source,
    }


def load_deterministic_policy_aggregated_candidate_row(
    *,
    pdp_store_path: Path | str,
    run_id: str,
    aggregated_row_ref: str,
) -> dict[str, Any] | None:
    ref = str(aggregated_row_ref or "").strip()
    if not ref or "#" not in ref:
        return None
    relative_path, candidate_key = ref.split("#", 1)
    target = candidate_run_root(pdp_store_path) / run_id / relative_path
    if not target.exists():
        return None
    df = pl.read_parquet(target)
    if df.is_empty() or "candidate_key" not in df.columns:
        return None
    matched = df.filter(pl.col("candidate_key") == candidate_key)
    if matched.is_empty():
        return None
    row = matched.to_dicts()[0]
    for key in _JSON_COLUMNS:
        raw = row.get(key)
        if isinstance(raw, str) and raw.strip():
            try:
                row[key] = json.loads(raw)
            except json.JSONDecodeError:
                continue
    return row
