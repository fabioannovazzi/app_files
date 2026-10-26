"""Restricted evidence stays local while unrelated authorized work can report."""

from __future__ import annotations

import hashlib
import json
import urllib.error
from pathlib import Path
from uuid import uuid4

import pytest

from tests.plugins.test_incident_task_scope import client, retained_state

__all__: list[str] = []
PRODUCTS = ("vera", "clara", "lucia")


def restricted_report(module, monkeypatch, task_id=None):
    """Create real retained evidence through the public reporting entrypoint."""
    with monkeypatch.context() as local:
        local.setenv("MPARANZA_INCIDENT_DELIVERY", "local-only")
        if task_id:
            local.setenv("MPARANZA_INCIDENT_TASK_ID", task_id)
        return module.report_failure(
            "journal-sampling", "execution", "Controlled failure"
        )


def authorization(module, report, task_id=None):
    raw = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {
        "installation_id": module.reporting_credentials()["installation_id"],
        "task_id": task_id,
        "report_id": report["report_id"],
        "report_sha256": hashlib.sha256(raw.encode()).hexdigest(),
    }


@pytest.mark.parametrize("product", PRODUCTS)
@pytest.mark.parametrize("with_task", [False, True])
def test_new_automatic_task_delivers_without_releasing_local_only_history(
    tmp_path, monkeypatch, product, with_task
):
    module, store, _ = client(tmp_path, monkeypatch, product)
    restricted_report(module, monkeypatch, str(uuid4()) if with_task else None)
    original = retained_state(module)
    if with_task:
        monkeypatch.setenv("MPARANZA_INCIDENT_TASK_ID", str(uuid4()))

    result = module.report_failure("journal-sampling", "execution", "New task failure")

    assert result["reporting"] == "delivered"
    assert retained_state(module)["outbox"] == original["outbox"]
    assert retained_state(module)["credentials"] == original["credentials"]
    assert store.queue()[0]["reports"][0]["report_id"] == result["report"]["report_id"]


@pytest.mark.parametrize("product", PRODUCTS)
def test_resumed_local_only_task_keeps_new_reports_local(
    tmp_path, monkeypatch, product
):
    module, store, _ = client(tmp_path, monkeypatch, product)
    task_id = str(uuid4())
    restricted_report(module, monkeypatch, task_id)
    monkeypatch.setenv("MPARANZA_INCIDENT_TASK_ID", task_id)

    result = module.report_failure("journal-sampling", "execution", "Second failure")

    assert result["reporting"] == "queued"
    assert store.queue() == []
    assert retained_state(module)["outbox"][1]["delivery_mode"] == "local-only"


@pytest.mark.parametrize("product", PRODUCTS)
def test_native_retry_cannot_override_saved_local_only_permission(
    tmp_path, monkeypatch, product
):
    module, store, _ = client(tmp_path, monkeypatch, product)
    original = restricted_report(module, monkeypatch)

    result = module.native_request(
        {"operation": "report", "report": original["report"]}
    )

    assert result["delivery"] == "local-only"
    assert store.queue() == []
    assert (
        retained_state(module)["outbox"][0]["payload"]["report"] == original["report"]
    )


@pytest.mark.parametrize("product", PRODUCTS)
def test_native_supplement_of_restricted_report_also_stays_local(
    tmp_path, monkeypatch, product
):
    module, store, _ = client(tmp_path, monkeypatch, product)
    original = restricted_report(module, monkeypatch)
    supplement = {
        **original["report"],
        "report_id": str(uuid4()),
        "evidence_for_report_id": original["report"]["report_id"],
    }

    result = module.native_request({"operation": "report", "report": supplement})

    assert result["delivery"] == "local-only"
    assert store.queue() == []


@pytest.mark.parametrize("product", PRODUCTS)
def test_legacy_global_mode_migrates_existing_queue_without_blocking_new_task(
    tmp_path, monkeypatch, product
):
    module, store, _ = client(tmp_path, monkeypatch, product)
    old = restricted_report(module, monkeypatch)
    path = Path(module.local_context()["outbox_path"])
    legacy = json.loads(path.read_text())
    legacy["delivery_mode"] = "local-only"
    legacy["outbox"][0].pop("delivery_mode")
    path.write_text(json.dumps(legacy))
    monkeypatch.setenv("MPARANZA_INCIDENT_TASK_ID", str(uuid4()))

    current = module.report_failure("journal-sampling", "execution", "Current failure")

    saved = retained_state(module)
    assert current["reporting"] == "delivered"
    assert saved["outbox"][0]["payload"]["report"] == old["report"]
    assert saved["outbox"][0]["delivery_mode"] == "local-only"
    assert saved["credentials"] == legacy["credentials"]
    assert saved["delivery_permissions_version"] == 1
    assert (
        saved["delivery_mode"] == "local-only"
    )  # Older running reporters stay blocked.
    assert len(store.queue()) == 1


@pytest.mark.parametrize("product", PRODUCTS)
def test_explicit_exact_report_authorization_sends_nothing_and_preserves_other_entries(
    tmp_path, monkeypatch, product
):
    module, store, _ = client(tmp_path, monkeypatch, product)
    report = restricted_report(module, monkeypatch)
    restricted_report(module, monkeypatch, str(uuid4()))
    before = retained_state(module)
    value = authorization(module, report["report"])

    result = module.authorize_report_delivery(value)

    after = retained_state(module)
    assert result["authorized"] is True and result["sent"] is False
    assert store.queue() == []
    assert after["outbox"][0]["payload"] == before["outbox"][0]["payload"]
    assert after["outbox"][1:] == before["outbox"][1:]
    assert after["credentials"] == before["credentials"]
    assert after["delivery_authorizations"] == [value]


@pytest.mark.parametrize("product", PRODUCTS)
def test_authorized_exact_report_delivers_once_without_releasing_same_task_history(
    tmp_path, monkeypatch, product
):
    module, store, _ = client(tmp_path, monkeypatch, product)
    task_id = str(uuid4())
    report = restricted_report(module, monkeypatch, task_id)
    monkeypatch.setenv("MPARANZA_INCIDENT_TASK_ID", task_id)
    module.report_failure("journal-sampling", "execution", "Another restricted report")
    module.authorize_report_delivery(authorization(module, report["report"], task_id))
    remaining = retained_state(module)["outbox"][1:]

    delivered = module.native_request(
        {"operation": "report", "report": report["report"]}
    )

    assert delivered["report_id"] == report["report"]["report_id"]
    assert len(store.queue()) == 1
    assert retained_state(module)["outbox"] == remaining


@pytest.mark.parametrize(
    "mismatch", ["installation_id", "task_id", "report_sha256", "report_id"]
)
def test_authorization_mismatch_preserves_queue_and_sends_nothing(
    tmp_path, monkeypatch, mismatch
):
    module, store, _ = client(tmp_path, monkeypatch)
    task_id = str(uuid4())
    report = restricted_report(module, monkeypatch, task_id)
    before = retained_state(module)
    value = authorization(module, report["report"], task_id)
    value[mismatch] = "0" * 64 if mismatch == "report_sha256" else str(uuid4())

    with pytest.raises(ValueError):
        module.authorize_report_delivery(value)

    assert retained_state(module) == before
    assert store.queue() == []


@pytest.mark.parametrize("product", PRODUCTS)
def test_authorized_native_retry_returns_same_receipt_without_resending(
    tmp_path, monkeypatch, product
):
    module, store, _ = client(tmp_path, monkeypatch, product)
    report = restricted_report(module, monkeypatch)
    value = authorization(module, report["report"])
    module.authorize_report_delivery(value)
    module.authorize_report_delivery(value)
    request = {"operation": "report", "report": report["report"]}
    receipt = module.native_request(request)
    monkeypatch.setattr(
        module, "_post", lambda *_: pytest.fail("A retained receipt needs no resend")
    )

    repeated = module.native_request(request)

    assert repeated == receipt
    assert retained_state(module)["delivery_authorizations"] == [value]
    assert len(store.queue()) == 1


@pytest.mark.parametrize("product", PRODUCTS)
def test_schema_correction_does_not_inherit_exact_bytes_authorization(
    tmp_path, monkeypatch, product
):
    module, store, _ = client(tmp_path, monkeypatch, product)
    report = restricted_report(module, monkeypatch)["report"]
    module.authorize_report_delivery(authorization(module, report))
    transport = module._post

    def reject_report(operation, payload):
        if operation == "report":
            raise urllib.error.HTTPError("https://fixture", 422, "Schema", {}, None)
        return transport(operation, payload)

    with monkeypatch.context() as rejected:
        rejected.setattr(module, "_post", reject_report)
        reply = module.native_request({"operation": "report", "report": report})
    assert reply["delivery"] == "rejected"
    corrected = {**report, "summary": "Changed report bytes"}

    result = module.native_request({"operation": "report", "report": corrected})

    assert result["delivery"] == "local-only"
    assert store.queue() == []
    assert retained_state(module)["outbox"][0]["payload"]["report"] == corrected


@pytest.mark.parametrize("product", PRODUCTS)
def test_offline_automatic_event_retries_without_releasing_restricted_entry(
    tmp_path, monkeypatch, product
):
    module, store, _ = client(tmp_path, monkeypatch, product)
    restricted_report(module, monkeypatch)
    restricted = retained_state(module)["outbox"]
    with monkeypatch.context() as offline:

        def unavailable(*_args):
            raise urllib.error.URLError("Controlled outage")

        offline.setattr(module, "_post", unavailable)
        current = module.report_failure(
            "journal-sampling", "execution", "Current failure"
        )

    result = module.native_request({"operation": "report", "report": current["report"]})

    assert result["report_id"] == current["report"]["report_id"]
    assert retained_state(module)["outbox"] == restricted
    assert len(store.queue()) == 1
