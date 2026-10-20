"""Task identity, delivery, outcome, receipt and satisfaction acceptance."""

from __future__ import annotations

import importlib
import json
import urllib.error
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from modules.operational_incidents import api
from modules.operational_incidents.contracts import Credentials, DeviceCredentials
from modules.operational_incidents.store import IncidentNotFound, IncidentStore
from modules.run_receipts import api as receipt_api
from modules.run_receipts.signing import RunReceiptSigner
from modules.run_receipts.store import RunReceiptStore
from modules.workflow_usage.contracts import WorkflowEvent
from modules.workflow_usage.reporting import render_html, summarize
from modules.workflow_usage.repository import WorkflowConflict
from tests.modules.operational_incidents.test_oauth import connection_headers
from tests.plugins.test_vera_customer_folder_ledger import (
    archive_core,
    archive_script_imports,
    client_case,
)
from tests.plugins.test_vera_selective_reporting import _evidence, _finish, _start


def event(run_id, sequence=1, kind="started", **fields):
    defaults = (
        {"pipeline": "journal-sampling", "host": "codex", "sample_kind": "user"}
        if kind == "started"
        else {}
    )
    return WorkflowEvent(
        event_id=uuid4(),
        run_id=run_id,
        sequence=sequence,
        kind=kind,
        occurred_at="2026-10-17T12:00:00Z",
        product_version="0.1.400",
        **(defaults | fields),
    )


@pytest.fixture
def setup(tmp_path, monkeypatch):
    store = IncidentStore(tmp_path / "incidents.sqlite3")
    credentials = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    store.register(credentials)
    receipt_store = RunReceiptStore(sqlite_path=tmp_path / "receipts.sqlite3")
    signer = RunReceiptSigner(private_key=Ed25519PrivateKey.generate())
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(receipt_api.api_router)
    app.dependency_overrides[api.get_incident_store] = lambda: store
    app.dependency_overrides[receipt_api.get_run_receipt_store] = lambda: receipt_store
    app.dependency_overrides[receipt_api.get_run_receipt_signer] = lambda: signer
    monkeypatch.setattr(api, "get_run_receipt_store", lambda: receipt_store)
    monkeypatch.setattr(api, "get_run_receipt_signer", lambda: signer)
    monkeypatch.setattr(api, "_admit", lambda source: None)
    return store, credentials, TestClient(app)


def post(client, owner, item):
    return client.post(
        "/api/operational-incidents/workflow-record",
        json={
            "credentials": owner.model_dump(mode="json"),
            "event": item.model_dump(mode="json", exclude_none=True),
        },
    )


def test_complete_task_receipt_feedback_and_operator_metrics(setup):
    store, owner, client = setup
    run_id = uuid4()
    post(client, owner, event(run_id))
    post(client, owner, event(run_id, 2, "completed"))
    proof = {
        "receipt_id": str(uuid4()),
        "report_sha256": "a" * 64,
        "plugin_version": "0.1.400",
        "schema_version": 1,
    }
    stamped = client.post("/api/vera/run-receipts", json=proof)
    linked = post(
        client,
        owner,
        event(
            run_id,
            3,
            "receipt",
            receipt_id=proof["receipt_id"],
            receipt_version=proof["plugin_version"],
            report_sha256=proof["report_sha256"],
        ),
    )
    post(client, owner, event(run_id, 4, "feedback_prompted"))
    post(
        client,
        owner,
        event(
            run_id,
            5,
            "feedback",
            stars=2,
            comment="Il risultato non spiega gli scostamenti.",
            feedback_source="user_chat",
        ),
    )

    report = summarize(store.workflow_overview())

    assert stamped.status_code == 201
    assert linked.status_code == 200
    assert linked.json()["reporting"]["model_data_receipt"] == "linked"
    assert linked.json()["reporting"]["model_data_report_scope"] == "archive_run"
    assert report["totals"]["completed"] == 1
    assert report["totals"]["receipt_linked_runs"] == 1
    assert report["totals"]["stars"] == {"1": 0, "2": 1, "3": 0, "4": 0, "5": 0}
    assert report["totals"]["response_rate_of_terminal_runs"] == 1
    assert report["review_candidates"][0]["reasons"] == ["low_rating", "user_comment"]
    assert "feedback_key" not in json.dumps(report)
    assert "installation_key" not in json.dumps(report)
    assert len(store.workflow_inspect(str(run_id))["events"]) == 5


def test_cowork_completion_exposes_missing_host_link_and_archive_report_scope(setup):
    store, owner, client = setup
    run_id = uuid4()
    post(client, owner, event(run_id, host="cowork", sample_kind="agent_test"))

    reply = post(client, owner, event(run_id, 2, "completed")).json()

    assert reply["reporting"]["computer_link"] == "unlinked"
    assert reply["reporting"]["computer_id"] is None
    assert reply["reporting"]["model_data_receipt"] == "archive_managed"
    assert reply["reporting"]["model_data_report_scope"] == "archive_run"
    assert len(reply["reporting"]["next_steps"]) == 2
    assert store.workflow_status(owner, str(run_id))["state"] == "completed"
    assert summarize(store.workflow_overview())["included_user_runs"] == 0


@pytest.mark.parametrize(
    "pipeline",
    [
        "quesito-legale-fiscale",
        "presenza-digitale-studio",
        "new-client",
        "bilancio-oic",
    ],
)
def test_excluded_vera_task_needs_no_privacy_receipt_or_monitoring_alert(
    setup, pipeline
):
    store, owner, client = setup
    run_id = uuid4()
    post(client, owner, event(run_id, pipeline=pipeline))

    response = post(client, owner, event(run_id, 2, "completed")).json()

    assert response["reporting"]["model_data_receipt"] == "not_applicable"
    assert response["reporting"]["model_data_report_scope"] == "not_applicable"
    assert response["reporting"]["model_data_report_eligible"] is False
    assert len(response["reporting"]["next_steps"]) == 1
    assert summarize(store.workflow_overview())["review_candidates"] == []


def test_native_binding_updates_same_cowork_run_status_without_event_replay(setup):
    store, owner, client = setup
    run_id = uuid4()
    device = DeviceCredentials(
        device_id=uuid4(), device_key=uuid4().hex, native_app="cowork"
    )
    post(client, owner, event(run_id, host="cowork", sample_kind="agent_test"))
    post(client, owner, event(run_id, 2, "completed"))
    store.register(owner, device)

    status = store.workflow_status(owner, str(run_id))

    assert status["installation_id"] == str(owner.installation_id)
    assert status["run_id"] == str(run_id)
    assert status["sequence"] == 2
    assert status["reporting"]["computer_link"] == "verified"
    assert status["reporting"]["computer_id"] == str(device.device_id)
    assert status["reporting"]["model_data_receipt"] == "archive_managed"
    assert status["reporting"]["model_data_report_scope"] == "archive_run"
    assert len(status["reporting"]["next_steps"]) == 1
    assert device.device_key not in json.dumps(status)
    assert owner.installation_key not in json.dumps(status)


@pytest.mark.parametrize("outcome", ["completed", "failed", "cancelled"])
def test_vera_task_status_does_not_infer_missing_archive_receipt(setup, outcome):
    store, owner, _ = setup
    run_id = uuid4()
    device = DeviceCredentials(
        device_id=uuid4(), device_key=uuid4().hex, native_app="codex"
    )
    store.register(owner, device)
    store.workflow_record(owner, event(run_id, pipeline="journal-bank-reconciliation"))
    store.workflow_record(owner, event(run_id, 2, outcome))

    status = store.workflow_status(owner, str(run_id))

    assert status["state"] == outcome
    assert status["receipts"] == []
    assert status["reporting"]["model_data_receipt"] == "archive_managed"
    assert status["reporting"]["model_data_report_scope"] == "archive_run"
    assert status["reporting"]["model_data_report_eligible"] is True
    assert status["reporting"]["next_steps"] == [
        "Studio Archive owns automatic report generation and receipt delivery "
        "for every selected Archive run, including full exposure, zero local remainder "
        "or incomplete measurements. Inspect that run's saved report and receipt "
        "when verification is needed. This task status does not establish whether "
        "an Archive report or receipt exists. No separate usage-task receipt link "
        "is required; do not rerun work or manufacture evidence."
    ]


@pytest.mark.parametrize(
    ("product", "pipeline"),
    [("clara", "business-planning"), ("lucia", "quesito-legale-fiscale")],
)
def test_other_products_still_report_missing_task_receipt(setup, product, pipeline):
    store, _, _ = setup
    owner = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    device = DeviceCredentials(
        device_id=uuid4(), device_key=uuid4().hex, native_app="codex"
    )
    run_id = uuid4()
    store.register(owner, device, product=product)
    store.workflow_record(owner, event(run_id, product=product, pipeline=pipeline))
    store.workflow_record(owner, event(run_id, 2, "completed", product=product))

    status = store.workflow_status(owner, str(run_id))

    assert status["reporting"]["model_data_receipt"] == "missing"
    assert status["reporting"]["model_data_report_scope"] == "usage_task"
    assert status["reporting"]["model_data_report_eligible"] is True
    assert len(status["reporting"]["next_steps"]) == 1
    assert "link it to this same run" in status["reporting"]["next_steps"][0]


def test_duplicate_event_ack_refreshes_link_without_changing_acknowledged_bytes(setup):
    store, owner, client = setup
    start = event(uuid4(), host="cowork", sample_kind="agent_test")
    original = post(client, owner, start).json()
    device = DeviceCredentials(
        device_id=uuid4(), device_key=uuid4().hex, native_app="cowork"
    )
    store.register(owner, device)

    replay = post(client, owner, start).json()

    assert replay["event_id"] == original["event_id"]
    assert replay["payload_sha256"] == original["payload_sha256"]
    assert replay["reporting"]["computer_id"] == str(device.device_id)
    assert store.workflow_status(owner, str(start.run_id))["sequence"] == 1


def test_silence_is_unknown_unrated_and_tests_are_excluded(setup):
    store, owner, _ = setup
    actual = uuid4()
    synthetic = uuid4()
    store.workflow_record(owner, event(actual))
    store.workflow_record(owner, event(synthetic, sample_kind="synthetic"))
    store.workflow_record(owner, event(synthetic, 2, "completed"))
    store.workflow_record(
        owner,
        event(synthetic, 3, "feedback", stars=5, feedback_source="synthetic_test"),
    )

    report = summarize(store.workflow_overview())

    assert report["totals"]["runs"] == 1
    assert report["totals"]["outcome_unknown"] == 1
    assert report["totals"]["failed"] == 0
    assert report["totals"]["average_stars"] is None
    assert report["excluded_test_runs"] == 1
    assert report["review_candidates"] == []


def test_retry_is_idempotent_conflicting_bytes_or_sequence_are_rejected(setup):
    store, owner, _ = setup
    item = event(uuid4())
    first = store.workflow_record(owner, item)

    retry = store.workflow_record(owner, item)

    assert retry["duplicate"] is True
    assert retry["event_id"] == first["event_id"]
    with pytest.raises(WorkflowConflict):
        store.workflow_record(owner, item.model_copy(update={"host": "cowork"}))
    with pytest.raises(WorkflowConflict):
        store.workflow_record(owner, event(item.run_id, 3, "completed"))
    assert len(store.workflow_inspect(str(item.run_id))["events"]) == 1


@pytest.mark.parametrize("terminal", ["failed", "cancelled"])
def test_resume_preserves_original_task_and_failure_history(setup, terminal):
    store, owner, _ = setup
    run = uuid4()
    store.workflow_record(owner, event(run))
    store.workflow_record(owner, event(run, 2, terminal))
    store.workflow_record(owner, event(run, 3, "resumed"))
    store.workflow_record(owner, event(run, 4, "completed"))

    report = summarize(store.workflow_overview())

    assert report["totals"]["runs"] == 1
    assert report["totals"]["completed"] == 1
    assert report["totals"]["observed_failed_attempts"] == int(terminal == "failed")
    assert store.workflow_inspect(str(run))["run"]["resume_count"] == 1


@pytest.mark.parametrize(
    "fields",
    [
        {"pipeline": "studio-archive"},
        {"sample_kind": "probably_user"},
        {"host": "Fabio Mac"},
    ],
)
def test_invalid_or_infrastructure_start_is_not_counted(fields):
    with pytest.raises(ValidationError):
        event(uuid4(), **fields)


@pytest.mark.parametrize("stars", [0, 6, True, "5"])
def test_rating_is_an_actual_integer_in_standard_range(stars):
    with pytest.raises(ValidationError):
        event(uuid4(), 3, "feedback", stars=stars, feedback_source="user_chat")


def test_unrecognized_case_fields_and_feedback_on_running_task_are_rejected(setup):
    store, owner, client = setup
    run = uuid4()
    item = event(run).model_dump(mode="json")
    item["prompt"] = "must never enter the registry"
    response = client.post(
        "/api/operational-incidents/workflow-record",
        json={"credentials": owner.model_dump(mode="json"), "event": item},
    )
    assert response.status_code == 422
    assert "must never" not in response.text
    store.workflow_record(owner, event(run))
    with pytest.raises(WorkflowConflict):
        store.workflow_record(
            owner, event(run, 2, "feedback", stars=4, feedback_source="user_chat")
        )


def test_another_installation_cannot_read_or_finish_a_task(setup):
    store, owner, _ = setup
    run = uuid4()
    store.workflow_record(owner, event(run))
    other = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    store.register(other)
    with pytest.raises(IncidentNotFound):
        store.workflow_status(other, str(run))
    with pytest.raises(IncidentNotFound):
        store.workflow_record(other, event(run, 2, "completed"))


def test_saved_oauth_connector_records_ai_only_work_and_retains_identity(setup):
    store, _, client = setup
    headers = connection_headers(store)
    run = uuid4()
    call = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "vera_workflow_record",
            "arguments": {
                "event": event(run, pipeline="quesito-legale-fiscale").model_dump(
                    mode="json", exclude_none=True
                )
            },
        },
    }

    response = client.post("/mcp/vera-incidents", json=call, headers=headers).json()[
        "result"
    ]

    assert response["isError"] is False
    assert response["structuredContent"]["run_id"] == str(run)
    assert store.workflow_overview()["total"] == 1


def test_saved_connector_stamps_exact_pending_receipt_and_links_original_run(setup):
    store, owner, client = setup
    run_id = uuid4()
    post(client, owner, event(run_id, host="cowork", sample_kind="agent_test"))
    headers = connection_headers(store)
    proof = {
        "receipt_id": str(uuid4()),
        "report_sha256": "b" * 64,
        "plugin_version": "0.1.400",
        "schema_version": 1,
    }
    call = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "vera_workflow_stamp",
            "arguments": {
                "credentials": owner.model_dump(mode="json"),
                "run_id": str(run_id),
                "receipt_request": proof,
            },
        },
    }

    first = client.post("/mcp/vera-incidents", json=call, headers=headers).json()[
        "result"
    ]
    retry = client.post("/mcp/vera-incidents", json=call, headers=headers).json()[
        "result"
    ]
    linked = post(
        client,
        owner,
        event(
            run_id,
            2,
            "receipt",
            receipt_id=proof["receipt_id"],
            report_sha256=proof["report_sha256"],
            receipt_version=proof["plugin_version"],
        ),
    )

    assert first["isError"] is False
    assert first == retry
    assert first["structuredContent"]["signature_valid"] is True
    assert first["structuredContent"]["receipt_id"] == proof["receipt_id"]
    assert linked.json()["reporting"]["model_data_receipt"] == "linked"
    assert store.workflow_status(owner, str(run_id))["state"] == "unknown"


@pytest.mark.parametrize(
    "invalid", ["owner", "product", "private_content", "missing_run"]
)
def test_workflow_stamp_rejects_wrong_scope_and_unrelated_content(setup, invalid):
    store, owner, client = setup
    run_id = uuid4()
    post(client, owner, event(run_id))
    actor = owner
    proof = {
        "receipt_id": str(uuid4()),
        "report_sha256": "c" * 64,
        "plugin_version": "0.1.400",
        "schema_version": 1,
    }
    if invalid == "owner":
        actor = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
        store.register(actor)
    if invalid == "product":
        proof.update(schema_version=2, product="clara")
    if invalid == "private_content":
        proof["report"] = "PRIVATE_SENTINEL"
    payload = {
        "credentials": actor.model_dump(mode="json"),
        "run_id": str(run_id),
        "receipt_request": proof,
    }
    if invalid == "missing_run":
        del payload["run_id"]

    result = client.post(
        "/mcp/vera-incidents",
        headers=connection_headers(store),
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "vera_workflow_stamp", "arguments": payload},
        },
    ).json()["result"]

    assert result["isError"] is True
    assert "PRIVATE_SENTINEL" not in json.dumps(result)
    assert api.get_run_receipt_store().get(proof["receipt_id"]) is None


def test_form_capability_cannot_read_tasks_and_retry_does_not_duplicate(setup):
    store, owner, client = setup
    run = uuid4()
    store.workflow_record(owner, event(run))
    completed = store.workflow_record(owner, event(run, 2, "completed"))
    key = completed["feedback_url"].split("#")[1]
    answer = {
        "key": key,
        "event_id": str(uuid4()),
        "stars": 1,
        "comment": "<script>alert('not code')</script>",
    }
    response = client.post(f"/api/vera/workflow-feedback/{run}", json=answer)
    duplicate = client.post(f"/api/vera/workflow-feedback/{run}", json=answer)
    wrong = client.post(f"/api/vera/workflow-feedback/{uuid4()}", json=answer)

    assert response.status_code == 200
    assert duplicate.json() == response.json()
    assert wrong.status_code == 409
    assert len(store.workflow_inspect(str(run))["events"]) == 3
    assert "&lt;script&gt;" in render_html(summarize(store.workflow_overview()))
    assert "<script>alert" not in render_html(summarize(store.workflow_overview()))
    assert client.get(f"/vera/feedback/{run}").status_code == 200
    assert key not in client.get(f"/vera/feedback/{run}").text


def test_receipt_requires_a_real_matching_signed_server_record(setup):
    store, owner, client = setup
    run = uuid4()
    post(client, owner, event(run))

    response = post(
        client,
        owner,
        event(
            run,
            2,
            "receipt",
            receipt_id=uuid4(),
            receipt_version="0.1.400",
            report_sha256="b" * 64,
        ),
    )

    assert response.status_code == 409
    assert store.workflow_inspect(str(run))["run"]["receipts"] == []


def test_truncated_report_says_inventory_incomplete(setup):
    store, owner, _ = setup
    store.workflow_record(owner, event(uuid4()))
    store.workflow_record(owner, event(uuid4()))

    result = summarize(store.workflow_overview(1))

    assert result["inventory_complete"] is False
    assert result["inventory_total"] == 2


@pytest.fixture
def installed_client(setup, tmp_path, monkeypatch):
    _, _, client = setup
    scripts = Path(__file__).resolve().parents[3] / "plugins/vera/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    usage = importlib.import_module("workflow_usage")
    monkeypatch.setenv("MPARANZA_INCIDENT_STATE_DIR", str(tmp_path / "local-state"))
    monkeypatch.setenv("MPARANZA_INCIDENT_DEVICE_DIR", str(tmp_path / "local-device"))
    monkeypatch.setenv("MPARANZA_INCIDENT_DELIVERY", "local-only")
    monkeypatch.setenv("VERA_REPORTING_STATE_DIR", str(tmp_path / "reporting-state"))
    monkeypatch.setattr(usage, "ROOT", scripts.parent)

    def transport(operation, payload):
        registered = client.post(
            "/api/operational-incidents/register",
            json={"credentials": payload["credentials"]},
        )
        assert registered.status_code == 200
        response = client.post(f"/api/operational-incidents/{operation}", json=payload)
        if response.status_code != 200:
            raise urllib.error.HTTPError(
                "https://mparanza.com", response.status_code, "rejected", {}, None
            )
        return response.json()

    monkeypatch.setattr(usage, "_send", transport)
    return usage


@pytest.mark.parametrize("host", ["codex", "cowork", "chatgpt", "antigravity"])
def test_observed_app_is_recorded_without_changing_installation_owner(
    installed_client, host
):
    usage = installed_client
    owner = usage.incidents.local_context()["credentials"]["installation_id"]
    run = str(uuid4())

    usage.start(run, "journal-sampling", sample_kind="user", host=host)

    result = usage.status(run)["remote"]
    assert result["host"] == host
    assert result["installation_id"] == owner


def test_unobserved_app_stays_unknown_despite_incident_default(installed_client):
    usage = installed_client
    assert usage.incidents.local_context()["client_status"]["host"] in {
        "codex",
        "cowork",
    }
    run = str(uuid4())

    usage.start(run, "journal-sampling", sample_kind="user")

    assert usage.status(run)["remote"]["host"] == "unknown"


def test_unrecognized_app_is_rejected_before_task_is_started(installed_client):
    with pytest.raises(ValueError, match="observed app"):
        installed_client.start(
            str(uuid4()), "journal-sampling", sample_kind="user", host="personal laptop"
        )


def test_offline_outbox_restarts_retries_exact_bytes_and_receives_acks(
    setup, installed_client, monkeypatch
):
    usage = installed_client
    transport = usage._send
    run = str(uuid4())
    usage.start(run, "journal-sampling", sample_kind="user", deliver=False)
    usage.record(run, "completed", deliver=False)
    monkeypatch.setattr(
        usage, "_send", lambda *args: (_ for _ in ()).throw(OSError("offline"))
    )
    failed = usage.flush()
    monkeypatch.setattr(usage, "_send", transport)

    delivered = usage.flush()

    assert failed["queued"] == 2
    assert delivered["delivered"] == 2
    assert delivered["queued"] == 0
    assert usage.flush()["delivered"] == 0
    assert summarize(setup[0].workflow_overview())["totals"]["completed"] == 1


def test_lost_ack_after_server_commit_is_recovered_without_new_run(
    setup, installed_client, monkeypatch
):
    usage = installed_client
    transport = usage._send
    run = str(uuid4())
    usage.start(run, "journal-sampling", sample_kind="synthetic", deliver=False)

    def lost_ack(*args):
        transport(*args)
        raise OSError("response lost after commit")

    monkeypatch.setattr(usage, "_send", lost_ack)
    usage.flush()
    monkeypatch.setattr(usage, "_send", transport)

    result = usage.flush()

    assert result["queued"] == 0
    assert setup[0].workflow_overview()["total"] == 1
    assert summarize(setup[0].workflow_overview())["totals"]["runs"] == 0


def test_wrong_ack_never_discards_local_event(installed_client, monkeypatch):
    usage = installed_client
    run = str(uuid4())
    usage.start(run, "journal-sampling", sample_kind="user", deliver=False)
    monkeypatch.setattr(
        usage, "_send", lambda *args: {"recorded": True, "event_id": str(uuid4())}
    )

    result = usage.flush()

    assert result["queued"] == 1
    assert result["delivered"] == 0


def _queue_unrelated_prerelease(usage, monkeypatch):
    """Retain a historical event the current server cannot accept."""
    run = str(uuid4())
    with monkeypatch.context() as context:
        context.setattr(usage, "_version", lambda: "0.1.406-folder-intake.1")
        usage.start(
            run, "archive-organization", sample_kind="agent_test", deliver=False
        )
    return run


def _retained_usage_events(usage, run):
    """Read exact stored payloads and acknowledgements for preservation checks."""
    connection = usage._database()
    try:
        return [
            tuple(row)
            for row in connection.execute(
                "SELECT event_id,payload,receipt FROM events WHERE run_id=? ORDER BY sequence",
                (run,),
            )
        ]
    finally:
        connection.close()


def test_start_delivers_only_current_task_with_unrelated_invalid_backlog(
    installed_client, monkeypatch
):
    usage = installed_client
    unrelated = _queue_unrelated_prerelease(usage, monkeypatch)
    original = _retained_usage_events(usage, unrelated)
    transport = usage._send
    sent = []

    def capture(operation, payload):
        sent.append(payload["event"]["run_id"])
        return transport(operation, payload)

    monkeypatch.setattr(usage, "_send", capture)
    current = str(uuid4())

    result = usage.start(current, "journal-sampling", sample_kind="agent_test")

    assert result["delivery"] == {"delivered": 1, "queued": 0, "blocked": {}}
    assert sent == [current]
    assert _retained_usage_events(usage, unrelated) == original


def test_outcome_delivery_ignores_unrelated_invalid_backlog(
    installed_client, monkeypatch
):
    usage = installed_client
    current = str(uuid4())
    usage.start(current, "journal-sampling", sample_kind="agent_test")
    unrelated = _queue_unrelated_prerelease(usage, monkeypatch)
    original = _retained_usage_events(usage, unrelated)

    result = usage.record(current, "completed")

    assert result["delivery"] == {"delivered": 1, "queued": 0, "blocked": {}}
    assert usage.status(current)["remote"]["state"] == "completed"
    assert _retained_usage_events(usage, unrelated) == original


def test_scoped_flush_cli_preserves_unrelated_invalid_backlog(
    installed_client, monkeypatch, capsys
):
    usage = installed_client
    unrelated = _queue_unrelated_prerelease(usage, monkeypatch)
    original = _retained_usage_events(usage, unrelated)
    current = str(uuid4())
    usage.start(current, "journal-sampling", sample_kind="agent_test", deliver=False)

    code = usage.main(["flush", "--run-id", current])

    assert code == 0
    assert json.loads(capsys.readouterr().out) == {
        "delivered": 1,
        "queued": 0,
        "blocked": {},
    }
    assert usage.status(current)["local_events"][0]["acknowledged"] is True
    assert _retained_usage_events(usage, unrelated) == original


def test_scoped_pending_cli_exposes_only_selected_task(
    installed_client, monkeypatch, capsys
):
    usage = installed_client
    unrelated = _queue_unrelated_prerelease(usage, monkeypatch)
    original = _retained_usage_events(usage, unrelated)
    current = str(uuid4())
    usage.start(current, "journal-sampling", sample_kind="agent_test", deliver=False)

    code = usage.main(["pending", "--run-id", current])

    body = json.loads(capsys.readouterr().out)
    assert code == 0
    assert body["queued"] == 1
    assert [event["run_id"] for event in body["events"]] == [current]
    assert (
        usage.status(current, remote=False)["local_events"][0]["acknowledged"] is False
    )
    assert _retained_usage_events(usage, unrelated) == original


def test_selected_invalid_event_remains_pending_and_reports_delivery_failure(
    installed_client, monkeypatch
):
    usage = installed_client
    selected = _queue_unrelated_prerelease(usage, monkeypatch)
    original = _retained_usage_events(usage, selected)

    result = usage.flush(run_id=selected)

    assert result == {
        "delivered": 0,
        "queued": 1,
        "blocked": {selected: "HTTPError"},
    }
    assert _retained_usage_events(usage, selected) == original


def test_startup_context_keeps_backlog_diagnostic_without_other_task_identifiers(
    installed_client, monkeypatch
):
    usage = installed_client
    unrelated = _queue_unrelated_prerelease(usage, monkeypatch)
    original = _retained_usage_events(usage, unrelated)

    context = usage.startup_context()

    assert unrelated not in context
    assert "workflow_usage.py flush --run-id <retained-uuid>" in context
    assert "Pending events across retained tasks: 1" in context
    assert _retained_usage_events(usage, unrelated) == original


def test_receipt_version_is_independent_of_current_reporting_version(
    setup, installed_client, tmp_path
):
    store, _, client = setup
    usage = installed_client
    run = str(uuid4())
    usage.start(run, "journal-sampling", sample_kind="user")
    proof = client.post(
        "/api/vera/run-receipts",
        json={
            "receipt_id": str(uuid4()),
            "report_sha256": "d" * 64,
            "plugin_version": "0.1.400",
        },
    ).json()
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(proof))

    result = usage.attach_receipt(run, path)

    assert result["delivery"]["queued"] == 0
    saved = store.workflow_inspect(run)["run"]
    assert saved["current_version"] == usage._version()
    assert saved["receipts"][0]["product_version"] == "0.1.400"


def test_feedback_reservation_is_once_and_terminal_retry_survives_later_events(
    installed_client,
):
    usage = installed_client
    run = str(uuid4())
    usage.start(run, "journal-sampling", sample_kind="user")
    usage.record(run, "completed")
    first = usage.record(run, "feedback_prompted")
    usage.record(run, "feedback", stars=3, feedback_source="user_chat", comment=None)

    second = usage.record(run, "feedback_prompted")
    completed_again = usage.record(run, "completed")

    assert first["ask"] is True
    assert second["ask"] is False
    assert completed_again["duplicate"] is True
    assert usage.status(run)["queued"] == 0
    assert usage.status(run)["remote"]["feedback"]["stars"] == 3


def test_offline_receipt_and_resume_survive_concurrent_form_feedback(
    setup, installed_client, tmp_path
):
    store, _, client = setup
    usage = installed_client
    run = str(uuid4())
    usage.start(run, "journal-sampling", sample_kind="user")
    usage.record(run, "failed")
    key = usage.status(run)["remote"]["feedback_url"].split("#")[1]
    proof = client.post(
        "/api/vera/run-receipts",
        json={
            "receipt_id": str(uuid4()),
            "report_sha256": "e" * 64,
            "plugin_version": "0.1.400",
        },
    ).json()
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(proof))
    usage.attach_receipt(run, path, deliver=False)
    usage.record(run, "resumed", deliver=False)
    usage.record(run, "completed", deliver=False)
    form = client.post(
        f"/api/vera/workflow-feedback/{run}",
        json={"key": key, "event_id": str(uuid4()), "stars": 2},
    )

    result = usage.flush()

    assert form.status_code == 200
    assert result["queued"] == 0
    assert result["delivered"] == 3
    saved = store.workflow_inspect(run)
    assert saved["run"]["state"] == "completed"
    assert saved["run"]["feedback"]["stars"] == 2
    assert saved["run"]["sequence"] == 6
    assert saved["run"]["client_sequence"] == 5
    assert len(saved["events"]) == 6
    assert saved["run"]["receipts"][0]["receipt_id"] == proof["receipt_id"]


def test_one_conflicted_run_does_not_block_another_installation_task(
    installed_client, monkeypatch
):
    usage = installed_client
    transport = usage._send
    bad, good = str(uuid4()), str(uuid4())
    usage.start(bad, "journal-sampling", sample_kind="user", deliver=False)
    usage.start(good, "variance-analysis", sample_kind="user", deliver=False)

    def selective(operation, payload):
        if payload.get("event", {}).get("run_id") == bad:
            raise ValueError("conflict")
        return transport(operation, payload)

    monkeypatch.setattr(usage, "_send", selective)

    result = usage.flush()

    assert result["delivered"] == 1
    assert result["queued"] == 1
    assert bad in result["blocked"]
    assert good not in result["blocked"]


def test_feedback_edit_is_one_response_and_unknown_infrastructure_never_becomes_user_use(
    setup,
):
    store, owner, _ = setup
    run = uuid4()
    store.workflow_record(owner, event(run))
    store.workflow_record(owner, event(run, 2, "completed"))
    store.workflow_record(
        owner, event(run, 3, "feedback", stars=1, feedback_source="user_chat")
    )
    store.workflow_record(
        owner, event(run, 4, "feedback", stars=4, feedback_source="user_chat")
    )

    report = summarize(store.workflow_overview())

    assert report["totals"]["rated_runs"] == 1
    assert report["totals"]["stars"]["1"] == 0
    assert report["totals"]["stars"]["4"] == 1
    assert "studio-archive" not in {row["pipeline"] for row in report["pipelines"]}


def test_unlinked_new_receipt_is_a_coverage_gap_and_old_receipts_are_not_counted_as_runs(
    setup,
):
    store, _, _ = setup
    proofs = {
        "complete": True,
        "receipts": [
            {"receipt_id": str(uuid4()), "plugin_version": "0.1.400"},
            {"receipt_id": str(uuid4()), "plugin_version": "0.1.404"},
        ],
    }

    report = summarize(store.workflow_overview(), proofs)

    assert report["totals"]["runs"] == 0
    assert report["legacy_unattributed_receipt_count"] == 1
    assert len(report["unattributed_receipts"]) == 1
    assert report["unattributed_receipts"][0]["plugin_version"] == "0.1.404"


def test_direct_cli_persists_and_reads_the_same_run(installed_client, capsys):
    usage = installed_client
    run = str(uuid4())
    assert (
        usage.main(
            [
                "start",
                "--run-id",
                run,
                "--pipeline",
                "quesito-legale-fiscale",
                "--sample-kind",
                "agent_test",
                "--host",
                "codex",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert usage.main(["record", "--run-id", run, "--kind", "cancelled"]) == 0
    capsys.readouterr()

    result = usage.main(["status", "--run-id", run])
    body = json.loads(capsys.readouterr().out)

    assert result == 0
    assert body["remote"]["state"] == "cancelled"
    assert body["queued"] == 0


def test_every_user_process_wrapper_keeps_lifecycle_on_cowork_projection():
    from modules.workflow_usage.contracts import pipeline_catalog
    from scripts.build_claude_plugin_zip import project_cowork_skill

    root = Path(__file__).resolve().parents[3]
    entrypoints = json.loads((root / "plugins/vera/usage/pipelines.json").read_text())[
        "entrypoints"
    ]
    # These are protocol/package coverage assertions, not claims of user adoption.
    for pipeline in [
        "vera",
        *(name for name in pipeline_catalog() if name != "datev-invoice-start"),
    ]:
        relative = f"skills/{entrypoints.get(pipeline, pipeline)}/SKILL.md"
        content = (root / "plugins/vera" / relative).read_bytes()
        projected = project_cowork_skill(
            content,
            relative_path=relative,
            cowork_runtime_reference=(
                root / "plugins/vera/skills/vera/references/cowork-runtime.md"
            ).read_bytes(),
            studio_archive_reference=b"## Cowork Runtime\n\nUse the selected workspace.",
        )
        assert projected.count(b"VERA_WORKFLOW_USAGE_BEGIN") == 1, pipeline
        assert b"workflow-usage.md" in projected, pipeline
        assert b"Codex" not in projected, pipeline
        assert b"hosted feedback or voice" not in projected, pipeline


def test_independent_connector_acknowledges_the_exact_local_outbox_item(
    setup, installed_client
):
    usage = installed_client
    run = str(uuid4())
    usage.start(run, "journal-sampling", sample_kind="user", deliver=False)
    queued = usage.pending()
    actual = api._dispatch(setup[0], "register", {"credentials": queued["credentials"]})
    assert actual["registered"] is True
    receipt = api._dispatch(
        setup[0],
        "workflow-record",
        {"credentials": queued["credentials"], "event": queued["events"][0]},
    )

    result = usage.acknowledge(receipt)

    assert result["acknowledged"] is True
    assert usage.pending()["queued"] == 0
    assert usage.pending()["credentials"] == queued["credentials"]
    with pytest.raises(ValueError):
        usage.acknowledge({**receipt, "payload_sha256": "0" * 64})


def test_usage_task_cannot_rebuild_or_claim_an_automatic_archive_report(
    setup, installed_client, tmp_path, monkeypatch, archive_core, client_case
):
    store, _, _ = setup
    usage = installed_client
    run = str(uuid4())
    usage.start(run, "variance-analysis", sample_kind="synthetic")
    archive_run, tmp_path = _start(archive_core, client_case)
    _evidence(tmp_path, archive_run)
    _finish(archive_core, client_case, archive_run, tmp_path)
    source = tmp_path / "model_data_report_input.json"

    report_path = tmp_path / "model_data_report.json"
    retained = report_path.read_bytes()

    with pytest.raises(ValueError, match="could not be built"):
        usage.build_report(run, source, tmp_path)

    assert report_path.read_bytes() == retained
    projection = store.workflow_inspect(run)["run"]
    assert projection["receipts"] == []
    assert projection["state"] == "unknown"
    assert projection["feedback"] is None


def test_usage_task_cannot_stamp_archive_report_under_a_separate_task_identity(
    setup, installed_client, tmp_path, monkeypatch, archive_core, client_case
):
    store, _, _ = setup
    usage = installed_client
    run = str(uuid4())
    usage.start(run, "variance-analysis", sample_kind="synthetic")
    archive_run, tmp_path = _start(archive_core, client_case)
    _evidence(tmp_path, archive_run)
    _finish(archive_core, client_case, archive_run, tmp_path)
    retained_bytes = (tmp_path / "model_data_report.json").read_bytes()

    with pytest.raises(ValueError, match="bound and retried automatically"):
        usage.stamp_report(run, tmp_path / "model_data_report.json", tmp_path)

    assert (tmp_path / "model_data_report.json").read_bytes() == retained_bytes
    assert store.workflow_overview()["total"] == 1
    assert store.workflow_inspect(run)["run"]["receipts"] == []
