from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import (  # type: ignore  # pylint: disable=wrong-import-position
    TestClient,
)
from starlette.responses import HTMLResponse

from modules.auth.config import get_auth_config
from modules.pdp import api as pdp_api
from modules.pdp.api import _get_landing_page_content, app
from modules.pdp.data_handling_content import get_data_handling_content

ROOT = Path(__file__).resolve().parents[3]


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


@pytest.mark.parametrize(
    ("lang", "page_title", "security_title"),
    (
        ("en", "How your data is handled.", "Secure by design."),
        ("it", "Come vengono gestiti i tuoi dati.", "Sicuri fin dalla progettazione."),
        ("fr", "Comment vos données sont traitées.", "Sécurisés dès la conception."),
        ("de", "So werden Ihre Daten verarbeitet.", "Sicher konzipiert."),
    ),
)
def test_data_handling_page_is_public_and_localized(
    monkeypatch: pytest.MonkeyPatch,
    lang: str,
    page_title: str,
    security_title: str,
) -> None:
    captured = _capture_template_response(monkeypatch)
    client = TestClient(app)

    response = client.get(f"/data-handling?lang={lang}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    assert f"lang={lang}" in response.headers["set-cookie"]
    assert captured["name"] == "data_handling.html"
    context = captured["context"]
    assert isinstance(context, dict)
    assert context["lang"] == lang
    assert context["auth_enabled"] is False
    page = context["page"]
    assert isinstance(page, dict)
    assert page["title"] == page_title
    assert str(page["closing"]).startswith(security_title)


@pytest.mark.parametrize(
    ("lang", "security_title"),
    (
        ("en", "Secure by design."),
        ("it", "Sicuri fin dalla progettazione."),
        ("fr", "Sécurisés dès la conception."),
        ("de", "Sicher konzipiert."),
    ),
)
def test_homepage_security_copy_is_localized(lang: str, security_title: str) -> None:
    security = _get_landing_page_content(lang)["security"]

    assert security["title"] == security_title
    assert security["cta_href"] == "/data-handling"


def test_homepage_uses_the_approved_english_security_copy() -> None:
    security = _get_landing_page_content("en")["security"]

    assert security["title"] == "Secure by design."
    assert (
        security["lead"]
        == "You do not have to trust us with your work. We do not receive it."
    )
    assert (
        security["description"]
        == "In local workflows, Vera and Clara run inside your existing Codex "
        "environment. Your prompts, files, and outputs do not pass through Mparanza."
    )
    assert security["cta_label"] == "See how your data is handled"


def test_homepage_places_security_after_open_by_design() -> None:
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    narrative_markers = (
        'class="landing-open-source"',
        'class="landing-security"',
        'class="landing-bridge"',
    )
    narrative_positions = [template.index(marker) for marker in narrative_markers]
    assert narrative_positions == sorted(narrative_positions)
    assert 'href="{{ security.cta_href }}?lang={{ lang }}"' in template


def test_data_handling_page_explains_local_execution_and_account_boundary() -> None:
    page = get_data_handling_content("en")
    sections = {section["id"]: section for section in page["sections"]}

    assert sections["local-execution"]["title"] == "The scripts run on your machine."
    assert (
        "provider-managed Jupyter notebook"
        in sections["local-execution"]["paragraphs"][2]
    )
    assert (
        "Mparanza is not the intermediary and cannot inspect prompts"
        in sections["security"]["paragraphs"][0]
    )
    assert sections["gdpr"]["title"] == "GDPR follows the actual data flow."


@pytest.mark.parametrize(
    ("lang", "expected_copy"),
    (
        (
            "en",
            "analyze, filter, and aggregate data locally, and limit what you send",
        ),
        (
            "it",
            "analizzare, filtrare e aggregare i dati localmente e di limitare ciò che",
        ),
        (
            "fr",
            "analyser, filtrer et agréger les données localement, et limiter ce qui",
        ),
        (
            "de",
            "Daten lokal analysieren, filtern und aggregieren und nur die",
        ),
    ),
)
def test_data_handling_page_localizes_data_minimization_copy(
    lang: str, expected_copy: str
) -> None:
    page = get_data_handling_content(lang)

    assert expected_copy in page["sections"][0]["paragraphs"][1]


def test_data_handling_template_has_one_heading_and_a_main_target() -> None:
    template = (ROOT / "templates" / "data_handling.html").read_text(encoding="utf-8")

    assert template.count("<h1") == 1
    assert 'href="#main-content"' in template
    assert 'id="main-content"' in template


def test_data_handling_reference_links_distinguish_internal_navigation() -> None:
    page = get_data_handling_content("en")
    template = (ROOT / "templates" / "data_handling.html").read_text(encoding="utf-8")

    source_link = page["resources"]["links"][0]
    policy_link = page["resources"]["links"][1]
    assert source_link["external"] is True
    assert policy_link == {
        "label": "Read the Zero Retention Policy",
        "href": "/zero-retention",
        "external": False,
    }
    assert '{{ "↗" if item.external else "→" }}' in template
    assert 'target="_blank"' not in template


def test_data_handling_content_returns_an_independent_english_fallback() -> None:
    fallback = get_data_handling_content("unsupported")
    fallback["title"] = "Changed"

    english = get_data_handling_content("en")

    assert english["title"] == "How your data is handled."
    assert fallback["title"] == "Changed"
