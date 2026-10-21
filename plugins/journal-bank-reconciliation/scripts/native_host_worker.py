"""Bounded handoff to the calling host's native subagent, with honest evidence.

The parent records its actual tool invocation and completion, never a model's
claim about itself. This is host-reported provenance, not provider attestation
or an OS filesystem sandbox. Hashes prevent stale packet/response substitution.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

__all__ = ["NativeWorkerPending", "configuration", "run_worker", "validate_receipt"]

SCHEMA = "vera.native_host_worker_receipt.v1"
REQUEST = "native_host_request.json"
RECORD = "native_host_record.json"
LIMIT = 1_000_000
HOSTS = {
    "cowork": ("Agent", "vera:reconciliation-reviewer", ["Read"]),
    "antigravity": ("invoke_subagent", "reconciliation-reviewer", []),
}


class NativeWorkerPending(ValueError):
    """The parent must dispatch the prepared native request and resume."""


def _bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: Any) -> str:
    return _sha(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    )


def _file(directory: Path, name: str) -> Path:
    path = directory / name
    if (
        directory.is_symlink()
        or path.is_symlink()
        or (
            path.exists()
            and (
                not path.is_file()
                or path.stat().st_nlink != 1
                or path.stat().st_size > LIMIT
            )
        )
    ):
        raise ValueError("Unsafe or oversized native worker artifact")
    return path


def _retain(directory: Path, name: str, data: bytes) -> Path:
    path = _file(directory, name)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Native worker artifact changed: {name}")
    else:
        path.write_bytes(data)
    return path


def configuration(selection: Mapping[str, Any]) -> dict[str, Any]:
    """Describe the native boundary without borrowing Codex-only guarantees."""
    host = selection["host"]
    tool, agent, declared_tools = HOSTS[host]
    model = selection["model"]
    return {
        "execution": "native_subagent",
        "host": host,
        "tool": tool,
        "agent": agent,
        "model": model,
        "reasoning_effort": "host_default",
        "selection_review": dict(selection),
        "fresh_context": True,
        "declared_tools": declared_tools,
        "direct_model_api": False,
        "main_chat_model_change": False,
        "provider_attestation": False,
        "host_ambient_instructions_excluded": False,
        "transcript_retention": "host_managed",
    }


def _request(
    prompt: str,
    schema: Mapping[str, Any],
    workflow: str,
    packet: str,
    selection: Mapping[str, Any],
) -> dict[str, Any]:
    config = configuration(selection)
    invocation_prompt = (
        prompt
        + "\nReturn only JSON conforming to OUTPUT_SCHEMA_JSON:\n"
        + json.dumps(schema, ensure_ascii=False, sort_keys=True)
    )
    if not prompt.strip() or len(invocation_prompt.encode()) > 96_000:
        raise ValueError("Native worker prompt is empty or exceeds its bounded packet")
    if config["host"] == "cowork":
        parameters = {
            "description": "Review reconciliation evidence",
            "subagent_type": config["agent"],
            "model": config["model"],
            "prompt": invocation_prompt,
        }
    else:
        parameters = {
            "TypeName": config["agent"],
            "Role": "Reconciliation Evidence Reviewer",
            "Model": config["model"],
            "Workspace": "inherit",
            "Prompt": invocation_prompt,
        }
    content = {
        "schema_version": "vera.native_host_worker_request.v1",
        "workflow_id": workflow,
        "packet_sha256": packet,
        "configuration": config,
        "prompt": prompt,
        "output_schema": dict(schema),
        "invocation": {"tool": config["tool"], "parameters": parameters},
    }
    return {**content, "content_sha256": _digest(content)}


def _completion(
    request: Mapping[str, Any], record: Mapping[str, Any]
) -> dict[str, Any]:
    config = request["configuration"]
    capabilities = record["capabilities"]
    completion = record["completion"]
    if (
        record.get("schema_version") != "vera.native_host_worker_record.v1"
        or record.get("provenance") != "parent_observed_native_tool"
        or record.get("request_sha256") != request["content_sha256"]
        or record.get("invocation") != request["invocation"]
        or capabilities.get("host") != config["host"]
        or capabilities.get("tool") != config["tool"]
        or capabilities.get("agent") != config["agent"]
        or capabilities.get("declared_tools") != config["declared_tools"]
        or config["model"] not in capabilities.get("model_choices", [])
        or capabilities.get("fresh_context") is not True
        or not isinstance(capabilities.get("runtime"), str)
        or not capabilities["runtime"].strip()
    ):
        raise ValueError(
            "Native invocation or current host capabilities do not match the request"
        )
    if (
        not isinstance(completion.get("invocation_id"), str)
        or not completion["invocation_id"].strip()
        or completion.get("status") != "completed"
        or type(completion.get("tool_uses")) is not int
        or completion["tool_uses"] != 0
        or completion.get("parent_history_inherited") is not False
        or completion.get("resumed") is not False
    ):
        raise ValueError(
            "Native worker is incomplete, reused, or used tools outside its evidence packet"
        )
    response = json.loads(completion["response_text"])
    if not isinstance(response, dict):
        raise ValueError("Native worker response must be a JSON object")
    return response


def run_worker(
    *,
    prompt: str,
    output_schema: Mapping[str, Any],
    output_dir: Path,
    workflow_id: str,
    packet_sha256: str,
    worker_selection: Mapping[str, Any],
) -> dict[str, Any]:
    """Prepare once; consume the same request after the native parent completes it."""
    if not output_dir.is_dir() or output_dir.is_symlink():
        raise ValueError("Native worker output must be an ordinary directory")
    request = _request(
        prompt, output_schema, workflow_id, packet_sha256, worker_selection
    )
    request_path = _retain(output_dir, REQUEST, _bytes(request))
    record_path = _file(output_dir, RECORD)
    if not record_path.exists():
        raise NativeWorkerPending(
            f"NATIVE_WORKER_PENDING: dispatch {request_path}; retain the actual native tool record and resume the same command"
        )
    record = json.loads(record_path.read_bytes())
    response = _completion(request, record)
    response_bytes = _bytes(response)
    events_bytes = _bytes(record)
    content = {
        "schema_version": SCHEMA,
        "workflow_id": workflow_id,
        "packet_sha256": packet_sha256,
        "request": request,
        "native_record": record,
        "requested_worker_configuration": request["configuration"],
        "packet": {
            "prompt_sha256": _sha(prompt.encode()),
            "output_schema_sha256": _sha(_bytes(output_schema)),
        },
        "process": {
            "return_code": 0,
            "response_sha256": _sha(response_bytes),
            "events_sha256": _sha(events_bytes),
            "stderr_sha256": _sha(b""),
        },
        "runtime_attestation": {
            "provenance": "parent_observed_native_tool",
            "provider_attestation": False,
            "os_isolation_probed": False,
            "tool_uses_observed": 0,
            "model_requested": request["configuration"]["model"],
            "model_observed": record["completion"].get("model_observed"),
        },
        "advisory_only": True,
    }
    receipt = {**content, "content_sha256": _digest(content)}
    paths = {
        key: _retain(output_dir, name, data)
        for key, name, data in (
            ("response", "luna_response.json", response_bytes),
            ("events", "luna_events.jsonl", events_bytes),
            ("stderr", "luna_stderr.log", b""),
            ("launch_receipt", "luna_launch_receipt.json", _bytes(receipt)),
        )
    }
    return {
        **paths,
        "response_payload": response,
        "model": request["configuration"]["model"],
        "reasoning_effort": "host_default",
        "worker_selection": dict(worker_selection),
        "usage": record["completion"].get("usage", {}),
        "main_chat_model_change": False,
    }


def validate_receipt(
    receipt: Mapping[str, Any],
    *,
    workflow_id: str,
    packet_sha256: str,
    prompt: str,
    output_schema: Mapping[str, Any],
    response: Mapping[str, Any],
) -> dict[str, Any]:
    """Replay native provenance independently of domain matching judgments."""
    from worker_capabilities import validate_selection

    content = {key: value for key, value in receipt.items() if key != "content_sha256"}
    if receipt.get("schema_version") != SCHEMA or receipt.get(
        "content_sha256"
    ) != _digest(content):
        raise ValueError("Native launch receipt digest is stale")
    selection = receipt["requested_worker_configuration"]["selection_review"]
    validate_selection(selection, workflow_id.replace("_", "-"), None)
    expected = _request(prompt, output_schema, workflow_id, packet_sha256, selection)
    if (
        receipt["request"] != expected
        or receipt["workflow_id"] != workflow_id
        or receipt["packet_sha256"] != packet_sha256
        or receipt["requested_worker_configuration"] != expected["configuration"]
        or receipt["advisory_only"] is not True
    ):
        raise ValueError("Native receipt belongs to another request or workflow")
    actual_response = _completion(expected, receipt["native_record"])
    if actual_response != response or receipt["process"] != {
        "return_code": 0,
        "response_sha256": _sha(_bytes(response)),
        "events_sha256": _sha(_bytes(receipt["native_record"])),
        "stderr_sha256": _sha(b""),
    }:
        raise ValueError("Native response differs from its completed host invocation")
    completion = receipt["native_record"]["completion"]
    return {
        "thread_id": completion["invocation_id"],
        "usage": completion.get("usage", {}),
        "completed_item_counts": {"native_completion": 1},
    }
