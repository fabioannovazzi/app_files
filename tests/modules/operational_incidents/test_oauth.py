"""Public OAuth and cross-task incident isolation acceptance tests."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.operational_incidents import api, oauth
from modules.operational_incidents.api import get_incident_store, router
from modules.operational_incidents.contracts import Credentials, Remedy
from modules.operational_incidents.oauth import (
    CLAUDE_CALLBACK,
    CLAUDE_CLIENT,
    RESOURCE,
    SCOPE,
    IncidentOAuth,
)
from modules.operational_incidents.store import IncidentStore

VERIFIER = "a" * 64
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest())
    .decode()
    .rstrip("=")
)


def connection_headers(store):
    service = IncidentOAuth(store)
    code = service.authorize(authorization_fields())
    tokens = service.token(token_fields(code))
    return {"Authorization": "Bearer " + tokens["access_token"]}


def authorization_fields(**changes):
    return {
        "client_id": CLAUDE_CLIENT,
        "redirect_uri": CLAUDE_CALLBACK,
        "response_type": "code",
        "code_challenge_method": "S256",
        "code_challenge": CHALLENGE,
        "resource": RESOURCE,
        "scope": SCOPE,
        "state": "opaque-host-state",
        **changes,
    }


def token_fields(code, **changes):
    return {
        "client_id": CLAUDE_CLIENT,
        "redirect_uri": CLAUDE_CALLBACK,
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": VERIFIER,
        "resource": RESOURCE,
        **changes,
    }


@pytest.fixture
def host(tmp_path, monkeypatch):
    store = IncidentStore(tmp_path / "incidents.sqlite3")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_incident_store] = lambda: store
    monkeypatch.setattr(api, "_RATE_EVENTS", api.OrderedDict())
    monkeypatch.setattr(api, "_GLOBAL_EVENTS", api.deque())
    return TestClient(app), store


def grant(client, **changes):
    redirect = client.get(
        "/oauth/vera-incidents/authorize",
        params=authorization_fields(**changes),
        follow_redirects=False,
    )
    assert redirect.status_code == 302
    location = redirect.headers["location"]
    assert location.startswith(CLAUDE_CALLBACK + "?")
    query = parse_qs(urlsplit(location).query)
    assert query["state"] == ["opaque-host-state"]
    code = query["code"][0]
    tokens = client.post(
        "/oauth/vera-incidents/token", data=token_fields(code, **changes)
    )
    assert tokens.status_code == 200
    assert tokens.headers["cache-control"] == "no-store"
    return code, tokens.json()


def rpc(client, token, name, arguments=None):
    return client.post(
        "/mcp/vera-incidents",
        headers={"Authorization": "Bearer " + token},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "vera_incident_" + name, "arguments": arguments or {}},
        },
    )


def technical_report():
    return {
        "report_id": str(uuid4()),
        "product_version": "0.1.368",
        "host": "cowork",
        "platform": "linux",
        "workflow": "journal-sampling",
        "stage": "execution-startup",
        "diagnostics": [
            {
                "component": "host-exec",
                "error_type": "CreateProcessError",
                "stage": "execution-startup",
                "message": "synthetic startup failure",
                "evidence_source": "observed-tool-result",
            }
        ],
    }


def test_saved_connection_refresh_keeps_identity_and_previous_task_remedy(host):
    client, store = host
    _, tokens = grant(client)
    identity = rpc(client, tokens["access_token"], "register").json()["result"][
        "structuredContent"
    ]
    UUID(identity["installation_id"])
    assert "credentials" not in identity
    receipt = rpc(
        client, tokens["access_token"], "report", {"report": technical_report()}
    ).json()["result"]["structuredContent"]
    store.remedy(
        receipt["incident_id"],
        Remedy(
            kind="user-action",
            target_report_id=receipt["report_id"],
            summary="Resume the retained synthetic task",
            evidence="Synthetic startup failure",
            instructions="Resume the original task",
            expected_outcome="Original execution succeeds",
        ),
    )

    refreshed = client.post(
        "/oauth/vera-incidents/token",
        data={
            "grant_type": "refresh_token",
            "client_id": CLAUDE_CLIENT,
            "refresh_token": tokens["refresh_token"],
            "resource": RESOURCE,
        },
    ).json()
    status = rpc(client, refreshed["access_token"], "status").json()["result"][
        "structuredContent"
    ]

    assert refreshed["access_token"] != tokens["access_token"]
    assert refreshed["refresh_token"] != tokens["refresh_token"]
    assert status["installation_id"] == identity["installation_id"]
    assert status["incidents"][0]["latest_report_id"] == receipt["report_id"]
    assert (
        status["incidents"][0]["remedy"]["instructions"] == "Resume the original task"
    )


def test_refresh_replay_revokes_rotated_grant_persistently(host):
    client, _ = host
    _, tokens = grant(client)
    fields = {
        "grant_type": "refresh_token",
        "client_id": CLAUDE_CLIENT,
        "refresh_token": tokens["refresh_token"],
        "resource": RESOURCE,
    }
    new = client.post("/oauth/vera-incidents/token", data=fields).json()

    replay = client.post("/oauth/vera-incidents/token", data=fields)

    assert replay.status_code == 400
    assert replay.json() == {"error": "invalid_grant"}
    assert rpc(client, new["access_token"], "status").status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"code_verifier": "b" * 64},
        {"code_verifier": "short"},
        {"redirect_uri": "http://127.0.0.1:9876/other"},
        {"client_id": "unknown"},
        {"resource": "https://other.example/mcp"},
        {"scope": "files:read"},
        {"grant_type": "client_credentials"},
    ],
)
def test_token_rejects_wrong_proof_client_callback_scope_or_resource(host, changes):
    client, _ = host
    redirect = client.get(
        "/oauth/vera-incidents/authorize",
        params=authorization_fields(),
        follow_redirects=False,
    )
    code = parse_qs(urlsplit(redirect.headers["location"]).query)["code"][0]

    response = client.post(
        "/oauth/vera-incidents/token", data=token_fields(code, **changes)
    )

    assert response.status_code == 400
    assert code not in response.text
    assert VERIFIER not in response.text


def test_authorization_code_is_single_use(host):
    client, _ = host
    code, _ = grant(client)

    response = client.post("/oauth/vera-incidents/token", data=token_fields(code))

    assert response.json() == {"error": "invalid_grant"}


@pytest.mark.parametrize(
    "changes",
    [
        {"redirect_uri": "https://attacker.example/callback"},
        {"client_id": "https://attacker.example/metadata"},
        {"code_challenge_method": "plain"},
        {"code_challenge": "bad"},
        {"resource": "https://attacker.example/mcp"},
        {"scope": "files:read"},
        {"response_type": "token"},
    ],
)
def test_authorization_never_redirects_invalid_requests(host, changes):
    client, _ = host

    response = client.get(
        "/oauth/vera-incidents/authorize",
        params=authorization_fields(**changes),
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "location" not in response.headers
    assert "attacker" not in response.text


@pytest.mark.parametrize(
    "callback",
    [
        "https://attacker.example/callback",
        "http://127.0.0.1:9900/callback?target=other",
        "http://user@localhost:9900/callback",
        "http://localhost/callback",
        "http://127.0.0.1:invalid/callback",
        "http://[::1",
        "file:///tmp/callback",
    ],
)
def test_dynamic_registration_rejects_external_or_ambiguous_callbacks(host, callback):
    client, _ = host

    response = client.post(
        "/oauth/vera-incidents/register", json={"redirect_uris": [callback]}
    )

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_client_metadata"}


def test_dynamic_public_loopback_client_uses_exact_registered_callback(host):
    client, _ = host
    callback = "http://127.0.0.1:9900/callback"
    registration = client.post(
        "/oauth/vera-incidents/register",
        json={
            "redirect_uris": [callback],
            "client_name": "Native host",
            "token_endpoint_auth_method": "none",
        },
    ).json()
    fields = authorization_fields(
        client_id=registration["client_id"], redirect_uri=callback
    )
    redirect = client.get(
        "/oauth/vera-incidents/authorize", params=fields, follow_redirects=False
    )
    code = parse_qs(urlsplit(redirect.headers["location"]).query)["code"][0]

    response = client.post(
        "/oauth/vera-incidents/token",
        data=token_fields(
            code, client_id=registration["client_id"], redirect_uri=callback
        ),
    )

    assert response.status_code == 200
    assert (
        rpc(client, response.json()["access_token"], "register").json()["result"][
            "isError"
        ]
        is False
    )


def test_expired_access_and_refresh_fail_closed(host, monkeypatch):
    client, _ = host
    now = oauth.time.time()
    _, tokens = grant(client)
    monkeypatch.setattr(oauth.time, "time", lambda: now + oauth.REFRESH_SECONDS + 10)

    response = client.post(
        "/oauth/vera-incidents/token",
        data={
            "grant_type": "refresh_token",
            "client_id": CLAUDE_CLIENT,
            "refresh_token": tokens["refresh_token"],
            "resource": RESOURCE,
        },
    )

    assert response.json() == {"error": "invalid_grant"}
    assert rpc(client, tokens["access_token"], "status").status_code == 401


def test_expired_authorization_code_fails_closed(host, monkeypatch):
    client, _ = host
    now = oauth.time.time()
    redirect = client.get(
        "/oauth/vera-incidents/authorize",
        params=authorization_fields(),
        follow_redirects=False,
    )
    code = parse_qs(urlsplit(redirect.headers["location"]).query)["code"][0]
    monkeypatch.setattr(oauth.time, "time", lambda: now + 301)

    response = client.post("/oauth/vera-incidents/token", data=token_fields(code))

    assert response.json() == {"error": "invalid_grant"}


def test_revoke_invalidates_access_and_refresh_without_token_disclosure(host):
    client, _ = host
    _, tokens = grant(client)

    response = client.post(
        "/oauth/vera-incidents/revoke",
        data={"client_id": CLAUDE_CLIENT, "token": tokens["refresh_token"]},
    )

    assert response.status_code == 200
    assert response.text == ""
    assert rpc(client, tokens["access_token"], "status").status_code == 401


def test_metadata_and_unauthenticated_challenge_use_fixed_resource(host):
    client, _ = host

    response = rpc(client, "wrong-token", "status")

    assert response.status_code == 401
    assert (
        RESOURCE
        in client.get("/.well-known/oauth-protected-resource/mcp/vera-incidents").text
    )
    assert "resource_metadata=" in response.headers["www-authenticate"]
    metadata = client.get(
        "/.well-known/oauth-authorization-server", headers={"Host": "attacker.example"}
    ).json()
    assert metadata["issuer"] == "https://mparanza.com"
    assert metadata["code_challenge_methods_supported"] == ["S256"]


def test_raw_codes_and_tokens_are_not_stored(host, tmp_path):
    client, _ = host
    code, tokens = grant(client)
    with sqlite3.connect(tmp_path / "incidents.sqlite3") as database:
        saved = "\n".join(database.iterdump())
    assert code not in saved
    assert tokens["access_token"] not in saved
    assert tokens["refresh_token"] not in saved


def test_saved_connector_links_local_reports_and_recovers_only_original_member(host):
    client, store = host
    _, tokens = grant(client)
    local = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    store.register(local)
    receipt = store.report(local, api.Report.model_validate(technical_report()))
    rpc(
        client,
        tokens["access_token"],
        "register",
        {"credentials": local.model_dump(mode="json")},
    )
    another = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    store.register(another)
    foreign = store.report(another, api.Report.model_validate(technical_report()))
    foreign_outcome = {
        "outcome_id": str(uuid4()),
        "report_id": foreign["report_id"],
        "incident_id": foreign["incident_id"],
        "remedy_revision": 1,
        "status": "recovered",
        "execution_succeeded": True,
        "original_task_verified": True,
    }

    rejected = rpc(
        client, tokens["access_token"], "outcome", {"outcome": foreign_outcome}
    )
    recovered = rpc(
        client,
        tokens["access_token"],
        "outcome",
        {
            "outcome": {
                **foreign_outcome,
                "outcome_id": str(uuid4()),
                "report_id": receipt["report_id"],
            }
        },
    )

    assert rejected.json()["result"]["isError"] is True
    assert recovered.json()["result"]["structuredContent"]["status"] == "recovered"
    assert store.status(another)["incidents"][0]["status"] == "open"


@pytest.mark.parametrize(
    "body,content_type",
    [
        ("client_id=a&client_id=b", "application/x-www-form-urlencoded"),
        ("not-a-form", "application/x-www-form-urlencoded"),
        ("{}", "application/json"),
        ("x=" + "a" * 9000, "application/x-www-form-urlencoded"),
    ],
)
def test_oauth_form_rejects_duplicate_malformed_or_oversized_fields(
    host, body, content_type
):
    client, _ = host

    response = client.post(
        "/oauth/vera-incidents/token",
        content=body,
        headers={"Content-Type": content_type},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request"}


@pytest.mark.parametrize(
    "grants", [["authorization_code"], ["refresh_token", "authorization_code"]]
)
def test_public_registration_accepts_supported_grants_in_any_order(host, grants):
    client, _ = host

    response = client.post(
        "/oauth/vera-incidents/register",
        json={"redirect_uris": [CLAUDE_CALLBACK], "grant_types": grants},
    )

    assert response.status_code == 201
    assert response.json()["token_endpoint_auth_method"] == "none"
