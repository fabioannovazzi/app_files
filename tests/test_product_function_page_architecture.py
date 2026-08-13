from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "static" / "shared"
PRODUCT_PAGES = {
    "vera": SHARED / "vera" / "index.html",
    "lucia": SHARED / "lucia" / "index.html",
    "clara": SHARED / "clara" / "index.html",
}


def _directory_links(page: str) -> list[str]:
    return re.findall(
        r'<a class="(?:module-row|function-link)"[^>]+href="([^"]+)"',
        page,
    )


def _resolved_page(source: Path, href: str) -> Path:
    path = urlsplit(href).path
    return (source.parent / path).resolve()


def test_product_pages_are_directories_without_generic_method_or_data_sections() -> None:
    forbidden_ids = ('id="assurance"', 'id="data-boundary"', 'id="data-handling"')
    forbidden_slogans = (
        "Metodo di assurance",
        "Prima il quesito. Poi la risposta.",
        "Prima il significato. Poi il calcolo.",
        "Un solo filo, sei passaggi controllabili.",
        "Tre passaggi, dal materiale alla pubblicazione.",
        "Vera lavora sui dati reali del cliente.",
    )

    for page_path in PRODUCT_PAGES.values():
        page = page_path.read_text(encoding="utf-8")
        for section_id in forbidden_ids:
            assert section_id not in page, page_path
        for slogan in forbidden_slogans:
            assert slogan not in page, page_path

        links = _directory_links(page)
        assert links, page_path
        for module in re.findall(
            r'<a class="(?:module-row|function-link)".*?</a>',
            page,
            flags=re.DOTALL,
        ):
            assert "<p" not in module, page_path


def test_every_directory_link_resolves_to_a_separate_explanation_page() -> None:
    for page_path in PRODUCT_PAGES.values():
        page = page_path.read_text(encoding="utf-8")
        for href in _directory_links(page):
            destination = _resolved_page(page_path, href)
            assert destination.is_file(), f"{page_path}: missing {href}"
            explanation = destination.read_text(encoding="utf-8")
            assert (
                "function-model-data.js" in explanation
                or "product-function-page.js" in explanation
                or "data-model-data-status" in explanation
            ), f"{destination}: missing final model-data section"


def test_lucia_and_vera_share_the_research_function_pages() -> None:
    vera = PRODUCT_PAGES["vera"].read_text(encoding="utf-8")
    lucia = PRODUCT_PAGES["lucia"].read_text(encoding="utf-8")

    for href in (
        "../prompt-optimizer/index.html",
        "../deep-research-validator/index.html",
    ):
        assert f'href="{href}"' in vera
        assert f'href="{href}?lang=it"' in lucia


def test_vera_names_the_italian_section_without_for_italy_copy() -> None:
    vera = PRODUCT_PAGES["vera"].read_text(encoding="utf-8")

    for text in (
        'data-i18n="jurisdiction.index">Italia</span>',
        'data-i18n="jurisdiction.title">Formati, enti e procedure italiane</h2>',
        "La sezione raccoglie le funzioni che dipendono da formati, enti o norme italiane.",
    ):
        assert text in vera
    assert "Funzioni disponibili per l’Italia" not in vera


def test_vera_country_navigation_uses_direct_place_names() -> None:
    vera = PRODUCT_PAGES["vera"].read_text(encoding="utf-8")

    for label in ("Italia", "United Kingdom", "Genève", "Zürich", "Mercado"):
        assert f'"nav.jurisdiction": "{label}"' in vera
    for obsolete in ("Per l’Italia", "For the UK", "Pour Genève", "Für Zürich"):
        assert obsolete not in vera


def test_function_pages_use_specific_data_copy_for_three_functions_and_placeholders_elsewhere() -> None:
    function_copy = (SHARED / "product-function-pages.js").read_text(encoding="utf-8")
    placeholder_script = (SHARED / "function-model-data.js").read_text(encoding="utf-8")
    bank_page = (SHARED / "journal-bank-reconciliation" / "index.html").read_text(
        encoding="utf-8"
    )

    assert function_copy.count('modelDataStatus: "relevant"') == 10
    assert '"comunicazione-professionale"' in function_copy
    assert '"presenza-digitale-studio"' in function_copy
    assert 'data-model-data-status="relevant"' in bank_page
    assert "Quali dati arrivano al modello" in bank_page

    for placeholder in (
        "Informazioni specifiche per questa funzione in preparazione.",
        "Function-specific information is being prepared.",
        "Les informations spécifiques à cette fonction sont en préparation.",
        "Funktionsspezifische Informationen werden derzeit vorbereitet.",
        "Se está preparando la información específica de esta función.",
    ):
        assert placeholder in placeholder_script
        assert placeholder in function_copy
