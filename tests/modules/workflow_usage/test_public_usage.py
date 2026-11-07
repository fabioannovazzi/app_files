"""The public dashboard counts distinct users, not runs or private identities."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.operational_incidents import api
from modules.operational_incidents.contracts import Credentials, DeviceCredentials
from modules.operational_incidents.store import IncidentStore
from modules.workflow_usage.contracts import WorkflowEvent

NOW = "2026-11-07T12:00:00+00:00"
OLD = "2026-01-01T12:00:00+00:00"
HTTPS_VERSIONS = {"vera": "0.1.492", "clara": "0.1.347", "lucia": "0.1.176"}


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.operational_incidents.store._now", lambda: NOW)
    return IncidentStore(tmp_path / "usage.sqlite3")


def device(app="codex"):
    return DeviceCredentials(device_id=uuid4(), device_key=uuid4().hex, native_app=app)


def add_run(
    store,
    computer,
    *,
    product="vera",
    pipeline="business-planning",
    state=None,
    sample="user",
    version=None,
    host=None,
):
    owner = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    store.register(owner, computer, product=product)
    common = {
        "run_id": uuid4(),
        "product": product,
        "product_version": version or HTTPS_VERSIONS[product],
        "occurred_at": NOW,
    }
    store.workflow_record(
        owner,
        WorkflowEvent(
            **common,
            event_id=uuid4(),
            sequence=1,
            kind="started",
            pipeline=pipeline,
            host=host or (computer.native_app if computer else "codex"),
            sample_kind=sample,
        ),
    )
    if state:
        store.workflow_record(
            owner,
            WorkflowEvent(**common, event_id=uuid4(), sequence=2, kind=state),
        )
    return owner, str(common["run_id"])


def test_public_usage_deduplicates_retries_and_counts_any_completion(store):
    computer = device()
    add_run(store, computer)
    add_run(store, computer, state="failed")
    add_run(store, computer, state="cancelled")
    add_run(store, computer, state="completed")

    result = store.public_workflow_usage()

    assert result["totals"] == {"started": 1, "completed": 1, "failed": 0}
    assert result["functions"] == [
        {
            "product": "vera",
            "pipeline": "business-planning",
            "label": "Business plan",
            "started": 1,
            "completed": 1,
            "failed": 0,
        }
    ]


def test_public_usage_deduplicates_total_across_products_functions_and_apps(store):
    computer = device()
    add_run(store, computer, state="completed")
    add_run(store, computer, pipeline="journal-sampling")
    add_run(
        store,
        computer.model_copy(update={"native_app": "cowork"}),
        product="clara",
    )

    result = store.public_workflow_usage()

    assert result["totals"] == {"started": 1, "completed": 1, "failed": 0}
    assert len(result["functions"]) == 3
    assert result["apps"] == [
        {"app": "codex", "started": 1, "completed": 1, "failed": 0},
        {"app": "cowork", "started": 1, "completed": 0, "failed": 1},
    ]


def test_public_usage_omits_designated_owner_across_products_and_explicit_tests(store):
    agent = device()
    add_run(store, agent, state="completed")
    add_run(store, agent, product="clara", state="completed")
    store.workflow_testing_reset([str(agent.device_id)])
    add_run(store, device(), state="completed", sample="agent_test")
    add_run(store, device(), state="completed", sample="synthetic")
    add_run(store, device(), state="completed")

    result = store.public_workflow_usage()

    assert result["totals"] == {"started": 1, "completed": 1, "failed": 0}
    assert len(result["functions"]) == 1
    assert "excluded" not in json.dumps(result)


@pytest.mark.parametrize("state", (None, "failed", "cancelled"))
def test_public_usage_counts_started_without_completion_as_failed(store, state):
    add_run(store, device(), state=state, host="antigravity")

    result = store.public_workflow_usage()

    assert result["totals"] == {"started": 1, "completed": 0, "failed": 1}
    assert result["apps"] == [
        {"app": "antigravity", "started": 1, "completed": 0, "failed": 1}
    ]


@pytest.mark.parametrize(
    "product,pipeline,version,expected",
    (
        ("vera", "business-planning", "0.1.403", 0),
        ("vera", "business-planning", "0.1.404", 0),
        ("vera", "business-planning", "0.1.491", 0),
        ("vera", "business-planning", "0.1.492", 1),
        ("vera", "business-planning", "0.1.1000", 1),
        ("clara", "business-planning", "0.1.297", 0),
        ("clara", "business-planning", "0.1.298", 0),
        ("clara", "business-planning", "0.1.346", 0),
        ("clara", "business-planning", "0.1.347", 1),
        ("lucia", "controllo-documento", "0.1.120", 0),
        ("lucia", "controllo-documento", "0.1.121", 0),
        ("lucia", "controllo-documento", "0.1.175", 0),
        ("lucia", "controllo-documento", "0.1.176", 1),
    ),
)
def test_public_usage_uses_each_products_numeric_version_threshold(
    store, product, pipeline, version, expected
):
    add_run(store, device(), product=product, pipeline=pipeline, version=version)

    result = store.public_workflow_usage()

    assert result["totals"]["started"] == expected


def test_public_usage_keeps_older_received_activity_without_a_time_window(
    store, monkeypatch
):
    monkeypatch.setattr("modules.operational_incidents.store._now", lambda: OLD)
    add_run(store, device(), state="completed")
    monkeypatch.setattr("modules.operational_incidents.store._now", lambda: NOW)

    result = store.public_workflow_usage()

    assert result["totals"] == {"started": 1, "completed": 1, "failed": 0}
    assert result["updated_at"] == NOW


def test_public_usage_legacy_completion_does_not_complete_an_https_start(store):
    computer = device()
    add_run(store, computer, version="0.1.491", state="completed")
    add_run(store, computer, version="0.1.492")

    result = store.public_workflow_usage()

    assert result["totals"] == {"started": 1, "completed": 0, "failed": 1}


@pytest.mark.parametrize("host", ("chatgpt", "unknown"))
def test_public_usage_counts_only_the_three_requested_apps(store, host):
    add_run(store, device(), host=host)

    result = store.public_workflow_usage()

    assert result["totals"] == {"started": 0, "completed": 0, "failed": 0}
    assert result["functions"] == []
    assert result["apps"] == []


def test_public_usage_never_substitutes_reporting_ids_for_missing_computer_proof(store):
    add_run(store, None, state="completed")

    result = store.public_workflow_usage()

    assert result["totals"] == {"started": 0, "completed": 0, "failed": 0}
    assert result["identity_complete"] is False


def test_public_usage_endpoint_exposes_only_aggregate_fields_and_no_write_route(store):
    computer = device()
    owner, run_id = add_run(store, computer, state="completed")
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_incident_store] = lambda: store
    client = TestClient(app)

    response = client.get("/api/usage-summary")

    assert response.status_code == 200
    assert set(response.json()) == {
        "updated_at",
        "minimum_versions",
        "minimum_version_release_dates",
        "supported_apps",
        "identity_complete",
        "totals",
        "functions",
        "apps",
    }
    assert response.json()["minimum_version_release_dates"] == {
        "vera": "2026-10-25",
        "clara": "2026-10-25",
        "lucia": "2026-10-25",
    }
    assert response.json()["minimum_versions"] == HTTPS_VERSIONS
    assert str(computer.device_id) not in response.text
    assert str(owner.installation_id) not in response.text
    assert owner.installation_key not in response.text
    assert run_id not in response.text
    assert "no-store" in response.headers["cache-control"]
    assert client.post("/api/usage-summary").status_code == 405


@pytest.mark.parametrize("product", ("vera", "clara", "lucia"))
def test_each_product_links_to_public_usage_with_a_readable_label(product):
    from bs4 import BeautifulSoup

    page = BeautifulSoup(
        Path(f"static/shared/{product}/index.html").read_text(encoding="utf-8"),
        "html.parser",
    )

    link = page.select_one('a[href="../utilizzo/index.html"]')

    assert link is not None
    assert link.get_text(strip=True) == "Utilizzo e risultati"


def test_usage_browser_keeps_last_counts_on_failure_and_renders_aggregate_rows():
    result = subprocess.run(
        ["node", "tests/modules/workflow_usage/public_usage_browser.cjs"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
