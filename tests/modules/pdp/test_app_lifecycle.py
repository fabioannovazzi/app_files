from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from fastapi.testclient import TestClient

from modules.pdp import api as pdp_api


def _event_handler(
    handlers: list[Callable[[], Awaitable[None]]], name: str
) -> Callable[[], Awaitable[None]]:
    return next(handler for handler in handlers if handler.__name__ == name)


def test_create_app_startup_starts_voice_retention_cleanup(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        pdp_api, "_mark_interrupted_background_jobs", lambda: calls.append("jobs")
    )
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

    assert calls == ["jobs", "notifications", "sessions", "voice-retention"]


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


def test_create_app_unhandled_exception_returns_error_id() -> None:
    test_app = pdp_api.create_app()

    @test_app.get("/__boom")
    def _boom() -> dict[str, str]:
        raise RuntimeError("boom")

    client = TestClient(test_app, raise_server_exceptions=False)
    response = client.get("/__boom?x=1")

    assert response.status_code == 500
    payload = response.json()
    assert "Internal server error" in str(payload.get("detail") or "")
    assert str(payload.get("error_id") or "").strip()
