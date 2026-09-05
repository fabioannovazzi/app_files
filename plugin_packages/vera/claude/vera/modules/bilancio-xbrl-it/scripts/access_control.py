#!/usr/bin/env python3
"""Tenant and role authorization primitives for the XBRL case service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

__all__ = ["RequestContext", "authorize"]

ROLE_CAPABILITIES = {
    "STUDIO_ADMIN": {"CREATE", "READ", "CONFIGURE", "ARCHIVE", "DELETE"},
    "PREPARER": {
        "CREATE",
        "READ",
        "INGEST",
        "PREPARE",
        "QUESTIONNAIRE",
        "QUEUE",
        "VALIDATE",
    },
    "REVIEWER": {
        "CREATE",
        "READ",
        "INGEST",
        "PREPARE",
        "QUESTIONNAIRE",
        "QUEUE",
        "VALIDATE",
        "APPROVE",
        "EXPORT",
        "OVERRIDE",
        "EXTERNAL_VALIDATION",
        "DOWNLOAD_ARTIFACT",
    },
    "CLIENT_CONTRIBUTOR": {"READ_ASSIGNED", "QUESTIONNAIRE_ASSIGNED"},
    "READ_ONLY_AUDITOR": {"READ", "DOWNLOAD_ARTIFACT"},
    "PLATFORM_OPERATOR": {"SUPPORT_READ"},
    "SERVICE_WORKER": {"RUN_JOBS"},
}


@dataclass(frozen=True)
class RequestContext:
    """Authenticated request attributes supplied by the hosting service."""

    tenant_id: str
    actor_id: str
    roles: tuple[str, ...]
    originating_interface: str
    support_grant: Mapping[str, Any] | None = None


def _support_grant_active(
    context: RequestContext, case: Mapping[str, Any] | None
) -> bool:
    grant = context.support_grant
    if not grant or case is None:
        return False
    if str(grant.get("tenant_id")) != context.tenant_id:
        return False
    if str(grant.get("case_id")) != str(case.get("case_id")):
        return False
    if not str(grant.get("reason", "")).strip():
        return False
    try:
        expires_at = datetime.fromisoformat(str(grant["expires_at"]))
    except (KeyError, ValueError) as exc:
        raise PermissionError("Support grant has an invalid expiry") from exc
    if expires_at.tzinfo is None:
        raise PermissionError("Support grant expiry must include a timezone")
    return expires_at.astimezone(timezone.utc) > datetime.now(tz=timezone.utc)


def authorize(
    context: RequestContext,
    capability: str,
    case: Mapping[str, Any] | None = None,
) -> None:
    """Reject cross-tenant or role-incompatible access before domain work."""

    if (
        not context.tenant_id
        or not context.actor_id
        or not context.originating_interface
    ):
        raise PermissionError("Authenticated tenant, actor, and interface are required")
    if case is not None and str(case.get("tenant_id")) != context.tenant_id:
        raise PermissionError("Cross-tenant case access is forbidden")
    normalized_roles = {str(role).upper() for role in context.roles}
    unknown_roles = normalized_roles - ROLE_CAPABILITIES.keys()
    if unknown_roles:
        raise PermissionError(f"Unknown roles: {sorted(unknown_roles)}")
    granted = {
        item for role in normalized_roles for item in ROLE_CAPABILITIES.get(role, set())
    }
    requested = capability.upper()
    if requested in granted:
        return
    if requested == "READ" and "SUPPORT_READ" in granted:
        if _support_grant_active(context, case):
            return
        raise PermissionError("Platform support access requires an active case grant")
    raise PermissionError(f"Capability {requested} is not granted")
