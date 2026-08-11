"""Public website and narrowly scoped hosted-service application."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    status,
)
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, RedirectResponse, Response

try:  # pragma: no cover - optional dependency during tests
    from fastapi.templating import Jinja2Templates
except Exception:  # noqa: BLE001
    Jinja2Templates = None  # type: ignore[misc,assignment]
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from modules.auth.api import router as auth_router
from modules.auth.api import site_router as auth_site_router
from modules.auth.config import get_auth_config
from modules.auth.dependencies import require_site_permission_for_request
from modules.case_notes_voice.api import router as case_notes_voice_router
from modules.case_notes_voice.api import site_router as case_notes_voice_site_router
from modules.case_notes_voice.api import (
    start_voice_retention_cleanup,
    stop_voice_retention_cleanup,
)
from modules.change_requests import router as change_requests_router
from modules.hosted_interviews.api import admin_router as hosted_interviews_admin_router
from modules.hosted_interviews.api import (
    public_router as hosted_interviews_public_router,
)
from modules.hosted_interviews.api import site_router as hosted_interviews_site_router
from modules.notifications.notifier import process_pending_notifications
from modules.pdp.attribute_reporting_api import router as attribute_reporting_router
from modules.pdp.data_handling_content import get_data_handling_content
from modules.pdp.language import (
    LANDING_LANGUAGE_LABELS,
    LANGUAGE_LABELS,
    LANGUAGE_ORDER,
    get_page_copy,
    resolve_language,
)
from modules.pdp.legal_content import get_legal_page
from modules.pdp.privacy_register import get_public_privacy_register
from modules.utilities.logging_config import configure_logging
from modules.utilities.secrets_loader import load_env_from_secrets_file
from modules.utilities.session_cleanup import cleanup_sessions
from modules.utilities.session_context import build_session_context, use_session_context

__all__ = ["app", "create_app"]

load_env_from_secrets_file()

configure_logging("hosted_services_api")

templates = Jinja2Templates(directory="templates") if Jinja2Templates else None
LOGGER = logging.getLogger(__name__)
SESSION_RETENTION_HOURS = 168  # seven days
SESSION_CLEANUP_INTERVAL_SECONDS = 24 * 3600  # run daily
_SESSION_CLEANUP_STOP = threading.Event()
_SESSION_CLEANUP_THREAD: Optional[threading.Thread] = None


def _forbidden_message(detail: Any) -> str:
    if isinstance(detail, dict):
        message = detail.get("message")
        email = detail.get("email")
        if isinstance(message, str) and message.strip():
            if isinstance(email, str) and email.strip():
                return f"{message.strip()} (signed in as {email.strip()})"
            return message
    if isinstance(detail, str) and detail.strip():
        return detail
    return "You are not authorized to see this page. Please contact fabio@mparanza.com."


def _request_prefers_html(request: Request) -> bool:
    if request.method not in {"GET", "HEAD"}:
        return False
    accept_header = request.headers.get("accept", "")
    if not accept_header:
        return False
    media_types = {
        item.split(";", 1)[0].strip().lower()
        for item in accept_header.split(",")
        if item.strip()
    }
    return "text/html" in media_types or "application/xhtml+xml" in media_types


def _not_found_destination(path: str, lang: str) -> tuple[str, str]:
    del path
    return f"/?lang={lang}", "Return home"


def _not_found_context(request: Request, detail: Any) -> Dict[str, Any]:
    _ = detail
    lang = request.query_params.get("lang") or resolve_language(request)
    primary_href, primary_label = _not_found_destination(request.url.path, lang)
    message = "The page may have moved, been deleted, or the URL may be incomplete."
    return {
        "request": request,
        "lang": lang,
        "requested_path": request.url.path,
        "primary_href": primary_href,
        "primary_label": primary_label,
        "message": message,
    }


def _run_session_cleanup() -> None:
    try:
        removed, scanned = cleanup_sessions(
            SESSION_RETENTION_HOURS,
            dry_run=False,
            logger=LOGGER,
        )
        LOGGER.info(
            "Session cleanup scanned %s artifacts and removed %s stale sessions",
            scanned,
            removed,
        )
    except Exception:
        LOGGER.exception("Session cleanup failed")


def _session_cleanup_loop() -> None:
    LOGGER.info(
        "Session cleanup worker started (interval=%sh, retention=%sh)",
        SESSION_CLEANUP_INTERVAL_SECONDS / 3600,
        SESSION_RETENTION_HOURS,
    )
    while not _SESSION_CLEANUP_STOP.is_set():
        _run_session_cleanup()
        if _SESSION_CLEANUP_STOP.wait(SESSION_CLEANUP_INTERVAL_SECONDS):
            break
    LOGGER.info("Session cleanup worker stopped")


def _start_session_cleanup() -> None:
    global _SESSION_CLEANUP_THREAD
    if _SESSION_CLEANUP_THREAD and _SESSION_CLEANUP_THREAD.is_alive():
        return
    _SESSION_CLEANUP_STOP.clear()
    _SESSION_CLEANUP_THREAD = threading.Thread(
        target=_session_cleanup_loop,
        name="session-cleanup-worker",
        daemon=True,
    )
    _SESSION_CLEANUP_THREAD.start()


def _stop_session_cleanup() -> None:
    _SESSION_CLEANUP_STOP.set()
    thread = _SESSION_CLEANUP_THREAD
    if thread and thread.is_alive():
        thread.join(timeout=5)


site_router = APIRouter()
BETA_LINKS: set[str] = set()
CLARA_PERMISSION_KEY = "clara"
CLARA_FORBIDDEN_COPY: dict[str, dict[str, str]] = {
    "en": {
        "title": "Clara access",
        "message": "Clara is available only to authorized users.",
        "return_home_label": "Return home",
    },
    "it": {
        "title": "Accesso Clara",
        "message": "Clara è disponibile solo per gli utenti autorizzati.",
        "return_home_label": "Torna alla home",
    },
    "fr": {
        "title": "Accès Clara",
        "message": "Clara est disponible uniquement pour les utilisateurs autorisés.",
        "return_home_label": "Retour à l'accueil",
    },
    "de": {
        "title": "Clara-Zugang",
        "message": "Clara ist nur für autorisierte Nutzer verfügbar.",
        "return_home_label": "Zur Startseite",
    },
    "es": {
        "title": "Acceso Clara",
        "message": "Clara solo está disponible para usuarios autorizados.",
        "return_home_label": "Volver al inicio",
    },
}


def _template_context(**extra: Any) -> dict[str, Any]:
    config = get_auth_config()
    base_context = {
        "auth_enabled": config.authentication_enabled,
        "app_css_asset_version": _static_asset_version("static/css/app.css"),
        "thesis_image_asset_version": _static_asset_version(
            "static/icons/power_control.png"
        ),
        "google_client_id": config.google_client_id,
    }
    base_context.update(extra)
    return base_context


def _static_asset_version(path: str) -> str:
    try:
        return str(int(Path(path).stat().st_mtime))
    except OSError:
        return str(int(time.time()))


TOOLTIP_CONTENT: Dict[str, Dict[str, str]] = {
    "en": {
        "clara_plugin": "Organizes case materials, notes, and reviewed judgements into shareable client outputs.",
        "lucia_plugin": "Prepares reviewable legal work, professional communications and law-firm websites.",
        "vera": "Vera works with accounting-firm files to prepare new-client work, checks, reconciliations, INPS case review, reports and tax or regulatory research.",
        "codex_accountants_group": "Guided procedures for documents, controls, reports, and tax or regulatory research.",
        "codex_consultants_group": "Guided procedures for turning materials, analysis, and expert judgement into client-ready outputs.",
        "codex_lawyers_group": "Guided procedures for legal research, professional communications and law-firm websites.",
    },
    "it": {
        "clara_plugin": "Organizza materiali, note e valutazioni approvate in output condivisibili per il cliente.",
        "lucia_plugin": "Prepara lavoro legale, comunicazioni professionali e siti di studio rivedibili.",
        "vera": "Vera lavora sui file dello studio per svolgere istruttorie, controlli, riconciliazioni, pratiche previdenziali INPS, report e ricerca fiscale o normativa.",
        "codex_accountants_group": "Procedure guidate per lavorare su documenti, controlli, report e ricerca fiscale.",
        "codex_consultants_group": "Procedure guidate per trasformare materiali, analisi e giudizio esperto in output per il cliente.",
        "codex_lawyers_group": "Procedure guidate per ricerca legale, comunicazioni professionali e siti dello studio.",
    },
    "fr": {
        "clara_plugin": "Organise les matériaux, notes et jugements validés en livrables client partageables.",
        "lucia_plugin": "Prépare travail juridique, communications professionnelles et sites de cabinet révisables.",
        "vera": "Vera travaille sur les fichiers du cabinet pour réaliser les revues de dossiers clients, contrôles, rapprochements, dossiers INPS, rapports et recherches fiscales ou réglementaires.",
        "codex_accountants_group": "Procédures guidées pour documents, contrôles, rapports et recherche fiscale ou réglementaire.",
        "codex_consultants_group": "Procédures guidées pour transformer matériaux, analyses et jugement expert en livrables client.",
        "codex_lawyers_group": "Procédures guidées pour recherche juridique, communications professionnelles et sites de cabinet.",
    },
    "de": {
        "clara_plugin": "Organisiert Fallmaterialien, Notizen und freigegebene Einschätzungen zu teilbaren Kundenergebnissen.",
        "lucia_plugin": "Erstellt überprüfbare Rechtsarbeit, Fachkommunikation und Kanzleiwebsites.",
        "vera": "Vera arbeitet mit Kanzleidateien an Mandantenaufnahme, Prüfungen, Abstimmungen, INPS-Fällen, Berichten sowie steuerlicher oder regulatorischer Recherche.",
        "codex_accountants_group": "Geführte Verfahren für Dokumente, Kontrollen, Berichte sowie Steuer- und Regulierungsrecherche.",
        "codex_consultants_group": "Geführte Verfahren, um Materialien, Analysen und Expertenurteile in Kundenergebnisse zu verwandeln.",
        "codex_lawyers_group": "Geführte Verfahren für Rechtsrecherche, fachliche Kommunikation und Kanzleiwebsites.",
    },
    "es": {
        "clara_plugin": "Organiza materiales del caso, notas y valoraciones revisadas en entregables que pueden compartirse con el cliente.",
        "lucia_plugin": "Prepara trabajo jurídico, comunicaciones profesionales y sitios de despacho revisables.",
        "vera": "Vera trabaja con los archivos del despacho para preparar nuevos clientes, comprobaciones, conciliaciones, revisiones de expedientes del INPS, informes e investigación fiscal o regulatoria.",
        "codex_accountants_group": "Procedimientos guiados para documentos, controles, informes e investigación fiscal o regulatoria.",
        "codex_consultants_group": "Procedimientos guiados para convertir materiales, análisis y criterio experto en entregables listos para el cliente.",
        "codex_lawyers_group": "Procedimientos guiados para investigación jurídica, comunicaciones profesionales y sitios de despacho.",
    },
}

LANDING_CONTENT: Dict[str, Dict[str, Any]] = {
    "en": {
        "primary": {
            "title": "",
            "links": [],
        },
        "sections": [
            {
                "preserve_order": True,
                "groups": [
                    {
                        "id": "vera",
                        "title": "For accountants",
                        "tooltip_key": "codex_accountants_group",
                        "audience": "For accountants",
                        "lead": (
                            "A specialist plugin for client files, accounting checks, "
                            "reconciliations and reporting."
                        ),
                        "description": (
                            "Vera works directly on the firm's files. It handles new-client "
                            "work and journal sampling, checks entries, reconciles records, "
                            "and prepares reports or tax and regulatory research."
                        ),
                        "proof": [
                            "From new-client work to regulatory research",
                            "Reviewable checks and reconciliations",
                            "Workpapers ready for professional review",
                        ],
                        "cta_label": "Explore Vera",
                        "icon": "/static/shared/vera/icon.svg",
                        "links": [
                            {
                                "label": "Vera",
                                "href": "/static/shared/vera/index.html",
                                "active": True,
                                "tooltip_key": "vera",
                                "public": True,
                            },
                        ],
                    },
                    {
                        "id": "clara",
                        "title": "For consultants",
                        "tooltip_key": "codex_consultants_group",
                        "audience": "For consultants",
                        "lead": (
                            "A specialist plugin for presentations and ongoing project work."
                        ),
                        "description": (
                            "Clara brings documents, notes, interviews and recordings together "
                            "in the project folder, then uses that context to create or revise "
                            "presentations, briefs and decision packs."
                        ),
                        "proof": [
                            "Project context carried forward",
                            "Evidence gathered in one workspace",
                            "Briefs, presentations and decision packs",
                        ],
                        "cta_label": "Explore Clara",
                        "icon": "/static/shared/clara/icon.svg",
                        "links": [
                            {
                                "label": "Clara",
                                "href": "/static/shared/clara/index.html",
                                "active": True,
                                "tooltip_key": "clara_plugin",
                                "public": True,
                            },
                        ],
                    },
                    {
                        "id": "lucia",
                        "title": "For independent lawyers",
                        "tooltip_key": "codex_lawyers_group",
                        "audience": "For independent lawyers",
                        "lead": (
                            "A specialist plugin for reviewable legal work, professional "
                            "communications and the firm’s informational website."
                        ),
                        "description": (
                            "Lucia frames and checks legal work, prepares source-backed "
                            "communications and builds informational law-firm websites "
                            "from verified material."
                        ),
                        "proof": [
                            "Legal questions with a defined scope",
                            "Professional communications with sources and approval gates",
                            "Informational websites built from verified firm facts",
                        ],
                        "cta_label": "Explore Lucia",
                        "icon": "/static/shared/lucia/icon.svg",
                        "links": [
                            {
                                "label": "Lucia",
                                "href": "/static/shared/lucia/index.html",
                                "active": True,
                                "tooltip_key": "lucia_plugin",
                                "public": True,
                            },
                        ],
                    },
                ],
            },
        ],
        "menu_links": [],
        "hero": {
            "id": "hero",
            "skip_label": "Skip to main content",
            "plugins_label": "Mparanza plugins",
            "eyebrow": "Plugins for professional work",
            "headline": "AI has the power. The method provides the control.",
            "subheadline": (
                "Mparanza builds specialist methods into plugins for professional work. "
                "For ChatGPT Work, Codex, and Claude Cowork."
            ),
        },
        "harness": {
            "id": "method",
            "title": "The method turns AI capability into professional work.",
            "description": (
                "AI can reason, analyze, and create. Each plugin gives those capabilities "
                "a specialist method: defined sources, ordered steps, explicit checks, "
                "review points, and expected outputs. That method is what we mean by control."
            ),
            "layers": [
                {
                    "title": "Power",
                    "blurb": "The model reasons, analyzes and creates.",
                },
                {
                    "title": "Method",
                    "blurb": "The plugin defines sources, steps, and professional criteria.",
                },
                {
                    "title": "Control",
                    "blurb": (
                        "Checks, review points, and expected outputs make the work reviewable."
                    ),
                },
            ],
        },
        "open_source": {
            "id": "open-source",
            "title": "Open by design.",
            "description": (
                "Clara, Vera and Lucia are open-source plugins. "
                "You can inspect the methods, controls, and code before using them—and "
                "adapt them to your work."
            ),
            "links_label": "Open-source information",
            "links": [
                {
                    "label": "Inspect the source on GitHub",
                    "href": "https://github.com/fabioannovazzi/app_files",
                },
                {
                    "label": "Read the GNU AGPLv3 license",
                    "href": "https://github.com/fabioannovazzi/app_files/blob/main/LICENSE",
                },
            ],
        },
        "free": {
            "id": "free",
            "title": "Free by design.",
            "description": (
                "Clara, Vera and Lucia are free to install and use. We welcome contributions "
                "to their development. We charge for consulting, implementation, "
                "and hosted services."
            ),
        },
        "security": {
            "id": "security",
            "title": "Secure by design.",
            "lead": (
                "In ordinary Clara, Vera and Lucia workflows, Mparanza does not receive your client work."
            ),
            "description": (
                "Ordinary plugin workflows run inside the AI workspace you choose. "
                "Your client prompts, files, and outputs do not pass through Mparanza."
            ),
            "cta_label": "See how your data is handled",
            "cta_href": "/data-handling",
        },
        "compliance": {
            "id": "compliance",
            "title": "Compliant by design.",
            "lead": (
                "Professional work may require the selected AI workspace to read real client data."
            ),
            "description": (
                "Clara, Vera and Lucia do not automatically anonymise data. They may use "
                "local Python to filter or aggregate information when useful. Data "
                "supplied to the model is processed under the terms and controls of "
                "the AI workspace the user chooses."
            ),
            "principles": [
                {
                    "title": "Use local Python when useful",
                    "blurb": "Filtering and aggregation can happen on your computer when they improve the work. They are not automatic anonymisation.",
                },
                {
                    "title": "Real data may reach the model",
                    "blurb": "Names, documents, original language, and case facts may enter the model context when the professional task needs them.",
                },
                {
                    "title": "Two processing categories",
                    "blurb": "Ordinary plugin functions use the AI workspace the user chooses. Mparanza-hosted services form a separate processing boundary.",
                },
            ],
            "closing": "One policy for Clara, Vera and Lucia. No prompt-by-prompt paperwork.",
            "cta_label": "See how your data is handled",
            "cta_href": "/data-handling",
        },
        "bridge": {
            "id": "plugins",
            "title": "Plugins by design.",
            "description": (
                "Mparanza is Clara, Vera and Lucia: three plugins that bring specialist "
                "methods to three different professions."
            ),
        },
    },
    "it": {
        "primary": {
            "title": "",
            "links": [],
        },
        "sections": [
            {
                "preserve_order": True,
                "groups": [
                    {
                        "id": "vera",
                        "title": "Per commercialisti",
                        "tooltip_key": "codex_accountants_group",
                        "audience": "Per commercialisti",
                        "lead": (
                            "Un plugin specialistico per lavorare su fascicoli, controlli contabili, "
                            "riconciliazioni e report."
                        ),
                        "description": (
                            "Vera lavora direttamente sui file dello studio. Gestisce "
                            "istruttorie e campionamenti, controlla le scritture, esegue "
                            "riconciliazioni e prepara report o ricerche fiscali e normative."
                        ),
                        "proof": [
                            "Dall'istruttoria alla ricerca fiscale",
                            "Controlli e riconciliazioni rivedibili",
                            "Carte di lavoro pronte per la revisione",
                        ],
                        "cta_label": "Scopri Vera",
                        "icon": "/static/shared/vera/icon.svg",
                        "links": [
                            {
                                "label": "Vera",
                                "href": "/static/shared/vera/index.html",
                                "active": True,
                                "tooltip_key": "vera",
                                "public": True,
                            },
                        ],
                    },
                    {
                        "id": "clara",
                        "title": "Per consulenti",
                        "tooltip_key": "codex_consultants_group",
                        "audience": "Per consulenti",
                        "lead": (
                            "Un plugin specialistico per creare presentazioni e dare continuità "
                            "al lavoro sui progetti."
                        ),
                        "description": (
                            "Clara riunisce documenti, note, interviste e registrazioni "
                            "nella cartella del progetto e usa questo contesto per creare "
                            "o aggiornare presentazioni, note di sintesi e dossier "
                            "decisionali."
                        ),
                        "proof": [
                            "Contesto del progetto sempre disponibile",
                            "Materiali riuniti nella cartella del progetto",
                            "Presentazioni, sintesi e dossier decisionali",
                        ],
                        "cta_label": "Scopri Clara",
                        "icon": "/static/shared/clara/icon.svg",
                        "links": [
                            {
                                "label": "Clara",
                                "href": "/static/shared/clara/index.html",
                                "active": True,
                                "tooltip_key": "clara_plugin",
                                "public": True,
                            },
                        ],
                    },
                    {
                        "id": "lucia",
                        "title": "Per avvocati indipendenti",
                        "tooltip_key": "codex_lawyers_group",
                        "audience": "Per avvocati indipendenti",
                        "lead": (
                            "Un plugin specialistico per lavoro legale rivedibile, "
                            "comunicazioni professionali e sito informativo dello studio."
                        ),
                        "description": (
                            "Lucia imposta e verifica il lavoro legale, prepara "
                            "comunicazioni fondate su fonti e realizza siti informativi "
                            "dello studio da materiali verificati."
                        ),
                        "proof": [
                            "Quesiti legali con un perimetro definito",
                            "Comunicazioni professionali con fonti e approvazioni",
                            "Siti informativi costruiti su fatti verificati dello studio",
                        ],
                        "cta_label": "Scopri Lucia",
                        "icon": "/static/shared/lucia/icon.svg",
                        "links": [
                            {
                                "label": "Lucia",
                                "href": "/static/shared/lucia/index.html",
                                "active": True,
                                "tooltip_key": "lucia_plugin",
                                "public": True,
                            },
                        ],
                    },
                ],
            },
        ],
        "menu_links": [],
        "hero": {
            "id": "hero",
            "skip_label": "Vai al contenuto principale",
            "plugins_label": "Plugin Mparanza",
            "eyebrow": "Plugin per il lavoro professionale",
            "headline": "La potenza viene dall'AI. Il controllo, dal metodo.",
            "subheadline": (
                "Mparanza incorpora metodi specialistici in plugin per il lavoro "
                "professionale. Per ChatGPT Work, Codex e Claude Cowork."
            ),
        },
        "harness": {
            "id": "method",
            "title": "Il metodo trasforma le capacità dell'AI in lavoro professionale.",
            "description": (
                "L'AI può ragionare, analizzare e creare. Ogni plugin dà a queste capacità "
                "un metodo specialistico: fonti definite, passaggi ordinati, verifiche "
                "esplicite, punti di revisione e risultati attesi. È questo metodo che "
                "intendiamo per controllo."
            ),
            "layers": [
                {
                    "title": "Potenza",
                    "blurb": "Il modello ragiona, analizza e crea.",
                },
                {
                    "title": "Metodo",
                    "blurb": "Il plugin definisce fonti, passaggi e criteri professionali.",
                },
                {
                    "title": "Controllo",
                    "blurb": (
                        "Verifiche, punti di revisione e risultati attesi rendono il "
                        "lavoro rivedibile."
                    ),
                },
            ],
        },
        "open_source": {
            "id": "open-source",
            "title": "Aperti per scelta.",
            "description": (
                "Clara, Vera e Lucia sono plugin open source. "
                "Puoi esaminare i metodi, i controlli e il codice prima di usarli, e "
                "adattarli al tuo lavoro."
            ),
            "links_label": "Informazioni open source",
            "links": [
                {
                    "label": "Esamina il codice su GitHub",
                    "href": "https://github.com/fabioannovazzi/app_files",
                },
                {
                    "label": "Leggi la licenza GNU AGPLv3",
                    "href": "https://github.com/fabioannovazzi/app_files/blob/main/LICENSE",
                },
            ],
        },
        "free": {
            "id": "free",
            "title": "Gratuiti per scelta.",
            "description": (
                "Clara, Vera e Lucia si possono installare e usare gratuitamente. Accogliamo "
                "volentieri contributi al loro sviluppo. Offriamo a pagamento "
                "consulenza, implementazione e servizi hosted."
            ),
        },
        "security": {
            "id": "security",
            "title": "Sicuri per scelta.",
            "lead": "Nei flussi ordinari di Clara, Vera e Lucia, Mparanza non riceve il lavoro dei tuoi clienti.",
            "description": (
                "I normali workflow dei plugin operano nell'ambiente AI che scegli. "
                "Prompt, file e risultati dei tuoi clienti non passano attraverso Mparanza."
            ),
            "cta_label": "Scopri come vengono gestiti i tuoi dati",
            "cta_href": "/data-handling",
        },
        "compliance": {
            "id": "compliance",
            "title": "Conformi per scelta.",
            "lead": "Il lavoro professionale può richiedere che l'ambiente AI scelto legga dati reali dei clienti.",
            "description": "Clara, Vera e Lucia non anonimizzano automaticamente i dati. Possono usare Python in locale per filtrare o aggregare le informazioni quando è utile. I dati forniti al modello vengono trattati secondo i termini e i controlli dell'ambiente AI scelto dall'utente.",
            "principles": [
                {
                    "title": "Usa Python in locale quando serve",
                    "blurb": "Filtri e aggregazioni possono essere eseguiti sul tuo computer quando migliorano il lavoro. Non sono anonimizzazione automatica.",
                },
                {
                    "title": "I dati reali possono arrivare al modello",
                    "blurb": "Nomi, documenti, testo originale e fatti del caso possono entrare nel contesto del modello quando servono al lavoro professionale.",
                },
                {
                    "title": "Due categorie di trattamento",
                    "blurb": "Le normali funzioni dei plugin usano l'ambiente AI scelto dall'utente. I servizi hosted di Mparanza hanno un confine di trattamento separato.",
                },
            ],
            "closing": "Una regola per Clara, Vera e Lucia. Nessuna burocrazia prompt per prompt.",
            "cta_label": "Scopri come vengono gestiti i tuoi dati",
            "cta_href": "/data-handling",
        },
        "bridge": {
            "id": "plugins",
            "title": "Plugin per scelta.",
            "description": (
                "Mparanza è Clara, Vera e Lucia: tre plugin che incorporano metodi "
                "specialistici per tre professioni diverse."
            ),
        },
    },
    "fr": {
        "primary": {
            "title": "",
            "links": [],
        },
        "sections": [
            {
                "preserve_order": True,
                "groups": [
                    {
                        "id": "vera",
                        "title": "Pour les experts-comptables",
                        "tooltip_key": "codex_accountants_group",
                        "audience": "Pour les experts-comptables",
                        "lead": (
                            "Un plugin spécialisé pour les dossiers clients, les contrôles "
                            "comptables, les rapprochements et les rapports."
                        ),
                        "description": (
                            "Vera travaille directement sur les fichiers du cabinet. Elle "
                            "prépare les dossiers et les échantillons, contrôle les écritures, "
                            "effectue les rapprochements et produit des rapports ou des "
                            "recherches fiscales et réglementaires."
                        ),
                        "proof": [
                            "De l'ouverture du dossier à la recherche fiscale",
                            "Contrôles et rapprochements révisables",
                            "Feuilles de travail prêtes à être revues",
                        ],
                        "cta_label": "Découvrir Vera",
                        "icon": "/static/shared/vera/icon.svg",
                        "links": [
                            {
                                "label": "Vera",
                                "href": "/static/shared/vera/index.html",
                                "active": True,
                                "tooltip_key": "vera",
                                "public": True,
                            },
                        ],
                    },
                    {
                        "id": "clara",
                        "title": "Pour les consultants",
                        "tooltip_key": "codex_consultants_group",
                        "audience": "Pour les consultants",
                        "lead": (
                            "Un plugin spécialisé pour créer des présentations et poursuivre "
                            "le travail sur les projets dans la durée."
                        ),
                        "description": (
                            "Clara réunit dans le dossier du projet les documents, notes, "
                            "entretiens et enregistrements, puis s'appuie sur ce contexte "
                            "pour créer ou mettre à jour des présentations, des notes de "
                            "synthèse et des dossiers d'aide à la décision."
                        ),
                        "proof": [
                            "Contexte du projet conservé dans la durée",
                            "Sources réunies dans un même espace de travail",
                            "Présentations, synthèses et dossiers de décision",
                        ],
                        "cta_label": "Découvrir Clara",
                        "icon": "/static/shared/clara/icon.svg",
                        "links": [
                            {
                                "label": "Clara",
                                "href": "/static/shared/clara/index.html",
                                "active": True,
                                "tooltip_key": "clara_plugin",
                                "public": True,
                            },
                        ],
                    },
                    {
                        "id": "lucia",
                        "title": "Pour les avocats indépendants",
                        "tooltip_key": "codex_lawyers_group",
                        "audience": "Pour les avocats indépendants",
                        "lead": (
                            "Un plugin spécialisé pour le travail juridique révisable, les "
                            "communications professionnelles et le site du cabinet."
                        ),
                        "description": (
                            "Lucia cadre et contrôle le travail juridique, prépare des "
                            "communications fondées sur des sources et crée le site "
                            "d’information du cabinet à partir de documents vérifiés."
                        ),
                        "proof": [
                            "Questions juridiques au périmètre défini",
                            "Communications professionnelles avec sources et approbations",
                            "Sites d’information construits sur des faits vérifiés",
                        ],
                        "cta_label": "Découvrir Lucia",
                        "icon": "/static/shared/lucia/icon.svg",
                        "links": [
                            {
                                "label": "Lucia",
                                "href": "/static/shared/lucia/index.html",
                                "active": True,
                                "tooltip_key": "lucia_plugin",
                                "public": True,
                            },
                        ],
                    },
                ],
            },
        ],
        "menu_links": [],
        "hero": {
            "id": "hero",
            "skip_label": "Aller au contenu principal",
            "plugins_label": "Plugins Mparanza",
            "eyebrow": "Plugins pour les professionnels",
            "headline": "L'IA apporte la puissance. La méthode apporte le contrôle.",
            "subheadline": (
                "Mparanza intègre des méthodes spécialisées dans des plugins pour le "
                "travail professionnel. Pour ChatGPT Work, Codex et Claude Cowork."
            ),
        },
        "harness": {
            "id": "method",
            "title": "La méthode transforme les capacités de l'IA en travail professionnel.",
            "description": (
                "L'IA peut raisonner, analyser et créer. Chaque plugin donne à ces "
                "capacités une méthode spécialisée : sources définies, étapes ordonnées, "
                "contrôles explicites, points de revue et livrables attendus. C'est cette "
                "méthode que nous appelons le contrôle."
            ),
            "layers": [
                {
                    "title": "Puissance",
                    "blurb": "Le modèle raisonne, analyse et crée.",
                },
                {
                    "title": "Méthode",
                    "blurb": "Le plugin définit les sources, les étapes et les critères professionnels.",
                },
                {
                    "title": "Contrôle",
                    "blurb": (
                        "Les contrôles, les points de revue et les livrables attendus "
                        "rendent le travail révisable."
                    ),
                },
            ],
        },
        "open_source": {
            "id": "open-source",
            "title": "Ouverts par conception.",
            "description": (
                "Clara, Vera et Lucia sont des plugins open source. Vous pouvez examiner "
                "leurs méthodes, leurs contrôles et leur code avant de les utiliser — "
                "et les adapter à votre travail."
            ),
            "links_label": "Informations open source",
            "links": [
                {
                    "label": "Examiner le code sur GitHub",
                    "href": "https://github.com/fabioannovazzi/app_files",
                },
                {
                    "label": "Lire la licence GNU AGPLv3",
                    "href": "https://github.com/fabioannovazzi/app_files/blob/main/LICENSE",
                },
            ],
        },
        "free": {
            "id": "free",
            "title": "Gratuits par conception.",
            "description": (
                "Clara, Vera et Lucia sont gratuites à installer et à utiliser. Nous accueillons "
                "volontiers les contributions à leur développement. Nous facturons nos "
                "prestations de conseil et de mise en œuvre, ainsi que nos services "
                "hébergés."
            ),
        },
        "security": {
            "id": "security",
            "title": "Sécurisés par conception.",
            "lead": (
                "Dans les flux ordinaires de Clara, Vera et Lucia, Mparanza ne reçoit pas le travail de vos clients."
            ),
            "description": (
                "Les workflows ordinaires des plugins fonctionnent dans l'environnement "
                "d'IA que vous choisissez. Les prompts, fichiers et livrables de vos "
                "clients ne transitent pas par Mparanza."
            ),
            "cta_label": "Voir comment vos données sont traitées",
            "cta_href": "/data-handling",
        },
        "compliance": {
            "id": "compliance",
            "title": "Conformes par conception.",
            "lead": "Le travail professionnel peut nécessiter que l'environnement d'IA choisi lise de vraies données clients.",
            "description": "Clara, Vera et Lucia n'anonymisent pas automatiquement les données. Elles peuvent utiliser Python localement pour filtrer ou agréger des informations lorsque cela est utile. Les données fournies au modèle sont traitées selon les conditions et les contrôles de l'environnement d'IA choisi par l'utilisateur.",
            "principles": [
                {
                    "title": "Utiliser Python localement lorsque c'est utile",
                    "blurb": "Le filtrage et l'agrégation peuvent s'exécuter sur votre ordinateur lorsqu'ils améliorent le travail. Il ne s'agit pas d'une anonymisation automatique.",
                },
                {
                    "title": "Les données réelles peuvent parvenir au modèle",
                    "blurb": "Noms, documents, texte original et faits propres au dossier peuvent entrer dans le contexte du modèle lorsque le travail professionnel l'exige.",
                },
                {
                    "title": "Deux catégories de traitement",
                    "blurb": "Les fonctions ordinaires des plugins utilisent l'environnement d'IA choisi par l'utilisateur. Les services hébergés par Mparanza ont un périmètre de traitement distinct.",
                },
            ],
            "closing": "Une règle pour Clara, Vera et Lucia. Aucune paperasse prompt par prompt.",
            "cta_label": "Voir comment vos données sont traitées",
            "cta_href": "/data-handling",
        },
        "bridge": {
            "id": "plugins",
            "title": "Plugins par conception.",
            "description": (
                "Mparanza, c'est Clara, Vera et Lucia : trois plugins qui intègrent des "
                "méthodes spécialisées pour trois métiers différents."
            ),
        },
    },
    "de": {
        "primary": {
            "title": "",
            "links": [],
        },
        "sections": [
            {
                "preserve_order": True,
                "groups": [
                    {
                        "id": "vera",
                        "title": "Für Steuerberaterinnen und Steuerberater",
                        "tooltip_key": "codex_accountants_group",
                        "audience": "Für Steuerberaterinnen und Steuerberater",
                        "lead": (
                            "Ein spezialisiertes Plugin für Mandantendateien, Buchungsprüfungen, "
                            "Abstimmungen und Berichte."
                        ),
                        "description": (
                            "Vera arbeitet direkt mit den Kanzleidateien. Sie übernimmt "
                            "Mandantenaufnahme und Stichproben, prüft Buchungen, stimmt "
                            "Unterlagen ab und erstellt Berichte oder steuerliche und "
                            "regulatorische Recherchen."
                        ),
                        "proof": [
                            "Von der Mandantenaufnahme bis zur Fachrecherche",
                            "Nachvollziehbare Prüfungen und Abstimmungen",
                            "Arbeitspapiere für die fachliche Prüfung",
                        ],
                        "cta_label": "Vera kennenlernen",
                        "icon": "/static/shared/vera/icon.svg",
                        "links": [
                            {
                                "label": "Vera",
                                "href": "/static/shared/vera/index.html",
                                "active": True,
                                "tooltip_key": "vera",
                                "public": True,
                            },
                        ],
                    },
                    {
                        "id": "clara",
                        "title": "Für Beraterinnen und Berater",
                        "tooltip_key": "codex_consultants_group",
                        "audience": "Für Beraterinnen und Berater",
                        "lead": (
                            "Ein spezialisiertes Plugin für Präsentationen und die fortlaufende "
                            "Arbeit an Projekten."
                        ),
                        "description": (
                            "Clara bündelt Dokumente, Notizen, Interviews und Aufzeichnungen "
                            "im Projektordner. Diesen Kontext nutzt sie, um Präsentationen, "
                            "Briefings und Entscheidungsvorlagen zu erstellen oder zu "
                            "überarbeiten."
                        ),
                        "proof": [
                            "Projektkontext bleibt langfristig verfügbar",
                            "Quellen gebündelt in einem Arbeitsbereich",
                            "Briefings, Präsentationen und Entscheidungsvorlagen",
                        ],
                        "cta_label": "Clara kennenlernen",
                        "icon": "/static/shared/clara/icon.svg",
                        "links": [
                            {
                                "label": "Clara",
                                "href": "/static/shared/clara/index.html",
                                "active": True,
                                "tooltip_key": "clara_plugin",
                                "public": True,
                            },
                        ],
                    },
                    {
                        "id": "lucia",
                        "title": "Für selbständige Anwälte",
                        "tooltip_key": "codex_lawyers_group",
                        "audience": "Für selbständige Anwälte",
                        "lead": (
                            "Ein spezialisiertes Plugin für überprüfbare Rechtsarbeit, "
                            "fachliche Kommunikation und die Kanzleiwebsite."
                        ),
                        "description": (
                            "Lucia strukturiert und prüft Rechtsarbeit, erstellt "
                            "quellengestützte Kommunikation und baut informative "
                            "Kanzleiwebsites aus geprüften Materialien."
                        ),
                        "proof": [
                            "Rechtsfragen mit festgelegtem Umfang",
                            "Fachliche Kommunikation mit Quellen und Freigaben",
                            "Informationswebsites auf Grundlage geprüfter Kanzleidaten",
                        ],
                        "cta_label": "Lucia kennenlernen",
                        "icon": "/static/shared/lucia/icon.svg",
                        "links": [
                            {
                                "label": "Lucia",
                                "href": "/static/shared/lucia/index.html",
                                "active": True,
                                "tooltip_key": "lucia_plugin",
                                "public": True,
                            },
                        ],
                    },
                ],
            },
        ],
        "menu_links": [],
        "hero": {
            "id": "hero",
            "skip_label": "Zum Hauptinhalt springen",
            "plugins_label": "Mparanza-Plugins",
            "eyebrow": "Plugins für professionelle Arbeit",
            "headline": "KI liefert die Leistung. Die Methode sorgt für Kontrolle.",
            "subheadline": (
                "Mparanza verankert fachliche Methoden in Plugins für professionelle "
                "Arbeit. Für ChatGPT Work, Codex und Claude Cowork."
            ),
        },
        "harness": {
            "id": "method",
            "title": "Die Methode macht KI-Fähigkeiten für professionelle Arbeit nutzbar.",
            "description": (
                "KI kann analysieren, Schlussfolgerungen ziehen und Inhalte erstellen. "
                "Jedes Plugin gibt diesen Fähigkeiten eine fachliche Methode: definierte "
                "Quellen, geordnete Schritte, explizite Prüfungen, Prüfpunkte und erwartete "
                "Ergebnisse. Diese Methode meinen wir, wenn wir von Kontrolle sprechen."
            ),
            "layers": [
                {
                    "title": "Leistung",
                    "blurb": (
                        "Das Modell analysiert, zieht Schlüsse und erstellt Inhalte."
                    ),
                },
                {
                    "title": "Methode",
                    "blurb": "Das Plugin legt Quellen, Schritte und fachliche Kriterien fest.",
                },
                {
                    "title": "Kontrolle",
                    "blurb": (
                        "Prüfungen, Prüfpunkte und erwartete Ergebnisse machen die Arbeit "
                        "nachvollziehbar."
                    ),
                },
            ],
        },
        "open_source": {
            "id": "open-source",
            "title": "Offen konzipiert.",
            "description": (
                "Clara, Vera und Lucia sind Open-Source-Plugins. Sie können Methoden, "
                "Kontrollen und Code vor der Verwendung prüfen und an Ihre Arbeit anpassen."
            ),
            "links_label": "Open-Source-Informationen",
            "links": [
                {
                    "label": "Quellcode auf GitHub prüfen",
                    "href": "https://github.com/fabioannovazzi/app_files",
                },
                {
                    "label": "GNU-AGPLv3-Lizenz lesen",
                    "href": "https://github.com/fabioannovazzi/app_files/blob/main/LICENSE",
                },
            ],
        },
        "free": {
            "id": "free",
            "title": "Kostenlos konzipiert.",
            "description": (
                "Clara, Vera und Lucia können kostenlos installiert und genutzt werden. Wir "
                "freuen uns über Beiträge zu ihrer Weiterentwicklung. Wir stellen "
                "Beratungs- und Implementierungsleistungen sowie gehostete Services "
                "in Rechnung."
            ),
        },
        "security": {
            "id": "security",
            "title": "Sicher konzipiert.",
            "lead": (
                "Bei normalen Abläufen von Clara, Vera und Lucia erhält Mparanza Ihre Mandantenarbeit nicht."
            ),
            "description": (
                "Normale Plugin-Abläufe laufen in der von Ihnen gewählten KI-Arbeitsumgebung. "
                "Prompts, Dateien und Ergebnisse Ihrer Mandanten laufen nicht über Mparanza."
            ),
            "cta_label": "Erfahren Sie, wie Ihre Daten verarbeitet werden",
            "cta_href": "/data-handling",
        },
        "compliance": {
            "id": "compliance",
            "title": "Für Compliance konzipiert.",
            "lead": "Professionelle Arbeit kann erfordern, dass die gewählte KI-Arbeitsumgebung echte Mandantendaten liest.",
            "description": "Clara, Vera und Lucia anonymisieren Daten nicht automatisch. Sie können Python lokal einsetzen, um Informationen zu filtern oder zu aggregieren, wenn dies nützlich ist. Daten, die dem Modell bereitgestellt werden, werden nach den Bedingungen und Kontrollen der vom Nutzer gewählten KI-Arbeitsumgebung verarbeitet.",
            "principles": [
                {
                    "title": "Python lokal einsetzen, wenn es nützt",
                    "blurb": "Filtern und Aggregieren kann auf Ihrem Computer erfolgen, wenn es die Arbeit verbessert. Das ist keine automatische Anonymisierung.",
                },
                {
                    "title": "Echte Daten können das Modell erreichen",
                    "blurb": "Namen, Dokumente, Originalformulierungen und Fallfakten können in den Modellkontext gelangen, wenn die professionelle Aufgabe sie benötigt.",
                },
                {
                    "title": "Zwei Verarbeitungskategorien",
                    "blurb": "Normale Plugin-Funktionen nutzen die vom Nutzer gewählte KI-Arbeitsumgebung. Mparanza-gehostete Dienste haben eine separate Verarbeitungsgrenze.",
                },
            ],
            "closing": "Eine Regel für Clara, Vera und Lucia. Kein Papierkram für jeden Prompt.",
            "cta_label": "Erfahren Sie, wie Ihre Daten verarbeitet werden",
            "cta_href": "/data-handling",
        },
        "bridge": {
            "id": "plugins",
            "title": "Als Plugins konzipiert.",
            "description": (
                "Mparanza, das sind Clara, Vera und Lucia: drei Plugins mit fachlichen "
                "Methoden für drei unterschiedliche Berufsgruppen."
            ),
        },
    },
    "es": {
        "primary": {
            "title": "",
            "links": [],
        },
        "sections": [
            {
                "preserve_order": True,
                "groups": [
                    {
                        "id": "vera",
                        "title": "Para profesionales contables",
                        "tooltip_key": "codex_accountants_group",
                        "audience": "Para profesionales contables",
                        "lead": (
                            "Un plugin especializado para expedientes de clientes, controles "
                            "contables, conciliaciones e informes."
                        ),
                        "description": (
                            "Vera trabaja directamente con los archivos del despacho. "
                            "Gestiona la incorporación de nuevos clientes y el muestreo "
                            "de diarios, comprueba asientos, concilia registros y prepara "
                            "informes o investigaciones fiscales y regulatorias."
                        ),
                        "proof": [
                            "De la incorporación de clientes a la investigación regulatoria",
                            "Comprobaciones y conciliaciones revisables",
                            "Papeles de trabajo listos para la revisión profesional",
                        ],
                        "cta_label": "Descubrir Vera",
                        "icon": "/static/shared/vera/icon.svg",
                        "links": [
                            {
                                "label": "Vera",
                                "href": "/static/shared/vera/index.html",
                                "active": True,
                                "tooltip_key": "vera",
                                "public": True,
                            },
                        ],
                    },
                    {
                        "id": "clara",
                        "title": "Para consultores",
                        "tooltip_key": "codex_consultants_group",
                        "audience": "Para consultores",
                        "lead": (
                            "Un plugin especializado para presentaciones y trabajo continuo "
                            "en proyectos."
                        ),
                        "description": (
                            "Clara reúne documentos, notas, entrevistas y grabaciones en "
                            "la carpeta del proyecto y usa ese contexto para crear o revisar "
                            "presentaciones, informes breves y documentos para la toma de "
                            "decisiones."
                        ),
                        "proof": [
                            "Contexto del proyecto conservado",
                            "Evidencias reunidas en un solo espacio de trabajo",
                            "Informes, presentaciones y documentos de decisión",
                        ],
                        "cta_label": "Descubrir Clara",
                        "icon": "/static/shared/clara/icon.svg",
                        "links": [
                            {
                                "label": "Clara",
                                "href": "/static/shared/clara/index.html",
                                "active": True,
                                "tooltip_key": "clara_plugin",
                                "public": True,
                            },
                        ],
                    },
                    {
                        "id": "lucia",
                        "title": "Para abogados independientes",
                        "tooltip_key": "codex_lawyers_group",
                        "audience": "Para abogados independientes",
                        "lead": (
                            "Un plugin especializado para trabajo jurídico revisable, "
                            "comunicaciones profesionales y el sitio del despacho."
                        ),
                        "description": (
                            "Lucia estructura y revisa el trabajo jurídico, prepara "
                            "comunicaciones basadas en fuentes y crea sitios informativos "
                            "del despacho a partir de materiales verificados."
                        ),
                        "proof": [
                            "Preguntas jurídicas con un alcance definido",
                            "Comunicaciones profesionales con fuentes y aprobaciones",
                            "Sitios informativos construidos sobre hechos verificados",
                        ],
                        "cta_label": "Descubrir Lucia",
                        "icon": "/static/shared/lucia/icon.svg",
                        "links": [
                            {
                                "label": "Lucia",
                                "href": "/static/shared/lucia/index.html",
                                "active": True,
                                "tooltip_key": "lucia_plugin",
                                "public": True,
                            },
                        ],
                    },
                ],
            },
        ],
        "menu_links": [],
        "hero": {
            "id": "hero",
            "skip_label": "Ir al contenido principal",
            "plugins_label": "Plugins de Mparanza",
            "eyebrow": "Plugins para el trabajo profesional",
            "headline": "La IA aporta la potencia. El método aporta el control.",
            "subheadline": (
                "Mparanza incorpora métodos especializados en plugins para el trabajo "
                "profesional. Para ChatGPT Work, Codex y Claude Cowork."
            ),
        },
        "harness": {
            "id": "method",
            "title": "El método convierte la capacidad de la IA en trabajo profesional.",
            "description": (
                "La IA puede razonar, analizar y crear. Cada plugin da a esas capacidades "
                "un método especializado: fuentes definidas, pasos ordenados, controles "
                "explícitos, puntos de revisión y resultados esperados. Ese método es lo "
                "que entendemos por control."
            ),
            "layers": [
                {
                    "title": "Potencia",
                    "blurb": "El modelo razona, analiza y crea.",
                },
                {
                    "title": "Método",
                    "blurb": "El plugin define las fuentes, los pasos y los criterios profesionales.",
                },
                {
                    "title": "Control",
                    "blurb": (
                        "Los controles, los puntos de revisión y los resultados esperados "
                        "hacen que el trabajo sea revisable."
                    ),
                },
            ],
        },
        "open_source": {
            "id": "open-source",
            "title": "Abiertos por diseño.",
            "description": (
                "Clara, Vera y Lucia son plugins open source. Puedes examinar "
                "los métodos, los controles y el código antes de usarlos, y adaptarlos "
                "a tu trabajo."
            ),
            "links_label": "Información sobre código abierto",
            "links": [
                {
                    "label": "Examinar el código fuente en GitHub",
                    "href": "https://github.com/fabioannovazzi/app_files",
                },
                {
                    "label": "Leer la licencia GNU AGPLv3",
                    "href": "https://github.com/fabioannovazzi/app_files/blob/main/LICENSE",
                },
            ],
        },
        "free": {
            "id": "free",
            "title": "Gratuitos por diseño.",
            "description": (
                "Clara, Vera y Lucia se pueden instalar y usar gratuitamente. Agradecemos las "
                "contribuciones a su desarrollo. Cobramos por la consultoría, la "
                "implementación y los servicios alojados."
            ),
        },
        "security": {
            "id": "security",
            "title": "Seguros por diseño.",
            "lead": (
                "En los flujos ordinarios de Clara, Vera y Lucia, Mparanza no recibe el trabajo de tus clientes."
            ),
            "description": (
                "Los flujos ordinarios de los plugins funcionan dentro del entorno de "
                "IA que elijas. Los prompts, archivos y resultados de tus clientes no "
                "pasan por Mparanza."
            ),
            "cta_label": "Ver cómo se tratan tus datos",
            "cta_href": "/data-handling",
        },
        "compliance": {
            "id": "compliance",
            "title": "Conformes por diseño.",
            "lead": (
                "El trabajo profesional puede requerir que el entorno de IA elegido lea "
                "datos reales de clientes."
            ),
            "description": (
                "Clara, Vera y Lucia no anonimizan los datos automáticamente. Pueden usar Python "
                "en local para filtrar o agregar información cuando resulte útil. Los datos "
                "facilitados al modelo se tratan según las condiciones y los controles del "
                "entorno de IA elegido por el usuario."
            ),
            "principles": [
                {
                    "title": "Usa Python en local cuando resulte útil",
                    "blurb": (
                        "El filtrado y la agregación pueden realizarse en tu ordenador "
                        "cuando mejoran el trabajo. No son anonimización automática."
                    ),
                },
                {
                    "title": "Los datos reales pueden llegar al modelo",
                    "blurb": (
                        "Los nombres, documentos, el idioma original y los hechos del caso "
                        "pueden entrar en el contexto del modelo cuando la tarea profesional "
                        "los necesita."
                    ),
                },
                {
                    "title": "Dos categorías de tratamiento",
                    "blurb": (
                        "Las funciones ordinarias de los plugins usan el entorno de IA "
                        "elegido por el usuario. Los servicios alojados por Mparanza "
                        "constituyen un "
                        "límite de tratamiento separado."
                    ),
                },
            ],
            "closing": (
                "Una política para Clara, Vera y Lucia. Sin documentación para cada prompt."
            ),
            "cta_label": "Ver cómo se tratan tus datos",
            "cta_href": "/data-handling",
        },
        "bridge": {
            "id": "plugins",
            "title": "Plugins por diseño.",
            "description": (
                "Mparanza es Clara, Vera y Lucia: tres plugins que incorporan métodos "
                "especializados para tres profesiones distintas."
            ),
        },
    },
}

LANDING_PRODUCT_RANK = {
    product_id: rank for rank, product_id in enumerate(("clara", "vera", "lucia"))
}


def _render_legal_page(request: Request, slug: str) -> Response:
    if templates is None:  # pragma: no cover - defensive fallback
        raise HTTPException(
            status_code=503, detail="Templating support is not available."
        )
    response = templates.TemplateResponse(
        request,
        "legal_page.html",
        _template_context(
            page=get_legal_page(slug),
            active_legal_page=slug,
            copy={},
            lang="en",
        ),
    )
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


@site_router.get("/zero-retention", include_in_schema=False)
def zero_retention_page(request: Request) -> Response:
    return _render_legal_page(request, "zero-retention")


@site_router.get("/privacy", include_in_schema=False)
def privacy_page_redirect() -> RedirectResponse:
    return RedirectResponse(
        url="/zero-retention",
        status_code=status.HTTP_308_PERMANENT_REDIRECT,
    )


@site_router.get("/terms", include_in_schema=False)
def terms_page(request: Request) -> Response:
    return _render_legal_page(request, "terms")


@site_router.get("/support", include_in_schema=False)
def support_page(request: Request) -> Response:
    return _render_legal_page(request, "support")


@site_router.get("/data-handling", include_in_schema=False)
def data_handling_page(request: Request) -> Response:
    """Render Mparanza's localized public data-handling position."""

    lang = resolve_language(request)
    if templates is None:  # pragma: no cover - defensive fallback
        raise HTTPException(
            status_code=503, detail="Templating support is not available."
        )
    response = templates.TemplateResponse(
        request,
        "data_handling.html",
        _template_context(
            page=get_data_handling_content(lang),
            privacy_register=get_public_privacy_register(lang),
            copy={},
            lang=lang,
            language_labels=LANDING_LANGUAGE_LABELS,
            language_names=LANGUAGE_LABELS,
            language_order=LANGUAGE_ORDER,
            auth_enabled=False,
            google_client_id="",
        ),
    )
    response.headers["Cache-Control"] = "public, max-age=300"
    if lang != request.cookies.get("lang"):
        response.set_cookie("lang", lang, max_age=30 * 24 * 60 * 60, httponly=False)
    return response


@site_router.get("/", include_in_schema=False)
def landing_page(request: Request) -> Any:
    try:
        lang = resolve_language(request)
    except Exception:  # pragma: no cover - fallback if geolocation fails unexpectedly
        lang = "en"
    landing_page_content = _get_landing_page_content(lang)
    primary_section = landing_page_content["primary"]
    other_sections = landing_page_content["sections"]
    menu_links = landing_page_content["menu_links"]
    if templates is None:  # pragma: no cover - defensive fallback
        raise HTTPException(
            status_code=503, detail="Templating support is not available."
        )
    tooltip_map = TOOLTIP_CONTENT.get(lang, TOOLTIP_CONTENT["en"])
    response = templates.TemplateResponse(
        request,
        "index.html",
        _template_context(
            primary_section=primary_section,
            sections=other_sections,
            menu_links=menu_links,
            hero=landing_page_content["hero"],
            harness=landing_page_content["harness"],
            open_source=landing_page_content["open_source"],
            free=landing_page_content["free"],
            security=landing_page_content["security"],
            compliance=landing_page_content["compliance"],
            bridge=landing_page_content["bridge"],
            copy=get_page_copy("landing", lang),
            lang=lang,
            language_labels=LANDING_LANGUAGE_LABELS,
            language_names=LANGUAGE_LABELS,
            language_order=LANGUAGE_ORDER,
            language_tooltips=tooltip_map,
            beta_links=BETA_LINKS,
            auth_enabled=False,
            google_client_id="",
        ),
    )
    cookie_lang = request.cookies.get("lang")
    if lang != cookie_lang:
        response.set_cookie("lang", lang, max_age=30 * 24 * 60 * 60, httponly=False)
    return response


def create_app() -> FastAPI:
    app = FastAPI(
        title="Mparanza Hosted Services",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(get_auth_config().trusted_hosts),
    )

    @app.middleware("http")
    async def _attach_session_context(request: Request, call_next):
        session_ctx = build_session_context(request)
        with use_session_context(session_ctx):
            response = await call_next(request)
        return response

    app.mount("/static", StaticFiles(directory="static"), name="static")
    app.include_router(auth_router)
    app.include_router(auth_site_router)
    app.include_router(site_router)
    app.include_router(hosted_interviews_site_router)
    app.include_router(hosted_interviews_public_router)
    app.include_router(change_requests_router)
    protected_site_routers = [
        (
            case_notes_voice_site_router,
            [Depends(require_site_permission_for_request)],
        ),
    ]
    for protected_router, dependencies in protected_site_routers:
        app.include_router(protected_router, dependencies=list(dependencies))
    app.include_router(hosted_interviews_admin_router)
    app.include_router(attribute_reporting_router)
    app.include_router(
        case_notes_voice_router,
        dependencies=[Depends(require_site_permission_for_request)],
    )

    @app.on_event("startup")
    async def _startup_cleanup() -> None:
        process_pending_notifications()
        _start_session_cleanup()
        start_voice_retention_cleanup()

    @app.on_event("shutdown")
    async def _shutdown_cleanup() -> None:
        stop_voice_retention_cleanup()
        _stop_session_cleanup()

    async def _render_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        if exc.status_code == status.HTTP_403_FORBIDDEN and templates is not None:
            lang = request.query_params.get("lang") or resolve_language(request)
            detail = exc.detail
            page_key = detail.get("page") if isinstance(detail, dict) else None
            clara_access_required = page_key == CLARA_PERMISSION_KEY
            clara_copy = CLARA_FORBIDDEN_COPY.get(lang, CLARA_FORBIDDEN_COPY["en"])
            context = {
                "request": request,
                "lang": lang,
                "message": (
                    clara_copy["message"]
                    if clara_access_required
                    else _forbidden_message(detail)
                ),
                "clara_access_required": clara_access_required,
                "forbidden_title": clara_copy["title"],
                "return_home_label": clara_copy["return_home_label"],
            }
            return templates.TemplateResponse(
                "forbidden.html", context, status_code=exc.status_code
            )
        if (
            exc.status_code == status.HTTP_404_NOT_FOUND
            and templates is not None
            and _request_prefers_html(request)
        ):
            return templates.TemplateResponse(
                "not_found.html",
                _not_found_context(request, exc.detail),
                status_code=exc.status_code,
            )
        return await http_exception_handler(request, exc)

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> Response:
        return await _render_http_exception(request, exc)

    @app.exception_handler(StarletteHTTPException)
    async def _starlette_http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        return await _render_http_exception(request, exc)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        error_id = uuid.uuid4().hex[:12]
        LOGGER.exception(
            "Unhandled API exception error_id=%s method=%s path=%s has_query=%s",
            error_id,
            request.method,
            request.url.path,
            bool(request.url.query),
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": f"Internal server error (error_id={error_id})",
                "error_id": error_id,
            },
        )

    return app


app = create_app()


def _order_links_by_reference(
    links: Sequence[Dict[str, Any]],
    reference_links: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Order links to match the reference href sequence."""
    if not links:
        return []
    if not reference_links:
        return list(links)
    remaining = list(links)
    ordered: List[Dict[str, Any]] = []
    for ref in reference_links:
        if not isinstance(ref, dict):
            continue
        ref_href = ref.get("href")
        if not ref_href:
            continue
        for index, link in enumerate(remaining):
            if not isinstance(link, dict):
                continue
            if link.get("href") == ref_href:
                ordered.append(link)
                remaining.pop(index)
                break
    ordered.extend(remaining)
    return ordered


def _get_landing_page_content(lang: str) -> Dict[str, Any]:
    content = LANDING_CONTENT.get(lang) or LANDING_CONTENT["en"]
    sections = []
    for section in content.get("sections", []):
        copied_section = {**section, "links": list(section.get("links", []))}
        if section.get("groups"):
            copied_groups = [
                {**group, "links": list(group.get("links", []))}
                for group in section.get("groups", [])
            ]
            copied_section["groups"] = sorted(
                copied_groups,
                key=lambda group: LANDING_PRODUCT_RANK.get(
                    group["id"], len(LANDING_PRODUCT_RANK)
                ),
            )
        sections.append(copied_section)
    if lang != "en":
        reference_sections = LANDING_CONTENT["en"].get("sections", [])
        for section, reference in zip(sections, reference_sections):
            if section.get("preserve_order"):
                continue
            section["links"] = _order_links_by_reference(
                section.get("links", []),
                reference.get("links", []) if isinstance(reference, dict) else [],
            )
    return {
        "primary": content.get("primary"),
        "sections": sections,
        "menu_links": content.get("menu_links", []),
        "hero": content.get("hero"),
        "harness": content.get("harness", {}),
        "open_source": content.get("open_source", {}),
        "free": content.get("free", {}),
        "security": content.get("security", {}),
        "compliance": content.get("compliance", {}),
        "bridge": content.get("bridge", {}),
    }
