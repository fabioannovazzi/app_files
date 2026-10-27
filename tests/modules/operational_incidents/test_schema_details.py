"""Reproduce the incomplete supplement without echoing its submitted values."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.operational_incidents.api import get_incident_store, router
from tests.modules.operational_incidents.support import browser_headers
from tests.modules.operational_incidents.test_incidents import registered, report


@pytest.mark.parametrize("route", ["native", "browser"])
def test_complete_capture_rejection_explains_required_evidence(tmp_path, route):
    store, owner = registered(tmp_path)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_incident_store] = lambda: store
    payload = report().model_dump(mode="json")
    payload["capture_state"] = "complete"
    payload["diagnostics"][0]["errno"] = 1
    payload["diagnostics"][0]["message"] = "DO_NOT_ECHO"
    client = TestClient(app)
    if route == "native":
        endpoint = "/api/operational-incidents/report"
        arguments = {"credentials": owner.model_dump(mode="json"), "report": payload}
        headers = {}
    else:
        endpoint = "/api/vera/incident-recovery/report"
        arguments = {"report": payload}
        headers = browser_headers(store)
        client.post("/api/vera/incident-recovery/register", headers=headers, json={})

    result = client.post(endpoint, headers=headers, json=arguments)

    assert result.status_code == 422
    assert result.json()["detail"] == [
        {
            "loc": ["report"],
            "type": "value_error",
            "msg": "Value error, Complete capture requires technical evidence",
        }
    ]
    assert "DO_NOT_ECHO" not in result.text
    assert owner.installation_key not in result.text


def test_unknown_field_names_and_values_are_not_echoed(tmp_path):
    store, owner = registered(tmp_path)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_incident_store] = lambda: store

    result = TestClient(app).post(
        "/api/operational-incidents/report",
        json={
            "credentials": owner.model_dump(mode="json"),
            "private_client_name": "private_client_value",
        },
    )

    assert result.status_code == 422
    assert result.json()["detail"] == [
        {"loc": ["unrecognized_field"], "type": "extra_forbidden"}
    ]
    assert "private_client" not in result.text
