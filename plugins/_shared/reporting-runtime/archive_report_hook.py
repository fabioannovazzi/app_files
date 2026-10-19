#!/usr/bin/env python3
"""Observe host tool results locally for active Studio Archive reporting runs."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from archive_report_store import Registry, RunStore
from archive_reporting import close_observed_run, observe_tool

__all__ = ["handle", "main"]
LOGGER = logging.getLogger(__name__)
_RUN = re.compile(r"(?<![A-Za-z0-9])run_[0-9a-f]{24}(?![A-Za-z0-9])")


def _run_ids(value: Any) -> set[str]:
    if isinstance(value, str):
        return set(_RUN.findall(value))
    if isinstance(value, dict):
        return {identifier for item in value.values() for identifier in _run_ids(item)}
    if isinstance(value, list):
        return {identifier for item in value for identifier in _run_ids(item)}
    return set()


def handle(event: dict[str, Any]) -> dict[str, Any]:
    """Host events never start/end a report; only Archive lifecycle writes do."""
    kind = event.get("hook_event_name")
    if kind not in {
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "SessionStart",
        "Stop",
    }:
        return {}
    session = event.get("session_id")
    if not isinstance(session, str) or not session:
        raise ValueError("Host reporting event lacks its session identity")
    registry = Registry()
    if kind in {"SessionStart", "Stop"}:
        from archive_report_transcript import refresh

        host = registry.host(session)
        for root in registry.active(session):
            if host and host["host"] == "codex":
                refresh(root, session)
            close_observed_run(root)
        for root in registry.terminal_runs():
            close_observed_run(root)
        from archive_report_receipt import retry_pending

        retry_pending(registry)
        return {}
    tool = event.get("tool_use_id")
    if not isinstance(tool, str) or not tool:
        raise ValueError("Host reporting event lacks its tool-call identity")
    ids = _run_ids(event.get("tool_input"))
    if kind == "PreToolUse":
        registry.begin_tool(
            session,
            tool,
            ids,
            transcript_path=event.get("transcript_path"),
            host="codex" if "turn_id" in event else "claude",
        )
        host = registry.host(session)
        if host and host["host"] == "codex":
            from archive_report_transcript import attach, refresh

            for root in registry.active(session, ids):
                attach(root, session, Path(host["transcript_path"]))
                refresh(root, session)
                close_observed_run(root)
        return {}
    roots = registry.active(session, ids)
    for root in roots:
        host = registry.host(session)
        if host and host["host"] == "codex":
            # Nested code-mode results are not necessarily emitted to the model.
            # The next PreToolUse/Stop consumes the actual outer transcript result.
            continue
        if kind == "PostToolUseFailure":
            RunStore(root).error("tool_failed_without_observed_result")
        observe_tool(root, event, ambiguous=len(roots) > 1 and not ids)
    registry.end_tool(session, tool)
    for root in roots:
        close_observed_run(root)
    return {}


def main() -> int:
    event = {}
    try:
        event = json.load(sys.stdin.buffer)
        if not isinstance(event, dict):
            raise ValueError("Hook input must be an object")
        result = handle(event)
    except (
        ValueError,
        OSError,
        sqlite3.Error,
        KeyError,
        TypeError,
        RecursionError,
    ) as exc:
        LOGGER.error("Archive reporting hook failed: %s", type(exc).__name__)
        session = event.get("session_id") if isinstance(event, dict) else None
        if isinstance(session, str):
            try:
                for root in Registry().active(session):
                    RunStore(root).error("host_collection_failed")
            except (OSError, ValueError, sqlite3.Error):
                LOGGER.error("Archive reporting failure could not be persisted")
        # Do not echo commands, tool responses, source values or credentials.
        result = {
            "systemMessage": "Vera: automatic report evidence collection failed; the run must retain an incomplete-report status."
        }
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
