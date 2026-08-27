from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import (  # type: ignore  # pylint: disable=wrong-import-position
    TestClient,
)
from starlette.responses import HTMLResponse

from modules.auth.config import get_auth_config
from modules.hosted_services import api as pdp_api
from modules.hosted_services.api import _get_landing_page_content, app
from modules.pdp.data_handling_content import get_data_handling_content

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _reset_auth_config(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dummy-client-id")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "s" * 32)
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


def _copy_shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _copy_shape(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_copy_shape(child) for child in value]
    return type(value)


@pytest.mark.parametrize(
    ("lang", "page_title", "video_title", "boundary_title", "closing"),
    (
        (
            "en",
            "How your data is handled.",
            "How Vera and Clara handle data.",
            "Your selected AI workspace is the main boundary.",
            "One global boundary. Process details stay with the process.",
        ),
        (
            "it",
            "Come vengono gestiti i dati.",
            "Come Vera e Clara gestiscono i dati.",
            "Operazioni locali e trattamento del modello.",
            (
                "Ogni processo spiega quali dati restano locali e quali arrivano al "
                "modello."
            ),
        ),
        (
            "fr",
            "Comment vos données sont traitées.",
            "Comment Vera et Clara traitent les données.",
            "L'environnement d'IA choisi est le périmètre principal.",
            "Un périmètre global. Les détails du processus restent avec le processus.",
        ),
        (
            "de",
            "So werden Ihre Daten verarbeitet.",
            "Wie Vera und Clara Daten verarbeiten.",
            "Die gewählte KI-Arbeitsumgebung ist die Hauptgrenze.",
            "Eine globale Grenze. Prozessdetails bleiben beim Prozess.",
        ),
        (
            "es",
            "Cómo se tratan tus datos.",
            "Cómo tratan los datos Vera y Clara.",
            "El entorno de IA elegido es el límite principal.",
            "Un límite global. Los detalles del proceso permanecen con el proceso.",
        ),
    ),
)
def test_data_handling_page_is_public_and_localized(
    monkeypatch: pytest.MonkeyPatch,
    lang: str,
    page_title: str,
    video_title: str,
    boundary_title: str,
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
    assert page["video"]["title"] == video_title
    assert page["boundary"]["title"] == boundary_title
    assert page["closing"] == closing
    assert "privacy_register" not in context


def test_data_handling_template_links_localized_accessible_youtube_video() -> None:
    template = (ROOT / "templates" / "data_handling.html").read_text(encoding="utf-8")

    assert 'id="data-handling-video"' in template
    assert "https://youtu.be/{{ page.video.youtube_id }}" in template
    assert (
        "https://i.ytimg.com/vi/{{ page.video.youtube_id }}/maxresdefault.jpg"
        in template
    )
    assert "<video" not in template
    assert "transcript" not in template.casefold()
    assert 'aria-describedby="data-handling-video-description"' in template

    expected_ids = {
        "en": "HhmQgTEnl78",
        "it": "q3nS9YBaEP8",
        "fr": "gIpiAURzyjA",
        "de": "g5XV1cZoTaI",
        "es": "LAimCM-F994",
    }
    for language, youtube_id in expected_ids.items():
        assert get_data_handling_content(language)["video"]["youtube_id"] == youtube_id


def test_italian_data_handling_copy_states_the_shared_boundaries_directly() -> None:
    page = get_data_handling_content("it")
    sections = {section["id"]: section for section in page["sections"]}

    assert page["boundary"]["intro"] == (
        "Il plugin esegue localmente e in modo deterministico ordinamenti, calcoli, "
        "riconciliazioni, filtri e aggregazioni. Il modello riceve i dati necessari "
        "al singolo processo."
    )
    assert page["boundary"]["exclusion"] == (
        "Ogni processo dichiara che cosa viene elaborato localmente, che cosa arriva "
        "al modello e che cosa resta escluso."
    )
    assert sections["local-execution"]["paragraphs"][1] == (
        "Per questo i nostri plugin, in generale, non anonimizzano i dati; lo fanno "
        "solo quando ciò non incide sul processo."
    )
    assert sections["workflow-boundaries"]["paragraphs"][1] == (
        "Se si caricano dati personali, è necessario avere un DPA con il provider "
        "del modello."
    )
    assert sections["run-evidence"]["title"] == (
        "Vera registra il confine dei dati di ogni esecuzione sostanziale."
    )
    assert "ricevuta JSON e una versione Markdown" in (
        sections["run-evidence"]["paragraphs"][0]
    )
    assert "non prova la consegna lato provider" in (
        sections["run-evidence"]["paragraphs"][1]
    )
    assert sections["hosted-features"]["paragraphs"][0] == (
        "Il normale funzionamento dei plugin non invia né conserva sul server di "
        "Mparanza LLC i dati del cliente o del lavoro. Per il normale funzionamento "
        "dei plugin non è quindi necessario un DPA con Mparanza LLC."
    )


def test_spanish_public_content_has_recursive_key_parity_with_english() -> None:
    english_landing = _get_landing_page_content("en")
    spanish_landing = _get_landing_page_content("es")
    english_data_handling = get_data_handling_content("en")
    spanish_data_handling = get_data_handling_content("es")

    assert _copy_shape(spanish_landing) == _copy_shape(english_landing)
    assert _copy_shape(spanish_data_handling) == _copy_shape(english_data_handling)


@pytest.mark.parametrize(
    ("lang", "open_title", "free_title", "security_title", "bridge_title"),
    (
        (
            "en",
            "Open by design.",
            "Free by design.",
            "Secure by design.",
            "Plugins by design.",
        ),
        (
            "it",
            "Aperti per scelta.",
            "Gratuiti per scelta.",
            "Sicuri per scelta.",
            "Plugin per scelta.",
        ),
        (
            "fr",
            "Ouverts par conception.",
            "Gratuits par conception.",
            "Sécurisés par conception.",
            "Plugins par conception.",
        ),
        (
            "de",
            "Offen konzipiert.",
            "Kostenlos konzipiert.",
            "Sicher konzipiert.",
            "Als Plugins konzipiert.",
        ),
        (
            "es",
            "Abiertos por diseño.",
            "Gratuitos por diseño.",
            "Seguros por diseño.",
            "Plugins por diseño.",
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


@pytest.mark.parametrize("lang", ("en", "it", "fr", "de", "es"))
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


def test_homepage_passes_complete_spanish_locale_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_template_response(monkeypatch)
    client = TestClient(app)

    response = client.get("/?lang=es")

    assert response.status_code == 200
    context = captured["context"]
    assert isinstance(context, dict)
    assert context["language_order"] == ["en", "it", "fr", "de", "es"]
    assert context["language_names"]["es"] == "Español"
    assert context["language_labels"]["es"] == "Es"
    assert set(context["language_tooltips"]) == {
        "clara_plugin",
        "codex_accountants_group",
        "codex_consultants_group",
        "codex_lawyers_group",
        "lucia_plugin",
        "vera",
    }
    assert context["language_tooltips"]["clara_plugin"] == (
        "Organiza materiales del caso, notas y valoraciones revisadas en entregables "
        "que pueden compartirse con el cliente."
    )


@pytest.mark.parametrize("lang", ("en", "it", "fr", "de", "es"))
def test_homepage_download_tooltips_are_workspace_neutral(lang: str) -> None:
    tooltips = pdp_api.TOOLTIP_CONTENT[lang]

    assert "Codex" not in repr(tooltips)


@pytest.mark.parametrize(
    ("lang", "subheadline"),
    (
        (
            "en",
            "Mparanza builds specialist methods into plugins for professional work. "
            "For ChatGPT Work, Codex, and Claude Cowork.",
        ),
        (
            "it",
            "Mparanza incorpora metodi specialistici in plugin per il lavoro "
            "professionale. Per ChatGPT Work, Codex e Claude Cowork.",
        ),
        (
            "fr",
            "Mparanza intègre des méthodes spécialisées dans des plugins pour le "
            "travail professionnel. Pour ChatGPT Work, Codex et Claude Cowork.",
        ),
        (
            "de",
            "Mparanza verankert fachliche Methoden in Plugins für professionelle "
            "Arbeit. Für ChatGPT Work, Codex und Claude Cowork.",
        ),
        (
            "es",
            "Mparanza incorpora métodos especializados en plugins para el trabajo "
            "profesional. Para ChatGPT Work, Codex y Claude Cowork.",
        ),
    ),
)
def test_homepage_describes_mparanza_as_specialist_plugins(
    lang: str, subheadline: str
) -> None:
    content = _get_landing_page_content(lang)

    assert content["hero"]["subheadline"] == subheadline


def test_homepage_uses_the_approved_english_security_copy() -> None:
    security = _get_landing_page_content("en")["security"]

    assert security["title"] == "Secure by design."
    assert (
        security["lead"]
        == "In ordinary Clara, Vera and Lucia workflows, Mparanza does not receive your client work."
    )
    assert (
        security["description"]
        == "Ordinary plugin workflows run inside the AI workspace you choose. "
        "Your client prompts, files, and outputs do not pass through Mparanza."
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


def test_data_handling_page_explains_only_stable_global_boundaries() -> None:
    page = get_data_handling_content("en")
    sections = {section["id"]: section for section in page["sections"]}

    assert "OpenAI ChatGPT or Codex" in page["boundary"]["intro"]
    assert "Anthropic Claude or Cowork" in page["boundary"]["intro"]
    assert "Mparanza is not a separate recipient" in page["boundary"]["intro"]
    assert set(sections) == {
        "local-execution",
        "workflow-boundaries",
        "run-evidence",
        "connected-sources",
        "hosted-features",
    }
    assert "do not automatically anonymise or pseudonymise" in (
        sections["local-execution"]["paragraphs"][1]
    )
    assert "does not duplicate" in sections["workflow-boundaries"]["paragraphs"][0]
    assert "each model-visible phase" in sections["run-evidence"]["paragraphs"][0]
    assert "A complete relevant document or population can be the correct minimum" in (
        sections["run-evidence"]["paragraphs"][1]
    )
    assert "does not prove provider-side delivery" in (
        sections["run-evidence"]["paragraphs"][1]
    )
    assert "destination's terms and controls apply separately" in (
        sections["connected-sources"]["paragraphs"][0]
    )
    assert "reaches Mparanza-controlled systems" in (
        sections["hosted-features"]["paragraphs"][0]
    )


@pytest.mark.parametrize("language", ("en", "it", "fr", "de", "es"))
def test_data_handling_localizes_vera_run_evidence(language: str) -> None:
    page = get_data_handling_content(language)
    sections = {section["id"]: section for section in page["sections"]}
    run_evidence = sections["run-evidence"]

    assert "Vera" in run_evidence["title"]
    assert len(run_evidence["paragraphs"]) == 2
    assert "JSON" in run_evidence["paragraphs"][0]
    assert "Markdown" in run_evidence["paragraphs"][0]


def test_data_handling_template_does_not_render_a_function_register() -> None:
    template = (ROOT / "templates" / "data_handling.html").read_text(encoding="utf-8")

    assert "function-register" not in template
    assert "privacy_register" not in template
    assert "privacy-register.js" not in template
    assert "data-privacy-register" not in template


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
