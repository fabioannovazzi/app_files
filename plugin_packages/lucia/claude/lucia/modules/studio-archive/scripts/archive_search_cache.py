"""Owner-private, root-bound search cache shared by product sessions."""

from __future__ import annotations

import os
import sqlite3
import stat
import tempfile
from contextlib import closing
from pathlib import Path
from threading import RLock

import archive_preferences as preferences

__all__ = ["database_path"]
_MUTEX = RLock()
_FILENAME = "archive.sqlite3"


def _private_file(path: Path) -> bool:
    if any(part.is_symlink() for part in (path, *path.parents)):
        return False
    try:
        info = path.stat()
        return (
            stat.S_ISREG(info.st_mode)
            and info.st_nlink == 1
            and (
                os.name != "posix"
                or (
                    info.st_uid == os.geteuid()
                    and not stat.S_IMODE(info.st_mode) & 0o077
                )
            )
        )
    except OSError:
        return False


def _legacy_metadata(path: Path, root: Path, schema: str) -> str | None:
    """Inspect only index metadata; never adopt session configuration or work."""
    if not _private_file(path):
        return None
    try:
        with closing(
            sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
        ) as connection:
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
            if (
                metadata.get("archive_root") != str(root)
                or metadata.get("schema_version") != schema
            ):
                return None
            return metadata.get("last_refresh_at")
    except sqlite3.Error:
        return None


def database_path(directory: Path, state: Path, root: Path, schema: str) -> Path:
    """Migrate one compatible legacy SQLite snapshot once, without extraction."""
    target = directory / _FILENAME
    if target.exists() or target.is_symlink():
        if not _private_file(target):
            raise ValueError(
                "Archive search index must be an ordinary owner-private file."
            )
        return target
    with _MUTEX:
        # mkdir(parents=True) applies its mode only to the leaf. Create each
        # private profile level explicitly, including a newly selected profile.
        for parent in (directory.parent.parent, directory.parent, directory):
            if parent.is_symlink():
                raise ValueError(
                    "Archive search storage cannot contain symbolic links."
                )
            parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name == "posix":
                parent.chmod(0o700)
        with preferences.file_lock(
            directory / ".index-migration.lock", label="search migration"
        ):
            if target.exists():
                if not _private_file(target):
                    raise ValueError("Archive search index is not owner-private.")
                return target
            candidates = [state / _FILENAME]
            # Only the selected product's default sessions are eligible. Explicit
            # operator/test directories never discover neighboring session state.
            sessions = preferences.default_state_directory() / "sessions"
            if (
                state.parent == sessions
                and sessions.is_dir()
                and not sessions.is_symlink()
            ):
                candidates.extend(sessions.glob(f"*/{_FILENAME}"))
            valid = [
                (stamp, path)
                for path in set(candidates)
                if (stamp := _legacy_metadata(path, root, schema))
            ]
            for _, legacy in sorted(valid, reverse=True):
                descriptor, name = tempfile.mkstemp(
                    prefix=".index-", suffix=".sqlite3", dir=directory
                )
                os.close(descriptor)
                temporary = Path(name)
                try:
                    source = sqlite3.connect(f"{legacy.as_uri()}?mode=ro", uri=True)
                    destination = sqlite3.connect(temporary)
                    try:
                        source.backup(destination)
                    finally:
                        destination.close()
                        source.close()
                    # Validate the actual snapshot, including a concurrent writer.
                    if _legacy_metadata(temporary, root, schema) is None:
                        continue
                    os.replace(temporary, target)
                    break
                finally:
                    temporary.unlink(missing_ok=True)
    return target
