from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import polars as pl

from modules.pdp.review_constants import DEFAULT_PDP_STORE_PATH

__all__ = [
    "build_phase1_taxonomy_candidate_run",
    "build_taxonomy_context",
    "candidate_run_root",
    "load_aggregated_candidate_row",
]

logger = logging.getLogger(__name__)

_PLACEHOLDER_VALUES = frozenset(
    {"", "n/a", "na", "none", "unknown", "n/a_(not_stated)", "not_stated"}
)
_JSON_COLUMNS = {
    "sample_refs_json",
    "evidence_summary_json",
    "source_channel_counts_json",
    "affected_value_ids_json",
    "conflicting_value_ids_json",
    "occurrence_roles_json",
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
    "sample_refs_json": pl.Utf8,
    "evidence_summary_json": pl.Utf8,
    "created_from_run_id": pl.Utf8,
    "priority_score": pl.Float64,
    "term": pl.Utf8,
    "phrase": pl.Utf8,
    "source_channel_counts_json": pl.Utf8,
    "agreement_rate": pl.Float64,
    "false_positive_rate": pl.Float64,
    "affected_value_ids_json": pl.Utf8,
    "conflicting_value_ids_json": pl.Utf8,
    "identity_confidence": pl.Float64,
    "occurrence_roles_json": pl.Utf8,
    "sibling_value_count": pl.Int64,
    "competing_value_count": pl.Int64,
    "label_text": pl.Utf8,
    "wrong_or_unstable_count": pl.Int64,
    "error_rate": pl.Float64,
    "source_channel": pl.Utf8,
    "false_positive_count": pl.Int64,
    "false_positive_share": pl.Float64,
    "good_match_count": pl.Int64,
    "expression": pl.Utf8,
    "negative_pattern": pl.Utf8,
    "rare_in_correct_matches": pl.Boolean,
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


def _normalize_key(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "_")


def _normalize_text(value: object | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).lower()


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


def candidate_run_root(pdp_store_path: Path | str) -> Path:
    path = Path(pdp_store_path)
    return path.parent / f"{path.stem}_candidate_runs"


def _attribute_cache_dir(pdp_store_path: Path | str) -> Path:
    path = Path(pdp_store_path)
    return path.parent / f"{path.stem}_attribute_cache"


def _iter_cache_retailers(pdp_store_path: Path | str) -> list[str]:
    root = _attribute_cache_dir(pdp_store_path)
    if not root.exists():
        return []
    retailers = [path.name for path in root.iterdir() if path.is_dir()]
    return sorted(retailers)


def _concat_frames(frames: list[pl.DataFrame]) -> pl.DataFrame:
    if not frames:
        return pl.DataFrame()
    if len(frames) == 1:
        return frames[0]
    return pl.concat(frames, how="diagonal_relaxed")


def _load_coverage_parent_rows(pdp_store_path: Path | str) -> pl.DataFrame | None:
    path = Path(pdp_store_path)
    try:
        if path.resolve() != DEFAULT_PDP_STORE_PATH.resolve():
            return None
    except OSError:
        return None

    try:
        from modules.pdp.api import _get_tables_for_coverage
    except ImportError:
        return None

    try:
        tables = _get_tables_for_coverage()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to load coverage parent rows for taxonomy issues")
        return None

    parents_df = tables.parents
    if parents_df.is_empty():
        return None
    return parents_df.with_columns(
        pl.lit("parent").alias("row_type"),
        pl.lit("").alias("variant_id"),
        pl.concat_str(
            [
                pl.col("brand").fill_null(""),
                pl.when(pl.col("brand").fill_null("") != "")
                .then(pl.lit(" "))
                .otherwise(pl.lit("")),
                pl.col("product_name").fill_null(""),
            ]
        )
        .str.strip_chars()
        .alias("display_name"),
    )


def _load_assignment_rows(pdp_store_path: Path | str) -> pl.DataFrame:
    coverage_rows = _load_coverage_parent_rows(pdp_store_path)
    if coverage_rows is not None:
        return coverage_rows

    frames: list[pl.DataFrame] = []
    for retailer in _iter_cache_retailers(pdp_store_path):
        root = _attribute_cache_dir(pdp_store_path) / retailer
        parent_path = root / "parents.parquet"
        if not parent_path.exists():
            continue
        try:
            parent_df = pl.read_parquet(parent_path)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Skipping unreadable taxonomy assignment cache for retailer=%s path=%s",
                retailer,
                parent_path,
            )
            continue
        if parent_df.is_empty():
            continue
        frames.append(
            parent_df.with_columns(
                pl.lit("parent").alias("row_type"),
                pl.lit("").alias("variant_id"),
                pl.concat_str(
                    [
                        pl.col("brand").fill_null(""),
                        pl.when(pl.col("brand").fill_null("") != "")
                        .then(pl.lit(" "))
                        .otherwise(pl.lit("")),
                        pl.col("product_name").fill_null(""),
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


def _compose_pdp_text(row: Mapping[str, Any]) -> str:
    fields = (
        "pdp_text",
        "product_description",
        "description_markdown",
        "description",
        "long_description",
        "short_description",
        "usage",
        "ingredients",
        "restrictions",
        "benefits",
        "how_to_use",
        "details",
        "variant_description",
    )
    parts: list[str] = []
    seen: set[str] = set()
    for field in fields:
        value = row.get(field)
        candidates = value if isinstance(value, (list, tuple)) else (value,)
        for candidate in candidates:
            text = str(candidate or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            parts.append(text)
    return "\n".join(parts).strip()


def _iter_leaf_nodes(
    nodes: Iterable[Mapping[str, Any]],
    *,
    category_key: str,
    attribute_id: str,
    parent_path: list[str] | None = None,
) -> Iterable[dict[str, Any]]:
    path_prefix = list(parent_path or [])
    for node in nodes:
        children = node.get("children")
        label = str(node.get("label") or node.get("id") or "").strip()
        node_id = _normalize_key(node.get("id") or label)
        if not node_id:
            continue
        if isinstance(children, list) and children:
            yield from _iter_leaf_nodes(
                children,
                category_key=category_key,
                attribute_id=attribute_id,
                parent_path=path_prefix + [node_id],
            )
            continue
        synonyms = [
            str(item).strip()
            for item in (node.get("synonyms") or [])
            if str(item).strip()
        ]
        yield {
            "category_key": category_key,
            "attribute_id": attribute_id,
            "value_id": node_id,
            "label": label,
            "synonyms": synonyms,
            "path": path_prefix + [node_id],
        }


def build_taxonomy_context(
    taxonomy: Mapping[str, Any],
    *,
    category_key: str,
    attribute_id: str,
) -> dict[str, Any]:
    categories = taxonomy.get("categories")
    if not isinstance(categories, list):
        return {"category_key": category_key, "attribute_id": attribute_id, "values": []}
    for category in categories:
        if not isinstance(category, Mapping):
            continue
        current_category_key = _normalize_key(category.get("id") or category.get("label"))
        if current_category_key != category_key:
            continue
        attributes = category.get("attributes")
        if not isinstance(attributes, list):
            continue
        for attribute in attributes:
            if not isinstance(attribute, Mapping):
                continue
            current_attribute_id = _normalize_key(
                attribute.get("id") or attribute.get("label")
            )
            if current_attribute_id != attribute_id:
                continue
            values = list(
                _iter_leaf_nodes(
                    attribute.get("nodes") or [],
                    category_key=category_key,
                    attribute_id=attribute_id,
                )
            )
            return {
                "category_key": category_key,
                "category_label": str(category.get("label") or category.get("id") or "").strip(),
                "attribute_id": attribute_id,
                "attribute_label": str(
                    attribute.get("label") or attribute.get("id") or ""
                ).strip(),
                "hierarchical": bool(attribute.get("hierarchical")),
                "selection": str(attribute.get("selection") or "single").strip(),
                "values": values,
            }
    return {"category_key": category_key, "attribute_id": attribute_id, "values": []}


def _same_term_collision_rows(
    taxonomy: Mapping[str, Any],
    *,
    run_id: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    categories = taxonomy.get("categories")
    if not isinstance(categories, list):
        return rows
    for category in categories:
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
            leaves = list(
                _iter_leaf_nodes(
                    attribute.get("nodes") or [],
                    category_key=category_key,
                    attribute_id=attribute_id,
                )
            )
            term_map: dict[str, list[dict[str, str]]] = {}
            for leaf in leaves:
                value_id = leaf["value_id"]
                if value_id in {"unknown", "other"}:
                    continue
                label_text = str(leaf["label"]).strip()
                normalized_label = _normalize_text(label_text)
                if normalized_label:
                    term_map.setdefault(normalized_label, []).append(
                        {"value_id": value_id, "role": "label", "text": label_text}
                    )
                for synonym in leaf["synonyms"]:
                    normalized_synonym = _normalize_text(synonym)
                    if normalized_synonym:
                        term_map.setdefault(normalized_synonym, []).append(
                            {"value_id": value_id, "role": "synonym", "text": synonym}
                        )
            sibling_value_count = len([leaf for leaf in leaves if leaf["value_id"] not in {"unknown", "other"}])
            for term, occurrences in term_map.items():
                affected_value_ids = sorted(
                    {str(item["value_id"]).strip() for item in occurrences if str(item["value_id"]).strip()}
                )
                if len(affected_value_ids) < 2:
                    continue
                candidate_key = f"{category_key}|{attribute_id}|{term}"
                rows.append(
                    {
                        "candidate_domain": "taxonomy",
                        "candidate_type": "same_term_same_attribute_collision",
                        "candidate_key": candidate_key,
                        "category_key": category_key,
                        "attribute_id": attribute_id,
                        "value_id": None,
                        "support_product_count": 0,
                        "support_retailer_count": 0,
                        "confidence_level": "high",
                        "decision_ease": "easy",
                        "sample_refs_json": [],
                        "evidence_summary_json": {
                            "term": term,
                            "occurrences": occurrences,
                            "affected_value_ids": affected_value_ids,
                        },
                        "created_from_run_id": run_id,
                        "priority_score": 100.0,
                        "term": term,
                        "affected_value_ids_json": affected_value_ids,
                        "occurrence_roles_json": occurrences,
                        "sibling_value_count": sibling_value_count,
                    }
                )
    return rows
def _cross_retailer_inconsistency_rows(
    taxonomy: Mapping[str, Any],
    *,
    pdp_store_path: Path | str,
    run_id: str,
) -> list[dict[str, Any]]:
    assignments = _load_assignment_rows(pdp_store_path)
    if assignments.is_empty():
        return []

    rows: list[dict[str, Any]] = []
    categories = taxonomy.get("categories")
    if not isinstance(categories, list):
        return rows

    for category in categories:
        if not isinstance(category, Mapping):
            continue
        category_key = _normalize_key(category.get("id") or category.get("label"))
        if not category_key:
            continue
        category_rows = assignments.filter(
            (pl.col("category_key") == category_key)
            & (pl.col("row_type") == "parent")
            & (pl.col("canonical_id").fill_null("") != "")
        )
        if category_rows.is_empty():
            continue

        for attribute in category.get("attributes") or []:
            if not isinstance(attribute, Mapping):
                continue
            attribute_id = _normalize_key(attribute.get("id") or attribute.get("label"))
            if not attribute_id or attribute_id not in category_rows.columns:
                continue

            leaves = list(
                _iter_leaf_nodes(
                    attribute.get("nodes") or [],
                    category_key=category_key,
                    attribute_id=attribute_id,
                )
            )
            valid_value_ids = {
                leaf["value_id"]
                for leaf in leaves
                if leaf["value_id"] not in {"unknown", "other"}
            }
            if not valid_value_ids:
                continue

            by_canonical_id: dict[str, list[dict[str, str]]] = defaultdict(list)
            for item in category_rows.iter_rows(named=True):
                canonical_id = str(item.get("canonical_id") or "").strip()
                if not canonical_id:
                    continue
                value_id = _normalize_assignment_value(item.get(attribute_id))
                if value_id not in valid_value_ids:
                    continue
                by_canonical_id[canonical_id].append(
                    {
                        "retailer": str(item.get("retailer") or "").strip(),
                        "parent_product_id": str(item.get("parent_product_id") or "").strip(),
                        "variant_id": str(item.get("variant_id") or "").strip(),
                        "value_id": value_id,
                        "display_name": str(item.get("display_name") or "").strip(),
                        "brand": str(item.get("brand") or "").strip(),
                        "product_name": str(item.get("product_name") or "").strip(),
                        "pdp_url": str(item.get("pdp_url") or "").strip(),
                        "hero_image_url": str(item.get("hero_image_url") or "").strip(),
                        "swatch_image_url": str(item.get("swatch_image_url") or "").strip(),
                        "pdp_text": _compose_pdp_text(item),
                    }
                )

            cluster_map: dict[tuple[str, ...], dict[str, Any]] = {}
            for canonical_id, entries in by_canonical_id.items():
                retailers = sorted(
                    {
                        str(entry.get("retailer") or "").strip()
                        for entry in entries
                        if str(entry.get("retailer") or "").strip()
                    }
                )
                conflicting_value_ids = sorted(
                    {
                        _normalize_key(entry.get("value_id"))
                        for entry in entries
                        if _normalize_key(entry.get("value_id"))
                    }
                )
                if len(retailers) < 2 or len(conflicting_value_ids) < 2:
                    continue
                bucket = cluster_map.setdefault(
                    tuple(conflicting_value_ids),
                    {
                        "canonical_ids": set(),
                        "retailers": set(),
                        "value_counts": Counter(),
                        "samples": [],
                    },
                )
                bucket["canonical_ids"].add(canonical_id)
                bucket["retailers"].update(retailers)
                bucket["value_counts"].update(conflicting_value_ids)
                if len(bucket["samples"]) < 5:
                    bucket["samples"].append(
                        {
                            "canonical_id": canonical_id,
                            "retailers": retailers,
                            "entries": entries,
                        }
                    )

            for conflicting_value_ids, payload in cluster_map.items():
                support_product_count = len(payload["canonical_ids"])
                if support_product_count < 1:
                    continue
                candidate_key = (
                    f"{category_key}|{attribute_id}|cross-retailer|{'|'.join(conflicting_value_ids)}"
                )
                rows.append(
                    {
                        "candidate_domain": "taxonomy",
                        "candidate_type": "cross_retailer_assignment_inconsistency",
                        "candidate_key": candidate_key,
                        "category_key": category_key,
                        "attribute_id": attribute_id,
                        "value_id": None,
                        "support_product_count": support_product_count,
                        "support_retailer_count": len(payload["retailers"]),
                        "confidence_level": "high",
                        "decision_ease": "medium",
                        "sample_refs_json": payload["samples"],
                        "evidence_summary_json": {
                            "conflicting_value_ids": list(conflicting_value_ids),
                            "value_counts": dict(payload["value_counts"]),
                            "canonical_group_count": support_product_count,
                            "sample_groups": payload["samples"],
                        },
                        "created_from_run_id": run_id,
                        "priority_score": 95.0 + min(float(support_product_count), 20.0),
                        "conflicting_value_ids_json": list(conflicting_value_ids),
                    }
                )
    return rows


def _build_surfaced_rows(
    aggregated_rows: list[dict[str, Any]],
    *,
    file_name: str,
    run_id: str,
) -> list[dict[str, Any]]:
    surfaced: list[dict[str, Any]] = []
    for row in aggregated_rows:
        candidate_type = str(row.get("candidate_type") or "").strip()
        candidate_key = str(row.get("candidate_key") or "").strip()
        if not candidate_type or not candidate_key:
            continue
        if candidate_type == "same_term_same_attribute_collision":
            title = f"Same term collision in {row.get('attribute_id')}: {row.get('term')}"
            short_reason = (
                f"The same term appears under multiple values in {row.get('attribute_id')}."
            )
        elif candidate_type == "cross_retailer_assignment_inconsistency":
            evidence = row.get("evidence_summary_json") or {}
            conflicting_values = []
            if isinstance(evidence, Mapping):
                conflicting_values = [
                    str(item).strip()
                    for item in (evidence.get("conflicting_value_ids") or [])
                    if str(item).strip()
                ]
            values_text = ", ".join(conflicting_values) if conflicting_values else "multiple values"
            title = f"Cross-retailer inconsistency in {row.get('attribute_id')}: {values_text}"
            short_reason = (
                "The same canonical products are receiving different values across retailers."
            )
        else:
            continue
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


def _write_frame(df: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)


def build_phase1_taxonomy_candidate_run(
    taxonomy: Mapping[str, Any],
    *,
    pdp_store_path: Path | str,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    timestamp = now or dt.datetime.now(dt.timezone.utc)
    run_id = timestamp.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_root = candidate_run_root(pdp_store_path) / run_id
    aggregated_dir = run_root / "aggregated"
    surfaced_dir = run_root / "surfaced"

    same_term_rows = _same_term_collision_rows(taxonomy, run_id=run_id)
    cross_retailer_rows = _cross_retailer_inconsistency_rows(
        taxonomy,
        pdp_store_path=pdp_store_path,
        run_id=run_id,
    )

    same_term_df = _rows_to_frame(same_term_rows, _AGGREGATED_SCHEMA)
    cross_retailer_df = _rows_to_frame(cross_retailer_rows, _AGGREGATED_SCHEMA)
    same_term_name = "taxonomy_same_term_collision.parquet"
    cross_retailer_name = "taxonomy_cross_retailer_assignment_inconsistency.parquet"
    _write_frame(same_term_df, aggregated_dir / same_term_name)
    _write_frame(cross_retailer_df, aggregated_dir / cross_retailer_name)

    surfaced_rows = [
        *_build_surfaced_rows(same_term_rows, file_name=same_term_name, run_id=run_id),
        *_build_surfaced_rows(
            cross_retailer_rows,
            file_name=cross_retailer_name,
            run_id=run_id,
        ),
    ]
    surfaced_df = _rows_to_frame(surfaced_rows, _SURFACED_SCHEMA)
    _write_frame(surfaced_df, surfaced_dir / "surfaced_candidates.parquet")

    manifest = {
        "run_id": run_id,
        "created_at": timestamp.isoformat(),
        "taxonomy_version": str(taxonomy.get("version") or ""),
        "deterministic_policy_version": "",
        "explicit_rules_version": "",
        "stage_snapshot_id": "",
        "scope": {"retailers": [], "categories": [], "attributes": []},
        "generated_files": [
            f"aggregated/{same_term_name}",
            f"aggregated/{cross_retailer_name}",
            "surfaced/surfaced_candidates.parquet",
        ],
        "generator_version": "taxonomy-phase1-v1",
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
            "same_term_same_attribute_collision": same_term_df.height,
            "cross_retailer_assignment_inconsistency": cross_retailer_df.height,
        },
        "surfaced_count": surfaced_df.height,
    }


def load_aggregated_candidate_row(
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
