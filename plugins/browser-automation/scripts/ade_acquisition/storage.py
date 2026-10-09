"""Private, crash-resumable acquisition storage and verified original reuse."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from .artifacts import MAX_BYTES
from .contracts import AcquisitionError, Client, safe_name

__all__ = ["Store", "atomic_json", "private_root", "read_json"]


def private_root(path: Path) -> Path:
    """Prevent business output inside source repositories or through linked paths."""
    path = path.expanduser().absolute()
    for parent in (path, *path.parents):
        if parent.is_symlink() or (parent / ".git").exists():
            raise AcquisitionError("output-must-be-private-outside-git")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir():
        raise AcquisitionError("output-not-directory")
    return path


def _ordinary(path: Path) -> bool:
    try:
        info = path.lstat()
        return stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    except FileNotFoundError:
        return False


def atomic_json(path: Path, payload: Any) -> None:
    """Write one complete durable snapshot; interruption cannot truncate prior state."""
    if path.exists() and not _ordinary(path):
        raise AcquisitionError("state-file-unsafe")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> Any:
    if not _ordinary(path):
        raise AcquisitionError("state-file-missing-or-unsafe")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise AcquisitionError("state-file-corrupt") from exc


class Store:
    """One archive index with per-run evidence and explicit file validation."""

    def __init__(self, root: Path) -> None:
        self.root = private_root(root)
        self.database = self.root / "acquisition.sqlite3"
        if self.database.exists() and not _ordinary(self.database):
            raise AcquisitionError("archive-index-unsafe")

    @contextmanager
    def lock(self) -> Iterator[None]:
        """OS-released lock prevents concurrent workers and stale lock-file blockers."""
        path = self.root / ".worker.lock"
        if path.exists() and not _ordinary(path):
            raise AcquisitionError("worker-lock-unsafe")
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        handle = os.fdopen(descriptor, "r+b")
        try:
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                if sys.platform == "win32":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise AcquisitionError("acquisition-already-running") from exc
            yield
        finally:
            handle.close()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=10)
        try:
            self.database.chmod(0o600)
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS files (
                client TEXT NOT NULL, category TEXT NOT NULL, portal_key TEXT NOT NULL,
                record TEXT NOT NULL, PRIMARY KEY(client, category, portal_key))"""
            )
            yield connection
            connection.commit()
        finally:
            connection.close()

    def safe_path(self, relative: str) -> Path:
        candidate = self.root / relative
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise AcquisitionError("artifact-path-invalid")
        for parent in (candidate, *candidate.parents):
            if parent == self.root:
                break
            if parent.is_symlink():
                raise AcquisitionError("artifact-path-unsafe")
        return candidate

    def verified(self, record: dict[str, Any]) -> bool:
        for item in record["artifacts"]:
            path = self.safe_path(item["path"])
            if not _ordinary(path):
                return False
            size = path.stat().st_size
            if size != item["byte_length"] or not 0 < size <= MAX_BYTES:
                return False
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                return False
        return bool(record["artifacts"])

    def lookup(
        self, client: Client, category: str, portal_key: str
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT record FROM files WHERE client=? AND category=? AND portal_key=?",
                (client.vat_number, category, portal_key),
            ).fetchone()
        if row is None:
            return None
        try:
            record = json.loads(row[0])
            return record if self.verified(record) else None
        except (KeyError, TypeError, ValueError) as exc:
            raise AcquisitionError("archive-index-corrupt") from exc

    def retain(
        self,
        client: Client,
        category: str,
        portal_key: str,
        year: int,
        quarter: int,
        filename: str,
        data: bytes,
        evidence: dict[str, Any],
        xml: bytes | None = None,
    ) -> dict[str, Any]:
        directory = (
            self.root
            / f"{safe_name(client.name)}__{client.vat_number}"
            / str(year)
            / category
            / f"{quarter}_Trimestre"
            / uuid4().hex
        )
        private_root(directory)
        record = {**evidence, "portal_key": portal_key, "artifacts": []}
        payloads = [(safe_name(filename), data)]
        if xml is not None:
            payloads.append(("contenuto_fattura.xml", xml))
        for index, (name, content) in enumerate(payloads):
            path = directory / f"{index}_{name}"
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            record["artifacts"].append(
                {
                    "path": path.relative_to(self.root).as_posix(),
                    "byte_length": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO files VALUES(?,?,?,?)",
                (client.vat_number, category, portal_key, json.dumps(record)),
            )
        return record

    def new_run(self, plan: dict[str, Any]) -> Path:
        directory = self.root / "runs" / uuid4().hex
        private_root(directory)
        atomic_json(directory / "plan.json", plan)
        return directory
