"""Authenticated HTTP routes for the Attribute Reporting server boundary."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, model_validator

from modules.auth.dependencies import require_site_permission
from modules.auth.session import AuthenticatedUser
from modules.pdp.attribute_reporting_bridge import (
    AttributeReportingBridge,
    BridgeConflictError,
    BridgeNotFoundError,
    BridgeValidationError,
    get_attribute_reporting_bridge,
)

__all__ = ["router"]

MAX_REQUEST_BODY_BYTES = 65 * 1024 * 1024
MAX_SMALL_REQUEST_BODY_BYTES = 64 * 1024
_require_attribute_reporting_permission = require_site_permission("attribute_reporting")


class _BoundedAttributeReportingRoute(APIRoute):
    """Reject oversized bridge requests before FastAPI parses their JSON body."""

    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_handler = super().get_route_handler()

        async def bounded_handler(request: Request) -> Response:
            # Authenticate and authorize before consuming a potentially large body.
            # FastAPI will resolve the same dependency again for the typed endpoint
            # parameter; this early check protects the pre-parse buffering boundary.
            _require_attribute_reporting_permission(request)
            if request.method in {"POST", "PUT", "PATCH"}:
                is_mapping_submission = request.url.path.endswith("/submissions")
                body_limit = (
                    MAX_REQUEST_BODY_BYTES
                    if is_mapping_submission
                    else min(MAX_SMALL_REQUEST_BODY_BYTES, MAX_REQUEST_BODY_BYTES)
                )
                raw_length = request.headers.get("content-length")
                if raw_length:
                    try:
                        declared_length = int(raw_length)
                    except ValueError as exc:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid Content-Length header.",
                        ) from exc
                    if declared_length < 0:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid Content-Length header.",
                        )
                    if declared_length > body_limit:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="Attribute Reporting request body is too large.",
                        )
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > body_limit:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="Attribute Reporting request body is too large.",
                        )
                setattr(request, "_body", bytes(body))
            response = await original_handler(request)
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Pragma"] = "no-cache"
            vary = [
                item.strip()
                for item in response.headers.get("Vary", "").split(",")
                if item.strip()
            ]
            if not any(item.casefold() == "cookie" for item in vary):
                vary.append("Cookie")
            response.headers["Vary"] = ", ".join(vary)
            return response

        return bounded_handler


router = APIRouter(
    prefix="/case-notes/api/attribute-reporting",
    tags=["attribute-reporting"],
    route_class=_BoundedAttributeReportingRoute,
)
AttributeReportingUser = Annotated[
    AuthenticatedUser | None,
    Depends(_require_attribute_reporting_permission),
]
Bridge = Annotated[
    AttributeReportingBridge,
    Depends(get_attribute_reporting_bridge),
]


class EvidencePackRequest(BaseModel):
    """Current-database evidence package requested by an installed plugin."""

    retailer: str = Field(min_length=1, max_length=128)
    category_key: str = Field(min_length=1, max_length=128)
    taxonomy_version: str = Field(min_length=1, max_length=128)
    taxonomy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mapping_submission_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )


class MappingWorksetRequest(BaseModel):
    """Pinned mapping workset derived from one ready evidence package."""

    evidence_job_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    taxonomy_version: str = Field(min_length=1, max_length=128)
    taxonomy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mapping_mode: Literal["unresolved", "correction"] = "unresolved"
    correction_reason: str | None = Field(default=None, max_length=1_000)

    @model_validator(mode="after")
    def validate_correction_contract(self) -> MappingWorksetRequest:
        """Require an explicit reason only for an overwrite-capable workset."""

        reason = str(self.correction_reason or "").strip()
        if self.mapping_mode == "correction" and not reason:
            raise ValueError("A correction workset requires a reason.")
        if self.mapping_mode == "unresolved" and reason:
            raise ValueError(
                "A correction reason is valid only for a correction workset."
            )
        self.correction_reason = reason or None
        return self


class MappingSubmissionRequest(BaseModel):
    """Complete Codex decisions submitted against one immutable workset."""

    workset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    mapping_tasks: dict[str, Any]
    decisions: dict[str, Any]
    validated_mappings: dict[str, Any]
    mapping_review: dict[str, Any]


def _actor_email(user: AuthenticatedUser | None) -> str:
    # Authentication can be disabled only in local development and tests.
    return user.email if user is not None else "local-dev"


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, BridgeNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, BridgeConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, BridgeValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    if isinstance(exc, (KeyError, TypeError, ValueError)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Attribute Reporting request failed validation.",
        )
    raise exc


@router.get("/taxonomies/{category_key}")
def get_taxonomy_snapshot(
    category_key: str,
    user: AttributeReportingUser,
    bridge: Bridge,
) -> dict[str, Any]:
    """Return one published central taxonomy category and checksum."""

    try:
        return bridge.taxonomy_snapshot(
            category_key,
            actor_email=_actor_email(user),
        )
    except (
        BridgeNotFoundError,
        BridgeConflictError,
        BridgeValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        _raise_http_error(exc)
        raise AssertionError("unreachable")


@router.post("/evidence-packs", status_code=status.HTTP_202_ACCEPTED)
def create_evidence_pack(
    payload: EvidencePackRequest,
    background_tasks: BackgroundTasks,
    user: AttributeReportingUser,
    bridge: Bridge,
) -> dict[str, Any]:
    """Start an immutable package build from the current central database."""

    try:
        job = bridge.create_evidence_job(
            retailer=payload.retailer,
            category_key=payload.category_key,
            taxonomy_version=payload.taxonomy_version,
            taxonomy_sha256=payload.taxonomy_sha256,
            actor_email=_actor_email(user),
            mapping_submission_id=payload.mapping_submission_id,
        )
    except (
        BridgeNotFoundError,
        BridgeConflictError,
        BridgeValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        _raise_http_error(exc)
        raise AssertionError("unreachable")
    background_tasks.add_task(bridge.build_evidence_job, str(job["job_id"]))
    return job


@router.get("/evidence-packs/{job_id}")
def poll_evidence_pack(
    job_id: str,
    background_tasks: BackgroundTasks,
    user: AttributeReportingUser,
    bridge: Bridge,
) -> dict[str, Any]:
    """Poll an actor-owned build and resume work abandoned by a prior worker."""

    try:
        result = bridge.evidence_status(job_id, actor_email=_actor_email(user))
        if result.get("status") in {"pending", "running"}:
            background_tasks.add_task(bridge.build_evidence_job, job_id)
        return result
    except (
        BridgeNotFoundError,
        BridgeConflictError,
        BridgeValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        _raise_http_error(exc)
        raise AssertionError("unreachable")


@router.get("/evidence-packs/{job_id}/download")
def download_evidence_pack(
    job_id: str,
    user: AttributeReportingUser,
    bridge: Bridge,
) -> FileResponse:
    """Download one checksum-verified evidence ZIP."""

    try:
        package_path, receipt = bridge.evidence_download(
            job_id,
            actor_email=_actor_email(user),
        )
    except (
        BridgeNotFoundError,
        BridgeConflictError,
        BridgeValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        _raise_http_error(exc)
        raise AssertionError("unreachable")
    return FileResponse(
        package_path,
        media_type="application/zip",
        filename=f"attribute-reporting-{job_id}.zip",
        headers={
            "X-Content-SHA256": str(receipt["package_sha256"]),
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/mapping-worksets", status_code=status.HTTP_201_CREATED)
def create_mapping_workset(
    payload: MappingWorksetRequest,
    user: AttributeReportingUser,
    bridge: Bridge,
) -> dict[str, Any]:
    """Create a complete unresolved workset from one ready package."""

    try:
        return bridge.create_mapping_workset(
            evidence_job_id=payload.evidence_job_id,
            taxonomy_version=payload.taxonomy_version,
            taxonomy_sha256=payload.taxonomy_sha256,
            actor_email=_actor_email(user),
            mapping_mode=payload.mapping_mode,
            correction_reason=payload.correction_reason,
        )
    except (
        BridgeNotFoundError,
        BridgeConflictError,
        BridgeValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        _raise_http_error(exc)
        raise AssertionError("unreachable")


@router.get("/mapping-worksets/{workset_id}")
def get_mapping_workset(
    workset_id: str,
    user: AttributeReportingUser,
    bridge: Bridge,
) -> dict[str, Any]:
    """Retrieve an immutable actor-owned mapping workset."""

    try:
        return bridge.get_mapping_workset(
            workset_id,
            actor_email=_actor_email(user),
        )
    except (
        BridgeNotFoundError,
        BridgeConflictError,
        BridgeValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        _raise_http_error(exc)
        raise AssertionError("unreachable")


@router.post("/mapping-worksets/{workset_id}/submissions")
def submit_mapping_results(
    workset_id: str,
    payload: MappingSubmissionRequest,
    user: AttributeReportingUser,
    bridge: Bridge,
) -> dict[str, Any]:
    """Accept one validated, hash-pinned and idempotent mapping submission."""

    try:
        return bridge.submit_mapping_results(
            workset_id=workset_id,
            workset_sha256=payload.workset_sha256,
            idempotency_key=payload.idempotency_key,
            mapping_tasks=payload.mapping_tasks,
            decisions=payload.decisions,
            validated_mappings=payload.validated_mappings,
            mapping_review=payload.mapping_review,
            actor_email=_actor_email(user),
        )
    except (
        BridgeNotFoundError,
        BridgeConflictError,
        BridgeValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        _raise_http_error(exc)
        raise AssertionError("unreachable")
