"""Report through HTTPS browser sessions without the plugin's local runtime."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.operational_incidents import api, recovery
from modules.operational_incidents.contracts import Credentials, Remedy
from modules.operational_incidents.store import IncidentStore
from modules.run_receipts.signing import RunReceiptSigner
from modules.run_receipts.store import RunReceiptStore
from tests.modules.operational_incidents.support import technical_report

__all__: list[str] = []

PRODUCTS = ("vera", "clara", "lucia")
HEADERS = {"Origin": "https://mparanza.com", "X-Mparanza-Recovery": "1"}


@pytest.fixture
def service(tmp_path, monkeypatch):
    database = tmp_path / "incidents.sqlite3"
    store = IncidentStore(database)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_incident_store] = lambda: store
    monkeypatch.setattr(api, "_RATE_EVENTS", api.OrderedDict())
    monkeypatch.setattr(api, "_GLOBAL_EVENTS", api.deque())
    with TestClient(app, base_url="https://mparanza.com") as client:
        yield client, store, database


def request(client, product, operation, arguments=None):
    return client.post(
        f"/api/{product}/incident-recovery/{operation}",
        json=arguments or {},
        headers=HEADERS,
    )


@pytest.mark.parametrize("product", PRODUCTS)
def test_browser_reopens_same_identity_without_exposing_cookie_capability(
    service, product
):
    client, _, database = service
    first = client.get(f"/{product}/incident-recovery")
    token = client.cookies[f"__Host-mpr_{product}_recovery"]
    before = request(client, product, "register").json()

    reopened = client.get(f"/{product}/incident-recovery")
    after = request(client, product, "register").json()

    assert first.status_code == reopened.status_code == 200
    assert before["installation_id"] == after["installation_id"]
    assert "HttpOnly" in first.headers["set-cookie"]
    assert "Secure" in first.headers["set-cookie"]
    assert "SameSite=strict" in first.headers["set-cookie"]
    assert token not in first.text
    assert "credentials" not in after
    with sqlite3.connect(database) as connection:
        saved = connection.execute(
            "SELECT token_hash FROM operational_recovery_sessions"
        ).fetchone()[0]
    assert saved == hashlib.sha256(token.encode()).hexdigest()


@pytest.mark.parametrize("product", PRODUCTS)
def test_browser_retry_after_lost_ack_keeps_one_original_report(service, product):
    client, store, _ = service
    client.get(f"/{product}/incident-recovery")
    report = {**technical_report(), "product": product}
    original = request(client, product, "report", {"report": report}).json()

    repeated = request(client, product, "report", {"report": report})

    assert repeated.status_code == 200
    assert repeated.json()["report_id"] == original["report_id"] == report["report_id"]
    assert repeated.json()["installation_id"] == original["installation_id"]
    assert len(store.queue()) == 1


@pytest.mark.parametrize("product", PRODUCTS)
def test_browser_links_existing_local_report_owner_without_replacing_it(
    service, product
):
    client, store, _ = service
    owner = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    store.register(owner, product=product)
    client.get(f"/{product}/incident-recovery")
    report = {**technical_report(), "product": product}

    result = request(
        client,
        product,
        "report",
        {
            "credentials": owner.model_dump(mode="json"),
            "report": report,
        },
    )

    assert result.status_code == 200
    assert result.json()["installation_id"] == str(owner.installation_id)
    assert owner.installation_key not in result.text
    assert (
        store.status(owner)["incidents"][0]["latest_report_id"] == report["report_id"]
    )


def test_foreign_product_cookie_cannot_read_another_products_history(service):
    client, _, _ = service
    client.get("/vera/incident-recovery")
    client.cookies.set(
        "__Host-mpr_clara_recovery", client.cookies["__Host-mpr_vera_recovery"]
    )

    result = request(client, "clara", "status")

    assert result.status_code == 401


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://other.example", "X-Mparanza-Recovery": "1"},
        {"Origin": "https://mparanza.com"},
    ],
)
def test_cross_origin_write_is_rejected_before_reporting(service, headers):
    client, store, _ = service
    client.get("/vera/incident-recovery")

    result = client.post(
        "/api/vera/incident-recovery/report",
        headers=headers,
        json={"report": technical_report()},
    )

    assert result.status_code == 403
    assert store.queue() == []


def test_expired_session_is_not_silently_replaced_with_a_new_owner(
    service, monkeypatch
):
    client, _, _ = service
    client.get("/lucia/incident-recovery")
    original = client.cookies["__Host-mpr_lucia_recovery"]
    expires = recovery.time.time() + recovery.SESSION_SECONDS + 1
    monkeypatch.setattr(recovery.time, "time", lambda: expires)

    result = client.get("/lucia/incident-recovery")

    assert result.status_code == 200
    assert "Nessuna nuova identità" in result.text
    assert request(client, "lucia", "status").status_code == 401
    assert "set-cookie" not in result.headers
    assert client.cookies["__Host-mpr_lucia_recovery"] == original


def test_unrelated_client_content_is_rejected_without_echoing_it(service):
    client, store, _ = service
    client.get("/clara/incident-recovery")

    result = request(
        client, "clara", "report", {"client_document": "private case text"}
    )

    assert result.status_code == 422
    assert "private case text" not in result.text
    assert store.queue() == []


@pytest.mark.parametrize("product", PRODUCTS)
def test_browser_delivers_remedy_progress_and_verified_recovery(service, product):
    client, store, _ = service
    client.get(f"/{product}/incident-recovery")
    receipt = request(
        client,
        product,
        "report",
        {
            "report": {**technical_report(), "product": product},
        },
    ).json()
    remedy = store.remedy(
        receipt["incident_id"],
        Remedy(
            target_report_id=receipt["report_id"],
            kind="user-action",
            summary="Retry the synthetic operation",
            evidence="Synthetic fixture failure",
            instructions="Resume the retained fixture",
            expected_outcome="Fixture succeeds",
        ),
    )
    status = request(client, product, "status")
    progress = request(
        client,
        product,
        "progress",
        {
            "progress": {
                "event_id": str(uuid4()),
                "incident_id": receipt["incident_id"],
                "report_id": receipt["report_id"],
                "remedy_revision": remedy["revision"],
                "kind": "retry-succeeded",
            }
        },
    )

    result = request(
        client,
        product,
        "outcome",
        {
            "outcome": {
                "outcome_id": str(uuid4()),
                "incident_id": receipt["incident_id"],
                "report_id": receipt["report_id"],
                "remedy_revision": remedy["revision"],
                "status": "recovered",
                "execution_succeeded": True,
                "original_task_verified": True,
            }
        },
    )

    assert (
        status.json()["incidents"][0]["remedy"]["instructions"]
        == "Resume the retained fixture"
    )
    assert progress.status_code == 200
    assert result.status_code == 200
    assert result.json()["status"] == "recovered"
    assert store.queue() == []


@pytest.mark.parametrize(
    "product,pipeline",
    [
        ("vera", "journal-bank-reconciliation"),
        ("clara", "reporting-engine"),
        ("lucia", "contenzioso-tributario"),
    ],
)
def test_browser_workflow_stamp_and_status_preserve_product_and_original_run(
    service, tmp_path, monkeypatch, product, pipeline
):
    client, _, _ = service
    receipts = RunReceiptStore(sqlite_path=tmp_path / "receipts.sqlite3")
    signer = RunReceiptSigner(private_key=Ed25519PrivateKey.generate())
    monkeypatch.setattr(api, "get_run_receipt_store", lambda: receipts)
    monkeypatch.setattr(api, "get_run_receipt_signer", lambda: signer)
    client.get(f"/{product}/incident-recovery")
    run_id = str(uuid4())
    started = request(
        client,
        product,
        "workflow-record",
        {
            "event": {
                "schema_version": 1,
                "product": product,
                "event_id": str(uuid4()),
                "run_id": run_id,
                "sequence": 1,
                "kind": "started",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "product_version": "1.0.0",
                "pipeline": pipeline,
                "host": "codex",
                "sample_kind": "agent_test",
            }
        },
    )
    receipt_request = {
        "schema_version": 2,
        "product": product,
        "receipt_id": str(uuid4()),
        "plugin_version": "1.0.0",
        "report_sha256": "d" * 64,
    }

    stamped = request(
        client,
        product,
        "workflow-stamp",
        {"run_id": run_id, "receipt_request": receipt_request},
    )

    assert started.status_code == 200
    assert stamped.status_code == 200
    retained = receipts.get(receipt_request["receipt_id"])
    assert retained.product == product
    assert signer.verify(retained.signed_payload, stamped.json()["signature"])
    state = request(client, product, "workflow-status", {"run_id": run_id})
    assert state.json()["run_id"] == run_id
    assert state.json()["product"] == product


@pytest.mark.parametrize("product", PRODUCTS)
def test_retired_mcp_transfer_code_cannot_restore_browser(service, product):
    client, _, _ = service
    response = request(
        client, product, "restore-session", {"transfer_code": "retired-synthetic-code"}
    )
    assert response.status_code == 422
    assert "set-cookie" not in response.headers


def test_local_credentials_cannot_restore_another_product(service):
    client, store, _ = service
    owner = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    store.register(owner, product="clara")
    credentials = {"credentials": owner.model_dump(mode="json")}

    rejected = request(client, "lucia", "restore-session", credentials)
    restored = request(client, "clara", "restore-session", credentials)

    assert rejected.status_code == 401
    assert "set-cookie" not in rejected.headers
    assert restored.status_code == 200
    assert restored.json()["installation_id"] == str(owner.installation_id)


@pytest.mark.parametrize("product", PRODUCTS)
def test_restore_preserves_browser_and_local_reports_with_original_owners(
    service, product
):
    client, store, _ = service
    owner = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    store.register(owner, product=product)
    local_report = {**technical_report(), "product": product}
    original = store.report(owner, api.Report.model_validate(local_report))
    client.get(f"/{product}/incident-recovery")
    browser_report = {**technical_report(), "product": product}
    browser = request(client, product, "report", {"report": browser_report}).json()
    restored = request(
        client,
        product,
        "restore-session",
        {"credentials": owner.model_dump(mode="json")},
    )

    assert restored.status_code == 200
    assert restored.json()["installation_id"] == original["installation_id"]
    status = request(client, product, "status").json()
    owners = {
        row["latest_report_id"]: row["installation_id"] for row in status["incidents"]
    }
    assert owners == {
        local_report["report_id"]: original["installation_id"],
        browser_report["report_id"]: browser["installation_id"],
    }
    assert len(store.queue()[0]["deliveries"]) == 2


@pytest.mark.parametrize("product", PRODUCTS)
def test_local_capability_recovers_expired_browser_without_remote_mcp(
    service, monkeypatch, product
):
    client, store, _ = service
    owner = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    store.register(owner, product=product)
    original = request(
        client,
        product,
        "restore-session",
        {"credentials": owner.model_dump(mode="json")},
    )
    report = {**technical_report(), "product": product}
    request(client, product, "report", {"report": report})
    expires = recovery.time.time() + recovery.SESSION_SECONDS + 1
    monkeypatch.setattr(recovery.time, "time", lambda: expires)

    restored = request(
        client,
        product,
        "restore-session",
        {"credentials": owner.model_dump(mode="json")},
    )

    assert restored.status_code == 200
    assert restored.json()["installation_id"] == original.json()["installation_id"]
    assert restored.json()["installation_id"] == str(owner.installation_id)
    assert owner.installation_key not in restored.text
    status = request(client, product, "status").json()
    assert status["incidents"][0]["latest_report_id"] == report["report_id"]


def test_incorrect_local_capability_cannot_recover_existing_identity(service):
    client, store, _ = service
    owner = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    store.register(owner, product="lucia")

    result = request(
        client,
        "lucia",
        "restore-session",
        {
            "credentials": {
                **owner.model_dump(mode="json"),
                "installation_key": uuid4().hex,
            }
        },
    )

    assert result.status_code == 401
    assert "set-cookie" not in result.headers


@pytest.mark.parametrize("product", PRODUCTS)
def test_browser_exposes_product_bound_schema_without_local_tools_or_credentials(
    service, product
):
    client, _, _ = service

    result = request(client, product, "schema", {"operation": "report"})

    assert result.status_code == 200
    schema = result.json()["input_schema"]
    assert schema["required"] == ["report"]
    assert "product_version" in schema["$defs"]["Report"]["properties"]
    assert schema["$defs"]["Report"]["properties"]["product"]["const"] == product
    assert "evidence_source" in schema["$defs"]["Diagnostic"]["required"]
    assert "RecoveryEvent" not in schema["$defs"]
    assert "set-cookie" not in result.headers


def test_browser_links_local_reports_and_recovers_only_original_member(service):
    client, store, _ = service
    client.get("/vera/incident-recovery")
    local = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    store.register(local)
    receipt = store.report(local, api.Report.model_validate(technical_report()))
    request(
        client,
        "vera",
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

    rejected = request(client, "vera", "outcome", {"outcome": foreign_outcome})
    recovered = request(
        client,
        "vera",
        "outcome",
        {
            "outcome": {
                **foreign_outcome,
                "outcome_id": str(uuid4()),
                "report_id": receipt["report_id"],
            }
        },
    )

    assert rejected.status_code == 404
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "recovered"
    assert store.status(another)["incidents"][0]["status"] == "open"
