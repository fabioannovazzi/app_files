from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import polars as pl

from modules.add_attributes.explicit_declaration_classifier import (
    load_explicit_declaration_rules,
)
from modules.pdp.postgres_compat import connect_pdp_database

_REVIEW_KEYS = {"reviews", "reviews_positive", "reviews_negative", "reviews_meta"}


@dataclass(frozen=True, slots=True)
class ExplicitRuleCandidate:
    candidate_id: str
    category_key: str
    attribute_id: str
    proposed_value: str
    pattern: str
    pattern_type: str
    sample_count: int
    sample_snippets: tuple[str, ...]
    estimated_conflict_rate: float
    status: str


__all__ = [
    "ExplicitRuleCandidate",
    "load_parent_pdp_text_rows",
    "mine_explicit_declaration_candidates",
]


def _normalize_category_key(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    cleaned = text.replace("&", " and ")
    cleaned = "".join(char if char.isalnum() else " " for char in cleaned)
    return "_".join(part for part in cleaned.split() if part)


def _extract_leaf_labels(nodes: Sequence[Mapping[str, object]] | None) -> list[str]:
    labels: list[str] = []
    if not nodes:
        return labels
    for node in nodes:
        children = node.get("children")
        if isinstance(children, Sequence) and not isinstance(
            children, (str, bytes, bytearray)
        ):
            labels.extend(_extract_leaf_labels(children))  # type: ignore[arg-type]
            continue
        label = str(node.get("label") or "").strip()
        if label:
            labels.append(label)
    return labels


def _flatten_text_payload(payload: object) -> list[str]:
    texts: list[str] = []

    def _walk(value: object, *, path: str) -> None:
        if value is None:
            return
        if isinstance(value, str):
            text = value.strip()
            if text:
                texts.append(text)
            return
        if isinstance(value, Mapping):
            for key, child in value.items():
                key_text = str(key).strip().lower()
                if key_text in _REVIEW_KEYS:
                    continue
                child_path = f"{path}.{key_text}" if path else key_text
                _walk(child, path=child_path)
            return
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            for idx, child in enumerate(value):
                child_path = f"{path}[{idx}]" if path else f"[{idx}]"
                _walk(child, path=child_path)

    _walk(payload, path="")
    return texts


def _extract_pdp_text(extras_raw: object) -> str:
    if isinstance(extras_raw, str):
        extras_text = extras_raw.strip()
        if not extras_text:
            return ""
        try:
            extras = json.loads(extras_text)
        except json.JSONDecodeError:
            return extras_text
    elif isinstance(extras_raw, Mapping):
        extras = extras_raw
    else:
        return ""
    parts = _flatten_text_payload(extras)
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        normalized = part.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return "\n".join(deduped)


def _normalize_category_path(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = []
            if isinstance(parsed, list) and parsed:
                candidate = str(parsed[-1]).strip().lower()
                return _normalize_category_key(candidate)
        return _normalize_category_key(text)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            return ""
        return _normalize_category_key(str(value[-1]).strip().lower())
    return ""


def load_parent_pdp_text_rows(
    pdp_store_path: Path | str,
    *,
    retailers: Sequence[str] | None = None,
    categories: Sequence[str] | None = None,
) -> pl.DataFrame:
    normalized_retailers = [
        str(retailer).strip().lower()
        for retailer in (retailers or [])
        if str(retailer).strip()
    ]
    normalized_categories = {
        _normalize_category_key(str(category).strip().lower())
        for category in (categories or [])
        if str(category).strip()
    }
    conditions: list[str] = []
    params: list[Any] = []
    if normalized_retailers:
        placeholders = ",".join("?" for _ in normalized_retailers)
        conditions.append(f"lower(retailer) IN ({placeholders})")
        params.extend(normalized_retailers)
    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    query = (
        "SELECT retailer, parent_product_id, category_path, extras "
        "FROM parent_products"
        f"{where_clause}"
    )
    with connect_pdp_database(Path(pdp_store_path)) as conn:
        rows = conn.execute(query, params).fetchall()

    records: list[dict[str, Any]] = []
    for retailer, parent_product_id, category_path, extras in rows:
        category_key = _normalize_category_path(category_path)
        if normalized_categories and category_key not in normalized_categories:
            continue
        pdp_text = _extract_pdp_text(extras)
        if not pdp_text:
            continue
        records.append(
            {
                "retailer": str(retailer or "").strip(),
                "parent_product_id": str(parent_product_id or "").strip(),
                "category_key": category_key,
                "pdp_text": pdp_text,
            }
        )
    if not records:
        return pl.DataFrame(
            schema={
                "retailer": pl.Utf8,
                "parent_product_id": pl.Utf8,
                "category_key": pl.Utf8,
                "pdp_text": pl.Utf8,
            }
        )
    return pl.DataFrame(records, strict=False, infer_schema_length=None)


def _taxonomy_phrase_templates(
    taxonomy: Mapping[str, object],
) -> dict[str, dict[str, dict[str, str]]]:
    templates: dict[str, dict[str, dict[str, str]]] = {}
    for category in taxonomy.get("categories", []) or []:
        if not isinstance(category, Mapping):
            continue
        category_key = _normalize_category_key(
            str(category.get("id") or category.get("label") or "").strip().lower()
        )
        if not category_key:
            continue
        for attribute in category.get("attributes", []) or []:
            if not isinstance(attribute, Mapping):
                continue
            attribute_id = str(attribute.get("id") or "").strip()
            attribute_label = (
                str(attribute.get("label") or attribute_id).strip().lower()
            )
            if not attribute_id or not attribute_label:
                continue
            value_templates: dict[str, str] = {}
            for value_label in _extract_leaf_labels(attribute.get("nodes")):
                normalized_value = str(value_label).strip()
                if not normalized_value:
                    continue
                phrase = f"{normalized_value.lower()} {attribute_label}".strip()
                if phrase:
                    value_templates[normalized_value] = phrase
            if value_templates:
                templates.setdefault(category_key, {})[attribute_id] = value_templates
    return templates


def _existing_patterns_lookup(
    rules: Mapping[str, object],
) -> set[tuple[str, str, str, str]]:
    lookup: set[tuple[str, str, str, str]] = set()
    categories = rules.get("categories")
    if not isinstance(categories, Mapping):
        return lookup
    for category_key, category_payload in categories.items():
        if not isinstance(category_payload, Mapping):
            continue
        attributes = category_payload.get("attributes")
        if not isinstance(attributes, Mapping):
            continue
        for attribute_id, attribute_payload in attributes.items():
            if not isinstance(attribute_payload, Mapping):
                continue
            values = attribute_payload.get("values")
            if not isinstance(values, Mapping):
                continue
            for value_label, value_payload in values.items():
                if not isinstance(value_payload, Mapping):
                    continue
                signals = value_payload.get("certainty_signals")
                if not isinstance(signals, Sequence) or isinstance(
                    signals, (str, bytes)
                ):
                    continue
                for signal in signals:
                    if not isinstance(signal, Mapping):
                        continue
                    pattern = str(signal.get("pattern") or "").strip().casefold()
                    if not pattern:
                        continue
                    lookup.add(
                        (
                            _normalize_category_key(str(category_key).strip().lower()),
                            str(attribute_id).strip(),
                            str(value_label).strip(),
                            pattern,
                        )
                    )
    return lookup


def _snippet(text: str, *, start: int, end: int) -> str:
    low = max(0, start - 50)
    high = min(len(text), end + 50)
    return " ".join(text[low:high].split())


def _candidate_id(
    category_key: str, attribute_id: str, proposed_value: str, pattern: str
) -> str:
    raw = f"{category_key}|{attribute_id}|{proposed_value}|{pattern}".encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()[:12]
    return f"{category_key}.{attribute_id}.{proposed_value}.{digest}"


def mine_explicit_declaration_candidates(
    source_df: pl.DataFrame,
    *,
    taxonomy: Mapping[str, object],
    rules: Mapping[str, object] | None = None,
    min_sample_count: int = 3,
    max_snippets_per_candidate: int = 5,
) -> list[ExplicitRuleCandidate]:
    if source_df.is_empty():
        return []
    for column in ("retailer", "parent_product_id", "category_key", "pdp_text"):
        if column not in source_df.columns:
            raise ValueError(f"Missing required source column '{column}'.")

    templates = _taxonomy_phrase_templates(taxonomy)
    if not templates:
        return []

    active_rules = _existing_patterns_lookup(rules or load_explicit_declaration_rules())

    buckets: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in source_df.select(
        ["retailer", "parent_product_id", "category_key", "pdp_text"]
    ).to_dicts():
        category_key = _normalize_category_key(
            str(row.get("category_key") or "").strip().lower()
        )
        if not category_key:
            continue
        category_templates = templates.get(category_key)
        if not category_templates:
            continue
        text = str(row.get("pdp_text") or "")
        text_lc = text.casefold()
        if not text_lc.strip():
            continue

        for attribute_id, value_templates in category_templates.items():
            matched_for_attribute: list[tuple[str, str, int, int]] = []
            for proposed_value, pattern in value_templates.items():
                existing_key = (
                    category_key,
                    attribute_id,
                    proposed_value,
                    pattern.casefold(),
                )
                if existing_key in active_rules:
                    continue
                idx = text_lc.find(pattern.casefold())
                if idx < 0:
                    continue
                matched_for_attribute.append(
                    (proposed_value, pattern, idx, idx + len(pattern))
                )

            if not matched_for_attribute:
                continue
            conflict = len({value for value, _, _, _ in matched_for_attribute}) > 1
            for proposed_value, pattern, start, end in matched_for_attribute:
                key = (category_key, attribute_id, proposed_value, pattern)
                bucket = buckets.setdefault(
                    key,
                    {
                        "sample_count": 0,
                        "conflict_count": 0,
                        "snippets": [],
                    },
                )
                bucket["sample_count"] += 1
                if conflict:
                    bucket["conflict_count"] += 1
                if len(bucket["snippets"]) < max(1, max_snippets_per_candidate):
                    snippet = _snippet(text, start=start, end=end)
                    if snippet and snippet not in bucket["snippets"]:
                        bucket["snippets"].append(snippet)

    candidates: list[ExplicitRuleCandidate] = []
    for (category_key, attribute_id, proposed_value, pattern), bucket in sorted(
        buckets.items()
    ):
        sample_count = int(bucket["sample_count"])
        if sample_count < max(1, int(min_sample_count)):
            continue
        conflict_count = int(bucket["conflict_count"])
        candidates.append(
            ExplicitRuleCandidate(
                candidate_id=_candidate_id(
                    category_key, attribute_id, proposed_value, pattern
                ),
                category_key=category_key,
                attribute_id=attribute_id,
                proposed_value=proposed_value,
                pattern=pattern,
                pattern_type="phrase",
                sample_count=sample_count,
                sample_snippets=tuple(bucket["snippets"]),
                estimated_conflict_rate=(
                    conflict_count / sample_count if sample_count else 0.0
                ),
                status="pending",
            )
        )
    return candidates
