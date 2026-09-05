from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import pytest
from fastapi.testclient import TestClient

from modules.hosted_services import api as pdp_api


def test_fastapi_entrypoint_reexports_single_app_instance() -> None:
    from src.fastapi_app_entry import app as entrypoint_app

    assert entrypoint_app is pdp_api.app


def _event_handler(
    handlers: list[Callable[[], Awaitable[None]]], name: str
) -> Callable[[], Awaitable[None]]:
    return next(handler for handler in handlers if handler.__name__ == name)


def test_create_app_startup_starts_voice_retention_cleanup(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        pdp_api,
        "process_pending_notifications",
        lambda: calls.append("notifications"),
    )
    monkeypatch.setattr(
        pdp_api, "_start_session_cleanup", lambda: calls.append("sessions")
    )
    monkeypatch.setattr(
        pdp_api,
        "start_voice_retention_cleanup",
        lambda: calls.append("voice-retention"),
    )
    test_app = pdp_api.create_app()
    startup = _event_handler(test_app.router.on_startup, "_startup_cleanup")

    asyncio.run(startup())

    assert calls == ["notifications", "sessions", "voice-retention"]


def test_create_app_shutdown_stops_voice_retention_cleanup(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        pdp_api,
        "stop_voice_retention_cleanup",
        lambda: calls.append("voice-retention"),
    )
    monkeypatch.setattr(
        pdp_api, "_stop_session_cleanup", lambda: calls.append("sessions")
    )
    test_app = pdp_api.create_app()
    shutdown = _event_handler(test_app.router.on_shutdown, "_shutdown_cleanup")

    asyncio.run(shutdown())

    assert calls == ["voice-retention", "sessions"]


def test_create_app_unhandled_exception_returns_error_id_without_logging_query(
    caplog: pytest.LogCaptureFixture,
) -> None:
    test_app = pdp_api.create_app()

    @test_app.get("/__boom")
    def _boom() -> dict[str, str]:
        raise RuntimeError("boom")

    client = TestClient(test_app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR):
        response = client.get("/__boom?sensitive-token=do-not-log")

    assert response.status_code == 500
    payload = response.json()
    assert "Internal server error" in str(payload.get("detail") or "")
    assert str(payload.get("error_id") or "").strip()
    assert "has_query=True" in caplog.text
    assert "do-not-log" not in caplog.text


def test_create_app_rejects_untrusted_host_header() -> None:
    client = TestClient(pdp_api.create_app(), raise_server_exceptions=False)

    response = client.get("/", headers={"Host": "attacker.example"})

    assert response.status_code == 400


def test_create_app_does_not_mount_hosted_whatsapp_routes() -> None:
    route_paths = {getattr(route, "path", "") for route in pdp_api.create_app().routes}

    assert not any(path.startswith("/whatsapp") for path in route_paths)
    assert "/.well-known/oauth-protected-resource" not in route_paths
    assert "/.well-known/oauth-authorization-server" not in route_paths


def test_create_app_mounts_only_current_hosted_route_families() -> None:
    app = pdp_api.create_app()
    route_paths = {getattr(route, "path", "") for route in app.routes}
    retired_prefixes = (
        "/check",
        "/hierarchy",
        "/identify-columns",
        "/presentations",
        "/projects",
        "/review",
        "/slides",
    )

    assert "/api/vera/run-receipts" in route_paths
    assert not any(path.startswith(retired_prefixes) for path in route_paths if path)
    assert "/case-notes/interview/{token}" in route_paths
    assert "/case-notes/api/voice/interviews" in route_paths
    assert "/case-notes/api/attribute-reporting/evidence-packs" in route_paths
    assert "/api/change-requests" in route_paths
    assert "/auth/magic/request" in route_paths
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/check/page"),
        ("get", "/hierarchy/page"),
        ("post", "/identify-columns/messages"),
        ("get", "/presentations/page"),
        ("get", "/projects/page"),
        ("get", "/review/health"),
        ("get", "/review/deterministic-policy/page"),
        ("get", "/review/explicit-rules/page"),
        ("get", "/review/issues/page"),
        ("get", "/review/product-hypotheses/page"),
        ("get", "/slides/page"),
        ("get", "/docs"),
        ("get", "/redoc"),
        ("get", "/openapi.json"),
    ],
)
def test_retired_fastapi_surfaces_return_json_404(method: str, path: str) -> None:
    client = TestClient(pdp_api.create_app())

    response = getattr(client, method)(path)

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
