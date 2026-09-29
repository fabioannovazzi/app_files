"""Transactional revision log for a native Studio Archive construction run."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from construction_core import apply_event, digest, require, verify_snapshot

__all__ = ["CaseStore", "RevisionConflict"]


class RevisionConflict(ValueError):
    """An optimistic revision or idempotency key conflicts with saved work."""


class CaseStore:
    """Use SQLite transactions for atomic, non-overwriting local revisions."""

    def __init__(self, path: Path, *, client_id: str, engagement_id: str):
        require(not path.is_symlink(), "Case database must not be a symlink")
        self.path = path
        self.client_id = client_id
        self.engagement_id = engagement_id

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        require(not self.path.is_symlink(), "Case database must not be a symlink")
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self.path.chmod(0o600)
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS revisions (revision INTEGER PRIMARY KEY, snapshot TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS requests (request_id TEXT PRIMARY KEY, body_hash TEXT NOT NULL, revision INTEGER NOT NULL)"
        )
        return connection

    def _verify(self, state: dict) -> dict:
        verify_snapshot(state)
        require(
            state["client_id"] == self.client_id
            and state["engagement_id"] == self.engagement_id,
            "Construction case belongs to another client or engagement",
        )
        return state

    def initialize(self, state: dict) -> dict:
        """Seed a new run from a new case or an exactly imported prior snapshot."""
        self._verify(state)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT snapshot FROM revisions ORDER BY revision DESC LIMIT 1"
            ).fetchone()
            if row:
                existing = self._verify(json.loads(row[0]))
                require(
                    existing["case_id"] == state["case_id"],
                    "Another construction case already exists",
                )
                connection.commit()
                return existing
            connection.execute(
                "INSERT INTO revisions VALUES (?, ?)",
                (
                    state["revision"],
                    json.dumps(state, ensure_ascii=False, allow_nan=False),
                ),
            )
            connection.commit()
            return state
        finally:
            connection.close()

    def read(self, revision: int | None = None) -> dict:
        """Read and verify an immutable historical revision or the current head."""
        require(self.path.is_file(), "Construction case has not been opened")
        connection = self._connect()
        try:
            row = (
                connection.execute(
                    "SELECT snapshot FROM revisions ORDER BY revision DESC LIMIT 1"
                ).fetchone()
                if revision is None
                else connection.execute(
                    "SELECT snapshot FROM revisions WHERE revision=?", (revision,)
                ).fetchone()
            )
            require(row is not None, "Construction revision not found")
            return self._verify(json.loads(row[0]))
        finally:
            connection.close()

    def commit(
        self,
        event: dict,
        *,
        request_id: str,
        expected_revision: int,
        actor: str,
        at: str,
    ) -> dict:
        """Compare-and-append; identical retries return their original revision."""
        require(
            isinstance(request_id, str) and bool(request_id.strip()),
            "Missing request ID",
        )
        require(
            type(expected_revision) is int and expected_revision >= 0,
            "Invalid expected revision",
        )
        body_hash = digest(
            {
                "event": event,
                "actor": actor,
                "at": at,
                "expected_revision": expected_revision,
            }
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            seen = connection.execute(
                "SELECT body_hash, revision FROM requests WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if seen:
                if seen[0] != body_hash:
                    raise RevisionConflict(
                        "Request ID was already used with a different body"
                    )
                saved = connection.execute(
                    "SELECT snapshot FROM revisions WHERE revision=?", (seen[1],)
                ).fetchone()
                return self._verify(json.loads(saved[0]))
            row = connection.execute(
                "SELECT snapshot FROM revisions ORDER BY revision DESC LIMIT 1"
            ).fetchone()
            require(row is not None, "Construction case has not been opened")
            state = self._verify(json.loads(row[0]))
            if expected_revision != state["revision"]:
                raise RevisionConflict(
                    "Construction revision conflict; compare the current snapshot before retrying"
                )
            result = apply_event(state, event, actor=actor, at=at)
            connection.execute(
                "INSERT INTO revisions VALUES (?, ?)",
                (
                    result["revision"],
                    json.dumps(result, ensure_ascii=False, allow_nan=False),
                ),
            )
            connection.execute(
                "INSERT INTO requests VALUES (?, ?, ?)",
                (request_id, body_hash, result["revision"]),
            )
            connection.commit()
            return result
        finally:
            connection.close()
