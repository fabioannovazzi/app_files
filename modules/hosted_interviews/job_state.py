"""Durable post-call task state; unknown provider outcomes are never auto-replayed.

Exact stage identity and an existing cross-worker lock distinguish active work
from interrupted work without making judgments about interview quality.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "AUDIO_WORK_DIRECTORY",
    "JOB_FILENAME",
    "inspect_job",
    "queue_job",
    "run_job",
]
AUDIO_WORK_DIRECTORY = ".post-call-audio"
JOB_FILENAME = "post_completion_job.json"
LockFactory = Callable[[Path], AbstractContextManager[bool]]


def _clean_audio_work(directory: Path) -> None:
    """Remove only owned assembly copies while the caller holds the job lock."""
    workspace = directory / AUDIO_WORK_DIRECTORY
    if workspace.is_symlink():
        raise OSError("Interview audio workspace must not be a symbolic link")
    if workspace.exists():
        shutil.rmtree(workspace)


def _read(directory: Path) -> dict[str, Any]:
    path = directory / JOB_FILENAME
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write(directory: Path, state: dict[str, Any]) -> None:
    path = directory / JOB_FILENAME
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=directory, delete=False
    ) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def queue_job(directory: Path, *, attempt_id: str, stage: str) -> dict[str, Any]:
    """Persist acknowledgment state under the caller's completion lock."""
    state = {
        "schema_version": 1,
        "attempt_id": attempt_id,
        "stage": stage,
        "status": "queued",
        "owner_pid": os.getpid(),
        "owner_host": socket.gethostname(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write(directory, state)
    return state


def _interrupt(directory: Path, state: dict[str, Any]) -> dict[str, Any]:
    state.update(
        status="interrupted",
        updated_at=datetime.now(timezone.utc).isoformat(),
        message="Post-call processing was interrupted. Saved transcripts and results remain available. Review those results before requesting another provider call; no automatic retry was made.",
    )
    _write(directory, state)
    return state


def inspect_job(directory: Path, *, lock: LockFactory) -> dict[str, Any]:
    """Report an abandoned queue/worker explicitly without replaying provider work."""
    with lock(directory) as acquired:
        if acquired:
            _clean_audio_work(directory)
        state = _read(directory)
        if not acquired or state.get("status") not in {"queued", "running"}:
            return state
        if state["status"] == "running":
            return _interrupt(directory, state)
        owner_alive = False
        if state.get("owner_host") == socket.gethostname():
            try:
                pid = int(state["owner_pid"])
                if pid <= 0:
                    raise ValueError("Invalid owner process")
                # Windows kill(0) does not provide the Unix existence probe.
                if os.name != "nt":
                    os.kill(pid, 0)
                owner_alive = True
            except (ProcessLookupError, ValueError, KeyError):
                pass
            except PermissionError:
                owner_alive = True
        age = (
            datetime.now(timezone.utc) - datetime.fromisoformat(state["updated_at"])
        ).total_seconds()
        if (
            state.get("owner_host") == socket.gethostname() and not owner_alive
        ) or age > 300:
            return _interrupt(directory, state)
        return state


def run_job(directory: Path, action: Callable[[], None], *, lock: LockFactory) -> bool:
    """Run one queued action under its lock; retain terminal state across restarts."""
    with lock(directory) as acquired:
        if not acquired:
            return False
        _clean_audio_work(directory)
        state = _read(directory)
        if state.get("status") in {"completed", "failed", "interrupted"}:
            return False
        if state.get("status") == "running":
            _interrupt(directory, state)
            return False
        state.update(
            status="running",
            owner_pid=os.getpid(),
            owner_host=socket.gethostname(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        _write(directory, state)
        completed = False
        try:
            action()
            completed = True
        finally:
            _clean_audio_work(directory)
            state.update(
                status="completed" if completed else "failed",
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            if not completed:
                state["message"] = (
                    "Post-call processing failed; inspect saved results before requesting a retry."
                )
            _write(directory, state)
    return True
