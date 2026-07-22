from __future__ import annotations

# notifier.py
import logging
import re
from typing import Mapping

from modules.notifications.outbox import enqueue_email, process_email_outbox
from modules.notifications.resend_client import (
    ResendAuthenticationError,
    is_resend_configured,
    send_email,
)
from modules.utilities.ui_notifier import FastAPINotifier, Notifier

__all__ = ["notify_failed", "notify_finished", "process_pending_notifications"]

LOGGER = logging.getLogger(__name__)
_DEFAULT_NOTIFIER = FastAPINotifier(logger=LOGGER)

# ---------- client-side cues ---------------------------------------------
_DING_WAV_B64 = (
    "data:audio/wav;base64,"
    "UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQgAAAAA"  # 0.2-s click
)


def _pretty(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h} h {m:02d} min"
    return f"{m} min {s:02d} s"


def _ping_browser(notifier: Notifier, label: str = "Validation") -> None:
    notifier.notify("success", f"✅ {label} finished", {"event": "toast", "icon": "🎉"})
    notifier.notify(
        "info",
        f"""
        <script>
          document.title='✅ {label} ready!';
        </script>
        """,
        {"format": "markdown", "unsafe_html": True},
    )


# ---------- (optional) one-shot e-mail -----------------------------------

LANG_ALIASES = {
    "eng": "en",
    "en": "en",
    "english": "en",
    "ita": "it",
    "it": "it",
    "italian": "it",
    "italiano": "it",
    "fra": "fr",
    "fr": "fr",
    "french": "fr",
    "français": "fr",
    "francais": "fr",
    "deu": "de",
    "de": "de",
    "german": "de",
    "deutsch": "de",
    "spa": "es",
    "es": "es",
    "spanish": "es",
    "español": "es",
    "espanol": "es",
}

RESULTS_CTA_LABELS = {
    "en": "Open results",
    "it": "Apri i risultati",
    "fr": "Ouvrir les résultats",
    "de": "Ergebnisse öffnen",
    "es": "Abrir resultados",
}
RESULTS_LINK_LABELS = {"es": "Resultados"}

SUCCESS_TEMPLATES = {
    "entries": {
        "en": {
            "subject": "Your journal entry check results are ready",
            "body": (
                "Hi there,\n\n"
                "✅  Your journal entry check finished just now (total time: {pretty}).\n\n"
                "— This is a one-time notification you asked for. —\n"
                "Your email address will be deleted once you close the session.\n\n"
                "Thanks for using our Entry Check Tool!\n"
            ),
        },
        "it": {
            "subject": "I risultati del controllo delle scritture sono pronti",
            "body": (
                "Ciao,\n\n"
                "✅ Il controllo delle scritture si è concluso ora (durata totale: {pretty}).\n\n"
                "— Questa è una notifica una tantum richiesta da te. —\n"
                "Il tuo indirizzo email verrà eliminato alla chiusura della sessione.\n\n"
                "Grazie per aver usato il nostro tool di verifica delle scritture!\n"
            ),
        },
        "fr": {
            "subject": "Vos résultats de contrôle des écritures sont prêts",
            "body": (
                "Bonjour,\n\n"
                "✅ La vérification des écritures vient de se terminer (durée totale : {pretty}).\n\n"
                "— Ceci est une notification ponctuelle que vous aviez demandée. —\n"
                "Votre adresse e-mail sera supprimée lorsque vous fermerez la session.\n\n"
                "Merci d'utiliser notre outil de contrôle des écritures !\n"
            ),
        },
        "de": {
            "subject": "Ihre Journalprüfung ist abgeschlossen",
            "body": (
                "Hallo,\n\n"
                "✅ Ihre Buchungsprüfung ist soeben abgeschlossen (Gesamtdauer: {pretty}).\n\n"
                "— Dies ist die einmalige Benachrichtigung, die Sie angefordert haben. —\n"
                "Ihre E-Mail-Adresse wird gelöscht, sobald Sie die Sitzung schließen.\n\n"
                "Vielen Dank, dass Sie unser Entry-Check-Tool nutzen!\n"
            ),
        },
        "es": {
            "subject": "Los resultados de la revisión de asientos están listos",
            "body": (
                "Hola,\n\n"
                "✅ La revisión de asientos acaba de finalizar (duración total: {pretty}).\n\n"
                "— Esta es la notificación única que solicitaste. —\n"
                "Tu dirección de correo electrónico se eliminará cuando cierres la sesión.\n\n"
                "¡Gracias por utilizar nuestra herramienta de revisión de asientos!\n"
            ),
        },
    },
    "statements": {
        "en": {
            "subject": "Your reconciliation results are ready",
            "body": (
                "Hi there,\n\n"
                "✅  Your bank statement reconciliation check finished just now (total time: {pretty}).\n\n"
                "— This is a one-time notification you asked for. —\n"
                "Your email address will be deleted once you close the session.\n\n"
                "Thanks for using our Bank Statement Reconciliation Tool!\n"
            ),
        },
        "it": {
            "subject": "I risultati della riconciliazione sono pronti",
            "body": (
                "Ciao,\n\n"
                "✅ La riconciliazione degli estratti conto si è conclusa ora (durata totale: {pretty}).\n\n"
                "— Questa è una notifica una tantum richiesta da te. —\n"
                "L'indirizzo email verrà eliminato alla chiusura della sessione.\n\n"
                "Grazie per aver usato il nostro tool di riconciliazione!\n"
            ),
        },
        "fr": {
            "subject": "Vos résultats de rapprochement sont prêts",
            "body": (
                "Bonjour,\n\n"
                "✅ Le rapprochement bancaire vient de se terminer (durée totale : {pretty}).\n\n"
                "— Ceci est une notification ponctuelle que vous aviez demandée. —\n"
                "Votre adresse e-mail sera supprimée lorsque vous fermerez la session.\n\n"
                "Merci d'utiliser notre outil de rapprochement bancaire !\n"
            ),
        },
        "de": {
            "subject": "Ihre Kontoabstimmung ist abgeschlossen",
            "body": (
                "Hallo,\n\n"
                "✅ Ihre Kontoabrechnungsabstimmung wurde soeben abgeschlossen (Gesamtdauer: {pretty}).\n\n"
                "— Dies ist die einmalige Benachrichtigung, die Sie angefordert haben. —\n"
                "Ihre E-Mail-Adresse wird gelöscht, sobald Sie die Sitzung schließen.\n\n"
                "Vielen Dank, dass Sie unser Abstimmungs-Tool nutzen!\n"
            ),
        },
        "es": {
            "subject": "Los resultados de la conciliación están listos",
            "body": (
                "Hola,\n\n"
                "✅ La conciliación bancaria acaba de finalizar (duración total: {pretty}).\n\n"
                "— Esta es la notificación única que solicitaste. —\n"
                "Tu dirección de correo electrónico se eliminará cuando cierres la sesión.\n\n"
                "¡Gracias por utilizar nuestra herramienta de conciliación bancaria!\n"
            ),
        },
    },
    "report": {
        "en": {
            "subject": "Your report is ready",
            "body": (
                "Hi there,\n\n"
                "✅  Your report run finished just now (total time: {pretty}).\n\n"
                "— This is a one-time notification you asked for. —\n"
                "Your email address will be deleted once you close the session.\n\n"
                "Thanks for using our Report Builder Tool!\n"
            ),
        },
        "es": {
            "subject": "Tu informe está listo",
            "body": (
                "Hola,\n\n"
                "✅ El informe acaba de generarse (duración total: {pretty}).\n\n"
                "— Esta es la notificación única que solicitaste. —\n"
                "Tu dirección de correo electrónico se eliminará cuando cierres la sesión.\n\n"
                "¡Gracias por utilizar nuestra herramienta de creación de informes!\n"
            ),
        },
    },
    "deck_ocr": {
        "en": {
            "subject": "Your slide OCR results are ready",
            "body": (
                "Hi there,\n\n"
                "✅  Your deck OCR build finished just now (total time: {pretty}).\n\n"
                "You can reopen the slide editor to continue working.\n"
            ),
        },
        "es": {
            "subject": "Los resultados del OCR de tus diapositivas están listos",
            "body": (
                "Hola,\n\n"
                "✅ El procesamiento OCR de la presentación acaba de finalizar "
                "(duración total: {pretty}).\n\n"
                "Puedes volver a abrir el editor de diapositivas para continuar.\n"
            ),
        },
    },
    "deck_processing": {
        "en": {
            "subject": "Your uploaded PDF deck has been processed",
            "body": (
                "Hi there,\n\n"
                "✅ Your uploaded PDF deck has been processed (total time: {pretty}).\n\n"
                "You can reopen the slide editor to continue working.\n"
            ),
        },
        "es": {
            "subject": "Tu presentación en PDF se ha procesado",
            "body": (
                "Hola,\n\n"
                "✅ La presentación en PDF se ha procesado (duración total: {pretty}).\n\n"
                "Puedes volver a abrir el editor de diapositivas para continuar.\n"
            ),
        },
    },
    "default": {
        "en": {
            "subject": "Your results are ready",
            "body": (
                "Hi there,\n\n"
                "✅ The process finished just now (total time: {pretty}).\n\n"
                "Thanks for using our tools!\n"
            ),
        },
        "es": {
            "subject": "Tus resultados están listos",
            "body": (
                "Hola,\n\n"
                "✅ El proceso acaba de finalizar (duración total: {pretty}).\n\n"
                "¡Gracias por utilizar nuestras herramientas!\n"
            ),
        },
    },
}

ERROR_TEMPLATES = {
    "entries": {
        "en": {
            "subject": "Issue with your journal entry check",
            "body": (
                "Hi there,\n\n"
                "❌  Your journal entry check stopped due to an error. "
                "Partial results are available for download."
            ),
        },
        "it": {
            "subject": "Problema con il controllo delle scritture",
            "body": (
                "Ciao,\n\n"
                "❌ Il controllo delle scritture si è interrotto a causa di un errore. "
                "Puoi scaricare i risultati parziali."
            ),
        },
        "fr": {
            "subject": "Problème lors du contrôle des écritures",
            "body": (
                "Bonjour,\n\n"
                "❌ Le contrôle des écritures s'est arrêté en raison d'une erreur. "
                "Les résultats partiels sont disponibles au téléchargement."
            ),
        },
        "de": {
            "subject": "Problem bei der Journalprüfung",
            "body": (
                "Hallo,\n\n"
                "❌ Die Journalprüfung wurde aufgrund eines Fehlers gestoppt. "
                "Teilresultate stehen zum Download bereit."
            ),
        },
        "es": {
            "subject": "Problema con la revisión de asientos",
            "body": (
                "Hola,\n\n"
                "❌ La revisión de asientos se detuvo debido a un error. "
                "Puedes descargar los resultados parciales."
            ),
        },
    },
    "statements": {
        "en": {
            "subject": "Issue with your statements reconciliation check",
            "body": (
                "Hi there,\n\n"
                "❌  Your statements reconciliation check stopped due to an error. "
                "Partial results are available for download."
            ),
        },
        "it": {
            "subject": "Problema con la riconciliazione degli estratti conto",
            "body": (
                "Ciao,\n\n"
                "❌ La riconciliazione degli estratti conto si è interrotta a causa di un errore. "
                "Sono disponibili risultati parziali da scaricare."
            ),
        },
        "fr": {
            "subject": "Problème lors du rapprochement bancaire",
            "body": (
                "Bonjour,\n\n"
                "❌ Le rapprochement bancaire s'est arrêté en raison d'une erreur. "
                "Des résultats partiels sont disponibles en téléchargement."
            ),
        },
        "de": {
            "subject": "Problem bei der Kontoabstimmung",
            "body": (
                "Hallo,\n\n"
                "❌ Die Kontoabstimmung wurde aufgrund eines Fehlers gestoppt. "
                "Teilresultate können heruntergeladen werden."
            ),
        },
        "es": {
            "subject": "Problema con la conciliación bancaria",
            "body": (
                "Hola,\n\n"
                "❌ La conciliación bancaria se detuvo debido a un error. "
                "Puedes descargar los resultados parciales."
            ),
        },
    },
    "default": {
        "en": {
            "subject": "Processing issue",
            "body": "Hi there,\n\n❌ The process stopped due to an error. Partial results may be available.",
        },
        "es": {
            "subject": "Problema de procesamiento",
            "body": "Hola,\n\n❌ El proceso se detuvo debido a un error. Puede haber resultados parciales disponibles.",
        },
    },
    "deck_ocr": {
        "en": {
            "subject": "Issue with your slide OCR request",
            "body": (
                "Hi there,\n\n"
                "❌  Your deck OCR build stopped due to an error. "
                "Please retry from the slide editor."
            ),
        },
        "es": {
            "subject": "Problema con la solicitud de OCR de diapositivas",
            "body": (
                "Hola,\n\n"
                "❌ El procesamiento OCR de la presentación se detuvo debido a un error. "
                "Vuelve a intentarlo desde el editor de diapositivas."
            ),
        },
    },
    "deck_processing": {
        "en": {
            "subject": "Issue with your uploaded PDF deck",
            "body": (
                "Hi there,\n\n"
                "❌ Your uploaded PDF deck processing stopped due to an error. "
                "Please retry from the slide editor."
            ),
        },
        "es": {
            "subject": "Problema con la presentación en PDF",
            "body": (
                "Hola,\n\n"
                "❌ El procesamiento de la presentación en PDF se detuvo debido a un error. "
                "Vuelve a intentarlo desde el editor de diapositivas."
            ),
        },
    },
}


def _resolve_language(session_data: Mapping[str, str]) -> str:
    raw = session_data.get("notify_lang") or session_data.get("language") or ""
    return LANG_ALIASES.get(raw.strip().lower(), "en")


def _get_template(
    step: str, lang: str, catalog: Mapping[str, Mapping[str, Mapping[str, str]]]
) -> Mapping[str, str]:
    bundle = catalog.get(step) or catalog.get("default", {})
    template = bundle.get(lang) or bundle.get("en")
    if not template:
        template = catalog["default"]["en"]
    return template


def _send_email(
    dest: str, pretty: str, step: str, lang: str, link: str | None = None
) -> None:
    """Send a success notification email."""
    recipients = _normalize_destinations(dest)
    if not recipients:
        return
    if not is_resend_configured():
        LOGGER.debug("Skipping notification email: Resend is not configured.")
        return
    template = _get_template(step, lang, SUCCESS_TEMPLATES)
    subject = template["subject"]
    body = template["body"].format(pretty=pretty)
    if link:
        link_label = RESULTS_LINK_LABELS.get(lang, "Results")
        body += f"\n{link_label}: {link}\n"
    notification_id = enqueue_email(
        recipients=recipients,
        subject=subject,
        body=body,
        cta_label=RESULTS_CTA_LABELS.get(lang, RESULTS_CTA_LABELS["en"]),
        cta_url=link,
    )
    if notification_id:
        process_pending_notifications(notification_id=notification_id)


def _send_error_email(dest: str, step: str, lang: str, link: str | None = None) -> None:
    """Send an error notification email."""
    recipients = _normalize_destinations(dest)
    if not recipients:
        return
    if not is_resend_configured():
        LOGGER.debug("Skipping error notification email: Resend is not configured.")
        return
    template = _get_template(step, lang, ERROR_TEMPLATES)
    subject = template["subject"]
    body = template["body"]
    if link:
        link_label = RESULTS_LINK_LABELS.get(lang, "Results")
        body += f"\n{link_label}: {link}\n"
    notification_id = enqueue_email(
        recipients=recipients,
        subject=subject,
        body=body,
        cta_label=RESULTS_CTA_LABELS.get(lang, RESULTS_CTA_LABELS["en"]),
        cta_url=link,
    )
    if notification_id:
        process_pending_notifications(notification_id=notification_id)


def _normalize_destinations(raw: str | None) -> list[str]:
    cleaned = str(raw or "").strip()
    if not cleaned:
        return []
    parts = [token.strip() for token in re.split(r"[;,]", cleaned) if token.strip()]
    return parts


def _deliver_outbox_email(
    recipients: list[str],
    subject: str,
    body: str,
    cta_label: str | None,
    cta_url: str | None,
) -> bool:
    try:
        return send_email(
            recipients,
            subject,
            body,
            cta_label=cta_label,
            cta_url=cta_url,
        )
    except ResendAuthenticationError:
        LOGGER.warning("Notification email skipped: Resend authentication failed.")
        return False


def process_pending_notifications(
    *, limit: int = 50, notification_id: str | None = None
) -> int:
    """Deliver pending emails from the durable notification outbox."""

    if not is_resend_configured():
        LOGGER.debug("Skipping notification outbox flush: Resend is not configured.")
        return 0
    return process_email_outbox(
        _deliver_outbox_email,
        limit=limit,
        notification_id=notification_id,
    )


# ---------- public API ----------------------------------------------------


def notify_finished(
    elapsed_sec: float,
    step: str,
    session_data: Mapping[str, str],
    notifier: Notifier | None = None,
) -> None:
    """Call once at the end of the job; elapsed_sec is run-time in seconds.

    ``session_data`` should provide a ``notify_email`` key when notifications are desired.
    """
    label_map = {
        "report": "reportBuilder",
        "entries": "Entry check",
        "statements": "reconciliation",
        "deck_ocr": "Deck OCR",
        "deck_processing": "Deck processing",
    }
    notify = notifier or _DEFAULT_NOTIFIER
    _ping_browser(notify, label_map.get(step, step.capitalize()))
    pretty = _pretty(elapsed_sec)

    lang = _resolve_language(session_data)
    email = session_data.get("notify_email", "")
    if not email:
        LOGGER.warning(
            "Notification skipped: missing notify_email for step '%s'.", step
        )
        return
    if not is_resend_configured():
        LOGGER.warning("Notification skipped for %s: Resend not configured.", step)
        return
    _send_email(email, pretty, step, lang, session_data.get("job_link"))


def notify_failed(
    step: str, session_data: Mapping[str, str], notifier: Notifier | None = None
) -> None:
    """Notify the user that the job failed but partial results exiui."""
    notify = notifier or _DEFAULT_NOTIFIER
    email = session_data.get("notify_email", "")
    lang = _resolve_language(session_data)
    notify.error("Notification failed.", step=step)
    if email:
        _send_error_email(email, step, lang, session_data.get("job_link"))
