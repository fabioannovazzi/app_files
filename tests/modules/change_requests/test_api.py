from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.change_requests import api
from modules.change_requests.store import ChangeRequestStore


def _client(tmp_path: Path) -> tuple[TestClient, ChangeRequestStore]:
    store = ChangeRequestStore(sqlite_path=tmp_path / "change-requests.sqlite3")
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_change_request_store] = lambda: store
    return TestClient(app), store


def _payload(*, submission_id: str | None = None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "submission_id": submission_id or str(uuid4()),
        "kind": "problem",
        "plugin": "clara",
        "plugin_version": "1.0.0",
        "request": {
            "observed": "The synthetic input failed.",
            "expected": "The synthetic input should pass.",
        },
    }


def test_submit_and_batch_poll_return_stable_public_contract(tmp_path: Path) -> None:
    client, _store = _client(tmp_path)

    submitted = client.post("/api/change-requests", json=_payload())
    receipt = submitted.json()
    polled = client.post(
        "/api/change-requests/status",
        json={
            "requests": [
                {
                    "change_request_id": receipt["change_request_id"],
                    "status_token": receipt["status_token"],
                }
            ]
        },
    )

    assert submitted.status_code == 201
    assert receipt == {
        "schema_version": 1,
        "change_request_id": "CR-1",
        "status_token": receipt["status_token"],
        "status": "open",
        "fixed": False,
        "fixed_version": None,
        "install_url": None,
    }
    assert polled.status_code == 200
    assert polled.json() == {
        "schema_version": 1,
        "requests": [
            {
                "change_request_id": "CR-1",
                "found": True,
                "status": "open",
                "fixed": False,
                "fixed_version": None,
                "install_url": None,
            }
        ],
    }
    assert submitted.headers["cache-control"] == "no-store"
    assert polled.headers["cache-control"] == "no-store"


def test_submit_retry_is_idempotent_and_changed_content_conflicts(
    tmp_path: Path,
) -> None:
    client, _store = _client(tmp_path)
    submission_id = str(uuid4())
    payload = _payload(submission_id=submission_id)

    first = client.post("/api/change-requests", json=payload)
    retried = client.post("/api/change-requests", json=payload)
    payload["request"] = {"observed": "Changed"}
    conflict = client.post("/api/change-requests", json=payload)

    assert retried.status_code == 201
    assert retried.json() == first.json()
    assert conflict.status_code == 409


def test_batch_poll_does_not_reveal_missing_or_wrong_token(tmp_path: Path) -> None:
    client, _store = _client(tmp_path)
    receipt = client.post("/api/change-requests", json=_payload()).json()

    response = client.post(
        "/api/change-requests/status",
        json={
            "requests": [
                {
                    "change_request_id": receipt["change_request_id"],
                    "status_token": "wrong-token-value-long-enough",
                },
                {
                    "change_request_id": "CR-999",
                    "status_token": "another-token-value-long-enough",
                },
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["requests"] == [
        {
            "change_request_id": "CR-1",
            "found": False,
            "status": None,
            "fixed": False,
            "fixed_version": None,
            "install_url": None,
        },
        {
            "change_request_id": "CR-999",
            "found": False,
            "status": None,
            "fixed": False,
            "fixed_version": None,
            "install_url": None,
        },
    ]


def test_public_intake_rate_limit_returns_retry_after(tmp_path: Path) -> None:
    client, _store = _client(tmp_path)
    limiter = api.ChangeRequestRateLimiter(
        window_seconds=30,
        intake_per_source=1,
        intake_global=1,
    )
    client.app.dependency_overrides[api.get_change_request_rate_limiter] = (
        lambda: limiter
    )

    first = client.post("/api/change-requests", json=_payload())
    limited = client.post("/api/change-requests", json=_payload())

    assert first.status_code == 201
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "30"


def test_rate_limiter_separates_sources_and_expires_fixed_window() -> None:
    current_time = [0.0]
    limiter = api.ChangeRequestRateLimiter(
        window_seconds=30,
        intake_per_source=1,
        intake_global=2,
        clock=lambda: current_time[0],
    )

    limiter.check("source-a", "intake")
    with pytest.raises(api.ChangeRequestRateLimitError):
        limiter.check("source-a", "intake")
    limiter.check("source-b", "intake")
    with pytest.raises(api.ChangeRequestRateLimitError):
        limiter.check("source-c", "intake")
    current_time[0] = 31.0

    limiter.check("source-a", "intake")


def test_public_intake_capacity_is_bounded(tmp_path: Path) -> None:
    client, _store = _client(tmp_path)
    bounded_store = ChangeRequestStore(
        sqlite_path=tmp_path / "bounded.sqlite3", max_records=1
    )
    client.app.dependency_overrides[api.get_change_request_store] = (
        lambda: bounded_store
    )

    first = client.post("/api/change-requests", json=_payload())
    full = client.post("/api/change-requests", json=_payload())

    assert first.status_code == 201
    assert full.status_code == 429
    assert full.headers["retry-after"] == "3600"


def test_submit_rejects_oversized_body_before_json_parsing(tmp_path: Path) -> None:
    client, _store = _client(tmp_path)
    oversized = "x" * api.MAX_REQUEST_BODY_BYTES
    payload = _payload()
    payload["request"] = {"observed": oversized}

    response = client.post("/api/change-requests", json=payload)

    assert response.status_code == 413


def test_submit_rejects_unknown_plugin_and_empty_request(tmp_path: Path) -> None:
    client, _store = _client(tmp_path)
    unknown_plugin = _payload()
    unknown_plugin["plugin"] = "other"
    empty_request = _payload()
    empty_request["request"] = {}

    plugin_response = client.post("/api/change-requests", json=unknown_plugin)
    request_response = client.post("/api/change-requests", json=empty_request)

    assert plugin_response.status_code == 422
    assert request_response.status_code == 422


def test_full_app_keeps_change_request_intake_public_when_login_is_enabled(
    tmp_path: Path, monkeypatch
) -> None:
    from modules.auth.config import get_auth_config
    from modules.pdp.api import create_app

    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "s" * 32)
    get_auth_config.cache_clear()
    store = ChangeRequestStore(sqlite_path=tmp_path / "change-requests.sqlite3")
    app = create_app()
    app.dependency_overrides[api.get_change_request_store] = lambda: store
    client = TestClient(app)

    response = client.post("/api/change-requests", json=_payload())
    get_auth_config.cache_clear()

    assert response.status_code == 201
    assert response.json()["change_request_id"] == "CR-1"
