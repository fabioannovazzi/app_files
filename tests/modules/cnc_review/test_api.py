"""Authenticate with real signed test cookies; never trust a JSON reviewer name."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.auth import dependencies
from modules.auth.google_identity import GoogleUserInfo
from modules.auth.session import create_session_cookie
from modules.cnc_review import api
from tests.modules.auth.test_dependencies import _config

HEADERS = {"Origin": "http://testserver", "X-CNC-Review": "1"}


@pytest.fixture
def service(tmp_path, monkeypatch):
    config = _config(session_secret="synthetic-secret-for-auth-tests-only")
    monkeypatch.setattr(dependencies, "get_auth_config", lambda: config)
    store = api.ReviewStore(tmp_path / "reviews.sqlite3")
    app = FastAPI()
    app.include_router(api.api_router)
    app.include_router(api.site_router)
    app.dependency_overrides[api.get_store] = lambda: store
    client = TestClient(app)
    cookie, _ = create_session_cookie(
        GoogleUserInfo(email="reviewer@example.test"), config
    )
    client.cookies.set(config.session_cookie_name, cookie)
    return client, store, config


def target():
    return {
        "request_id": str(uuid4()),
        "case_ref": "a" * 64,
        "role": "advisor",
        "node_ref": "b" * 64,
        "node_version": "c" * 64,
        "decision": "accepted",
    }


def test_signed_account_decision_is_persisted_and_retry_stable(service):
    client, store, _ = service
    payload = target()
    first = client.post("/api/vera/cnc-reviews", json=payload, headers=HEADERS)
    repeated = client.post("/api/vera/cnc-reviews", json=payload, headers=HEADERS)
    receipt = first.json()
    assert first.status_code == 200
    assert receipt["actor"] == "reviewer@example.test"
    assert receipt["authority"] == "mparanza_authenticated_account"
    assert repeated.json() == receipt
    assert store.verify(payload["request_id"], api.fingerprint(receipt)) == receipt


@pytest.mark.parametrize("cookie", [None, "forged-cookie"])
def test_absent_or_forged_session_cannot_record_review(service, cookie):
    client, _, config = service
    client.cookies.clear()
    if cookie:
        client.cookies.set(config.session_cookie_name, cookie)
    response = client.post("/api/vera/cnc-reviews", json=target(), headers=HEADERS)
    assert response.status_code == 401


def test_disabled_authentication_fails_closed(service, monkeypatch):
    client, _, config = service
    monkeypatch.setattr(
        dependencies,
        "get_auth_config",
        lambda: replace(config, authentication_enabled=False),
    )
    assert (
        client.post("/api/vera/cnc-reviews", json=target(), headers=HEADERS).status_code
        == 401
    )


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://attacker.invalid", "X-CNC-Review": "1"},
        {"Origin": "http://testserver"},
    ],
)
def test_cross_origin_or_noninteractive_request_is_rejected(service, headers):
    client, _, _ = service
    assert (
        client.post("/api/vera/cnc-reviews", json=target(), headers=headers).status_code
        == 403
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("actor", "forged@example.test"),
        ("content", "private case text"),
        ("authority", "authenticated"),
    ],
)
def test_extra_identity_or_case_content_fields_are_rejected(service, field, value):
    client, _, _ = service
    payload = {**target(), field: value}
    assert (
        client.post("/api/vera/cnc-reviews", json=payload, headers=HEADERS).status_code
        == 422
    )


def test_another_account_cannot_review_the_existing_case(service):
    client, _, config = service
    payload = target()
    assert (
        client.post("/api/vera/cnc-reviews", json=payload, headers=HEADERS).status_code
        == 200
    )
    cookie, _ = create_session_cookie(
        GoogleUserInfo(email="other@example.test"), config
    )
    client.cookies.set(config.session_cookie_name, cookie)
    payload["request_id"] = str(uuid4())
    assert (
        client.post("/api/vera/cnc-reviews", json=payload, headers=HEADERS).status_code
        == 403
    )


def test_role_change_and_conflicting_retry_cannot_replace_decision(service):
    client, _, _ = service
    payload = target()
    receipt = client.post("/api/vera/cnc-reviews", json=payload, headers=HEADERS).json()
    assert (
        client.post(
            "/api/vera/cnc-reviews",
            json={**payload, "role": "esperto"},
            headers=HEADERS,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/vera/cnc-reviews",
            json={**payload, "decision": "rejected"},
            headers=HEADERS,
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/vera/cnc-reviews/verify",
            json={
                "receipt_id": payload["request_id"],
                "receipt_sha256": api.fingerprint(receipt),
            },
        ).json()
        == receipt
    )
    assert (
        client.post(
            "/api/vera/cnc-reviews/verify",
            json={"receipt_id": payload["request_id"], "receipt_sha256": "0" * 64},
        ).status_code
        == 404
    )


def test_corrupted_retained_receipt_is_not_verified(service):
    _, store, _ = service
    receipt = store.record(api.ReviewTarget(**target()), "reviewer@example.test")
    connection = store.connect()
    with connection:
        connection.execute(
            "UPDATE cnc_review_receipts SET payload = ?", ('{"actor": "changed"}',)
        )
    connection.close()
    with pytest.raises(ValueError, match="integrity"):
        store.verify(receipt["request_id"], api.fingerprint(receipt))


def test_browser_review_page_loads_without_reading_client_files():
    # The repository conftest substitutes Jinja; exercise real rendering in a fresh interpreter.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from fastapi import FastAPI; from fastapi.testclient import TestClient; from modules.cnc_review.api import site_router; app=FastAPI(); app.include_router(site_router); response=TestClient(app).get('/vera/cnc-review'); assert response.status_code == 200; assert 'type=\"file\"' in response.text; assert 'textContent=data.node.content' in response.text",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_oversized_metadata_is_rejected_before_recording(service):
    client, _, _ = service
    response = client.post(
        "/api/vera/cnc-reviews", content=b"x" * 4097, headers=HEADERS
    )
    assert response.status_code == 413


def test_session_identifies_the_authenticated_account(service):
    client, _, _ = service
    assert client.get("/api/vera/cnc-reviews/session").json() == {
        "account": "reviewer@example.test"
    }
    client.cookies.clear()
    assert client.get("/api/vera/cnc-reviews/session").status_code == 401


def test_older_acceptance_cannot_be_reimported_after_later_rejection(service):
    client, _, _ = service
    payload = target()
    accepted = client.post(
        "/api/vera/cnc-reviews", json=payload, headers=HEADERS
    ).json()
    rejected = client.post(
        "/api/vera/cnc-reviews",
        json={**payload, "request_id": str(uuid4()), "decision": "rejected"},
        headers=HEADERS,
    ).json()
    response = client.post(
        "/api/vera/cnc-reviews/verify",
        json={
            "receipt_id": accepted["request_id"],
            "receipt_sha256": api.fingerprint(accepted),
        },
    )
    assert response.status_code == 409
    assert "later decision" in response.json()["detail"]
    assert (
        client.post(
            "/api/vera/cnc-reviews/verify",
            json={
                "receipt_id": rejected["request_id"],
                "receipt_sha256": api.fingerprint(rejected),
            },
        ).json()
        == rejected
    )
