"""Private, durable collection for one Archive execution, independent of the agent.

Run identity, event deduplication and counts are mechanical evidence, not model
judgments. Raw tool content never goes to the receipt server.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Iterator

__all__ = [
    "canonical",
    "digest",
    "file_digest",
    "now",
    "private_directory",
    "atomic_json",
    "atomic_bytes",
    "run_lock",
    "serialized_run",
    "RunStore",
    "Registry",
]
_LOCKS: dict[str, Any] = {}
_LOCK_GUARD = threading.Lock()


@contextmanager
def run_lock(root: Path) -> Iterator[None]:
    """Serialize snapshots, hook records and retries across processes and threads."""
    directory = private_directory(root / "reporting")
    with _LOCK_GUARD:
        entry = _LOCKS.setdefault(
            str(directory), {"lock": threading.RLock(), "depth": 0}
        )
    with entry["lock"]:
        if entry["depth"]:
            yield
            return
        path = directory / "collection.lock"
        if path.is_symlink():
            raise ValueError("Collection lock cannot be a symbolic link")
        descriptor = os.open(
            path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError("Collection lock must be an ordinary unlinked file")
            if os.name == "nt":
                import msvcrt

                os.ftruncate(descriptor, 1)
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX)
            entry["depth"] = 1
            try:
                yield
            finally:
                entry["depth"] = 0
        finally:
            os.close(descriptor)


def serialized_run(function):
    """Use the exact Archive root for automatic collector operations."""

    @wraps(function)
    def wrapped(first, *args, **kwargs):
        if isinstance(first, dict) and "run" in first:
            from selective_reporting import report_pipeline

            if report_pipeline(first["run"]["workflow_id"]) is None:
                return function(first, *args, **kwargs)
        root = Path(first["run_root"]) if isinstance(first, dict) else Path(first)
        with run_lock(root):
            return function(first, *args, **kwargs)

    return wrapped


def canonical(value: Any) -> bytes:
    """Use one stable representation for local records and report hashes."""
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def digest(value: Any) -> str:
    """Hash the exact canonical report bytes, including the final newline."""
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path: Path) -> str:
    """Hash bounded chunks on the host's lightweight Python 3.9+ interpreter."""
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def now() -> str:
    """Return an unambiguous UTC event time."""
    return datetime.now(timezone.utc).isoformat()


def private_directory(path: Path) -> Path:
    """Reject symlinks before creating an owner-private local evidence directory."""
    path = path.expanduser().absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("Reporting paths cannot traverse symbolic links")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir():
        raise ValueError("Reporting directory is unavailable")
    return path


def atomic_json(path: Path, value: Any) -> None:
    """Persist a complete JSON snapshot without exposing partial writes."""
    atomic_bytes(path, canonical(value))


def atomic_bytes(path: Path, value: bytes) -> None:
    """Replace one ordinary local artifact with a complete, owner-private file."""
    import tempfile

    private_directory(path.parent)
    if path.is_symlink() or (
        path.exists() and (not path.is_file() or path.stat().st_nlink != 1)
    ):
        raise ValueError("Reporting file must be an ordinary private file")
    descriptor, name = tempfile.mkstemp(prefix=".report-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _database(path: Path) -> Iterator[sqlite3.Connection]:
    private_directory(path.parent)
    for item in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        if item.exists() or item.is_symlink():
            metadata = item.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError("Reporting database must be an ordinary private file")
    connection = sqlite3.connect(path, timeout=15)
    if os.name == "posix":
        path.chmod(0o600)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


class RunStore:
    """Keep collection durable alongside, but outside, sealed professional outputs."""

    def __init__(self, run_root: Path):
        self.root = private_directory(run_root / "reporting")
        self.path = self.root / "events.sqlite3"

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with _database(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, recorded_at TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS sources (source_id TEXT PRIMARY KEY, path TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            yield connection

    def state(self) -> dict[str, Any] | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT payload FROM state WHERE singleton=1"
            ).fetchone()
            return json.loads(row["payload"]) if row else None

    def save(self, state: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO state VALUES(1,?) ON CONFLICT(singleton) DO UPDATE SET payload=excluded.payload",
                (canonical(state).decode(),),
            )

    def error(self, reason: str) -> None:
        """Retain a collection failure without overwriting another hook's state."""
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT payload FROM state WHERE singleton=1"
            ).fetchone()
            if row:
                state = json.loads(row["payload"])
                state["errors"] = sorted(set(state["errors"]) | {reason})
                connection.execute(
                    "UPDATE state SET payload=? WHERE singleton=1",
                    (canonical(state).decode(),),
                )

    def event(self, event_id: str, payload: dict[str, Any]) -> None:
        """Identical hook retries are harmless; conflicting evidence is an error."""
        with self.transaction() as connection:
            old = connection.execute(
                "SELECT payload FROM events WHERE event_id=?", (event_id,)
            ).fetchone()
            encoded = canonical(payload).decode()
            if old and old["payload"] != encoded:
                raise ValueError(
                    "Reporting event identity was reused with different evidence"
                )
            connection.execute(
                "INSERT INTO events VALUES(?,?,?) ON CONFLICT(event_id) DO NOTHING",
                (event_id, now(), encoded),
            )

    def events(self) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            result = []
            for row in connection.execute(
                "SELECT event_id,recorded_at,payload FROM events ORDER BY recorded_at,event_id"
            ):
                payload = json.loads(row["payload"])
                payload.pop("local_response", None)
                result.append(
                    {
                        "event_id": row["event_id"],
                        "recorded_at": row["recorded_at"],
                        **payload,
                    }
                )
            return result

    def source(self, source: dict[str, Any]) -> None:
        with self.transaction() as connection:
            old = connection.execute(
                "SELECT payload FROM sources WHERE source_id=?", (source["source_id"],)
            ).fetchone()
            encoded = canonical(source).decode()
            if old and old["payload"] != encoded:
                raise ValueError("Registered reporting source bytes changed")
            connection.execute(
                "INSERT INTO sources VALUES(?,?,?) ON CONFLICT(source_id) DO NOTHING",
                (source["source_id"], source["path"], encoded),
            )

    def sources(self) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            return [
                json.loads(row["payload"])
                for row in connection.execute(
                    "SELECT payload FROM sources ORDER BY source_id"
                )
            ]


class Registry:
    """Bind observed host sessions to exact active runs without inspecting chats."""

    def __init__(self, directory: Path | None = None):
        configured = os.environ.get("VERA_REPORTING_STATE_DIR")
        self.path = (
            directory
            or (
                Path(configured).expanduser()
                if configured
                else Path.home() / ".mparanza/vera/reporting"
            )
        ) / "registry.sqlite3"

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with _database(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, run_root TEXT NOT NULL, active INTEGER NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS sessions (session_id TEXT NOT NULL, run_id TEXT NOT NULL, PRIMARY KEY(session_id,run_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS invocations (session_id TEXT NOT NULL, tool_id TEXT NOT NULL, run_id TEXT NOT NULL, PRIMARY KEY(session_id,tool_id,run_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS heartbeats (session_id TEXT PRIMARY KEY, at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS hosts (session_id TEXT PRIMARY KEY, transcript_path TEXT NOT NULL, host TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS receipt_queue (run_id TEXT PRIMARY KEY, status TEXT NOT NULL, checked_at TEXT NOT NULL)"
            )
            yield connection

    def register(self, run_id: str, root: Path, session_id: str | None = None) -> None:
        with self.transaction() as connection:
            old = connection.execute(
                "SELECT run_root FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if old and old["run_root"] != str(root):
                raise ValueError(
                    "Archive run identity is already bound to another directory"
                )
            connection.execute(
                "INSERT INTO runs VALUES(?,?,1) ON CONFLICT(run_id) DO UPDATE SET active=1",
                (run_id, str(root)),
            )
            pending = connection.execute(
                "SELECT DISTINCT session_id FROM invocations WHERE run_id=?", (run_id,)
            ).fetchall()
            sessions = {row["session_id"] for row in pending}
            if session_id:
                sessions.add(session_id)
            for session in sessions:
                connection.execute(
                    "INSERT INTO sessions VALUES(?,?) ON CONFLICT DO NOTHING",
                    (session, run_id),
                )
        from archive_report_transcript import attach

        for session in sessions:
            host = self.host(session)
            if host and host["host"] == "codex":
                attach(root, session, Path(host["transcript_path"]))

    def begin_tool(
        self,
        session_id: str,
        tool_id: str,
        run_ids: set[str],
        *,
        transcript_path: str | None = None,
        host: str = "claude",
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO heartbeats VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET at=excluded.at",
                (session_id, now()),
            )
            if transcript_path:
                connection.execute(
                    "INSERT INTO hosts VALUES(?,?,?) ON CONFLICT(session_id) DO UPDATE SET transcript_path=excluded.transcript_path,host=excluded.host",
                    (session_id, transcript_path, host),
                )
            if not run_ids:
                run_ids = {
                    row["run_id"]
                    for row in connection.execute(
                        "SELECT r.run_id FROM runs r JOIN sessions s ON s.run_id=r.run_id WHERE s.session_id=? AND r.active=1",
                        (session_id,),
                    )
                }
            for run_id in run_ids:
                connection.execute(
                    "INSERT INTO invocations VALUES(?,?,?) ON CONFLICT DO NOTHING",
                    (session_id, tool_id, run_id),
                )
                if connection.execute(
                    "SELECT 1 FROM runs WHERE run_id=? AND active=1", (run_id,)
                ).fetchone():
                    connection.execute(
                        "INSERT INTO sessions VALUES(?,?) ON CONFLICT DO NOTHING",
                        (session_id, run_id),
                    )

    def host(self, session_id: str) -> dict[str, str] | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT transcript_path,host FROM hosts WHERE session_id=?",
                (session_id,),
            ).fetchone()
            return dict(row) if row else None

    def pending_calls(self, run_id: str) -> dict[str, list[str]]:
        with self.transaction() as connection:
            result: dict[str, list[str]] = {}
            for row in connection.execute(
                "SELECT i.session_id,i.tool_id FROM invocations i LEFT JOIN hosts h ON h.session_id=i.session_id WHERE i.run_id=? AND (h.host IS NULL OR h.host!='codex')",
                (run_id,),
            ):
                result.setdefault(row["session_id"], []).append(row["tool_id"])
            return result

    def end_tool(self, session_id: str, tool_id: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "DELETE FROM invocations WHERE session_id=? AND tool_id=?",
                (session_id, tool_id),
            )

    def active(self, session_id: str, run_ids: set[str] | None = None) -> list[Path]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT r.run_id,r.run_root FROM runs r JOIN sessions s ON s.run_id=r.run_id WHERE s.session_id=? AND r.active=1",
                (session_id,),
            ).fetchall()
            return [
                Path(row["run_root"])
                for row in rows
                if (not run_ids or row["run_id"] in run_ids)
                and (Path(row["run_root"]) / "run.json").is_file()
                and not Path(row["run_root"]).is_symlink()
            ]

    def close(self, run_id: str) -> None:
        with self.transaction() as connection:
            connection.execute("UPDATE runs SET active=0 WHERE run_id=?", (run_id,))
            connection.execute(
                "INSERT INTO receipt_queue VALUES(?,'pending',?) ON CONFLICT DO NOTHING",
                (run_id, now()),
            )

    def terminal_runs(self) -> list[Path]:
        """Find written terminal transitions whose local collection did not finish."""
        with self.transaction() as connection:
            roots = [
                Path(row["run_root"])
                for row in connection.execute(
                    "SELECT run_root FROM runs WHERE active=1"
                )
            ]
        result = []
        for root in roots:
            path = root / "run.json"
            if path.is_symlink() or not path.is_file() or root.is_symlink():
                continue
            if json.loads(path.read_text())["status"] in {
                "completed",
                "failed",
                "cancelled",
            }:
                result.append(root)
                if len(result) == 3:
                    break
        return result

    def receipt_result(self, root: Path, status: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE receipt_queue SET status=?,checked_at=? WHERE run_id IN (SELECT run_id FROM runs WHERE run_root=?)",
                (status, now(), str(root)),
            )

    def pending_receipts(self) -> list[Path]:
        with self.transaction() as connection:
            return [
                Path(row["run_root"])
                for row in connection.execute(
                    "SELECT r.run_root FROM runs r JOIN receipt_queue q ON r.run_id=q.run_id WHERE r.active=0 AND q.status='pending' ORDER BY q.checked_at LIMIT 3"
                )
            ]
