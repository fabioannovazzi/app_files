"""File handoff to Vera's configured native Cowork Haiku subagent."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from audit_core import AuditError, SemanticReviewPending

__all__ = ["configured_runtime", "run_cowork_chunk"]


def configured_runtime() -> str:
    """Read the distribution's explicit worker configuration."""
    payload = json.loads(Path(__file__).with_name("worker_config.json").read_text())
    runtime = payload["runtime"]
    if runtime not in {"codex-luna", "cowork-haiku"}:
        raise AuditError("Unsupported packaged semantic runtime")
    return runtime


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def run_cowork_chunk(
    prompt: str,
    output_schema: Mapping[str, Any],
    output_dir: Path,
    workflow_id: str,
    packet_sha256: str,
    reasoning_effort: str,
) -> Mapping[str, Any]:
    """Prepare a bounded request, then ingest its host-recorded worker response.

    This invokes no API and does not assert a verified model identity. Cowork
    dispatches the packaged Haiku agent and saves its response and tool record.
    Missing responses leave the audit pending, never successfully screened.
    """
    if reasoning_effort != "low":
        raise AuditError("Cowork Haiku does not accept Luna effort overrides")
    request = {
        "schema_version": "vera.cowork_semantic_request.v1",
        "workflow_id": workflow_id,
        "packet_sha256": packet_sha256,
        "agent": "vera:passive-invoice-reviewer",
        "requested_model": "haiku",
        "prompt": prompt,
        "output_schema": dict(output_schema),
    }
    request["request_sha256"] = _digest(request)
    request_path = output_dir / "cowork_request.json"
    response_path = output_dir / "cowork_response.json"
    record_path = output_dir / "cowork_worker_record.json"
    for path in (request_path, response_path, record_path):
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise AuditError("Unsafe Cowork worker artifact")
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n")
    if not response_path.exists():
        raise SemanticReviewPending(f"Dispatch {request['agent']} for {request_path}")
    if not record_path.exists():
        raise AuditError("Cowork response is missing its host worker record")
    response_bytes = response_path.read_bytes()
    response_text = response_bytes.decode("utf-8").strip()
    if response_text.startswith("```json\n") and response_text.endswith("\n```"):
        response_text = response_text[8:-4]
    response = json.loads(response_text)
    record = json.loads(record_path.read_text())
    if not isinstance(record, dict) or (
        record.get("schema_version") != "vera.cowork_worker_record.v1"
        or record.get("request_sha256") != request["request_sha256"]
        or record.get("agent") != request["agent"]
        or record.get("requested_model") != "haiku"
        or record.get("response_sha256") != hashlib.sha256(response_bytes).hexdigest()
        or record.get("provenance") != "cowork_host_reported"
        or not isinstance(record.get("invocation_id"), str)
        or not record["invocation_id"].strip()
    ):
        raise AuditError(
            "Cowork worker record does not match this request and response"
        )
    return {
        "response_payload": response,
        "model": "haiku",
        "reasoning_effort": "host_default",
        "usage": {},
        "duration_ms": 0,
        "recovery_source": "cowork_host_reported",
    }
