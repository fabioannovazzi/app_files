#!/usr/bin/env python3
"""Optional authenticated FastAPI adapter for the Bilancio case service."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Mapping

from access_control import RequestContext
from artifact_delivery import ExpiredDownloadGrant
from case_service import CaseService
from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

__all__ = ["create_app"]


def create_app(
    service: CaseService,
    rule_pack: Mapping[str, Any],
    context_provider: Callable[[Request], RequestContext] | None = None,
    disclosure_rule_pack: Mapping[str, Any] | None = None,
) -> FastAPI:
    """Create the optional HTTP adapter around one configured service instance."""

    app = FastAPI(title="Vera Bilancio intelligente API", version="1.0")

    def context(request: Request) -> RequestContext:
        resolved = (
            context_provider(request)
            if context_provider is not None
            else getattr(request.state, "vera_request_context", None)
        )
        if not isinstance(resolved, RequestContext):
            raise HTTPException(
                status_code=401,
                detail="Authenticated Vera request context is required",
            )
        return resolved

    def revision(value: str) -> str:
        normalized = value.strip()
        if normalized.startswith("W/"):
            normalized = normalized[2:].strip()
        normalized = normalized.strip('"')
        if not normalized:
            raise ValueError("If-Match must contain the current revision_id")
        return normalized

    def mutate(
        request: Request,
        case_id: str,
        operation: str,
        payload: Mapping[str, Any],
        if_match: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return service.mutate(
            context(request),
            case_id,
            operation,
            payload,
            revision(if_match),
            idempotency_key,
        )

    @app.exception_handler(PermissionError)
    async def permission_error(_request: Request, exc: PermissionError):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(FileNotFoundError)
    async def missing_resource(_request: Request, exc: FileNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def invalid_request(_request: Request, exc: ValueError):
        status = 409 if "Stale revision" in str(exc) else 422
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    @app.exception_handler(ExpiredDownloadGrant)
    async def expired_download_grant(_request: Request, exc: ExpiredDownloadGrant):
        return JSONResponse(status_code=410, content={"detail": str(exc)})

    @app.post("/v1/xbrl-cases", status_code=201)
    def create_case_resource(
        request: Request,
        payload: dict[str, Any] = Body(...),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        if "rule_pack" in payload:
            raise ValueError(
                "Statutory rule packs are deployment configuration, not request data"
            )
        case_payload = payload.get("payload", payload)
        return service.create(
            context(request), case_payload, rule_pack, idempotency_key
        )

    @app.get("/v1/xbrl-cases/{case_id}")
    def get_case_resource(request: Request, case_id: str) -> Any:
        return service.get(context(request), case_id)

    @app.post("/v1/xbrl-cases/{case_id}/archive")
    def archive_case_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "archive",
            {"reason": payload["reason"]},
            if_match,
            idempotency_key,
        )

    @app.delete("/v1/xbrl-cases/{case_id}")
    def delete_case_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return service.delete_archived_case(
            context(request),
            case_id,
            revision(if_match),
            idempotency_key,
            reason=str(payload["reason"]),
        )

    def ingest_resource(
        request: Request,
        case_id: str,
        payload: Mapping[str, Any],
        if_match: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        kind = str(payload.get("document_kind", "TRIAL_BALANCE")).upper()
        if kind == "PRIOR_XBRL":
            operation = "ingest_prior_xbrl"
        elif kind == "TRIAL_BALANCE":
            operation = "ingest"
        else:
            operation = "attach_supporting_document"
        operation_payload = {
            "source_path": payload["source_path"],
            "sheet": payload.get("sheet"),
        }
        if operation == "attach_supporting_document":
            operation_payload.update(
                {
                    "purpose": kind,
                    "description": payload["description"],
                }
            )
        return mutate(
            request,
            case_id,
            operation,
            operation_payload,
            if_match,
            idempotency_key,
        )

    @app.post("/v1/xbrl-cases/{case_id}/documents")
    def create_document_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return ingest_resource(request, case_id, payload, if_match, idempotency_key)

    @app.post("/v1/xbrl-cases/{case_id}/ingest")
    def ingest_case_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return ingest_resource(request, case_id, payload, if_match, idempotency_key)

    @app.post("/v1/xbrl-cases/{case_id}/confirm-parser")
    def confirm_parser_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "confirm_parser",
            {"convention": payload["convention"]},
            if_match,
            idempotency_key,
        )

    @app.post("/v1/xbrl-cases/{case_id}/determine-forms")
    def determine_forms_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "determine_forms",
            {"metrics": payload["metrics"], "rule_pack": rule_pack},
            if_match,
            idempotency_key,
        )

    @app.post("/v1/xbrl-cases/{case_id}/regulatory-migrations")
    def migrate_regulatory_versions_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "migrate_regulatory_versions",
            payload,
            if_match,
            idempotency_key,
        )

    @app.post("/v1/xbrl-cases/{case_id}/select-form")
    def select_form_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "select_form",
            {"form": payload["form"]},
            if_match,
            idempotency_key,
        )

    @app.get("/v1/xbrl-cases/{case_id}/mappings")
    def get_mappings_resource(request: Request, case_id: str) -> Any:
        return service.get(context(request), case_id, "mappings")

    @app.get("/v1/xbrl-cases/{case_id}/taxonomy-mapping-index")
    def get_taxonomy_mapping_index_resource(request: Request, case_id: str) -> Any:
        return service.get(context(request), case_id, "taxonomy_mapping_index")

    @app.post("/v1/xbrl-cases/{case_id}/taxonomy-mapping-index")
    def build_taxonomy_mapping_index_resource(
        request: Request,
        case_id: str,
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "taxonomy_mapping_index",
            {},
            if_match,
            idempotency_key,
        )

    @app.patch("/v1/xbrl-cases/{case_id}/mappings")
    def patch_mappings_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "apply_mappings",
            {"decisions": payload["decisions"]},
            if_match,
            idempotency_key,
        )

    @app.get("/v1/xbrl-cases/{case_id}/comparative-reconciliation")
    def get_comparative_reconciliation_resource(request: Request, case_id: str) -> Any:
        return service.get(context(request), case_id, "comparative_reconciliation")

    @app.post("/v1/xbrl-cases/{case_id}/comparative-reconciliation")
    def record_comparative_reconciliation_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "record_comparative_reconciliation",
            {"decisions": payload["decisions"]},
            if_match,
            idempotency_key,
        )

    @app.post("/v1/xbrl-cases/{case_id}/compute-statements")
    def compute_statements_resource(
        request: Request,
        case_id: str,
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "compute_statements",
            {},
            if_match,
            idempotency_key,
        )

    @app.post("/v1/xbrl-cases/{case_id}/statutory-presentation")
    def review_statutory_presentation_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "record_statutory_presentation",
            {"decisions": payload.get("decisions", [])},
            if_match,
            idempotency_key,
        )

    @app.get("/v1/xbrl-cases/{case_id}/schedules")
    def get_schedules_resource(request: Request, case_id: str) -> Any:
        return service.get(context(request), case_id, "schedules")

    @app.post("/v1/xbrl-cases/{case_id}/schedules")
    def record_schedule_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "record_schedule",
            {"schedule": payload.get("schedule", payload)},
            if_match,
            idempotency_key,
        )

    @app.post("/v1/xbrl-cases/{case_id}/schedule-taxonomy-adapter")
    def record_schedule_taxonomy_adapter_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "record_schedule_taxonomy_adapter",
            {"decisions": payload.get("decisions", [])},
            if_match,
            idempotency_key,
        )

    @app.post("/v1/xbrl-cases/{case_id}/activate-disclosures")
    def activate_disclosures_resource(
        request: Request,
        case_id: str,
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        if disclosure_rule_pack is None:
            raise ValueError(
                "The HTTP adapter requires a configured disclosure rule pack"
            )
        return mutate(
            request,
            case_id,
            "activate_disclosures",
            {"rule_pack": disclosure_rule_pack},
            if_match,
            idempotency_key,
        )

    @app.get("/v1/xbrl-cases/{case_id}/disclosure-triggers")
    def get_disclosure_triggers_resource(request: Request, case_id: str) -> Any:
        return service.get(context(request), case_id, "disclosure_triggers")

    @app.post("/v1/xbrl-cases/{case_id}/disclosure-triggers")
    def record_disclosure_triggers_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "record_disclosure_triggers",
            {"decisions": payload["decisions"]},
            if_match,
            idempotency_key,
        )

    @app.get("/v1/xbrl-cases/{case_id}/questions")
    def get_questions_resource(request: Request, case_id: str) -> Any:
        return service.get(context(request), case_id, "questions")

    @app.post("/v1/xbrl-cases/{case_id}/answers")
    def answer_questions_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "record_answers",
            {"answers": payload["answers"]},
            if_match,
            idempotency_key,
        )

    @app.post("/v1/xbrl-cases/{case_id}/generate-notes")
    def generate_notes_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "record_narratives",
            {"blocks": payload["blocks"]},
            if_match,
            idempotency_key,
        )

    def no_payload_mutation(
        request: Request,
        case_id: str,
        operation: str,
        if_match: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return mutate(request, case_id, operation, {}, if_match, idempotency_key)

    @app.post("/v1/xbrl-cases/{case_id}/validate")
    def validate_case_resource(
        request: Request,
        case_id: str,
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return no_payload_mutation(
            request, case_id, "validate", if_match, idempotency_key
        )

    @app.post("/v1/xbrl-cases/{case_id}/prepare-xbrl-review")
    def prepare_xbrl_review_resource(
        request: Request,
        case_id: str,
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return no_payload_mutation(
            request,
            case_id,
            "prepare_xbrl_review",
            if_match,
            idempotency_key,
        )

    @app.post("/v1/xbrl-cases/{case_id}/approve")
    def approve_case_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return mutate(
            request,
            case_id,
            "approve",
            {"declaration": payload["declaration"]},
            if_match,
            idempotency_key,
        )

    @app.post("/v1/xbrl-cases/{case_id}/export")
    def export_case_resource(
        request: Request,
        case_id: str,
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return no_payload_mutation(
            request, case_id, "export", if_match, idempotency_key
        )

    @app.get("/v1/xbrl-cases/{case_id}/artifacts")
    def get_artifacts_resource(request: Request, case_id: str) -> Any:
        return service.get(context(request), case_id, "artifacts")

    @app.post(
        "/v1/xbrl-cases/{case_id}/artifacts/{artifact_id}/download-grants",
        status_code=201,
    )
    def create_artifact_download_grant(
        request: Request,
        case_id: str,
        artifact_id: str,
        payload: dict[str, Any] = Body(default={}),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return service.issue_artifact_download(
            context(request),
            case_id,
            artifact_id,
            idempotency_key,
            ttl_seconds=int(payload.get("ttl_seconds", 300)),
        )

    @app.get("/v1/xbrl-artifacts/download")
    def download_artifact(token: str) -> Response:
        artifact = service.redeem_artifact_download(token)
        return Response(
            content=artifact["content"],
            media_type=artifact["media_type"],
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{artifact["file_name"]}"'
                ),
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Digest": f"sha-256={artifact['sha256']}",
            },
        )

    @app.get("/v1/xbrl-cases/{case_id}/audit-events")
    def get_audit_events_resource(request: Request, case_id: str) -> Any:
        return service.get(context(request), case_id, "audit_events")

    @app.get("/v1/xbrl-cases/{case_id}/review-views/{view}")
    def get_review_view_resource(
        request: Request,
        case_id: str,
        view: str,
        offset: int = 0,
        limit: int = 200,
    ) -> Any:
        return service.review_view(
            context(request), case_id, view, offset=offset, limit=limit
        )

    @app.post("/v1/xbrl-cases/{case_id}/jobs", status_code=202)
    def enqueue_job_resource(
        request: Request,
        case_id: str,
        payload: dict[str, Any] = Body(...),
        if_match: str = Header(..., alias="If-Match"),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> Any:
        return service.enqueue_job(
            context(request),
            case_id,
            idempotency_key,
            str(payload["operation"]),
            payload.get("payload", {}),
            revision(if_match),
            max_attempts=int(payload.get("max_attempts", 3)),
        )

    @app.get("/v1/xbrl-cases/{case_id}/jobs/{job_id}")
    def get_job_resource(request: Request, case_id: str, job_id: str) -> Any:
        return service.get_job(context(request), case_id, job_id)

    return app
