from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import time
from typing import Any, Mapping
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
try:  # pragma: no cover - optional template dependency
    from fastapi.templating import Jinja2Templates
except Exception:  # noqa: BLE001
    Jinja2Templates = None  # type: ignore[misc,assignment]
import polars as pl
from pydantic import BaseModel, Field

from modules.add_attributes.attribute_taxonomy import get_attribute_taxonomy
from modules.auth.dependencies import maybe_current_user
from modules.pdp.review_constants import DEFAULT_PDP_STORE_PATH
from modules.pdp.taxonomy_review_queue import build_taxonomy_context
from modules.pdp.deterministic_policy_draft_mutations import (
    APPLICABLE_DETERMINISTIC_POLICY_CANDIDATE_TYPES,
    apply_deterministic_policy_queue_item,
)
from modules.pdp.deterministic_policy_review_queue import (
    build_phase1_deterministic_policy_candidate_run,
    build_policy_context,
    load_deterministic_policy_aggregated_candidate_row,
)
from modules.pdp.store import PDPStore

__all__ = [
    "DEFAULT_DETERMINISTIC_POLICY_PATH",
    "router",
    "site_router",
]


DEFAULT_DETERMINISTIC_POLICY_PATH = Path("config/pdp_deterministic_policy.json")
SOURCE_CHANNELS = (
    "title",
    "summary",
    "features",
    "description_short",
    "description_long",
    "description_markdown",
    "variant_name",
    "variant_description",
    "ingredients",
    "usage",
    "restrictions",
    "reviews",
)
DEFAULT_ALLOWED_SOURCES = (
    "title",
    "summary",
    "features",
    "description_markdown",
    "description_short",
    "variant_name",
    "variant_description",
)
DEFAULT_BLOCKED_SOURCES = (
    "reviews",
    "ingredients",
    "usage",
    "restrictions",
)
SOURCE_CHANNELS_VERSION = "2026-03-11"

router = APIRouter(prefix="/review/deterministic-policy", tags=["review"])
site_router = APIRouter(prefix="/review/deterministic-policy")
templates = Jinja2Templates(directory="templates") if Jinja2Templates else None


class DeterministicPolicyValidateRequest(BaseModel):
    config: dict[str, Any] | None = None


class DeterministicPolicyValidateResponse(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]
    normalized_config: dict[str, Any] | None = None


class DeterministicPolicyBootstrapAttribute(BaseModel):
    category_key: str = Field(min_length=1)
    attribute_id: str = Field(min_length=1)


class DeterministicPolicyBootstrapRequest(BaseModel):
    attributes: list[DeterministicPolicyBootstrapAttribute] = Field(default_factory=list)


class DeterministicPolicyBootstrapResponse(BaseModel):
    config: dict[str, Any]


class DeterministicPolicyDraftRequest(BaseModel):
    config: dict[str, Any]


class DeterministicPolicyDraftResetRequest(BaseModel):
    pass


class PublishDeterministicPolicyDraftRequest(BaseModel):
    note: str | None = None
    version: str | None = None


class DeterministicPolicyDraftResponse(BaseModel):
    has_draft: bool
    updated_at: str | None = None
    updated_by: str | None = None
    diff_summary: dict[str, Any]
    diff_items: list[dict[str, Any]]
    warnings: list[str]
    config: dict[str, Any]


class DeterministicPolicyQueueRunResponse(BaseModel):
    run_id: str
    config_source: str
    surfaced_count: int
    inserted_count: int
    refreshed_count: int
    suppressed_count: int
    aggregated_counts: dict[str, int]


class DeterministicPolicyQueueListResponse(BaseModel):
    total: int
    items: list[dict[str, Any]]


class DeterministicPolicyQueueDecisionRequest(BaseModel):
    decision_reason: str | None = Field(default=None, min_length=1)


class ApplyDeterministicPolicyQueueItemResponse(BaseModel):
    item: dict[str, Any]
    draft: DeterministicPolicyDraftResponse
    mutation_summary: dict[str, Any]


class PreviewDeterministicPolicyQueueItemApplyResponse(BaseModel):
    apply_supported: bool
    warnings: list[str]
    mutation_summary: dict[str, Any]
    preview: DeterministicPolicyDraftResponse


class PublishDeterministicPolicyResponse(BaseModel):
    version: str
    updated_at: str
    diff_summary: dict[str, Any]
    warnings: list[str]


def _normalize_key(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "_")


def _request_actor_email(request: Request) -> str | None:
    user = maybe_current_user(request)
    email = str(getattr(user, "email", "") or "").strip().lower()
    return email or None


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _normalize_list(values: Any) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        normalized = _normalize_text(value)
        if not normalized or normalized in seen:
            continue
        cleaned.append(normalized)
        seen.add(normalized)
    return cleaned


def _empty_policy(taxonomy: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "version": "",
        "taxonomy_version": str(taxonomy.get("version") or "").strip(),
        "source_channels_version": SOURCE_CHANNELS_VERSION,
        "categories": {},
    }


def _load_config_from_disk() -> dict[str, Any]:
    if not DEFAULT_DETERMINISTIC_POLICY_PATH.exists():
        return _empty_policy(get_attribute_taxonomy())
    try:
        raw = json.loads(DEFAULT_DETERMINISTIC_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_policy(get_attribute_taxonomy())
    if isinstance(raw, dict):
        return raw
    return _empty_policy(get_attribute_taxonomy())


def _store() -> PDPStore:
    return PDPStore(DEFAULT_PDP_STORE_PATH)


def _save_config_to_disk(config: Mapping[str, Any]) -> None:
    DEFAULT_DETERMINISTIC_POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_DETERMINISTIC_POLICY_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _static_asset_version(path: str) -> str:
    target = Path(path)
    try:
        return str(int(target.stat().st_mtime))
    except OSError:
        return str(int(time.time()))


def _taxonomy_indexes(
    taxonomy: Mapping[str, Any],
) -> tuple[
    dict[str, dict[str, Mapping[str, Any]]],
    dict[tuple[str, str], dict[str, Mapping[str, Any]]],
]:
    attribute_index: dict[str, dict[str, Mapping[str, Any]]] = {}
    value_index: dict[tuple[str, str], dict[str, Mapping[str, Any]]] = {}

    def _walk_leaves(nodes: list[dict[str, Any]], bucket: dict[str, Mapping[str, Any]]) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            children = node.get("children")
            if isinstance(children, list) and children:
                _walk_leaves(children, bucket)
                continue
            value_id = _normalize_key(node.get("id") or node.get("label"))
            if value_id:
                bucket[value_id] = node

    for category in taxonomy.get("categories") or []:
        if not isinstance(category, dict):
            continue
        category_key = _normalize_key(category.get("id") or category.get("label"))
        if not category_key:
            continue
        attribute_bucket: dict[str, Mapping[str, Any]] = {}
        for attribute in category.get("attributes") or []:
            if not isinstance(attribute, dict):
                continue
            attribute_id = _normalize_key(attribute.get("id") or attribute.get("label"))
            if not attribute_id:
                continue
            attribute_bucket[attribute_id] = attribute
            leaf_bucket: dict[str, Mapping[str, Any]] = {}
            nodes = attribute.get("nodes")
            if isinstance(nodes, list):
                _walk_leaves(nodes, leaf_bucket)
            value_index[(category_key, attribute_id)] = leaf_bucket
        attribute_index[category_key] = attribute_bucket

    return attribute_index, value_index


def _normalize_attribute_block(
    *,
    block: Mapping[str, Any],
    category_key: str,
    attribute_id: str,
    value_lookup: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    allowed_sources = _normalize_list(block.get("allowed_sources"))
    blocked_sources = _normalize_list(block.get("blocked_sources"))

    unknown_allowed = sorted(set(allowed_sources) - set(SOURCE_CHANNELS))
    unknown_blocked = sorted(set(blocked_sources) - set(SOURCE_CHANNELS))
    if unknown_allowed:
        errors.append(
            f"{category_key}/{attribute_id} has unknown allowed_sources: {unknown_allowed}"
        )
    if unknown_blocked:
        errors.append(
            f"{category_key}/{attribute_id} has unknown blocked_sources: {unknown_blocked}"
        )
    overlap = sorted(set(allowed_sources) & set(blocked_sources))
    if overlap:
        errors.append(
            f"{category_key}/{attribute_id} has overlapping allowed/blocked sources: {overlap}"
        )

    conflict_resolution = _normalize_key(block.get("conflict_resolution") or "na")
    if conflict_resolution != "na":
        errors.append(
            f"{category_key}/{attribute_id} conflict_resolution must be 'na'."
        )

    normalized_values: dict[str, Any] = {}
    for raw_value_id, raw_value_block in dict(block.get("values") or {}).items():
        value_id = _normalize_key(raw_value_id)
        if not value_id:
            continue
        if value_id not in value_lookup:
            errors.append(
                f"{category_key}/{attribute_id}/{value_id} does not exist in the taxonomy."
            )
            continue
        if value_id in {"unknown", "other"}:
            errors.append(
                f"{category_key}/{attribute_id}/{value_id} is reserved and cannot appear in deterministic policy."
            )
            continue
        if not isinstance(raw_value_block, Mapping):
            errors.append(
                f"{category_key}/{attribute_id}/{value_id} must be an object."
            )
            continue
        expressions = _normalize_list(raw_value_block.get("deterministic_expressions"))
        required_context_any = _normalize_list(raw_value_block.get("required_context_any"))
        negative_patterns = _normalize_list(raw_value_block.get("negative_patterns"))
        allow_label = bool(raw_value_block.get("allow_label"))
        if not allow_label and not expressions:
            errors.append(
                f"{category_key}/{attribute_id}/{value_id} is a no-op: allow_label is false and deterministic_expressions is empty."
            )
        normalized_values[value_id] = {
            "allow_label": allow_label,
            "deterministic_expressions": expressions,
            "required_context_any": required_context_any,
            "negative_patterns": negative_patterns,
        }

    normalized_block = {
        "allowed_sources": allowed_sources,
        "blocked_sources": blocked_sources,
        "conflict_resolution": "na",
        "values": normalized_values,
    }
    return normalized_block, errors, warnings


def _validate_config(
    config: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    taxonomy = get_attribute_taxonomy()
    attribute_index, value_index = _taxonomy_indexes(taxonomy)
    errors: list[str] = []
    warnings: list[str] = []
    normalized = _empty_policy(taxonomy)
    normalized["version"] = str(config.get("version") or "").strip()
    normalized["taxonomy_version"] = str(
        config.get("taxonomy_version") or taxonomy.get("version") or ""
    ).strip()
    normalized["source_channels_version"] = str(
        config.get("source_channels_version") or SOURCE_CHANNELS_VERSION
    ).strip()

    categories_raw = config.get("categories") or {}
    if not isinstance(categories_raw, Mapping):
        return None, ["categories must be an object keyed by category id."], warnings

    normalized_categories: dict[str, Any] = {}
    for raw_category_key, raw_category_block in dict(categories_raw).items():
        category_key = _normalize_key(raw_category_key)
        if not category_key:
            continue
        if category_key not in attribute_index:
            errors.append(f"{category_key} does not exist in the taxonomy.")
            continue
        if not isinstance(raw_category_block, Mapping):
            errors.append(f"{category_key} must be an object.")
            continue
        attributes_raw = raw_category_block.get("attributes") or {}
        if not isinstance(attributes_raw, Mapping):
            errors.append(f"{category_key}.attributes must be an object.")
            continue
        normalized_attributes: dict[str, Any] = {}
        for raw_attribute_id, raw_attribute_block in dict(attributes_raw).items():
            attribute_id = _normalize_key(raw_attribute_id)
            if not attribute_id:
                continue
            if attribute_id not in attribute_index[category_key]:
                errors.append(
                    f"{category_key}/{attribute_id} does not exist in the taxonomy."
                )
                continue
            if not isinstance(raw_attribute_block, Mapping):
                errors.append(f"{category_key}/{attribute_id} must be an object.")
                continue
            normalized_block, attr_errors, attr_warnings = _normalize_attribute_block(
                block=raw_attribute_block,
                category_key=category_key,
                attribute_id=attribute_id,
                value_lookup=value_index.get((category_key, attribute_id), {}),
            )
            errors.extend(attr_errors)
            warnings.extend(attr_warnings)
            normalized_attributes[attribute_id] = normalized_block
        if normalized_attributes:
            normalized_categories[category_key] = {"attributes": normalized_attributes}
    normalized["categories"] = normalized_categories
    return (normalized if not errors else None), errors, warnings


def _bootstrap_config(
    request: DeterministicPolicyBootstrapRequest,
) -> dict[str, Any]:
    taxonomy = get_attribute_taxonomy()
    attribute_index, _value_index = _taxonomy_indexes(taxonomy)
    config = _empty_policy(taxonomy)
    categories: dict[str, Any] = {}
    for item in request.attributes:
        category_key = _normalize_key(item.category_key)
        attribute_id = _normalize_key(item.attribute_id)
        if not category_key or not attribute_id:
            continue
        if category_key not in attribute_index:
            continue
        if attribute_id not in attribute_index[category_key]:
            continue
        category_payload = categories.setdefault(category_key, {"attributes": {}})
        category_payload["attributes"][attribute_id] = {
            "allowed_sources": list(DEFAULT_ALLOWED_SOURCES),
            "blocked_sources": list(DEFAULT_BLOCKED_SOURCES),
            "conflict_resolution": "na",
            "values": {},
        }
    config["categories"] = categories
    return config


def _flatten_policy(config: Mapping[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    flattened: dict[tuple[str, str, str], dict[str, Any]] = {}
    categories = config.get("categories") or {}
    if not isinstance(categories, Mapping):
        return flattened
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
            flattened[(category_key, attribute_id, "__attribute__")] = {
                "allowed_sources": _normalize_list(raw_attribute_block.get("allowed_sources")),
                "blocked_sources": _normalize_list(raw_attribute_block.get("blocked_sources")),
                "conflict_resolution": _normalize_key(
                    raw_attribute_block.get("conflict_resolution") or "na"
                ),
            }
            values = raw_attribute_block.get("values") or {}
            if not isinstance(values, Mapping):
                continue
            for raw_value_id, raw_value_block in dict(values).items():
                value_id = _normalize_key(raw_value_id)
                if not value_id or not isinstance(raw_value_block, Mapping):
                    continue
                flattened[(category_key, attribute_id, value_id)] = {
                    "allow_label": bool(raw_value_block.get("allow_label")),
                    "deterministic_expressions": _normalize_list(
                        raw_value_block.get("deterministic_expressions")
                    ),
                    "required_context_any": _normalize_list(
                        raw_value_block.get("required_context_any")
                    ),
                    "negative_patterns": _normalize_list(
                        raw_value_block.get("negative_patterns")
                    ),
                }
    return flattened


def _policy_diff(
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    previous_flat = _flatten_policy(previous)
    current_flat = _flatten_policy(current)
    diff_items: list[dict[str, Any]] = []
    changed_categories: set[str] = set()
    changed_attributes: set[tuple[str, str]] = set()
    for key in sorted(set(previous_flat) | set(current_flat)):
        before = previous_flat.get(key)
        after = current_flat.get(key)
        if before == after:
            continue
        category_key, attribute_id, value_id = key
        changed_categories.add(category_key)
        changed_attributes.add((category_key, attribute_id))
        diff_items.append(
            {
                "category_key": category_key,
                "attribute_id": attribute_id,
                "value_id": None if value_id == "__attribute__" else value_id,
                "scope": "attribute" if value_id == "__attribute__" else "value",
                "before": before,
                "after": after,
            }
        )
    diff_summary = {
        "changed_category_count": len(changed_categories),
        "changed_attribute_count": len(changed_attributes),
        "changed_item_count": len(diff_items),
    }
    return diff_summary, diff_items


def _draft_response_payload(
    *,
    store: PDPStore,
    draft_row: Mapping[str, Any] | None = None,
) -> DeterministicPolicyDraftResponse:
    published = _load_config_from_disk()
    normalized_published, published_errors, _published_warnings = _validate_config(published)
    published_for_diff = (
        normalized_published if not published_errors and normalized_published is not None else published
    )
    row = dict(draft_row) if draft_row is not None else (store.get_deterministic_policy_draft() or {})
    has_draft = bool(row)
    config = dict(row.get("config") or published)
    diff_summary, diff_items = _policy_diff(published_for_diff, config)
    normalized_config, errors, warnings = _validate_config(config)
    if errors or normalized_config is None:
        return DeterministicPolicyDraftResponse(
            has_draft=has_draft,
            updated_at=str(row.get("updated_at") or "") or None,
            updated_by=str(row.get("updated_by") or "") or None,
            diff_summary=diff_summary,
            diff_items=diff_items,
            warnings=[*warnings, *errors],
            config=config,
        )
    normalized_diff_summary, normalized_diff_items = _policy_diff(
        published_for_diff, normalized_config
    )
    return DeterministicPolicyDraftResponse(
        has_draft=has_draft,
        updated_at=str(row.get("updated_at") or "") or None,
        updated_by=str(row.get("updated_by") or "") or None,
        diff_summary=normalized_diff_summary,
        diff_items=normalized_diff_items,
        warnings=warnings,
        config=normalized_config,
    )


def _next_version(current: str) -> str:
    current_value = str(current or "").strip()
    if not current_value:
        return "1"
    parts = current_value.split(".")
    try:
        parts[-1] = str(int(parts[-1]) + 1)
        return ".".join(parts)
    except ValueError:
        return f"{current_value}.1"


def _publish_deterministic_policy(
    *,
    previous: Mapping[str, Any],
    normalized_config: Mapping[str, Any],
    actor: str | None,
    note: str | None,
    version: str | None,
    warnings: list[str],
    audit_action: str,
    audit_details: Mapping[str, Any] | None = None,
    diff_summary: Mapping[str, Any] | None = None,
) -> PublishDeterministicPolicyResponse:
    now = _now_iso()
    store = _store()
    previous_versions = store.list_deterministic_policy_config_versions(limit=1)
    current_version = (
        str(previous_versions[0].get("version") or "")
        if previous_versions
        else str(previous.get("version") or "")
    )
    next_version = str(version or "").strip() or _next_version(current_version)
    published_config = dict(normalized_config)
    published_config["version"] = next_version
    _save_config_to_disk(published_config)
    resolved_diff_summary = dict(diff_summary or _policy_diff(previous, published_config)[0])
    store.append_deterministic_policy_config_version(
        version=next_version,
        published_at=now,
        actor=actor,
        note=note,
        config=published_config,
        diff_summary=resolved_diff_summary,
    )
    store.append_deterministic_policy_audit(
        timestamp=now,
        action=audit_action,
        actor=actor,
        details={
            "version": next_version,
            "warnings": warnings,
            "diff_summary": resolved_diff_summary,
            "note": note,
            **dict(audit_details or {}),
        },
    )
    return PublishDeterministicPolicyResponse(
        version=next_version,
        updated_at=now,
        diff_summary=resolved_diff_summary,
        warnings=warnings,
    )


def _current_policy_config(
    store: PDPStore,
) -> tuple[dict[str, Any], str]:
    draft_row = store.get_deterministic_policy_draft()
    if isinstance(draft_row, Mapping) and isinstance(draft_row.get("config"), Mapping):
        config = dict(draft_row["config"])
        config_source = "draft"
    else:
        config = _load_config_from_disk()
        config_source = "published"
    normalized_config, errors, warnings = _validate_config(config)
    if errors or normalized_config is None:
        raise HTTPException(
            status_code=400,
            detail={
                "errors": errors,
                "warnings": warnings,
                "config_source": config_source,
            },
        )
    return normalized_config, config_source


def _upsert_surfaced_queue_items(
    *,
    store: PDPStore,
    surfaced_rows: list[dict[str, Any]],
) -> tuple[int, int, int]:
    inserted = 0
    refreshed = 0
    suppressed = 0
    for row in surfaced_rows:
        candidate_domain = str(row.get("candidate_domain") or "").strip()
        candidate_type = str(row.get("candidate_type") or "").strip()
        candidate_key = str(row.get("candidate_key") or "").strip()
        evidence_signature = str(row.get("evidence_signature") or "").strip()
        if not candidate_domain or not candidate_type or not candidate_key:
            continue
        existing = store.get_review_queue_item_by_candidate(
            candidate_domain=candidate_domain,
            candidate_type=candidate_type,
            candidate_key=candidate_key,
        )
        now = _now_iso()
        if existing is None:
            store.upsert_review_queue_items(
                [
                    {
                        "queue_item_id": uuid.uuid4().hex,
                        "candidate_domain": candidate_domain,
                        "candidate_type": candidate_type,
                        "candidate_key": candidate_key,
                        "aggregated_row_ref": row.get("aggregated_row_ref"),
                        "run_id": row.get("run_id"),
                        "evidence_signature": evidence_signature,
                        "origin": "system_suggested",
                        "status": "open",
                        "category_key": row.get("category_key"),
                        "attribute_id": row.get("attribute_id"),
                        "value_id": row.get("value_id"),
                        "title": row.get("title"),
                        "short_reason": row.get("short_reason"),
                        "priority_score": row.get("priority_score"),
                        "confidence_level": row.get("confidence_level"),
                        "decision_ease": row.get("decision_ease"),
                        "support_product_count": row.get("support_product_count"),
                        "support_retailer_count": row.get("support_retailer_count"),
                        "created_at": now,
                        "updated_at": now,
                    }
                ]
            )
            inserted += 1
            continue
        existing_status = str(existing.get("status") or "").strip().lower()
        existing_signature = str(existing.get("evidence_signature") or "").strip()
        if existing_status in {"rejected", "applied"} and existing_signature == evidence_signature:
            suppressed += 1
            continue
        next_status = (
            "open"
            if existing_status in {"rejected", "applied"}
            else existing_status or "open"
        )
        store.upsert_review_queue_items(
            [
                {
                    "queue_item_id": existing.get("queue_item_id"),
                    "candidate_domain": candidate_domain,
                    "candidate_type": candidate_type,
                    "candidate_key": candidate_key,
                    "aggregated_row_ref": row.get("aggregated_row_ref"),
                    "run_id": row.get("run_id"),
                    "evidence_signature": evidence_signature,
                    "origin": existing.get("origin") or "system_suggested",
                    "status": next_status,
                    "category_key": row.get("category_key"),
                    "attribute_id": row.get("attribute_id"),
                    "value_id": row.get("value_id"),
                    "title": row.get("title"),
                    "short_reason": row.get("short_reason"),
                    "priority_score": row.get("priority_score"),
                    "confidence_level": row.get("confidence_level"),
                    "decision_ease": row.get("decision_ease"),
                    "support_product_count": row.get("support_product_count"),
                    "support_retailer_count": row.get("support_retailer_count"),
                    "reviewer": None
                    if next_status == "open" and existing_status in {"rejected", "applied"}
                    else existing.get("reviewer"),
                    "decision_reason": None
                    if next_status == "open" and existing_status in {"rejected", "applied"}
                    else existing.get("decision_reason"),
                    "payload_json": existing.get("payload_json"),
                    "created_at": existing.get("created_at") or now,
                    "updated_at": now,
                }
            ]
        )
        refreshed += 1
    return inserted, refreshed, suppressed


def _read_surfaced_candidates(pdp_store_path: Path | str, run_id: str) -> list[dict[str, Any]]:
    path = (
        Path(pdp_store_path).parent
        / f"{Path(pdp_store_path).stem}_candidate_runs"
        / run_id
        / "surfaced"
        / "surfaced_candidates.parquet"
    )
    if not path.exists():
        return []
    return pl.read_parquet(path).to_dicts()


def _queue_detail_payload(
    *,
    pdp_store_path: Path | str,
    config: Mapping[str, Any],
    taxonomy: Mapping[str, Any],
    item: Mapping[str, Any],
) -> dict[str, Any]:
    category_key = str(item.get("category_key") or "").strip()
    attribute_id = str(item.get("attribute_id") or "").strip()
    value_id = str(item.get("value_id") or "").strip() or None
    detail: dict[str, Any] = {
        "item": dict(item),
        "taxonomy_context": build_taxonomy_context(
            taxonomy,
            category_key=category_key,
            attribute_id=attribute_id,
        ),
        "policy_context": build_policy_context(
            config,
            category_key=category_key,
            attribute_id=attribute_id,
            value_id=value_id,
        ),
        "aggregated": None,
    }
    run_id = str(item.get("run_id") or "").strip()
    aggregated_row_ref = str(item.get("aggregated_row_ref") or "").strip()
    if run_id and aggregated_row_ref:
        detail["aggregated"] = load_deterministic_policy_aggregated_candidate_row(
            pdp_store_path=pdp_store_path,
            run_id=run_id,
            aggregated_row_ref=aggregated_row_ref,
        )
    return detail


def _preview_apply_queue_item(
    *,
    store: PDPStore,
    item: Mapping[str, Any],
) -> PreviewDeterministicPolicyQueueItemApplyResponse:
    candidate_type = str(item.get("candidate_type") or "").strip()
    apply_supported = candidate_type in APPLICABLE_DETERMINISTIC_POLICY_CANDIDATE_TYPES
    config, _config_source = _current_policy_config(store)
    aggregated: Mapping[str, Any] | None = None
    aggregated_row_ref = str(item.get("aggregated_row_ref") or "").strip()
    run_id = str(item.get("run_id") or "").strip()
    if aggregated_row_ref and run_id:
        aggregated = load_deterministic_policy_aggregated_candidate_row(
            pdp_store_path=store.path,
            run_id=run_id,
            aggregated_row_ref=aggregated_row_ref,
        )
    if not apply_supported:
        return PreviewDeterministicPolicyQueueItemApplyResponse(
            apply_supported=False,
            warnings=[
                "Draft preview currently supports only: "
                + ", ".join(sorted(APPLICABLE_DETERMINISTIC_POLICY_CANDIDATE_TYPES))
            ],
            mutation_summary={},
            preview=_draft_response_payload(store=store),
        )
    try:
        next_config, mutation_summary = apply_deterministic_policy_queue_item(
            config,
            item,
            aggregated=aggregated,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    normalized_config, errors, warnings = _validate_config(next_config)
    if errors or normalized_config is None:
        raise HTTPException(
            status_code=400,
            detail={"errors": errors, "warnings": warnings},
        )
    preview = _draft_response_payload(
        store=store,
        draft_row={
            "config": normalized_config,
            "updated_at": None,
            "updated_by": None,
        },
    )
    return PreviewDeterministicPolicyQueueItemApplyResponse(
        apply_supported=True,
        warnings=preview.warnings,
        mutation_summary=mutation_summary,
        preview=preview,
    )


@router.get("/config")
def read_config() -> dict[str, Any]:
    config = _load_config_from_disk()
    return {"path": str(DEFAULT_DETERMINISTIC_POLICY_PATH), "config": config}


@router.post("/config/validate", response_model=DeterministicPolicyValidateResponse)
def validate_config(
    request: DeterministicPolicyValidateRequest,
) -> DeterministicPolicyValidateResponse:
    config = request.config if request.config is not None else _load_config_from_disk()
    normalized_config, errors, warnings = _validate_config(config)
    return DeterministicPolicyValidateResponse(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        normalized_config=normalized_config if not errors else None,
    )


@router.post("/config/bootstrap", response_model=DeterministicPolicyBootstrapResponse)
def bootstrap_config(
    request: DeterministicPolicyBootstrapRequest,
) -> DeterministicPolicyBootstrapResponse:
    return DeterministicPolicyBootstrapResponse(config=_bootstrap_config(request))


@router.get("/draft", response_model=DeterministicPolicyDraftResponse)
def read_draft() -> DeterministicPolicyDraftResponse:
    return _draft_response_payload(store=_store())


@router.get("/draft/preview", response_model=DeterministicPolicyDraftResponse)
def preview_draft() -> DeterministicPolicyDraftResponse:
    return _draft_response_payload(store=_store())


@router.post("/draft/save", response_model=DeterministicPolicyDraftResponse)
def save_draft(
    request: DeterministicPolicyDraftRequest,
    http_request: Request,
) -> DeterministicPolicyDraftResponse:
    store = _store()
    normalized_config, errors, warnings = _validate_config(request.config)
    if errors or normalized_config is None:
        raise HTTPException(
            status_code=400,
            detail={"errors": errors, "warnings": warnings},
        )
    store.upsert_deterministic_policy_draft(
        config=normalized_config,
        updated_at=_now_iso(),
        updated_by=_request_actor_email(http_request),
    )
    return _draft_response_payload(store=store)


@router.post("/draft/bootstrap", response_model=DeterministicPolicyDraftResponse)
def bootstrap_draft(
    request: DeterministicPolicyBootstrapRequest,
    http_request: Request,
) -> DeterministicPolicyDraftResponse:
    store = _store()
    config = _bootstrap_config(request)
    normalized_config, errors, warnings = _validate_config(config)
    if errors or normalized_config is None:
        raise HTTPException(
            status_code=400,
            detail={"errors": errors, "warnings": warnings},
        )
    store.upsert_deterministic_policy_draft(
        config=normalized_config,
        updated_at=_now_iso(),
        updated_by=_request_actor_email(http_request),
    )
    return _draft_response_payload(store=store)


@router.post("/draft/reset", response_model=DeterministicPolicyDraftResponse)
def reset_draft(
    request: DeterministicPolicyDraftResetRequest,
    http_request: Request,
) -> DeterministicPolicyDraftResponse:
    store = _store()
    now = _now_iso()
    actor = _request_actor_email(http_request)
    store.delete_deterministic_policy_draft()
    store.append_deterministic_policy_audit(
        timestamp=now,
        action="draft_reset",
        actor=actor,
        details={},
    )
    return _draft_response_payload(store=store)


@router.post("/draft/publish", response_model=PublishDeterministicPolicyResponse)
def publish_draft(
    request: PublishDeterministicPolicyDraftRequest,
    http_request: Request,
) -> PublishDeterministicPolicyResponse:
    store = _store()
    draft_row = store.get_deterministic_policy_draft()
    if draft_row is None or not isinstance(draft_row.get("config"), Mapping):
        raise HTTPException(
            status_code=409,
            detail="No draft deterministic policy is available to publish.",
        )
    previous = _load_config_from_disk()
    normalized_config, errors, warnings = _validate_config(draft_row["config"])
    if errors or normalized_config is None:
        raise HTTPException(
            status_code=400,
            detail={"errors": errors, "warnings": warnings},
        )
    response = _publish_deterministic_policy(
        previous=previous,
        normalized_config=normalized_config,
        actor=_request_actor_email(http_request),
        note=request.note,
        version=request.version,
        warnings=warnings,
        audit_action="draft_published",
        audit_details={
            "draft_updated_at": draft_row.get("updated_at"),
            "draft_updated_by": draft_row.get("updated_by"),
        },
        diff_summary=_policy_diff(previous, normalized_config)[0],
    )
    store.delete_deterministic_policy_draft()
    return response


@site_router.get("/page", include_in_schema=False)
def deterministic_policy_page(request: Request) -> Any:
    if templates is None:  # pragma: no cover - defensive fallback
        raise HTTPException(status_code=503, detail="Templating support is not available.")
    return templates.TemplateResponse(
        request,
        "review_deterministic_policy_queue_react.html",
        {
            "request": request,
            "page_title": "Deterministic policy",
            "bundle_url": f"/static/js/review-deterministic-policy-queue-react.js?v={_static_asset_version('static/js/review-deterministic-policy-queue-react.js')}",
        },
    )


@router.post("/queue/run", response_model=DeterministicPolicyQueueRunResponse)
def run_queue() -> DeterministicPolicyQueueRunResponse:
    store = _store()
    config, config_source = _current_policy_config(store)
    result = build_phase1_deterministic_policy_candidate_run(
        config,
        get_attribute_taxonomy(),
        pdp_store_path=store.path,
        config_source=config_source,
    )
    surfaced_rows = _read_surfaced_candidates(store.path, result["run_id"])
    inserted, refreshed, suppressed = _upsert_surfaced_queue_items(
        store=store,
        surfaced_rows=surfaced_rows,
    )
    return DeterministicPolicyQueueRunResponse(
        run_id=result["run_id"],
        config_source=str(result["config_source"]),
        surfaced_count=int(result["surfaced_count"]),
        inserted_count=inserted,
        refreshed_count=refreshed,
        suppressed_count=suppressed,
        aggregated_counts={
            key: int(value) for key, value in result["aggregated_counts"].items()
        },
    )


@router.get("/queue/items", response_model=DeterministicPolicyQueueListResponse)
def list_queue_items(
    status: str | None = Query(default=None),
    candidate_type: str | None = Query(default=None),
    category_key: str | None = Query(default=None),
    attribute_id: str | None = Query(default=None),
    origin: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> DeterministicPolicyQueueListResponse:
    items = _store().list_review_queue_items(
        status=str(status).strip() if status else None,
        candidate_domain="deterministic_policy",
        candidate_type=str(candidate_type).strip() if candidate_type else None,
        category_key=_normalize_key(category_key) if category_key else None,
        attribute_id=_normalize_key(attribute_id) if attribute_id else None,
        origin=str(origin).strip() if origin else None,
        limit=limit,
    )
    return DeterministicPolicyQueueListResponse(total=len(items), items=items)


@router.get("/queue/items/{queue_item_id}")
def get_queue_item(queue_item_id: str) -> dict[str, Any]:
    store = _store()
    item = store.get_review_queue_item(queue_item_id)
    if item is None or str(item.get("candidate_domain") or "") != "deterministic_policy":
        raise HTTPException(status_code=404, detail="Queue item not found.")
    config, _config_source = _current_policy_config(store)
    return _queue_detail_payload(
        pdp_store_path=store.path,
        config=config,
        taxonomy=get_attribute_taxonomy(),
        item=item,
    )


@router.get(
    "/queue/items/{queue_item_id}/preview-apply",
    response_model=PreviewDeterministicPolicyQueueItemApplyResponse,
)
def preview_apply_queue_item(
    queue_item_id: str,
) -> PreviewDeterministicPolicyQueueItemApplyResponse:
    store = _store()
    item = store.get_review_queue_item(queue_item_id)
    if item is None or str(item.get("candidate_domain") or "") != "deterministic_policy":
        raise HTTPException(status_code=404, detail="Queue item not found.")
    return _preview_apply_queue_item(store=store, item=item)


@router.post("/queue/items/{queue_item_id}/approve")
def approve_queue_item(
    queue_item_id: str,
    request: DeterministicPolicyQueueDecisionRequest,
    http_request: Request,
) -> dict[str, Any]:
    item = _store().update_review_queue_item_status(
        queue_item_id,
        status="approved",
        reviewer=_request_actor_email(http_request),
        decision_reason=str(request.decision_reason or "").strip() or None,
        updated_at=_now_iso(),
    )
    if item is None or str(item.get("candidate_domain") or "") != "deterministic_policy":
        raise HTTPException(status_code=404, detail="Queue item not found.")
    return item


@router.post("/queue/items/{queue_item_id}/reject")
def reject_queue_item(
    queue_item_id: str,
    request: DeterministicPolicyQueueDecisionRequest,
    http_request: Request,
) -> dict[str, Any]:
    item = _store().update_review_queue_item_status(
        queue_item_id,
        status="rejected",
        reviewer=_request_actor_email(http_request),
        decision_reason=str(request.decision_reason or "").strip() or None,
        updated_at=_now_iso(),
    )
    if item is None or str(item.get("candidate_domain") or "") != "deterministic_policy":
        raise HTTPException(status_code=404, detail="Queue item not found.")
    return item


@router.post(
    "/queue/items/{queue_item_id}/apply",
    response_model=ApplyDeterministicPolicyQueueItemResponse,
)
def apply_queue_item(
    queue_item_id: str,
    request: DeterministicPolicyQueueDecisionRequest,
    http_request: Request,
) -> ApplyDeterministicPolicyQueueItemResponse:
    store = _store()
    item = store.get_review_queue_item(queue_item_id)
    if item is None or str(item.get("candidate_domain") or "") != "deterministic_policy":
        raise HTTPException(status_code=404, detail="Queue item not found.")
    if str(item.get("status") or "").strip().lower() != "approved":
        raise HTTPException(
            status_code=409,
            detail="Only approved deterministic-policy queue items can be applied to the draft.",
        )
    if str(item.get("candidate_type") or "").strip() not in APPLICABLE_DETERMINISTIC_POLICY_CANDIDATE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Draft apply currently supports only: "
                + ", ".join(sorted(APPLICABLE_DETERMINISTIC_POLICY_CANDIDATE_TYPES))
            ),
        )
    config, _config_source = _current_policy_config(store)
    aggregated: Mapping[str, Any] | None = None
    aggregated_row_ref = str(item.get("aggregated_row_ref") or "").strip()
    run_id = str(item.get("run_id") or "").strip()
    if aggregated_row_ref and run_id:
        aggregated = load_deterministic_policy_aggregated_candidate_row(
            pdp_store_path=store.path,
            run_id=run_id,
            aggregated_row_ref=aggregated_row_ref,
        )
    try:
        next_config, mutation_summary = apply_deterministic_policy_queue_item(
            config,
            item,
            aggregated=aggregated,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    normalized_config, errors, warnings = _validate_config(next_config)
    if errors or normalized_config is None:
        raise HTTPException(
            status_code=400,
            detail={"errors": errors, "warnings": warnings},
        )
    now = _now_iso()
    reviewer = _request_actor_email(http_request)
    decision_reason = str(request.decision_reason or "").strip() or None
    store.upsert_deterministic_policy_draft(
        config=normalized_config,
        updated_at=now,
        updated_by=reviewer,
    )
    updated_item = store.update_review_queue_item_status(
        queue_item_id,
        status="applied",
        reviewer=reviewer,
        decision_reason=decision_reason,
        updated_at=now,
    )
    store.append_deterministic_policy_audit(
        timestamp=now,
        action="queue_item_applied_to_draft",
        actor=reviewer,
        details={
            "queue_item_id": queue_item_id,
            "candidate_type": item.get("candidate_type"),
            "candidate_key": item.get("candidate_key"),
            "mutation_summary": mutation_summary,
        },
    )
    return ApplyDeterministicPolicyQueueItemResponse(
        item=dict(updated_item or item),
        draft=_draft_response_payload(store=store),
        mutation_summary=mutation_summary,
    )
