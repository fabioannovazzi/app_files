"""Server activity counts deduplicate hosts and retain missing linkage."""

from __future__ import annotations

from uuid import uuid4

import pytest

from modules.operational_incidents.contracts import Credentials, DeviceCredentials
from modules.operational_incidents.store import IncidentStore
from modules.workflow_usage.contracts import WorkflowEvent

SINCE = "2026-10-01T00:00:00+00:00"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "modules.operational_incidents.store._now",
        lambda: "2026-10-18T12:00:00+00:00",
    )
    return IncidentStore(tmp_path / "incidents.sqlite3")


def add_run(store, device=None, sample="user", product="vera"):
    owner = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    store.register(owner, device, product=product)
    item = WorkflowEvent(
        event_id=uuid4(),
        run_id=uuid4(),
        sequence=1,
        kind="started",
        occurred_at="2026-10-18T12:00:00+00:00",
        product_version="0.1.412",
        product=product,
        pipeline="journal-sampling" if product == "vera" else "nda-review",
        host="cowork",
        sample_kind=sample,
    )
    store.workflow_record(owner, item)
    return owner, str(item.run_id)


def host():
    return DeviceCredentials(
        device_id=uuid4(), device_key=uuid4().hex, native_app="cowork"
    )


def test_computers_deduplicates_reporters_and_excludes_designated_mac_even_if_user(
    store,
):
    customer, agent = host(), host()
    add_run(store, customer)
    add_run(store, customer.model_copy(update={"native_app": "codex"}))
    add_run(store, agent)
    store.workflow_testing_reset([str(agent.device_id)])

    result = store.workflow_computers(SINCE)

    assert result["verified_active_user_computers"] == 1
    assert result["excluded_test_runs"] == 1
    assert result["excluded_test_computers"] == 1
    assert result["computer_count_complete"] is True
    assert len(result["runs"]) == 3


def test_computers_keeps_unlinked_users_unknown_and_excludes_explicit_fixtures(store):
    add_run(store)
    add_run(store, sample="agent_test")
    add_run(store, host(), sample="synthetic")

    result = store.workflow_computers(SINCE)

    assert result["verified_active_user_computers"] == 0
    assert result["unlinked_user_reporting_instances"] == 1
    assert result["excluded_test_runs"] == 2
    assert result["excluded_test_computers"] == 1
    assert result["computer_count_complete"] is False


def test_computers_uses_receipt_window_and_product_scope(store):
    add_run(store, host())

    result = store.workflow_computers("2026-10-19T00:00:00+00:00")

    assert result["runs"] == []
    assert result["verified_active_user_computers"] == 0


def test_computers_does_not_count_another_products_runs(store):
    add_run(store, host())

    result = store.workflow_computers(SINCE, "lucia")

    assert result["runs"] == []
    assert result["product"] == "lucia"


def test_computers_rejects_ambiguous_cutoff(store):
    with pytest.raises(ValueError, match="timezone"):
        store.workflow_computers("2026-10-01T00:00:00")
