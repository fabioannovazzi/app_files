from __future__ import annotations

import datetime as dt
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

import polars as pl
from fastapi import APIRouter, HTTPException, Query, Request

try:  # pragma: no cover - optional template dependency
    from fastapi.templating import Jinja2Templates
except Exception:  # noqa: BLE001
    Jinja2Templates = None  # type: ignore[misc,assignment]
from pydantic import BaseModel, Field

from modules.add_attributes.attribute_taxonomy import (
    TAXONOMY_PATH,
    get_attribute_taxonomy,
    save_attribute_taxonomy,
)
from modules.add_attributes.explicit_declaration_classifier import (
    DEFAULT_EXPLICIT_RULES_PATH,
    collect_explicit_declaration_rule_taxonomy_impacts,
    load_explicit_declaration_rules,
)
from modules.add_attributes.taxonomy_schema import validate_branch
from modules.auth.dependencies import maybe_current_user
from modules.pdp.attribute_mapping_paths import get_attribute_mapping_dir
from modules.pdp.language import get_navigation_label, get_page_copy, resolve_language
from modules.pdp.postgres_compat import connect_pdp_database
from modules.pdp.review_constants import DEFAULT_PDP_STORE_PATH
from modules.pdp.store import PDPStore
from modules.pdp.taxonomy_draft_mutations import (
    APPLICABLE_USER_PROPOSAL_TYPES,
    PREVIEWABLE_USER_PROPOSAL_TYPES,
    apply_user_taxonomy_proposal,
)
from modules.pdp.taxonomy_review_queue import (
    build_phase1_taxonomy_candidate_run,
    build_taxonomy_context,
    candidate_run_root,
    load_aggregated_candidate_row,
)

router = APIRouter(prefix="/review/taxonomy", tags=["review"])
site_router = APIRouter(prefix="/review/taxonomy")
issues_site_router = APIRouter(prefix="/review/issues")
templates = Jinja2Templates(directory="templates") if Jinja2Templates else None
logger = logging.getLogger(__name__)
_MIN_ISSUES_PROMOTION_SUPPORT_RUNS = 3
_ISSUES_MAPPING_DIR = get_attribute_mapping_dir()


class ValidateTaxonomyConfigRequest(BaseModel):
    config: dict[str, Any] | None = None


class ValidateTaxonomyConfigResponse(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]
    normalized_config: dict[str, Any] | None = None


class PreviewTaxonomyConfigResponse(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]
    explicit_rules_path: str
    explicit_rule_summary: dict[str, Any]
    explicit_rule_impacts: list[dict[str, Any]]


class PublishTaxonomyConfigRequest(BaseModel):
    config: dict[str, Any]
    note: str | None = None
    version: str | None = None
    acknowledge_invalid_active_explicit_rules: bool = False


class PublishTaxonomyDraftRequest(BaseModel):
    note: str | None = None
    version: str | None = None
    acknowledge_invalid_active_explicit_rules: bool = False


class PublishTaxonomyConfigResponse(BaseModel):
    version: str
    updated_at: str
    diff_summary: dict[str, Any]
    warnings: list[str]


class TaxonomyGovernanceAuditResponse(BaseModel):
    audit: list[dict[str, Any]]
    versions: list[dict[str, Any]]


class TaxonomyQueueListResponse(BaseModel):
    total: int
    items: list[dict[str, Any]]


class TaxonomyQueueRunResponse(BaseModel):
    run_id: str
    surfaced_count: int
    inserted_count: int
    refreshed_count: int
    suppressed_count: int
    aggregated_counts: dict[str, int]


class QueueDecisionRequest(BaseModel):
    decision_reason: str | None = Field(default=None, min_length=1)


class ApplyQueueItemRequest(BaseModel):
    pass


class PreviewQueueItemApplyResponse(BaseModel):
    apply_supported: bool
    proposal_type: str
    warnings: list[str]
    mutation_summary: dict[str, Any]
    preview: TaxonomyDraftResponse


class ResetTaxonomyDraftRequest(BaseModel):
    pass


class CreateTaxonomyProposalRequest(BaseModel):
    proposal_type: str = Field(min_length=1)
    category_key: str = Field(min_length=1)
    attribute_id: str = Field(min_length=1)
    value_id: str | None = None
    target_value_ids: list[str] = Field(default_factory=list)
    new_value_labels: list[str] = Field(default_factory=list)
    term_text: str | None = None
    new_label: str | None = None
    title: str | None = None
    note: str = Field(min_length=1)


class TaxonomyDraftResponse(BaseModel):
    has_draft: bool
    updated_at: str | None = None
    updated_by: str | None = None
    last_queue_item_id: str | None = None
    diff_summary: dict[str, Any]
    diff_items: list[dict[str, Any]]
    warnings: list[str]
    explicit_rule_summary: dict[str, Any]
    explicit_rule_impacts: list[dict[str, Any]]
    config: dict[str, Any]


__all__ = ["router", "site_router", "issues_site_router"]


def _store() -> PDPStore:
    return PDPStore(DEFAULT_PDP_STORE_PATH)


def _load_config_from_disk() -> dict[str, Any]:
    return get_attribute_taxonomy()


def _static_asset_version(path: str) -> str:
    target = Path(path)
    try:
        return str(int(target.stat().st_mtime))
    except OSError:
        return str(int(time.time()))


def _normalize_key(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "_")


def _request_actor_email(request: Request) -> str | None:
    user = maybe_current_user(request)
    email = str(getattr(user, "email", "") or "").strip().lower()
    return email or None


def _leaf_status(node: Mapping[str, Any]) -> str:
    node_id = _normalize_key(node.get("id"))
    if node_id in {"unknown", "other"}:
        return "active"
    status = str(node.get("status") or "active").strip().lower()
    return status or "active"


def _flatten_taxonomy_governance(
    taxonomy: Mapping[str, Any],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    flattened: dict[tuple[str, str, str], dict[str, Any]] = {}
    categories = taxonomy.get("categories")
    if not isinstance(categories, list):
        return flattened

    def _walk_nodes(
        *,
        category_key: str,
        attribute_id: str,
        nodes: list[dict[str, Any]],
    ) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            children = node.get("children")
            if isinstance(children, list) and children:
                _walk_nodes(
                    category_key=category_key,
                    attribute_id=attribute_id,
                    nodes=children,
                )
                continue
            leaf_id = _normalize_key(node.get("id") or node.get("label"))
            if not leaf_id:
                continue
            flattened[(category_key, attribute_id, leaf_id)] = {
                "status": _leaf_status(node),
                "governance_action": str(node.get("governance_action") or "").strip(),
                "successor_leaf_ids": [
                    _normalize_key(item)
                    for item in (
                        node.get("successor_leaf_ids")
                        or (
                            [node.get("replacement_leaf_id")]
                            if node.get("replacement_leaf_id")
                            else []
                        )
                    )
                    if _normalize_key(item)
                ],
                "governance_reason": str(node.get("governance_reason") or "").strip(),
            }

    for category in categories:
        if not isinstance(category, dict):
            continue
        category_key = _normalize_key(category.get("id") or category.get("label"))
        if not category_key:
            continue
        attributes = category.get("attributes")
        if not isinstance(attributes, list):
            continue
        for attribute in attributes:
            if not isinstance(attribute, dict):
                continue
            attribute_id = _normalize_key(attribute.get("id") or attribute.get("label"))
            if not attribute_id:
                continue
            nodes = attribute.get("nodes")
            if not isinstance(nodes, list):
                continue
            _walk_nodes(
                category_key=category_key,
                attribute_id=attribute_id,
                nodes=nodes,
            )

    return flattened


def _flatten_taxonomy_semantics(
    taxonomy: Mapping[str, Any],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    flattened: dict[tuple[str, str, str], dict[str, Any]] = {}
    categories = taxonomy.get("categories")
    if not isinstance(categories, list):
        return flattened

    def _walk_nodes(
        *,
        category_key: str,
        attribute_id: str,
        nodes: list[dict[str, Any]],
        parent_path: list[str],
    ) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = _normalize_key(node.get("id") or node.get("label"))
            if not node_id:
                continue
            children = node.get("children")
            if isinstance(children, list) and children:
                _walk_nodes(
                    category_key=category_key,
                    attribute_id=attribute_id,
                    nodes=children,
                    parent_path=[*parent_path, node_id],
                )
                continue
            synonyms = [
                str(item).strip()
                for item in (node.get("synonyms") or [])
                if str(item).strip()
            ]
            flattened[(category_key, attribute_id, node_id)] = {
                "label": str(node.get("label") or node.get("id") or "").strip(),
                "synonyms": synonyms,
                "path": [*parent_path, node_id],
            }

    for category in categories:
        if not isinstance(category, dict):
            continue
        category_key = _normalize_key(category.get("id") or category.get("label"))
        if not category_key:
            continue
        attributes = category.get("attributes")
        if not isinstance(attributes, list):
            continue
        for attribute in attributes:
            if not isinstance(attribute, dict):
                continue
            attribute_id = _normalize_key(attribute.get("id") or attribute.get("label"))
            if not attribute_id:
                continue
            nodes = attribute.get("nodes")
            if not isinstance(nodes, list):
                continue
            _walk_nodes(
                category_key=category_key,
                attribute_id=attribute_id,
                nodes=nodes,
                parent_path=[],
            )
    return flattened


def _count_active_leaves(taxonomy: Mapping[str, Any]) -> int:
    return sum(
        1
        for payload in _flatten_taxonomy_governance(taxonomy).values()
        if payload.get("status") == "active"
    )


def _diff_summary(
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
) -> dict[str, Any]:
    previous_flat = _flatten_taxonomy_governance(previous)
    current_flat = _flatten_taxonomy_governance(current)
    changed_keys = {
        key
        for key in set(previous_flat) | set(current_flat)
        if previous_flat.get(key) != current_flat.get(key)
    }
    changed_categories = {key[0] for key in changed_keys}
    changed_attributes = {(key[0], key[1]) for key in changed_keys}
    return {
        "previous_active_leaf_count": _count_active_leaves(previous),
        "current_active_leaf_count": _count_active_leaves(current),
        "changed_category_count": len(changed_categories),
        "changed_attribute_count": len(changed_attributes),
        "changed_leaf_count": len(changed_keys),
    }


def _semantic_diff(
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    previous_flat = _flatten_taxonomy_semantics(previous)
    current_flat = _flatten_taxonomy_semantics(current)
    diff_items: list[dict[str, Any]] = []
    changed_categories: set[str] = set()
    changed_attributes: set[tuple[str, str]] = set()
    added = 0
    removed = 0
    updated = 0

    for key in sorted(set(previous_flat) | set(current_flat)):
        before = previous_flat.get(key)
        after = current_flat.get(key)
        if before == after:
            continue
        category_key, attribute_id, value_id = key
        changed_categories.add(category_key)
        changed_attributes.add((category_key, attribute_id))
        if before is None:
            added += 1
            diff_items.append(
                {
                    "category_key": category_key,
                    "attribute_id": attribute_id,
                    "value_id": value_id,
                    "change_type": "added",
                    "before": None,
                    "after": after,
                }
            )
            continue
        if after is None:
            removed += 1
            diff_items.append(
                {
                    "category_key": category_key,
                    "attribute_id": attribute_id,
                    "value_id": value_id,
                    "change_type": "removed",
                    "before": before,
                    "after": None,
                }
            )
            continue
        updated += 1
        diff_items.append(
            {
                "category_key": category_key,
                "attribute_id": attribute_id,
                "value_id": value_id,
                "change_type": "updated",
                "label_changed": before.get("label") != after.get("label"),
                "synonyms_changed": before.get("synonyms") != after.get("synonyms"),
                "before": before,
                "after": after,
            }
        )

    summary = {
        "changed_category_count": len(changed_categories),
        "changed_attribute_count": len(changed_attributes),
        "changed_leaf_count": len(diff_items),
        "added_leaf_count": added,
        "removed_leaf_count": removed,
        "updated_leaf_count": updated,
    }
    return summary, diff_items


def _next_version(current: str) -> str:
    token = str(current or "").strip()
    if not token:
        return "1.0.0"
    parts = token.split(".")
    if len(parts) != 3:
        return f"{token}.1"
    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2])
    except ValueError:
        return f"{token}.1"
    return f"{major}.{minor}.{patch + 1}"


def _validate_config(
    config: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    categories = config.get("categories")
    if not isinstance(categories, list):
        return None, ["'categories' must be a list."], warnings

    normalized_categories: list[dict[str, Any]] = []
    for category in categories:
        if not isinstance(category, dict):
            errors.append("Each category branch must be an object.")
            continue
        category_id = _normalize_key(category.get("id") or category.get("label"))
        try:
            normalized_branch, branch_warnings = validate_branch(category)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        normalized_categories.append(normalized_branch)
        warnings.extend(
            f"{category_id or 'unknown_category'}: {warning}"
            for warning in branch_warnings
        )

    if errors:
        return None, errors, warnings

    normalized_config = dict(config)
    normalized_config["categories"] = normalized_categories
    return normalized_config, errors, warnings


def _summarize_explicit_rule_preview(
    draft_taxonomy: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rules = load_explicit_declaration_rules(DEFAULT_EXPLICIT_RULES_PATH)
    current_taxonomy = _load_config_from_disk()
    current_impacts = collect_explicit_declaration_rule_taxonomy_impacts(
        rules, current_taxonomy
    )
    draft_impacts = collect_explicit_declaration_rule_taxonomy_impacts(
        rules, draft_taxonomy
    )

    current_keys = {
        (
            str(item.get("rule_id") or ""),
            str(item.get("category_key") or ""),
            str(item.get("attribute_id") or ""),
            str(item.get("value_key") or ""),
            str(item.get("reason") or ""),
        )
        for item in current_impacts
    }
    newly_invalid_impacts = [
        item
        for item in draft_impacts
        if (
            str(item.get("rule_id") or ""),
            str(item.get("category_key") or ""),
            str(item.get("attribute_id") or ""),
            str(item.get("value_key") or ""),
            str(item.get("reason") or ""),
        )
        not in current_keys
    ]

    categories = rules.get("categories")
    total_rules = 0
    active_rules = 0
    if isinstance(categories, Mapping):
        for category_payload in categories.values():
            if not isinstance(category_payload, Mapping):
                continue
            attributes = category_payload.get("attributes")
            if not isinstance(attributes, Mapping):
                continue
            for attribute_payload in attributes.values():
                if not isinstance(attribute_payload, Mapping):
                    continue
                values = attribute_payload.get("values")
                if not isinstance(values, Mapping):
                    continue
                for value_payload in values.values():
                    if not isinstance(value_payload, Mapping):
                        continue
                    signals = value_payload.get("certainty_signals")
                    if not isinstance(signals, list):
                        continue
                    for signal in signals:
                        if not isinstance(signal, Mapping):
                            continue
                        total_rules += 1
                        if (
                            str(signal.get("status") or "active").strip().lower()
                            == "active"
                        ):
                            active_rules += 1

    summary = {
        "total_rules": total_rules,
        "active_rules": active_rules,
        "current_invalid_rules": len(current_impacts),
        "current_invalid_active_rules": sum(
            1 for item in current_impacts if item.get("signal_status") == "active"
        ),
        "draft_invalid_rules": len(draft_impacts),
        "draft_invalid_active_rules": sum(
            1 for item in draft_impacts if item.get("signal_status") == "active"
        ),
        "newly_invalid_rules": len(newly_invalid_impacts),
        "newly_invalid_active_rules": sum(
            1 for item in newly_invalid_impacts if item.get("signal_status") == "active"
        ),
    }
    return summary, newly_invalid_impacts


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _draft_response_payload(
    *,
    store: PDPStore,
    taxonomy: Mapping[str, Any] | None = None,
    draft_row: Mapping[str, Any] | None = None,
) -> TaxonomyDraftResponse:
    published = dict(taxonomy or _load_config_from_disk())
    normalized_published, published_errors, _published_warnings = _validate_config(
        published
    )
    published_for_diff = (
        normalized_published
        if not published_errors and normalized_published is not None
        else published
    )
    row = (
        dict(draft_row) if draft_row is not None else (store.get_taxonomy_draft() or {})
    )
    has_draft = bool(row)
    config = dict(row.get("config") or published)
    diff_summary, diff_items = _semantic_diff(published_for_diff, config)
    normalized_config, errors, warnings = _validate_config(config)
    if errors or normalized_config is None:
        return TaxonomyDraftResponse(
            has_draft=has_draft,
            updated_at=str(row.get("updated_at") or "") or None,
            updated_by=str(row.get("updated_by") or "") or None,
            last_queue_item_id=str(row.get("last_queue_item_id") or "") or None,
            diff_summary=diff_summary,
            diff_items=diff_items,
            warnings=[*warnings, *errors],
            explicit_rule_summary={
                "total_rules": 0,
                "active_rules": 0,
                "current_invalid_rules": 0,
                "current_invalid_active_rules": 0,
                "draft_invalid_rules": 0,
                "draft_invalid_active_rules": 0,
                "newly_invalid_rules": 0,
                "newly_invalid_active_rules": 0,
            },
            explicit_rule_impacts=[],
            config=config,
        )
    explicit_rule_summary, explicit_rule_impacts = _summarize_explicit_rule_preview(
        normalized_config
    )
    normalized_diff_summary, normalized_diff_items = _semantic_diff(
        published_for_diff, normalized_config
    )
    return TaxonomyDraftResponse(
        has_draft=has_draft,
        updated_at=str(row.get("updated_at") or "") or None,
        updated_by=str(row.get("updated_by") or "") or None,
        last_queue_item_id=str(row.get("last_queue_item_id") or "") or None,
        diff_summary=normalized_diff_summary,
        diff_items=normalized_diff_items,
        warnings=warnings,
        explicit_rule_summary=explicit_rule_summary,
        explicit_rule_impacts=explicit_rule_impacts,
        config=normalized_config,
    )


def _publish_taxonomy_config(
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
) -> PublishTaxonomyConfigResponse:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    store = _store()
    previous_versions = store.list_taxonomy_config_versions(limit=1)
    current_version = (
        str(previous_versions[0].get("version") or "") if previous_versions else ""
    )
    next_version = str(version or "").strip() or _next_version(current_version)

    save_attribute_taxonomy(dict(normalized_config))
    resolved_diff_summary = dict(
        diff_summary or _diff_summary(previous, normalized_config)
    )
    store.append_taxonomy_config_version(
        version=next_version,
        published_at=now,
        actor=actor,
        note=note,
        config=normalized_config,
        diff_summary=resolved_diff_summary,
    )
    store.append_taxonomy_governance_audit(
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
    return PublishTaxonomyConfigResponse(
        version=next_version,
        updated_at=now,
        diff_summary=resolved_diff_summary,
        warnings=warnings,
    )


def _preview_user_taxonomy_proposal(
    *,
    store: PDPStore,
    payload: Mapping[str, Any],
) -> PreviewQueueItemApplyResponse:
    proposal_type = _normalize_key(payload.get("proposal_type"))
    if proposal_type not in PREVIEWABLE_USER_PROPOSAL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Draft preview currently supports only: "
                + ", ".join(sorted(PREVIEWABLE_USER_PROPOSAL_TYPES))
            ),
        )

    published = _load_config_from_disk()
    current_draft = store.get_taxonomy_draft()
    base_config = (
        dict(current_draft.get("config") or {})
        if isinstance(current_draft, Mapping) and current_draft.get("config")
        else published
    )
    try:
        next_draft, mutation_summary = apply_user_taxonomy_proposal(
            base_config, payload
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    normalized_config, errors, warnings = _validate_config(next_draft)
    if errors or normalized_config is None:
        preview = TaxonomyDraftResponse(
            has_draft=bool(current_draft),
            updated_at=(
                str(current_draft.get("updated_at") or "") or None
                if current_draft
                else None
            ),
            updated_by=(
                str(current_draft.get("updated_by") or "") or None
                if current_draft
                else None
            ),
            last_queue_item_id=(
                str(current_draft.get("last_queue_item_id") or "") or None
                if current_draft
                else None
            ),
            diff_summary=_semantic_diff(published, next_draft)[0],
            diff_items=_semantic_diff(published, next_draft)[1],
            warnings=[*warnings, *errors],
            explicit_rule_summary={
                "total_rules": 0,
                "active_rules": 0,
                "current_invalid_rules": 0,
                "current_invalid_active_rules": 0,
                "draft_invalid_rules": 0,
                "draft_invalid_active_rules": 0,
                "newly_invalid_rules": 0,
                "newly_invalid_active_rules": 0,
            },
            explicit_rule_impacts=[],
            config=next_draft,
        )
        return PreviewQueueItemApplyResponse(
            apply_supported=proposal_type in APPLICABLE_USER_PROPOSAL_TYPES,
            proposal_type=proposal_type,
            warnings=[*warnings, *errors],
            mutation_summary=mutation_summary,
            preview=preview,
        )

    preview = _draft_response_payload(
        store=store,
        taxonomy=published,
        draft_row={
            "config": normalized_config,
            "updated_at": current_draft.get("updated_at") if current_draft else None,
            "updated_by": current_draft.get("updated_by") if current_draft else None,
            "last_queue_item_id": (
                current_draft.get("last_queue_item_id") if current_draft else None
            ),
        },
    )
    preview_warnings = list(preview.warnings)
    if proposal_type == "merge_values":
        preview_warnings.append(
            "Merge preview removes the source value without automatically transferring its synonyms."
        )
        preview = preview.model_copy(update={"warnings": preview_warnings})
    elif proposal_type == "add_value":
        preview_warnings.append(
            "Add value preview creates a new root-level leaf only; V1 does not support choosing a parent path."
        )
        preview = preview.model_copy(update={"warnings": preview_warnings})
    elif proposal_type == "split_value":
        preview_warnings.append(
            "Split preview removes the source value without automatically redistributing its synonyms or deterministic references."
        )
        created_value_ids = mutation_summary.get("created_value_ids") or []
        if created_value_ids:
            preview_warnings.append(
                "Split preview creates new target values only in the preview draft; they are not published or reusable until an explicit draft publish."
            )
        preview = preview.model_copy(update={"warnings": preview_warnings})
    return PreviewQueueItemApplyResponse(
        apply_supported=proposal_type in APPLICABLE_USER_PROPOSAL_TYPES,
        proposal_type=proposal_type,
        warnings=preview.warnings,
        mutation_summary=mutation_summary,
        preview=preview,
    )


def _read_surfaced_candidates(
    pdp_store_path: Path | str, run_id: str
) -> list[dict[str, Any]]:
    path = (
        candidate_run_root(pdp_store_path)
        / run_id
        / "surfaced"
        / "surfaced_candidates.parquet"
    )
    if not path.exists():
        return []
    frame = pl.read_parquet(path)
    return frame.to_dicts()


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
        if (
            existing_status in {"rejected", "applied"}
            and existing_signature == evidence_signature
        ):
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
                    "reviewer": (
                        None
                        if next_status == "open"
                        and existing_status in {"rejected", "applied"}
                        else existing.get("reviewer")
                    ),
                    "decision_reason": (
                        None
                        if next_status == "open"
                        and existing_status in {"rejected", "applied"}
                        else existing.get("decision_reason")
                    ),
                    "payload_json": existing.get("payload_json"),
                    "created_at": existing.get("created_at") or now,
                    "updated_at": now,
                }
            ]
        )
        refreshed += 1
    return inserted, refreshed, suppressed


def _prune_stale_surfaced_queue_items(
    *,
    store: PDPStore,
    candidate_domain: str,
    candidate_types: list[str],
    surfaced_rows: list[dict[str, Any]],
) -> int:
    active_types = sorted(
        {
            str(candidate_type).strip()
            for candidate_type in candidate_types
            if str(candidate_type).strip()
        }
    )
    if not active_types:
        return 0

    surfaced_keys_by_type: dict[str, set[str]] = {}
    for row in surfaced_rows:
        row_type = str(row.get("candidate_type") or "").strip()
        row_key = str(row.get("candidate_key") or "").strip()
        if row_type and row_key:
            surfaced_keys_by_type.setdefault(row_type, set()).add(row_key)

    queued_items = store.list_review_queue_items(
        status="open",
        candidate_domain=candidate_domain,
        origin="system_suggested",
        limit=10_000,
    )
    stale_queue_item_ids: list[str] = []
    for item in queued_items:
        item_type = str(item.get("candidate_type") or "").strip()
        if item_type not in active_types:
            continue
        candidate_key = str(item.get("candidate_key") or "").strip()
        if candidate_key in surfaced_keys_by_type.get(item_type, set()):
            continue
        queue_item_id = str(item.get("queue_item_id") or "").strip()
        if queue_item_id:
            stale_queue_item_ids.append(queue_item_id)
    return store.delete_review_queue_items(stale_queue_item_ids)


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, Mapping):
        return {}
    return dict(parsed)


def _normalize_issue_audit_value(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _is_meaningful_issue_audit_value(value: Any) -> bool:
    text = _normalize_issue_audit_value(value)
    if text is None:
        return False
    lowered = text.lower()
    if lowered in {"", "n/a", "na", "none", "unknown", "-", "--"}:
        return False
    if lowered.startswith("not in taxonomy"):
        return False
    return True


def _infer_issue_supporting_step(payload: Mapping[str, Any]) -> str | None:
    evidence = payload.get("evidence")
    if isinstance(evidence, Mapping):
        step = _normalize_issue_audit_value(evidence.get("step"))
        if step:
            return step
        stage_source = _normalize_issue_audit_value(evidence.get("stage_source"))
        if stage_source:
            source = stage_source.lower()
            if source == "web":
                return "brand_web_search"
            if source == "llm":
                return "llm_pdp_lookup"
            return source

    source = (_normalize_issue_audit_value(payload.get("source")) or "").lower()
    decision_rule = (
        _normalize_issue_audit_value(payload.get("decision_rule")) or ""
    ).lower()
    combined = f"{source} {decision_rule}".strip()
    if "brand_web_search" in combined or "web_" in combined or source == "web":
        return "brand_web_search"
    if "vision" in combined:
        return "vision"
    if "llm" in combined:
        return "llm_pdp_lookup"
    if "cross_retailer_fill" in combined:
        return "cross_retailer_fill"
    if "parent_propagation" in combined:
        return "parent_propagation"
    if source:
        return source
    return None


def _infer_issue_source(payload: Mapping[str, Any]) -> str | None:
    source = (_normalize_issue_audit_value(payload.get("source")) or "").lower()
    if source:
        return source

    evidence = payload.get("evidence")
    if isinstance(evidence, Mapping):
        stage_source = (
            _normalize_issue_audit_value(evidence.get("stage_source")) or ""
        ).lower()
        if stage_source:
            return stage_source
        step = (_normalize_issue_audit_value(evidence.get("step")) or "").lower()
        if "web" in step:
            return "web"
        if "vision" in step:
            return "vision"
        if "llm" in step:
            return "llm"
        if "explicit" in step:
            return "explicit"
        if "deterministic" in step:
            return "deterministic"

    decision_rule = (
        _normalize_issue_audit_value(payload.get("decision_rule")) or ""
    ).lower()
    combined = f"{source} {decision_rule}".strip()
    if "deterministic_explicit" in combined:
        return "deterministic_explicit"
    if "explicit" in combined:
        return "explicit"
    if "brand_web_search" in combined or "web_" in combined or " web" in combined:
        return "web"
    if "vision" in combined:
        return "vision"
    if "llm" in combined:
        return "llm"
    if "deterministic" in combined:
        return "deterministic"
    return None


def _ensure_issue_audit_source(payload: dict[str, Any]) -> None:
    inferred = _infer_issue_source(payload)
    if inferred:
        payload["source"] = inferred


def _attach_issue_single_signal_metrics(payload: dict[str, Any]) -> None:
    if not _is_meaningful_issue_audit_value(payload.get("value")):
        return
    _ensure_issue_audit_source(payload)
    if payload.get("promoted") is None:
        payload["promoted"] = False
    if payload.get("support_runs") is None:
        payload["support_runs"] = 1
    if payload.get("total_runs") is None:
        payload["total_runs"] = 1
    if payload.get("agreement_rate") is None:
        payload["agreement_rate"] = 1.0
    if payload.get("certainty_class") is None:
        payload["certainty_class"] = "uncertain"
    if payload.get("supporting_steps") is None:
        step = _infer_issue_supporting_step(payload)
        payload["supporting_steps"] = [step] if step else []
    if payload.get("available_runs") is None:
        payload["available_runs"] = None


def _attach_issue_history_metrics_from_audit_rows(
    payload: dict[str, Any],
    rows: list[dict[str, Any]],
) -> bool:
    if not rows or not _is_meaningful_issue_audit_value(payload.get("value")):
        return False

    payload_value = _normalize_issue_audit_value(payload.get("value"))
    if not payload_value:
        return False

    payload_source = (_normalize_issue_audit_value(payload.get("source")) or "").lower()

    history: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        value = _normalize_issue_audit_value(row.get("value"))
        if not _is_meaningful_issue_audit_value(value):
            continue
        source = (_normalize_issue_audit_value(row.get("source")) or "").lower()
        timestamp = _normalize_issue_audit_value(row.get("timestamp")) or ""
        dedupe_key = (source, timestamp, value.casefold())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        history.append((source, timestamp, value))

    if not history:
        return False

    if payload.get("supporting_sources") is None:
        supporting_sources: list[str] = []
        seen_sources: set[str] = set()
        for source, _timestamp, value in history:
            if value.casefold() != payload_value.casefold():
                continue
            if not source or source == payload_source or source in seen_sources:
                continue
            seen_sources.add(source)
            supporting_sources.append(source)
        if supporting_sources:
            payload["supporting_sources"] = supporting_sources

    scoped_history = history
    if payload_source:
        source_rows = [row for row in history if row[0] == payload_source]
        if source_rows:
            scoped_history = source_rows

    deterministic_seen = False
    collapsed_history: list[tuple[str, str, str]] = []
    for source, timestamp, value in scoped_history:
        if source == "deterministic":
            if deterministic_seen:
                continue
            deterministic_seen = True
        collapsed_history.append((source, timestamp, value))
    scoped_history = collapsed_history

    total_runs = len(scoped_history)
    support_runs = sum(
        1
        for _, _, value in scoped_history
        if value.casefold() == payload_value.casefold()
    )
    if total_runs <= 0 or support_runs <= 0:
        return False

    _ensure_issue_audit_source(payload)
    agreement_rate = float(support_runs) / float(total_runs)
    if payload.get("promoted") is None:
        payload["promoted"] = (
            support_runs == total_runs
            and total_runs >= _MIN_ISSUES_PROMOTION_SUPPORT_RUNS
        )
    payload["support_runs"] = support_runs
    payload["total_runs"] = total_runs
    payload["available_runs"] = total_runs
    payload["agreement_rate"] = agreement_rate
    if payload.get("certainty_class") is None:
        payload["certainty_class"] = (
            "sure"
            if (
                support_runs == total_runs
                and total_runs >= _MIN_ISSUES_PROMOTION_SUPPORT_RUNS
            )
            else "uncertain"
        )
    if payload.get("supporting_steps") is None:
        step = _infer_issue_supporting_step(payload)
        payload["supporting_steps"] = [step] if step else []
    return True


def _build_stage_audit_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    source = str(row.get("source") or "").strip()
    return {
        "timestamp": row.get("updated_at"),
        "source": source or None,
        "decision_rule": f"{source}_stage_value" if source else "stage_value",
        "value": row.get("value"),
        "evidence": {
            "updated_at": row.get("updated_at"),
            "stage_source": source or None,
        },
    }


def _compose_parent_pdp_text(extras: Mapping[str, Any]) -> str:
    parts: list[str] = []
    seen: set[str] = set()

    def _add(value: Any) -> None:
        if isinstance(value, (list, tuple)):
            for item in value:
                _add(item)
            return
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        parts.append(text)

    _add(extras.get("summary"))
    _add(extras.get("short_description"))
    _add(extras.get("long_description"))
    _add(extras.get("highlights"))
    _add(extras.get("reviews_positive"))
    _add(extras.get("reviews_negative"))

    details = extras.get("details")
    if isinstance(details, Mapping):
        for key in (
            "description_markdown",
            "description",
            "usage",
            "ingredients",
            "restrictions",
            "features",
            "benefits",
            "details",
        ):
            _add(details.get(key))

    return "\n".join(parts).strip()


def _load_parent_card_context(
    *,
    pdp_store_path: Path | str,
    key_pairs: list[tuple[str, str]],
) -> dict[tuple[str, str], dict[str, Any]]:
    normalized_pairs = [
        (str(retailer or "").strip(), str(parent_id or "").strip())
        for retailer, parent_id in key_pairs
        if str(retailer or "").strip() and str(parent_id or "").strip()
    ]
    if not normalized_pairs:
        return {}

    parent_conditions: list[str] = []
    parent_params: list[str] = []
    for retailer, parent_id in normalized_pairs:
        parent_conditions.append("(retailer = ? AND parent_product_id = ?)")
        parent_params.extend([retailer, parent_id])

    parent_query = (
        "SELECT retailer, parent_product_id, pdp_url, brand_raw, title_raw, extras "
        "FROM parent_products WHERE " + " OR ".join(parent_conditions)
    )
    variant_query = (
        "SELECT retailer, parent_product_id, variant_id, hero_image_url, swatch_image_url, shade_name_raw "
        "FROM variants WHERE " + " OR ".join(parent_conditions)
    )

    parent_rows: list[tuple[Any, ...]]
    variant_rows: list[tuple[Any, ...]]
    with connect_pdp_database(pdp_store_path) as conn:
        parent_rows = conn.execute(parent_query, parent_params).fetchall()
        variant_rows = conn.execute(variant_query, parent_params).fetchall()

    context: dict[tuple[str, str], dict[str, Any]] = {}
    for (
        retailer,
        parent_product_id,
        pdp_url,
        brand_raw,
        title_raw,
        extras_raw,
    ) in parent_rows:
        extras = _parse_json_object(extras_raw)
        context[(str(retailer), str(parent_product_id))] = {
            "pdp_url": str(pdp_url or "").strip(),
            "brand": str(brand_raw or "").strip(),
            "product_name": str(title_raw or "").strip(),
            "pdp_text": _compose_parent_pdp_text(extras),
            "extras": extras,
        }

    for (
        retailer,
        parent_product_id,
        variant_id,
        hero_image_url,
        swatch_image_url,
        shade_name_raw,
    ) in variant_rows:
        key = (str(retailer), str(parent_product_id))
        payload = context.setdefault(
            key,
            {
                "pdp_url": "",
                "brand": "",
                "product_name": "",
                "pdp_text": "",
                "extras": {},
            },
        )
        if not payload.get("hero_image_url") and str(hero_image_url or "").strip():
            payload["hero_image_url"] = str(hero_image_url).strip()
        if not payload.get("swatch_image_url") and str(swatch_image_url or "").strip():
            payload["swatch_image_url"] = str(swatch_image_url).strip()
        if not payload.get("sample_variant_id") and str(variant_id or "").strip():
            payload["sample_variant_id"] = str(variant_id).strip()
        if not payload.get("sample_variant_name") and str(shade_name_raw or "").strip():
            payload["sample_variant_name"] = str(shade_name_raw).strip()

    return context


def _build_cross_retailer_diagnostic_groups(
    *,
    store: PDPStore,
    pdp_store_path: Path | str,
    attribute_id: str,
    category_key: str,
    aggregated: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    summary = (
        aggregated.get("evidence_summary_json")
        if isinstance(aggregated, Mapping)
        else {}
    )
    if not isinstance(summary, Mapping):
        return []
    sample_groups = summary.get("sample_groups")
    if not isinstance(sample_groups, list):
        return []

    keys: list[tuple[str, str, str]] = []
    parent_key_pairs: list[tuple[str, str]] = []
    for sample in sample_groups:
        if not isinstance(sample, Mapping):
            continue
        for entry in sample.get("entries") or []:
            if not isinstance(entry, Mapping):
                continue
            retailer = str(entry.get("retailer") or "").strip()
            parent_product_id = str(entry.get("parent_product_id") or "").strip()
            variant_id = str(entry.get("variant_id") or "").strip()
            if retailer and parent_product_id:
                keys.append((retailer, parent_product_id, ""))
                parent_key_pairs.append((retailer, parent_product_id))

    parent_ids = sorted(
        {parent_id for _retailer, parent_id in parent_key_pairs if parent_id}
    )
    retailers = sorted(
        {retailer for retailer, _parent_id in parent_key_pairs if retailer}
    )
    if parent_ids:
        store.backfill_attribute_audit_from_values(
            sources=("deterministic_explicit", "deterministic", "llm"),
            retailers=retailers,
            parent_ids=parent_ids,
        )

    audit_rows = store.fetch_attribute_audit_rows(
        attribute_id=attribute_id,
        row_type="parent",
        keys=keys,
    )
    stage_rows = store.fetch_attribute_stage_rows(
        attribute_id=attribute_id,
        row_type="parent",
        keys=keys,
        sources=("deterministic_explicit", "deterministic", "llm"),
    )
    parent_context = _load_parent_card_context(
        pdp_store_path=pdp_store_path,
        key_pairs=parent_key_pairs,
    )

    audit_map: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in audit_rows:
        key = (
            str(row.get("retailer") or "").strip(),
            str(row.get("parent_product_id") or "").strip(),
            str(row.get("variant_id") or "").strip(),
        )
        audit_map.setdefault(key, []).append(row)
    audit_parent_map: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in audit_rows:
        key = (
            str(row.get("retailer") or "").strip(),
            str(row.get("parent_product_id") or "").strip(),
        )
        audit_parent_map.setdefault(key, []).append(row)

    stage_map: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in stage_rows:
        key = (
            str(row.get("retailer") or "").strip(),
            str(row.get("parent_product_id") or "").strip(),
            str(row.get("variant_id") or "").strip(),
        )
        stage_map.setdefault(key, []).append(row)
    stage_parent_map: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in stage_rows:
        key = (
            str(row.get("retailer") or "").strip(),
            str(row.get("parent_product_id") or "").strip(),
        )
        stage_parent_map.setdefault(key, []).append(row)

    source_priority = {
        "explicit": 0,
        "deterministic_explicit": 0,
        "web": 1,
        "vision": 2,
        "llm": 3,
        "deterministic": 4,
    }
    groups: list[dict[str, Any]] = []

    for index, sample in enumerate(sample_groups):
        if not isinstance(sample, Mapping):
            continue
        entries = sample.get("entries")
        if not isinstance(entries, list):
            continue
        cards: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            retailer = str(entry.get("retailer") or "").strip()
            parent_product_id = str(entry.get("parent_product_id") or "").strip()
            variant_id = str(entry.get("variant_id") or "").strip()
            key = (retailer, parent_product_id, "")
            parent_key = (retailer, parent_product_id)
            target_value = _normalize_key(entry.get("value_id"))

            chosen_audit: dict[str, Any] | None = None
            history_rows = audit_map.get(key, [])
            for candidate in history_rows:
                if _normalize_key(candidate.get("value")) == target_value:
                    chosen_audit = {
                        "timestamp": candidate.get("timestamp"),
                        "source": candidate.get("source"),
                        "decision_rule": candidate.get("decision_rule"),
                        "value": candidate.get("value"),
                        "evidence": _parse_json_object(candidate.get("evidence_json")),
                    }
                    break

            if chosen_audit is None and variant_id:
                history_rows = audit_parent_map.get(parent_key, [])
                for candidate in history_rows:
                    if _normalize_key(candidate.get("value")) == target_value:
                        chosen_audit = {
                            "timestamp": candidate.get("timestamp"),
                            "source": candidate.get("source"),
                            "decision_rule": candidate.get("decision_rule"),
                            "value": candidate.get("value"),
                            "evidence": _parse_json_object(
                                candidate.get("evidence_json")
                            ),
                        }
                        break

            if chosen_audit is None:
                ordered_stage_rows = sorted(
                    stage_map.get(key, []),
                    key=lambda row: (
                        source_priority.get(str(row.get("source") or "").strip(), 99),
                        str(row.get("updated_at") or ""),
                    ),
                )
                for candidate in ordered_stage_rows:
                    if _normalize_key(candidate.get("value")) == target_value:
                        chosen_audit = _build_stage_audit_payload(candidate)
                        break
                if chosen_audit is None and variant_id:
                    ordered_stage_rows = sorted(
                        stage_parent_map.get(parent_key, []),
                        key=lambda row: (
                            source_priority.get(
                                str(row.get("source") or "").strip(), 99
                            ),
                            str(row.get("updated_at") or ""),
                        ),
                    )
                    for candidate in ordered_stage_rows:
                        if _normalize_key(candidate.get("value")) == target_value:
                            chosen_audit = _build_stage_audit_payload(candidate)
                            break
                if chosen_audit is None and ordered_stage_rows:
                    chosen_audit = _build_stage_audit_payload(ordered_stage_rows[0])

            if chosen_audit is not None:
                if not _attach_issue_history_metrics_from_audit_rows(
                    chosen_audit,
                    history_rows,
                ):
                    _attach_issue_single_signal_metrics(chosen_audit)

            card = dict(entry)
            parent_payload = parent_context.get((retailer, parent_product_id), {})
            # Issue cards must show only retailer-native evidence from raw parent rows.
            # If none is available, leave PDP text empty rather than falling back to
            # shared/postfilled text from the review cache.
            card["pdp_text"] = ""
            if parent_payload:
                native_pdp_url = str(parent_payload.get("pdp_url") or "").strip()
                if native_pdp_url:
                    card["pdp_url"] = native_pdp_url
                elif not str(card.get("pdp_url") or "").strip():
                    card["pdp_url"] = parent_payload.get("pdp_url")
                if not str(card.get("brand") or "").strip():
                    card["brand"] = parent_payload.get("brand")
                if not str(card.get("product_name") or "").strip():
                    card["product_name"] = parent_payload.get("product_name")
                card["pdp_text"] = str(parent_payload.get("pdp_text") or "").strip()
                if not str(card.get("hero_image_url") or "").strip():
                    card["hero_image_url"] = parent_payload.get("hero_image_url")
                if not str(card.get("swatch_image_url") or "").strip():
                    card["swatch_image_url"] = parent_payload.get("swatch_image_url")
                if not str(card.get("variant_id") or "").strip():
                    card["variant_id"] = parent_payload.get("sample_variant_id")
                if not str(card.get("sample_variant_name") or "").strip():
                    card["sample_variant_name"] = parent_payload.get(
                        "sample_variant_name"
                    )
            if chosen_audit is not None:
                card["attribute_audit"] = chosen_audit
            cards.append(card)

        label = ""
        if cards:
            first = cards[0]
            label = str(
                first.get("display_name") or first.get("product_name") or ""
            ).strip()
        groups.append(
            {
                "group_index": index + 1,
                "group_label": label or f"Product group {index + 1}",
                "category_key": category_key,
                "attribute_id": attribute_id,
                "retailers": [
                    str(item).strip()
                    for item in (sample.get("retailers") or [])
                    if str(item).strip()
                ],
                "cards": cards,
            }
        )
    return groups


def _queue_detail_payload(
    *,
    pdp_store_path: Path | str,
    taxonomy: Mapping[str, Any],
    item: Mapping[str, Any],
) -> dict[str, Any]:
    category_key = str(item.get("category_key") or "").strip()
    attribute_id = str(item.get("attribute_id") or "").strip()
    detail: dict[str, Any] = {
        "item": dict(item),
        "taxonomy_context": build_taxonomy_context(
            taxonomy,
            category_key=category_key,
            attribute_id=attribute_id,
        ),
        "aggregated": None,
    }
    if str(item.get("origin") or "") == "user_created":
        return detail
    run_id = str(item.get("run_id") or "").strip()
    aggregated_row_ref = str(item.get("aggregated_row_ref") or "").strip()
    if run_id and aggregated_row_ref:
        detail["aggregated"] = load_aggregated_candidate_row(
            pdp_store_path=pdp_store_path,
            run_id=run_id,
            aggregated_row_ref=aggregated_row_ref,
        )
        if (
            str(item.get("candidate_type") or "").strip()
            == "cross_retailer_assignment_inconsistency"
        ):
            detail["diagnostic_groups"] = _build_cross_retailer_diagnostic_groups(
                store=PDPStore(pdp_store_path),
                pdp_store_path=pdp_store_path,
                attribute_id=attribute_id,
                category_key=category_key,
                aggregated=detail["aggregated"],
            )
    return detail


def _attach_taxonomy_labels_to_queue_items(
    items: list[dict[str, Any]],
    *,
    taxonomy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    labeled_items: list[dict[str, Any]] = []
    for item in items:
        category_key = str(item.get("category_key") or "").strip()
        attribute_id = str(item.get("attribute_id") or "").strip()
        if not category_key or not attribute_id:
            labeled_items.append(item)
            continue
        taxonomy_context = build_taxonomy_context(
            taxonomy,
            category_key=category_key,
            attribute_id=attribute_id,
        )
        labeled_items.append(
            {
                **item,
                "category_label": (
                    taxonomy_context.get("category_label")
                    or item.get("category_label")
                    or item.get("category_key")
                ),
                "attribute_label": (
                    taxonomy_context.get("attribute_label")
                    or item.get("attribute_label")
                    or item.get("attribute_id")
                ),
            }
        )
    return labeled_items


@site_router.get("/page", include_in_schema=False)
def taxonomy_governance_page(request: Request) -> Any:
    return _render_taxonomy_issue_page(request)


@issues_site_router.get("/page", include_in_schema=False)
def taxonomy_issues_page(request: Request) -> Any:
    return _render_taxonomy_issue_page(request)


def _render_taxonomy_issue_page(request: Request) -> Any:
    if templates is None:  # pragma: no cover - defensive fallback
        raise HTTPException(
            status_code=503, detail="Templating support is not available."
        )
    lang = resolve_language(request)
    page_label = get_navigation_label(lang, "/review/issues/page")
    response = templates.TemplateResponse(
        request,
        "review_taxonomy_queue_react.html",
        {
            "request": request,
            "lang": lang,
            "page_label": page_label,
            "copy": get_page_copy("product_attributes", lang),
            "asset_version": _static_asset_version(
                "static/js/review-taxonomy-queue-react.js"
            ),
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/queue/run", response_model=TaxonomyQueueRunResponse)
def run_taxonomy_queue() -> TaxonomyQueueRunResponse:
    store = _store()
    taxonomy = _load_config_from_disk()
    result = build_phase1_taxonomy_candidate_run(
        taxonomy,
        pdp_store_path=store.path,
    )
    surfaced_rows = _read_surfaced_candidates(store.path, result["run_id"])
    inserted, refreshed, suppressed = _upsert_surfaced_queue_items(
        store=store,
        surfaced_rows=surfaced_rows,
    )
    _prune_stale_surfaced_queue_items(
        store=store,
        candidate_domain="taxonomy",
        candidate_types=list(result["aggregated_counts"].keys()),
        surfaced_rows=surfaced_rows,
    )
    return TaxonomyQueueRunResponse(
        run_id=result["run_id"],
        surfaced_count=int(result["surfaced_count"]),
        inserted_count=inserted,
        refreshed_count=refreshed,
        suppressed_count=suppressed,
        aggregated_counts={
            key: int(value) for key, value in result["aggregated_counts"].items()
        },
    )


@router.get("/queue/items", response_model=TaxonomyQueueListResponse)
def list_queue_items(
    status: str | None = Query(default=None),
    candidate_type: str | None = Query(default=None),
    category_key: str | None = Query(default=None),
    attribute_id: str | None = Query(default=None),
    origin: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> TaxonomyQueueListResponse:
    items = _store().list_review_queue_items(
        status=str(status).strip() if status else None,
        candidate_domain="taxonomy",
        candidate_type=str(candidate_type).strip() if candidate_type else None,
        category_key=_normalize_key(category_key) if category_key else None,
        attribute_id=_normalize_key(attribute_id) if attribute_id else None,
        origin=str(origin).strip() if origin else None,
        limit=limit,
    )
    try:
        items = _attach_taxonomy_labels_to_queue_items(
            items,
            taxonomy=_load_config_from_disk(),
        )
    except Exception:  # pragma: no cover - defensive live fallback
        logger.exception("Failed to attach taxonomy labels to queue items")
    return TaxonomyQueueListResponse(total=len(items), items=items)


@router.get("/queue/items/{queue_item_id}")
def get_queue_item(queue_item_id: str) -> dict[str, Any]:
    store = _store()
    item = store.get_review_queue_item(queue_item_id)
    if item is None or str(item.get("candidate_domain") or "") != "taxonomy":
        raise HTTPException(status_code=404, detail="Queue item not found.")
    taxonomy: Mapping[str, Any]
    taxonomy_error = ""
    try:
        taxonomy = _load_config_from_disk()
    except Exception as exc:  # pragma: no cover - defensive live fallback
        logger.exception(
            "Failed to load taxonomy while building issue detail for queue_item_id=%s",
            queue_item_id,
        )
        taxonomy = {}
        taxonomy_error = str(exc).strip() or "Unable to load taxonomy."
    payload = _queue_detail_payload(
        pdp_store_path=store.path,
        taxonomy=taxonomy,
        item=item,
    )
    if taxonomy_error:
        payload["taxonomy_context"] = {
            **dict(payload.get("taxonomy_context") or {}),
            "error": taxonomy_error,
        }
    return payload


@router.get("/draft", response_model=TaxonomyDraftResponse)
def get_taxonomy_draft() -> TaxonomyDraftResponse:
    store = _store()
    return _draft_response_payload(store=store)


@router.get("/draft/preview", response_model=TaxonomyDraftResponse)
def preview_taxonomy_draft() -> TaxonomyDraftResponse:
    store = _store()
    return _draft_response_payload(store=store)


@router.post("/draft/reset", response_model=TaxonomyDraftResponse)
def reset_taxonomy_draft(
    request: ResetTaxonomyDraftRequest,
    http_request: Request,
) -> TaxonomyDraftResponse:
    store = _store()
    now = _now_iso()
    reviewer = _request_actor_email(http_request)
    store.delete_taxonomy_draft()
    store.append_taxonomy_governance_audit(
        timestamp=now,
        action="draft_reset",
        actor=reviewer,
        details={},
    )
    return _draft_response_payload(store=store)


@router.post("/draft/publish", response_model=PublishTaxonomyConfigResponse)
def publish_taxonomy_draft(
    request: PublishTaxonomyDraftRequest,
    http_request: Request,
) -> PublishTaxonomyConfigResponse:
    store = _store()
    draft_row = store.get_taxonomy_draft()
    if draft_row is None or not isinstance(draft_row.get("config"), Mapping):
        raise HTTPException(
            status_code=409, detail="No draft taxonomy is available to publish."
        )

    previous = _load_config_from_disk()
    normalized_config, errors, warnings = _validate_config(draft_row["config"])
    if errors or normalized_config is None:
        raise HTTPException(
            status_code=400,
            detail={"errors": errors, "warnings": warnings},
        )

    explicit_rule_summary, explicit_rule_impacts = _summarize_explicit_rule_preview(
        normalized_config
    )
    if (
        int(explicit_rule_summary.get("newly_invalid_active_rules") or 0) > 0
        and not request.acknowledge_invalid_active_explicit_rules
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Publishing this taxonomy would invalidate active explicit rules. "
                    "Preview the impact and acknowledge it before publishing."
                ),
                "explicit_rules_path": str(DEFAULT_EXPLICIT_RULES_PATH),
                "explicit_rule_summary": explicit_rule_summary,
                "explicit_rule_impacts": explicit_rule_impacts,
            },
        )

    response = _publish_taxonomy_config(
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
            "last_queue_item_id": draft_row.get("last_queue_item_id"),
        },
        diff_summary=_semantic_diff(previous, normalized_config)[0],
    )
    store.delete_taxonomy_draft()
    return response


@router.get(
    "/queue/items/{queue_item_id}/preview-apply",
    response_model=PreviewQueueItemApplyResponse,
)
def preview_apply_queue_item(queue_item_id: str) -> PreviewQueueItemApplyResponse:
    store = _store()
    item = store.get_review_queue_item(queue_item_id)
    if item is None or str(item.get("candidate_domain") or "") != "taxonomy":
        raise HTTPException(status_code=404, detail="Queue item not found.")
    if str(item.get("origin") or "").strip() != "user_created":
        raise HTTPException(
            status_code=400,
            detail="Draft preview is currently supported only for user-created taxonomy proposals.",
        )
    payload = item.get("payload_json")
    if not isinstance(payload, Mapping):
        raise HTTPException(
            status_code=400, detail="Queue item has no proposal payload."
        )
    return _preview_user_taxonomy_proposal(store=store, payload=payload)


@router.post("/queue/items/{queue_item_id}/approve")
def approve_queue_item(
    queue_item_id: str,
    request: QueueDecisionRequest,
    http_request: Request,
) -> dict[str, Any]:
    item = _store().update_review_queue_item_status(
        queue_item_id,
        status="approved",
        reviewer=_request_actor_email(http_request),
        decision_reason=str(request.decision_reason or "").strip() or None,
        updated_at=_now_iso(),
    )
    if item is None or str(item.get("candidate_domain") or "") != "taxonomy":
        raise HTTPException(status_code=404, detail="Queue item not found.")
    return item


@router.post("/queue/items/{queue_item_id}/reject")
def reject_queue_item(
    queue_item_id: str,
    request: QueueDecisionRequest,
    http_request: Request,
) -> dict[str, Any]:
    item = _store().update_review_queue_item_status(
        queue_item_id,
        status="rejected",
        reviewer=_request_actor_email(http_request),
        decision_reason=str(request.decision_reason or "").strip() or None,
        updated_at=_now_iso(),
    )
    if item is None or str(item.get("candidate_domain") or "") != "taxonomy":
        raise HTTPException(status_code=404, detail="Queue item not found.")
    return item


@router.post("/queue/items/{queue_item_id}/apply")
def apply_queue_item(
    queue_item_id: str,
    request: ApplyQueueItemRequest,
    http_request: Request,
) -> dict[str, Any]:
    store = _store()
    item = store.get_review_queue_item(queue_item_id)
    if item is None or str(item.get("candidate_domain") or "") != "taxonomy":
        raise HTTPException(status_code=404, detail="Queue item not found.")
    if str(item.get("status") or "").strip().lower() != "approved":
        raise HTTPException(
            status_code=409,
            detail="Queue item must be approved before it can be applied.",
        )
    if str(item.get("origin") or "").strip() != "user_created":
        raise HTTPException(
            status_code=400,
            detail=(
                "Draft apply is currently supported only for user-created taxonomy "
                "proposals."
            ),
        )
    payload = item.get("payload_json")
    if not isinstance(payload, Mapping):
        raise HTTPException(
            status_code=400, detail="Queue item has no proposal payload."
        )
    proposal_type = _normalize_key(payload.get("proposal_type"))
    if proposal_type not in APPLICABLE_USER_PROPOSAL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Draft apply currently supports only: "
                + ", ".join(sorted(APPLICABLE_USER_PROPOSAL_TYPES))
            ),
        )

    published = _load_config_from_disk()
    current_draft = store.get_taxonomy_draft()
    base_config = (
        dict(current_draft.get("config") or {})
        if isinstance(current_draft, Mapping) and current_draft.get("config")
        else published
    )
    try:
        next_draft, mutation_summary = apply_user_taxonomy_proposal(
            base_config, payload
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    normalized_config, errors, warnings = _validate_config(next_draft)
    if errors or normalized_config is None:
        raise HTTPException(
            status_code=400,
            detail={"errors": errors, "warnings": warnings},
        )

    now = _now_iso()
    reviewer = _request_actor_email(http_request)
    store.upsert_taxonomy_draft(
        config=normalized_config,
        updated_at=now,
        updated_by=reviewer,
        last_queue_item_id=queue_item_id,
    )
    updated_item = store.update_review_queue_item_status(
        queue_item_id,
        status="applied",
        reviewer=reviewer,
        decision_reason=str(item.get("decision_reason") or "").strip() or None,
        updated_at=now,
    )
    store.append_taxonomy_governance_audit(
        timestamp=now,
        action="draft_applied",
        actor=reviewer,
        category_key=str(item.get("category_key") or "") or None,
        attribute_id=str(item.get("attribute_id") or "") or None,
        leaf_id=str(item.get("value_id") or "") or None,
        details={
            "queue_item_id": queue_item_id,
            "proposal_type": proposal_type,
            "mutation_summary": mutation_summary,
            "warnings": warnings,
        },
    )
    return {
        "item": updated_item,
        "draft": _draft_response_payload(store=store, taxonomy=published),
        "mutation_summary": mutation_summary,
    }


@router.post("/queue/proposals")
def create_queue_proposal(
    request: CreateTaxonomyProposalRequest,
    http_request: Request,
) -> dict[str, Any]:
    now = _now_iso()
    category_key = _normalize_key(request.category_key)
    attribute_id = _normalize_key(request.attribute_id)
    value_id = _normalize_key(request.value_id) if request.value_id else ""
    target_value_ids = [
        _normalize_key(item)
        for item in request.target_value_ids
        if _normalize_key(item)
    ]
    new_value_labels = [
        str(item).strip() for item in request.new_value_labels if str(item).strip()
    ]
    proposal_type = _normalize_key(request.proposal_type)
    title = (
        str(request.title).strip()
        if request.title and str(request.title).strip()
        else f"{proposal_type.replace('_', ' ').title()} in {attribute_id}"
    )
    item = {
        "queue_item_id": uuid.uuid4().hex,
        "candidate_domain": "taxonomy",
        "candidate_type": proposal_type,
        "candidate_key": f"user|{proposal_type}|{uuid.uuid4().hex}",
        "aggregated_row_ref": None,
        "run_id": None,
        "evidence_signature": None,
        "origin": "user_created",
        "status": "open",
        "category_key": category_key,
        "attribute_id": attribute_id,
        "value_id": value_id or None,
        "title": title,
        "short_reason": str(request.note).strip(),
        "priority_score": 1000.0,
        "confidence_level": "high",
        "decision_ease": "medium",
        "support_product_count": None,
        "support_retailer_count": None,
        "reviewer": _request_actor_email(http_request),
        "decision_reason": None,
        "payload_json": {
            "proposal_type": proposal_type,
            "category_key": category_key,
            "attribute_id": attribute_id,
            "value_id": value_id or None,
            "target_value_ids": target_value_ids,
            "new_value_labels": new_value_labels,
            "term_text": str(request.term_text or "").strip() or None,
            "new_label": str(request.new_label or "").strip() or None,
            "note": str(request.note).strip(),
        },
        "created_at": now,
        "updated_at": now,
    }
    _store().upsert_review_queue_items([item])
    stored = _store().get_review_queue_item(str(item["queue_item_id"]))
    if stored is None:
        raise HTTPException(status_code=500, detail="Failed to create proposal.")
    return stored


@router.get("/config")
def read_config() -> dict[str, Any]:
    config = _load_config_from_disk()
    return {"path": str(TAXONOMY_PATH), "config": config}


@router.post("/config/validate", response_model=ValidateTaxonomyConfigResponse)
def validate_config(
    request: ValidateTaxonomyConfigRequest,
) -> ValidateTaxonomyConfigResponse:
    config = request.config if request.config is not None else _load_config_from_disk()
    normalized_config, errors, warnings = _validate_config(config)
    return ValidateTaxonomyConfigResponse(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        normalized_config=normalized_config if not errors else None,
    )


@router.post("/config/preview", response_model=PreviewTaxonomyConfigResponse)
def preview_config(
    request: ValidateTaxonomyConfigRequest,
) -> PreviewTaxonomyConfigResponse:
    config = request.config if request.config is not None else _load_config_from_disk()
    normalized_config, errors, warnings = _validate_config(config)
    if errors or normalized_config is None:
        return PreviewTaxonomyConfigResponse(
            valid=False,
            errors=errors,
            warnings=warnings,
            explicit_rules_path=str(DEFAULT_EXPLICIT_RULES_PATH),
            explicit_rule_summary={
                "total_rules": 0,
                "active_rules": 0,
                "current_invalid_rules": 0,
                "current_invalid_active_rules": 0,
                "draft_invalid_rules": 0,
                "draft_invalid_active_rules": 0,
                "newly_invalid_rules": 0,
                "newly_invalid_active_rules": 0,
            },
            explicit_rule_impacts=[],
        )

    summary, impacts = _summarize_explicit_rule_preview(normalized_config)
    return PreviewTaxonomyConfigResponse(
        valid=True,
        errors=[],
        warnings=warnings,
        explicit_rules_path=str(DEFAULT_EXPLICIT_RULES_PATH),
        explicit_rule_summary=summary,
        explicit_rule_impacts=impacts,
    )


@router.post("/config/publish", response_model=PublishTaxonomyConfigResponse)
def publish_config(
    request: PublishTaxonomyConfigRequest,
    http_request: Request,
) -> PublishTaxonomyConfigResponse:
    previous = _load_config_from_disk()
    normalized_config, errors, warnings = _validate_config(request.config)
    if errors or normalized_config is None:
        raise HTTPException(
            status_code=400,
            detail={"errors": errors, "warnings": warnings},
        )

    explicit_rule_summary, explicit_rule_impacts = _summarize_explicit_rule_preview(
        normalized_config
    )
    if (
        int(explicit_rule_summary.get("newly_invalid_active_rules") or 0) > 0
        and not request.acknowledge_invalid_active_explicit_rules
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Publishing this taxonomy would invalidate active explicit rules. "
                    "Preview the impact and acknowledge it before publishing."
                ),
                "explicit_rules_path": str(DEFAULT_EXPLICIT_RULES_PATH),
                "explicit_rule_summary": explicit_rule_summary,
                "explicit_rule_impacts": explicit_rule_impacts,
            },
        )

    return _publish_taxonomy_config(
        previous=previous,
        normalized_config=normalized_config,
        actor=_request_actor_email(http_request),
        note=request.note,
        version=request.version,
        warnings=warnings,
        audit_action="config_published",
    )


@router.get("/audit", response_model=TaxonomyGovernanceAuditResponse)
def taxonomy_governance_audit(
    limit: int = Query(default=200, ge=1, le=2000),
) -> TaxonomyGovernanceAuditResponse:
    store = _store()
    audit = store.list_taxonomy_governance_audit(limit=limit)
    versions = store.list_taxonomy_config_versions(limit=max(10, min(limit, 200)))
    return TaxonomyGovernanceAuditResponse(audit=audit, versions=versions)
