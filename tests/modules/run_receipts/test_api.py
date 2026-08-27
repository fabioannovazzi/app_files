from __future__ import annotations

import base64
import sqlite3
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.run_receipts import api
from modules.run_receipts.signing import RunReceiptSigner, canonical_receipt_bytes
from modules.run_receipts.store import RunReceiptStore


def _client(
    tmp_path: Path,
) -> tuple[TestClient, RunReceiptStore, RunReceiptSigner, Path]:
    database_path = tmp_path / "run-receipts.sqlite3"
    store = RunReceiptStore(sqlite_path=database_path)
    signer = RunReceiptSigner(private_key=Ed25519PrivateKey.generate())
    app = FastAPI()
    app.include_router(api.site_router)
    app.include_router(api.api_router)
    app.dependency_overrides[api.get_run_receipt_store] = lambda: store
    app.dependency_overrides[api.get_run_receipt_signer] = lambda: signer
    app.dependency_overrides[api.get_run_receipt_rate_limiter] = (
        lambda: api.RunReceiptRateLimiter()
    )
    return TestClient(app), store, signer, database_path


def _payload(*, receipt_id: str | None = None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "receipt_id": receipt_id or str(uuid4()),
        "plugin_version": "0.1.183",
        "report_sha256": "a" * 64,
    }


def test_stamp_persists_only_minimal_signed_record_and_verifies(
    tmp_path: Path,
) -> None:
    client, store, signer, database_path = _client(tmp_path)
    payload = _payload()

    stamped = client.post("/api/vera/run-receipts", json=payload)
    proof = stamped.json()
    verified = client.get(
        f"/api/vera/run-receipts/{payload['receipt_id']}",
        params={"sha256": payload["report_sha256"]},
    )
    record = store.get(str(payload["receipt_id"]))
    assert record is not None

    assert stamped.status_code == 201
    assert verified.status_code == 200
    assert verified.json() == proof
    assert proof["signature_valid"] is True
    assert proof["algorithm"] == "Ed25519"
    assert signer.verify(record.signed_payload, record.signature) is True
    portable_signed_payload = {
        key: proof[key]
        for key in (
            "schema_version",
            "receipt_id",
            "plugin_version",
            "report_sha256",
            "stamped_at",
            "key_id",
        )
    }
    public_key = Ed25519PublicKey.from_public_bytes(
        base64.urlsafe_b64decode(proof["public_key"] + "==")
    )
    public_key.verify(
        base64.urlsafe_b64decode(proof["signature"] + "=="),
        canonical_receipt_bytes(portable_signed_payload),
    )
    assert proof["verification_url"].endswith(
        f"/{payload['receipt_id']}?sha256={payload['report_sha256']}"
    )
    with sqlite3.connect(database_path) as connection:
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(mparanza_vera_run_receipts)"
            ).fetchall()
        }
    assert columns == {
        "receipt_id",
        "plugin_version",
        "report_sha256",
        "stamped_at",
        "key_id",
        "signature",
    }


def test_stamp_forbids_case_or_report_fields(tmp_path: Path) -> None:
    client, _store, _signer, _database_path = _client(tmp_path)
    payload = _payload()
    payload["client_name"] = "Synthetic Client"
    payload["report"] = {"professional_purpose": "Should stay local"}

    response = client.post("/api/vera/run-receipts", json=payload)

    assert response.status_code == 422
    locations = {tuple(item["loc"]) for item in response.json()["detail"]}
    assert ("body", "client_name") in locations
    assert ("body", "report") in locations


def test_stamp_retry_is_idempotent_and_changed_digest_conflicts(
    tmp_path: Path,
) -> None:
    client, _store, _signer, _database_path = _client(tmp_path)
    receipt_id = str(uuid4())
    payload = _payload(receipt_id=receipt_id)

    first = client.post("/api/vera/run-receipts", json=payload)
    retried = client.post("/api/vera/run-receipts", json=payload)
    payload["report_sha256"] = "b" * 64
    conflict = client.post("/api/vera/run-receipts", json=payload)

    assert first.status_code == 201
    assert retried.status_code == 201
    assert retried.json() == first.json()
    assert conflict.status_code == 409


def test_verification_requires_matching_id_and_digest(tmp_path: Path) -> None:
    client, _store, _signer, _database_path = _client(tmp_path)
    payload = _payload()
    client.post("/api/vera/run-receipts", json=payload)

    wrong_digest = client.get(
        f"/api/vera/run-receipts/{payload['receipt_id']}",
        params={"sha256": "b" * 64},
    )
    unknown_id = client.get(
        f"/api/vera/run-receipts/{uuid4()}",
        params={"sha256": payload["report_sha256"]},
    )

    assert wrong_digest.status_code == 404
    assert unknown_id.status_code == 404


def test_customer_page_states_proof_and_limits_without_case_content(
    tmp_path: Path,
) -> None:
    client, _store, _signer, _database_path = _client(tmp_path)
    payload = _payload()
    client.post("/api/vera/run-receipts", json=payload)

    response = client.get(
        f"/verify/vera-run-receipt/{payload['receipt_id']}",
        params={"sha256": payload["report_sha256"], "lang": "en"},
    )

    assert response.status_code == 200
    template = (Path("templates") / "vera_run_receipt_verify.html").read_text(
        encoding="utf-8"
    )
    assert "{{ copy.verified }}" in template
    assert "does not prove who submitted the digest" in api._VERIFY_COPY["en"]["limit"]
    assert "does not retain the report" in api._VERIFY_COPY["en"]["boundary"]
    assert "client_name" not in template


def test_rate_limit_and_body_bound_fail_before_stamping(tmp_path: Path) -> None:
    client, store, _signer, _database_path = _client(tmp_path)
    limiter = api.RunReceiptRateLimiter(
        stamp_per_source=1,
        stamp_global=1,
    )
    client.app.dependency_overrides[api.get_run_receipt_rate_limiter] = lambda: limiter

    first = client.post("/api/vera/run-receipts", json=_payload())
    limited_payload = _payload()
    limited = client.post("/api/vera/run-receipts", json=limited_payload)
    oversized = client.post(
        "/api/vera/run-receipts",
        content=b"{" + b" " * api.MAX_REQUEST_BODY_BYTES + b"}",
        headers={"content-type": "application/json"},
    )

    assert first.status_code == 201
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert oversized.status_code == 413
    assert store.get(str(limited_payload["receipt_id"])) is None
