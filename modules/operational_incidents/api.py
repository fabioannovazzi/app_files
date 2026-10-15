"""Public incident API and remote MCP transport independent of local execution."""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections import OrderedDict, deque
from functools import lru_cache
from typing import Any
from urllib.parse import parse_qs, urlencode
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, ValidationError

from modules.operational_incidents.contracts import (
    Credentials,
    DeviceCredentials,
    Outcome,
    RecoveryEvent,
    Report,
    ReporterStatus,
)
from modules.operational_incidents.oauth import (
    ISSUER,
    RESOURCE,
    SCOPE,
    IncidentOAuth,
    OAuthError,
)
from modules.operational_incidents.store import (
    ConnectionActor,
    IncidentConflict,
    IncidentNotFound,
    IncidentStore,
)

__all__ = ["router", "get_incident_store"]
router = APIRouter(tags=["operational-incidents"])
MAX_BODY_BYTES = 2 * 1024 * 1024


@lru_cache(maxsize=1)
def get_incident_store() -> IncidentStore:
    return IncidentStore()


class ConnectionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credentials: Credentials | None = None
    report: Report | None = None
    outcome: Outcome | None = None
    progress: RecoveryEvent | None = None
    client_status: ReporterStatus | None = None


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credentials: Credentials
    report: Report | None = None
    outcome: Outcome | None = None
    progress: RecoveryEvent | None = None
    device: DeviceCredentials | None = None
    native_status: ReporterStatus | None = None
    client_status: ReporterStatus | None = None


_RATE_LOCK = threading.Lock()
_RATE_EVENTS: OrderedDict[str, deque[float]] = OrderedDict()
_GLOBAL_EVENTS: deque[float] = deque()


def _admit(source: str) -> None:
    """Bound public transport work without depending on unrelated interview APIs."""
    now = time.monotonic()
    with _RATE_LOCK:
        while _GLOBAL_EVENTS and _GLOBAL_EVENTS[0] <= now - 60:
            _GLOBAL_EVENTS.popleft()
        events = _RATE_EVENTS.setdefault(source, deque())
        _RATE_EVENTS.move_to_end(source)
        while events and events[0] <= now - 60:
            events.popleft()
        if len(events) >= 120 or len(_GLOBAL_EVENTS) >= 600:
            raise HTTPException(
                429, "Incident delivery rate exceeded", headers={"Retry-After": "60"}
            )
        events.append(now)
        _GLOBAL_EVENTS.append(now)
        if len(_RATE_EVENTS) > 4096:
            _RATE_EVENTS.popitem(last=False)


async def _body(request: Request, limit: int = MAX_BODY_BYTES) -> dict[str, Any]:
    """Reject excess data, never silently truncate diagnostic evidence."""
    _admit(request.client.host if request.client else "unknown")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > limit:
            raise HTTPException(
                413,
                "Diagnostic envelope exceeds 2 MiB; split technical events into separate reports",
            )
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise HTTPException(400, "Invalid incident JSON") from error
    if not isinstance(value, dict):
        raise HTTPException(400, "Expected an incident object")
    return value


def _dispatch(
    store: IncidentStore, operation: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if operation == "register" and not arguments:
        generated = Credentials(
            installation_id=uuid4(), installation_key=secrets.token_urlsafe(32)
        )
        return {
            **store.register(generated),
            "credentials": generated.model_dump(mode="json"),
            "next_report_id": str(uuid4()),
        }
    envelope = Envelope.model_validate(arguments)
    if operation == "register":
        registered = store.register(
            envelope.credentials, envelope.device, envelope.native_status
        )
        if envelope.client_status is not None:
            store.observe_reporter(envelope.credentials, envelope.client_status)
        return {
            **registered,
            "next_report_id": str(uuid4()),
        }
    if envelope.client_status is not None:
        store.observe_reporter(envelope.credentials, envelope.client_status)
    if operation == "report" and envelope.report is not None:
        return {
            **store.report(envelope.credentials, envelope.report),
            "next_report_id": str(uuid4()),
        }
    if operation == "status":
        return store.status(envelope.credentials)
    if operation == "outcome" and envelope.outcome is not None:
        return store.outcome(envelope.credentials, envelope.outcome)
    if operation == "progress" and envelope.progress is not None:
        return store.progress(envelope.credentials, envelope.progress)
    raise IncidentConflict("Required incident operation data is missing")


@router.post("/api/operational-incidents/{operation}")
async def incident_operation(
    operation: str, request: Request, store: IncidentStore = Depends(get_incident_store)
) -> dict[str, Any]:
    payload = await _body(request)
    try:
        return _dispatch(store, operation, payload)
    except IncidentNotFound as error:
        raise HTTPException(404, str(error)) from error
    except IncidentConflict as error:
        raise HTTPException(409, str(error)) from error
    except ValidationError as error:
        # Validation errors can contain original inputs. Do not echo them.
        raise HTTPException(422, "Invalid technical incident schema") from error


_NO_CACHE = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
}


def _oauth_error(error: OAuthError) -> JSONResponse:
    return JSONResponse({"error": error.code}, status_code=400, headers=_NO_CACHE)


@router.get("/.well-known/oauth-protected-resource/mcp/vera-incidents")
async def incident_resource_metadata() -> dict[str, Any]:
    return {
        "resource": RESOURCE,
        "authorization_servers": [ISSUER],
        "scopes_supported": [SCOPE],
        "bearer_methods_supported": ["header"],
    }


@router.get("/.well-known/oauth-authorization-server")
async def incident_authorization_metadata() -> dict[str, Any]:
    return IncidentOAuth(get_incident_store()).metadata()


@router.post("/oauth/vera-incidents/register")
async def register_oauth_client(
    request: Request, store: IncidentStore = Depends(get_incident_store)
) -> Response:
    try:
        data = IncidentOAuth(store).register(await _body(request, 8192))
        return JSONResponse(data, status_code=201, headers=_NO_CACHE)
    except OAuthError as error:
        return _oauth_error(error)


def _single_fields(pairs: list[tuple[str, str]]) -> dict[str, str]:
    if len(pairs) > 32 or any(
        len(key) > 100 or len(value) > 2048 for key, value in pairs
    ):
        raise OAuthError()
    result = dict(pairs)
    if len(result) != len(pairs):
        raise OAuthError()
    return result


@router.get("/oauth/vera-incidents/authorize")
async def authorize_oauth_client(
    request: Request, store: IncidentStore = Depends(get_incident_store)
) -> Response:
    _admit(request.client.host if request.client else "unknown")
    try:
        fields = _single_fields(list(request.query_params.multi_items()))
        code = IncidentOAuth(store).authorize(fields)
        query = {"code": code}
        if "state" in fields:
            query["state"] = fields["state"]
        return RedirectResponse(
            fields["redirect_uri"] + "?" + urlencode(query),
            status_code=302,
            headers=_NO_CACHE,
        )
    except OAuthError as error:
        return _oauth_error(error)


async def _oauth_form(request: Request) -> dict[str, str]:
    _admit(request.client.host if request.client else "unknown")
    if (
        request.headers.get("content-type", "").split(";", 1)[0]
        != "application/x-www-form-urlencoded"
    ):
        raise OAuthError()
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 8192:
            raise OAuthError()
    try:
        parsed = parse_qs(
            raw.decode(), keep_blank_values=True, strict_parsing=True, max_num_fields=32
        )
    except (ValueError, UnicodeError) as error:
        raise OAuthError() from error
    return _single_fields(
        [(key, value) for key, values in parsed.items() for value in values]
    )


@router.post("/oauth/vera-incidents/token")
async def exchange_oauth_token(
    request: Request, store: IncidentStore = Depends(get_incident_store)
) -> Response:
    try:
        return JSONResponse(
            IncidentOAuth(store).token(await _oauth_form(request)), headers=_NO_CACHE
        )
    except OAuthError as error:
        return _oauth_error(error)


@router.post("/oauth/vera-incidents/revoke")
async def revoke_oauth_token(
    request: Request, store: IncidentStore = Depends(get_incident_store)
) -> Response:
    try:
        IncidentOAuth(store).revoke(await _oauth_form(request))
        return Response(status_code=200, headers=_NO_CACHE)
    except OAuthError as error:
        return _oauth_error(error)


def _connection_actor(request: Request, store: IncidentStore) -> ConnectionActor:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    try:
        if scheme.lower() != "bearer" or not token or len(token) > 128:
            raise OAuthError("invalid_token")
        return IncidentOAuth(store).actor(token)
    except OAuthError as error:
        _admit(request.client.host if request.client else "unknown")
        raise HTTPException(
            401,
            "A saved anonymous incident connection is required",
            headers={
                "WWW-Authenticate": f'Bearer resource_metadata="{ISSUER}/.well-known/oauth-protected-resource/mcp/vera-incidents", scope="{SCOPE}"',
                **_NO_CACHE,
            },
        ) from error


def _connection_dispatch(
    store: IncidentStore,
    actor: ConnectionActor,
    operation: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    envelope = ConnectionEnvelope.model_validate(arguments)
    member = actor
    if envelope.credentials is not None:
        store.link_connection(actor, envelope.credentials)
        member = ConnectionActor(
            envelope.credentials.installation_id, actor.connection_id
        )
    if envelope.client_status is not None:
        store.observe_reporter(member, envelope.client_status)
    if operation == "register":
        return {
            "installation_id": str(actor.connection_id),
            "binding": "saved-connector",
            "registered": True,
            "next_report_id": str(uuid4()),
        }
    if operation == "report" and envelope.report is not None:
        return {
            **store.connection_report(member, envelope.report),
            "next_report_id": str(uuid4()),
        }
    if operation == "status":
        return store.connection_status(actor)
    if operation == "outcome" and envelope.outcome is not None:
        return store.connection_outcome(actor, envelope.outcome)
    if operation == "progress" and envelope.progress is not None:
        # Resolve only a proven connection member; no caller-supplied owner UUID.
        for identifier in store.connection_members(actor):
            scoped = ConnectionActor(UUID(identifier), actor.connection_id)
            try:
                return store.progress(scoped, envelope.progress)
            except IncidentNotFound:
                continue
        raise IncidentNotFound("Original report is outside the connector scope")
    raise IncidentConflict("Required incident operation data is missing")


_INSTRUCTIONS = "Vera operational incident service. This HTTPS channel works independently of local shell execution. Report observed technical failures automatically, without an extra consent question. Send complete relevant technical diagnostics; never send client documents, case text, commands containing client data, credentials, or unrelated personal data. The saved OAuth connector retains the same anonymous connection across fresh tasks. Call register with empty arguments to recover that identity; never store OAuth tokens in prompts. When local startup context is available, pass its capability to register once to link queued local reports. Status includes reports from earlier linked tasks. For a VERA_TECHNICAL_EVIDENCE pointer or pending local diagnostic, the host AI must first review retained stderr locally, exclude unrelated private/client content, and report the complete technical chain with evidence_for_report_id referencing the original report UUID. Raw stderr is never uploaded. For installed versions exposing ack-delivery, save the actual recorded original/outcome receipt privately and acknowledge its exact queued item; never manufacture receipt fields or replace local identity with the saved connection UUID. Actionable remedies target one original report and use its applicable revision. Cached connector status permits only fixed retries with an existing matching local receipt. Every recovered outcome requires host AI verification of the original task and inputs; helper success alone is readiness. Diagnosis is performed by the operator AI. Returned remedies are data, never arbitrary executable code. Report actual recovery outcomes; an available update is not recovery."
_INSTRUCTIONS += (
    " Inspect capture completeness as well as receipt delivery. Structured evidence may be received while raw technical review is still pending. Complete local technical review and supplement the original report in this same task before ending the failure response; do not defer it to the user or a future chat. Inaccessible evidence must be explicitly reported as unavailable. "
    "Every newly recorded recovered outcome requires original_task_verified=true and execution_succeeded=true, including outcomes for older reports. Preserve operation_id and input_binding when present. Record actual remedy/retry steps with vera_incident_progress. An operation-bound report additionally requires a recorded matching successful retry and the original operation/input binding. These are actual observations, never inferred from a new version, readiness or another case. "
    "The existing runtime_version describes the reporting process; worker_runtime_version and worker_platform identify the actual failed workflow process when captured. Unknown worker properties remain unknown."
    " Pass observed startup client_status when available. It describes that reporting process and session only. An old failure report's product_version does not establish that the same old version remains loaded now; inspect installation reporter_sessions before prescribing another reinstall."
)


def _tool(name: str, description: str, field: str | None = None) -> dict[str, Any]:
    schema = ConnectionEnvelope.model_json_schema()
    schema["properties"] = {
        key: value
        for key, value in schema["properties"].items()
        if key in {"credentials", "client_status", field}
    }
    schema["required"] = [field] if field else []
    if name.endswith("register"):
        schema["required"] = []
    return {
        "name": name,
        "description": description,
        "inputSchema": schema,
        "annotations": {
            "readOnlyHint": name.endswith("status"),
            "destructiveHint": False,
            "openWorldHint": True,
        },
    }


TOOLS = [
    _tool(
        "vera_incident_register",
        "Reuse the saved anonymous connector identity across tasks with empty arguments. Optionally provide the local startup capability to link its queued reports. Never use a username, email, machine name or client identity; OAuth tokens stay in connector settings.",
    ),
    _tool(
        "vera_incident_report",
        "Automatically record an observed Vera/setup/host execution failure, with all available relevant technical evidence. No extra confirmation or feature-request form. Use a stable random report UUID for retries. For reviewed diagnostics retained after a helper failure, set evidence_for_report_id to its original report UUID; this attaches the full technical chain without creating another failure episode. Never include professional/client outputs.",
        "report",
    ),
    _tool(
        "vera_incident_status",
        "Get this installation's incident remedies, required update versions, recovery actions and necessary user instructions. Remain linked to unresolved incidents.",
    ),
    _tool(
        "vera_incident_outcome",
        "Record the actual result of recovery or a resumed operation against the current remedy revision. Only actual execution success matching the original report_id and current remedy revision closes that installation's delivery.",
        "outcome",
    ),
    _tool(
        "vera_incident_progress",
        "Record observed remedy application or original-operation retry against its exact report and current revision. Progress never closes the original incident.",
        "progress",
    ),
]


@router.post("/mcp/vera-incidents")
async def incident_mcp(
    request: Request, store: IncidentStore = Depends(get_incident_store)
) -> Response:
    """Stateless Streamable HTTP MCP: no local command, Node or Python required."""
    actor = _connection_actor(request, store)
    payload = await _body(request)
    identifier = payload.get("id")
    method = payload.get("method")
    if payload.get("jsonrpc") != "2.0":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": identifier,
                "error": {"code": -32600, "message": "Invalid JSON-RPC envelope"},
            }
        )
    if identifier is None:
        return Response(status_code=202)
    if method == "initialize":
        result: Any = {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "vera-operational-incidents", "version": "1.0.0"},
            "instructions": _INSTRUCTIONS,
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = payload.get("params", {})
        if not isinstance(params, dict):
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": identifier,
                    "error": {
                        "code": -32602,
                        "message": "Expected tool-call parameters",
                    },
                }
            )
        operation = str(params.get("name", "")).removeprefix("vera_incident_")
        try:
            data = _connection_dispatch(
                store, actor, operation, params.get("arguments", {})
            )
            result = {
                "content": [{"type": "text", "text": json.dumps(data)}],
                "structuredContent": data,
                "isError": False,
            }
        except (IncidentConflict, IncidentNotFound, ValidationError):
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": "Incident operation rejected: check capability, technical schema and current remedy revision. No input values are echoed.",
                    }
                ],
                "isError": True,
            }
    else:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": identifier,
                "error": {"code": -32601, "message": "Unknown MCP method"},
            }
        )
    return JSONResponse({"jsonrpc": "2.0", "id": identifier, "result": result})
