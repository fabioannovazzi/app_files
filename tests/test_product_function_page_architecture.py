from __future__ import annotations

import json
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


def _javascript_string_values(source: str, key: str) -> list[str]:
    pattern = rf'{re.escape(key)}\s*:\s*("(?:\\.|[^"\\])*")'
    return [json.loads(match) for match in re.findall(pattern, source)]


def _function_page_copy(source: str, page_name: str) -> str:
    if page_name == "bilancio-xbrl-it":
        return source.split("const bilancioModelData =", 1)[1].split(
            "Object.entries(bilancioModelData)", 1
        )[0]

    marker = f'    "{page_name}": {{'
    blocks: list[str] = []
    for match in re.finditer(re.escape(marker), source):
        start = match.start()
        following = re.search(r'\n    "[^"]+": \{', source[start + len(marker) :])
        end = (
            len(source)
            if following is None
            else start + len(marker) + following.start()
        )
        blocks.append(source[start:end])
    return max(blocks, key=lambda block: block.count("modelData:"))


def _directory_links(page: str) -> list[str]:
    return re.findall(
        r'<a class="(?:module-row|function-link)"[^>]+href="([^"]+)"',
        page,
    )


def _resolved_page(source: Path, href: str) -> Path:
    path = urlsplit(href).path
    return (source.parent / path).resolve()


def test_product_pages_are_directories_without_generic_method_or_data_sections() -> (
    None
):
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


def test_function_pages_do_not_repeat_the_breadcrumb_as_a_hero_eyebrow() -> None:
    destinations = {
        _resolved_page(page_path, href)
        for page_path in PRODUCT_PAGES.values()
        for href in _directory_links(page_path.read_text(encoding="utf-8"))
    }

    for destination in destinations:
        page = destination.read_text(encoding="utf-8")
        breadcrumb_match = re.search(
            r'<(?:strong|span)[^>]+(?:data-i18n="breadcrumb\.current"|'
            r'data-copy="breadcrumb\.product")[^>]*>([^<]+)</(?:strong|span)>',
            page,
        )
        eyebrow_match = re.search(
            r'<p class="eyebrow"[^>]+(?:data-i18n|data-copy)="hero\.eyebrow"'
            r"[^>]*>([^<]+)</p>",
            page,
        )
        if breadcrumb_match and eyebrow_match:
            assert (
                breadcrumb_match.group(1).casefold()
                != eyebrow_match.group(1).casefold()
            ), f"{destination}: hero eyebrow repeats the breadcrumb"


def test_italy_function_pages_honor_the_requested_language() -> None:
    for page_name in ("previdenza-inps", "registro-imprese-sari"):
        page = (SHARED / page_name / "index.html").read_text(encoding="utf-8")

        assert 'new URLSearchParams(window.location.search).get("lang")' in page
        assert "function applyLanguage(requestedLang)" in page
        assert 'translations[requestedLang] ? requestedLang : "it"' in page
        assert 'const safeLang = "it";' not in page


def test_lucia_and_vera_share_the_user_facing_research_function_page() -> None:
    vera = PRODUCT_PAGES["vera"].read_text(encoding="utf-8")
    lucia = PRODUCT_PAGES["lucia"].read_text(encoding="utf-8")

    shared_href = "../quesito-legale-fiscale/index.html"
    assert f'href="{shared_href}"' in vera
    assert f'href="{shared_href}?lang=it"' in lucia

    for internal_href in (
        "../prompt-optimizer/index.html",
        "../deep-research-validator/index.html",
    ):
        assert f'href="{internal_href}"' not in vera
        assert f'href="{internal_href}?lang=it"' in lucia


def test_lucia_and_vera_shared_studio_pages_are_product_neutral() -> None:
    function_copy = (SHARED / "product-function-pages.js").read_text(encoding="utf-8")
    renderer = (SHARED / "product-function-page.js").read_text(encoding="utf-8")

    for page_name in (
        "comunicazione-professionale",
        "presenza-digitale-studio",
        "quesito-legale-fiscale",
    ):
        page = (SHARED / page_name / "index.html").read_text(encoding="utf-8")
        configuration = re.search(
            rf'"{page_name}"\s*:\s*\{{(?P<body>.*?)\n\s*\}},\n\s*"',
            function_copy,
            re.DOTALL,
        )

        assert configuration is not None
        assert "shared: true" in configuration.group("body")
        assert "| Mparanza</title>" in page
        assert "| Vera</title>" not in page

    for expected in (
        "const isShared = page.shared === true;",
        'isShared ? "Mparanza" : page.product',
        "isShared ? ui.sharedRole : ui.productRole(page.product)",
        "isShared ? text.name : `${page.product} · ${text.name}`",
    ):
        assert expected in renderer


def test_starting_prompts_invoke_the_selected_product() -> None:
    navigation = (SHARED / "function-page-navigation.js").read_text(encoding="utf-8")

    for expected in (
        'const assistantNames = { vera: "Vera", lucia: "Lucia", clara: "Clara" };',
        '#prompt-example, [data-journey="prompt.text"], '
        '[data-i18n="example.prompt"], .pf-prompt',
        "renderStartingPrompts(product, currentLanguage);",
        "return `@${assistant} ${directCommand}`;",
        'it: ["Usa Vera per preparare", "Prepara"]',
    ):
        assert expected in navigation


def test_every_function_page_gets_one_clickable_work_area_breadcrumb() -> None:
    navigation = (SHARED / "function-page-navigation.js").read_text(encoding="utf-8")
    navigation_css = (SHARED / "function-page-navigation.css").read_text(
        encoding="utf-8"
    )
    destinations = {
        _resolved_page(page_path, href)
        for page_path in PRODUCT_PAGES.values()
        for href in _directory_links(page_path.read_text(encoding="utf-8"))
    }

    for destination in destinations:
        relative = destination.relative_to(SHARED)
        key = relative.parent.as_posix()
        page = destination.read_text(encoding="utf-8")

        assert f'"{key}": [' in navigation, f"{key}: missing area mapping"
        assert any(
            loader in page
            for loader in (
                "product-function-page.js",
                "function-model-data.js",
                "function-page-navigation.js",
            )
        ), f"{destination}: missing breadcrumb loader"

    assert 'const areaLink = document.createElement("a");' in navigation
    assert (
        "areaLink.href = `../${product}/index.html?lang=${currentLanguage}#${area}`;"
        in navigation
    )
    assert "breadcrumb.append(areaLink, separator, current);" in navigation
    assert ".function-breadcrumb a" in navigation_css


def test_product_directories_pass_the_exact_area_to_function_pages() -> None:
    expected_context = {
        "vera": 'url.searchParams.set("from", "vera");',
        "lucia": 'url.searchParams.set("from", "lucia");',
        "clara": 'url.searchParams.set("from", "clara");',
    }

    for product, page_path in PRODUCT_PAGES.items():
        page = page_path.read_text(encoding="utf-8")
        assert expected_context[product] in page
        assert 'url.searchParams.set("area", area);' in page


def test_vera_keeps_market_specific_functions_inside_user_job_areas() -> None:
    vera = PRODUCT_PAGES["vera"].read_text(encoding="utf-8")

    assert 'id="jurisdiction"' not in vera
    assert 'href="#jurisdiction"' not in vera
    assert "data-jurisdiction-section" not in vera
    assert "data-jurisdiction-nav" not in vera
    assert vera.count('data-jurisdiction-item="it"') == 7
    assert 'id="area-matters"' in vera
    assert 'id="area-analysis"' in vera
    assert 'id="area-studio"' in vera


def test_vera_navigation_links_to_the_five_user_job_areas() -> None:
    vera = PRODUCT_PAGES["vera"].read_text(encoding="utf-8")
    navigation_css = (SHARED / "product-navigation.css").read_text(encoding="utf-8")

    for href, key in (
        ("#area-clients", "nav.clients"),
        ("#area-matters", "nav.matters"),
        ("#area-accounting", "nav.accounting"),
        ("#area-analysis", "nav.analysis"),
        ("#area-studio", "nav.studio"),
    ):
        assert f'href="{href}"' in vera
        assert f'data-i18n="{key}"' in vera

    for label in (
        "Clienti, incarichi e documenti",
        "Pratiche e adempimenti",
        "Controlli e riconciliazioni",
        "Pianificazione, analisi e report",
        "Ricerca, comunicazione e sviluppo dello studio",
        "Clients, engagements, and documents",
        "Matters and compliance",
        "Dossiers et obligations",
        "Verfahren und Pflichten",
        "Expedientes y obligaciones",
    ):
        assert label in vera

    assert 'data-i18n="nav.capabilities">Cosa fa</a>' not in vera
    assert ".workstream { display: grid; gap: 28px; scroll-margin-top: 88px; }" in vera
    assert "@media (max-width: 1080px)" in navigation_css


def test_function_page_menus_use_literal_section_and_destination_labels() -> None:
    common_journey_pages = (
        "check-entries",
        "journal-bank-reconciliation",
        "journal-sampling",
        "report-builder",
        "riconciliazione-partite",
    )
    common_labels = {
        "nav.overview": (
            "Sintesi",
            "Summary",
            "Synthèse",
            "Zusammenfassung",
            "Resumen",
        ),
        "nav.workflow": ("Passaggi", "Steps", "Étapes", "Schritte", "Pasos"),
        "nav.proof": ("Video", "Video", "Vidéo", "Video", "Vídeo"),
    }
    specific_labels = {
        ("archive-organization", "nav.journey"): (
            "Passaggi",
            "Steps",
            "Étapes",
            "Schritte",
            "Pasos",
        ),
        ("new-client", "nav.journey"): (
            "Passaggi",
            "Steps",
            "Étapes",
            "Schritte",
            "Pasos",
        ),
        ("previdenza-inps", "nav.workflow"): (
            "Passaggi",
            "Steps",
            "Étapes",
            "Schritte",
            "Pasos",
        ),
        ("registro-imprese-sari", "nav.workflow"): (
            "Passaggi",
            "Steps",
            "Étapes",
            "Schritte",
            "Pasos",
        ),
        ("check-entries", "nav.next"): (
            "Campionamento",
            "Journal sampling",
            "Échantillonnage du journal",
            "Journalstichprobe",
            "Muestreo del diario",
        ),
        ("journal-sampling", "nav.next"): (
            "Controllo scritture",
            "Check entries",
            "Contrôle des écritures",
            "Buchungen prüfen",
            "Comprobar asientos",
        ),
        ("journal-bank-reconciliation", "nav.next"): (
            "Partite aperte",
            "Open items",
            "Postes ouverts",
            "Offene Posten",
            "Partidas abiertas",
        ),
        ("riconciliazione-partite", "nav.next"): (
            "Banca e contabilità",
            "Bank and accounting",
            "Banque et comptabilité",
            "Bank und Buchhaltung",
            "Banco y contabilidad",
        ),
        ("report-builder", "nav.next"): (
            "Funzioni collegate",
            "Related functions",
            "Fonctions associées",
            "Verknüpfte Funktionen",
            "Funciones relacionadas",
        ),
    }

    for page_name in common_journey_pages:
        page = (SHARED / page_name / "index.html").read_text(encoding="utf-8")
        for key, labels in common_labels.items():
            for label in labels:
                assert re.search(
                    rf'"{re.escape(key)}"\s*:\s*"{re.escape(label)}"', page
                )
            assert re.search(
                rf'data-journey="{re.escape(key)}"[^>]*>{re.escape(labels[0])}</a>',
                page,
            )

    for (page_name, key), labels in specific_labels.items():
        page = (SHARED / page_name / "index.html").read_text(encoding="utf-8")
        for label in labels:
            assert re.search(rf'"{re.escape(key)}"\s*:\s*"{re.escape(label)}"', page)
        assert re.search(
            rf'data-(?:i18n|journey)="{re.escape(key)}"[^>]*>'
            rf"{re.escape(labels[0])}</a>",
            page,
        )

    concordato = (SHARED / "concordato-plan-review" / "index.html").read_text(
        encoding="utf-8"
    )
    for label in (
        "File e data",
        "File and date",
        "Fichier et date",
        "Datei und Datum",
        "Archivo y fecha",
    ):
        assert re.search(rf'\bstart\s*:\s*"{re.escape(label)}"', concordato)
    assert 'data-copy="nav.start">File e data</a>' in concordato


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


def test_all_product_directories_distinguish_area_headings_from_function_links() -> (
    None
):
    vera = PRODUCT_PAGES["vera"].read_text(encoding="utf-8")
    lucia_css = (SHARED / "lucia" / "lucia-page.css").read_text(encoding="utf-8")
    clara_css = (SHARED / "clara" / "clara-page.css").read_text(encoding="utf-8")

    for stylesheet in (vera, lucia_css):
        assert ".workstream-head h3" in stylesheet
        assert "font-size: clamp(1.8rem, 3.5vw, 2.8rem)" in stylesheet
        assert ".module-row h4" in stylesheet
        assert "font-size: clamp(1.2rem, 1.8vw, 1.5rem)" in stylesheet

    assert "font-size: clamp(2rem, 4vw, 2.8rem)" in clara_css
    assert "font-size: clamp(1.05rem, 1.8vw, 1.2rem)" in clara_css


def test_product_roots_stop_after_the_function_directory() -> None:
    for page_path in PRODUCT_PAGES.values():
        page = page_path.read_text(encoding="utf-8")
        assert page.count("<section") == 2
        assert '<section id="workflow">' not in page
        assert "Funzioni disponibili" in page or "Available functions" in page


def test_shared_navigation_enforces_literal_titles_and_section_labels() -> None:
    navigation = (SHARED / "function-page-navigation.js").read_text(encoding="utf-8")

    for task_name in (
        "Request documents and clarifications from the client",
        "Prepare a legal or tax research question",
        "Verify research sources and conclusions",
        "Create Word reports from Excel, CSV, and PDF",
        "Create and revise presentations",
    ):
        assert task_name in (
            navigation
            + PRODUCT_PAGES["vera"].read_text(encoding="utf-8")
            + PRODUCT_PAGES["lucia"].read_text(encoding="utf-8")
            + PRODUCT_PAGES["clara"].read_text(encoding="utf-8")
            + (SHARED / "product-function-pages.js").read_text(encoding="utf-8")
        )

    for literal_label in (
        "Inputs and result",
        "Steps",
        "Video",
        "Starting prompt",
        "Related function",
        "Technical details",
    ):
        assert literal_label in navigation

    for vague_label in ("Guarda", "Da dove parte"):
        assert vague_label not in navigation


def test_shared_research_pages_are_product_neutral_at_render_time() -> None:
    navigation = (SHARED / "function-page-navigation.js").read_text(encoding="utf-8")

    for expected in (
        'key !== "prompt-optimizer" && key !== "deep-research-validator"',
        "sharedFunctionNouns",
        "document.title = `${title} | Mparanza`;",
        "node.textContent.replace(/\\bVera\\b/g, replacement)",
    ):
        assert expected in navigation


def test_function_pages_use_specific_data_copy_and_keep_future_page_fallback() -> None:
    function_copy = (SHARED / "product-function-pages.js").read_text(encoding="utf-8")
    placeholder_script = (SHARED / "function-model-data.js").read_text(encoding="utf-8")
    bank_page = (SHARED / "journal-bank-reconciliation" / "index.html").read_text(
        encoding="utf-8"
    )

    assert '"comunicazione-professionale"' in function_copy
    assert '"presenza-digitale-studio"' in function_copy
    communication_copy = function_copy.split('"comunicazione-professionale":', 1)[
        1
    ].split('"presenza-digitale-studio":', 1)[0]
    website_copy = function_copy.split('"presenza-digitale-studio":', 1)[1].split(
        '"apertura-pratica":', 1
    )[0]
    for workflow_copy in (communication_copy, website_copy):
        assert workflow_copy.count('modelDataStatus: "relevant"') == 5
        assert 'modelDataStatus: "not-relevant"' not in workflow_copy
    assert 'data-model-data-status="relevant"' in bank_page
    assert "Quali dati arrivano al modello" in bank_page
    assert "modelDataConclusion" in function_copy

    reviewed_vera_lucia = function_copy.split("const reviewedFunctionModelData =", 1)[
        1
    ].split("Object.entries(reviewedFunctionModelData)", 1)[0]
    reviewed_clara = function_copy.split("const reviewedClaraModelData =", 1)[1].split(
        "Object.entries(reviewedClaraModelData)", 1
    )[0]
    vera_lucia_workflows = (
        "dati-fiscali-strutturati",
        "email-cliente",
        "avviso-intake",
        "fatture-xml-check",
        "report-enti-locali",
        "apertura-pratica",
    )
    clara_workflows = (
        "clara-presentations",
        "clara-retailer-signals",
        "clara-brand-fit",
        "clara-interview",
        "clara-transcribe",
        "clara-documents",
        "clara-data-analysis",
    )
    for workflow in vera_lucia_workflows:
        assert f'"{workflow}": {{' in reviewed_vera_lucia
    for workflow in clara_workflows:
        assert f'"{workflow}": {{' in reviewed_clara
    assert (
        reviewed_vera_lucia.count("modelDataConclusion:")
        == len(vera_lucia_workflows) * 5
    )
    assert reviewed_clara.count("modelDataConclusion:") == len(clara_workflows) * 5
    assert (
        'modelDataStatus: "relevant"'
        in function_copy.split("Object.entries(reviewedFunctionModelData)", 1)[1]
    )
    assert (
        'modelDataStatus: "relevant"'
        in function_copy.split("Object.entries(reviewedClaraModelData)", 1)[1]
    )

    for placeholder in (
        "Informazioni specifiche per questa funzione in preparazione.",
        "Function-specific information is being prepared.",
        "Les informations spécifiques à cette fonction sont en préparation.",
        "Funktionsspezifische Informationen werden derzeit vorbereitet.",
        "Se está preparando la información específica de esta función.",
    ):
        assert placeholder in placeholder_script
        assert placeholder in function_copy


def test_professional_communication_page_explains_exact_phase_boundaries() -> None:
    function_copy = (SHARED / "product-function-pages.js").read_text(encoding="utf-8")
    communication_copy = function_copy.split('"comunicazione-professionale":', 1)[
        1
    ].split('"presenza-digitale-studio":', 1)[0]

    for snippet in (
        "Il nucleo condiviso di Vera e Lucia applica lo stesso perimetro",
        "Vera and Lucia’s shared core applies the same boundary",
        "Le noyau partagé de Vera et Lucia applique le même périmètre",
        "Der gemeinsame Kern von Vera und Lucia wendet dieselbe Grenze an",
        "El núcleo compartido de Vera y Lucia aplica el mismo límite",
        "non applica campioni o limiti di righe e colonne",
        "crea una copia completa pseudonimizzata per ogni file",
        "La verifica delle affermazioni riceve contratto, bozza e tutte le fonti correnti",
        "Il connettore per lo storico è bloccato",
        "solo Codex può inviare facoltativamente a Creative Production",
        "non è un sandbox di file autenticato dal provider",
        "applies no sampling or row/column cap",
        "new sources are added to a new run",
        "not a provider-authenticated file sandbox",
        "aucun échantillon ni plafond de lignes ou colonnes",
        "keine Stichprobe oder Zeilen-/Spaltenbegrenzung",
        "no aplica muestras ni límites de filas o columnas",
    ):
        assert snippet in communication_copy

    assert communication_copy.count('modelDataStatus: "relevant"') == 5
    assert communication_copy.count("modelDataConclusion:") == 5


def test_bandi_page_explains_task_specific_private_model_context() -> None:
    function_copy = (SHARED / "product-function-pages.js").read_text(encoding="utf-8")
    bandi_copy = function_copy.split('"bandi-agevolazioni":', 1)[1].split(
        '"quesito-legale-fiscale":', 1
    )[0]

    assert bandi_copy.count('modelDataStatus: "relevant"') == 5
    for snippet in (
        "una sessione del modello può leggere le sole evidenze cliente selezionate",
        "Le query pubbliche contengono solo territorio, categoria, tema d’investimento",
        "Il modulo iniziale del richiedente e i percorsi locali restano fuori",
        "500 elementi per collezione, 200 estratti e 2.000.000 byte",
        "gli ID esatti scelti dal professionista per la collezione eccedente",
        "Questi controlli operano nel run Studio Archive vincolato",
        "Non c’è anonimizzazione o pseudonimizzazione automatica",
        "500 items per collection, 200 excerpts, and 2,000,000 bytes",
        "These controls run inside the bound Studio Archive run",
        "Ces contrôles s’exécutent dans le run Studio Archive lié",
        "Diese Kontrollen gelten im gebundenen Studio-Archive-Run",
        "Estos controles operan en la ejecución vinculada de Studio Archive",
    ):
        assert snippet in bandi_copy


def test_bilancio_page_explains_task_specific_model_data_flow() -> None:
    function_copy = (SHARED / "product-function-pages.js").read_text(encoding="utf-8")

    for snippet in (
        'window.MPARANZA_FUNCTION_PAGES["bilancio-xbrl-it"]',
        "Il codice elabora l'intero bilancio",
        "Code processes the full accounts",
        "Le code traite l'intégralité des comptes",
        "Der Code verarbeitet den vollständigen Abschluss",
        "El código procesa todas las cuentas",
        "ragione sociale, codice fiscale, sede, periodo e configurazione",
        "paginated collections return at most 500 records per page",
        "not the snapshot body, storage paths, or bytes",
        "1 to 50 accounts for mapping",
        "the first 20 accounts plus at most 50 exact optional selectors",
        "jusqu'à 50 questions actives",
        "keine automatische Anonymisierung oder Pseudonymisierung",
        "no recibe automáticamente los archivos fuente, case.json ni el snapshot completo",
        "The model uses the same tools and limits",
    ):
        assert snippet in function_copy


def test_answer_assurance_pages_explain_actual_model_context_bounds() -> None:
    prompt_page = (SHARED / "prompt-optimizer" / "index.html").read_text(
        encoding="utf-8"
    )
    validator_page = (SHARED / "deep-research-validator" / "index.html").read_text(
        encoding="utf-8"
    )

    assert prompt_page.count('"model.copy":') == 5
    for snippet in (
        "l'intero quesito, non un campione",
        "20 URL, 30 date, 30 anni, 30 importi, 30 percentuali",
        "No automatic anonymization or pseudonymization is applied",
        "complete optimized brief, complete site list",
        "termes de la question ou des faits du dossier",
        "2.500 elementos o 2 MB",
        "vier Stunden lang",
        "legacy or unmanaged packages may still send the payload inline",
    ):
        assert snippet in prompt_page

    assert validator_page.count('"model.copy":') == 5
    for snippet in (
        "link Markdown e note restano completi",
        "1.000.001 byte",
        "every distinct HTTP/S URL extracted from the document may be fetched",
        "No automatic anonymization or pseudonymization is applied",
        "The screen shows up to 750 claims",
        "toutes les affirmations et tous les contrôles restent disponibles",
        "2 500 éléments ou 2 Mo",
        "cuatro horas",
        "ältere oder nicht verwaltete Pakete",
    ):
        assert snippet in validator_page

    for jargon in (
        "Nella revisione gestita con MCP locale",
        "riferimento SHA-256",
        "record canonico",
        "managed local-MCP review",
        "canonical record",
        "payload inline",
    ):
        assert jargon not in validator_page

    for page in (prompt_page, validator_page):
        model_data_start = page.index('id="model-data"')
        main_end = page.index("</main>", model_data_start)
        assert "<section" not in page[model_data_start + 1 : main_end]


def test_professional_question_page_explains_the_complete_answer_journey() -> None:
    page = (SHARED / "quesito-legale-fiscale" / "index.html").read_text(
        encoding="utf-8"
    )
    function_copy = (SHARED / "product-function-pages.js").read_text(encoding="utf-8")
    workflow_copy = function_copy.split('"quesito-legale-fiscale":', 1)[1].split(
        '"comunicazione-professionale":', 1
    )[0]

    assert 'data-function-page="quesito-legale-fiscale"' in page
    assert workflow_copy.count('modelDataStatus: "relevant"') == 5
    for snippet in (
        "Risposta a quesiti legali e fiscali",
        "Answer legal and tax questions",
        "Répondre aux questions juridiques et fiscales",
        "Rechtliche und steuerliche Fragen beantworten",
        "Responder consultas jurídicas y fiscales",
        "l'intero quesito, non un campione",
        "separate runs in the same Studio Archive engagement",
        "Aucune anonymisation ou pseudonymisation automatique",
        "keine automatische Anonymisierung oder Pseudonymisierung",
        "No se aplica anonimización ni seudonimización automática",
    ):
        assert snippet in workflow_copy


def test_clara_research_video_has_a_localized_public_explanation() -> None:
    page = (SHARED / "clara-research-video" / "index.html").read_text(encoding="utf-8")
    function_copy = (SHARED / "product-function-pages.js").read_text(encoding="utf-8")
    renderer = (SHARED / "product-function-page.js").read_text(encoding="utf-8")
    clara = PRODUCT_PAGES["clara"].read_text(encoding="utf-8")
    navigation = (SHARED / "function-page-navigation.js").read_text(encoding="utf-8")
    research_video = function_copy.split('"clara-research-video":', 1)[1].split(
        '"clara-retailer-signals":', 1
    )[0]

    assert 'data-function-page="clara-research-video"' in page
    assert research_video.count('modelDataStatus: "relevant"') == 5
    for snippet in (
        "Approved ordered scenes",
        "English, Italian, French, German, or Spanish narration",
        "localized AI-voice disclosure",
        "accepted Vera visuals and their review artifacts",
        "Parallax requires already separated and aligned",
        "No automatic anonymization is applied",
        "authenticated Mparanza page sends only the approved text to OpenAI",
        "No user API key is required",
        "does not save the request or audio to application storage",
        "does not state an OpenAI retention period",
    ):
        assert snippet in research_video
    for heading in (
        "Quali dati arrivano al modello",
        "What data reaches the model",
        "Quelles données parviennent au modèle",
        "Welche Daten das Modell erhält",
        "Qué datos recibe el modelo",
    ):
        assert heading in renderer
    assert 'href="../clara-research-video/index.html?lang=en"' in clara
    assert clara.count('"functions.researchVideo":') == 5
    assert '"clara-research-video": [["clara", "area-deliverables"]]' in navigation


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
    assert "function-model-data__conclusion" in renderer
    assert "function-model-data__conclusion" in component_css
    assert "pf-model-data" not in renderer
    assert "pf-model-data" not in renderer_css
    assert 'href="../function-model-data.css"' in bank_page
    assert (
        "grid-template-columns: minmax(240px, 0.75fr) minmax(0, 1.25fr)"
        in component_css
    )

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


def test_long_vera_model_data_explanations_render_as_three_paragraphs() -> None:
    function_copy = (SHARED / "product-function-pages.js").read_text(encoding="utf-8")
    renderer = (SHARED / "product-function-page.js").read_text(encoding="utf-8")
    injector = (SHARED / "function-model-data.js").read_text(encoding="utf-8")

    for page_name in (
        "variance-analysis",
        "bilancio-xbrl-it",
        "bandi-agevolazioni",
        "quesito-legale-fiscale",
        "comunicazione-professionale",
        "presenza-digitale-studio",
    ):
        values = _javascript_string_values(
            _function_page_copy(function_copy, page_name), "modelData"
        )
        assert len(values) == 5
        assert all(len(value.split("\n\n")) == 3 for value in values)

    for page_name in (
        "deep-research-validator",
        "previdenza-inps",
        "prompt-optimizer",
        "registro-imprese-sari",
        "report-builder",
        "sales-plan",
    ):
        page = (SHARED / page_name / "index.html").read_text(encoding="utf-8")
        values = _javascript_string_values(page, '"model.copy"')
        assert len(values) == 5
        assert all(len(value.split("\n\n")) == 3 for value in values)

    assert "modelDataParagraphs.map" in renderer
    assert 'class="function-model-data__copy"' in renderer
    assert "initializeParagraphs" in injector
    assert 'paragraph.className = "function-model-data__copy";' in injector


def test_all_function_page_systems_use_the_shared_quiet_typography_scale() -> None:
    scale = (SHARED / "function-page-scale.css").read_text(encoding="utf-8")
    renderer_css = (SHARED / "product-function-page.css").read_text(encoding="utf-8")
    shell_css = (SHARED / "plugin-page-shell.css").read_text(encoding="utf-8")
    model_data_css = (SHARED / "function-model-data.css").read_text(encoding="utf-8")
    studio_archive = (SHARED / "studio-archive" / "index.html").read_text(
        encoding="utf-8"
    )

    for token in (
        "--function-title-size: 2.875rem",
        "--function-section-title-size: 2.125rem",
        "--function-subsection-title-size: 1.125rem",
        "--function-lead-size: 1.1875rem",
        "--function-heading-line-height: 1.12",
    ):
        assert token in scale

    assert '@import url("./function-page-scale.css")' in renderer_css
    assert '@import url("./function-page-scale.css")' in shell_css
    assert "var(--function-title-size)" in renderer_css
    assert "var(--function-section-title-size, 2.125rem)" in model_data_css
    assert (
        'href="../function-page-scale.css?v=20260813-function-pages"' in studio_archive
    )
    assert "clamp(3rem, 7vw, 6rem)" not in renderer_css
    assert "clamp(3.25rem, 7.4vw, 6.8rem)" not in studio_archive

    for page_path in PRODUCT_PAGES.values():
        page = page_path.read_text(encoding="utf-8")
        for href in _directory_links(page):
            destination = _resolved_page(page_path, href)
            explanation = destination.read_text(encoding="utf-8")
            assert any(
                stylesheet in explanation
                for stylesheet in (
                    "product-function-page.css?v=20260813-function-pages",
                    "plugin-page-shell.css?v=20260813-function-pages",
                    "function-page-scale.css?v=20260813-function-pages",
                )
            ), f"{destination}: does not consume the shared function-page scale"
