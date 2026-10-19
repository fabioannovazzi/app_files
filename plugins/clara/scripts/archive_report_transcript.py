"""Read model-visible Codex results, including the outer result of code mode.

PostToolUse can observe a nested result which a JavaScript caller never emits.
Only response-item tool outputs in the local host transcript are counted here.
The parser is deliberately version-bounded: unsupported or missing evidence
leaves the report incomplete. It does not reconstruct earlier chats.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from archive_report_store import Registry, RunStore, atomic_json, serialized_run

__all__ = ["attach", "refresh", "closing_calls", "barrier_complete"]
_CALLS = {"function_call", "custom_tool_call"}
_OUTPUTS = {"function_call_output", "custom_tool_call_output"}


def _cursor(root: Path, session: str) -> Path:
    return (
        root
        / "reporting"
        / ("host-" + hashlib.sha256(session.encode()).hexdigest() + ".json")
    )


def _source(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Host transcript is not an ordinary file")


def _call(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload["name"],
        "input": payload.get("arguments", payload.get("input")),
    }


@serialized_run
def attach(root: Path, session: str, transcript: Path) -> None:
    """Start at the current EOF, retaining only the in-flight call identifiers."""
    target = _cursor(root, session)
    if target.is_file():
        existing = json.loads(target.read_text(encoding="utf-8"))
        if existing["path"] != str(transcript):
            RunStore(root).error("host_transcript_path_changed")
        return
    _source(transcript)
    size = transcript.stat().st_size
    calls = {}
    offset = size
    with transcript.open("rb") as handle:
        handle.seek(max(0, size - 262144))
        if handle.tell():
            handle.readline()
        while line := handle.readline():
            if not line.endswith(b"\n"):
                offset = handle.tell() - len(line)
                break
            value = json.loads(line)
            if value.get("type") != "response_item":
                continue
            payload = value["payload"]
            if payload.get("type") in _CALLS:
                calls[payload["call_id"]] = _call(payload)
            elif payload.get("type") in _OUTPUTS:
                calls.pop(payload["call_id"], None)
    atomic_json(
        target,
        {
            "path": str(transcript),
            "session": session,
            "offset": offset,
            "calls": calls,
            "completed": [],
            "format": "codex-response-item-v1",
        },
    )


@serialized_run
def refresh(root: Path, session: str) -> None:
    """Consume complete new JSONL records once, without collecting chat history."""
    target = _cursor(root, session)
    if not target.is_file():
        RunStore(root).error("host_transcript_missing")
        return
    cursor = json.loads(target.read_text(encoding="utf-8"))
    path = Path(cursor["path"])
    _source(path)
    if path.stat().st_size < cursor["offset"]:
        RunStore(root).error("host_transcript_truncated")
        return
    from archive_reporting import observe_tool

    ambiguous = len(Registry().active(session)) > 1
    state = RunStore(root).state()
    terminal_calls = (
        set(state["closing_calls"].get(session, []))
        if state and state["finished_at"] is not None
        else None
    )
    if terminal_calls is not None and terminal_calls <= set(cursor["completed"]):
        return

    with path.open("rb") as handle:
        handle.seek(cursor["offset"])
        for line in handle:
            if not line.endswith(b"\n"):
                break
            value = json.loads(line)
            if value.get("type") == "response_item":
                payload = value["payload"]
                kind = payload.get("type")
                if kind in _CALLS:
                    cursor["calls"][payload["call_id"]] = _call(payload)
                elif kind in _OUTPUTS:
                    call_id = payload["call_id"]
                    call = cursor["calls"].pop(call_id, None)
                    if call is None:
                        RunStore(root).error("host_tool_call_unresolved")
                    else:
                        observe_tool(
                            root,
                            {
                                "session_id": session,
                                "tool_use_id": call_id,
                                "tool_name": call["name"],
                                "tool_input": call["input"],
                                "tool_response": payload["output"],
                                "evidence_basis": "codex_model_visible_transcript",
                            },
                            ambiguous=ambiguous,
                        )
                    cursor["completed"].append(call_id)
                elif kind == "message" and payload.get("role") == "user":
                    RunStore(root).error("additional_user_context_not_measured")
                elif kind in {
                    "web_search_call",
                    "image_generation_call",
                    "computer_call",
                    "computer_call_output",
                }:
                    RunStore(root).error("hosted_tool_output_not_measured")
            cursor["offset"] = handle.tell()
            if terminal_calls is not None and terminal_calls <= set(
                cursor["completed"]
            ):
                break
    atomic_json(target, cursor)


def closing_calls(root: Path) -> dict[str, list[str]]:
    """Retain the exact outer calls in flight at the terminal Archive write."""
    state = RunStore(root).state()
    result = {
        "hook:" + session: calls
        for session, calls in Registry().pending_calls(state["run_id"]).items()
    }
    for path in (root / "reporting").glob("host-*.json"):
        cursor = json.loads(path.read_text(encoding="utf-8"))
        refresh(root, cursor["session"])
        cursor = json.loads(path.read_text(encoding="utf-8"))
        result[cursor["session"]] = sorted(cursor["calls"])
    return result


def barrier_complete(root: Path, barrier: dict[str, list[str]]) -> bool:
    """Wait for the actual model-visible results of calls that closed Archive."""
    for session, calls in barrier.items():
        if session.startswith("hook:"):
            completed = {item["event_id"] for item in RunStore(root).events()}
            if any(
                "tool:" + session.removeprefix("hook:") + ":" + call not in completed
                for call in calls
            ):
                return False
            continue
        cursor = json.loads(_cursor(root, session).read_text(encoding="utf-8"))
        if not set(calls) <= set(cursor["completed"]):
            return False
    return True
