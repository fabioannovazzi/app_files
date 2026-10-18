"""Shared reporting must retain exact product, owner, receipt and epoch boundaries."""

from __future__ import annotations

import base64
import hashlib
import os
from uuid import uuid4

import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo

from modules.operational_incidents import api
from modules.operational_incidents import store as store_module
from modules.operational_incidents.contracts import (
    Credentials,
    DeviceCredentials,
    Report,
)
from modules.operational_incidents.oauth import (
    CLAUDE_CALLBACK,
    CLAUDE_CLIENT,
    IncidentOAuth,
    OAuthError,
)
from modules.operational_incidents.store import IncidentConflict, IncidentStore
from modules.run_receipts import api as receipt_api
from modules.run_receipts.signing import RunReceiptSigner
from modules.run_receipts.store import RunReceiptStore
from modules.workflow_usage.contracts import WorkflowEvent
from modules.workflow_usage.repository import WorkflowConflict

BEFORE = "2026-10-18T08:00:00+00:00"
AFTER = "2026-10-18T09:00:00+00:00"
PIPELINES = {
    "vera": "business-planning",
    "clara": "business-planning",
    "lucia": "quesito-legale-fiscale",
}


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """Run the same contract against the real production adapter in CI."""
    dsn = os.environ.get("REPORTING_TEST_POSTGRES_DSN")
    if not dsn:
        yield IncidentStore(tmp_path / "incidents.sqlite3"), RunReceiptStore(
            sqlite_path=tmp_path / "receipts.sqlite3"
        )
        return
    schema = "reporting_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(
            psycopg.sql.SQL("CREATE SCHEMA {}").format(psycopg.sql.Identifier(schema))
        )
    monkeypatch.setenv(
        "PDP_DATABASE_URL", make_conninfo(dsn, options=f"-csearch_path={schema}")
    )
    try:
        yield IncidentStore(), RunReceiptStore()
    finally:
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(
                psycopg.sql.SQL("DROP SCHEMA {} CASCADE").format(
                    psycopg.sql.Identifier(schema)
                )
            )


@pytest.fixture
def service(stores, monkeypatch):
    store, receipts = stores
    signer = RunReceiptSigner(private_key=Ed25519PrivateKey.generate())
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(receipt_api.api_router)
    app.include_router(receipt_api.site_router)
    app.dependency_overrides[api.get_incident_store] = lambda: store
    app.dependency_overrides[receipt_api.get_run_receipt_store] = lambda: receipts
    app.dependency_overrides[receipt_api.get_run_receipt_signer] = lambda: signer
    monkeypatch.setattr(api, "get_run_receipt_store", lambda: receipts)
    monkeypatch.setattr(api, "get_run_receipt_signer", lambda: signer)
    monkeypatch.setattr(api, "_RATE_EVENTS", api.OrderedDict())
    monkeypatch.setattr(api, "_GLOBAL_EVENTS", api.deque())
    monkeypatch.setattr(store_module, "_now", lambda: BEFORE)
    device = DeviceCredentials(
        device_id=uuid4(), device_key=uuid4().hex, native_app="codex"
    )
    owners = {}
    for product in PIPELINES:
        owner = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
        store.register(owner, device, product=product)
        store.workflow_testing_reset([str(device.device_id)], product)
        owners[product] = owner
    monkeypatch.setattr(store_module, "_now", lambda: AFTER)
    return TestClient(app), store, receipts, signer, owners, device


def event(product, run_id, sequence, kind, **fields):
    return WorkflowEvent(
        product=product,
        run_id=run_id,
        event_id=uuid4(),
        sequence=sequence,
        kind=kind,
        occurred_at=AFTER,
        product_version="1.0.0",
        **fields,
    )


@pytest.mark.parametrize("product", PIPELINES)
def test_full_task_receipt_feedback_and_public_count_are_product_scoped(
    service, product
):
    client, store, receipts, signer, owners, _ = service
    owner = owners[product].model_dump(mode="json")
    run_id = uuid4()
    start = event(
        product,
        run_id,
        1,
        "started",
        pipeline=PIPELINES[product],
        host="codex",
        sample_kind="agent_test",
    )
    stamp = {
        "schema_version": 2,
        "product": product,
        "receipt_id": str(uuid4()),
        "plugin_version": "1.0.0",
        "report_sha256": "a" * 64,
    }

    # Drive the normal public API with one original run and its real signed proof.
    assert (
        client.post(
            "/api/operational-incidents/workflow-record",
            json={
                "credentials": owner,
                "event": start.model_dump(mode="json", exclude_none=True),
            },
        ).status_code
        == 200
    )
    response = client.post(f"/api/{product}/run-receipts", json=stamp)
    assert response.status_code == 201
    proof = response.json()
    retained = receipts.get(stamp["receipt_id"])
    assert retained.product == product
    assert signer.verify(retained.signed_payload, proof["signature"])
    attach = event(
        product,
        run_id,
        2,
        "receipt",
        receipt_id=stamp["receipt_id"],
        receipt_version="1.0.0",
        report_sha256=stamp["report_sha256"],
    )
    assert (
        client.post(
            "/api/operational-incidents/workflow-record",
            json={
                "credentials": owner,
                "event": attach.model_dump(mode="json", exclude_none=True),
            },
        ).status_code
        == 200
    )
    completion = event(product, run_id, 3, "completed")
    acknowledged = client.post(
        "/api/operational-incidents/workflow-record",
        json={
            "credentials": owner,
            "event": completion.model_dump(mode="json", exclude_none=True),
        },
    )
    assert acknowledged.status_code == 200
    answer = {
        "key": acknowledged.json()["feedback_url"].split("#")[1],
        "event_id": str(uuid4()),
        "stars": 2,
        "comment": "Synthetic acceptance feedback",
    }
    assert (
        client.post(
            f"/api/{product}/workflow-feedback/{run_id}", json=answer
        ).status_code
        == 200
    )

    projection = client.get(f"/api/{product}/testing-status").json()
    assert projection["pipelines"][PIPELINES[product]] == "agent"
    assert store.workflow_inspect(str(run_id))["run"]["feedback"]["stars"] == 2
    assert store.workflow_inspect(str(run_id))["run"]["product"] == product


def test_same_named_pipeline_does_not_promote_another_product(service):
    _, store, _, _, owners, _ = service
    run_id = uuid4()
    store.workflow_record(
        owners["clara"],
        event(
            "clara",
            run_id,
            1,
            "started",
            pipeline="business-planning",
            host="codex",
            sample_kind="user",
        ),
    )

    store.workflow_record(owners["clara"], event("clara", run_id, 2, "completed"))

    assert (
        store.workflow_testing("clara")["pipelines"]["business-planning"]["status"]
        == "agent"
    )
    assert (
        store.workflow_testing("vera")["pipelines"]["business-planning"]["status"]
        == "untried"
    )


def test_reset_another_product_preserves_vera_epoch_and_exact_run(service):
    _, store, _, _, owners, device = service
    run_id = uuid4()
    store.workflow_record(
        owners["vera"],
        event(
            "vera",
            run_id,
            1,
            "started",
            pipeline="business-planning",
            host="codex",
            sample_kind="user",
        ),
    )
    before = store.workflow_inspect(str(run_id))
    epoch = store.workflow_testing()["epoch_id"]

    store.workflow_testing_reset([str(device.device_id)], "lucia")

    assert store.workflow_inspect(str(run_id)) == before
    assert store.workflow_testing()["epoch_id"] == epoch


def test_product_cannot_be_reassigned_or_claimed_by_another_owner(service):
    _, store, _, _, owners, _ = service
    with pytest.raises(IncidentConflict, match="another product"):
        store.register(owners["vera"], product="clara")
    with pytest.raises(WorkflowConflict, match="another product"):
        store.workflow_record(
            owners["clara"],
            event(
                "vera",
                uuid4(),
                1,
                "started",
                pipeline="business-planning",
                host="codex",
                sample_kind="user",
            ),
        )


def oauth_grant(store, product):
    service = IncidentOAuth(store)
    verifier = "a" * 64
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    resource = f"https://mparanza.com/mcp/{product}-incidents"
    code = service.authorize(
        {
            "client_id": CLAUDE_CLIENT,
            "redirect_uri": CLAUDE_CALLBACK,
            "response_type": "code",
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "resource": resource,
        }
    )
    return service.token(
        {
            "client_id": CLAUDE_CLIENT,
            "redirect_uri": CLAUDE_CALLBACK,
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "resource": resource,
        }
    )


def test_saved_oauth_connection_cannot_cross_product_resources(service):
    client, store, _, _, _, _ = service
    grant = oauth_grant(store, "clara")
    headers = {"Authorization": "Bearer " + grant["access_token"]}
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}

    accepted = client.post("/mcp/clara-incidents", headers=headers, json=request)
    rejected = client.post("/mcp/lucia-incidents", headers=headers, json=request)

    assert accepted.status_code == 200
    assert accepted.json()["result"]["tools"][0]["name"] == "clara_workflow_record"
    assert rejected.status_code == 401
    with pytest.raises(OAuthError):
        IncidentOAuth(store).token(
            {
                "client_id": CLAUDE_CLIENT,
                "grant_type": "refresh_token",
                "refresh_token": grant["refresh_token"],
                "resource": "https://mparanza.com/mcp/vera-incidents",
            }
        )


def test_clara_receipt_cannot_attach_to_lucia_task(service):
    client, store, _, _, owners, _ = service
    run_id = uuid4()
    store.workflow_record(
        owners["lucia"],
        event(
            "lucia",
            run_id,
            1,
            "started",
            pipeline=PIPELINES["lucia"],
            host="codex",
            sample_kind="user",
        ),
    )
    receipt_id = uuid4()
    assert (
        client.post(
            "/api/clara/run-receipts",
            json={
                "schema_version": 2,
                "product": "clara",
                "receipt_id": str(receipt_id),
                "plugin_version": "1.0.0",
                "report_sha256": "b" * 64,
            },
        ).status_code
        == 201
    )
    attach = event(
        "lucia",
        run_id,
        2,
        "receipt",
        receipt_id=receipt_id,
        receipt_version="1.0.0",
        report_sha256="b" * 64,
    )

    result = client.post(
        "/api/operational-incidents/workflow-record",
        json={
            "credentials": owners["lucia"].model_dump(mode="json"),
            "event": attach.model_dump(mode="json", exclude_none=True),
        },
    )

    assert result.status_code == 409
    assert store.workflow_inspect(str(run_id))["run"]["receipts"] == []
