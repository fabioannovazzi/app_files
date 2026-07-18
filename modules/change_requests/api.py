"""Public FastAPI routes for submitting and polling Mparanza change requests."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Coroutine
from functools import lru_cache
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

from modules.change_requests.store import (
    ChangeRequestCapacityError,
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
    "ChangeRequestRateLimiter",
    "ChangeRequestReceipt",
    "ChangeRequestInterviewReceipt",
    "ChangeRequestInterviewSubmission",
    "ChangeRequestSubmission",
    "ChangeRequestStatusBatchRequest",
    "ChangeRequestStatusBatchResponse",
    "get_change_request_store",
    "get_change_request_rate_limiter",
    "router",
]

MAX_REQUEST_BODY_BYTES = 1024 * 1024
MAX_STATUS_REQUESTS = 100
RATE_LIMIT_WINDOW_SECONDS = 60.0
INTAKE_PER_SOURCE_LIMIT = 20
INTAKE_GLOBAL_LIMIT = 120
STATUS_PER_SOURCE_LIMIT = 120
STATUS_GLOBAL_LIMIT = 600
MAX_RATE_LIMIT_SOURCES = 4_096


class ChangeRequestRateLimitError(RuntimeError):
    """Raised when one public source exceeds a mechanically auditable quota."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Change-request rate limit exceeded.")
        self.retry_after_seconds = retry_after_seconds


class ChangeRequestRateLimiter:
    """Bound public work with fixed rules required for security and auditability."""

    def __init__(
        self,
        *,
        window_seconds: float = RATE_LIMIT_WINDOW_SECONDS,
        intake_per_source: int = INTAKE_PER_SOURCE_LIMIT,
        intake_global: int = INTAKE_GLOBAL_LIMIT,
        status_per_source: int = STATUS_PER_SOURCE_LIMIT,
        status_global: int = STATUS_GLOBAL_LIMIT,
        max_sources: int = MAX_RATE_LIMIT_SOURCES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window_seconds = max(float(window_seconds), 1.0)
        self._limits = {
            "intake": (max(intake_per_source, 1), max(intake_global, 1)),
            "status": (max(status_per_source, 1), max(status_global, 1)),
        }
        self._max_sources = max(int(max_sources), 1)
        self._clock = clock
        self._source_events: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()
        self._global_events = {action: deque() for action in self._limits}
        self._lock = threading.Lock()

    def check(self, source: str, action: str) -> None:
        """Admit one request or raise with a bounded retry interval."""

        per_source_limit, global_limit = self._limits[action]
        now = self._clock()
        cutoff = now - self._window_seconds
        source_key = (source or "unknown", action)
        with self._lock:
            global_events = self._global_events[action]
            while global_events and global_events[0] <= cutoff:
                global_events.popleft()
            source_events = self._source_events.get(source_key)
            if source_events is None:
                if len(self._source_events) >= self._max_sources:
                    self._source_events.popitem(last=False)
                source_events = deque()
                self._source_events[source_key] = source_events
            else:
                self._source_events.move_to_end(source_key)
            while source_events and source_events[0] <= cutoff:
                source_events.popleft()
            if (
                len(source_events) >= per_source_limit
                or len(global_events) >= global_limit
            ):
                raise ChangeRequestRateLimitError(int(self._window_seconds))
            source_events.append(now)
            global_events.append(now)


@lru_cache(maxsize=1)
def get_change_request_rate_limiter() -> ChangeRequestRateLimiter:
    """Return the process-wide public intake limiter."""

    return ChangeRequestRateLimiter()


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
RateLimiter = Annotated[
    ChangeRequestRateLimiter, Depends(get_change_request_rate_limiter)
]


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
    if isinstance(exc, ChangeRequestCapacityError):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Change-request intake is temporarily at capacity.",
            headers={"Retry-After": "3600"},
        ) from exc
    if isinstance(exc, ChangeRequestStoreUnavailableError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Change-request service is temporarily unavailable.",
        ) from exc
    raise exc


def _enforce_rate_limit(
    request: Request, rate_limiter: ChangeRequestRateLimiter, action: str
) -> None:
    source = request.client.host if request.client is not None else "unknown"
    try:
        rate_limiter.check(source, action)
    except ChangeRequestRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many change-request operations. Try again shortly.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


@router.post(
    "",
    response_model=ChangeRequestReceipt,
    status_code=status.HTTP_201_CREATED,
)
def submit_change_request(
    payload: ChangeRequestSubmission,
    request: Request,
    store: Store,
    rate_limiter: RateLimiter,
) -> ChangeRequestReceipt:
    """Persist one user-approved Codex change request and return its receipt."""

    _enforce_rate_limit(request, rate_limiter, "intake")
    try:
        record = store.submit(payload.model_dump(mode="json"))
    except (
        ChangeRequestCapacityError,
        ChangeRequestConflictError,
        ChangeRequestStoreUnavailableError,
    ) as exc:
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
    rate_limiter: RateLimiter,
) -> ChangeRequestInterviewReceipt:
    """Create or recover one three-minute voice interview request."""

    _enforce_rate_limit(request, rate_limiter, "intake")
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
                ),
                public_url_base=url_base,
                change_request_id=record.change_request_id,
            )
            record = store.set_interview_url_if_absent(
                record.change_request_id, str(interview["public_url"])
            )
    except (
        ChangeRequestCapacityError,
        ChangeRequestConflictError,
        ChangeRequestStoreUnavailableError,
    ) as exc:
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
    request: Request,
    store: Store,
    rate_limiter: RateLimiter,
) -> ChangeRequestStatusBatchResponse:
    """Poll known receipts without requiring a user account."""

    _enforce_rate_limit(request, rate_limiter, "status")
    try:
        records = store.poll_many(
            [
                (lookup.change_request_id, lookup.status_token)
                for lookup in payload.requests
            ]
        )
    except ChangeRequestStoreUnavailableError as exc:
        _raise_http_store_error(exc)
        raise AssertionError("unreachable")
    return ChangeRequestStatusBatchResponse(
        requests=[
            _status_item(lookup.change_request_id, record)
            for lookup, record in zip(payload.requests, records, strict=True)
        ]
    )
