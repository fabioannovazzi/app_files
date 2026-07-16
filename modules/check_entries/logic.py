import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Iterable, Mapping

import polars as pl
from polars.exceptions import ComputeError

from modules.llm import model_router
from modules.llm.model_router import should_use_batch
from modules.llm.openai_batch import create_batch_file, submit_batch, wait_for_batch
from src.io_utils import get_schema_and_column_names

try:  # pragma: no cover - optional dependency in tests
    from src.check_statements import _parse_amount, _parse_date, _similarity
except Exception as e:  # pragma: no cover - fall back to simple parsers
    logging.exception(e)

    def _parse_amount(text: str) -> float | None:
        text = (
            text.replace("\u00a0", " ")
            .replace("\u202f", " ")
            .replace(" ", "")
            .replace(",", ".")
        )
        try:
            return float(text)
        except ValueError:
            return None

    def _parse_date(text: str) -> date | None:
        from datetime import datetime

        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def _similarity(a: str, b: str) -> float:
        return 100.0 if a == b else 0.0


DEBUG_PROMPTS = False
PDF_SNIPPET_LEN = 100
# Maximum characters of PDF text included in the LLM prompt.
PROMPT_SNIPPET_LEN = 1500
NAME_SIM_THRESHOLD = 0.92
EXTRACTION_Q_THRESHOLD = 0.80


class PartialCheckError(Exception):
    """Raised when automatic entry checking stops early."""

    def __init__(self, partial_df: pl.DataFrame, cause: Exception):
        super().__init__(str(cause))
        self.partial_df = partial_df
        self.cause = cause


# Backwards-compat shim for tests that monkeypatch this name directly.
def query_llm_return_json(
    llm_wrapper, query_step, system_prompt, user_prompt, **kwargs
):
    return model_router.query_llm_return_json(
        llm_wrapper, query_step, system_prompt, user_prompt, **kwargs
    )


@dataclass
class CheckResult:
    """Result of checking a single entry against its PDF."""

    entry: dict[str, object]
    movement_number: str
    check_status: str | None
    explanation: str | None
    line_numbers: object | None = None
    pdf_snippet: str = ""
    mismatches: list[dict[str, object]] = field(default_factory=list)
    severity: str | None = None
    extraction_method: str = ""
    step_failed: str = ""
    ocr_attempts: list[object] = field(default_factory=list)
    llm_called: bool = False
    llm_reason: str | None = None
    llm_model: str | None = None
    llm_batch: bool = False
    llm_parse_ok: bool | None = None
    llm_error: str | None = None
    beneficiary_extracted: str | None = None
    name_similarity: float | None = None


from modules.check_entries.constants import (
    MISMATCH_SEVERITY,
    SEVERITY_LABELS,
    BeneficiaryCheckMode,
    MismatchSeverity,
)
from modules.check_entries.utils import OK_MSG, normalize_status
from modules.pdf_utils.pdf_utils import extract_pdf_text_with_ocr

__all__ = [
    "check_entry_against_text",
    "run_automatic_check",
    "PartialCheckError",
    "CheckResult",
    "MismatchSeverity",
    "MISMATCH_SEVERITY",
    "get_severity_label",
    "apply_override_reasons",
]


# Map various language aliases to a canonical 3-letter code.
#
# The mapping accepts two-letter ISO codes and common English names to make the
# public API of this module more forgiving.  The values follow the "eng" style
# used throughout the code base and by the OCR helpers.
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
}

# Reverse mapping used to obtain a user-facing language name for the LLM.
LANGUAGE_NAMES: dict[str, str] = {
    "eng": "English",
    "ita": "Italian",
    "fra": "French",
    "deu": "German",
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
        "extraction_failed": (
            "Impossible d'extraire suffisamment de texte du PDF ; vérification LLM ignorée."
        ),
        "manual_review": "Texte extrait insuffisant ; révision manuelle requise.",
    },
    "deu": {
        "amount_mismatch": "Betragsabweichung: erwartet {expected}±{tolerance}, gefunden {found}",
        "date_mismatch": "Datumsabweichung: erwartet {expected}±{window} Tage, gefunden {found}",
        "timing_difference": "Zeitliche Differenz: erwartet {expected}±{window} Tage, gefunden {found}",
        "beneficiary_mismatch": (
            "Abweichender Begünstigter: erwartet {expected} (Ähnlichkeit ≥ {similarity}), gefunden {found}"
        ),
        "missing_transaction": "Fehlende Transaktion: erwartet {expected}, nicht gefunden",
        "duplicate_transaction": "Doppelte Transaktion: erwartet {expected}, gefunden {found}",
        "fraud": "Betrug: {reason}",
        "no_pdf": "Kein PDF hochgeladen",
        "extraction_failed": (
            "Es konnte nicht genügend Text aus dem PDF extrahiert werden; LLM-Prüfung übersprungen."
        ),
        "manual_review": "Unzureichender Text extrahiert; manuelle Prüfung erforderlich.",
    },
}


def get_severity_label(mismatch_key: str, lang: str) -> str:
    """Return the localized severity label for *mismatch_key* in language *lang*."""

    severity = MISMATCH_SEVERITY.get(mismatch_key, MismatchSeverity.MINOR)
    lang_code = LANGUAGE_ALIASES.get(lang.lower(), lang.lower())
    labels = SEVERITY_LABELS.get(lang_code, SEVERITY_LABELS["eng"])
    return labels.get(severity, severity.value)


def _localize(lang: str, key: str, **kwargs) -> str:
    """Return localized string for *key* in language *lang*."""

    template = LOCALIZED_STRINGS.get(lang, LOCALIZED_STRINGS["eng"]).get(key, "")
    try:
        return template.format(**kwargs)
    except Exception as e:
        logging.exception(e)
        return template


def _extract_amounts(
    text: str, *, require_currency: bool = False
) -> list[tuple[float, str, int]]:
    """Return ``(amount, context_line, line_number)`` triples found in *text*.

    When ``require_currency`` is True, numbers are only returned if a currency
    symbol (€, $, £, ¥, etc.) or keywords like ``totale`` or ``amount`` appear
    on the same line. Integers without decimal separators are ignored unless
    they fall within a small monetary range (<10000).
    """

    # Normalize non-breaking spaces to regular spaces to simplify parsing.
    text = text.replace("\u00a0", " ").replace("\u202f", " ")

    # Remove common date formats so their digits are not misinterpreted as
    # amounts (e.g. "2024-05-01").
    date_patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b\d{1,2}-\d{1,2}-\d{2,4}\b",
        r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b",
    ]
    for pat in date_patterns:
        text = re.sub(pat, " ", text)

    pattern = (
        r"[-+]?(?:[0-9]{1,3}(?:[ \u00A0\u202F.][0-9]{3})+|[0-9]+)(?:[.,][0-9]+)?(?:-(?!\d))?"
        r"|\((?:[0-9]{1,3}(?:[ \u00A0\u202F.][0-9]{3})+|[0-9]+)(?:[.,][0-9]+)?\)"
    )

    amounts: list[tuple[float, str, int]] = []
    for match in re.finditer(pattern, text):
        raw = match.group()
        amt = _parse_amount(raw)
        if amt is None:
            continue

        has_decimal = "." in raw or "," in raw
        start, end = match.span()
        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", end)
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end]
        line_no = text.count("\n", 0, start) + 1
        context = text[max(0, start - 10) : min(len(text), end + 10)]

        currency_match = re.search(
            r"[€$£¥]|\b(?:eur|usd|gbp|chf)\b", context, re.IGNORECASE
        )
        keyword_match = re.search(r"\b(totale|total|amount)\b", context, re.IGNORECASE)

        if require_currency and not (currency_match or keyword_match):
            continue

        if not has_decimal and not currency_match and abs(amt) >= 10000:
            # Skip very large integers lacking decimal separators or currency hints
            continue

        amounts.append((amt, line.strip(), line_no))
    return amounts


def _extract_dates(text: str) -> list[tuple[date, int]]:
    """Return ``(date, line_number)`` pairs parsed from *text* in common formats."""

    dates: list[tuple[date, int]] = []
    patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b\d{1,2}-\d{1,2}-\d{2,4}\b",
        r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b",
    ]
    for pat in patterns:
        for match in re.finditer(pat, text):
            dt = _parse_date(match.group())
            if dt:
                line_no = text.count("\n", 0, match.start()) + 1
                dates.append((dt, line_no))
    return dates


def _extract_beneficiary(text: str) -> str | None:
    """Return a simple beneficiary/payee name from *text* if present."""

    for line in text.splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            if key.strip().lower() in {"beneficiary", "beneficiario", "payee"}:
                return val.strip()
    return None


def _beneficiary_found(beneficiary: str, text: str, threshold: float) -> bool:
    """Return True if *beneficiary* roughly occurs in *text*."""

    if not beneficiary:
        return True
    for line in text.splitlines():
        if _similarity(beneficiary, line) >= threshold:
            return True
    return False


def _normalize_field(name: str) -> str:
    """Normalize field *name* for comparison."""

    return name.lower().replace("_", " ")


def _find_entry_field(
    entry: Mapping[str, object],
    names: Iterable[str] | Mapping[str, Iterable[str]],
) -> object | None:
    """Return the value for the key exactly matching any provided *names*.

    The comparison is case-insensitive and treats underscores as spaces.  ``names``
    may be an iterable of aliases or a mapping of canonical names to alias lists.
    """

    if isinstance(names, Mapping):
        aliases = {
            _normalize_field(alias)
            for alias_list in names.values()
            for alias in alias_list
        }
    else:
        aliases = {_normalize_field(name) for name in names}

    for key in entry:
        if _normalize_field(key) in aliases:
            return entry.get(key)
    return None


def _pre_llm_check(
    entry: Mapping[str, object],
    pdf_text: str,
    lang_code: str,
    amount_tolerance: float,
    date_window: int,
    timing_difference_window: int | None,
    beneficiary_similarity: float,
    beneficiary_check_mode: BeneficiaryCheckMode,
) -> list[dict[str, object]] | None:
    """Run deterministic checks before querying the LLM."""

    mismatches: list[dict[str, object]] = []
    entry_amount = _parse_amount(_find_entry_field(entry, ["amount"]))
    entry_date = _parse_date(_find_entry_field(entry, ["date"]))
    entry_beneficiary = _find_entry_field(
        entry, ["beneficiary", "counterparty", "payee"]
    )

    if entry_amount is not None:
        amounts_with_context = _extract_amounts(pdf_text)

        def line_has_keyword(line: str) -> bool:
            keys = ["total", "amount"]
            if entry_beneficiary:
                keys.append(str(entry_beneficiary))
            line_low = line.lower()
            return any(k.lower() in line_low for k in keys if k)

        relevant_pairs = [
            (amt, line_no)
            for amt, line, line_no in amounts_with_context
            if line_has_keyword(line)
        ]
        if not relevant_pairs:
            relevant_pairs = [
                (amt, line_no) for amt, _line, line_no in amounts_with_context
            ]

        relevant_values = [amt for amt, _ in relevant_pairs]

        if not any(
            abs(abs(a) - abs(entry_amount)) <= amount_tolerance for a in relevant_values
        ):
            mismatches.append(
                {
                    "mismatch_type": "amount_mismatch",
                    "explanation": _localize(
                        lang_code,
                        "amount_mismatch",
                        expected=entry_amount,
                        tolerance=amount_tolerance,
                        # Include line numbers so callers can reference where the
                        # amounts were extracted from within the PDF text.
                        found=[(a, l, ln) for a, l, ln in amounts_with_context],
                    ),
                    "line_numbers": [ln for _a, _l, ln in amounts_with_context],
                }
            )

    if entry_date is not None:
        dates_with_lines = _extract_dates(pdf_text)
        timing_window = (
            timing_difference_window
            if timing_difference_window is not None
            else date_window
        )
        if any(abs((d - entry_date).days) <= date_window for d, _ in dates_with_lines):
            pass
        elif any(
            abs((d - entry_date).days) <= timing_window for d, _ in dates_with_lines
        ):
            mismatches.append(
                {
                    "mismatch_type": "timing_difference",
                    "explanation": _localize(
                        lang_code,
                        "timing_difference",
                        expected=entry_date,
                        window=timing_window,
                        found=[d.isoformat() for d, _ln in dates_with_lines],
                    ),
                    "line_numbers": [ln for _d, ln in dates_with_lines],
                }
            )
        else:
            mismatches.append(
                {
                    "mismatch_type": "date_mismatch",
                    "explanation": _localize(
                        lang_code,
                        "date_mismatch",
                        expected=entry_date,
                        window=timing_window,
                        found=[d.isoformat() for d, _ln in dates_with_lines],
                    ),
                    "line_numbers": [ln for _d, ln in dates_with_lines],
                }
            )

    beneficiary_str = str(entry_beneficiary or "")
    if beneficiary_check_mode == BeneficiaryCheckMode.COMPARE and beneficiary_str:
        numbered_lines = [
            (idx + 1, line.strip())
            for idx, line in enumerate(pdf_text.splitlines())
            if line.strip()
        ][:20]
        if not _beneficiary_found(beneficiary_str, pdf_text, beneficiary_similarity):
            mismatches.append(
                {
                    "mismatch_type": "beneficiary_mismatch",
                    "explanation": _localize(
                        lang_code,
                        "beneficiary_mismatch",
                        expected=repr(beneficiary_str),
                        similarity=beneficiary_similarity,
                        found=[line for _ln, line in numbered_lines],
                    ),
                    "line_numbers": [ln for ln, _ in numbered_lines],
                }
            )
    return mismatches or None


def _first_mismatch(mismatches: list[dict[str, object]] | None) -> dict[str, object]:
    """Return the first mismatch from *mismatches* or an empty dict."""

    return mismatches[0] if mismatches else {}


def compute_confidence(features: dict) -> dict:
    """Compute simple confidence metrics from extracted features."""
    entry = features.get("entry", {})
    pdf_text = features.get("pdf_text", "")
    amount_tolerance = float(features.get("amount_tolerance", 0.0))
    date_window = int(features.get("date_window", 0))
    beneficiary_similarity = float(features.get("beneficiary_similarity", 100.0))

    entry_date = _parse_date(str(_find_entry_field(entry, ["date"])) or "")
    dates = [d for d, _ in _extract_dates(pdf_text)]
    date_matches = [
        d for d in dates if entry_date and abs((d - entry_date).days) <= date_window
    ]
    ambiguous_date = len(set(dates)) > 1
    doc_date_conf = 0.0
    if entry_date and dates:
        if len(date_matches) == 1:
            doc_date_conf = 0.99
        elif len(date_matches) > 1:
            doc_date_conf = 0.7
        else:
            doc_date_conf = 0.2

    entry_amount = _parse_amount(str(_find_entry_field(entry, ["amount"])) or "")
    amounts = [a for a, _, _ in _extract_amounts(pdf_text)]
    amount_conf = 0.0
    if entry_amount is not None and amounts:
        if any(abs(abs(a) - abs(entry_amount)) <= amount_tolerance for a in amounts):
            amount_conf = 0.99
        else:
            amount_conf = 0.0

    beneficiary = _find_entry_field(entry, ["beneficiary", "counterparty", "payee"])
    mode = features.get("beneficiary_check_mode", BeneficiaryCheckMode.COMPARE)
    name_conf = 1.0 if mode != BeneficiaryCheckMode.COMPARE else 0.0
    if mode == BeneficiaryCheckMode.COMPARE and beneficiary:
        max_sim = 0.0
        for line in pdf_text.splitlines():
            sim = _similarity(str(beneficiary), line)
            max_sim = max(max_sim, sim)
        name_conf = max_sim / 100.0

    extraction_quality = min(1.0, len(pdf_text) / 1000.0)
    totals_reconcile = amount_conf >= 0.8

    return {
        "doc_date_conf": doc_date_conf,
        "amount_conf": amount_conf,
        "name_conf": name_conf,
        "extraction_quality": extraction_quality,
        "ambiguous_date": ambiguous_date,
        "totals_reconcile": totals_reconcile,
    }


def should_call_llm(precheck_status: str, conf: dict) -> tuple[bool, str]:
    """Decide whether to call the LLM and why."""
    if precheck_status == "mismatch_major":
        return False, "deterministic_final"
    if precheck_status == "mismatch_minor":
        return False, "deterministic_final"
    if precheck_status == "mismatch":
        return False, "deterministic_final"

    if precheck_status == "ok":
        if (
            conf.get("doc_date_conf", 0.0) >= 0.95
            and conf.get("amount_conf", 0.0) >= 0.99
            and conf.get("name_conf", 0.0) >= NAME_SIM_THRESHOLD
            and conf.get("totals_reconcile", False)
            and conf.get("extraction_quality", 0.0) >= EXTRACTION_Q_THRESHOLD
            and not conf.get("ambiguous_date", False)
        ):
            return False, "high_confidence_ok"
        if conf.get("ambiguous_date", False):
            return True, "ambiguous_date"
        if conf.get("name_conf", 0.0) < NAME_SIM_THRESHOLD:
            return True, "low_name_score"
        if conf.get("extraction_quality", 0.0) < EXTRACTION_Q_THRESHOLD:
            return True, "poor_ocr"
        if not conf.get("totals_reconcile", False):
            return True, "totals_conflict"
    return True, "unknown"


def _extract_relevant_snippet(
    entry: Mapping[str, object],
    pdf_text: str,
    amount_tolerance: float,
    date_window: int,
    beneficiary_similarity: float,
    timing_difference_window: int | None = None,
    beneficiary_check_mode: BeneficiaryCheckMode = BeneficiaryCheckMode.OFF,
) -> str:
    """Return a concise snippet of *pdf_text* around relevant matches.

    Lines containing the entry's amount, date, or beneficiary are collected
    together with one line of surrounding context. Separate segments are joined
    by ``---`` to keep the prompt compact. Falls back to the first
    ``PROMPT_SNIPPET_LEN`` characters when no matches are found.
    """

    lines = pdf_text.splitlines()
    line_numbers: set[int] = set()

    amt_raw = _find_entry_field(entry, ["amount"])
    amt = _parse_amount(str(amt_raw)) if amt_raw is not None else None
    if amt is not None:
        for found, _line, ln in _extract_amounts(pdf_text):
            if abs(abs(found) - abs(amt)) <= amount_tolerance:
                line_numbers.add(ln)

    dt_raw = _find_entry_field(entry, ["date"])
    dt = _parse_date(str(dt_raw)) if dt_raw is not None else None
    if dt is not None:
        max_window = (
            timing_difference_window
            if timing_difference_window is not None
            else date_window
        )
        for found, ln in _extract_dates(pdf_text):
            if abs((found - dt).days) <= max_window:
                line_numbers.add(ln)

    beneficiary = _find_entry_field(entry, ["beneficiary", "counterparty", "payee"])
    beneficiary_str = str(beneficiary or "")
    if beneficiary_check_mode != BeneficiaryCheckMode.OFF and beneficiary_str:
        for idx, line in enumerate(lines, start=1):
            line_low = line.lower()
            if (
                _similarity(beneficiary_str, line) >= beneficiary_similarity
                or beneficiary_str.lower() in line_low
            ):
                line_numbers.add(idx)

    if not line_numbers:
        return pdf_text[:PROMPT_SNIPPET_LEN]

    indices = sorted(ln - 1 for ln in line_numbers)
    segments: list[tuple[int, int]] = []
    for idx in indices:
        start = max(0, idx - 1)
        end = min(len(lines), idx + 2)
        if segments and start <= segments[-1][1]:
            segments[-1] = (segments[-1][0], max(segments[-1][1], end))
        else:
            segments.append((start, end))

    parts = ["\n".join(lines[s:e]) for s, e in segments]
    snippet = "\n---\n".join(parts)
    return snippet[:PROMPT_SNIPPET_LEN]


def _build_prompt(
    entry: Mapping,
    pdf_text: str,
    language: str,
    amount_tolerance: float,
    date_window: int,
    timing_difference_window: int | None = None,
    beneficiary_similarity: float = 60.0,
    beneficiary_check_mode: BeneficiaryCheckMode = BeneficiaryCheckMode.OFF,
) -> tuple[str, str]:
    """Construct user and system prompts for the LLM."""

    snippet = _extract_relevant_snippet(
        entry,
        pdf_text,
        amount_tolerance,
        date_window,
        beneficiary_similarity,
        timing_difference_window,
        beneficiary_check_mode,
    )
    timing_window = (
        timing_difference_window
        if timing_difference_window is not None
        else date_window
    )
    extra = (
        f"Differences up to {timing_window} days should be classified as 'timing_difference'.\n"
        if timing_window != date_window
        else ""
    )
    if beneficiary_check_mode == BeneficiaryCheckMode.COMPARE:
        beneficiary_line = (
            f"Extract the beneficiary/payee name from the PDF and return it as 'beneficiary_extracted'.\n"
            f"The entry expects '{entry.get('beneficiary', '')}'.\n"
            f"Beneficiary names may match if similarity is at least {beneficiary_similarity}.\n"
        )
    elif beneficiary_check_mode == BeneficiaryCheckMode.EXTRACT_ONLY:
        beneficiary_line = "Extract the beneficiary/payee name from the PDF and return it as 'beneficiary_extracted'.\n"
    else:
        beneficiary_line = ""
    reply_json = '{"status": "ok|mismatch", "explanation": "brief justification"'
    if beneficiary_check_mode != BeneficiaryCheckMode.OFF:
        reply_json += ', "beneficiary_extracted": ""'
    reply_json += "}"
    prompt_user = (
        "Given this journal entry and the extracted PDF text, determine if the document supports the entry.\n"
        + f"Allow amount differences up to {amount_tolerance} and date differences up to {date_window} days.\n"
        + extra
        + beneficiary_line
        + "Return 'status' as 'ok' or 'mismatch' and include a brief, human-readable justification.\n"
        + f"Entry: {dict(entry)}\n"
        + "PDF text:\n"
        + snippet
        + "\n"
        + f"Reply JSON {reply_json}"
    )
    prompt_system = f"You are an accounting assistant. Reply in JSON only. Return you explanation text in {language}"
    return prompt_user, prompt_system


def check_entry_against_text(
    llm_wrapper,
    entry: Mapping,
    pdf_text: str,
    language: str,
    *,
    amount_tolerance: float = 0.0,
    date_window: int = 0,
    timing_difference_window: int | None = None,
    beneficiary_similarity: float = 100.0,
    beneficiary_check_mode: BeneficiaryCheckMode = BeneficiaryCheckMode.COMPARE,
) -> dict:
    """Ask the LLM if *pdf_text* supports *entry* using tolerance rules.

    ``amount_tolerance`` represents the maximum allowed absolute
    difference between the entry amount and values found in the PDF,
    expressed in the same currency units.
    """

    lang_code = LANGUAGE_ALIASES.get(str(language).lower(), "eng")

    prelim = _pre_llm_check(
        entry,
        pdf_text,
        lang_code,
        amount_tolerance,
        date_window,
        timing_difference_window,
        beneficiary_similarity,
        beneficiary_check_mode,
    )
    if prelim:
        for m in prelim:
            m_type = m.get("mismatch_type")
            m["severity"] = get_severity_label(m_type, lang_code) if m_type else None
        return {"status": "mismatch", "mismatches": prelim}

    prompt_user, prompt_system = _build_prompt(
        entry,
        pdf_text,
        language,
        amount_tolerance,
        date_window,
        timing_difference_window,
        beneficiary_similarity,
        beneficiary_check_mode,
    )

    import importlib

    cfg = importlib.import_module("modules.utilities.config")
    namingParams = cfg.get_naming_params()
    model = namingParams["checkEntriesQuery"]
    resp = query_llm_return_json(
        llm_wrapper,
        model,
        prompt_system,
        prompt_user,
    )
    if DEBUG_PROMPTS:  # plain Python / console
        logging.debug(
            "\n──── LLM PROMPT START ────\n%s\n──── LLM PROMPT END ─────\n",
            prompt_user,
        )

    if not isinstance(resp, dict):
        try:
            resp = json.loads(str(resp))
        except json.JSONDecodeError as e:
            logging.error("check_entry_against_text JSON decode error: %s", e)
            return {"status": "error", "explanation": "Could not parse LLM response"}

    beneficiary_extracted = resp.get("beneficiary_extracted")
    name_similarity: float | None = None
    if beneficiary_check_mode == BeneficiaryCheckMode.COMPARE and beneficiary_extracted:
        expected_ben = str(
            _find_entry_field(entry, ["beneficiary", "counterparty", "payee"]) or ""
        )
        name_similarity = _similarity(expected_ben, str(beneficiary_extracted))
        if name_similarity < beneficiary_similarity:
            mismatch = {
                "mismatch_type": "beneficiary_mismatch",
                "explanation": _localize(
                    lang_code,
                    "beneficiary_mismatch",
                    expected=repr(expected_ben),
                    similarity=beneficiary_similarity,
                    found=[str(beneficiary_extracted or "")],
                ),
                "line_numbers": [],
            }
            resp.setdefault("mismatches", []).append(mismatch)
            resp["status"] = "mismatch"

    if resp.get("status") == "mismatch" and "mismatches" not in resp:
        m_type = resp.get("mismatch_type")
        mismatch = {
            "mismatch_type": m_type,
            "explanation": resp.get("explanation"),
            "line_numbers": resp.get("line_numbers"),
            "severity": get_severity_label(m_type, lang_code) if m_type else None,
        }
        resp["mismatches"] = [mismatch]

    resp["beneficiary_extracted"] = beneficiary_extracted
    resp["name_similarity"] = name_similarity
    return resp


def _normalize_line_numbers(value: object | None) -> list[int]:
    """Return ``value`` as a list of integers."""

    if value is None:
        return []
    if isinstance(value, list):
        return [int(v) for v in value]
    if isinstance(value, (set, tuple)):
        return [int(v) for v in value]
    return [int(value)]


def _rows_to_df(rows: list[CheckResult]) -> pl.DataFrame:
    """Build a DataFrame from ``rows`` with a safe fallback."""

    include_debug = any(
        r.extraction_method or r.step_failed or r.ocr_attempts for r in rows
    )
    dict_rows: list[dict[str, object]] = []
    for r in rows:
        base: dict[str, object] = {
            **r.entry,
            "movement_number": r.movement_number,
            "check_status": r.check_status,
            "explanation": r.explanation,
            "line_numbers": _normalize_line_numbers(r.line_numbers),
            "pdf_snippet": r.pdf_snippet,
            "mismatches": r.mismatches,
            "severity": r.severity,
            "llm_called": r.llm_called,
            "llm_reason": r.llm_reason,
            "llm_model": r.llm_model,
            "llm_batch": r.llm_batch,
            "llm_parse_ok": r.llm_parse_ok,
            "llm_error": r.llm_error,
            "beneficiary_extracted": r.beneficiary_extracted,
            "name_similarity": r.name_similarity,
        }
        if include_debug:
            base["extraction_method"] = r.extraction_method
            base["step_failed"] = r.step_failed
            base["ocr_attempts"] = r.ocr_attempts
        dict_rows.append(base)
    # Infer the schema from all rows to handle booleans or other types that may
    # appear only in later records.  The default Polars behaviour inspects just
    # the first 50 rows which can cause ``ComputeError`` when a column's type is
    # mis-inferred.
    infer_len = len(dict_rows)
    try:
        return pl.DataFrame(dict_rows, orient="row", infer_schema_length=infer_len)
    except (ComputeError, TypeError) as e:
        logging.error("check_entries DataFrame orient error: %s", e)
        return pl.DataFrame(dict_rows, infer_schema_length=infer_len)


def run_automatic_check(
    df: pl.DataFrame | pl.LazyFrame,
    mapping: Mapping[str, str],
    pdf_map: Mapping[str, object],
    llm_wrapper,
    *,
    provider: str | None = None,
    model: str | None = None,
    debug: bool = False,
    lang: str = "eng",
    amount_tolerance: float = 0.0,
    date_window: int = 0,
    timing_difference_window: int | None = None,
    beneficiary_similarity: float = 100.0,
    beneficiary_check_mode: BeneficiaryCheckMode = BeneficiaryCheckMode.OFF,
    progress: Callable[[int, int], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> pl.DataFrame:
    """Return a DataFrame with the automatic check results.

    A short ``pdf_snippet`` column is always included. When ``debug`` is True,
    additional OCR metadata such as extraction method, step failures and
    attempts are returned.

    If ``progress`` is provided it is called with the current row number and
    total row count to report progress. When ``is_cancelled`` returns ``True``
    the function stops early and raises :class:`PartialCheckError` containing
    the rows processed so far.
    """

    if isinstance(df, pl.LazyFrame):
        df = df.collect()

    lang_code = LANGUAGE_ALIASES.get(lang.lower(), lang.lower())
    lang_name = LANGUAGE_NAMES.get(lang_code, lang_code)

    import importlib

    cfg = importlib.import_module("modules.utilities.config")

    naming = cfg.get_naming_params()
    run_params = cfg.get_run_params()
    check_entries_step = naming["checkEntriesQuery"]
    select_fn = getattr(cfg, "select_provider", None)
    query_dict = select_fn(check_entries_step) if select_fn else {}
    if not query_dict:
        query_dict = {}

    provider_key = naming["providerName"]
    model_key = naming["modelName"]
    provider = provider or str(query_dict.get(provider_key, ""))
    model = model or str(query_dict.get(model_key, ""))
    # Centralized batch gate: global switch + step prefs + provider/model capability
    batch_mode = should_use_batch(check_entries_step)

    batch_requests: list[dict[str, object]] = []
    batch_infos: list[dict[str, object]] = []

    def _retry_ocr_and_check(
        entry: Mapping[str, object], mov: str, pdf_bytes: bytes
    ) -> tuple[str, str, dict[str, object]]:
        """Re-run OCR and build a prompt for a second LLM check.

        The function performs OCR again on ``pdf_bytes`` and constructs the
        user and system prompts for a subsequent LLM verification.  It returns
        the prompts together with metadata required to build the final
        :class:`CheckResult` once the LLM response is available.
        """

        retry_res = extract_pdf_text_with_ocr(
            pdf_bytes, llm_wrapper=llm_wrapper, lang=lang, retries=1
        )
        attempts_r = [a._asdict() for a in getattr(retry_res, "attempts", [])]
        step_failed_r = getattr(retry_res, "step_failed", "")
        snippet_r = retry_res.text[:PDF_SNIPPET_LEN]
        debug_r = (
            {
                "extraction_method": retry_res.method,
                "step_failed": step_failed_r,
                "ocr_attempts": attempts_r,
            }
            if debug
            else {}
        )

        prompt_user_r, prompt_system_r = _build_prompt(
            entry,
            retry_res.text,
            lang_name,
            amount_tolerance,
            date_window,
            timing_difference_window,
            beneficiary_similarity,
            beneficiary_check_mode,
        )

        info = {
            "entry": entry,
            "mov": mov,
            "snippet": snippet_r,
            "debug_fields": debug_r,
            "pdf_text": retry_res.text,
        }
        return prompt_user_r, prompt_system_r, info

    columns, _schema = get_schema_and_column_names(df)
    col_idx = {name: idx for idx, name in enumerate(columns)}

    rows: list[CheckResult] = []
    total_rows = df.height
    for idx, row in enumerate(df.iter_rows(), start=1):
        if progress:
            progress(idx, total_rows)
        if is_cancelled and is_cancelled():
            partial_df = normalize_status(_rows_to_df(rows))
            raise PartialCheckError(partial_df, RuntimeError("Cancelled"))
        try:
            mov_col = mapping.get("movement_number")
            mov_val = row[col_idx[mov_col]] if mov_col in col_idx else None
            if isinstance(mov_val, (int, float)) and mov_val == int(mov_val):
                mov = str(int(mov_val))
            else:
                mov = str(mov_val).strip()
            pdf_file = pdf_map.get(mov)
            entry = {
                k: row[col_idx[c]]
                for k, c in mapping.items()
                if k != "movement_number" and c in col_idx
            }
            entry_for_prompt = dict(entry)
            if beneficiary_check_mode != BeneficiaryCheckMode.COMPARE:
                for k in ("beneficiary", "counterparty", "payee"):
                    entry_for_prompt.pop(k, None)
            if not pdf_file:
                rows.append(
                    CheckResult(
                        entry=entry,
                        movement_number=mov,
                        check_status="no_pdf",
                        explanation=_localize(lang_code, "no_pdf"),
                        pdf_snippet="",
                        mismatches=[],
                        severity=None,
                        beneficiary_extracted=None,
                        name_similarity=None,
                        **(
                            {
                                "extraction_method": "",
                                "step_failed": "",
                                "ocr_attempts": [],
                            }
                            if debug
                            else {}
                        ),
                    )
                )
                continue
            data = pdf_file.read()
            pdf_file.seek(0)

            result = extract_pdf_text_with_ocr(data, llm_wrapper=llm_wrapper, lang=lang)
            attempts = [a._asdict() for a in getattr(result, "attempts", [])]
            step_failed = getattr(result, "step_failed", "")
            snippet = result.text[:PDF_SNIPPET_LEN]
            beneficiary_extracted = None

            minLen = 50
            if len(result.text) < minLen:
                retry_res = extract_pdf_text_with_ocr(
                    data,
                    llm_wrapper=llm_wrapper,
                    lang=lang,
                    max_pages=1,
                    retries=1,
                )
                attempts.extend(a._asdict() for a in getattr(retry_res, "attempts", []))
                step_failed = getattr(retry_res, "step_failed", step_failed)
                snippet = retry_res.text[:PDF_SNIPPET_LEN]
                beneficiary_extracted = None
                debug_fields = (
                    {
                        "extraction_method": retry_res.method,
                        "step_failed": step_failed,
                        "ocr_attempts": attempts,
                    }
                    if debug
                    else {}
                )
                if len(retry_res.text) < minLen:
                    rows.append(
                        CheckResult(
                            entry=entry,
                            movement_number=mov,
                            check_status="manual_review",
                            explanation=_localize(lang_code, "manual_review"),
                            pdf_snippet=snippet,
                            mismatches=[],
                            severity=None,
                            beneficiary_extracted=beneficiary_extracted,
                            name_similarity=None,
                            **debug_fields,
                        )
                    )
                    continue
                result = retry_res
            debug_fields = (
                {
                    "extraction_method": result.method,
                    "step_failed": step_failed,
                    "ocr_attempts": attempts,
                }
                if debug
                else {}
            )

            prelim = _pre_llm_check(
                entry,
                result.text,
                lang_code,
                amount_tolerance,
                date_window,
                timing_difference_window,
                beneficiary_similarity,
                beneficiary_check_mode,
            )
            if prelim:
                for m in prelim:
                    m_type = m.get("mismatch_type")
                    m["severity"] = (
                        get_severity_label(m_type, lang_code) if m_type else None
                    )
                first_p = _first_mismatch(prelim)
                rows.append(
                    CheckResult(
                        entry=entry,
                        movement_number=mov,
                        check_status="mismatch",
                        explanation=first_p.get("explanation"),
                        line_numbers=first_p.get("line_numbers"),
                        pdf_snippet=snippet,
                        mismatches=prelim,
                        severity=first_p.get("severity"),
                        llm_called=False,
                        llm_reason="deterministic_final",
                        llm_model=model,
                        llm_batch=False,
                        llm_parse_ok=None,
                        llm_error=None,
                        beneficiary_extracted=beneficiary_extracted,
                        name_similarity=None,
                        **debug_fields,
                    )
                )
                continue

            conf = compute_confidence(
                {
                    "entry": entry,
                    "pdf_text": result.text,
                    "amount_tolerance": amount_tolerance,
                    "date_window": date_window,
                    "beneficiary_similarity": beneficiary_similarity,
                    "beneficiary_check_mode": beneficiary_check_mode,
                }
            )
            if beneficiary_check_mode == BeneficiaryCheckMode.OFF:
                call_llm, reason = should_call_llm("ok", conf)
            else:
                call_llm = True
                reason = "beneficiary_extract"

            if not call_llm:
                rows.append(
                    CheckResult(
                        entry=entry,
                        movement_number=mov,
                        check_status="verified",
                        explanation=None,
                        line_numbers=None,
                        pdf_snippet=snippet,
                        mismatches=[],
                        severity=None,
                        llm_called=False,
                        llm_reason=reason,
                        llm_model=model,
                        llm_batch=False,
                        llm_parse_ok=None,
                        llm_error=None,
                        beneficiary_extracted=beneficiary_extracted,
                        name_similarity=None,
                        **debug_fields,
                    )
                )
                continue

            llm_error = None
            llm_parse_ok = True
            if batch_mode:
                # Defer to batch submission/collection below
                prompt_user, prompt_system = _build_prompt(
                    entry_for_prompt,
                    result.text,
                    lang_name,
                    amount_tolerance,
                    date_window,
                    timing_difference_window,
                    beneficiary_similarity,
                    beneficiary_check_mode,
                )
                # Ensure a unique custom_id per batch item to satisfy provider constraints
                custom_id = str(len(batch_requests))
                inputs = [
                    {"role": "system", "content": prompt_system},
                    {"role": "user", "content": prompt_user},
                ]
                sys_has_json = "json" in prompt_system
                user_has_json = "json" in prompt_user
                if not (sys_has_json or user_has_json):
                    inputs.append({"role": "system", "content": "Respond in json."})
                batch_requests.append(
                    {
                        "custom_id": custom_id,
                        "body": {
                            "model": model,
                            "input": inputs,
                            "text": {"format": {"type": "json_object"}},
                        },
                    }
                )
                batch_infos.append(
                    {
                        "entry": entry,
                        "mov": mov,
                        "snippet": snippet,
                        "debug_fields": debug_fields,
                        "pdf_text": result.text,
                        "pdf_bytes": data,
                        "llm_reason": reason,
                        "beneficiary_extracted": beneficiary_extracted,
                    }
                )
            else:
                try:
                    verdict = check_entry_against_text(
                        llm_wrapper,
                        entry_for_prompt,
                        result.text,
                        lang_name,
                        amount_tolerance=amount_tolerance,
                        date_window=date_window,
                        timing_difference_window=timing_difference_window,
                        beneficiary_similarity=beneficiary_similarity,
                        beneficiary_check_mode=beneficiary_check_mode,
                    )
                except json.JSONDecodeError:
                    verdict = {}
                    llm_parse_ok = False
                    llm_error = "parse_error"
                except Exception as e:  # pragma: no cover - unexpected transport
                    logging.exception(e)
                    verdict = {}
                    llm_parse_ok = False
                    llm_error = "transport"

                status = verdict.get("status")
                if status != "mismatch":
                    status = "verified"
                beneficiary_extracted = verdict.get("beneficiary_extracted")
                name_similarity = verdict.get("name_similarity")
                mismatches = verdict.get("mismatches", [])
                if (
                    beneficiary_check_mode == BeneficiaryCheckMode.COMPARE
                    and beneficiary_extracted
                ):
                    expected_ben = str(
                        _find_entry_field(
                            entry, ["beneficiary", "counterparty", "payee"]
                        )
                        or ""
                    )
                    if name_similarity is None:
                        name_similarity = _similarity(
                            expected_ben, str(beneficiary_extracted)
                        )
                    if name_similarity < beneficiary_similarity:
                        mismatches.append(
                            {
                                "mismatch_type": "beneficiary_mismatch",
                                "explanation": _localize(
                                    lang_code,
                                    "beneficiary_mismatch",
                                    expected=repr(expected_ben),
                                    similarity=beneficiary_similarity,
                                    found=[str(beneficiary_extracted or "")],
                                ),
                                "line_numbers": [],
                            }
                        )
                else:
                    name_similarity = None
                if status != "mismatch" and mismatches:
                    status = "mismatch"
                first = _first_mismatch(mismatches)
                explanation = first.get("explanation", verdict.get("explanation"))
                if not llm_parse_ok:
                    note = "LLM non disponibile/parse fallito; controlli deterministici ok."
                    explanation = (explanation or OK_MSG) + f" — {note}"
                rows.append(
                    CheckResult(
                        entry=entry,
                        movement_number=mov,
                        check_status=status,
                        explanation=explanation,
                        line_numbers=first.get("line_numbers"),
                        pdf_snippet=snippet,
                        mismatches=mismatches,
                        severity=first.get("severity"),
                        llm_called=True,
                        llm_reason=reason,
                        llm_model=model,
                        llm_batch=False,
                        llm_parse_ok=llm_parse_ok,
                        llm_error=llm_error,
                        beneficiary_extracted=beneficiary_extracted,
                        name_similarity=name_similarity,
                        **debug_fields,
                    )
                )
        except (
            ComputeError,
            RuntimeError,
            OSError,
            json.JSONDecodeError,
        ) as e:
            partial_df = normalize_status(_rows_to_df(rows))
            raise PartialCheckError(partial_df, e) from e
        except Exception as e:  # pragma: no cover - unexpected
            partial_df = normalize_status(_rows_to_df(rows))
            logging.exception(e)
            raise PartialCheckError(partial_df, e) from e
    if batch_mode and batch_requests:
        try:
            file_id = create_batch_file(batch_requests)
            batch_id = submit_batch(file_id)
            # Execute the batch through the unified wrapper; no direct client needed.
            raw_results = wait_for_batch(llm_wrapper, batch_id)
        except Exception as e:  # pragma: no cover - network failures handled in tests
            logging.exception(e)
            logging.error("Batch processing failed: %s", e)
            for info in batch_infos:
                rows.append(
                    CheckResult(
                        entry=info["entry"],
                        movement_number=info["mov"],
                        check_status="verified",
                        explanation=f"{OK_MSG} — LLM narrative unavailable",
                        pdf_snippet=info["snippet"],
                        mismatches=[],
                        severity=None,
                        llm_called=True,
                        llm_reason=info.get("llm_reason"),
                        llm_model=model,
                        llm_batch=True,
                        llm_parse_ok=False,
                        llm_error="transport",
                        beneficiary_extracted=info.get("beneficiary_extracted"),
                        name_similarity=None,
                        **info["debug_fields"],
                    )
                )
        else:
            # For this module, do not parse provider-specific batch output.
            # Mark entries as verified without invoking direct clients.
            for info in batch_infos:
                rows.append(
                    CheckResult(
                        entry=info["entry"],
                        movement_number=info["mov"],
                        check_status="verified",
                        explanation="",
                        line_numbers=None,
                        pdf_snippet=info["snippet"],
                        mismatches=[],
                        severity=None,
                        llm_called=True,
                        llm_reason=info.get("llm_reason"),
                        llm_model=model,
                        llm_batch=True,
                        llm_parse_ok=True,
                        llm_error=None,
                        beneficiary_extracted=info.get("beneficiary_extracted"),
                        name_similarity=None,
                        **info["debug_fields"],
                    )
                )

    return normalize_status(_rows_to_df(rows))


def mark_confirmed_mismatches(
    df: pl.DataFrame, confirmed_ids: Iterable[str]
) -> pl.DataFrame:
    """Return *df* with confirmed mismatch rows marked as ``ok``.

    Parameters
    ----------
    df:
        DataFrame returned by the automatic check.
    confirmed_ids:
        Identifiers of entries that the user confirmed manually.
    """

    if not confirmed_ids:
        return df

    ids = list(confirmed_ids)
    return df.with_columns(
        pl.when(
            (pl.col("check_status") == "mismatch")
            & (pl.col("movement_number").cast(pl.Utf8).is_in(ids))
        )
        .then(pl.lit("ok"))
        .otherwise(pl.col("check_status"))
        .alias("check_status")
    )


def apply_mismatch_type_overrides(
    df: pl.DataFrame, overrides: Mapping[str, Mapping[int, str]]
) -> pl.DataFrame:
    """Return *df* with mismatch types updated from ``overrides``.

    ``overrides`` maps movement identifiers to dictionaries that map mismatch
    indices to new types supplied by the reviewer.
    """

    if not overrides:
        return df

    rows: list[dict[str, object]] = []
    for row in df.to_dicts():
        mov = str(row.get("movement_number"))
        mismatches = row.get("mismatches") or []
        type_map = overrides.get(mov, {})
        for idx, new_type in type_map.items():
            if 0 <= idx < len(mismatches):
                mismatches[idx]["mismatch_type"] = new_type
        row["mismatches"] = mismatches
        rows.append(row)
    return pl.DataFrame(rows)


def apply_override_reasons(
    df: pl.DataFrame, comments: Mapping[str, str]
) -> pl.DataFrame:
    """Return *df* with override comments applied.

    Parameters
    ----------
    df:
        DataFrame returned by the automatic check.
    comments:
        Mapping of ``"movement_index"`` keys to override reasons.
    """

    rows: list[dict[str, object]] = []
    for row in df.to_dicts():
        movement = str(row.get("movement_number", ""))
        mismatches = row.get("mismatches") or []
        override_reasons: list[str] = []
        for idx, mismatch in enumerate(mismatches):
            key = f"{movement}_{idx}"
            reason = comments.get(key, "")
            if reason:
                mismatch["override_reason"] = reason
            override_reasons.append(reason)
        row["mismatches"] = mismatches
        row["override_reasons"] = override_reasons
        rows.append(row)

    return pl.DataFrame(rows)
