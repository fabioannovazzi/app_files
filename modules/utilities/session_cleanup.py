from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

SESSION_DIRS: Dict[str, Path] = {
    "check_entries": Path("tmp") / "check_entries_sessions",
    "check_statements": Path("tmp") / "check_statements_sessions",
    "conversation": Path("tmp") / "conversation_sessions",
    "session_context": Path("tmp") / "session_context_sessions",
}


def _iter_session_files(directory: Path) -> Iterable[Path]:
    if not directory.exists():
        return []
    files = list(directory.glob("*.pkl"))
    files.extend(directory.glob("*.tmp"))
    return files


def cleanup_sessions(
    retention_hours: float,
    *,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
) -> Tuple[int, int]:
    """
    Remove session files older than the configured retention window.

    Returns a tuple of (removed, scanned).
    """

    cutoff = time.time() - retention_hours * 3600
    removed = 0
    scanned = 0
    for name, directory in SESSION_DIRS.items():
        for path in _iter_session_files(directory):
            scanned += 1
            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                continue
            if mtime >= cutoff:
                continue
            message = f"Deleting stale {name} session {path}"
            if dry_run:
                if logger:
                    logger.info("[dry-run] %s", message)
                else:
                    print(f"[dry-run] {message}")
                removed += 1
                continue
            try:
                path.unlink()
                if logger:
                    logger.info(
                        "%s (age %.1f h)", message, (time.time() - mtime) / 3600
                    )
                removed += 1
            except OSError as exc:
                if logger:
                    logger.warning("Failed to delete %s: %s", path, exc)
                else:
                    print(f"Failed to delete {path}: {exc}")
    return removed, scanned
