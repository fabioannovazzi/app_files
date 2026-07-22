from __future__ import annotations

from pathlib import Path

import pytest

from modules.pdp.api import _get_landing_page_content


@pytest.mark.parametrize(
    ("lang", "title"),
    [
        ("en", "Compliant by design."),
        ("it", "Conformi per scelta."),
        ("fr", "Conformes par conception."),
        ("de", "Für Compliance konzipiert."),
    ],
)
def test_homepage_content_includes_localized_compliance_section(
    lang: str, title: str
) -> None:
    content = _get_landing_page_content(lang)["compliance"]

    assert content["id"] == "compliance"
    assert content["title"] == title
    assert len(content["principles"]) == 3
    assert content["cta_href"] == "/data-handling"
    assert "Mparanza" not in content["closing"]


def test_homepage_content_states_the_llm_context_boundary_honestly() -> None:
    content = _get_landing_page_content("en")["compliance"]

    assert content["lead"] == (
        "Professional work may require Codex to read real client data."
    )
    assert "do not make data anonymous" in content["description"]
    assert content["principles"][0]["title"] == "Codex may read client data"
    assert "passwords" in content["principles"][1]["blurb"]
    assert "The firm chooses the Codex/OpenAI account" in (
        content["principles"][2]["blurb"]
    )
    assert "data controls available for that plan" in content["principles"][2]["blurb"]
    assert "other external services" in content["principles"][2]["blurb"]
    assert "public or external routes" not in content["principles"][2]["blurb"]
    assert content["closing"] == (
        "Local processing reduces copies. It is not anonymization or a compliance "
        "determination."
    )


@pytest.mark.parametrize(
    ("lang", "client_data", "automatic_removal", "session_secret"),
    (
        ("en", "real client data", "do not automatically remove", "session material"),
        (
            "it",
            "dati reali dei clienti",
            "non rimuovono automaticamente",
            "dati di sessione",
        ),
        (
            "fr",
            "vraies données clients",
            "ne suppriment pas automatiquement",
            "données de session",
        ),
        ("de", "echte Mandantendaten", "nicht automatisch", "Sitzungsdaten"),
    ),
)
def test_homepage_localizes_the_real_client_data_boundary(
    lang: str,
    client_data: str,
    automatic_removal: str,
    session_secret: str,
) -> None:
    content = _get_landing_page_content(lang)["compliance"]

    assert client_data in content["lead"]
    assert automatic_removal in content["description"]
    assert session_secret in content["principles"][1]["blurb"]


@pytest.mark.parametrize(
    ("lang", "security_lead", "external_routes"),
    (
        (
            "en",
            "In local Vera and Clara workflows, Mparanza does not receive your work.",
            "Local workflows, Mparanza-hosted features, and other external services",
        ),
        (
            "it",
            "Nei flussi locali di Vera e Clara, Mparanza non riceve il tuo lavoro.",
            "I flussi locali, le funzioni ospitate da Mparanza e gli altri servizi esterni",
        ),
        (
            "fr",
            "Dans les flux locaux de Vera et Clara, Mparanza ne reçoit pas votre travail.",
            "Les flux locaux, les fonctions hébergées par Mparanza et les autres services externes",
        ),
        (
            "de",
            "Bei lokalen Vera- und Clara-Abläufen erhält Mparanza Ihre Arbeit nicht.",
            "Lokale Abläufe, von Mparanza gehostete Funktionen und andere externe Dienste",
        ),
    ),
)
def test_homepage_scopes_the_mparanza_boundary_and_names_route_categories(
    lang: str, security_lead: str, external_routes: str
) -> None:
    content = _get_landing_page_content(lang)

    assert content["security"]["lead"] == security_lead
    assert external_routes in content["compliance"]["principles"][2]["blurb"]


def test_homepage_template_places_compliance_after_security_before_plugins() -> None:
    template = Path("templates/index.html").read_text(encoding="utf-8")

    assert template.index("{% if security %}") < template.index("{% if compliance %}")
    assert template.index("{% if compliance %}") < template.index("{% if bridge %}")
    assert 'class="landing-compliance__principles"' in template
