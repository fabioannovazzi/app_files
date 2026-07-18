"""Public FastAPI routes for submitting and polling Mparanza change requests."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

from modules.change_requests.store import (
    ChangeRequestConflictError,
    ChangeRequestRecord,
    ChangeRequestStore,
    ChangeRequestStoreUnavailableError,
    get_change_request_store,
)
from modules.hosted_interviews.api import (
    PUBLIC_URL_TOKEN_PLACEHOLDER,
    PreparedInterviewRequest,
    create_prepared_interview,
)

__all__ = [
    "MAX_REQUEST_BODY_BYTES",
    "ChangeRequestReceipt",
    "ChangeRequestInterviewReceipt",
    "ChangeRequestInterviewSubmission",
    "ChangeRequestSubmission",
    "ChangeRequestStatusBatchRequest",
    "ChangeRequestStatusBatchResponse",
    "get_change_request_store",
    "router",
]

MAX_REQUEST_BODY_BYTES = 1024 * 1024
MAX_STATUS_REQUESTS = 100


class _BoundedChangeRequestRoute(APIRoute):
    """Reject an oversized public request before FastAPI parses its JSON."""

    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_handler = super().get_route_handler()

        async def bounded_handler(request: Request) -> Response:
            if request.method in {"POST", "PUT", "PATCH"}:
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
                    if declared_length > MAX_REQUEST_BODY_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="Change-request body is too large.",
                        )
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > MAX_REQUEST_BODY_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="Change-request body is too large.",
                        )
                setattr(request, "_body", bytes(body))
            response = await original_handler(request)
            response.headers["Cache-Control"] = "no-store"
            return response

        return bounded_handler


router = APIRouter(
    prefix="/api/change-requests",
    tags=["change-requests"],
    route_class=_BoundedChangeRequestRoute,
)
Store = Annotated[ChangeRequestStore, Depends(get_change_request_store)]


class ChangeRequestSubmission(BaseModel):
    """Codex-produced problem reproduction or capability proposal."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    submission_id: UUID
    kind: Literal["problem", "capability"]
    plugin: Literal["clara", "vera"]
    plugin_version: str = Field(min_length=1, max_length=128)
    request: dict[str, Any] = Field(min_length=1)


class ChangeRequestReceipt(BaseModel):
    """Stable receipt returned after a durable submission."""

    schema_version: Literal[1] = 1
    change_request_id: str
    status_token: str
    status: Literal["open", "fixed"]
    fixed: bool
    fixed_version: str | None = None
    install_url: str | None = None


class ChangeRequestInterviewSubmission(BaseModel):
    """One concrete capability opportunity to explore by voice."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    submission_id: UUID
    plugin: Literal["clara", "vera"]
    plugin_version: str = Field(min_length=1, max_length=128)
    opportunity: str = Field(min_length=1, max_length=4_000)
    language: Literal["it", "en", "fr", "de"] = "it"


class ChangeRequestInterviewReceipt(ChangeRequestReceipt):
    """Stable request receipt plus its three-minute interview link."""

    interview_url: str


class ChangeRequestStatusLookup(BaseModel):
    """One capability-token lookup in a batch status request."""

    model_config = ConfigDict(extra="forbid")

    change_request_id: str = Field(pattern=r"^CR-[1-9][0-9]*$")
    status_token: str = Field(min_length=20, max_length=200)


class ChangeRequestStatusBatchRequest(BaseModel):
    """Bounded collection of locally stored change-request receipts."""

    model_config = ConfigDict(extra="forbid")

    requests: list[ChangeRequestStatusLookup] = Field(
        min_length=1,
        max_length=MAX_STATUS_REQUESTS,
    )


class ChangeRequestStatusItem(BaseModel):
    """Minimal public release status for one receipt."""

    change_request_id: str
    found: bool
    status: Literal["open", "fixed"] | None = None
    fixed: bool = False
    fixed_version: str | None = None
    install_url: str | None = None


class ChangeRequestStatusBatchResponse(BaseModel):
    """Status results returned in the same order as the request."""

    schema_version: Literal[1] = 1
    requests: list[ChangeRequestStatusItem]


def _receipt(record: ChangeRequestRecord) -> ChangeRequestReceipt:
    return ChangeRequestReceipt(
        change_request_id=record.change_request_id,
        status_token=record.status_token,
        status=record.status,
        fixed=record.fixed,
        fixed_version=record.fixed_version,
        install_url=record.install_url,
    )


def _status_item(
    change_request_id: str, record: ChangeRequestRecord | None
) -> ChangeRequestStatusItem:
    if record is None:
        return ChangeRequestStatusItem(
            change_request_id=change_request_id,
            found=False,
        )
    return ChangeRequestStatusItem(
        change_request_id=record.change_request_id,
        found=True,
        status=record.status,
        fixed=record.fixed,
        fixed_version=record.fixed_version,
        install_url=record.install_url,
    )


def _raise_http_store_error(exc: Exception) -> None:
    if isinstance(exc, ChangeRequestConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if isinstance(exc, ChangeRequestStoreUnavailableError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Change-request service is temporarily unavailable.",
        ) from exc
    raise exc


@router.post(
    "",
    response_model=ChangeRequestReceipt,
    status_code=status.HTTP_201_CREATED,
)
def submit_change_request(
    payload: ChangeRequestSubmission,
    store: Store,
) -> ChangeRequestReceipt:
    """Persist one user-approved Codex change request and return its receipt."""

    try:
        record = store.submit(payload.model_dump(mode="json"))
    except (ChangeRequestConflictError, ChangeRequestStoreUnavailableError) as exc:
        _raise_http_store_error(exc)
        raise AssertionError("unreachable")
    return _receipt(record)


@router.post(
    "/interviews",
    response_model=ChangeRequestInterviewReceipt,
    status_code=status.HTTP_201_CREATED,
)
def start_change_request_interview(
    payload: ChangeRequestInterviewSubmission,
    request: Request,
    store: Store,
) -> ChangeRequestInterviewReceipt:
    """Create or recover one three-minute voice interview request."""

    envelope = ChangeRequestSubmission(
        submission_id=payload.submission_id,
        kind="capability",
        plugin=payload.plugin,
        plugin_version=payload.plugin_version,
        request={
            "opportunity": payload.opportunity,
            "language": payload.language,
            "source": "voice_interview",
        },
    )
    try:
        record = store.submit(envelope.model_dump(mode="json"))
        if record.interview_url is None:
            url_base = str(
                request.url_for(
                    "hosted_interview_page", token=PUBLIC_URL_TOKEN_PLACEHOLDER
                )
            ).removesuffix(f"/{PUBLIC_URL_TOKEN_PLACEHOLDER}")
            participant_intro = {
                "it": "In tre minuti, racconta il miglioramento concreto che vorresti.",
                "en": "In three minutes, explain the concrete improvement you want.",
                "fr": "En trois minutes, expliquez l'amélioration concrète souhaitée.",
                "de": "Erklären Sie in drei Minuten die gewünschte konkrete Verbesserung.",
            }[payload.language]
            _token, interview = create_prepared_interview(
                PreparedInterviewRequest(
                    interview_campaign_id="plugin-improvement-v1",
                    case_id=record.change_request_id,
                    case_name=f"{payload.plugin.title()} improvement",
                    interview_title="Three-minute improvement interview",
                    interviewee_role="Plugin user",
                    language=payload.language,
                    purpose=(
                        "Understand one concrete plugin capability request well enough "
                        "for the developer to act on it."
                    ),
                    participant_intro=participant_intro,
                    background_context=payload.opportunity,
                    priority_topics=[
                        "What the user wants the plugin to do",
                        "What happens today",
                        "What a useful result would look like",
                    ],
                    boundaries=[
                        "Do not ask for client or customer names or identifying details.",
                        "Do not ask for source documents, files, credentials, or secrets.",
                    ],
                    interviewer_name="Mparanza",
                    max_duration_seconds=180,
                    change_request_id=record.change_request_id,
                ),
                public_url_base=url_base,
            )
            record = store.set_interview_url_if_absent(
                record.change_request_id, str(interview["public_url"])
            )
    except (ChangeRequestConflictError, ChangeRequestStoreUnavailableError) as exc:
        _raise_http_store_error(exc)
        raise AssertionError("unreachable")
    if record.interview_url is None:  # pragma: no cover - defensive store guard
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview link could not be created.",
        )
    receipt = _receipt(record)
    return ChangeRequestInterviewReceipt(
        **receipt.model_dump(),
        interview_url=record.interview_url,
    )


@router.post("/status", response_model=ChangeRequestStatusBatchResponse)
def poll_change_request_statuses(
    payload: ChangeRequestStatusBatchRequest,
    store: Store,
) -> ChangeRequestStatusBatchResponse:
    """Poll known receipts without requiring a user account."""

    results: list[ChangeRequestStatusItem] = []
    try:
        for lookup in payload.requests:
            record = store.poll(lookup.change_request_id, lookup.status_token)
            results.append(_status_item(lookup.change_request_id, record))
    except ChangeRequestStoreUnavailableError as exc:
        _raise_http_store_error(exc)
        raise AssertionError("unreachable")
    return ChangeRequestStatusBatchResponse(requests=results)
