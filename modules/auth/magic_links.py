"""Distributed-friendly store for issuing and consuming email magic link tokens."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Dict, Optional

from modules.utilities.cache import get_cache_path

try:  # pragma: no cover - optional dependency guarded by requirements
    import redis  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    redis = None  # type: ignore

LOGGER = logging.getLogger(__name__)

__all__ = [
    "MagicLinkError",
    "MagicLinkExpiredError",
    "MagicLinkNotFoundError",
    "MagicLinkRecord",
    "consume_magic_link",
    "issue_magic_link",
    "purge_expired_tokens",
]

_DEFAULT_TTL_SECONDS = 15 * 60  # 15 minutes
_MAX_ACTIVE_TOKENS = 2048
_REDIS_KEY_PREFIX = "magic-link:"
_FILE_STORE_ENV = "AUTH_MAGIC_LINK_STORE_PATH"
_DEFAULT_FILE_STORE = "magic_link_tokens.json"
_REDIS_CLIENT: Optional["redis.Redis"] = None
_REDIS_CLIENT_URL: Optional[str] = None
_STORE_LOCK = RLock()


class MagicLinkError(RuntimeError):
    """Base error for magic link issues."""


class MagicLinkNotFoundError(MagicLinkError):
    """Raised when attempting to consume an unknown token."""


class MagicLinkExpiredError(MagicLinkError):
    """Raised when a token expired before being consumed."""


@dataclass(frozen=True)
class MagicLinkRecord:
    email: str
    expires_at: float
    redirect_path: str | None = None


_TOKENS: Dict[str, MagicLinkRecord] = {}


def _redis_key(token_hash: str) -> str:
    return f"{_REDIS_KEY_PREFIX}{token_hash}"


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _clean_email(email: str) -> str:
    return email.strip().lower()


def _clean_path(path: str | None) -> str | None:
    if not path:
        return None
    cleaned = path.strip()
    if not cleaned.startswith("/"):
        return None
    return cleaned


def purge_expired_tokens(now: float | None = None) -> None:
    """Remove tokens that are past their expiry."""

    reference = now if now is not None else time.time()
    with _STORE_LOCK:
        _refresh_memory_store(reference, include_expired=True)
        expired = [
            token for token, record in _TOKENS.items() if record.expires_at <= reference
        ]
        for token in expired:
            _TOKENS.pop(token, None)
        if expired:
            _write_file_store(_TOKENS)


def _prune_when_needed() -> None:
    if len(_TOKENS) <= _MAX_ACTIVE_TOKENS:
        return
    # Drop oldest tokens first
    sorted_tokens = sorted(_TOKENS.items(), key=lambda item: item[1].expires_at)
    for token, _record in sorted_tokens[: len(_TOKENS) - _MAX_ACTIVE_TOKENS]:
        _TOKENS.pop(token, None)


def _record_to_dict(record: MagicLinkRecord) -> dict[str, object]:
    return {
        "email": record.email,
        "expires_at": record.expires_at,
        "redirect_path": record.redirect_path,
    }


def _record_to_payload(record: MagicLinkRecord) -> str:
    return json.dumps(_record_to_dict(record), separators=(",", ":"))


def _record_from_data(data: dict[str, object]) -> MagicLinkRecord:
    redirect_path = data.get("redirect_path")
    return MagicLinkRecord(
        email=str(data["email"]),
        expires_at=float(data["expires_at"]),
        redirect_path=redirect_path if isinstance(redirect_path, str) else None,
    )


def _record_from_payload(payload: str) -> MagicLinkRecord:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Magic link payload must be an object.")
    return _record_from_data(data)


def _file_store_path() -> Path:
    configured = (os.getenv(_FILE_STORE_ENV) or "").strip()
    if configured:
        return Path(configured).expanduser()
    return get_cache_path(_DEFAULT_FILE_STORE)


def _load_file_store(
    now: float | None = None, *, include_expired: bool = False
) -> Dict[str, MagicLinkRecord]:
    path = _file_store_path()
    if not path.exists():
        return {}
    try:
        raw_payload = path.read_text(encoding="utf-8")
    except OSError as exc:
        LOGGER.warning("Unable to read magic link token store %s: %s", path, exc)
        return {}
    if not raw_payload.strip():
        return {}
    try:
        payload = json.loads(raw_payload)
        token_payloads = payload.get("tokens") if isinstance(payload, dict) else None
        if not isinstance(token_payloads, dict):
            return {}
        reference = now if now is not None else time.time()
        records: Dict[str, MagicLinkRecord] = {}
        for token_hash, record_payload in token_payloads.items():
            if not isinstance(token_hash, str) or not isinstance(record_payload, dict):
                continue
            record = _record_from_data(record_payload)
            if include_expired or record.expires_at > reference:
                records[token_hash] = record
        return records
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        LOGGER.warning("Ignoring invalid magic link token store %s: %s", path, exc)
        return {}


def _write_file_store(records: Dict[str, MagicLinkRecord]) -> None:
    path = _file_store_path()
    payload = {
        "tokens": {
            token_hash: _record_to_dict(record)
            for token_hash, record in sorted(records.items())
        }
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.{secrets.token_hex(8)}.tmp")
        tmp_path.write_text(
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        try:
            tmp_path.chmod(0o600)
        except OSError as exc:
            LOGGER.debug("Unable to set permissions on %s: %s", tmp_path, exc)
        tmp_path.replace(path)
        try:
            path.chmod(0o600)
        except OSError as exc:
            LOGGER.debug("Unable to set permissions on %s: %s", path, exc)
    except OSError as exc:
        LOGGER.warning("Unable to persist magic link token store %s: %s", path, exc)
        raise MagicLinkError("Magic link storage is unavailable.") from exc


def _refresh_memory_store(
    now: float | None = None, *, include_expired: bool = False
) -> None:
    _TOKENS.clear()
    _TOKENS.update(_load_file_store(now, include_expired=include_expired))


def _get_redis_client() -> Optional["redis.Redis"]:
    global _REDIS_CLIENT, _REDIS_CLIENT_URL
    if redis is None:
        if os.getenv("REDIS_URL"):
            LOGGER.error("REDIS_URL is set but the redis package is not installed.")
        return None
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    if _REDIS_CLIENT and _REDIS_CLIENT_URL == url:
        return _REDIS_CLIENT
    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        # Ping once to fail fast when Redis is unreachable.
        client.ping()
    except redis.RedisError as exc:  # pragma: no cover - connection errors logged
        LOGGER.warning("Magic link Redis unavailable: %s", exc)
        _REDIS_CLIENT = None
        _REDIS_CLIENT_URL = None
        return None
    _REDIS_CLIENT = client
    _REDIS_CLIENT_URL = url
    return client


def _redis_set_record(
    token_hash: str, record: MagicLinkRecord, ttl_seconds: int
) -> bool:
    client = _get_redis_client()
    if not client:
        return False
    try:
        client.setex(
            _redis_key(token_hash),
            max(int(ttl_seconds), 1),
            _record_to_payload(record),
        )
        return True
    except redis.RedisError as exc:  # pragma: no cover - logged and fallback
        LOGGER.warning("Unable to persist magic link token in Redis: %s", exc)
        if os.getenv("REDIS_URL"):
            raise MagicLinkError("Magic link storage is unavailable.") from exc
        return False


def _redis_getdel(client: "redis.Redis", key: str) -> Optional[str]:
    try:
        return client.execute_command("GETDEL", key)
    except redis.ResponseError:
        pipe = client.pipeline()
        pipe.get(key)
        pipe.delete(key)
        value, _ = pipe.execute()
        return value


def _redis_consume(token_hash: str) -> Optional[MagicLinkRecord]:
    client = _get_redis_client()
    if not client:
        return None
    try:
        payload = _redis_getdel(client, _redis_key(token_hash))
    except redis.RedisError as exc:  # pragma: no cover - logged and fallback
        LOGGER.warning("Unable to read magic link token from Redis: %s", exc)
        if os.getenv("REDIS_URL"):
            raise MagicLinkError("Magic link storage is unavailable.") from exc
        return None
    if payload is None:
        return None
    record = _record_from_payload(payload)
    if record.expires_at < time.time():
        raise MagicLinkExpiredError("Magic link token expired.")
    return record


def _memory_store(token_hash: str, record: MagicLinkRecord) -> None:
    with _STORE_LOCK:
        _refresh_memory_store()
        reference = time.time()
        for token, stored_record in list(_TOKENS.items()):
            if stored_record.expires_at <= reference:
                _TOKENS.pop(token, None)
        _TOKENS[token_hash] = record
        _prune_when_needed()
        _write_file_store(_TOKENS)


def _memory_consume(token_hash: str) -> MagicLinkRecord:
    with _STORE_LOCK:
        reference = time.time()
        _refresh_memory_store(reference, include_expired=True)
        record = _TOKENS.get(token_hash)
        if record is None:
            raise MagicLinkNotFoundError("Magic link token is invalid or already used.")
        _TOKENS.pop(token_hash, None)
        if record.expires_at < reference:
            _write_file_store(_TOKENS)
            raise MagicLinkExpiredError("Magic link token expired.")
        _write_file_store(_TOKENS)
        return record


def issue_magic_link(
    email: str,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    redirect_path: str | None = None,
) -> str:
    """Create a new token for *email* and return the raw token string."""

    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    record = MagicLinkRecord(
        email=_clean_email(email),
        expires_at=time.time() + max(ttl_seconds, 1),
        redirect_path=_clean_path(redirect_path),
    )
    if not _redis_set_record(token_hash, record, ttl_seconds):
        _memory_store(token_hash, record)
    return token


def consume_magic_link(token: str) -> MagicLinkRecord:
    """Validate *token* and return its metadata, removing it from the store."""

    token_hash = _hash_token(token)
    record = _redis_consume(token_hash)
    if record is not None:
        return record
    return _memory_consume(token_hash)
