"""Persist media attempt state and retain failed stage evidence under a run lock."""

from __future__ import annotations

import json
import os
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from case_store import atomic_text

__all__ = ["media_attempt"]


def _write(path: Path, payload: dict[str, Any]) -> None:
    atomic_text(path, json.dumps(payload, indent=2) + "\n")


@contextmanager
def media_attempt(root: Path) -> Iterator[Path]:
    """Serialize attempts and retain state even when rendering raises."""
    if not root.is_dir():
        raise ValueError("Media run directory does not exist")
    lock = root / ".media-render.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or lock.is_symlink():
            raise ValueError("Media render lock must be an ordinary single-link file")
        if os.name == "nt":
            import msvcrt

            if info.st_size == 0:
                os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
        attempts = root / ".render-attempts"
        if attempts.is_symlink():
            raise ValueError("Media attempt directory must not be a symbolic link")
        attempts.mkdir(exist_ok=True)
        receipt_path = root / "render_attempt.json"
        if receipt_path.is_file():
            previous = json.loads(receipt_path.read_text(encoding="utf-8"))
            if previous.get("status") == "running":
                previous["status"] = "interrupted"
                _write(attempts / f"recovered-{uuid.uuid4().hex}.json", previous)
        attempt_id = uuid.uuid4().hex
        work = attempts / attempt_id
        work.mkdir()
        for name in (
            "render_report.json",
            "final_artifacts.json",
            "current_render.json",
        ):
            path = root / name
            if path.is_file():
                atomic_text(work / f"previous-{name}", path.read_text(encoding="utf-8"))
        receipt = {
            "schema_version": 1,
            "attempt_id": attempt_id,
            "status": "running",
            "stage_directory": str(work),
        }
        _write(receipt_path, receipt)
        _write(root / "current_render.json", receipt)
        try:
            yield work
        except BaseException as exc:
            receipt.update(
                status="failed_or_interrupted",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            _write(root / "current_render.json", receipt)
            for name in ("render_report.json", "final_artifacts.json"):
                _write(
                    root / name,
                    {**receipt, "outputs": [], "historical_evidence": str(work)},
                )
            raise
        else:
            receipt["status"] = "completed"
        finally:
            _write(work / "attempt.json", receipt)
            _write(receipt_path, receipt)
    finally:
        os.close(fd)
