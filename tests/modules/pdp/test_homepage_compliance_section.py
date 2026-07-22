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
        ("es", "Cumplimiento por diseño."),
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
    assert "do not automatically anonymise data" in content["description"]
    assert "local Python to filter or aggregate" in content["description"]
    assert "user's existing ChatGPT plan" in content["description"]
    assert content["principles"][0]["title"] == "Use local Python when useful"
    assert "not automatic anonymisation" in content["principles"][0]["blurb"]
    assert content["principles"][1]["title"] == "Real data may reach the model"
    assert "Names, documents, original language, and case facts" in (
        content["principles"][1]["blurb"]
    )
    assert content["principles"][2]["title"] == "Two processing categories"
    assert "Ordinary plugin functions use the existing ChatGPT plan" in (
        content["principles"][2]["blurb"]
    )
    assert "Mparanza-hosted services form a separate processing boundary" in (
        content["principles"][2]["blurb"]
    )
    assert content["closing"] == (
        "One policy for Vera and Clara. No prompt-by-prompt paperwork."
    )


@pytest.mark.parametrize(
    (
        "lang",
        "client_data",
        "automatic_anonymisation",
        "local_python",
        "chatgpt_plan",
        "model_data",
        "no_prompt_paperwork",
    ),
    (
        (
            "en",
            "real client data",
            "do not automatically anonymise data",
            "local Python to filter or aggregate",
            "existing ChatGPT plan",
            "Names, documents, original language, and case facts",
            "No prompt-by-prompt paperwork",
        ),
        (
            "it",
            "dati reali dei clienti",
            "non anonimizzano automaticamente i dati",
            "Python in locale per filtrare o aggregare",
            "piano ChatGPT già utilizzato",
            "Nomi, documenti, testo originale e fatti del caso",
            "Nessuna burocrazia prompt per prompt",
        ),
        (
            "fr",
            "vraies données clients",
            "n'anonymisent pas automatiquement les données",
            "Python localement pour filtrer ou agréger",
            "offre ChatGPT existante",
            "Noms, documents, texte original et faits propres au dossier",
            "Aucune paperasse prompt par prompt",
        ),
        (
            "de",
            "echte Mandantendaten",
            "anonymisieren Daten nicht automatisch",
            "Python lokal einsetzen, um Informationen zu filtern oder zu aggregieren",
            "bestehenden ChatGPT-Tarifs",
            "Namen, Dokumente, Originalformulierungen und Fallfakten",
            "Kein Papierkram für jeden Prompt",
        ),
        (
            "es",
            "datos reales de clientes",
            "no anonimizan los datos automáticamente",
            "Python en local para filtrar o agregar",
            "plan de ChatGPT que ya usa",
            "Los nombres, documentos, el idioma original y los hechos del caso",
            "Sin documentación para cada prompt",
        ),
    ),
)
def test_homepage_localizes_the_two_category_data_boundary(
    lang: str,
    client_data: str,
    automatic_anonymisation: str,
    local_python: str,
    chatgpt_plan: str,
    model_data: str,
    no_prompt_paperwork: str,
) -> None:
    content = _get_landing_page_content(lang)["compliance"]

    assert client_data in content["lead"]
    assert automatic_anonymisation in content["description"]
    assert local_python in content["description"]
    assert chatgpt_plan in content["description"]
    assert model_data in content["principles"][1]["blurb"]
    assert no_prompt_paperwork in content["closing"]


@pytest.mark.parametrize(
    ("lang", "security_lead", "ordinary_functions", "hosted_boundary"),
    (
        (
            "en",
            "In ordinary Vera and Clara workflows, Mparanza does not receive your client work.",
            "Ordinary plugin functions use the existing ChatGPT plan.",
            "Mparanza-hosted services form a separate processing boundary.",
        ),
        (
            "it",
            "Nei flussi ordinari di Vera e Clara, Mparanza non riceve il lavoro dei tuoi clienti.",
            "Le normali funzioni dei plugin usano il piano ChatGPT esistente.",
            "I servizi hosted di Mparanza hanno un confine di trattamento separato.",
        ),
        (
            "fr",
            "Dans les flux ordinaires de Vera et Clara, Mparanza ne reçoit pas le travail de vos clients.",
            "Les fonctions ordinaires des plugins utilisent l'offre ChatGPT existante.",
            "Les services hébergés par Mparanza ont un périmètre de traitement distinct.",
        ),
        (
            "de",
            "Bei normalen Vera- und Clara-Abläufen erhält Mparanza Ihre Mandantenarbeit nicht.",
            "Normale Plugin-Funktionen nutzen den bestehenden ChatGPT-Tarif.",
            "Mparanza-gehostete Dienste haben eine separate Verarbeitungsgrenze.",
        ),
        (
            "es",
            "En los flujos ordinarios de Vera y Clara, Mparanza no recibe el trabajo de tus clientes.",
            "Las funciones ordinarias de los plugins usan el plan de ChatGPT existente.",
            "Los servicios alojados por Mparanza constituyen un límite de tratamiento separado.",
        ),
    ),
)
def test_homepage_scopes_the_mparanza_boundary_and_names_two_categories(
    lang: str,
    security_lead: str,
    ordinary_functions: str,
    hosted_boundary: str,
) -> None:
    content = _get_landing_page_content(lang)

    assert content["security"]["lead"] == security_lead
    boundary_copy = content["compliance"]["principles"][2]["blurb"]
    assert ordinary_functions in boundary_copy
    assert hosted_boundary in boundary_copy


def test_homepage_template_places_compliance_after_security_before_plugins() -> None:
    template = Path("templates/index.html").read_text(encoding="utf-8")

    assert template.index("{% if security %}") < template.index("{% if compliance %}")
    assert template.index("{% if compliance %}") < template.index("{% if bridge %}")
    assert 'class="landing-compliance__principles"' in template
