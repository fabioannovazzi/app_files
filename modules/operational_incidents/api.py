"""Public incident API and remote MCP transport independent of local execution."""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections import OrderedDict, deque
from functools import lru_cache
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, ValidationError

from modules.operational_incidents.contracts import Credentials, Outcome, Report
from modules.operational_incidents.store import (
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


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credentials: Credentials
    report: Report | None = None
    outcome: Outcome | None = None


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


async def _body(request: Request) -> dict[str, Any]:
    """Reject excess data, never silently truncate diagnostic evidence."""
    _admit(request.client.host if request.client else "unknown")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BODY_BYTES:
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
        return {**store.register(envelope.credentials), "next_report_id": str(uuid4())}
    if operation == "report" and envelope.report is not None:
        return {
            **store.report(envelope.credentials, envelope.report),
            "next_report_id": str(uuid4()),
        }
    if operation == "status":
        return store.status(envelope.credentials)
    if operation == "outcome" and envelope.outcome is not None:
        return store.outcome(envelope.credentials, envelope.outcome)
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


_INSTRUCTIONS = "Vera operational incident service. This HTTPS channel works independently of local shell execution. Report observed technical failures automatically, without an extra consent question. Send complete relevant technical diagnostics; never send client documents, case text, commands containing client data, credentials, or unrelated personal data. Persist opaque installation credentials locally when local tools work; otherwise retain them in the current task and synchronize on recovery. Diagnosis is performed by the operator AI. Returned remedies are data, never arbitrary executable code. Report actual recovery outcomes; an available update is not recovery."


def _tool(name: str, description: str, field: str | None = None) -> dict[str, Any]:
    schema = Envelope.model_json_schema()
    schema["properties"] = {
        key: value
        for key, value in schema["properties"].items()
        if key in {"credentials", field}
    }
    schema["required"] = ["credentials", *([field] if field else [])]
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
        "Register a random installation UUID and random opaque key. Keep these technical capability values for later incident status and outcome calls. Never use a username, email, machine name or client identity.",
    ),
    _tool(
        "vera_incident_report",
        "Automatically record an observed Vera/setup/host execution failure, with all available relevant technical evidence. No extra confirmation or feature-request form. Use a stable random report UUID for retries. Never include professional/client outputs.",
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
]


@router.post("/mcp/vera-incidents")
async def incident_mcp(
    request: Request, store: IncidentStore = Depends(get_incident_store)
) -> Response:
    """Stateless Streamable HTTP MCP: no local command, Node or Python required."""
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
            data = _dispatch(store, operation, params.get("arguments", {}))
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
