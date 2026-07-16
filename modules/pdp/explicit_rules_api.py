from __future__ import annotations

import datetime as dt
import json
import re
import time
from pathlib import Path
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException, Query, Request

try:  # pragma: no cover - optional template dependency
    from fastapi.templating import Jinja2Templates
except Exception:  # noqa: BLE001
    Jinja2Templates = None  # type: ignore[misc,assignment]
from pydantic import BaseModel, Field

from modules.add_attributes.attribute_taxonomy import get_attribute_taxonomy
from modules.add_attributes.explicit_declaration_classifier import (
    DEFAULT_ACTIVATION_DEFAULTS,
    DEFAULT_EXPLICIT_RULES_PATH,
    load_explicit_declaration_rules,
    validate_explicit_declaration_rules,
)
from modules.auth.dependencies import maybe_current_user
from modules.pdp.language import get_navigation_label, get_page_copy, resolve_language
from modules.pdp.review_constants import DEFAULT_PDP_STORE_PATH
from modules.pdp.store import PDPStore

router = APIRouter(prefix="/review/explicit-rules", tags=["review"])
site_router = APIRouter(prefix="/review/explicit-rules")
templates = Jinja2Templates(directory="templates") if Jinja2Templates else None


class CandidateListResponse(BaseModel):
    total: int
    candidates: list[dict[str, Any]]


class ApproveCandidateRequest(BaseModel):
    pattern: str | None = None
    reviewer_note: str | None = None
    reviewed_samples: int | None = Field(default=None, ge=0)
    precision_estimate: float | None = Field(default=None, ge=0.0, le=1.0)


class RejectCandidateRequest(BaseModel):
    reason: str = Field(min_length=1)
    reviewer_note: str | None = None


class ValidateConfigRequest(BaseModel):
    config: dict[str, Any] | None = None


class ValidateConfigResponse(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]


class PublishConfigRequest(BaseModel):
    config: dict[str, Any]
    note: str | None = None


class PublishConfigResponse(BaseModel):
    version: str
    updated_at: str
    diff_summary: dict[str, Any]


class ExplicitRulesAuditResponse(BaseModel):
    audit: list[dict[str, Any]]
    versions: list[dict[str, Any]]
    precision_metrics: list[dict[str, Any]]


__all__ = ["router", "site_router"]


def _rules_path() -> Path:
    return DEFAULT_EXPLICIT_RULES_PATH


def _store() -> PDPStore:
    return PDPStore(DEFAULT_PDP_STORE_PATH)


def _load_config_from_disk() -> dict[str, Any]:
    return load_explicit_declaration_rules(_rules_path())


def _request_actor_email(request: Request) -> str | None:
    user = maybe_current_user(request)
    email = str(getattr(user, "email", "") or "").strip().lower()
    return email or None


def _is_broad_pattern(signal: Mapping[str, object]) -> bool:
    pattern = str(signal.get("pattern") or "").strip()
    if not pattern:
        return True
    match_type = str(signal.get("type") or "phrase").strip().lower()
    if match_type == "regex":
        tokens = re.findall(r"[a-z0-9]+", pattern.casefold())
        return len(tokens) <= 1
    tokens = re.findall(r"[a-z0-9]+", pattern.casefold())
    return len(tokens) <= 1


def _count_active_rules(config: Mapping[str, object]) -> int:
    categories = config.get("categories")
    if not isinstance(categories, Mapping):
        return 0
    count = 0
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
                    status = str(signal.get("status") or "active").strip().lower()
                    if status == "active":
                        count += 1
    return count


def _validate_activation_quality(
    config: Mapping[str, object],
) -> tuple[list[str], list[str]]:
    metadata = config.get("metadata")
    metadata_map = dict(metadata) if isinstance(metadata, Mapping) else {}
    defaults_raw = metadata_map.get("activation_defaults")
    defaults = (
        dict(defaults_raw)
        if isinstance(defaults_raw, Mapping)
        else dict(DEFAULT_ACTIVATION_DEFAULTS)
    )
    min_samples = defaults.get("min_reviewed_samples")
    if not isinstance(min_samples, int) or min_samples < 1:
        min_samples = DEFAULT_ACTIVATION_DEFAULTS["min_reviewed_samples"]
    min_precision = defaults.get("min_precision")
    if not isinstance(min_precision, (int, float)) or not (0 <= min_precision <= 1):
        min_precision = DEFAULT_ACTIVATION_DEFAULTS["min_precision"]
    requires_broad_justification = defaults.get("broad_pattern_requires_justification")
    if not isinstance(requires_broad_justification, bool):
        requires_broad_justification = DEFAULT_ACTIVATION_DEFAULTS[
            "broad_pattern_requires_justification"
        ]

    errors: list[str] = []
    warnings: list[str] = []
    categories = config.get("categories")
    if not isinstance(categories, Mapping):
        return errors, warnings
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
            for value_key, value_payload in values.items():
                if not isinstance(value_payload, Mapping):
                    continue
                signals = value_payload.get("certainty_signals")
                if not isinstance(signals, list):
                    continue
                for signal in signals:
                    if not isinstance(signal, Mapping):
                        continue
                    rule_id = (
                        str(signal.get("rule_id") or "").strip() or "(missing-rule-id)"
                    )
                    status = str(signal.get("status") or "active").strip().lower()
                    if status != "active":
                        continue
                    reviewed_samples = signal.get("reviewed_samples")
                    precision = signal.get("observed_precision")
                    if (
                        not isinstance(reviewed_samples, int)
                        or reviewed_samples < min_samples
                    ):
                        errors.append(
                            "Active rule "
                            f"'{rule_id}' for {category_key}/{attribute_id}/{value_key} "
                            f"requires reviewed_samples >= {min_samples}."
                        )
                    if not isinstance(precision, (int, float)) or float(
                        precision
                    ) < float(min_precision):
                        errors.append(
                            "Active rule "
                            f"'{rule_id}' for {category_key}/{attribute_id}/{value_key} "
                            f"requires observed_precision >= {min_precision:.2f}."
                        )
                    if requires_broad_justification and _is_broad_pattern(signal):
                        justification = str(
                            signal.get("reviewer_justification") or ""
                        ).strip()
                        if not justification:
                            errors.append(
                                f"Broad active rule '{rule_id}' requires reviewer_justification."
                            )
                    if _is_broad_pattern(signal):
                        warnings.append(
                            f"Rule '{rule_id}' is broad and should be monitored for drift."
                        )
    return errors, warnings


def _validate_config(config: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    taxonomy = get_attribute_taxonomy()
    try:
        validate_explicit_declaration_rules(config, taxonomy)
    except ValueError as exc:
        errors.append(str(exc))
    quality_errors, quality_warnings = _validate_activation_quality(config)
    errors.extend(quality_errors)
    warnings.extend(quality_warnings)
    return errors, warnings


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


def _diff_summary(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "previous_version": str(previous.get("version") or ""),
        "current_version": str(current.get("version") or ""),
        "previous_active_rules": _count_active_rules(previous),
        "current_active_rules": _count_active_rules(current),
    }


def _static_asset_version(path: str) -> str:
    target = Path(path)
    try:
        return str(int(target.stat().st_mtime))
    except OSError:
        return str(int(time.time()))


@site_router.get("/page", include_in_schema=False)
def explicit_rules_page(request: Request) -> Any:
    if templates is None:  # pragma: no cover - defensive fallback
        raise HTTPException(
            status_code=503, detail="Templating support is not available."
        )
    lang = resolve_language(request)
    page_label = get_navigation_label(lang, "/review/explicit-rules/page")
    response = templates.TemplateResponse(
        request,
        "review_explicit_rules_react.html",
        {
            "request": request,
            "lang": lang,
            "page_label": page_label,
            "copy": get_page_copy("product_attributes", lang),
            "asset_version": _static_asset_version(
                "static/js/review-explicit-rules-react.js"
            ),
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/candidates", response_model=CandidateListResponse)
def list_candidates(
    status: str | None = Query(default=None),
    category_key: str | None = Query(default=None),
    attribute_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
) -> CandidateListResponse:
    store = _store()
    candidates = store.list_explicit_rule_candidates(
        status=status,
        category_key=category_key,
        attribute_id=attribute_id,
        limit=limit,
    )
    return CandidateListResponse(total=len(candidates), candidates=candidates)


@router.post("/candidates/{candidate_id}/approve")
def approve_candidate(
    candidate_id: str, request: ApproveCandidateRequest, http_request: Request
) -> dict[str, Any]:
    store = _store()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    reviewer = _request_actor_email(http_request)
    updated = store.update_explicit_rule_candidate(
        candidate_id=candidate_id,
        status="approved",
        updated_at=now,
        pattern=request.pattern,
        reviewer_note=request.reviewer_note,
        rejection_reason=None,
        reviewer=reviewer,
        reviewed_samples=request.reviewed_samples,
        precision_estimate=request.precision_estimate,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    store.append_explicit_rules_audit(
        timestamp=now,
        action="candidate_approved",
        actor=reviewer,
        candidate_id=candidate_id,
        details={
            "pattern": updated.get("pattern"),
            "reviewer_note": request.reviewer_note,
            "reviewed_samples": request.reviewed_samples,
            "precision_estimate": request.precision_estimate,
        },
    )
    return updated


@router.post("/candidates/{candidate_id}/reject")
def reject_candidate(
    candidate_id: str, request: RejectCandidateRequest, http_request: Request
) -> dict[str, Any]:
    store = _store()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    reviewer = _request_actor_email(http_request)
    updated = store.update_explicit_rule_candidate(
        candidate_id=candidate_id,
        status="rejected",
        updated_at=now,
        reviewer_note=request.reviewer_note,
        rejection_reason=request.reason,
        reviewer=reviewer,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    store.append_explicit_rules_audit(
        timestamp=now,
        action="candidate_rejected",
        actor=reviewer,
        candidate_id=candidate_id,
        details={"reason": request.reason, "reviewer_note": request.reviewer_note},
    )
    return updated


@router.get("/config")
def read_config() -> dict[str, Any]:
    config = _load_config_from_disk()
    return {
        "path": str(_rules_path()),
        "config": config,
    }


@router.post("/config/validate", response_model=ValidateConfigResponse)
def validate_config(request: ValidateConfigRequest) -> ValidateConfigResponse:
    config = request.config if request.config is not None else _load_config_from_disk()
    errors, warnings = _validate_config(config)
    return ValidateConfigResponse(valid=not errors, errors=errors, warnings=warnings)


@router.post("/config/publish", response_model=PublishConfigResponse)
def publish_config(
    request: PublishConfigRequest, http_request: Request
) -> PublishConfigResponse:
    previous = _load_config_from_disk()
    config = dict(request.config)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    actor = _request_actor_email(http_request)
    if not str(config.get("updated_at") or "").strip():
        config["updated_at"] = now
    version = str(config.get("version") or "").strip()
    if not version:
        version = _next_version(str(previous.get("version") or ""))
        config["version"] = version

    errors, warnings = _validate_config(config)
    if errors:
        raise HTTPException(
            status_code=400, detail={"errors": errors, "warnings": warnings}
        )

    rules_path = _rules_path()
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    diff_summary = _diff_summary(previous, config)
    store = _store()
    store.append_explicit_rules_config_version(
        version=version,
        published_at=now,
        actor=actor,
        note=request.note,
        config=config,
        diff_summary=diff_summary,
    )
    store.append_explicit_rules_audit(
        timestamp=now,
        action="config_published",
        actor=actor,
        details={
            "version": version,
            "warnings": warnings,
            "diff_summary": diff_summary,
            "note": request.note,
        },
    )
    return PublishConfigResponse(
        version=version, updated_at=now, diff_summary=diff_summary
    )


@router.get("/audit", response_model=ExplicitRulesAuditResponse)
def explicit_rules_audit(
    limit: int = Query(default=200, ge=1, le=2000),
    run_id: str | None = Query(default=None),
) -> ExplicitRulesAuditResponse:
    store = _store()
    audit = store.list_explicit_rules_audit(limit=limit)
    versions = store.list_explicit_rules_config_versions(limit=max(10, min(limit, 200)))
    precision = store.fetch_explicit_precision_metrics(run_id=run_id, limit=limit)
    return ExplicitRulesAuditResponse(
        audit=audit,
        versions=versions,
        precision_metrics=precision,
    )
