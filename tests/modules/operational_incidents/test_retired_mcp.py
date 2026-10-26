"""Retired remote MCP and OAuth URLs cannot accept reporting connections."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.operational_incidents import api
from modules.operational_incidents.store import IncidentStore

__all__: list[str] = []


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/mcp/vera-incidents"),
        ("POST", "/mcp/clara-incidents"),
        ("POST", "/mcp/lucia-incidents"),
        ("GET", "/.well-known/oauth-protected-resource/mcp/vera-incidents"),
        ("GET", "/.well-known/oauth-protected-resource/mcp/clara-incidents"),
        ("GET", "/.well-known/oauth-protected-resource/mcp/lucia-incidents"),
        ("GET", "/.well-known/oauth-authorization-server"),
        ("POST", "/oauth/vera-incidents/register"),
        ("GET", "/oauth/vera-incidents/authorize"),
        ("POST", "/oauth/vera-incidents/token"),
        ("POST", "/oauth/vera-incidents/revoke"),
    ],
)
def test_old_reporting_and_authentication_urls_are_unavailable(tmp_path, method, path):
    store = IncidentStore(tmp_path / "incidents.sqlite3")
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_incident_store] = lambda: store

    response = TestClient(app).request(method, path, json={})

    assert response.status_code == 404
    assert "www-authenticate" not in response.headers
