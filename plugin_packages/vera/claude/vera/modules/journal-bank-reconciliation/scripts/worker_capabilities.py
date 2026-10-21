"""Shared reconciliation worker selection from the current host's capabilities.

The cost policy is owned configuration, not a claim that a model is available
or adequate. Availability comes from the running harness; the capsule separately
probes isolation on every invocation. No provider API or visible chat is used.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
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
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
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
                        if not selector.select(1):
                            continue
                        chunk = os.read(process.stdout.fileno(), 65536)
                        buffer += chunk
                        if not chunk or len(buffer) > 1_000_000:
                            raise UnsupportedWorkerCapability(
                                "Claude model/list probe exited or exceeded its response bound"
                            )
                        continue
                    line, buffer = buffer.split(b"\n", 1)
                    message = json.loads(line)
                    if message.get("id") == number:
                        if "error" in message:
                            raise UnsupportedWorkerCapability(
                                f"Claude {method} failed: {message['error']}"
                            )
                        return message["result"]
                raise UnsupportedWorkerCapability(f"Claude {method} timed out")

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
                models = request(
                    2, "model/list", {"limit": 100, "includeHidden": False}
                )
                if models.get("nextCursor"):
                    raise UnsupportedWorkerCapability(
                        "Claude model catalog exceeds the bounded discovery page"
                    )
                return {"runtime": runtime["userAgent"], "models": models["data"]}
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def select_worker(
    workflow_id: str, effort: str | None = None, *, host: str | None = None
) -> dict[str, Any]:
    """Select a policy candidate actually advertised by this host's model API."""
    policy = json.loads(
        Path(__file__).with_name("semantic_worker_policy.json").read_text()
    )
    selected_host = host or policy["host"]
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
    for candidate in policy["candidates"][selected_host]:
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
    if value.get("host") != "codex" or value.get("cost_class") != "low":
        raise UnsupportedWorkerCapability(
            "Worker selection has no supported low-cost host adapter"
        )
    model, selected_effort = value["model"], value["reasoning_effort"]
    if (
        not isinstance(model, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", model) is None
        or selected_effort not in {"none", "low", "medium", "high", "xhigh", "max"}
    ):
        raise ValueError("Invalid worker model/effort")
    if effort is not None and effort != selected_effort:
        raise ValueError("Requested effort differs from the discovered selection")
    return model, selected_effort, dict(value)


def legacy_selection(effort: str | None) -> tuple[str, str, None]:
    """Read the retained API default; new reconciliation paths use discovery."""
    policy = json.loads(
        Path(__file__).with_name("semantic_worker_policy.json").read_text()
    )
    selected = effort or policy["legacy_default"]["effort"]
    if selected not in {"none", "low", "medium", "high", "xhigh", "max"}:
        raise ValueError("Unsupported legacy worker reasoning effort")
    return policy["legacy_default"]["model"], selected, None
