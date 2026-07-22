from __future__ import annotations

import logging
from enum import Enum


class MismatchSeverity(str, Enum):
    """Severity levels for journal entry mismatches."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class BeneficiaryCheckMode(str, Enum):
    """How beneficiary/payee information should be handled."""

    OFF = "off"
    EXTRACT_ONLY = "extract_only"
    COMPARE = "compare"


LANGUAGE_ALIASES: dict[str, str] = {
    "en": "eng",
    "eng": "eng",
    "english": "eng",
    "it": "ita",
    "ita": "ita",
    "italian": "ita",
    "fr": "fra",
    "fra": "fra",
    "french": "fra",
    "de": "deu",
    "deu": "deu",
    "german": "deu",
    "es": "spa",
    "spa": "spa",
    "spanish": "spa",
    "español": "spa",
    "espanol": "spa",
}

LANGUAGE_NAMES: dict[str, str] = {
    "eng": "English",
    "ita": "Italian",
    "fra": "French",
    "deu": "German",
    "spa": "Spanish",
}

LOCALIZED_STRINGS: dict[str, dict[str, str]] = {
    "eng": {
        "amount_mismatch": "Amount mismatch: expected {expected}±{tolerance}, found {found}",
        "date_mismatch": "Date mismatch: expected {expected}±{window} days, found {found}",
        "timing_difference": "Timing difference: expected {expected}±{window} days, found {found}",
        "beneficiary_mismatch": (
            "Beneficiary mismatch: expected {expected} (similarity ≥ {similarity}), found {found}"
        ),
        "missing_transaction": "Missing transaction: expected {expected}, not found",
        "duplicate_transaction": "Duplicate transaction: expected {expected}, found {found}",
        "fraud": "Fraud: {reason}",
        "no_pdf": "No PDF uploaded",
        "extraction_failed": "Could not extract enough text from PDF; LLM check skipped.",
        "manual_review": "Insufficient text extracted; requires manual review.",
    },
    "ita": {
        "amount_mismatch": "Importo non corrispondente: previsto {expected}±{tolerance}, trovato {found}",
        "date_mismatch": "Data non corrispondente: prevista {expected}±{window} giorni, trovate {found}",
        "timing_difference": "Differenza temporale: prevista {expected}±{window} giorni, trovata {found}",
        "beneficiary_mismatch": (
            "Beneficiario non corrispondente: previsto {expected} (somiglianza ≥ {similarity}), trovati {found}"
        ),
        "missing_transaction": "Transazione mancante: prevista {expected}, non trovata",
        "duplicate_transaction": "Transazione duplicata: prevista {expected}, trovate {found}",
        "fraud": "Frode: {reason}",
        "no_pdf": "Nessun PDF caricato",
        "extraction_failed": "Impossibile estrarre testo sufficiente dal PDF; controllo LLM saltato.",
        "manual_review": "Testo estratto insufficiente; è necessaria una revisione manuale.",
    },
    "fra": {
        "amount_mismatch": "Discordance de montant : attendu {expected}±{tolerance}, trouvé {found}",
        "date_mismatch": "Discordance de date : attendu {expected}±{window} jours, trouvé {found}",
        "timing_difference": "Décalage de date : attendu {expected}±{window} jours, trouvé {found}",
        "beneficiary_mismatch": (
            "Bénéficiaire différent : attendu {expected} (similarité ≥ {similarity}), trouvé {found}"
        ),
        "missing_transaction": "Transaction manquante : attendu {expected}, non trouvée",
        "duplicate_transaction": "Transaction en double : attendu {expected}, trouvé {found}",
        "fraud": "Fraude : {reason}",
        "no_pdf": "Aucun PDF téléchargé",
        "extraction_failed": "Impossible d'extraire suffisamment de texte du PDF ; contrôle LLM ignoré.",
        "manual_review": "Texte extrait insuffisant ; nécessite une révision manuelle.",
    },
    "deu": {
        "amount_mismatch": "Betragsabweichung: erwartet {expected}±{tolerance}, gefunden {found}",
        "date_mismatch": "Datumsabweichung: erwartet {expected}±{window} Tage, gefunden {found}",
        "timing_difference": "Zeitliche Abweichung: erwartet {expected}±{window} Tage, gefunden {found}",
        "beneficiary_mismatch": (
            "Begünstigter stimmt nicht überein: erwartet {expected} (Ähnlichkeit ≥ {similarity}), gefunden {found}"
        ),
        "missing_transaction": "Fehlende Transaktion: erwartet {expected}, nicht gefunden",
        "duplicate_transaction": "Doppelte Transaktion: erwartet {expected}, gefunden {found}",
        "fraud": "Betrug: {reason}",
        "no_pdf": "Kein PDF hochgeladen",
        "extraction_failed": "Es konnten nicht genügend Text aus dem PDF extrahiert werden; LLM-Prüfung übersprungen.",
        "manual_review": "Unzureichender Text extrahiert; manuelle Überprüfung erforderlich.",
    },
    "spa": {
        "amount_mismatch": "Diferencia de importe: se esperaba {expected}±{tolerance}, se encontró {found}",
        "date_mismatch": "Diferencia de fecha: se esperaba {expected}±{window} días, se encontró {found}",
        "timing_difference": "Diferencia temporal: se esperaba {expected}±{window} días, se encontró {found}",
        "beneficiary_mismatch": (
            "Beneficiario diferente: se esperaba {expected} (similitud ≥ {similarity}), se encontró {found}"
        ),
        "missing_transaction": "Transacción pendiente: se esperaba {expected}, no se encontró",
        "duplicate_transaction": "Transacción duplicada: se esperaba {expected}, se encontró {found}",
        "fraud": "Fraude: {reason}",
        "no_pdf": "No se ha cargado ningún PDF",
        "extraction_failed": "No se pudo extraer suficiente texto del PDF; se omitió la comprobación con LLM.",
        "manual_review": "El texto extraído es insuficiente; se requiere revisión manual.",
    },
}

MISMATCH_SEVERITY: dict[str, MismatchSeverity] = {
    "amount_mismatch": MismatchSeverity.CRITICAL,
    "date_mismatch": MismatchSeverity.MAJOR,
    "beneficiary_mismatch": MismatchSeverity.MINOR,
    "timing_difference": MismatchSeverity.MINOR,
    "missing_transaction": MismatchSeverity.CRITICAL,
    "duplicate_transaction": MismatchSeverity.MAJOR,
    "fraud": MismatchSeverity.CRITICAL,
}

SEVERITY_LABELS: dict[str, dict[MismatchSeverity, str]] = {
    "eng": {
        MismatchSeverity.CRITICAL: "Critical",
        MismatchSeverity.MAJOR: "Major",
        MismatchSeverity.MINOR: "Minor",
    },
    "ita": {
        MismatchSeverity.CRITICAL: "Critico",
        MismatchSeverity.MAJOR: "Maggiore",
        MismatchSeverity.MINOR: "Minore",
    },
    "fra": {
        MismatchSeverity.CRITICAL: "Critique",
        MismatchSeverity.MAJOR: "Majeur",
        MismatchSeverity.MINOR: "Mineur",
    },
    "deu": {
        MismatchSeverity.CRITICAL: "Kritisch",
        MismatchSeverity.MAJOR: "Schwerwiegend",
        MismatchSeverity.MINOR: "Gering",
    },
    "spa": {
        MismatchSeverity.CRITICAL: "Crítico",
        MismatchSeverity.MAJOR: "Mayor",
        MismatchSeverity.MINOR: "Menor",
    },
}

# Reverse lookup for parsing free-form severity strings.
_SEVERITY_ALIASES: dict[str, MismatchSeverity] = {
    sev.value: sev for sev in MismatchSeverity
}
for lang_map in SEVERITY_LABELS.values():
    for sev, label in lang_map.items():
        _SEVERITY_ALIASES[label.lower()] = sev


def parse_severity(value: str | None) -> MismatchSeverity:
    """Return ``MismatchSeverity`` for *value*.

    Unknown or ``None`` values default to :class:`MismatchSeverity.MINOR` and are
    logged for easier debugging.
    """

    if not value:
        return MismatchSeverity.MINOR
    try:
        return _SEVERITY_ALIASES[value.lower()]
    except KeyError:
        accepted = ", ".join(sorted(_SEVERITY_ALIASES))
        logging.getLogger(__name__).warning(
            "Unknown mismatch severity '%s', defaulting to MINOR. Accepted severities: %s",
            value,
            accepted,
        )
        return MismatchSeverity.MINOR
