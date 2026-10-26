"""Browser-owned runs bind to the native computer through its scoped proof."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator

from modules.operational_incidents.contracts import Credentials
from modules.operational_incidents.store import IncidentNotFound
from tests.modules.operational_incidents.support import browser_headers
from tests.modules.workflow_usage.test_product_parity import (
    service,
    stores,
)
from tests.modules.workflow_usage.test_workflow_usage import event, setup


def call(client, headers, operation, **arguments):
    return client.post(
        f"/api/vera/incident-recovery/{operation}",
        headers=headers,
        json=arguments,
    )


def start(client, headers, run_id=None):
    item = event(run_id or uuid4(), host="cowork")
    result = call(
        client,
        headers,
        "workflow-record",
        event=item.model_dump(mode="json", exclude_none=True),
    )
    return item, result.json()


def native_envelope(ack, device=None):
    return {
        "product": "vera",
        "credentials": ack["reporting"]["host_link"]["credentials"],
        "device": device
        or {
            "device_id": str(uuid4()),
            "device_key": uuid4().hex,
            "native_app": "cowork",
        },
        "native_status": {
            "session_id": str(uuid4()),
            "protocol": 3,
            "product_version": "0.1.412",
            "host": "cowork",
            "platform": "macos",
        },
    }


def test_connector_run_links_native_computer_without_changing_original_owner(setup):
    store, _, client = setup
    headers = browser_headers(store)
    item, ack = start(client, headers)
    payload = native_envelope(ack)

    response = client.post("/api/operational-incidents/register", json=payload)

    assert response.status_code == 200
    assert response.json()["binding"] == "workflow-run"
    status = call(client, headers, "workflow-status", run_id=str(item.run_id)).json()
    assert status["installation_id"] == ack["installation_id"]
    assert status["reporting"]["computer_id"] == payload["device"]["device_id"]
    assert status["reporting"]["computer_link"] == "verified"
    assert "installation_key" not in json.dumps(status)
    assert status["state"] == "unknown"
    # The bearer ticket is not a new reporter and cannot read or write workflows.
    with pytest.raises(IncidentNotFound):
        store.workflow_status(Credentials(**payload["credentials"]), str(item.run_id))


def test_native_link_retry_is_idempotent_and_cannot_rebind_a_run(setup):
    store, _, client = setup
    item, ack = start(client, browser_headers(store))
    payload = native_envelope(ack)
    client.post("/api/operational-incidents/register", json=payload)

    retry = client.post("/api/operational-incidents/register", json=payload)

    assert retry.status_code == 200
    assert retry.json()["device_id"] == payload["device"]["device_id"]
    changed = native_envelope(ack)
    assert (
        client.post("/api/operational-incidents/register", json=changed).status_code
        == 409
    )
    assert store.workflow_inspect(str(item.run_id))["run"]["sequence"] == 1


def test_one_saved_connection_can_have_two_different_computers_and_test_exclusion(
    setup,
):
    store, _, client = setup
    headers = browser_headers(store)
    first, first_ack = start(client, headers)
    second, second_ack = start(client, headers)
    agent, user = native_envelope(first_ack), native_envelope(second_ack)
    client.post("/api/operational-incidents/register", json=agent)
    client.post("/api/operational-incidents/register", json=user)
    store.workflow_testing_reset([agent["device"]["device_id"]])

    result = store.workflow_computers("2026-01-01T00:00:00+00:00")

    assert first_ack["installation_id"] == second_ack["installation_id"]
    assert result["verified_active_user_computers"] == 1
    assert result["excluded_test_computers"] == 1
    assert result["excluded_test_runs"] == 1
    assert result["unlinked_user_reporting_instances"] == 0
    assert {entry["computer_id"] for entry in result["runs"]} == {
        agent["device"]["device_id"],
        user["device"]["device_id"],
    }
    # A later run on the same connection has no implied computer association.
    _, third = start(client, headers)
    assert third["reporting"]["computer_id"] is None


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("key", 404),
        ("product", 404),
        ("device", 409),
        ("app", 409),
        ("native_status", 409),
    ],
)
def test_scoped_link_rejects_missing_or_wrong_proof_without_registering_a_reporter(
    setup, fault, expected
):
    store, _, client = setup
    headers = browser_headers(store)
    item, ack = start(client, headers)
    payload = native_envelope(ack)
    if fault == "key":
        payload["credentials"]["installation_key"] = uuid4().hex
    elif fault == "product":
        payload["product"] = "clara"
    elif fault == "app":
        payload["device"]["native_app"] = "codex"
    else:
        payload.pop(fault)

    response = client.post("/api/operational-incidents/register", json=payload)

    assert response.status_code == expected
    status = call(client, headers, "workflow-status", run_id=str(item.run_id)).json()
    assert status["reporting"]["computer_link"] == "unlinked"


def test_expired_ticket_can_only_be_replaced_by_same_owned_event_replay(
    setup, monkeypatch
):
    store, _, client = setup
    monkeypatch.setattr(
        "modules.operational_incidents.store._now", lambda: "2026-10-18T12:00:00+00:00"
    )
    headers = browser_headers(store)
    item, ack = start(client, headers)
    monkeypatch.setattr(
        "modules.operational_incidents.store._now", lambda: "2026-10-18T12:16:00+00:00"
    )
    assert (
        client.post(
            "/api/operational-incidents/register", json=native_envelope(ack)
        ).status_code
        == 404
    )

    replay = call(
        client,
        headers,
        "workflow-record",
        event=item.model_dump(mode="json", exclude_none=True),
    ).json()

    assert replay["duplicate"] is True
    assert replay["current_sequence"] == 1
    assert replay["installation_id"] == ack["installation_id"]
    assert (
        replay["reporting"]["host_link"]["credentials"]
        != ack["reporting"]["host_link"]["credentials"]
    )
    assert (
        client.post(
            "/api/operational-incidents/register", json=native_envelope(replay)
        ).status_code
        == 200
    )
    unauthorized = call(
        client,
        browser_headers(store),
        "workflow-record",
        event=item.model_dump(mode="json", exclude_none=True),
    )
    assert unauthorized.status_code == 404
    assert "host_link" not in unauthorized.text


def test_rejected_completion_leaves_run_unchanged_without_echoing_input(setup):
    store, _, client = setup
    headers = browser_headers(store)
    item, _ = start(client, headers)
    invalid = event(item.run_id, 2, "completed").model_dump(
        mode="json", exclude_none=True
    )
    invalid.update(pipeline="private-client-content", host="cowork", sample_kind="user")

    result = call(client, headers, "workflow-record", event=invalid)

    assert result.status_code == 422
    assert "private-client-content" not in result.text
    assert store.workflow_inspect(str(item.run_id))["run"]["sequence"] == 1


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_advertised_schema_rejects_start_only_fields_on_completion(setup, product):
    store, _, client = setup
    response = client.post(
        f"/api/{product}/incident-recovery/schema",
        headers=browser_headers(store, product),
        json={"operation": "workflow-record"},
    )
    assert response.status_code == 200
    validator = Draft202012Validator(response.json()["input_schema"])
    complete = event(uuid4(), 2, "completed", product=product).model_dump(
        mode="json", exclude_none=True
    )
    validator.validate({"event": complete})

    errors = list(
        validator.iter_errors(
            {
                "event": {
                    **complete,
                    "pipeline": "journal-sampling",
                    "host": "cowork",
                    "sample_kind": "user",
                }
            }
        )
    )

    assert errors


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_native_scoped_link_works_for_each_product(service, product):
    client, store, _, _, _, _ = service
    headers = browser_headers(store, product)
    start_event = event(
        uuid4(),
        host="cowork",
        product=product,
        pipeline=(
            "business-planning" if product != "lucia" else "quesito-legale-fiscale"
        ),
    )
    ack = client.post(
        f"/api/{product}/incident-recovery/workflow-record",
        headers=headers,
        json={"event": start_event.model_dump(mode="json", exclude_none=True)},
    ).json()
    payload = native_envelope(ack)
    payload["product"] = product

    response = client.post("/api/operational-incidents/register", json=payload)

    assert response.status_code == 200
    assert (
        store.workflow_computers("2026-01-01T00:00:00+00:00", product)[
            "verified_active_user_computers"
        ]
        == 1
    )
    assert response.json()["device_id"] == payload["device"]["device_id"]
