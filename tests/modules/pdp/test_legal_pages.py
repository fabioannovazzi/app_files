from __future__ import annotations

from typing import Iterator

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import (
    TestClient,  # type: ignore  # pylint: disable=wrong-import-position
)
from starlette.responses import HTMLResponse

from modules.auth.config import get_auth_config
from modules.pdp import api as pdp_api
from modules.pdp.api import app


@pytest.fixture(autouse=True)
def _reset_auth_config(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dummy-client-id")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "dummy-secret")
    get_auth_config.cache_clear()
    yield
    get_auth_config.cache_clear()


def _capture_template_response(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    captured: dict[str, object] = {}

    def _template_response(
        request: object,
        name: str,
        context: dict[str, object],
        **kwargs: object,
    ) -> HTMLResponse:
        captured["request"] = request
        captured["name"] = name
        captured["context"] = context
        return HTMLResponse("ok", status_code=int(kwargs.get("status_code", 200)))

    monkeypatch.setattr(pdp_api.templates, "TemplateResponse", _template_response)
    return captured


def test_zero_retention_page_is_public_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_template_response(monkeypatch)
    client = TestClient(app)

    response = client.get("/zero-retention")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    assert captured["name"] == "legal_page.html"
    context = captured["context"]
    assert isinstance(context, dict)
    page = context["page"]
    assert isinstance(page, dict)
    assert page["title"] == "Zero Retention Policy"
    assert "does not receive or retain Customer Content" in page["summary"]
    assert "OpenAI" not in str(page)
    assert context["active_legal_page"] == "zero-retention"


def test_privacy_page_redirects_permanently_to_zero_retention() -> None:
    client = TestClient(app)

    response = client.get("/privacy", follow_redirects=False)

    assert response.status_code == 308
    assert response.headers["location"] == "/zero-retention"


def test_terms_page_is_public_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_template_response(monkeypatch)
    client = TestClient(app)

    response = client.get("/terms")

    assert response.status_code == 200
    assert captured["name"] == "legal_page.html"
    context = captured["context"]
    assert isinstance(context, dict)
    page = context["page"]
    assert isinstance(page, dict)
    assert page["title"] == "Terms of Service"
    assert context["active_legal_page"] == "terms"
    terms_text = str(page)
    assert "https://mparanza.com/zero-retention" in terms_text
    assert "https://mparanza.com/privacy" not in terms_text
    assert "Mparanza receives no license" in terms_text
    assert "improve, and develop" not in terms_text
    assert "OpenAI" not in terms_text


def test_support_page_is_public_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_template_response(monkeypatch)
    client = TestClient(app)

    response = client.get("/support")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    assert captured["name"] == "legal_page.html"
    context = captured["context"]
    assert isinstance(context, dict)
    page = context["page"]
    assert isinstance(page, dict)
    assert page["title"] == "Customer Support"
    assert page["contact_email"] == "fabio@mparanza.com"
    assert "no automatic access" in str(page)
    assert context["active_legal_page"] == "support"
