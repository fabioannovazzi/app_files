"""Bind a professional decision to an authenticated account and exact local version.

Documents never enter this service. Fixed schemas, same-origin mutation checks,
case ownership and exact digest matching are security controls, not judgments.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

from modules.auth.dependencies import require_authenticated_user
from modules.auth.session import AuthenticatedUser
from modules.run_receipts.api import (
    RunReceiptRateLimitError,
    get_run_receipt_rate_limiter,
)
from modules.utilities.cache import get_cache_dir

__all__ = ["ReviewStore", "api_router", "site_router", "get_store"]

HASH = r"^[0-9a-f]{64}$"


class BoundedReviewRoute(APIRoute):
    """Bound untrusted input before parsing and reuse the hosted receipt quota."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def bounded(request: Request) -> Response:
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 4096:
                    raise HTTPException(413, "Review metadata exceeds the size limit")
            request._body = bytes(data)
            try:
                source = request.client.host if request.client else "unknown"
                action = (
                    "verify"
                    if request.method == "GET" or request.url.path.endswith("/verify")
                    else "stamp"
                )
                get_run_receipt_rate_limiter().check("cnc:" + source, action)
            except RunReceiptRateLimitError as exc:
                raise HTTPException(
                    429,
                    "Review rate limit exceeded",
                    headers={"Retry-After": str(exc.retry_after_seconds)},
                ) from exc
            response = await original(request)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return bounded


api_router = APIRouter(prefix="/api/vera/cnc-reviews", route_class=BoundedReviewRoute)
site_router = APIRouter()


def fingerprint(value: Any) -> str:
    """Match the local client's canonical JSON representation."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


class ReviewTarget(BaseModel):
    """Only opaque case and document versions cross the account boundary."""

    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    case_ref: str = Field(pattern=HASH)
    role: Literal["advisor", "esperto"]
    node_ref: str = Field(pattern=HASH)
    node_version: str = Field(pattern=HASH)
    decision: Literal["accepted", "changes_requested", "rejected"]


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    receipt_id: str = Field(min_length=36, max_length=36)
    receipt_sha256: str = Field(pattern=HASH)


class ReviewStore:
    """Transactionally enforce account ownership and retry identity on local storage."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS cnc_review_owners (case_ref TEXT PRIMARY KEY, actor TEXT NOT NULL, role TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS cnc_review_receipts (receipt_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, payload TEXT NOT NULL, payload_hash TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS cnc_review_current (case_ref TEXT NOT NULL, node_ref TEXT NOT NULL, node_version TEXT NOT NULL, receipt_id TEXT NOT NULL, PRIMARY KEY (case_ref, node_ref, node_version))"
        )
        connection.commit()
        return connection

    def record(self, target: ReviewTarget, actor: str) -> dict[str, Any]:
        """Only the authenticated case owner can record a decision; retries are stable."""
        UUID(target.request_id)
        request_hash = fingerprint({**target.model_dump(), "actor": actor})
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            owner = connection.execute(
                "SELECT actor, role FROM cnc_review_owners WHERE case_ref = ?",
                (target.case_ref,),
            ).fetchone()
            if owner and owner != (actor, target.role):
                raise PermissionError("This account does not own this case and role")
            previous = connection.execute(
                "SELECT request_hash, payload FROM cnc_review_receipts WHERE receipt_id = ?",
                (target.request_id,),
            ).fetchone()
            if previous:
                if previous[0] != request_hash:
                    raise ValueError(
                        "Request ID was already used for a different decision"
                    )
                return json.loads(previous[1])
            payload = {
                "schema_version": "vera.cnc_authenticated_review.v1",
                **target.model_dump(),
                "actor": actor,
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "authority": "mparanza_authenticated_account",
            }
            connection.execute(
                "INSERT OR IGNORE INTO cnc_review_owners VALUES (?, ?, ?)",
                (target.case_ref, actor, target.role),
            )
            connection.execute(
                "INSERT INTO cnc_review_receipts VALUES (?, ?, ?, ?)",
                (
                    target.request_id,
                    request_hash,
                    json.dumps(payload, ensure_ascii=False),
                    fingerprint(payload),
                ),
            )
            connection.execute(
                "INSERT INTO cnc_review_current VALUES (?, ?, ?, ?) ON CONFLICT (case_ref, node_ref, node_version) DO UPDATE SET receipt_id = excluded.receipt_id",
                (
                    target.case_ref,
                    target.node_ref,
                    target.node_version,
                    target.request_id,
                ),
            )
            connection.commit()
            return payload
        finally:
            connection.close()

    def verify(self, receipt_id: str, receipt_sha256: str) -> dict[str, Any]:
        """Possession of the opaque ID and entire-record hash allows exact verification."""
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT payload, payload_hash FROM cnc_review_receipts WHERE receipt_id = ?",
                (receipt_id,),
            ).fetchone()
            if not row or not secrets.compare_digest(row[1], receipt_sha256):
                raise FileNotFoundError("No matching review receipt")
            payload = json.loads(row[0])
            if not secrets.compare_digest(fingerprint(payload), receipt_sha256):
                raise ValueError("Stored review integrity mismatch")
            current = connection.execute(
                "SELECT receipt_id FROM cnc_review_current WHERE case_ref = ? AND node_ref = ? AND node_version = ?",
                (payload["case_ref"], payload["node_ref"], payload["node_version"]),
            ).fetchone()
            if current != (receipt_id,):
                raise ValueError("A later decision supersedes this review receipt")
            return payload
        finally:
            connection.close()


def get_store() -> ReviewStore:
    """Keep approval metadata in the existing server data area."""
    return ReviewStore(get_cache_dir("cnc_reviews") / "reviews.sqlite3")


def reviewer(request: Request) -> AuthenticatedUser:
    """Fail closed even if general site authentication is disabled."""
    user = require_authenticated_user(request)
    if user is None:
        raise HTTPException(401, "Authenticated account required")
    origin = request.headers.get("origin")
    if origin != "https://mparanza.com" and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Same-origin browser confirmation required")
    if request.headers.get("x-cnc-review") != "1":
        raise HTTPException(403, "Interactive review header required")
    return user


@api_router.get("/session")
def review_session(request: Request) -> dict[str, str]:
    """Show the actual account before the professional chooses a decision."""
    user = require_authenticated_user(request)
    if user is None:
        raise HTTPException(401, "Authenticated account required")
    return {"account": user.email}


@api_router.post("")
def record_review(
    target: ReviewTarget,
    user: AuthenticatedUser = Depends(reviewer),
    store: ReviewStore = Depends(get_store),
) -> dict[str, Any]:
    """Record the browser user's decision; client-supplied identities are forbidden."""
    try:
        return store.record(target, user.email.strip().lower())
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@api_router.post("/verify")
def verify_review(
    query: VerifyRequest, store: ReviewStore = Depends(get_store)
) -> dict[str, Any]:
    """Return only the retained receipt matching the exact opaque lookup pair."""
    try:
        return store.verify(query.receipt_id, query.receipt_sha256)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@site_router.get("/vera/cnc-review", response_class=HTMLResponse)
def review_page(request: Request) -> Any:
    """Review a locally selected draft in the browser without uploading its contents."""
    return Jinja2Templates(directory="templates").TemplateResponse(
        request=request, name="vera_cnc_review.html", context={}
    )
