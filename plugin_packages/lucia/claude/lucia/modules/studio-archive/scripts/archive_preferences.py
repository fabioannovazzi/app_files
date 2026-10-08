"""Owner-private archive discovery, separate from session-owned configuration."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from threading import RLock, local
from typing import Any, Iterator

__all__ = ["PROFILE_ENV", "profile_directory", "read_json", "registry_lock"]
PROFILE_ENV = "VERA_STUDIO_ARCHIVE_PROFILE_DIR"
_LOCK = RLock()
_HELD = local()


def profile_directory(state: Path) -> Path | None:
    """Explicit test/operator state stays isolated unless a profile is selected."""
    selected = os.environ.get(PROFILE_ENV, "").strip()
    default = Path.home() / ".mparanza" / "vera-studio-archive"
    if selected:
        profile = Path(selected).expanduser()
    elif state.parent == default / "sessions":
        profile = default / "profile"
    else:
        return None
    if not profile.is_absolute():
        raise ValueError("Archive profile directory must be absolute.")
    for parent in (profile, *profile.parents):
        if parent.is_symlink():
            raise ValueError("Archive profile cannot contain symbolic links.")
    if profile.exists():
        if not profile.is_dir():
            raise ValueError("Archive profile must be a directory.")
        if os.name == "posix" and stat.S_IMODE(profile.stat().st_mode) & 0o077:
            raise ValueError("Archive profile must be owner-private.")
    return profile


def read_json(path: Path) -> dict[str, Any] | None:
    """Read only a bounded, owner-private, single-link profile record."""
    if not path.exists() and not path.is_symlink():
        return None
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError("Archive profile record cannot have symlink ancestors.")
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > 8 * 1024 * 1024
        or (os.name == "posix" and stat.S_IMODE(before.st_mode) & 0o077)
    ):
        raise ValueError("Archive profile record must be bounded and owner-private.")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            content = handle.read(before.st_size + 1)
            after = os.fstat(handle.fileno())
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mtime_ns,
            value.st_nlink,
        )
        if (
            identity(before) != identity(opened)
            or identity(before) != identity(after)
            or len(content) != before.st_size
        ):
            raise ValueError("Archive profile record changed while being read.")
        payload = json.loads(content)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Archive profile record is unreadable.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Archive profile record must be an object.")
    return payload


@contextmanager
def registry_lock(profile: Path, archive_root: Path) -> Iterator[Path]:
    """Serialize root-specific identity read/modify/write, never session selection."""
    root_key = hashlib.sha256(str(archive_root).encode()).hexdigest()
    directory = profile / "archives" / root_key
    with _LOCK:
        held = getattr(_HELD, "paths", set())
        if directory in held:
            yield directory
            return
        for parent in (directory, directory.parent):
            if parent.is_symlink():
                raise ValueError("Archive identity storage cannot be a symbolic link.")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.parent.chmod(0o700)
        directory.chmod(0o700)
        lock_path = directory / ".identities.lock"
        if lock_path.is_symlink():
            raise ValueError("Archive identity lock cannot be a symbolic link.")
        descriptor = os.open(
            lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        try:
            observed = os.fstat(descriptor)
            if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
                raise ValueError("Archive identity lock must be an ordinary file.")
            if os.name == "nt":
                import msvcrt

                os.write(descriptor, b"0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _HELD.paths = held | {directory}
            try:
                yield directory
            finally:
                _HELD.paths = held
        finally:
            os.close(descriptor)
