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
            if 'class="module-row"' in module:
                assert "<h4" in module, page_path
                assert "<h3" not in module, page_path


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


def test_vera_names_the_country_section_as_area_four() -> None:
    vera = PRODUCT_PAGES["vera"].read_text(encoding="utf-8")

    for text in (
        'data-i18n="jurisdiction.index">Area 4</span>',
        'data-i18n="jurisdiction.title">Formati, enti e procedure italiane</h2>',
        "La sezione raccoglie le funzioni che dipendono da formati, enti o norme italiane.",
        '"jurisdiction.index": "Area 4"',
        '"jurisdiction.index": "Domaine 4"',
        '"jurisdiction.index": "Bereich 4"',
        '"jurisdiction.index": "Área 4"',
    ):
        assert text in vera
    assert "Funzioni disponibili per l’Italia" not in vera


def test_vera_navigation_links_to_the_four_work_areas() -> None:
    vera = PRODUCT_PAGES["vera"].read_text(encoding="utf-8")
    navigation_css = (SHARED / "product-navigation.css").read_text(encoding="utf-8")

    for href, key in (
        ("#area-clients", "nav.clients"),
        ("#area-accounting", "nav.accounting"),
        ("#area-outputs", "nav.outputs"),
        ("#jurisdiction", "nav.jurisdiction"),
    ):
        assert f'href="{href}"' in vera
        assert f'data-i18n="{key}"' in vera

    for label in (
        "Clienti e fascicoli",
        "Controlli e analisi",
        "Report, comunicazione e ricerca",
        "Formati e procedure italiane",
        "Clients and files",
        "UK formats and procedures",
        "Formats et procédures genevoises",
        "Zürcher Formate und Verfahren",
    ):
        assert label in vera

    assert 'data-i18n="nav.capabilities">Cosa fa</a>' not in vera
    assert ".workstream { display: grid; gap: 28px; scroll-margin-top: 88px; }" in vera
    assert "@media (max-width: 1080px)" in navigation_css


def test_lucia_and_clara_navigation_links_to_their_work_areas() -> None:
    lucia = PRODUCT_PAGES["lucia"].read_text(encoding="utf-8")
    clara = PRODUCT_PAGES["clara"].read_text(encoding="utf-8")
    lucia_css = (SHARED / "lucia" / "lucia-page.css").read_text(encoding="utf-8")
    clara_css = (SHARED / "clara" / "clara-page.css").read_text(encoding="utf-8")

    for href, key in (
        ("#area-research", "stream.research.title"),
        ("#area-matters", "stream.matter.title"),
        ("#area-studio", "stream.studio.title"),
    ):
        assert f'href="{href}"' in lucia
        assert f'data-i18n="{key}"' in lucia

    for href, key in (
        ("#area-deliverables", "functions.deliverables"),
        ("#area-recordings", "functions.research"),
        ("#area-retail", "functions.retail"),
        ("#area-analysis", "functions.analysis"),
    ):
        assert f'href="{href}"' in clara
        assert f'data-i18n="{key}"' in clara

    assert 'data-i18n="nav.capabilities">Cosa fa</a>' not in lucia
    assert 'data-i18n="nav.capabilities">Functions</a>' not in clara
    assert 'data-i18n="nav.workflow">How it works</a>' not in clara
    assert "scroll-margin-top: 88px" in lucia_css
    assert "scroll-margin-top: 88px" in clara_css


def test_all_product_directories_distinguish_area_headings_from_function_links() -> None:
    vera = PRODUCT_PAGES["vera"].read_text(encoding="utf-8")
    lucia_css = (SHARED / "lucia" / "lucia-page.css").read_text(encoding="utf-8")
    clara_css = (SHARED / "clara" / "clara-page.css").read_text(encoding="utf-8")

    for stylesheet in (vera, lucia_css):
        assert ".workstream-head h3" in stylesheet
        assert "font-size: clamp(1.8rem, 3.5vw, 2.8rem)" in stylesheet
        assert ".module-row h4" in stylesheet
        assert "font-size: clamp(1.2rem, 1.8vw, 1.5rem)" in stylesheet

    assert "font-size: clamp(1.5rem, 2.8vw, 2.1rem)" in clara_css
    assert "font-size: clamp(1.05rem, 1.8vw, 1.2rem)" in clara_css


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


def test_every_function_page_uses_one_shared_model_data_component() -> None:
    component_css = (SHARED / "function-model-data.css").read_text(encoding="utf-8")
    injector = (SHARED / "function-model-data.js").read_text(encoding="utf-8")
    renderer = (SHARED / "product-function-page.js").read_text(encoding="utf-8")
    renderer_css = (SHARED / "product-function-page.css").read_text(encoding="utf-8")
    bank_page = (SHARED / "journal-bank-reconciliation" / "index.html").read_text(
        encoding="utf-8"
    )

    shared_classes = (
        "function-model-data",
        "function-model-data__head",
        "function-model-data__heading",
        "function-model-data__label",
        "function-model-data__copy",
    )
    for class_name in shared_classes:
        assert class_name in injector
        assert class_name in renderer
        assert class_name in bank_page

    assert '@import url("./function-model-data.css");' in renderer_css
    assert "pf-model-data" not in renderer
    assert "pf-model-data" not in renderer_css
    assert 'href="../function-model-data.css"' in bank_page
    assert "grid-template-columns: minmax(240px, 0.75fr) minmax(0, 1.25fr)" in component_css

    for page_path in PRODUCT_PAGES.values():
        page = page_path.read_text(encoding="utf-8")
        for href in _directory_links(page):
            destination = _resolved_page(page_path, href)
            explanation = destination.read_text(encoding="utf-8")
            assert (
                "function-model-data.js" in explanation
                or "product-function-page.js" in explanation
                or 'class="function-model-data"' in explanation
            ), f"{destination}: does not use the shared model-data component"
