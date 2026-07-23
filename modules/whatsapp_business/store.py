"""Durable, tenant-scoped storage for WhatsApp Business messages and OAuth."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import psycopg

from modules.pdp.postgres_compat import (
    DICT_ROW_FACTORY,
    PostgresCommitStateUnknownError,
    connect_pdp_database,
    is_postgres_enabled,
)

__all__ = [
    "IncomingWhatsAppMessage",
    "OAuthClient",
    "OAuthClientRegistrationLimitError",
    "OAuthIdentity",
    "WhatsAppAccount",
    "WhatsAppBusinessStore",
    "WhatsAppBusinessStoreError",
    "WhatsAppBusinessStoreUnavailableError",
    "WhatsAppMessage",
    "get_whatsapp_business_store",
]

_MAX_SEARCH_RESULTS = 20
_MAX_OAUTH_CLIENTS = 500
_OAUTH_CLIENT_IDLE_DAYS = 30
_OAUTH_CLIENT_REGISTRY_LOCK_ID = 7_642_907_109
_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS mparanza_whatsapp_accounts (
        owner_key TEXT PRIMARY KEY,
        waba_id TEXT NOT NULL,
        phone_number_id TEXT NOT NULL UNIQUE,
        display_phone_number TEXT NOT NULL,
        label TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mparanza_whatsapp_messages (
        source_id TEXT PRIMARY KEY,
        message_id TEXT NOT NULL UNIQUE,
        owner_key TEXT NOT NULL,
        phone_number_id TEXT NOT NULL,
        sender_phone TEXT NOT NULL,
        sender_name TEXT,
        occurred_at TEXT NOT NULL,
        message_type TEXT NOT NULL,
        body TEXT NOT NULL,
        reply_to_message_id TEXT,
        media_id TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (owner_key) REFERENCES mparanza_whatsapp_accounts(owner_key)
            ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS mparanza_whatsapp_messages_owner_sender_time
    ON mparanza_whatsapp_messages (owner_key, sender_phone, occurred_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS mparanza_whatsapp_oauth_clients (
        client_id TEXT PRIMARY KEY,
        client_name TEXT NOT NULL,
        redirect_uris_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_used_at TEXT NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS mparanza_whatsapp_oauth_clients_redirects
    ON mparanza_whatsapp_oauth_clients (redirect_uris_json)
    """,
    """
    CREATE TABLE IF NOT EXISTS mparanza_whatsapp_oauth_codes (
        code_hash TEXT PRIMARY KEY,
        client_id TEXT NOT NULL,
        owner_key TEXT NOT NULL,
        redirect_uri TEXT NOT NULL,
        resource TEXT NOT NULL,
        scope TEXT NOT NULL,
        code_challenge TEXT NOT NULL,
        expires_at INTEGER NOT NULL,
        consumed_at INTEGER,
        FOREIGN KEY (client_id) REFERENCES mparanza_whatsapp_oauth_clients(client_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS mparanza_whatsapp_oauth_codes_expiry
    ON mparanza_whatsapp_oauth_codes (expires_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS mparanza_whatsapp_oauth_tokens (
        token_hash TEXT PRIMARY KEY,
        client_id TEXT NOT NULL,
        owner_key TEXT NOT NULL,
        resource TEXT NOT NULL,
        scope TEXT NOT NULL,
        expires_at INTEGER NOT NULL,
        revoked_at INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY (client_id) REFERENCES mparanza_whatsapp_oauth_clients(client_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS mparanza_whatsapp_oauth_tokens_expiry
    ON mparanza_whatsapp_oauth_tokens (expires_at)
    """,
)


class WhatsAppBusinessStoreError(RuntimeError):
    """Base error for connector persistence."""


class WhatsAppBusinessStoreUnavailableError(WhatsAppBusinessStoreError):
    """Raised when durable storage cannot complete an operation."""


class OAuthClientRegistrationLimitError(WhatsAppBusinessStoreError):
    """Raised when the bounded public OAuth client registry is full."""


@dataclass(frozen=True, slots=True)
class WhatsAppAccount:
    """One WhatsApp Business phone number linked to one owner."""

    owner_key: str
    waba_id: str
    phone_number_id: str
    display_phone_number: str
    label: str
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class IncomingWhatsAppMessage:
    """Normalized message accepted from a verified Meta webhook."""

    message_id: str
    phone_number_id: str
    sender_phone: str
    sender_name: str | None
    occurred_at: str
    message_type: str
    body: str
    reply_to_message_id: str | None = None
    media_id: str | None = None


@dataclass(frozen=True, slots=True)
class WhatsAppMessage:
    """One stored message returned through the read-only connector."""

    source_id: str
    message_id: str
    owner_key: str
    phone_number_id: str
    sender_phone: str
    sender_name: str | None
    occurred_at: str
    message_type: str
    body: str
    reply_to_message_id: str | None
    media_id: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class OAuthClient:
    """Registered public OAuth client."""

    client_id: str
    client_name: str
    redirect_uris: tuple[str, ...]
    created_at: str


@dataclass(frozen=True, slots=True)
class OAuthIdentity:
    """Tenant identity resolved from a valid bearer token."""

    client_id: str
    owner_key: str
    resource: str
    scopes: frozenset[str]
    expires_at: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _retention_cutoff(retention_days: int) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(days=max(retention_days, 1)))
        .replace(microsecond=0)
        .isoformat()
    )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _configured_sqlite_path() -> Path | None:
    configured = os.getenv("WHATSAPP_DB_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    return None


def _row_values(row: Mapping[str, Any] | sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _account_from_row(row: Mapping[str, Any] | sqlite3.Row) -> WhatsAppAccount:
    values = _row_values(row)
    return WhatsAppAccount(
        owner_key=str(values["owner_key"]),
        waba_id=str(values["waba_id"]),
        phone_number_id=str(values["phone_number_id"]),
        display_phone_number=str(values["display_phone_number"]),
        label=str(values["label"]),
        active=bool(values["active"]),
        created_at=str(values["created_at"]),
        updated_at=str(values["updated_at"]),
    )


def _message_from_row(row: Mapping[str, Any] | sqlite3.Row) -> WhatsAppMessage:
    values = _row_values(row)
    return WhatsAppMessage(
        source_id=str(values["source_id"]),
        message_id=str(values["message_id"]),
        owner_key=str(values["owner_key"]),
        phone_number_id=str(values["phone_number_id"]),
        sender_phone=str(values["sender_phone"]),
        sender_name=(
            str(values["sender_name"])
            if values.get("sender_name") is not None
            else None
        ),
        occurred_at=str(values["occurred_at"]),
        message_type=str(values["message_type"]),
        body=str(values["body"]),
        reply_to_message_id=(
            str(values["reply_to_message_id"])
            if values.get("reply_to_message_id") is not None
            else None
        ),
        media_id=(
            str(values["media_id"]) if values.get("media_id") is not None else None
        ),
        created_at=str(values["created_at"]),
    )


def _oauth_client_from_row(row: Mapping[str, Any] | sqlite3.Row) -> OAuthClient:
    values = _row_values(row)
    try:
        raw_redirects = json.loads(str(values["redirect_uris_json"]))
    except json.JSONDecodeError as exc:
        raise WhatsAppBusinessStoreUnavailableError(
            "Stored OAuth client is invalid."
        ) from exc
    if not isinstance(raw_redirects, list) or not all(
        isinstance(item, str) for item in raw_redirects
    ):
        raise WhatsAppBusinessStoreUnavailableError("Stored OAuth client is invalid.")
    return OAuthClient(
        client_id=str(values["client_id"]),
        client_name=str(values["client_name"]),
        redirect_uris=tuple(raw_redirects),
        created_at=str(values["created_at"]),
    )


class WhatsAppBusinessStore:
    """Postgres-backed store with injected SQLite for local use and tests."""

    def __init__(
        self,
        *,
        sqlite_path: Path | None = None,
        oauth_client_limit: int = _MAX_OAUTH_CLIENTS,
    ) -> None:
        configured_sqlite_path = sqlite_path or _configured_sqlite_path()
        self._use_postgres = configured_sqlite_path is None and is_postgres_enabled()
        self._sqlite_path = configured_sqlite_path
        self._oauth_client_limit = max(int(oauth_client_limit), 1)
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self._use_postgres:
            with connect_pdp_database(Path(".")) as connection:
                connection.row_factory = DICT_ROW_FACTORY
                yield connection
            return

        if self._sqlite_path is None:
            raise WhatsAppBusinessStoreUnavailableError(
                "WhatsApp Business storage requires Postgres in production or "
                "an explicit WHATSAPP_DB_PATH for local development."
            )
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._sqlite_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            try:
                with self._connect() as connection:
                    for statement in _SCHEMA_STATEMENTS:
                        connection.execute(statement)
            except (
                OSError,
                sqlite3.Error,
                psycopg.Error,
                PostgresCommitStateUnknownError,
            ) as exc:
                raise WhatsAppBusinessStoreUnavailableError(
                    "WhatsApp Business storage is unavailable."
                ) from exc
            self._schema_ready = True

    def upsert_account(
        self,
        *,
        owner_key: str,
        waba_id: str,
        phone_number_id: str,
        display_phone_number: str,
        label: str,
    ) -> WhatsAppAccount:
        """Create or update the caller's single linked business number."""

        self._ensure_schema()
        timestamp = _utc_now()
        try:
            with self._connect() as connection:
                if self._use_postgres:
                    connection.disable_transaction_replay()
                else:
                    connection.execute("BEGIN IMMEDIATE")
                account_lock_sql = (
                    """
                    SELECT waba_id, phone_number_id
                    FROM mparanza_whatsapp_accounts
                    WHERE owner_key = ?
                    FOR UPDATE
                    """
                    if self._use_postgres
                    else """
                    SELECT waba_id, phone_number_id
                    FROM mparanza_whatsapp_accounts
                    WHERE owner_key = ?
                    """
                )
                existing = connection.execute(
                    account_lock_sql,
                    (owner_key,),
                ).fetchone()
                if existing is not None:
                    existing_values = _row_values(existing)
                    identifiers_changed = (
                        str(existing_values["waba_id"]) != waba_id
                        or str(existing_values["phone_number_id"]) != phone_number_id
                    )
                    if identifiers_changed:
                        connection.execute(
                            """
                            DELETE FROM mparanza_whatsapp_messages
                            WHERE owner_key = ?
                            """,
                            (owner_key,),
                        )
                        connection.execute(
                            """
                            DELETE FROM mparanza_whatsapp_oauth_tokens
                            WHERE owner_key = ?
                            """,
                            (owner_key,),
                        )
                        connection.execute(
                            """
                            DELETE FROM mparanza_whatsapp_oauth_codes
                            WHERE owner_key = ?
                            """,
                            (owner_key,),
                        )
                connection.execute(
                    """
                    INSERT INTO mparanza_whatsapp_accounts (
                        owner_key, waba_id, phone_number_id,
                        display_phone_number, label, active,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT (owner_key) DO UPDATE SET
                        waba_id = excluded.waba_id,
                        phone_number_id = excluded.phone_number_id,
                        display_phone_number = excluded.display_phone_number,
                        label = excluded.label,
                        active = 1,
                        updated_at = excluded.updated_at
                    """,
                    (
                        owner_key,
                        waba_id,
                        phone_number_id,
                        display_phone_number,
                        label,
                        timestamp,
                        timestamp,
                    ),
                )
                row = connection.execute(
                    """
                    SELECT * FROM mparanza_whatsapp_accounts
                    WHERE owner_key = ?
                    """,
                    (owner_key,),
                ).fetchone()
            if row is None:
                raise WhatsAppBusinessStoreUnavailableError(
                    "Linked WhatsApp account could not be read."
                )
            return _account_from_row(row)
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise WhatsAppBusinessStoreUnavailableError(
                "WhatsApp Business storage is unavailable."
            ) from exc

    def get_account_for_owner(self, owner_key: str) -> WhatsAppAccount | None:
        """Return the active account linked to one OAuth owner."""

        self._ensure_schema()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM mparanza_whatsapp_accounts
                    WHERE owner_key = ? AND active = 1
                    """,
                    (owner_key,),
                ).fetchone()
            return _account_from_row(row) if row is not None else None
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise WhatsAppBusinessStoreUnavailableError(
                "WhatsApp Business storage is unavailable."
            ) from exc

    def get_account_for_meta_ids(
        self,
        *,
        waba_id: str,
        phone_number_id: str,
    ) -> WhatsAppAccount | None:
        """Resolve both signed Meta identifiers to exactly one active owner."""

        self._ensure_schema()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM mparanza_whatsapp_accounts
                    WHERE waba_id = ? AND phone_number_id = ? AND active = 1
                    """,
                    (waba_id, phone_number_id),
                ).fetchone()
            return _account_from_row(row) if row is not None else None
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise WhatsAppBusinessStoreUnavailableError(
                "WhatsApp Business storage is unavailable."
            ) from exc

    def delete_account(self, owner_key: str) -> bool:
        """Delete one account, all messages, and its bearer tokens."""

        self._ensure_schema()
        try:
            with self._connect() as connection:
                if self._use_postgres:
                    connection.disable_transaction_replay()
                else:
                    connection.execute("BEGIN IMMEDIATE")
                account_lock_sql = (
                    """
                    SELECT owner_key
                    FROM mparanza_whatsapp_accounts
                    WHERE owner_key = ?
                    FOR UPDATE
                    """
                    if self._use_postgres
                    else """
                    SELECT owner_key
                    FROM mparanza_whatsapp_accounts
                    WHERE owner_key = ?
                    """
                )
                account = connection.execute(
                    account_lock_sql,
                    (owner_key,),
                ).fetchone()
                if account is None:
                    return False
                connection.execute(
                    "DELETE FROM mparanza_whatsapp_messages WHERE owner_key = ?",
                    (owner_key,),
                )
                connection.execute(
                    "DELETE FROM mparanza_whatsapp_oauth_tokens WHERE owner_key = ?",
                    (owner_key,),
                )
                connection.execute(
                    "DELETE FROM mparanza_whatsapp_oauth_codes WHERE owner_key = ?",
                    (owner_key,),
                )
                deleted = connection.execute(
                    "DELETE FROM mparanza_whatsapp_accounts WHERE owner_key = ?",
                    (owner_key,),
                )
            return bool(deleted.rowcount)
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise WhatsAppBusinessStoreUnavailableError(
                "WhatsApp Business storage is unavailable."
            ) from exc

    def ingest_messages(
        self,
        account: WhatsAppAccount,
        messages: Sequence[IncomingWhatsAppMessage],
    ) -> int:
        """Store normalized webhook messages exactly once."""

        if not messages:
            return 0
        self._ensure_schema()
        timestamp = _utc_now()
        inserted = 0
        try:
            with self._connect() as connection:
                if self._use_postgres:
                    connection.disable_transaction_replay()
                else:
                    connection.execute("BEGIN IMMEDIATE")
                account_lock_sql = (
                    """
                    SELECT owner_key
                    FROM mparanza_whatsapp_accounts
                    WHERE owner_key = ? AND waba_id = ? AND phone_number_id = ?
                      AND active = 1
                    FOR UPDATE
                    """
                    if self._use_postgres
                    else """
                    SELECT owner_key
                    FROM mparanza_whatsapp_accounts
                    WHERE owner_key = ? AND waba_id = ? AND phone_number_id = ?
                      AND active = 1
                    """
                )
                current_account = connection.execute(
                    account_lock_sql,
                    (
                        account.owner_key,
                        account.waba_id,
                        account.phone_number_id,
                    ),
                ).fetchone()
                if current_account is None:
                    return 0
                for message in messages:
                    if message.phone_number_id != account.phone_number_id:
                        continue
                    cursor = connection.execute(
                        """
                        INSERT INTO mparanza_whatsapp_messages (
                            source_id, message_id, owner_key, phone_number_id,
                            sender_phone, sender_name, occurred_at, message_type,
                            body, reply_to_message_id, media_id, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (message_id) DO NOTHING
                        """,
                        (
                            f"wa_{secrets.token_urlsafe(18)}",
                            message.message_id,
                            account.owner_key,
                            account.phone_number_id,
                            message.sender_phone,
                            message.sender_name,
                            message.occurred_at,
                            message.message_type,
                            message.body,
                            message.reply_to_message_id,
                            message.media_id,
                            timestamp,
                        ),
                    )
                    inserted += max(int(cursor.rowcount or 0), 0)
            return inserted
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise WhatsAppBusinessStoreUnavailableError(
                "WhatsApp Business storage is unavailable."
            ) from exc

    def purge_expired_messages(self, retention_days: int) -> int:
        """Delete messages older than the configured retention window."""

        self._ensure_schema()
        cutoff = _retention_cutoff(retention_days)
        try:
            with self._connect() as connection:
                deleted = connection.execute(
                    """
                    DELETE FROM mparanza_whatsapp_messages
                    WHERE occurred_at < ?
                    """,
                    (cutoff,),
                )
            return max(int(deleted.rowcount or 0), 0)
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise WhatsAppBusinessStoreUnavailableError(
                "WhatsApp Business storage is unavailable."
            ) from exc

    def search_messages(
        self,
        *,
        owner_key: str,
        phone_number_id: str,
        client_phone: str,
        terms: Sequence[str],
        after: str | None,
        before: str | None,
        retention_days: int,
        limit: int = _MAX_SEARCH_RESULTS,
    ) -> list[WhatsAppMessage]:
        """Search only one exact participant inside one authenticated tenant."""

        self._ensure_schema()
        clauses = [
            "owner_key = ?",
            "phone_number_id = ?",
            "sender_phone = ?",
            "occurred_at >= ?",
        ]
        parameters: list[Any] = [
            owner_key,
            phone_number_id,
            client_phone,
            _retention_cutoff(retention_days),
        ]
        if after:
            clauses.append("occurred_at >= ?")
            parameters.append(f"{after}T00:00:00+00:00")
        if before:
            clauses.append("occurred_at < ?")
            parameters.append(f"{before}T00:00:00+00:00")
        for term in terms:
            escaped = (
                term.lower()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            clauses.append("LOWER(body) LIKE ? ESCAPE '\\'")
            parameters.append(f"%{escaped}%")
        safe_limit = min(max(int(limit), 1), _MAX_SEARCH_RESULTS)
        parameters.append(safe_limit)
        # Every clause is selected from fixed literals; all values remain bound.
        query = (
            "SELECT * FROM mparanza_whatsapp_messages WHERE "  # nosec B608
            + " AND ".join(clauses)
            + " ORDER BY occurred_at DESC, source_id ASC LIMIT ?"
        )
        try:
            with self._connect() as connection:
                rows = connection.execute(query, tuple(parameters)).fetchall()
            return [_message_from_row(row) for row in rows]
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise WhatsAppBusinessStoreUnavailableError(
                "WhatsApp Business storage is unavailable."
            ) from exc

    def fetch_message(
        self,
        *,
        owner_key: str,
        phone_number_id: str,
        source_id: str,
        retention_days: int,
    ) -> WhatsAppMessage | None:
        """Fetch one opaque source only within the bearer token's tenant."""

        self._ensure_schema()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM mparanza_whatsapp_messages
                    WHERE owner_key = ? AND phone_number_id = ?
                      AND source_id = ? AND occurred_at >= ?
                    """,
                    (
                        owner_key,
                        phone_number_id,
                        source_id,
                        _retention_cutoff(retention_days),
                    ),
                ).fetchone()
            return _message_from_row(row) if row is not None else None
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise WhatsAppBusinessStoreUnavailableError(
                "WhatsApp Business storage is unavailable."
            ) from exc

    def register_oauth_client(
        self, *, client_name: str, redirect_uris: Sequence[str]
    ) -> OAuthClient:
        """Register one public PKCE client, evicting the oldest unused row."""

        self._ensure_schema()
        client_id = f"wa_client_{secrets.token_urlsafe(24)}"
        created_at = _utc_now()
        redirect_uris_json = json.dumps(
            list(redirect_uris), separators=(",", ":"), sort_keys=True
        )
        try:
            with self._connect() as connection:
                if self._use_postgres:
                    connection.disable_transaction_replay()
                    connection.execute(
                        "SELECT pg_advisory_xact_lock(?)",
                        (_OAUTH_CLIENT_REGISTRY_LOCK_ID,),
                    )
                else:
                    connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """
                    SELECT * FROM mparanza_whatsapp_oauth_clients
                    WHERE redirect_uris_json = ?
                    """,
                    (redirect_uris_json,),
                ).fetchone()
                if existing is not None:
                    return _oauth_client_from_row(existing)
                count_row = connection.execute(
                    "SELECT COUNT(*) AS client_count "
                    "FROM mparanza_whatsapp_oauth_clients"
                ).fetchone()
                client_count = (
                    int(_row_values(count_row)["client_count"])
                    if count_row is not None
                    else 0
                )
                if client_count >= self._oauth_client_limit:
                    evictable = connection.execute("""
                        SELECT client_id
                        FROM mparanza_whatsapp_oauth_clients
                        WHERE NOT EXISTS (
                            SELECT 1 FROM mparanza_whatsapp_oauth_codes
                            WHERE mparanza_whatsapp_oauth_codes.client_id =
                                  mparanza_whatsapp_oauth_clients.client_id
                        )
                          AND NOT EXISTS (
                            SELECT 1 FROM mparanza_whatsapp_oauth_tokens
                            WHERE mparanza_whatsapp_oauth_tokens.client_id =
                                  mparanza_whatsapp_oauth_clients.client_id
                        )
                        ORDER BY last_used_at ASC, created_at ASC, client_id ASC
                        LIMIT 1
                        """).fetchone()
                    if evictable is None:
                        raise OAuthClientRegistrationLimitError(
                            "OAuth client registration capacity is exhausted."
                        )
                    connection.execute(
                        """
                        DELETE FROM mparanza_whatsapp_oauth_clients
                        WHERE client_id = ?
                        """,
                        (str(_row_values(evictable)["client_id"]),),
                    )
                connection.execute(
                    """
                    INSERT INTO mparanza_whatsapp_oauth_clients (
                        client_id, client_name, redirect_uris_json,
                        created_at, last_used_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (redirect_uris_json) DO NOTHING
                    """,
                    (
                        client_id,
                        client_name,
                        redirect_uris_json,
                        created_at,
                        created_at,
                    ),
                )
                row = connection.execute(
                    """
                    SELECT * FROM mparanza_whatsapp_oauth_clients
                    WHERE redirect_uris_json = ?
                    """,
                    (redirect_uris_json,),
                ).fetchone()
            if row is None:
                raise WhatsAppBusinessStoreUnavailableError(
                    "OAuth client registration could not be read."
                )
            return _oauth_client_from_row(row)
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise WhatsAppBusinessStoreUnavailableError(
                "OAuth client storage is unavailable."
            ) from exc

    def get_oauth_client(self, client_id: str) -> OAuthClient | None:
        """Return one registered OAuth client."""

        self._ensure_schema()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM mparanza_whatsapp_oauth_clients
                    WHERE client_id = ?
                    """,
                    (client_id,),
                ).fetchone()
            if row is None:
                return None
            return _oauth_client_from_row(row)
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise WhatsAppBusinessStoreUnavailableError(
                "OAuth client storage is unavailable."
            ) from exc

    def issue_authorization_code(
        self,
        *,
        client_id: str,
        owner_key: str,
        redirect_uri: str,
        resource: str,
        scope: str,
        code_challenge: str,
        ttl_seconds: int = 300,
    ) -> str | None:
        """Persist a code only while the linked account is transaction-locked."""

        self._ensure_schema()
        code = secrets.token_urlsafe(36)
        expires_at = int(time.time()) + max(int(ttl_seconds), 60)
        try:
            with self._connect() as connection:
                if self._use_postgres:
                    connection.disable_transaction_replay()
                else:
                    connection.execute("BEGIN IMMEDIATE")
                account_lock_sql = (
                    """
                    SELECT owner_key
                    FROM mparanza_whatsapp_accounts
                    WHERE owner_key = ? AND active = 1
                    FOR UPDATE
                    """
                    if self._use_postgres
                    else """
                    SELECT owner_key
                    FROM mparanza_whatsapp_accounts
                    WHERE owner_key = ? AND active = 1
                    """
                )
                account = connection.execute(
                    account_lock_sql,
                    (owner_key,),
                ).fetchone()
                if account is None:
                    return None
                connection.execute(
                    """
                    INSERT INTO mparanza_whatsapp_oauth_codes (
                        code_hash, client_id, owner_key, redirect_uri, resource,
                        scope, code_challenge, expires_at, consumed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        _token_hash(code),
                        client_id,
                        owner_key,
                        redirect_uri,
                        resource,
                        scope,
                        code_challenge,
                        expires_at,
                    ),
                )
            return code
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise WhatsAppBusinessStoreUnavailableError(
                "OAuth authorization storage is unavailable."
            ) from exc

    def exchange_authorization_code(
        self,
        code: str,
        *,
        client_id: str,
        redirect_uri: str,
        resource: str,
        code_challenge: str,
        ttl_seconds: int,
    ) -> tuple[str, OAuthIdentity] | None:
        """Consume a PKCE code and issue its token atomically with account state."""

        self._ensure_schema()
        code_hash = _token_hash(code)
        now = int(time.time())
        token = secrets.token_urlsafe(48)
        expires_at = now + max(int(ttl_seconds), 300)
        created_at = _utc_now()
        try:
            with self._connect() as connection:
                if self._use_postgres:
                    connection.disable_transaction_replay()
                else:
                    connection.execute("BEGIN IMMEDIATE")
                authorization_sql = (
                    """
                    SELECT oauth_code.*
                    FROM mparanza_whatsapp_oauth_codes AS oauth_code
                    JOIN mparanza_whatsapp_accounts AS linked_account
                      ON linked_account.owner_key = oauth_code.owner_key
                     AND linked_account.active = 1
                    WHERE oauth_code.code_hash = ?
                      AND oauth_code.client_id = ?
                      AND oauth_code.redirect_uri = ?
                      AND oauth_code.resource = ?
                      AND oauth_code.code_challenge = ?
                      AND oauth_code.consumed_at IS NULL
                      AND oauth_code.expires_at >= ?
                    FOR UPDATE OF oauth_code, linked_account
                    """
                    if self._use_postgres
                    else """
                    SELECT oauth_code.*
                    FROM mparanza_whatsapp_oauth_codes AS oauth_code
                    JOIN mparanza_whatsapp_accounts AS linked_account
                      ON linked_account.owner_key = oauth_code.owner_key
                     AND linked_account.active = 1
                    WHERE oauth_code.code_hash = ?
                      AND oauth_code.client_id = ?
                      AND oauth_code.redirect_uri = ?
                      AND oauth_code.resource = ?
                      AND oauth_code.code_challenge = ?
                      AND oauth_code.consumed_at IS NULL
                      AND oauth_code.expires_at >= ?
                    """
                )
                row = connection.execute(
                    authorization_sql,
                    (
                        code_hash,
                        client_id,
                        redirect_uri,
                        resource,
                        code_challenge,
                        now,
                    ),
                ).fetchone()
                if row is None:
                    return None
                values = _row_values(row)
                consumed = connection.execute(
                    """
                    UPDATE mparanza_whatsapp_oauth_codes
                    SET consumed_at = ?
                    WHERE code_hash = ? AND consumed_at IS NULL
                    """,
                    (now, code_hash),
                )
                if int(consumed.rowcount or 0) != 1:
                    return None
                connection.execute(
                    """
                    INSERT INTO mparanza_whatsapp_oauth_tokens (
                        token_hash, client_id, owner_key, resource, scope,
                        expires_at, revoked_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        _token_hash(token),
                        str(values["client_id"]),
                        str(values["owner_key"]),
                        str(values["resource"]),
                        str(values["scope"]),
                        expires_at,
                        created_at,
                    ),
                )
                connection.execute(
                    """
                    UPDATE mparanza_whatsapp_oauth_clients
                    SET last_used_at = ?
                    WHERE client_id = ?
                    """,
                    (created_at, str(values["client_id"])),
                )
            return token, OAuthIdentity(
                client_id=str(values["client_id"]),
                owner_key=str(values["owner_key"]),
                resource=str(values["resource"]),
                scopes=frozenset(str(values["scope"]).split()),
                expires_at=expires_at,
            )
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise WhatsAppBusinessStoreUnavailableError(
                "OAuth token exchange is unavailable."
            ) from exc

    def resolve_access_token(self, token: str) -> OAuthIdentity | None:
        """Resolve a live bearer token without storing plaintext credentials."""

        self._ensure_schema()
        now = int(time.time())
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM mparanza_whatsapp_oauth_tokens
                    WHERE token_hash = ? AND revoked_at IS NULL AND expires_at >= ?
                    """,
                    (_token_hash(token), now),
                ).fetchone()
            if row is None:
                return None
            values = _row_values(row)
            return OAuthIdentity(
                client_id=str(values["client_id"]),
                owner_key=str(values["owner_key"]),
                resource=str(values["resource"]),
                scopes=frozenset(str(values["scope"]).split()),
                expires_at=int(values["expires_at"]),
            )
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise WhatsAppBusinessStoreUnavailableError(
                "OAuth token storage is unavailable."
            ) from exc

    def purge_expired_oauth_records(self) -> int:
        """Delete consumed/expired authorization codes and dead bearer tokens."""

        self._ensure_schema()
        now = int(time.time())
        try:
            with self._connect() as connection:
                deleted_codes = connection.execute(
                    """
                    DELETE FROM mparanza_whatsapp_oauth_codes
                    WHERE expires_at < ? OR consumed_at IS NOT NULL
                    """,
                    (now,),
                )
                deleted_tokens = connection.execute(
                    """
                    DELETE FROM mparanza_whatsapp_oauth_tokens
                    WHERE expires_at < ? OR revoked_at IS NOT NULL
                    """,
                    (now,),
                )
                idle_cutoff = (
                    (
                        datetime.now(timezone.utc)
                        - timedelta(days=_OAUTH_CLIENT_IDLE_DAYS)
                    )
                    .replace(microsecond=0)
                    .isoformat()
                )
                deleted_clients = connection.execute(
                    """
                    DELETE FROM mparanza_whatsapp_oauth_clients
                    WHERE last_used_at < ?
                      AND NOT EXISTS (
                          SELECT 1 FROM mparanza_whatsapp_oauth_codes
                          WHERE mparanza_whatsapp_oauth_codes.client_id =
                                mparanza_whatsapp_oauth_clients.client_id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM mparanza_whatsapp_oauth_tokens
                          WHERE mparanza_whatsapp_oauth_tokens.client_id =
                                mparanza_whatsapp_oauth_clients.client_id
                      )
                    """,
                    (idle_cutoff,),
                )
            return (
                max(int(deleted_codes.rowcount or 0), 0)
                + max(
                    int(deleted_tokens.rowcount or 0),
                    0,
                )
                + max(int(deleted_clients.rowcount or 0), 0)
            )
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise WhatsAppBusinessStoreUnavailableError(
                "OAuth cleanup is unavailable."
            ) from exc


@lru_cache(maxsize=1)
def get_whatsapp_business_store() -> WhatsAppBusinessStore:
    """Return the process-wide WhatsApp connector store."""

    return WhatsAppBusinessStore()
