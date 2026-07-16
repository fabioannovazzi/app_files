from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # type: ignore  # pylint: disable=wrong-import-position

from modules.auth.config import get_auth_config
from modules.pdp.api import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _disable_auth_for_taxonomy_queue_api_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_var in ("AUTH_ENABLED", "GOOGLE_CLIENT_ID", "AUTH_SESSION_SECRET"):
        monkeypatch.delenv(env_var, raising=False)
    get_auth_config.cache_clear()
    yield
    get_auth_config.cache_clear()


def test_taxonomy_queue_page_route_is_registered() -> None:
    page_routes = [
        route
        for route in app.routes
        if getattr(route, "path", "") == "/review/issues/page"
    ]

    assert len(page_routes) == 1
    assert getattr(page_routes[0].endpoint, "__name__", "") == "taxonomy_issues_page"


