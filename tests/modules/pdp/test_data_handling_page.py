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
from modules.pdp import api as pdp_api
from modules.pdp.api import _get_landing_page_content, app
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
            "When Vera and Clara work inside Codex.",
            "One policy for Vera and Clara. No prompt-by-prompt paperwork.",
        ),
        (
            "it",
            "Come vengono gestiti i tuoi dati.",
            "Come Vera e Clara gestiscono i dati.",
            "Quando Vera e Clara lavorano dentro Codex.",
            "Una regola per Vera e Clara. Nessuna burocrazia prompt per prompt.",
        ),
        (
            "fr",
            "Comment vos données sont traitées.",
            "Comment Vera et Clara traitent les données.",
            "Quand Vera et Clara travaillent dans Codex.",
            "Une règle pour Vera et Clara. Aucune paperasse prompt par prompt.",
        ),
        (
            "de",
            "So werden Ihre Daten verarbeitet.",
            "Wie Vera und Clara Daten verarbeiten.",
            "Wenn Vera und Clara in Codex arbeiten.",
            "Eine Regel für Vera und Clara. Kein Papierkram für jeden Prompt.",
        ),
        (
            "es",
            "Cómo se tratan tus datos.",
            "Cómo tratan los datos Vera y Clara.",
            "Cuando Vera y Clara trabajan dentro de Codex.",
            "Una política para Vera y Clara. Sin documentación para cada prompt.",
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
        (
            "es",
            "Abiertos por diseño.",
            "Gratuitos por diseño.",
            "Seguros por diseño.",
            "Codex por diseño.",
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
    assert set(context["language_tooltips"]) == set(pdp_api.TOOLTIP_CONTENT["en"])
    assert context["language_tooltips"]["slides_editor"] == (
        "Crea y edita diapositivas ejecutivas directamente en el navegador."
    )


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
        (
            "es",
            "Mparanza crea plugins de Codex. Cada uno proporciona a Codex una "
            "forma de trabajo especializada para tareas profesionales.",
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
        == "In ordinary Vera and Clara workflows, Mparanza does not receive your client work."
    )
    assert (
        security["description"]
        == "Ordinary plugin workflows run inside your existing Codex environment. "
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


def test_data_handling_page_explains_the_two_processing_categories() -> None:
    page = get_data_handling_content("en")
    sections = {section["id"]: section for section in page["sections"]}

    assert page["boundary"]["title"] == "When Vera and Clara work inside Codex."
    assert "do not automatically anonymise data" in page["boundary"]["intro"]
    assert "local Python to filter or aggregate" in page["boundary"]["intro"]
    assert "user's existing ChatGPT plan" in page["boundary"]["intro"]
    assert (
        "do not send client files, prompts, or model-context content"
        in page["boundary"]["intro"]
    )
    assert sections["local-execution"]["title"] == (
        "Local processing is used when it helps the work."
    )
    assert "names, documents, original language, or case facts" in (
        sections["local-execution"]["paragraphs"][1]
    )
    assert sections["security"]["title"] == (
        "Mapped once per workflow, not once per prompt."
    )
    assert "does not create a form, consent step, or record for each prompt" in (
        sections["security"]["paragraphs"][0]
    )
    assert "session material" in sections["security"]["paragraphs"][1]
    assert sections["hosted-features"]["title"] == (
        "Mparanza-hosted services are a separate boundary."
    )
    assert "content needed for that service reaches Mparanza-controlled systems" in (
        sections["hosted-features"]["paragraphs"][0]
    )
    assert "documented once at service level" in (
        sections["hosted-features"]["paragraphs"][1]
    )
    assert "not a third Mparanza processing category" in (
        sections["hosted-features"]["paragraphs"][2]
    )
    assert "check for updates" in sections["hosted-features"]["paragraphs"][3]
    assert "no client or work content" in sections["hosted-features"]["paragraphs"][3]
    assert (
        "explicit submission workflow" in sections["hosted-features"]["paragraphs"][3]
    )
    assert sections["gdpr"]["title"] == "One policy for Vera and Clara."
    assert "first category when they run inside Codex" in (
        sections["gdpr"]["paragraphs"][0]
    )
    assert "falls in the second category" in sections["gdpr"]["paragraphs"][1]


@pytest.mark.parametrize(
    (
        "lang",
        "directory_phrase",
        "desktop_stop_phrase",
        "gmail_phrase",
        "whatsapp_phrase",
        "mparanza_phrase",
        "codex_phrase",
    ),
    (
        (
            "en",
            "public Plugins Directory",
            "workflows stop on ChatGPT web and mobile and require Codex Desktop",
            "Inside Codex Desktop, Vera searches Gmail through OpenAI's separately "
            "installed and connected Gmail connector",
            "Codex Desktop with Computer Use",
            "No Mparanza server receives or stores a copy",
            "may still enter the model context",
        ),
        (
            "it",
            "directory pubblica dei plugin",
            "I workflow si fermano su ChatGPT web o mobile e richiedono Codex Desktop",
            "Dentro Codex Desktop, Vera cerca in Gmail attraverso il connector Gmail "
            "di OpenAI",
            "Codex Desktop con Computer Use",
            "Nessun server Mparanza riceve o conserva una copia",
            "possono comunque entrare nel contesto del modello",
        ),
        (
            "fr",
            "répertoire public des plugins",
            "Les workflows s'arrêtent sur ChatGPT web ou mobile et nécessitent Codex "
            "Desktop",
            "Dans Codex Desktop, Vera recherche dans Gmail au moyen du connecteur Gmail "
            "d'OpenAI",
            "Codex Desktop avec Computer Use",
            "Aucun serveur Mparanza ne reçoit ni ne conserve de copie",
            "peuvent toutefois entrer dans le contexte du modèle",
        ),
        (
            "de",
            "öffentlichen Plugin-Verzeichnis",
            "In ChatGPT im Web oder auf Mobilgeräten werden die Workflows gestoppt und "
            "erfordern Codex Desktop",
            "In Codex Desktop durchsucht Vera Gmail über den separat installierten und "
            "verbundenen Gmail-Connector von OpenAI",
            "Codex Desktop mit Computer Use",
            "Kein Mparanza-Server empfängt oder speichert eine Kopie",
            "können dennoch in den Modellkontext",
        ),
        (
            "es",
            "directorio público de plugins",
            "Los flujos se detienen en ChatGPT web o móvil y requieren Codex Desktop",
            "Dentro de Codex Desktop, Vera busca en Gmail mediante el conector de Gmail "
            "de OpenAI",
            "Codex Desktop con Computer Use",
            "Ningún servidor de Mparanza recibe ni conserva una copia",
            "pueden entrar en el contexto del modelo",
        ),
    ),
)
def test_data_handling_page_distinguishes_gmail_and_whatsapp_desktop(
    lang: str,
    directory_phrase: str,
    desktop_stop_phrase: str,
    gmail_phrase: str,
    whatsapp_phrase: str,
    mparanza_phrase: str,
    codex_phrase: str,
) -> None:
    page = get_data_handling_content(lang)
    sections = {section["id"]: section for section in page["sections"]}
    connected = " ".join(sections["connected-sources"]["paragraphs"])

    assert directory_phrase in connected
    assert desktop_stop_phrase in connected
    assert gmail_phrase in connected
    assert whatsapp_phrase in connected
    assert mparanza_phrase in connected
    assert codex_phrase in connected
    assert "90 days" not in connected


@pytest.mark.parametrize(
    (
        "lang",
        "automatic_anonymisation",
        "local_python",
        "chatgpt_plan",
        "hosted_boundary",
        "no_prompt_documentation",
    ),
    (
        (
            "en",
            "do not automatically anonymise data",
            "Local Python can sort, calculate, reconcile, filter, aggregate",
            "user's existing ChatGPT plan",
            "Mparanza-hosted services are a separate boundary.",
            "There is no prompt-by-prompt documentation.",
        ),
        (
            "it",
            "non anonimizzano automaticamente i dati",
            "Python in locale può ordinare, calcolare, riconciliare, filtrare, aggregare",
            "piano ChatGPT già utilizzato dall'utente",
            "I servizi hosted di Mparanza hanno un confine separato.",
            "Non esiste documentazione prompt per prompt.",
        ),
        (
            "fr",
            "n'anonymisent pas automatiquement les données",
            "Python peut localement trier, calculer, rapprocher, filtrer, agréger",
            "offre ChatGPT existante de l'utilisateur",
            "Les services hébergés par Mparanza ont un périmètre distinct.",
            "Il n'existe aucune documentation prompt par prompt.",
        ),
        (
            "de",
            "anonymisieren Daten nicht automatisch",
            "Lokales Python kann sortieren, berechnen, abstimmen, filtern, aggregieren",
            "bestehenden ChatGPT-Tarifs des Nutzers",
            "Mparanza-gehostete Dienste haben eine separate Grenze.",
            "Es gibt keine Dokumentation für jeden einzelnen Prompt.",
        ),
        (
            "es",
            "no anonimizan los datos automáticamente",
            "Python en local puede ordenar, calcular, conciliar, filtrar, agregar",
            "plan de ChatGPT que ya usa el usuario",
            "Los servicios alojados por Mparanza tienen un límite separado.",
            "No hay documentación para cada prompt.",
        ),
    ),
)
def test_data_handling_page_localizes_the_two_category_policy(
    lang: str,
    automatic_anonymisation: str,
    local_python: str,
    chatgpt_plan: str,
    hosted_boundary: str,
    no_prompt_documentation: str,
) -> None:
    page = get_data_handling_content(lang)
    sections = {section["id"]: section for section in page["sections"]}

    assert automatic_anonymisation in page["boundary"]["intro"]
    assert local_python in sections["local-execution"]["paragraphs"][0]
    assert chatgpt_plan in page["boundary"]["intro"]
    assert sections["hosted-features"]["title"] == hosted_boundary
    assert no_prompt_documentation in sections["hosted-features"]["paragraphs"][1]


@pytest.mark.parametrize(
    ("lang", "model_input", "workflow_mapping", "external_destination"),
    (
        (
            "en",
            "names, documents, original language, or case facts",
            "what normally stays local and what Codex may read",
            "external destination, not a third Mparanza processing category",
        ),
        (
            "it",
            "nomi, documenti, testo originale o fatti del caso",
            "che cosa resta normalmente locale e che cosa può leggere Codex",
            "destinazione esterna, non una terza categoria di trattamento Mparanza",
        ),
        (
            "fr",
            "noms, des documents, le texte original ou des faits propres au dossier",
            "ce qui reste normalement local et ce que Codex peut lire",
            "destination externe, pas une troisième catégorie de traitement Mparanza",
        ),
        (
            "de",
            "Namen, Dokumente, Originalformulierungen oder Fallfakten",
            "was normalerweise lokal bleibt und was Codex lesen kann",
            "externes Ziel, keine dritte Mparanza-Verarbeitungskategorie",
        ),
        (
            "es",
            "nombres, documentos, el idioma original o hechos del caso",
            "qué permanece normalmente en local y qué puede leer Codex",
            "destino externo, no de una tercera categoría de tratamiento de Mparanza",
        ),
    ),
)
def test_data_handling_page_names_model_data_and_workflow_level_mapping(
    lang: str,
    model_input: str,
    workflow_mapping: str,
    external_destination: str,
) -> None:
    page = get_data_handling_content(lang)
    sections = {section["id"]: section for section in page["sections"]}

    assert model_input in sections["local-execution"]["paragraphs"][1]
    assert workflow_mapping in sections["security"]["paragraphs"][0]
    assert external_destination in sections["hosted-features"]["paragraphs"][2]


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
