"""Current native work must not transmit or recover retained historical incidents."""

from __future__ import annotations

import json
import urllib.error
from uuid import uuid4

import pytest

from tests.plugins.test_operational_incident_client import client as incident_client

__all__: list[str] = []


def client(tmp_path, monkeypatch, product="vera"):
    monkeypatch.setenv("MPARANZA_INCIDENT_DELIVERY", "automatic")
    return incident_client(tmp_path, monkeypatch, product)


def retained_state(module):
    return json.loads(module._state_path().read_text())


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_current_failure_and_readiness_preserve_identical_historical_queue(
    tmp_path, monkeypatch, product
):
    module, store, _ = client(tmp_path, monkeypatch, product)
    monkeypatch.delenv("MPARANZA_INCIDENT_TASK_ID", raising=False)

    def offline(*_args):
        raise urllib.error.URLError("Controlled transport interruption")

    with monkeypatch.context() as isolated:
        isolated.setattr(module, "_post", offline)
        previous = module.report_failure(
            "journal-sampling", "dependency-setup", "Same technical failure"
        )
        with pytest.raises(urllib.error.URLError):
            module.record_success("journal-sampling", "check_dependencies.py")
    historical = retained_state(module)["outbox"]
    owner = module.reporting_credentials()
    task_id = str(uuid4())
    monkeypatch.setenv("MPARANZA_INCIDENT_TASK_ID", task_id)

    current = module.report_failure(
        "journal-sampling", "dependency-setup", "Same technical failure"
    )
    module.record_success("journal-sampling", "check_dependencies.py")

    state = retained_state(module)
    assert current["reporting"] == "delivered"
    assert current["report"]["report_id"] != previous["report"]["report_id"]
    assert state["outbox"] == historical
    assert state["credentials"] == owner
    assert len(store.queue()) == 1
    assert store.queue()[0]["reports"][0]["report_id"] == current["report"]["report_id"]
    assert store.queue()[0]["outcomes"][0]["status"] == "action-required"
    assert state["receipts"][0]["delivery_scope"] == task_id
    assert "delivery_scope" not in state["receipts"][0]["report"]


@pytest.mark.parametrize("historical_scope", [None, "other-task"])
def test_success_without_current_incident_does_not_revisit_older_failures(
    tmp_path, monkeypatch, historical_scope
):
    module, store, _ = client(tmp_path, monkeypatch)
    if historical_scope:
        monkeypatch.setenv("MPARANZA_INCIDENT_TASK_ID", str(uuid4()))
    else:
        monkeypatch.delenv("MPARANZA_INCIDENT_TASK_ID", raising=False)
    module.report_failure("journal-sampling", "dependency-setup", "Older task")
    before = module._state_path().read_bytes()
    monkeypatch.setenv("MPARANZA_INCIDENT_TASK_ID", str(uuid4()))
    monkeypatch.setattr(
        module, "_post", lambda *_: pytest.fail("No current incident needs transport")
    )

    module.record_success("journal-sampling", "check_dependencies.py")

    assert module._state_path().read_bytes() == before
    assert store.queue()[0]["outcomes"] == []


def test_operation_identity_resumes_same_task_without_sharing_an_unbound_helper(
    tmp_path, monkeypatch
):
    module, _, _ = client(tmp_path, monkeypatch)
    first_task = str(uuid4())
    arguments = ["run", "scripts/check_dependencies.py"]
    monkeypatch.setenv("MPARANZA_INCIDENT_TASK_ID", first_task)
    first = module.execution_identity("journal-sampling", arguments)
    monkeypatch.setenv("MPARANZA_INCIDENT_TASK_ID", str(uuid4()))

    other = module.execution_identity("journal-sampling", arguments)
    monkeypatch.setenv("MPARANZA_INCIDENT_TASK_ID", first_task)
    resumed = module.execution_identity("journal-sampling", arguments)

    assert other["operation_id"] != first["operation_id"]
    assert resumed["operation_id"] == first["operation_id"]


def test_current_progress_does_not_flush_older_incident_entries(tmp_path, monkeypatch):
    module, _, _ = client(tmp_path, monkeypatch)

    def offline(*_args):
        raise urllib.error.URLError("Controlled transport interruption")

    monkeypatch.delenv("MPARANZA_INCIDENT_TASK_ID", raising=False)
    monkeypatch.setattr(module, "_post", offline)
    module.report_failure("journal-sampling", "dependency-setup", "Older task")
    historical = retained_state(module)["outbox"]
    monkeypatch.setenv("MPARANZA_INCIDENT_TASK_ID", str(uuid4()))
    identity = module.execution_identity("journal-sampling", ["run", "checker.py"])
    monkeypatch.setattr(
        module, "_post", lambda *_: pytest.fail("Older queue must not be transmitted")
    )

    module.record_execution_progress(identity, "retry-started")

    assert retained_state(module)["outbox"] == historical


def test_current_scope_retry_delivers_its_queue_and_keeps_older_entries(
    tmp_path, monkeypatch
):
    module, store, transport = client(tmp_path, monkeypatch)

    def offline(*_args):
        raise urllib.error.URLError("Controlled transport interruption")

    monkeypatch.delenv("MPARANZA_INCIDENT_TASK_ID", raising=False)
    monkeypatch.setattr(module, "_post", offline)
    module.report_failure("journal-sampling", "dependency-setup", "Older task")
    historical = retained_state(module)["outbox"]
    monkeypatch.setenv("MPARANZA_INCIDENT_TASK_ID", str(uuid4()))
    current = module.report_failure(
        "journal-sampling", "dependency-setup", "Current task"
    )
    monkeypatch.setattr(module, "_post", transport)

    result = module.check_incidents(recover=False)

    assert len(result["pending"]) == 1
    assert result["queued"] == 0
    assert result["pending"][0]["latest_report_id"] == current["report"]["report_id"]
    assert len(store.queue()) == 1
    assert retained_state(module)["outbox"] == historical
