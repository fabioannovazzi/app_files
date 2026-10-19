from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.operational_incidents import api as incidents
from modules.operational_incidents.contracts import Credentials, DeviceCredentials
from modules.operational_incidents.store import IncidentStore
from modules.run_receipts import api
from modules.run_receipts.signing import RunReceiptSigner
from modules.run_receipts.store import RunReceiptStore
from tests.modules.workflow_usage.test_product_parity import stores


def archive_client(tmp_path: Path, monkeypatch, *, linked: bool = True, databases=None):
    """Exercise real authentication, durable stores and signing without a network."""
    owner = Credentials(installation_id=uuid4(), installation_key="a" * 40)
    device = DeviceCredentials(device_id=uuid4(), device_key="b" * 40)
    incident_store = (
        databases[0]
        if databases
        else IncidentStore(sqlite_path=tmp_path / "owners.sqlite3")
    )
    incident_store.register(owner, device if linked else None, product="vera")
    receipts = (
        databases[1]
        if databases
        else RunReceiptStore(sqlite_path=tmp_path / "proofs.sqlite3")
    )
    signer = RunReceiptSigner(private_key=Ed25519PrivateKey.generate())
    monkeypatch.setattr(incidents, "get_run_receipt_store", lambda: receipts)
    monkeypatch.setattr(incidents, "get_run_receipt_signer", lambda: signer)
    monkeypatch.setattr(incidents, "_admit", lambda source: None)
    app = FastAPI()
    app.include_router(incidents.router)
    app.include_router(api.api_router)
    app.dependency_overrides[incidents.get_incident_store] = lambda: incident_store
    app.dependency_overrides[api.get_run_receipt_store] = lambda: receipts
    app.dependency_overrides[api.get_run_receipt_signer] = lambda: signer
    app.dependency_overrides[api.get_run_receipt_rate_limiter] = (
        lambda: api.RunReceiptRateLimiter()
    )
    request = {
        "schema_version": 3,
        "product": "vera",
        "receipt_id": str(uuid4()),
        "plugin_version": "0.1.426",
        "report_sha256": "c" * 64,
        "user_id": str(owner.installation_id),
        "archive_run_id": "run_" + "d" * 24,
        "report_revision": 1,
    }
    return TestClient(app), owner, request, receipts, signer


def test_archive_receipt_signs_and_verifies_same_owner_run_and_report(
    tmp_path, monkeypatch
):
    client, owner, request, store, signer = archive_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/operational-incidents/archive-stamp",
        json={
            "credentials": owner.model_dump(mode="json"),
            "receipt_request": request,
        },
    )

    assert response.status_code == 200, response.text
    record = store.get(request["receipt_id"])
    assert record.user_id == str(owner.installation_id)
    assert record.archive_run_id == request["archive_run_id"]
    assert signer.verify(record.signed_payload, record.signature)
    verified = client.get(
        f"/api/vera/run-receipts/{record.receipt_id}",
        params={
            "sha256": record.report_sha256,
            "user_id": record.user_id,
            "archive_run_id": record.archive_run_id,
            "report_revision": 1,
        },
    )
    assert verified.status_code == 200
    assert verified.json() == response.json()


@pytest.mark.parametrize(
    "mismatch",
    ["user_id", "archive_run_id", "report_sha256", "report_revision", "missing_owner"],
)
def test_archive_verification_rejects_wrong_binding(tmp_path, monkeypatch, mismatch):
    client, owner, request, store, signer = archive_client(tmp_path, monkeypatch)
    client.post(
        "/api/operational-incidents/archive-stamp",
        json={
            "credentials": owner.model_dump(mode="json"),
            "receipt_request": request,
        },
    ).raise_for_status()
    params = {
        "sha256": request["report_sha256"],
        "user_id": request["user_id"],
        "archive_run_id": request["archive_run_id"],
        "report_revision": 1,
    }
    replacements = {
        "user_id": str(uuid4()),
        "archive_run_id": "run_" + "e" * 24,
        "report_sha256": "f" * 64,
        "report_revision": 2,
    }
    if mismatch == "missing_owner":
        params.pop("user_id")
    else:
        params["sha256" if mismatch == "report_sha256" else mismatch] = replacements[
            mismatch
        ]

    response = client.get(
        f"/api/vera/run-receipts/{request['receipt_id']}", params=params
    )

    assert response.status_code == 404


def test_anonymous_endpoint_cannot_issue_archive_receipt(tmp_path, monkeypatch):
    client, owner, request, store, signer = archive_client(tmp_path, monkeypatch)

    response = client.post("/api/vera/run-receipts", json=request)

    assert response.status_code == 403
    assert store.get(request["receipt_id"]) is None


def test_foreign_user_id_cannot_be_stamped_by_authenticated_owner(
    tmp_path, monkeypatch
):
    client, owner, request, store, signer = archive_client(tmp_path, monkeypatch)
    request["user_id"] = str(uuid4())

    response = client.post(
        "/api/operational-incidents/archive-stamp",
        json={
            "credentials": owner.model_dump(mode="json"),
            "receipt_request": request,
        },
    )

    assert response.status_code == 403
    assert store.get(request["receipt_id"]) is None


def test_unlinked_installation_cannot_claim_machine_binding(tmp_path, monkeypatch):
    client, owner, request, store, signer = archive_client(
        tmp_path, monkeypatch, linked=False
    )

    response = client.post(
        "/api/operational-incidents/archive-stamp",
        json={
            "credentials": owner.model_dump(mode="json"),
            "receipt_request": request,
        },
    )

    assert response.status_code == 409
    assert store.get(request["receipt_id"]) is None


def test_archive_receipt_retry_is_identical_and_modified_report_is_rejected(
    tmp_path, monkeypatch
):
    client, owner, request, store, signer = archive_client(tmp_path, monkeypatch)
    envelope = {
        "credentials": owner.model_dump(mode="json"),
        "receipt_request": request,
    }
    original = client.post("/api/operational-incidents/archive-stamp", json=envelope)

    retry = client.post("/api/operational-incidents/archive-stamp", json=envelope)

    assert retry.json() == original.json()
    request["report_sha256"] = "e" * 64
    conflict = client.post("/api/operational-incidents/archive-stamp", json=envelope)
    assert conflict.status_code == 409
    assert store.get(request["receipt_id"]).report_sha256 == "c" * 64


def test_concurrent_receipt_ids_cannot_claim_the_same_owner_run_revision(
    tmp_path, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    client, owner, request, store, signer = archive_client(tmp_path, monkeypatch)
    gate = Barrier(2)
    alternate = {**request, "receipt_id": str(uuid4())}

    def submit(payload):
        gate.wait(timeout=10)
        return client.post(
            "/api/operational-incidents/archive-stamp",
            json={
                "credentials": owner.model_dump(mode="json"),
                "receipt_request": payload,
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(submit, [request, alternate]))

    assert sorted(outcomes) == [200, 409]
    assert store.inventory()["total"] == 1


def test_archive_binding_uses_production_database_adapter(
    tmp_path, monkeypatch, stores
):
    client, owner, request, store, signer = archive_client(
        tmp_path, monkeypatch, databases=stores
    )
    envelope = {
        "credentials": owner.model_dump(mode="json"),
        "receipt_request": request,
    }

    result = client.post("/api/operational-incidents/archive-stamp", json=envelope)

    assert result.status_code == 200, result.text
    assert store.get(request["receipt_id"]).archive_run_id == request["archive_run_id"]
    request["receipt_id"] = str(uuid4())
    assert (
        client.post(
            "/api/operational-incidents/archive-stamp", json=envelope
        ).status_code
        == 409
    )
    assert store.inventory()["total"] == 1
