"""Local MCP tools deliver incidents through HTTPS, without a remote MCP server."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from modules.operational_incidents import api
from modules.operational_incidents.contracts import Remedy
from modules.run_receipts.signing import RunReceiptSigner
from modules.run_receipts.store import RunReceiptStore
from scripts.sync_reporting_runtime import reporting_tool_schemas
from tests.modules.operational_incidents.support import technical_report
from tests.plugins.test_incident_native_host import call, installed
from tests.plugins.test_native_workflow_usage import native_service, start_arguments
from tests.plugins.test_operational_incident_client import client

__all__: list[str] = []


@pytest.mark.parametrize("product", ("vera", "clara", "lucia"))
def test_native_migration_reports_new_failure_without_releasing_legacy_history(
    native_service, tmp_path, product
):
    store, endpoint, _, _ = native_service
    root = installed(tmp_path, endpoint, product)
    device = tmp_path / "device"
    call(root, device, f"{product}_incident_register", {})
    state_path = tmp_path / "unused-task-state/state.json"
    state = json.loads(state_path.read_text())
    old_report = {**technical_report(), "product": product}
    state["delivery_mode"] = "local-only"
    state["outbox"] = [{"operation": "report", "payload": {"report": old_report}}]
    state_path.write_text(json.dumps(state))
    new_report = {**technical_report(), "product": product}

    result = call(root, device, f"{product}_incident_report", {"report": new_report})

    retained = json.loads(state_path.read_text())
    assert result["structuredContent"]["report_id"] == new_report["report_id"]
    assert retained["outbox"][0]["payload"]["report"] == old_report
    assert retained["outbox"][0]["delivery_mode"] == "local-only"
    assert retained["credentials"] == state["credentials"]
    assert len(store.queue()[0]["reports"]) == 1
    assert store.queue()[0]["reports"][0]["report_id"] == new_report["report_id"]


def test_committed_native_tool_schemas_match_the_current_server_contract():
    root = Path(__file__).resolve().parents[2]
    actual = (
        root / "plugins/_shared/reporting-runtime/incident_tool_schemas.json"
    ).read_bytes()

    expected = reporting_tool_schemas()

    assert actual == expected


@pytest.mark.parametrize("product", ("vera", "clara", "lucia"))
def test_native_incident_delivery_retries_original_owner_without_mcp_http(
    native_service, tmp_path, product
):
    store, endpoint, _, requests = native_service
    root = installed(tmp_path, endpoint, product)
    device = tmp_path / "device"
    report = {**technical_report(), "product": product}
    original = call(root, device, f"{product}_incident_report", {"report": report})
    identity = json.loads((tmp_path / "unused-task-state/state.json").read_text())[
        "credentials"
    ]
    requests.clear()

    repeated = call(root, device, f"{product}_incident_report", {"report": report})

    assert original["structuredContent"]["report_id"] == report["report_id"]
    assert repeated["structuredContent"] == original["structuredContent"]
    assert (
        repeated["structuredContent"]["installation_id"] == identity["installation_id"]
    )
    assert identity["installation_key"] not in json.dumps(repeated)
    assert requests == []
    assert len(store.queue()) == 1
    assert store.registry()["linked_host_devices"] == 1


def test_native_report_survives_offline_restart_and_delivers_original_evidence(
    native_service, tmp_path
):
    store, endpoint, _, _ = native_service
    first_root = tmp_path / "offline"
    first_root.mkdir()
    offline = installed(first_root, "http://127.0.0.1:1", "lucia")
    device = tmp_path / "device"
    report = {**technical_report(), "product": "lucia"}
    pending = call(offline, device, "lucia_incident_report", {"report": report})
    retained = json.loads((tmp_path / "unused-task-state/state.json").read_text())
    second_root = tmp_path / "online"
    second_root.mkdir()
    online = installed(second_root, endpoint, "lucia")

    resumed = call(online, device, "lucia_incident_status", {})
    delivered = call(online, device, "lucia_incident_report", {"report": report})

    assert pending["structuredContent"]["delivery"] == "pending"
    assert (
        resumed["structuredContent"]["incidents"][0]["latest_report_id"]
        == report["report_id"]
    )
    assert delivered["structuredContent"]["report_id"] == report["report_id"]
    assert (
        delivered["structuredContent"]["installation_id"]
        == retained["credentials"]["installation_id"]
    )
    assert len(store.queue()) == 1


def test_native_reporting_rejects_supplied_credentials_before_creating_state(
    native_service, tmp_path
):
    _, endpoint, _, _ = native_service
    root = installed(tmp_path, endpoint, "clara")

    result = call(
        root,
        tmp_path / "device",
        "clara_incident_register",
        {
            "credentials": {
                "installation_id": str(uuid4()),
                "installation_key": uuid4().hex,
            },
        },
    )

    assert result["isError"] is True
    assert not (tmp_path / "unused-task-state/state.json").exists()


def test_native_reporting_preserves_original_payload_when_uuid_is_reused(
    native_service, tmp_path
):
    store, endpoint, _, requests = native_service
    root = installed(tmp_path, endpoint)
    device = tmp_path / "device"
    report = technical_report()
    call(root, device, "vera_incident_report", {"report": report})
    requests.clear()

    result = call(
        root,
        device,
        "vera_incident_report",
        {"report": {**report, "workflow": "another-workflow"}},
    )

    assert result["isError"] is True
    assert requests == []
    assert len(store.queue()) == 1


@pytest.mark.parametrize("product", ("vera", "clara", "lucia"))
def test_rejected_schema_can_be_corrected_under_the_same_report_and_owner(
    tmp_path, monkeypatch, product
):
    module, store, _ = client(tmp_path, monkeypatch, product)
    transport = module._post

    def post(operation, payload):
        try:
            return transport(operation, payload)
        except ValidationError as error:
            raise urllib.error.HTTPError(
                "https://fixture", 422, "Schema", {}, None
            ) from error

    monkeypatch.setattr(module, "_post", post)
    report = {**technical_report(), "product": product}
    rejected = module.native_request(
        {"operation": "report", "report": {**report, "invalid_field": True}}
    )

    corrected = module.native_request({"operation": "report", "report": report})

    assert rejected["delivery"] == "rejected"
    assert rejected["http_status"] == 422
    assert corrected["report_id"] == report["report_id"]
    assert corrected["installation_id"] == rejected["installation_id"]
    assert len(store.queue()) == 1
    retained = json.loads((tmp_path / "private/state.json").read_text())
    assert retained["outbox"] == []
    assert (
        retained["rejected_native_requests"][0]["payload"]["report"]["invalid_field"]
        is True
    )


def test_lost_ack_retains_evidence_and_retries_without_duplicate_or_owner_change(
    tmp_path, monkeypatch
):
    module, store, _ = client(tmp_path, monkeypatch)
    transport = module._post
    report = technical_report()

    def lose_response(operation, payload):
        reply = transport(operation, payload)
        if operation == "report":
            raise urllib.error.URLError("Synthetic lost response after commit")
        return reply

    monkeypatch.setattr(module, "_post", lose_response)
    pending = module.native_request({"operation": "report", "report": report})
    monkeypatch.setattr(module, "_post", transport)

    with pytest.raises(ValueError, match="different evidence"):
        module.native_request(
            {"operation": "report", "report": {**report, "workflow": "different"}}
        )
    delivered = module.native_request({"operation": "report", "report": report})

    assert pending["delivery"] == "pending"
    assert delivered["report_id"] == report["report_id"]
    assert delivered["installation_id"] == pending["installation_id"]
    assert len(store.queue()) == 1


def test_rejection_after_an_ambiguous_attempt_cannot_replace_the_original_payload(
    tmp_path, monkeypatch
):
    module, _, _ = client(tmp_path, monkeypatch)
    transport = module._post
    report = technical_report()

    def unavailable(operation, payload):
        if operation == "report":
            raise urllib.error.URLError("Synthetic unknown delivery")
        return transport(operation, payload)

    monkeypatch.setattr(module, "_post", unavailable)
    module.native_request({"operation": "report", "report": report})

    def later_schema_change(operation, payload):
        if operation == "report":
            raise urllib.error.HTTPError("https://fixture", 422, "Schema", {}, None)
        return transport(operation, payload)

    monkeypatch.setattr(module, "_post", later_schema_change)

    result = module.native_request({"operation": "report", "report": report})

    assert result["delivery"] == "pending"
    with pytest.raises(ValueError, match="different evidence"):
        module.native_request(
            {"operation": "report", "report": {**report, "workflow": "different"}}
        )


@pytest.mark.parametrize("product", ("vera", "clara", "lucia"))
def test_native_progress_and_outcome_close_only_the_original_verified_report(
    native_service, tmp_path, product
):
    store, endpoint, _, _ = native_service
    root = installed(tmp_path, endpoint, product)
    device = tmp_path / "device"
    receipt = call(
        root,
        device,
        f"{product}_incident_report",
        {"report": {**technical_report(), "product": product}},
    )["structuredContent"]
    remedy = store.remedy(
        receipt["incident_id"],
        Remedy(
            target_report_id=receipt["report_id"],
            kind="user-action",
            summary="Retry synthetic fixture",
            evidence="Synthetic fixture",
            instructions="Resume synthetic fixture",
            expected_outcome="Fixture succeeds",
        ),
    )
    binding = {
        "incident_id": receipt["incident_id"],
        "report_id": receipt["report_id"],
        "remedy_revision": remedy["revision"],
    }
    progress = call(
        root,
        device,
        f"{product}_incident_progress",
        {"progress": {**binding, "event_id": str(uuid4()), "kind": "retry-succeeded"}},
    )

    result = call(
        root,
        device,
        f"{product}_incident_outcome",
        {
            "outcome": {
                **binding,
                "outcome_id": str(uuid4()),
                "status": "recovered",
                "execution_succeeded": True,
                "original_task_verified": True,
            }
        },
    )

    assert progress["structuredContent"]["recorded"] is True
    assert result["structuredContent"]["status"] == "recovered"
    assert result["structuredContent"]["installation_id"] == receipt["installation_id"]
    assert store.queue() == []
    state = json.loads((tmp_path / "unused-task-state/state.json").read_text())
    assert state["outbox"] == []


@pytest.mark.parametrize("product", ("vera", "clara", "lucia"))
def test_native_workflow_stamp_retains_original_run_and_verifiable_product_receipt(
    native_service, tmp_path, monkeypatch, product
):
    _, endpoint, _, requests = native_service
    receipts = RunReceiptStore(sqlite_path=tmp_path / "receipts.sqlite3")
    signer = RunReceiptSigner(private_key=Ed25519PrivateKey.generate())
    monkeypatch.setattr(api, "get_run_receipt_store", lambda: receipts)
    monkeypatch.setattr(api, "get_run_receipt_signer", lambda: signer)
    root = installed(tmp_path, endpoint, product)
    device = tmp_path / "device"
    run_id = str(uuid4())
    call(root, device, f"{product}_workflow_usage", start_arguments(run_id, product))
    original_request = {
        "schema_version": 2,
        "product": product,
        "receipt_id": str(uuid4()),
        "plugin_version": "1.0.0",
        "report_sha256": "d" * 64,
    }

    result = call(
        root,
        device,
        f"{product}_workflow_stamp",
        {
            "run_id": run_id,
            "receipt_request": original_request,
        },
    )

    receipt = result["structuredContent"]
    retained = receipts.get(original_request["receipt_id"])
    assert retained.product == product
    assert signer.verify(retained.signed_payload, receipt["signature"])
    assert receipt["receipt_id"] == original_request["receipt_id"]
    assert requests[-1][0] == "workflow-stamp"
    assert requests[-1][1]["run_id"] == run_id
    assert requests[-1][1]["receipt_request"] == original_request
