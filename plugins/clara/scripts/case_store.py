"""Serialized, recoverable writes for case-owned state.

A disk undo journal is committed before mutation, so process death can be
recovered on the next operation. The lock serializes cooperating local writers;
this does not claim transactions for arbitrary external files or manual edits.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
import threading
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterator, TypeVar

__all__ = [
    "atomic_bytes",
    "atomic_stream",
    "atomic_text",
    "case_operation",
    "case_reader",
    "track_write",
    "transaction",
]

_STATE = threading.local()
F = TypeVar("F", bound=Callable[..., Any])


def _sync_directory(path: Path) -> None:
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _raw_write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Case write target is a symbolic link: {path}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        _sync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _safe_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Unsafe case transaction path")
    path = root / candidate
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError("Case transaction path is a symbolic link")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Case transaction path escapes case")
    return path


def _raw_stream(path: Path, source: BinaryIO) -> None:
    """Replace one file from a bounded stream without buffering its full content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Case write target is a symbolic link: {path}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as restored:
            temporary = Path(restored.name)
            shutil.copyfileobj(source, restored)
            restored.flush()
            os.fsync(restored.fileno())
        temporary.replace(path)
        _sync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _restore_file(path: Path, source: Path) -> None:
    """Restore a preimage without enlisting recovery in another transaction."""
    with source.open("rb") as original:
        _raw_stream(path, original)


def atomic_stream(path: Path, source: BinaryIO) -> None:
    """Enlist and atomically write a stream, retaining no complete in-memory copy."""
    track_write(path)
    _raw_stream(path, source)


def _recover(root: Path, journal: Path) -> None:
    if not journal.exists():
        return
    if journal.is_symlink():
        raise ValueError("Case transaction journal is a symbolic link")
    manifest = journal / "journal.json"
    if manifest.is_symlink() or (journal / "committed").is_symlink():
        raise ValueError("Case transaction marker is a symbolic link")
    if manifest.exists() and not (journal / "committed").exists():
        records = json.loads(manifest.read_text())
        for relative, backup in records.items():
            path = _safe_path(root, relative)
            if backup is None:
                path.unlink(missing_ok=True)
                if path.parent.exists():
                    _sync_directory(path.parent)
            else:
                source = _safe_path(journal, backup)
                _restore_file(path, source)
    shutil.rmtree(journal)
    _sync_directory(root)


def track_write(path: Path) -> None:
    """Persist an undo record before changing one case-owned file."""
    active = getattr(_STATE, "active", {})
    for root, (journal, records) in active.items():
        absolute = path.absolute()
        owner = next(
            (parent for parent in absolute.parents if parent.resolve() == root),
            None,
        )
        if owner is None:
            if absolute.resolve().is_relative_to(root):
                raise ValueError("Case write must use the case root or its root alias")
            continue
        # Preserve relative components so links *inside* the case still fail
        # _safe_path; resolve only the root alias (for example macOS /tmp).
        relative = absolute.relative_to(owner).as_posix()
        target = _safe_path(root, relative)
        if relative in records:
            return
        backup = None
        if target.exists():
            if not target.is_file():
                raise ValueError("Case transaction target must be a file")
            backup = f"{len(records)}.original"
            # Stream large prior artifacts to disk rather than snapshot the tree in RAM.
            with (
                target.open("rb") as source,
                (journal / backup).open("xb") as destination,
            ):
                shutil.copyfileobj(source, destination)
                destination.flush()
                os.fsync(destination.fileno())
        records[relative] = backup
        _raw_write(journal / "journal.json", json.dumps(records).encode())
        return


def atomic_bytes(path: Path, value: bytes) -> int:
    """Write exact bytes atomically and enlist case-owned files in the journal."""
    track_write(path)
    _raw_write(path, value)
    return len(value)


def atomic_text(path: Path, value: str, *, encoding: str = "utf-8") -> int:
    atomic_bytes(path, value.encode(encoding))
    return len(value)


@contextmanager
def transaction(case_dir: Path) -> Iterator[None]:
    """Serialize writers and recover an interrupted operation before resuming."""
    root = case_dir.resolve()
    active = getattr(_STATE, "active", {})
    if root in active:
        yield
        return
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".clara.lock"
    fd = os.open(
        lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or lock_path.is_symlink()
        ):
            raise ValueError("Case lock must be an ordinary single-link file")
        if os.name == "nt":
            import msvcrt

            if info.st_size == 0:
                os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
        journal = root / ".clara-transaction"
        _recover(root, journal)
        journal.mkdir(mode=0o700)
        _sync_directory(root)
        _STATE.active = {**active, root: (journal, {})}
        complete = False
        try:
            yield
            _raw_write(journal / "committed", b"committed\n")
            complete = True
        finally:
            _STATE.active = active
            # Recovery rolls back incomplete operations; committed journals only clean up.
            if complete or journal.exists():
                _recover(root, journal)
    finally:
        os.close(fd)


def case_operation(function: F) -> F:
    """Wrap a public operation whose first argument is its case directory."""

    @wraps(function)
    def wrapped(case_dir: Path, *args: Any, **kwargs: Any) -> Any:
        with transaction(case_dir):
            return function(case_dir.resolve(), *args, **kwargs)

    return wrapped  # type: ignore[return-value]


def case_reader(function: F) -> F:
    """Read one consistent state, recovering a crashed writer before inspection."""

    @wraps(function)
    def wrapped(case_dir: Path, *args: Any, **kwargs: Any) -> Any:
        if not case_dir.is_dir():
            return function(case_dir, *args, **kwargs)
        with transaction(case_dir):
            return function(case_dir.resolve(), *args, **kwargs)

    return wrapped  # type: ignore[return-value]
