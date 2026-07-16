from __future__ import annotations

import json
from pathlib import Path

import pytest

from modules.auth import magic_links
from modules.auth.magic_links import (
    MagicLinkExpiredError,
    MagicLinkNotFoundError,
    consume_magic_link,
    issue_magic_link,
    purge_expired_tokens,
)


@pytest.fixture(autouse=True)
def isolated_magic_link_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "AUTH_MAGIC_LINK_STORE_PATH", str(tmp_path / "magic_link_tokens.json")
    )
    monkeypatch.delenv("REDIS_URL", raising=False)
    _reset_store()


def _reset_store() -> None:
    magic_links._TOKENS.clear()  # type: ignore[attr-defined]
    magic_links._REDIS_CLIENT = None  # type: ignore[attr-defined]
    magic_links._REDIS_CLIENT_URL = None  # type: ignore[attr-defined]


def test_issue_and_consume_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_store()
    monkeypatch.setattr("modules.auth.magic_links.time.time", lambda: 1000.0)

    token = issue_magic_link(
        "User@example.com", ttl_seconds=120, redirect_path="/workspace"
    )
    record = consume_magic_link(token)

    assert record.email == "user@example.com"
    assert record.redirect_path == "/workspace"


def test_issue_and_consume_survives_process_memory_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_store()
    monkeypatch.setattr("modules.auth.magic_links.time.time", lambda: 1000.0)

    token = issue_magic_link(
        "User@example.com", ttl_seconds=120, redirect_path="/workspace"
    )
    magic_links._TOKENS.clear()  # type: ignore[attr-defined]

    record = consume_magic_link(token)

    assert record.email == "user@example.com"
    assert record.redirect_path == "/workspace"
    assert not magic_links._TOKENS  # type: ignore[attr-defined]


def test_file_store_keeps_only_hashed_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_store()
    monkeypatch.setattr("modules.auth.magic_links.time.time", lambda: 1000.0)

    token = issue_magic_link("user@example.com", ttl_seconds=120)
    store_path = magic_links._file_store_path()  # type: ignore[attr-defined]
    store_text = store_path.read_text(encoding="utf-8")
    payload = json.loads(store_text)
    token_hashes = list(payload["tokens"])

    assert token not in store_text
    assert token_hashes == [magic_links._hash_token(token)]  # type: ignore[attr-defined]


def test_consume_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_store()
    timeline = {"now": 1000.0}

    def _fake_time() -> float:
        return timeline["now"]

    monkeypatch.setattr("modules.auth.magic_links.time.time", _fake_time)
    token = issue_magic_link(
        "user@example.com", ttl_seconds=10, redirect_path="/workspace"
    )

    timeline["now"] = 2000.0
    with pytest.raises(MagicLinkExpiredError):
        consume_magic_link(token)


def test_consume_unknown_token() -> None:
    _reset_store()
    with pytest.raises(MagicLinkNotFoundError):
        consume_magic_link("missing")


def test_purge_expired_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_store()
    calls = {"now": 100.0}

    def _fake_time() -> float:
        return calls["now"]

    monkeypatch.setattr("modules.auth.magic_links.time.time", _fake_time)
    issue_magic_link("user@example.com", ttl_seconds=10)
    calls["now"] = 1000.0
    purge_expired_tokens()
    store_path = magic_links._file_store_path()  # type: ignore[attr-defined]
    payload = json.loads(store_path.read_text(encoding="utf-8"))

    assert not magic_links._TOKENS  # type: ignore[attr-defined]
    assert payload["tokens"] == {}


def test_issue_and_consume_redis_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_store()

    class FakeRedis:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        def ping(self) -> bool:
            return True

        def setex(self, key: str, ttl: int, value: str) -> None:
            self.store[key] = value

        def execute_command(self, command: str, key: str) -> str | None:
            assert command.upper() == "GETDEL"
            return self.store.pop(key, None)

    fake = FakeRedis()
    monkeypatch.setattr("modules.auth.magic_links._get_redis_client", lambda: fake)

    token = issue_magic_link("redis@example.com", redirect_path="/workspace")
    # Ensure in-memory fallback not used
    assert not magic_links._TOKENS  # type: ignore[attr-defined]

    record = consume_magic_link(token)
    assert record.email == "redis@example.com"
    assert record.redirect_path == "/workspace"

    with pytest.raises(MagicLinkNotFoundError):
        consume_magic_link(token)
