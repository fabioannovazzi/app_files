"""Completed pipeline runs drive a fresh, device-deduplicated public legend."""

from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.operational_incidents import api
from modules.operational_incidents import store as incident_store
from modules.operational_incidents.contracts import Credentials, DeviceCredentials
from modules.operational_incidents.store import IncidentStore
from modules.pdp.postgres_compat import PostgresCompatCursor
from modules.workflow_usage.contracts import WorkflowEvent, pipeline_catalog

BEFORE = "2026-10-17T10:00:00+00:00"
BASELINE = "2026-10-17T11:00:00+00:00"
AFTER = "2026-10-17T12:00:00+00:00"
ROOT = Path(__file__).resolve().parents[3]


def test_browser_projection_preserves_evidence_on_outage_and_handles_reset():
    result = subprocess.run(
        ["node", "--test", "tests/modules/workflow_usage/testing_status_browser.cjs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def register(store, device=None, app="codex"):
    owner = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    store.register(
        owner, device.model_copy(update={"native_app": app}) if device else None
    )
    return owner


def device():
    return DeviceCredentials(device_id=uuid4(), device_key=uuid4().hex)


def record(
    store,
    owner,
    kind="completed",
    sample="user",
    occurred=AFTER,
    pipeline="journal-sampling",
):
    run_id = uuid4()
    common = {"run_id": run_id, "product_version": "0.1.405", "occurred_at": occurred}
    store.workflow_record(
        owner,
        WorkflowEvent(
            **common,
            event_id=uuid4(),
            sequence=1,
            kind="started",
            pipeline=pipeline,
            host="codex",
            sample_kind=sample,
        ),
    )
    if kind != "started":
        store.workflow_record(
            owner, WorkflowEvent(**common, event_id=uuid4(), sequence=2, kind=kind)
        )
    return str(run_id)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    store = IncidentStore(tmp_path / "testing.sqlite3")
    agent = device()
    agent_owner = register(store, agent)
    monkeypatch.setattr(incident_store, "_now", lambda: BASELINE)
    store.workflow_testing_reset([str(agent.device_id)])
    monkeypatch.setattr(incident_store, "_now", lambda: AFTER)
    return store, agent, agent_owner


def test_unconfigured_service_starts_every_pipeline_at_untried(tmp_path):
    store = IncidentStore(tmp_path / "testing.sqlite3")

    result = store.workflow_testing()

    assert result["epoch_id"] is None
    assert set(result["pipelines"]) == set(pipeline_catalog())
    assert {row["status"] for row in result["pipelines"].values()} == {"untried"}


def test_completed_run_is_counted_through_production_postgres_cursor(
    setup, monkeypatch
):
    store, _, owner = setup
    run_id = record(store, owner)
    original_connection = store._connection

    @contextmanager
    def production_cursor_connection():
        with original_connection() as connection:

            class Connection:
                def execute(self, *args):
                    return PostgresCompatCursor(connection, connection.execute(*args))

            yield Connection()

    monkeypatch.setattr(store, "_connection", production_cursor_connection)

    result = store.workflow_testing()["pipelines"]["journal-sampling"]

    assert result["status"] == "agent"
    assert result["agent_runs"] == [run_id]


@pytest.mark.parametrize(
    "primary,other",
    [
        ("adversarial-opinion", "quesito-legale-fiscale"),
        ("report-enti-locali", "financial-report-builder"),
    ],
)
def test_standalone_specialist_completion_promotes_only_its_own_function(
    setup, primary, other
):
    store, _, _ = setup
    owner = register(store, device())
    run_id = record(store, owner, pipeline=primary)

    result = store.workflow_testing()["pipelines"]

    assert result[primary]["status"] == "tried"
    assert result[other]["status"] == "untried"
    assert list(result[primary]["professional_devices"].values()) == [[run_id]]


def test_reset_clears_levels_without_deleting_runs_or_incidents(setup, monkeypatch):
    store, agent, owner = setup
    run_id = record(store, owner)
    original_run = store.workflow_inspect(run_id)
    incident_before = store.registry()
    previous_epoch = store.workflow_testing()["epoch_id"]
    monkeypatch.setattr(incident_store, "_now", lambda: "2026-10-17T13:00:00+00:00")

    epoch = store.workflow_testing_reset([str(agent.device_id)])

    assert epoch["epoch_id"] != previous_epoch
    assert {x["status"] for x in store.workflow_testing()["pipelines"].values()} == {
        "untried"
    }
    assert store.workflow_inspect(run_id) == original_run
    assert store.registry() == incident_before


@pytest.mark.parametrize("devices", [[], [str(uuid4())], ["not-a-device"]])
def test_reset_rejects_unregistered_computers_without_changing_epoch(setup, devices):
    store, _, _ = setup
    before = store.workflow_testing()["epoch_id"]

    with pytest.raises(ValueError):
        store.workflow_testing_reset(devices)

    assert store.workflow_testing()["epoch_id"] == before


@pytest.mark.parametrize("app", ["codex", "cowork"])
@pytest.mark.parametrize("sample", ["user", "synthetic", "agent_test"])
def test_owners_computer_is_agent_for_every_app_and_sample(setup, app, sample):
    store, agent, _ = setup
    owner = register(store, agent, app)
    run_id = record(store, owner, sample=sample)

    result = store.workflow_testing()["pipelines"]["journal-sampling"]

    assert result["status"] == "agent"
    assert result["agent_runs"] == [run_id]
    assert result["professional_devices"] == {}


@pytest.mark.parametrize("kind", ["started", "failed", "cancelled"])
def test_only_completed_pipelines_advance_status(setup, kind):
    store, _, _ = setup
    record(store, register(store, device()), kind=kind)

    result = store.workflow_testing()["pipelines"]["journal-sampling"]

    assert result["status"] == "untried"


@pytest.mark.parametrize(
    "count,expected", [(1, "tried"), (2, "tried"), (3, "repeated")]
)
def test_professional_levels_count_distinct_other_computers(setup, count, expected):
    store, _, agent_owner = setup
    record(store, agent_owner)
    for _ in range(count):
        record(store, register(store, device()))

    result = store.workflow_testing()["pipelines"]["journal-sampling"]

    assert result["status"] == expected
    assert len(result["professional_devices"]) == count


def test_reinstalls_apps_and_repeated_runs_on_same_computer_count_once(setup):
    store, _, _ = setup
    professional = device()
    first = register(store, professional)
    second = register(store, professional, "cowork")
    record(store, first)
    record(store, first)
    record(store, second)

    result = store.workflow_testing()["pipelines"]["journal-sampling"]

    assert result["status"] == "tried"
    assert len(result["professional_devices"]) == 1
    assert len(result["professional_devices"][str(professional.device_id)]) == 3


@pytest.mark.parametrize("sample", ["synthetic", "agent_test"])
def test_controlled_fixtures_elsewhere_never_create_professional_evidence(
    setup, sample
):
    store, _, _ = setup
    record(store, register(store, device()), sample=sample)

    result = store.workflow_testing()

    assert result["pipelines"]["journal-sampling"]["status"] == "untried"
    assert result["excluded_test_runs"] == 1


@pytest.mark.parametrize("occurred", [BEFORE, BASELINE, "2026-10-17T12:00:00+02:00"])
def test_delayed_old_completions_do_not_repopulate_reset(setup, occurred):
    store, _, owner = setup
    record(store, owner, occurred=occurred)

    result = store.workflow_testing()["pipelines"]["journal-sampling"]

    assert result["status"] == "untried"


def test_unlinked_computer_waits_for_actual_binding_then_counts_without_replay(setup):
    store, _, _ = setup
    owner = register(store)
    run_id = record(store, owner)
    pending = store.workflow_testing()["pipelines"]["journal-sampling"]
    assert pending["status"] == "untried"
    assert pending["unlinked_runs"] == [run_id]

    store.register(owner, device())

    result = store.workflow_testing()["pipelines"]["journal-sampling"]
    assert result["status"] == "tried"
    assert result["unlinked_runs"] == []


def test_low_stars_and_missing_receipt_do_not_change_testing_level(setup):
    store, _, _ = setup
    owner = register(store, device())
    run_id = record(store, owner)

    store.workflow_record(
        owner,
        WorkflowEvent(
            event_id=uuid4(),
            run_id=run_id,
            sequence=3,
            kind="feedback",
            occurred_at=AFTER,
            product_version="0.1.405",
            stars=1,
            comment="Da migliorare",
            feedback_source="user_chat",
        ),
    )

    assert (
        store.workflow_testing()["pipelines"]["journal-sampling"]["status"] == "tried"
    )


def test_public_endpoint_returns_only_levels_and_has_no_reset_route(setup):
    store, _, owner = setup
    record(store, owner)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_incident_store] = lambda: store
    client = TestClient(app)

    response = client.get("/api/vera/testing-status")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"schema_version", "epoch_id", "started_at", "pipelines"}
    assert body["pipelines"]["journal-sampling"] == "agent"
    assert set(body["pipelines"].values()) == {"untried", "agent"}
    assert response.headers["cache-control"] == "no-store"
    assert client.post("/api/vera/testing-status").status_code == 405


def test_page_resets_every_icon_and_maps_package_aliases_to_primary_pipelines():
    page = BeautifulSoup(
        (ROOT / "static/shared/vera/index.html").read_text(), "html.parser"
    )
    indicators = page.select('.function-test-indicator[role="img"]')

    assert len(indicators) == len(page.select("a.module-row h4"))
    assert {node["data-test-status"] for node in indicators} == {"untried"}
    assert {node["aria-label"] for node in indicators} == {
        "Da provare su casi concreti"
    }
    assert (
        page.select_one(
            '[data-vera-workflow="bilancio-xbrl-it"] [data-testing-pipeline]'
        )["data-testing-pipeline"]
        == "bilancio-oic"
    )
    assert (
        page.select_one('[data-vera-workflow="check-entries"] [data-testing-pipeline]')[
            "data-testing-pipeline"
        ]
        == "vouching"
    )
    assert (
        page.select_one(
            '[data-vera-workflow="passive-invoice-audit"] [data-testing-pipeline]'
        )["data-testing-pipeline"]
        == "purchase-invoice-review"
    )
    assert (
        page.select_one(
            '[data-vera-workflow="report-builder"] [data-testing-pipeline]'
        )["data-testing-pipeline"]
        == "financial-report-builder"
    )
    mapped = {
        node["data-testing-pipeline"] for node in page.select("[data-testing-pipeline]")
    }
    assert mapped <= pipeline_catalog().keys()
    unmapped = {
        node.find_parent("a")["href"]
        for node in indicators
        if not node.has_attr("data-testing-pipeline")
    }
    assert unmapped == {"../studio-archive/index.html", "../learn-with-vera/index.html"}
    assert {"adversarial-opinion", "report-enti-locali"} <= mapped
    assert "studio-archive" not in mapped
    assert page.select_one('script[src="../vera-testing-status.js"]') is not None


def test_native_usage_transport_registers_actual_computer_without_incident(
    tmp_path, monkeypatch
):
    from tests.plugins.test_operational_incident_client import client

    module, store, transport = client(tmp_path, monkeypatch)
    monkeypatch.setenv("MPARANZA_INCIDENT_HOST", "codex")
    owner = module.local_context()["credentials"]

    def post(operation, payload):
        if operation == "workflow-record":
            return store.workflow_record(
                Credentials.model_validate(payload["credentials"]),
                WorkflowEvent.model_validate(payload["event"]),
            )
        return transport(operation, payload)

    monkeypatch.setattr(module, "_post", post)
    item = WorkflowEvent(
        event_id=uuid4(),
        run_id=uuid4(),
        sequence=1,
        kind="started",
        occurred_at=AFTER,
        product_version="0.1.406",
        pipeline="journal-sampling",
        host="codex",
        sample_kind="user",
    )

    result = module.workflow_transport(
        "workflow-record",
        {
            "credentials": owner,
            "event": item.model_dump(mode="json", exclude_none=True),
        },
    )

    assert result["recorded"] is True
    installation = store.installation(owner["installation_id"])
    assert installation["host_link"]["device_id"] == module.host_identity()["device_id"]
    assert installation["app_link"]["native_app"] == "codex"
    assert store.queue() == []


@pytest.mark.parametrize("unavailable", ["cowork_guest", "identity_unreadable"])
def test_missing_native_identity_does_not_block_usage_delivery(
    tmp_path, monkeypatch, unavailable
):
    from tests.plugins.test_operational_incident_client import client

    module, store, transport = client(tmp_path, monkeypatch)
    owner = module.local_context()["credentials"]
    if unavailable == "cowork_guest":
        monkeypatch.setenv("MPARANZA_INCIDENT_HOST", "cowork")
        monkeypatch.setattr(module.platform, "system", lambda: "Linux")
    else:

        def unavailable_identity():
            raise OSError("unavailable")

        monkeypatch.setattr(module, "_host_credentials", unavailable_identity)

    def post(operation, payload):
        if operation == "workflow-status":
            return {"observed": "transport-continues"}
        return transport(operation, payload)

    monkeypatch.setattr(module, "_post", post)

    result = module.workflow_transport("workflow-status", {"credentials": owner})

    assert result == {"observed": "transport-continues"}
    assert store.installation(owner["installation_id"])["host_link"] is None


def test_supported_cli_resets_only_testing_and_reads_new_epoch(
    setup, monkeypatch, capsys
):
    import sys

    from scripts import manage_workflow_usage

    store, agent, _ = setup
    monkeypatch.setattr(
        manage_workflow_usage, "load_env_from_secrets_file", lambda: None
    )
    monkeypatch.setattr(manage_workflow_usage, "IncidentStore", lambda path: store)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "manage_workflow_usage.py",
            "testing-reset",
            "--agent-device",
            str(agent.device_id),
        ],
    )

    manage_workflow_usage.main()

    reset = json.loads(capsys.readouterr().out)
    assert reset["agent_devices"] == [str(agent.device_id)]
    assert store.workflow_testing()["epoch_id"] == reset["epoch_id"]
