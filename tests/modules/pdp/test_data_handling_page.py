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
    ("lang", "page_title", "closing"),
    (
        (
            "en",
            "How your data is handled.",
            "Local processing changes the route, not the nature, of the data.",
        ),
        (
            "it",
            "Come vengono gestiti i tuoi dati.",
            "L'elaborazione locale cambia il percorso, non la natura dei dati.",
        ),
        (
            "fr",
            "Comment vos données sont traitées.",
            "Le traitement local change le parcours, pas la nature des données.",
        ),
        (
            "de",
            "So werden Ihre Daten verarbeitet.",
            "Lokale Verarbeitung ändert den Weg, nicht die Art der Daten.",
        ),
    ),
)
def test_data_handling_page_is_public_and_localized(
    monkeypatch: pytest.MonkeyPatch,
    lang: str,
    page_title: str,
    closing: str,
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
    assert page["closing"] == closing


@pytest.mark.parametrize(
    ("lang", "open_title", "free_title", "security_title", "bridge_title"),
    (
        (
            "en",
            "Open by design.",
            "Free by design.",
            "Secure by design.",
            "Codex by design.",
        ),
        (
            "it",
            "Aperti per scelta.",
            "Gratuiti per scelta.",
            "Sicuri per scelta.",
            "Codex per scelta.",
        ),
        (
            "fr",
            "Ouverts par conception.",
            "Gratuits par conception.",
            "Sécurisés par conception.",
            "Codex par conception.",
        ),
        (
            "de",
            "Offen konzipiert.",
            "Kostenlos konzipiert.",
            "Sicher konzipiert.",
            "Für Codex konzipiert.",
        ),
    ),
)
def test_homepage_design_copy_is_localized(
    lang: str,
    open_title: str,
    free_title: str,
    security_title: str,
    bridge_title: str,
) -> None:
    content = _get_landing_page_content(lang)
    security = content["security"]

    assert content["open_source"]["title"] == open_title
    assert content["free"]["title"] == free_title
    assert security["title"] == security_title
    assert security["cta_href"] == "/data-handling"
    assert content["bridge"]["title"] == bridge_title


@pytest.mark.parametrize("lang", ("en", "it", "fr", "de"))
def test_homepage_passes_free_section_to_template(
    monkeypatch: pytest.MonkeyPatch, lang: str
) -> None:
    captured = _capture_template_response(monkeypatch)
    client = TestClient(app)

    response = client.get(f"/?lang={lang}")

    assert response.status_code == 200
    assert captured["name"] == "index.html"
    context = captured["context"]
    assert isinstance(context, dict)
    assert context["free"] == _get_landing_page_content(lang)["free"]


@pytest.mark.parametrize(
    ("lang", "subheadline"),
    (
        (
            "en",
            "Mparanza builds Codex plugins. Each gives Codex a specialist way of "
            "working for professional tasks.",
        ),
        (
            "it",
            "Mparanza crea plugin Codex. Ogni plugin dà a Codex un metodo "
            "specialistico per il lavoro professionale.",
        ),
        (
            "fr",
            "Mparanza crée des plugins Codex. Chacun donne à Codex une méthode "
            "spécialisée pour le travail professionnel.",
        ),
        (
            "de",
            "Mparanza entwickelt Codex-Plugins. Jedes gibt Codex eine fachliche "
            "Arbeitsweise für professionelle Aufgaben.",
        ),
    ),
)
def test_homepage_describes_mparanza_as_codex_plugins(
    lang: str, subheadline: str
) -> None:
    content = _get_landing_page_content(lang)

    assert content["hero"]["subheadline"] == subheadline


def test_homepage_uses_the_approved_english_security_copy() -> None:
    security = _get_landing_page_content("en")["security"]

    assert security["title"] == "Secure by design."
    assert (
        security["lead"]
        == "In local Vera and Clara workflows, Mparanza does not receive your work."
    )
    assert (
        security["description"]
        == "In local workflows, Vera and Clara run inside your existing Codex "
        "environment. Your prompts, files, and outputs do not pass through Mparanza."
    )
    assert security["cta_label"] == "See how your data is handled"


def test_homepage_places_free_and_security_after_open_by_design() -> None:
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    narrative_markers = (
        'class="landing-open-source"',
        'class="landing-free"',
        'class="landing-security"',
        'class="landing-bridge"',
    )
    narrative_positions = [template.index(marker) for marker in narrative_markers]
    assert narrative_positions == sorted(narrative_positions)
    assert 'href="{{ security.cta_href }}?lang={{ lang }}"' in template


def test_data_handling_page_explains_local_execution_and_account_boundary() -> None:
    page = get_data_handling_content("en")
    sections = {section["id"]: section for section in page["sections"]}

    assert sections["local-execution"]["title"] == (
        "Local processing is useful. It is not anonymization."
    )
    assert "does not mean its contents stay out" in (
        sections["local-execution"]["paragraphs"][1]
    )
    assert sections["security"]["title"] == "Codex may read real client data."
    assert "do not automatically anonymize case material" in (
        sections["security"]["paragraphs"][0]
    )
    assert "documents, passages, facts, or other content" in page["boundary"]["intro"]
    assert "enter the model context" in page["boundary"]["intro"]
    assert "session material" in sections["security"]["paragraphs"][1]
    assert sections["hosted-features"]["title"] == (
        "Local, hosted, and external are different routes."
    )
    assert "Public searches, portals, and external services" in (
        sections["hosted-features"]["paragraphs"][2]
    )
    assert sections["gdpr"]["title"] == "Compliance follows the actual data flow."
    assert "The firm chooses the Codex/OpenAI account" in (
        sections["gdpr"]["paragraphs"][1]
    )
    assert "separate routes" in sections["gdpr"]["paragraphs"][1]


@pytest.mark.parametrize(
    ("lang", "not_anonymization", "purpose_based"),
    (
        (
            "en",
            "It is not anonymization",
            "GDPR data minimisation is purpose-based",
        ),
        (
            "it",
            "Non è anonimizzazione",
            "minimizzazione prevista dal GDPR dipende dallo scopo",
        ),
        (
            "fr",
            "Ce n'est pas une anonymisation",
            "minimisation prévue par le RGPD dépend de la finalité",
        ),
        (
            "de",
            "Sie ist keine Anonymisierung",
            "Datenminimierung nach der DSGVO richtet sich nach dem Zweck",
        ),
    ),
)
def test_data_handling_page_localizes_the_local_processing_limit(
    lang: str, not_anonymization: str, purpose_based: str
) -> None:
    page = get_data_handling_content(lang)
    sections = {section["id"]: section for section in page["sections"]}

    assert not_anonymization in sections["local-execution"]["title"]
    assert purpose_based in sections["gdpr"]["paragraphs"][0]


@pytest.mark.parametrize(
    ("lang", "model_input", "automatic_limit"),
    (
        (
            "en",
            "documents, passages, facts, or other content it reads",
            "do not automatically anonymize case material",
        ),
        (
            "it",
            "i documenti, i passaggi, i fatti o gli altri contenuti che legge",
            "non anonimizzano automaticamente il materiale del caso",
        ),
        (
            "fr",
            "les documents, passages, faits ou autres contenus qu'il lit",
            "n'anonymisent pas automatiquement les dossiers",
        ),
        (
            "de",
            "Dokumente, Passagen, Fakten oder anderen Inhalte, die Codex liest",
            "anonymisieren Fallmaterial nicht automatisch",
        ),
    ),
)
def test_data_handling_page_names_what_codex_reads_without_claiming_detection(
    lang: str, model_input: str, automatic_limit: str
) -> None:
    page = get_data_handling_content(lang)
    sections = {section["id"]: section for section in page["sections"]}

    assert model_input in page["boundary"]["intro"]
    assert automatic_limit in sections["security"]["paragraphs"][0]


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
    external_hrefs = {
        link["href"] for link in page["resources"]["links"] if link["external"]
    }
    assert "https://eur-lex.europa.eu/eli/reg/2016/679/oj" in external_hrefs
    assert any("opinion-282024" in href for href in external_hrefs)
    assert '{{ "↗" if item.external else "→" }}' in template
    assert 'target="_blank"' not in template


def test_data_handling_content_returns_an_independent_english_fallback() -> None:
    fallback = get_data_handling_content("unsupported")
    fallback["title"] = "Changed"

    english = get_data_handling_content("en")

    assert english["title"] == "How your data is handled."
    assert fallback["title"] == "Changed"
