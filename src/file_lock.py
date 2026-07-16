from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path
__all__ = ["FileLock", "lock_path_for"]


def lock_path_for(target: Path) -> Path:
    """Return the lock file path associated with ``target``."""
    target = Path(target)
    suffix = target.suffix or ""
    lock_name = target.name + ".lock" if not suffix else target.stem + suffix + ".lock"
    return target.with_name(lock_name)


class FileLock:
    """Cross-platform advisory file lock using a companion ``.lock`` file."""

    def __init__(self, target: Path, *, timeout: float | None = None, poll: float = 0.1):
        self._target = Path(target)
        self._lock_path = lock_path_for(self._target)
        self._timeout = timeout
        self._poll = poll
        self._fh: object | None = None

    def __enter__(self) -> "FileLock":
        deadline = None if self._timeout is None else time.monotonic() + self._timeout
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            fh = self._lock_path.open("a+b")
            try:
                _acquire_lock(fh)
            except BlockingIOError:
                fh.close()
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Timed out acquiring lock for {self._target}"
                    ) from None
                time.sleep(self._poll)
                continue
            self._fh = fh
            return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fh is None:
            return
        try:
            _release_lock(self._fh)
        finally:
            with contextlib.suppress(Exception):
                self._fh.close()
            self._fh = None


def _acquire_lock(fh) -> None:
    if os.name == "nt":
        import msvcrt

        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:  # pragma: no cover - dependent on OS
            raise BlockingIOError from exc
    else:
        import fcntl

        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise


def _release_lock(fh) -> None:
    if os.name == "nt":
        import msvcrt

        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
