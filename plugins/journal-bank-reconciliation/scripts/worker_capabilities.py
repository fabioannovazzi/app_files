"""Shared reconciliation worker selection from the current host's capabilities.

The cost policy is owned configuration, not a claim that a model is available
or adequate. Availability comes from the running harness; the capsule separately
probes isolation on every invocation. No provider API or visible chat is used.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "UnsupportedWorkerCapability",
    "select_worker",
    "validate_selection",
    "legacy_selection",
]


class UnsupportedWorkerCapability(ValueError):
    """The current host has no verified callable isolated low-cost worker."""


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def _catalog(executable: str) -> dict[str, Any]:
    """Query model/list without starting a conversation or reading client data."""
    with subprocess.Popen(
        [executable, "app-server", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ) as process:
        assert process.stdin is not None and process.stdout is not None
        chunks: queue.Queue[bytes | OSError] = queue.Queue(maxsize=2)
        stopped = threading.Event()

        def read_stdout() -> None:
            try:
                while not stopped.is_set():
                    chunk = os.read(process.stdout.fileno(), 65536)
                    while not stopped.is_set():
                        try:
                            chunks.put(chunk, timeout=0.1)
                            break
                        except queue.Full:
                            continue
                    if not chunk:
                        return
            except OSError as exc:
                if not stopped.is_set():
                    try:
                        chunks.put(exc, timeout=0.1)
                    except queue.Full:
                        pass

        reader = threading.Thread(target=read_stdout, daemon=True)
        reader.start()
        buffer = b""

        def request(number: int, method: str, params: dict[str, Any]) -> Any:
            nonlocal buffer
            process.stdin.write(
                (
                    json.dumps({"id": number, "method": method, "params": params})
                    + "\n"
                ).encode()
            )
            process.stdin.flush()
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if b"\n" not in buffer:
                    try:
                        chunk = chunks.get(
                            timeout=min(1, max(0.01, deadline - time.monotonic()))
                        )
                    except queue.Empty:
                        continue
                    if isinstance(chunk, OSError):
                        raise UnsupportedWorkerCapability(
                            "Codex model/list pipe failed"
                        ) from chunk
                    buffer += chunk
                    if not chunk or len(buffer) > 1_000_000:
                        raise UnsupportedWorkerCapability(
                            "Codex model/list probe exited or exceeded its response bound"
                        )
                    continue
                line, buffer = buffer.split(b"\n", 1)
                message = json.loads(line)
                if message.get("id") == number:
                    if "error" in message:
                        raise UnsupportedWorkerCapability(
                            f"Codex {method} failed: {message['error']}"
                        )
                    return message["result"]
            raise UnsupportedWorkerCapability(f"Codex {method} timed out")

        try:
            runtime = request(
                1,
                "initialize",
                {
                    "clientInfo": {
                        "name": "vera-worker-capabilities",
                        "version": "1",
                    }
                },
            )
            process.stdin.write(b'{"method":"initialized"}\n')
            process.stdin.flush()
            models = request(2, "model/list", {"limit": 100, "includeHidden": False})
            if models.get("nextCursor"):
                raise UnsupportedWorkerCapability(
                    "Codex model catalog exceeds the bounded discovery page"
                )
            return {"runtime": runtime["userAgent"], "models": models["data"]}
        finally:
            stopped.set()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            reader.join(timeout=1)


def select_worker(
    workflow_id: str,
    effort: str | None = None,
    *,
    host: str | None = None,
    stage: str = "luna",
) -> dict[str, Any]:
    """Select a policy candidate actually advertised by this host's model API."""
    policy = json.loads(
        Path(__file__)
        .with_name("semantic_worker_policy.json")
        .read_text(encoding="utf-8")
    )
    if stage not in {"luna", "sol"}:
        raise ValueError("Unknown reconciliation stage")
    candidates = policy["candidates" if stage == "luna" else "strong_candidates"]
    candidates = (
        {**candidates, **policy.get("workflow_candidates", {}).get(workflow_id, {})}
        if stage == "luna"
        else candidates
    )
    selected_host = host or policy["host"]
    if selected_host in {"cowork", "antigravity"}:
        # Python cannot inspect the calling agent's tool schema. Prepare a
        # preference, then require current native capabilities and an actual
        # completion before accepting any semantic result.
        candidate = candidates[selected_host][0]
        if effort not in {None, "host_default"}:
            raise UnsupportedWorkerCapability(
                "Native subagent effort is controlled by its host"
            )
        content = {
            "schema_version": "vera.semantic_worker_selection.v1",
            "workflow_id": workflow_id,
            "host": selected_host,
            "model": candidate["model"],
            "reasoning_effort": "host_default",
            "cost_class": candidate["cost_class"],
            "discovery": {
                "method": "native_tool_schema_at_dispatch",
                "status": "requires_parent_observation",
            },
            "policy_sha256": _digest(policy),
            "quality_claim": "requires_representative_validation",
        }
        return {**content, "content_sha256": _digest(content)}
    if selected_host != "codex":
        raise UnsupportedWorkerCapability(
            f"{selected_host}: no verified model-discovery and isolated invocation adapter is implemented; "
            "semantic resolution remains pending (no worker ran)"
        )
    executable = shutil.which("codex")
    if executable is None:
        raise UnsupportedWorkerCapability("codex: callable CLI is missing")
    catalog = _catalog(executable)
    available = {model["model"]: model for model in catalog["models"]}
    for candidate in candidates[selected_host]:
        model = available.get(candidate["model"])
        selected_effort = effort or candidate["effort"]
        if model is None or selected_effort not in {
            item["reasoningEffort"] for item in model["supportedReasoningEfforts"]
        }:
            continue
        content = {
            "schema_version": "vera.semantic_worker_selection.v1",
            "workflow_id": workflow_id,
            "host": selected_host,
            "model": candidate["model"],
            "reasoning_effort": selected_effort,
            "cost_class": candidate["cost_class"],
            "discovery": {
                "method": "model/list",
                "runtime": catalog["runtime"],
                "catalog_sha256": _digest(catalog),
            },
            "policy_sha256": _digest(policy),
            "quality_claim": "requires_representative_validation",
        }
        return {**content, "content_sha256": _digest(content)}
    raise UnsupportedWorkerCapability(
        "codex: no configured low-cost model/effort is advertised by model/list"
    )


def validate_selection(
    value: Mapping[str, Any], workflow_id: str, effort: str | None
) -> tuple[str, str, dict[str, Any]]:
    """Replay a selection without replacing it with a later catalog or policy.

    Digest and scope checks prevent configuration drift, not forged provenance.
    Actual invocation and executable/isolation evidence remain capsule-owned.
    """
    content = {key: item for key, item in value.items() if key != "content_sha256"}
    if (
        value.get("content_sha256") != _digest(content)
        or value.get("workflow_id") != workflow_id
    ):
        raise ValueError("Worker selection digest or workflow is inconsistent")
    if value.get("host") not in {"codex", "cowork", "antigravity"} or value.get(
        "cost_class"
    ) not in {"low", "standard", "escalation"}:
        raise UnsupportedWorkerCapability(
            "Worker selection has no supported low-cost host adapter"
        )
    model, selected_effort = value["model"], value["reasoning_effort"]
    owned = json.loads(
        Path(__file__)
        .with_name("semantic_worker_policy.json")
        .read_text(encoding="utf-8")
    )
    configured = owned[
        "strong_candidates" if value["cost_class"] == "escalation" else "candidates"
    ][value["host"]]
    if value["cost_class"] != "escalation":
        configured = (
            owned.get("workflow_candidates", {})
            .get(workflow_id, {})
            .get(value["host"], configured)
        )
    if not any(
        c["model"] == model and c["cost_class"] == value["cost_class"]
        for c in configured
    ):
        raise UnsupportedWorkerCapability(
            "Worker model does not belong to the owned stage policy"
        )
    if (
        not isinstance(model, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", model) is None
        or selected_effort
        not in {"none", "low", "medium", "high", "xhigh", "max", "host_default"}
    ):
        raise ValueError("Invalid worker model/effort")
    if value["host"] in {"cowork", "antigravity"} and (
        model == "inherit"
        or selected_effort != "host_default"
        or value["discovery"].get("method") != "native_tool_schema_at_dispatch"
    ):
        raise ValueError("Native selection does not match the callable host adapter")
    if value["host"] == "codex" and selected_effort == "host_default":
        raise ValueError("Codex requires an advertised reasoning effort")
    if effort is not None and effort != selected_effort:
        raise ValueError("Requested effort differs from the discovered selection")
    return model, selected_effort, dict(value)


def legacy_selection(effort: str | None) -> tuple[str, str, None]:
    """Read the retained API default; new reconciliation paths use discovery."""
    policy = json.loads(
        Path(__file__)
        .with_name("semantic_worker_policy.json")
        .read_text(encoding="utf-8")
    )
    selected = effort or policy["legacy_default"]["effort"]
    if selected not in {"none", "low", "medium", "high", "xhigh", "max"}:
        raise ValueError("Unsupported legacy worker reasoning effort")
    return policy["legacy_default"]["model"], selected, None
