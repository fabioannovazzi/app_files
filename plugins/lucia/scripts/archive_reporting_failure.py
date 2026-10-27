"""Keep reporting failures visible without cancelling professional work."""

from __future__ import annotations

import json
import sqlite3
import sys
from functools import wraps
from pathlib import Path
from typing import Any
from uuid import uuid4

__all__ = ["REPORTING_ERRORS", "reporting_failure", "isolated_projection"]

REPORTING_ERRORS = (OSError, ValueError, KeyError, TypeError, sqlite3.Error)


def reporting_failure(
    component: str,
    arguments: Any,
    error: Exception,
    *,
    stage: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Retain a content-free gap outside the collector DB, including after closure.

    If storage is also unavailable, the returned status and stderr notice remain
    truthful about that failure. Never claim missing measurements were recovered.
    """
    from archive_report_store import RunStore, atomic_json, now

    detail = {
        "status": "unavailable",
        "code": "archive_reporting_unavailable",
        "component": component,
        "stage": stage,
        "reason": type(error).__name__,
        "measurement_gap": True,
        "gap_saved": False,
        "retry_action": "retry_reporting_only",
    }
    try:
        if root is None:
            from archive_emit import _run_roots

            roots = _run_roots(arguments)
            if len(roots) == 1:
                root = roots.pop()
        if root is not None:
            # Do not recreate an unavailable/moved run as an empty directory.
            if not (root / "run.json").is_file():
                raise FileNotFoundError("The selected run is unavailable")
            run = json.loads((root / "run.json").read_text(encoding="utf-8"))
            closed = run["status"] in {"completed", "failed", "cancelled"}
            try:
                state = RunStore(root).state()
                closed = closed or bool(state and state["collection_closed"])
            except REPORTING_ERRORS:
                pass  # The independent run lifecycle still identifies terminal work.
            directory = "delivery-after-closure" if closed else "gaps"
            atomic_json(
                root / "reporting" / directory / (uuid4().hex + ".json"),
                {**detail, "gap_saved": True, "recorded_at": now()},
            )
            detail["gap_saved"] = True
    except REPORTING_ERRORS:
        pass  # The returned notice explicitly says the gap could not be saved.
    try:
        sys.stderr.write(json.dumps(detail, sort_keys=True) + "\n")
    except OSError:
        pass  # Callers can still deliver the separate structured reporting status.
    return detail


def isolated_projection(function):
    """Missing provenance stays unknown and cannot abort the owning producer."""

    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except REPORTING_ERRORS as error:
            component = args[0] if args else kwargs.get("component", "unknown")
            output = (
                args[1] if len(args) > 1 else kwargs.get("output", kwargs.get("path"))
            )
            reporting_failure(
                component,
                {"output": str(output)},
                error,
                stage=function.__name__,
            )
            return False if function.__name__ == "is_recording" else None

    return wrapped
