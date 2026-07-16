"""
Business logic for reconciling bank statements against accounting ledger data.

This module provides functions to load and normalise transaction data from
bank statements and ledger exports, reconcile them using a flexible
matching algorithm, and export the results. It is designed to sit
between the legacy UI and the underlying data extraction utilities.

Key features:

* **Flexible parsing** – Bank statements may arrive as Excel, CSV or PDF;
  ledger exports likewise. Spreadsheets are parsed with Polars (header/mapping
  inference is centralised in ``src.check_statements.loaders``). For PDFs, we
  first attempt fast‑path parsing via loaders (generic parser / bank_agent),
  then fall back to OCR (wrapped by loaders), and optionally call an LLM in
  batch mode to extract tabular data.

* **Robust normalisation** – Dates are parsed in European and ISO
  formats; amounts are normalised from either debit/credit columns or
  a single amount column. Descriptions and beneficiaries are
  trimmed and upper‑cased for matching.

* **Agentic matching** – Transactions are matched in multiple passes
  with configurable tolerance, date window and beneficiary rules. A
  fuzzy score (via rapidfuzz, if available) supplements exact
  matching. Optional group matching allows one bank entry to match
  the sum of several ledger entries, and vice versa.
* **Absolute amount mode** – When sign conventions differ, amounts can
  be compared using their absolute values to match debits with credits.

Parsing and header inference helpers live in ``src.check_statements.loaders``.
This module orchestrates those helpers (including LLM gating/batching) and
intentionally contains no UI imports; it can be reused in other
contexts (tests, APIs, etc.).
interface.

Author: OpenAI ChatGPT assistant
"""

from __future__ import annotations

import csv
import io
import itertools
import json
import logging
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import re
import math
from datetime import date, datetime, timedelta
from typing import (
    Any,
    Callable,
    Dict,
    Hashable,
    Iterable,
    Iterator,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

import polars as pl
import pdfplumber
from pdfminer.pdfparser import PDFSyntaxError

from src.check_statements.normalisation import (
    _amount_expr,
    _clean_description_local,
    _norm_token,
    _parse_amount,
    _parse_date,
    _parse_date_any,
    _parse_dates_expr,
    _similarity,
    _token_intersection_ratio,
    beneficiary_similarity,
)

logger = logging.getLogger(__name__)

# Tolerant import: tests may shadow the real 'modules' package with partial stubs
try:
    from modules.utilities.cache import get_cache_dir, get_cache_path
except Exception:  # pragma: no cover - fallback for isolated tests
    logger.warning("modules.utilities.cache import failed; using fallback cache helpers")

    def get_cache_dir(*parts: str) -> Path:  # type: ignore
        base = Path(".cache_fallback")
        for p in parts:
            base = base / p
        base.mkdir(parents=True, exist_ok=True)
        return base

    def get_cache_path(name: str) -> Path:  # type: ignore
        return get_cache_dir().parent / name


from parsers.extractors import (
    extract_beneficiary,
    extract_references,
    normalise_name,
)

from .bank_keywords import BASE_BANK_KEYWORDS

# These imports reference existing modules in the mparenza codebase.
# When integrating into the application, ensure that the correct
# module paths are used.  We guard imports with try/except so the
# module can still be imported in isolation (e.g. during unit tests).
try:
    from modules.pdf_utils.pdf_utils import extract_pdf_text_with_ocr
except ImportError:
    extract_pdf_text_with_ocr = None  # type: ignore

try:
    from modules.process_pdf_journal.logic import parse_journal
except ImportError:
    parse_journal = None  # type: ignore

try:
    from modules.utilities.config import get_naming_params, get_run_params
except Exception:  # pragma: no cover - fallback for unit tests
    logger.warning("modules.utilities.config not available; using empty run/naming params")

    def get_naming_params() -> dict:  # type: ignore
        return {}

    def get_run_params() -> dict:  # type: ignore
        return {}


try:
    from modules.utilities.utils import get_row_count, get_schema_and_column_names
except Exception:  # pragma: no cover
    logger.warning("modules.utilities.utils not available; using lightweight stubs")

    def get_row_count(df):  # type: ignore
        return getattr(df, "height", 0)

    def get_schema_and_column_names(df):  # type: ignore
        return (getattr(df, "columns", []), getattr(df, "schema", {}))


try:
    from modules.utils.polars_excel_writer import _prepare_df_for_excel
except Exception:  # pragma: no cover
    logger.warning("polars_excel_writer not available; exporting without normalization")

    def _prepare_df_for_excel(df):  # type: ignore
        return df

# Final-pass cleaner for unmatched bank rows (module-level to allow monkeypatching)
try:
    from .final_pass_filter import FilterReport, clean_bank_not_matched  # type: ignore
except Exception:  # pragma: no cover - fallback for unit tests
    logger.warning("final_pass_filter not available; proceeding without bank cleanup filter")

    class FilterReport:  # type: ignore
        def __init__(self, *a, **k):
            pass

    def clean_bank_not_matched(df, *a, **k):  # type: ignore
        return df

try:
    from statements.orchestrator import StatementExtractor
except Exception:  # pragma: no cover - tests without statements package
    logger.info("StatementExtractor not available; PDF extraction disabled")

    class StatementExtractor:  # type: ignore
        def orchestrate(self, *a, **k):  # noqa: D401
            return [], {}


try:
    from modules.pdf_utils.bank_agent import BankTransaction, extract_bank_pdf
except ImportError:
    extract_bank_pdf = None  # optional dependency

try:
    from parsers.generic_statement import GenericStatementParser
except ImportError:  # pragma: no cover - optional dependency
    GenericStatementParser = None  # type: ignore
from finance.ledger.ignore_patterns import load_ignore_patterns

# Import extracted filter helpers (API re-exports below maintain compatibility)
from src.check_statements.filters import (
    load_fee_patterns as _load_fee_patterns_impl,
    _preaggregate_bank_transactions as _preaggregate_bank_transactions,
    _early_filter_bank_transactions as _early_filter_bank_transactions,
)
from src.check_statements.classify import (
    classify_op,
    extract_iban as _extract_iban,
    is_tax_ledger_entry as _is_tax_ledger_entry,
    _lex_for,
)
from src.check_statements.matching import (
    _txns_to_polars,
    _pairs_from_candidates,
    _build_bank_candidates,
    _assignment_pass,
    _exact_pass,
    _fuzzy_score,
    _fuzzy_pass,
    _fuzzy_margin_pass,
    _reference_substring_pass,
    _group_match,
)
from src.check_statements.reconcile_pipeline import (
    _group_match_local,
    _stage2_fixers_and_routing,
    staged_reconcile,
)
from src.check_statements.loaders import (
    _detect_excel_header_polars,
    _rebuild_df_with_header,
    _infer_columns,
    _resolve_account_col,
    guess_columns_from_data,
    parse_spreadsheet_prepare as parse_spreadsheet_prepare_extracted,
    parse_spreadsheet_prepare_with_keywords as parse_spreadsheet_prepare_with_keywords_extracted,
    ocr_extract_pdf_text as ocr_extract_pdf_text_extracted,
    _resolve_mapping,
    _validate_required_columns,
    parse_pdf_prepare as parse_pdf_prepare_extracted,
    load_ledger_rows as load_ledger_rows_extracted,
    load_bank_rows as load_bank_rows_extracted,
    parse_bank_text_prepare as parse_bank_text_prepare_extracted,
)
from src.check_statements.models import Transaction


# ---------------------------------------------
# Operation classification and metadata helpers
# ---------------------------------------------




def _write_temp_file(filename: str, content: bytes) -> Path:
    """Persist uploaded content to a temporary file and return its path.

    The caller is responsible for deleting the file unless using
    :func:`_temp_file`.
    """
    suffix = Path(filename).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(content)
    tmp_path = Path(tmp.name)
    tmp.close()
    return tmp_path


@contextmanager
def _temp_file(filename: str, content: bytes) -> Iterator[Path]:
    """Yield a temporary file path that is deleted on context exit."""
    path = _write_temp_file(filename, content)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


# Trigger LLM fallback when the heuristic finds too few transactions
LLM_RATIO_THRESHOLD: float = 0.25  # e.g. 25 % of date lines
LLM_MIN_TRANSACTIONS: int = 10  # absolute minimum number of parsed rows

# Keywords that may denote account identifier columns in input files.
# Extend this list with synonyms used in specific ledgers (e.g. "iban", "acct").
ACCOUNT_COL_KEYWORDS: list[str] = ["conto", "account", "acct", "iban"]


_DESCRIPTION_CACHE_PATH = get_cache_path("description_cache.json")
try:
    _DESCRIPTION_CACHE: Dict[str, str] = json.loads(
        _DESCRIPTION_CACHE_PATH.read_text(encoding="utf-8")
    )
except FileNotFoundError:
    _DESCRIPTION_CACHE = {}


## Lexicon loaders moved to src.check_statements.classify


def load_fee_patterns(path: Path | None = None) -> List[re.Pattern]:
    """Compatibility shim to the extracted helper in src.check_statements.filters."""
    return _load_fee_patterns_impl(path)


# Header keywords and normalization have moved to src.check_statements.loaders


## header/mapping helpers are imported directly from src.check_statements.loaders


def _find_column(headers: list[str], candidates: set[str]) -> str | None:
    """Return the first header whose normalized token equals/contains one of candidates."""
    # build normalized map once
    norm_map = {h: _norm_token(h) for h in headers}
    for h, n in norm_map.items():
        for c in candidates:
            if n == c or c in n:
                return h
    return None


## Transaction class moved to src.check_statements.models


def _enrich_transaction(tx: Transaction) -> Transaction:
    """Populate reference IDs and normalised beneficiary."""
    # Collect additional text sources for robust extraction
    meta = tx.metadata or {}
    extra_texts: list[str] = []
    for key in (
        "account_desc",
        "account_name",
        "note",
        "notes",
        "narrative",
        "riferimento",
        "reference",
        "details",
        "extra_desc",
        "descr. agg",
        "descrizione agg",
        "descrizione aggiuntiva",
    ):
        v = meta.get(key)
        if isinstance(v, str) and v.strip():
            extra_texts.append(v)
    combined_text = "\n".join([tx.description or ""] + extra_texts)
    # Extract references from description + metadata text
    refs = extract_references(combined_text)
    if tx.reference_ids:
        # union and dedupe preserving order
        seen = set()
        merged: list[str] = []
        for r in list(tx.reference_ids) + list(refs):
            if r not in seen:
                seen.add(r)
                merged.append(r)
        tx.reference_ids = merged
    else:
        tx.reference_ids = refs
    # Prefer explicit beneficiary field; then try description; finally include
    # supplemental text (extra_desc/details/account_desc) as a fallback to help
    # ledger entries where the vendor appears after an invoice token.
    ben = tx.beneficiary or extract_beneficiary(tx.description) or extract_beneficiary(combined_text)
    tx.beneficiary = normalise_name(ben) if ben else None
    # Extract IBAN and classify operation type for downstream matching
    try:
        iban = _extract_iban(combined_text)
        if iban:
            tx.metadata.setdefault("iban", iban)
    except Exception:  # nosec - defensive
        pass
    try:
        # Use combined text (includes extra_desc/counter_account_desc/details)
        # so ATM/card/tax cues present in supplemental columns are considered.
        lang_hint = None
        try:
            if isinstance(meta, Mapping):
                lang_hint = meta.get("language") or meta.get("lang")
        except Exception:
            lang_hint = None
        op = classify_op(combined_text, lang_hint)
        tx.metadata.setdefault("op_type", op)
    except Exception:  # nosec - defensive
        pass
    try:
        if _is_tax_ledger_entry(tx):
            tx.metadata.setdefault("tax_flag", True)
    except Exception:  # nosec - defensive
        pass
    return tx




# ------------------------
# Bank pre-aggregation (fee folding)
# ------------------------

# moved to src.check_statements.filters: _preaggregate_bank_transactions, _early_filter_bank_transactions


def detect_bank_accounts(ledger_txns: list[Transaction]) -> list[dict]:
    """Heuristically detect ledger bank accounts.

    Ranks by occurrence count and presence of bank-like tokens in account name/desc.
    Returns a list of dicts: {account_id, account_name, count, score} sorted by score.
    """
    from collections import Counter

    acc_counter: Counter = Counter()
    acc_names: dict[str | int, str] = {}
    for tx in ledger_txns:
        meta = tx.metadata or {}
        acc = meta.get("account_id") or meta.get("account_identifier")
        if acc is None:
            continue
        acc_counter[acc] += 1
        nm = meta.get("account_desc") or meta.get("account_name") or ""
        if isinstance(nm, str):
            acc_names.setdefault(acc, nm)
    results: list[dict] = []
    for acc, cnt in acc_counter.items():
        nm = acc_names.get(acc, "")
        blob = f"{acc} {nm}".lower()
        bankish = any(t in blob for t in ("banca", "bank", "c/c", "conto", "iban"))
        score = cnt + (5 if bankish else 0)
        results.append(
            {
                "account_id": acc,
                "account_name": nm,
                "count": int(cnt),
                "score": int(score),
            }
        )
    return sorted(results, key=lambda d: (-d["score"], str(d["account_id"])))


def enrich_bank_ledger_entry_with_counterparty(
    ledger_bank_entry: Transaction, journal_lookup: dict | None = None
) -> None:
    """Best-effort enrichment: set tax_flag/IBAN/counterparty from journal info.

    This is a lightweight helper; callers may pass a small lookup for the journal
    entry to peek at offset lines. If not provided, we rely on description heuristics.
    """
    meta = ledger_bank_entry.metadata or {}
    if journal_lookup:
        jid = meta.get("journal_id") or meta.get("prima_nota")
        if jid in journal_lookup:
            j = journal_lookup[jid]
            if isinstance(j, Mapping):
                for k in ("counterparty_iban", "counterparty_name", "invoice_no"):
                    v = j.get(k)
                    if v and isinstance(v, str):
                        meta.setdefault(k, v)
                if j.get("tax_flag") is True:
                    meta.setdefault("tax_flag", True)
    # Always set tax_flag if description smells like tax
    if _is_tax_ledger_entry(ledger_bank_entry):
        meta.setdefault("tax_flag", True)
    ledger_bank_entry.metadata = meta


def reconcile_bank_only(
    bank_txns: list[Transaction],
    ledger_txns: list[Transaction],
    selected_account_id: str,
    opts: "MatchOptions",
) -> "RecoResult":
    """Bank-side-only reconciliation wrapper returning structured diagnostics.

    Filters the ledger to the chosen bank account and runs the existing matcher.
    Builds evidence metadata per match and basic diagnostics.
    """
    from .types import MatchOptions, RecoResult  # local import to avoid cycles

    # Filter ledger candidates to selected account
    selected_norm = selected_account_id.strip().casefold()
    ledger_filtered: list[Transaction] = []
    l_map: list[int] = []
    for idx, tx in enumerate(ledger_txns):
        meta = tx.metadata or {}
        acc = meta.get("account_id") or meta.get("account_identifier")
        if isinstance(acc, str) and acc.strip().casefold() == selected_norm:
            ledger_filtered.append(tx)
            l_map.append(idx)
    matched_pairs, ub, ul = reconcile_transactions(
        bank_txns,
        ledger_filtered,
        tolerance=float(opts.amount_tolerance_abs),
        date_window=int(opts.date_window_days),
        beneficiary_mode=str(opts.beneficiary_mode),
        fuzzy_threshold=float(opts.beneficiary_threshold * 100.0),
        group_limit=int(opts.group_limit),
        use_absolute_amounts=bool(opts.use_absolute_amounts),
        fee_mode=str(opts.fee_mode),
        llm_enabled=opts.llm_enabled,
        llm_auto_threshold_abs=opts.llm_auto_threshold_abs,
        llm_auto_threshold_pct=opts.llm_auto_threshold_pct,
        group_candidates_cap=opts.group_candidates_cap,
        max_combos_per_bank=opts.max_combos_per_bank,
        group_time_budget_ms=opts.group_time_budget_ms,
    )
    # Build meta evidence per pair
    structured: list[tuple[int, tuple[int, ...], dict]] = []
    for bi, li, how in matched_pairs:
        b = bank_txns[bi]
        lis = li if isinstance(li, tuple) else (li,)
        for li2 in lis:
            if li2 is None:
                evidence = {"method": how, "evidence": {"fee": True}}
                structured.append((bi, (li2,), evidence))
                continue
            l = ledger_filtered[li2]
            ev: dict[str, object] = {}
            # evidence signals
            if set(b.reference_ids) & set(l.reference_ids):
                ev["hard_id"] = True
            b_iban = (b.metadata or {}).get("iban")
            l_iban = (l.metadata or {}).get("iban")
            if b_iban and l_iban and b_iban == l_iban:
                ev["iban"] = True
            sim = beneficiary_similarity(
                b.normalised_beneficiary(), l.normalised_beneficiary()
            )
            if sim:
                ev["beneficiary"] = round(float(sim), 3)
            b_type = (b.metadata or {}).get("op_type") or classify_op(b.description)
            ev["type"] = b_type
            structured.append((bi, (l_map[li2],), {"method": how, "evidence": ev}))

    diags = {
        "bank_rows": len(bank_txns),
        "ledger_rows": len(ledger_filtered),
        "matched_count": len(structured),
        "unmatched_bank_count": len(ub),
        "unmatched_ledger_count": len([x for x in ul if x is not None]),
    }
    return RecoResult(structured, ub, [x for x in ul if isinstance(x, int)], diags)


def _coverage(rows: Iterable[Transaction]) -> Dict[str, Any]:
    """Return date coverage information for the given transactions."""
    dates = [r.date for r in rows if getattr(r, "date", None)]
    if not dates:
        return {"count": 0, "min": None, "max": None, "months": []}
    months = sorted({d.strftime("%Y-%m") for d in dates})
    return {"count": len(dates), "min": min(dates), "max": max(dates), "months": months}


def _filter_accounts(
    rows: Iterable[Transaction], exclude_accounts: Iterable[Hashable] | None
) -> List[Transaction]:
    """Return ``rows`` excluding any with a matching metadata account.

    Transactions are filtered out when their ``metadata`` dictionary contains an
    ``account_id`` or ``account_identifier`` present in ``exclude_accounts``. Rows
    lacking these keys are retained.
    """
    if not exclude_accounts:
        return list(rows)
    exclude_set: set[Hashable] = set()
    for acc in exclude_accounts:
        if isinstance(acc, str):
            acc = acc.strip()
            if not acc:
                continue
            exclude_set.add(acc.casefold())
        else:
            exclude_set.add(acc)

    filtered: List[Transaction] = []
    for tx in rows:
        meta = tx.metadata if isinstance(tx.metadata, Mapping) else {}
        acc_id = meta.get("account_id") or meta.get("account_identifier")
        if isinstance(acc_id, str):
            acc_id = acc_id.strip()
            acc_norm: Hashable | None = acc_id.casefold() if acc_id else None
        else:
            acc_norm = acc_id
        # Keep transactions without an account identifier or those not excluded
        if acc_norm not in exclude_set:
            filtered.append(tx)
    return filtered


def auto_filter_overlap(
    bank_rows: Sequence[Transaction],
    ledger_rows: Sequence[Transaction],
) -> Optional[Tuple[List[Transaction], List[Transaction], Dict[str, Any]]]:
    """Filter both sides to their overlapping date range, if any.

    Returns ``None`` if there is no date overlap."""

    if not bank_rows or not ledger_rows:
        return None
    bank_dates = [t.date for t in bank_rows]
    ledger_dates = [t.date for t in ledger_rows]
    bank_min, bank_max = min(bank_dates), max(bank_dates)
    ledger_min, ledger_max = min(ledger_dates), max(ledger_dates)
    start = max(bank_min, ledger_min)
    end = min(bank_max, ledger_max)
    if start > end:
        return None
    bank_f = [t for t in bank_rows if start <= t.date <= end]
    ledger_f = [t for t in ledger_rows if start <= t.date <= end]
    diagnostics = {
        "bank_range": (bank_min, bank_max),
        "ledger_range": (ledger_min, ledger_max),
        "overlap": (start, end),
    }
    return bank_f, ledger_f, diagnostics


# ---------------------------------------------------------------------------
# Ledger PDF fallback helpers (text-mode parsing)
# ---------------------------------------------------------------------------


_LEDGER_DATE_RE = re.compile(r"^(\d{2}-\d{2}-\d{4})\b")
_LEDGER_AMOUNT_RE = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")
_LEDGER_SKIP_PREFIXES = (
    "MASTRINO CONTABILE",
    "ESERCIZIO ",
    "REGISTRAZIONI ",
    "REGIME CONTABILE",
    "LEGENDA",
    "DATA REG.",
    "PROGRESSIVO MOVIMENTI",
    "AGO -",
)


def _ledger_amount_to_float(token: str) -> float:
    token = token.replace(".", "").replace(",", ".")
    try:
        return float(token)
    except ValueError:
        return float("nan")


def _is_probable_counter_code(token: str) -> bool:
    """Heuristically decide whether ``token`` looks like a ledger counter ID."""

    candidate = token.strip()
    if not candidate or any(char.isspace() for char in candidate):
        return False

    normalized = candidate.replace("/", "").replace(".", "")
    if not normalized or not normalized.isalnum():
        return False

    if any(char.isdigit() for char in normalized):
        return True

    return candidate.isupper() and len(normalized) <= 4


def _extract_counterparty_code_and_name(
    counter_desc_raw: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Split ledger counterparty tokens while avoiding ordinary hyphenated names."""

    cleaned = counter_desc_raw.strip()
    if not cleaned:
        return None, None
    if "-" not in cleaned:
        return None, cleaned

    code_part, name_part = cleaned.split("-", 1)
    code_candidate = code_part.strip()
    name_candidate = name_part.strip()
    if not name_candidate:
        return None, cleaned

    if _is_probable_counter_code(code_candidate):
        return code_candidate or None, name_candidate or None

    if not code_candidate:
        return None, name_candidate or None

    return None, cleaned


def _parse_ledger_pdf_text_fallback(
    content: bytes,
    filename: str,
    month: Optional[int],
    year: Optional[int],
    *,
    language: Optional[str] = None,
) -> List[Transaction]:
    """Heuristic parser for ledger-style PDFs when structured parser is unavailable."""

    if pdfplumber is None:
        logger.debug("pdfplumber not available; ledger text fallback skipped for %s", filename)
        return []

    lines: List[str] = []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                lines.extend(text.splitlines())
    except Exception as exc:  # pragma: no cover - pdf parsing best effort
        logger.warning("Ledger PDF text fallback failed to read %s: %s", filename, exc)
        return []

    transactions: List[Transaction] = []
    prev_balance: Optional[float] = None

    def _should_skip(line: str) -> bool:
        up = line.upper()
        return any(up.startswith(prefix) for prefix in _LEDGER_SKIP_PREFIXES)

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if _should_skip(line):
            if "PROGRESSIVO MOVIMENTI" in line.upper():
                amounts = _LEDGER_AMOUNT_RE.findall(line)
                if amounts:
                    prev_balance = _ledger_amount_to_float(amounts[-1])
            continue

        if line.upper().startswith("SALDO ESERCIZIO PRECEDENTE"):
            amounts = _LEDGER_AMOUNT_RE.findall(line)
            if amounts:
                prev_balance = _ledger_amount_to_float(amounts[-1])
            continue

        date_match = _LEDGER_DATE_RE.match(line)
        if not date_match:
            continue

        amounts = _LEDGER_AMOUNT_RE.findall(line)
        if len(amounts) < 2:
            continue

        date_str = date_match.group(1)
        date_val = _parse_date_any(date_str)
        if not date_val:
            continue
        if month and date_val.month != month:
            prev_balance = _ledger_amount_to_float(amounts[-1])
            continue
        if year and date_val.year not in {year, year % 100}:
            prev_balance = _ledger_amount_to_float(amounts[-1])
            continue

        amount_token = amounts[0]
        balance_token = amounts[-1]
        amount_val = _ledger_amount_to_float(amount_token)
        balance_val = _ledger_amount_to_float(balance_token)
        if math.isnan(balance_val):
            prev_balance = None
            continue

        head_end = line.find(amount_token)
        if head_end == -1:
            prev_balance = balance_val
            continue
        description_part = line[:head_end].strip()
        description_text = description_part[len(date_str) :].strip()
        description_text = re.sub(r"\s{2,}", " ", description_text)

        tail = line.split(balance_token, 1)[1].strip()
        section: Optional[str] = None
        counter_desc_raw = ""
        if tail:
            if tail[0] in {"A", "D"} and (len(tail) == 1 or tail[1].isspace()):
                section = tail[0]
                counter_desc_raw = tail[1:].strip()
            else:
                section = None
                counter_desc_raw = tail
        counter_desc_raw = counter_desc_raw.strip()
        counter_code: Optional[str] = None
        counter_name: Optional[str] = None
        if counter_desc_raw:
            counter_code, counter_name = _extract_counterparty_code_and_name(counter_desc_raw)
        counter_desc = counter_name or counter_desc_raw.strip("- ")

        signed_amount: float
        delta = None
        if prev_balance is not None and not math.isnan(prev_balance):
            delta = round(balance_val - prev_balance, 2)

        if delta is not None and not math.isnan(delta) and abs(delta) >= 0.005:
            signed_amount = delta
            if abs(abs(delta) - amount_val) > 0.05 and not math.isnan(amount_val):
                if section in {"A", "D"}:
                    signed_amount = amount_val if section == "D" else -amount_val
        else:
            if section in {"A", "D"} and not math.isnan(amount_val):
                signed_amount = amount_val if section == "D" else -amount_val
            else:
                signed_amount = amount_val if not math.isnan(amount_val) else 0.0

        prev_balance = balance_val

        metadata: Dict[str, Any] = {"source": filename, "language": language}
        if counter_desc:
            metadata["counter_account_desc"] = counter_desc
        if counter_code:
            metadata["counter_account_id"] = counter_code
        if counter_desc and "cassa" in counter_desc.lower() and "contanti" in counter_desc.lower():
            metadata["counter_account_is_cash"] = True
        metadata["ledger_section"] = section
        metadata["ledger_balance"] = balance_val
        metadata["raw_line"] = raw_line

        beneficiary_name = counter_desc
        if beneficiary_name:
            beneficiary_name = beneficiary_name.strip()
            if beneficiary_name == "" or beneficiary_name.lower() in {"", "beneficiari diversi", "beneficiari diversi - commissioni"}:
                beneficiary_name = None

        transactions.append(
            _enrich_transaction(
                Transaction(
                    date=date_val,
                    amount=float(signed_amount),
                    description=description_text,
                    beneficiary=beneficiary_name,
                    metadata=metadata,
                )
            )
        )

    return transactions


# (Removed) OpenAI batch response parsing is no longer needed; queries are routed
# via the unified model router instead of direct batch/client calls.


def _postprocess_rows(
    df: pl.DataFrame,
    mapping: Dict[str, str],
    month: Optional[int],
    year: Optional[int],
    filename: str,
    *,
    language: Optional[str] = None,
) -> List[Transaction]:
    """Vectorise row parsing into ``Transaction`` objects.

    Dates and amounts are parsed in bulk using Polars expressions.  Optional
    month/year filters are then applied before converting the remaining rows
    into :class:`Transaction` instances.
    """

    columns, _ = get_schema_and_column_names(df)
    available_columns = set(columns)

    if "date" not in mapping or mapping["date"] not in available_columns:
        return []

    date_col = mapping["date"]
    try:
        df = df.with_columns(_parse_dates_expr(date_col).alias("__booking_date"))
    except pl.exceptions.ComputeError:
        parsed_dates = [
            _parse_date_any(value)
            for value in df.get_column(date_col)
        ]
        df = df.with_columns(pl.Series("__booking_date", parsed_dates))

    if "amount" in mapping and mapping["amount"] in available_columns:
        df = df.with_columns(_amount_expr(mapping["amount"]).alias("__amount"))
    elif (
        ("debit" in mapping and mapping["debit"] in available_columns)
        or ("credit" in mapping and mapping["credit"] in available_columns)
    ):
        exprs: List[pl.Expr] = []
        if "debit" in mapping and mapping["debit"] in available_columns:
            exprs.append(_amount_expr(mapping["debit"]).alias("__debit"))
        else:
            exprs.append(pl.lit(None).alias("__debit"))
        if "credit" in mapping and mapping["credit"] in available_columns:
            exprs.append(_amount_expr(mapping["credit"]).alias("__credit"))
        else:
            exprs.append(pl.lit(None).alias("__credit"))
        df = df.with_columns(exprs).with_columns(
            (
                pl.coalesce(pl.col("__credit"), pl.lit(0.0))
                - pl.coalesce(pl.col("__debit"), pl.lit(0.0))
            ).alias("__amount")
        )
    else:
        return []

    desc_expr: pl.Expr = pl.lit("").alias("__description")
    if "description" in mapping and mapping["description"] in available_columns:
        desc_expr = (
            pl.col(mapping["description"])
            .cast(pl.Utf8, strict=False)
            .alias("__description")
        )

    ben_expr: pl.Expr = pl.lit(None).alias("__beneficiary")
    if "beneficiary" in mapping and mapping["beneficiary"] in available_columns:
        ben_expr = (
            pl.col(mapping["beneficiary"])
            .cast(pl.Utf8, strict=False)
            .alias("__beneficiary")
        )

    df = df.with_columns([desc_expr, ben_expr])

    df = df.filter(pl.col("__booking_date").is_not_null())
    df = df.filter(pl.col("__amount").is_not_null())

    if month is not None:
        df = df.filter(pl.col("__booking_date").dt.month() == month)
    if year is not None:
        df = df.filter(
            (pl.col("__booking_date").dt.year() == year)
            | ((pl.col("__booking_date").dt.year() % 100) == year)
        )

    rows = df.select(
        ["__booking_date", "__amount", "__description", "__beneficiary"]
    ).to_dicts()

    transactions = [
        _enrich_transaction(
            Transaction(
                date=row["__booking_date"],
                amount=float(row["__amount"]),
                description=(row["__description"] or "").strip(),
                beneficiary=(
                    row["__beneficiary"].strip() if row["__beneficiary"] else None
                ),
                metadata={"source": filename, "language": language},
            )
        )
        for row in rows
    ]

    try:  # optional keyword sign inference
        from parsers.normalization import infer_direction

        for tx in transactions:
            inferred = infer_direction(tx.description)
            if inferred == "credit":
                tx.amount = abs(tx.amount)
            elif inferred == "debit":
                tx.amount = -abs(tx.amount)
    except ImportError:  # pragma: no cover - optional dependency
        pass

    # Post-process: infer counter-account description by journal/registration id
    try:
        by_journal: dict[str, list[int]] = {}
        for idx, tx in enumerate(transactions):
            meta = tx.metadata or {}
            jid = meta.get("journal_id")
            if isinstance(jid, str) and jid.strip():
                by_journal.setdefault(jid.strip(), []).append(idx)

        def _is_bankish(text: str) -> bool:
            t = (text or "").upper()
            return any(k in t for k in ("BANCA", "BANK", "C/C", "CONTO", "IBAN"))

        for idxs in by_journal.values():
            if len(idxs) < 2:
                continue
            rows = []
            for i in idxs:
                meta = transactions[i].metadata or {}
                aid = meta.get("account_id")
                adesc = meta.get("account_desc") or meta.get("account_name") or ""
                rows.append((i, aid, adesc, float(transactions[i].amount)))
            for i, aid, _adesc, _amt in rows:
                others = [
                    (j, jad, jdesc, jamt)
                    for (j, jad, jdesc, jamt) in rows
                    if j != i and (jad is None or jad != aid)
                ]
                if not others:
                    continue
                non_bank = [o for o in others if not _is_bankish(o[2])]
                cand_list = non_bank or others
                j_best = max(cand_list, key=lambda x: abs(x[3]))
                counter_desc = j_best[2] or ""
                if counter_desc and isinstance(transactions[i].metadata, dict):
                    transactions[i].metadata.setdefault(
                        "counter_account_desc", counter_desc
                    )
        # Fallback: pair exact opposite entries by (date, abs(amount)) when journal id is missing
        from collections import defaultdict

        pairs: dict[tuple, list[int]] = defaultdict(list)
        for idx, tx in enumerate(transactions):
            meta = tx.metadata or {}
            if meta.get("journal_id"):
                continue
            key = (tx.date, round(abs(float(tx.amount)), 2))
            pairs[key].append(idx)
        for key, idxs in pairs.items():
            if len(idxs) != 2:
                continue
            i1, i2 = idxs
            a1 = (
                transactions[i1].metadata.get("account_id")
                if isinstance(transactions[i1].metadata, dict)
                else None
            )
            a2 = (
                transactions[i2].metadata.get("account_id")
                if isinstance(transactions[i2].metadata, dict)
                else None
            )
            if a1 and a2 and a1 == a2:
                continue
            d1 = (
                transactions[i2].metadata.get("account_desc")
                if isinstance(transactions[i2].metadata, dict)
                else None
            ) or ""
            d2 = (
                transactions[i1].metadata.get("account_desc")
                if isinstance(transactions[i1].metadata, dict)
                else None
            ) or ""
            if isinstance(transactions[i1].metadata, dict) and d1:
                transactions[i1].metadata.setdefault("counter_account_desc", d1)
            if isinstance(transactions[i2].metadata, dict) and d2:
                transactions[i2].metadata.setdefault("counter_account_desc", d2)
    except Exception as exc:
        logger.debug("Counter-account inference skipped: %s", exc)
    return transactions


def _parse_spreadsheet(
    content: bytes,
    filename: str,
    month: Optional[int],
    year: Optional[int],
    *,
    language: Optional[str] = None,
) -> List[Transaction]:
    """Parse spreadsheet bank statement using extracted helpers + postprocess."""
    if pl is None:
        raise ImportError("polars is required to parse spreadsheets")
    df, mapping = parse_spreadsheet_prepare_extracted(content, filename, max_header_scan_rows=50)
    if df is None or df.height == 0:
        logger.debug("No data found in %s", filename)
        return []
    columns, _ = get_schema_and_column_names(df)
    resolved = _resolve_mapping(columns, mapping)
    _validate_required_columns(resolved)
    return _postprocess_rows(df, resolved, month, year, filename, language=language)


def _parse_pdf_with_ocr(
    content: bytes,
    filename: str,
    month: Optional[int],
    year: Optional[int],
    llm: Optional[Any],
    language: str,
    ocr_retries: int,
    use_llm_threshold: float,
    progress_callback: Callable[[float, int, Tuple[date, date]], None] | None = None,
    strict: bool = False,
) -> List[Transaction]:
    """Extract transactions from a PDF using deterministic loaders and OCR."""
    logger.debug("Parsing %s as PDF", filename)
    try:
        fast_rows = parse_pdf_prepare_extracted(
            content,
            filename,
            language=language,
            deterministic_only=(llm is None),
            progress_callback=progress_callback,
            strict=strict,
        )
    except Exception:
        fast_rows = []
    if fast_rows:
        out: List[Transaction] = []
        for r in fast_rows:
            try:
                out.append(
                    _enrich_transaction(
                        Transaction(
                            date=r.get("date"),
                            amount=float(r.get("amount", 0.0)),
                            description=str(r.get("description", "")),
                            reference_ids=list(r.get("reference_ids", []) or []),
                            beneficiary=(r.get("beneficiary") or None),
                            metadata={"source": filename, "language": language},
                        )
                    )
                )
            except Exception:
                continue
        return out

    text = ""
    try:
        text = ocr_extract_pdf_text_extracted(
            content, llm_wrapper=llm, language=language, retries=ocr_retries
        )
    except (OSError, RuntimeError) as exc:
        logger.warning("OCR extraction failed for %s: %s", filename, exc)

    parsed_rows: List[Transaction] = _parse_bank_text(text, filename, month, year, language) if text else []

    if not parsed_rows:
        logger.debug("No transactions extracted from %s", filename)
    return parsed_rows


def load_bank_files(
    files: Iterable[Tuple[str, bytes]],
    month: Optional[int] = None,
    year: Optional[int] = None,
    llm: Optional[Any] = None,
    language: str = "ita",
    ocr_retries: int = 2,
    use_llm_threshold: float | None = None,
    llm_batch_size: int = 10,
    strict: bool = False,
    progress_callback: (
        Callable[[float, float, int, Tuple[date, date], str], None] | None
    ) = None,
) -> List[Transaction]:
    """Load and parse bank statement files into a list of Transactions.

    Args:
        strict: When ``True``, propagate parser errors instead of falling back
            to legacy parsing strategies.
        progress_callback: Optional function invoked during PDF processing with
            ``(global_progress, file_progress, rows_so_far, date_range, filename)``.
            If ``None`` behaviour is unchanged.
    """
    files = list(files)
    total_files = len(files) if files else 1
    run_params = get_run_params()
    transactions: List[Transaction] = []
    file_index = 0
    for filename, content in files:
        lower = filename.lower()
        if lower.endswith((".xlsx", ".xls", ".csv")):
            logger.debug("Processing %s as spreadsheet", filename)
            before = len(transactions)
            transactions.extend(
                _parse_spreadsheet(
                    content, filename, month, year, language=language
                )
            )
            if len(transactions) == before:
                with _temp_file(filename, content) as tmp:
                    extra, _ = StatementExtractor().orchestrate(tmp, {})
                    transactions.extend(extra)
        elif lower.endswith(".pdf"):
            logger.debug("Processing %s as PDF", filename)
            before = len(transactions)

            def wrapper(
                file_progress: float, rows_so_far: int, date_range: Tuple[date, date]
            ) -> None:
                if progress_callback:
                    global_progress = (file_index + file_progress) / total_files
                    progress_callback(
                        global_progress,
                        file_progress,
                        rows_so_far,
                        date_range,
                        filename,
                    )

            transactions.extend(
                _parse_pdf_with_ocr(
                    content,
                    filename,
                    month,
                    year,
                    llm,
                    language,
                    ocr_retries,
                    use_llm_threshold,
                    progress_callback=wrapper,
                    strict=strict,
                )
            )
            if len(transactions) == before:
                with _temp_file(filename, content) as tmp:
                    extra, _ = StatementExtractor().orchestrate(tmp, {})
                    transactions.extend(extra)
        else:
            logger.debug("Skipping unsupported file %s", filename)
        file_index += 1
    return transactions


def _parse_bank_text(
    text: str, filename: str, month: Optional[int], year: Optional[int], language: Optional[str] = None
) -> List[Transaction]:
    """Wrapper around loaders.parse_bank_text_prepare that returns Transactions."""
    rows = parse_bank_text_prepare_extracted(text, filename, month, year, language)
    out: List[Transaction] = []
    for r in rows:
        try:
            out.append(
                _enrich_transaction(
                    Transaction(
                        date=r.get("date"),
                        amount=float(r.get("amount", 0.0)),
                        description=str(r.get("description", "")),
                        beneficiary=(r.get("beneficiary") or None),
                        metadata=dict(r.get("metadata", {}) or {}),
                    )
                )
            )
        except Exception:
            continue
    return out


def _finalise_bank_row(
    row: Dict[str, Any], filename: str, month: Optional[int], year: Optional[int], language: Optional[str] = None
) -> Optional[Transaction]:
    """Compatibility wrapper that delegates to loaders and builds Transaction."""
    try:
        # Lazily import to avoid circulars if any
        from src.check_statements.loaders import _finalise_bank_row_prepare as _prep  # type: ignore
    except Exception:
        _prep = None  # type: ignore
    if _prep is None:
        return None
    r = _prep(row, filename, month, year, language)
    if not r:
        return None
    try:
        return _enrich_transaction(
            Transaction(
                date=r.get("date"),
                amount=float(r.get("amount", 0.0)),
                description=str(r.get("description", "")),
                beneficiary=(r.get("beneficiary") or None),
                metadata=dict(r.get("metadata", {}) or {}),
            )
        )
    except Exception:
        return None


def load_ledger_files(
    files: Iterable[Tuple[str, bytes]],
    month: Optional[int] = None,
    year: Optional[int] = None,
    llm: Optional[Any] = None,
    language: str = "ita",
    ocr_retries: int = 2,
    use_llm: bool = True,
    ignore_patterns_path: Path | None = None,
    account_column: str | None = None,
    account_desc_column: str | None = None,
    counter_account_desc_column: str | None = None,
    extra_desc_column: str | None = None,
) -> List[Transaction]:
    """Load accounting ledger files into a list of Transactions.

    Args:
        files: Iterable of (filename, content) tuples.
        month/year: Optional filters; if provided, only transactions in
            the given month and year are included.
        llm: Optional LLM wrapper for PDF parsing.  If provided, this
            function can use the existing `parse_journal` (for
            structured PDFs) or call an LLM to extract transactions.
        language: OCR language for PDF extraction.
        ocr_retries: Number of OCR retries.
        use_llm: Whether to use LLM for fallback extraction.
        ignore_patterns_path: Optional path to ignore-pattern config.
        account_column: Optional name of the column containing account
            identifiers. When provided, values from this column are stored
            in ``metadata['account_id']``; otherwise, a heuristic is used
            to detect the account column.
        account_desc_column: Optional name of the column containing the
            human‑readable account description (e.g., "descrizione conto").
            When provided, values from this column are stored in
            ``metadata['account_desc']`` and override automatic detection.
        counter_account_desc_column: Optional name of the column containing the
            counter‑account description (e.g., "descrizione contropartita"). Values
            are stored in ``metadata['counter_account_desc']`` for use in UI and
            heuristics. This column is distinct from the selected bank account.
        extra_desc_column: Optional name of an additional description column
            (e.g., "descrizione agg" / "desc add"). Values are stored in
            ``metadata['extra_desc']`` and are used by matching heuristics.

    Returns:
        List of Transaction objects.
    """
    # Batch mode removed; use the unified router per-file if LLM fallback is needed.
    patterns = load_ignore_patterns(ignore_patterns_path)
    transactions: List[Transaction] = []

    # Load ledger header tokens from config with safe defaults
    def _default_ledger_headers() -> Dict[str, List[str]]:
        return {
            "date": [
                "data",
                "date",
                "data operazione",
                "data reg",
                "data registrazione",
                "fecha",
                "fecha operacion",
                "fecha registro",
                "datum",
                "daten",
                "valuta",
                "datavaluta",
                "valuedate",
                "data valuta",
            ],
            "description": [
                "descrizione",
                "descrizione causale",
                "descrizione agg",
                "causale",
                "descr",
                "desc",
                "descrizione aggiuntiva",
                "description",
                "description causale",
                "descripcion",
                "beschreibung",
                "descrizione deposito",
                "narrative",
                "riferimento",
                "reference",
            ],
            "debit": [
                "addebito",
                "uscite",
                "dare",
                "debit",
                "debe",
                "débit",
                "débito",
                "lastschrift",
                "prelievo",
            ],
            "credit": [
                "accredito",
                "entrate",
                "avere",
                "accrediti",
                "accreditation",
                "credit",
                "credito",
                "crédito",
                "haber",
                "gutschrift",
                "versamento",
                "deposito",
            ],
            "amount": [
                "importo",
                "amount",
                "importe",
                "betrag",
                "montant",
                "ammontare",
            ],
            "beneficiary": [
                "benef",
                "beneficiario",
                "beneficiary",
                "cliente",
                "fornitore",
                "cliente/fornitore",
                "beneficiario/cliente",
                "beneficiario/fornitore",
            ],
            "extra_desc": [
                "descr. agg",
                "descrizione agg",
                "descrizione aggiuntiva",
                "descrizione integrativa",
                "descrizione supplementare",
                "desc add",
                "desc. add",
                "additional description",
                "extra description",
            ],
            "account_desc": [
                "descrizione conto",
                "descr. conto",
                "account description",
                "account name",
                "nome conto",
            ],
            "counter_account_desc": [
                "descrizione contropartita",
                "conto contropartita",
                "descrizione sottoconto",
                "sottoconto",
                "descrizione cliente/fornitore",
                "cliente/fornitore",
            ],
            "journal_id": [
                "num. reg",
                "num reg",
                "n. reg",
                "numero registrazione",
                "n. registrazione",
                "registrazione",
                "id registrazione",
                "protocollo",
                "protocol",
                "prima nota",
                "pn",
            ],
        }

    LEDGER_HEADERS_PATH = (
        Path(__file__).resolve().parent.parent / "config" / "lexicon" / "ledger_headers.json"
    )

    def _load_ledger_headers(path: Path | None = None) -> Dict[str, List[str]]:
        base = _default_ledger_headers()
        p = path or LEDGER_HEADERS_PATH
        try:
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if isinstance(v, list):
                        base[k] = [str(x) for x in v]
        except Exception as exc:
            logger.warning("Failed to load ledger header lexicon: %s", exc)
        return base

    ledger_keywords = _load_ledger_headers()

    for filename, content in files:
        name_lower = filename.lower()
        if name_lower.endswith((".xlsx", ".xls", ".csv")):
            logger.debug("Processing %s as spreadsheet", filename)
            if pl is None:
                raise ImportError("polars is required to parse spreadsheets")
            df, mapping = parse_spreadsheet_prepare_with_keywords_extracted(
                content, filename, ledger_keywords, max_header_scan_rows=50
            )
            if df is None or df.height == 0:
                logger.debug("No data found in %s", filename)
                continue
            columns, _ = get_schema_and_column_names(df)
            resolved = _resolve_mapping(columns, mapping)
            # Optional UI override for account description column
            if account_desc_column and account_desc_column in columns:
                resolved["account_desc"] = account_desc_column
            if counter_account_desc_column and counter_account_desc_column in columns:
                resolved["counter_account_desc"] = counter_account_desc_column
            if extra_desc_column and extra_desc_column in columns:
                resolved["extra_desc"] = extra_desc_column
            _validate_required_columns(resolved)
            if account_column and account_column in columns:
                account_col = account_column
            else:
                account_col = _resolve_account_col(df)
            for row in df.iter_rows(named=True):
                try:
                    raw_date = row.get(resolved.get("date"))
                    d = _parse_date_any(raw_date)
                    if not d:
                        logger.debug(
                            "Skipping row in %s: invalid date %r", filename, raw_date
                        )
                        continue
                    if month and d.month != month:
                        logger.debug(
                            "Skipping row in %s: month %s != %s",
                            filename,
                            d.month,
                            month,
                        )
                        continue
                    if year and d.year != year and d.year != (year % 100):
                        logger.debug(
                            "Skipping row in %s: year %s != %s", filename, d.year, year
                        )
                        continue
                    amt = None
                    if "amount" in resolved:
                        amt = _parse_amount(row.get(resolved["amount"]))
                    if amt is None:
                        debit = (
                            _parse_amount(row.get(resolved["debit"]))
                            if "debit" in resolved
                            else None
                        )
                        credit = (
                            _parse_amount(row.get(resolved["credit"]))
                            if "credit" in resolved
                            else None
                        )
                        if debit is not None and credit is not None:
                            amt = credit - debit
                        elif credit is not None:
                            amt = credit
                        elif debit is not None:
                            amt = -debit
                    if amt is None:
                        logger.debug("Skipping row in %s: missing amount", filename)
                        continue
                    desc = (
                        str(row.get(resolved["description"]))
                        if "description" in resolved
                        else ""
                    )
                    beneficiary = (
                        str(row.get(resolved["beneficiary"]))
                        if "beneficiary" in resolved
                        else None
                    )
                    if any(p.search(desc) for p in patterns):
                        logger.debug(
                            "Skipping row in %s: description %r matched ignore pattern",
                            filename,
                            desc,
                        )
                        continue
                    account = (
                        str(row.get(account_col)).strip()
                        if account_col and row.get(account_col) is not None
                        else None
                    )
                    account_desc = (
                        str(row.get(resolved["account_desc"])).strip()
                        if "account_desc" in resolved
                        and row.get(resolved["account_desc"]) is not None
                        else None
                    )
                    extra_desc = (
                        str(row.get(resolved["extra_desc"])).strip()
                        if "extra_desc" in resolved
                        and row.get(resolved["extra_desc"]) is not None
                        else None
                    )
                    counter_account_desc = (
                        str(row.get(resolved["counter_account_desc"])).strip()
                        if "counter_account_desc" in resolved
                        and row.get(resolved["counter_account_desc"]) is not None
                        else None
                    )
                    # Include a combined details field to help Step 6 reference extraction
                    try:
                        # Join all cell values as strings (short, non-binary) to help reference extraction later
                        row_texts = []
                        for v in row.values():
                            if v is None:
                                continue
                            s = str(v)
                            if s and len(s) < 2000:
                                row_texts.append(s)
                        combined_details = " ".join(row_texts)
                    except Exception:
                        combined_details = ""
                    metadata = {"source": filename, "details": combined_details, "language": language}
                    # Optional: attach journal/registration id to support counterparty pairing
                    jid = (
                        str(row.get(resolved["journal_id"]))
                        if "journal_id" in resolved
                        and row.get(resolved["journal_id"]) is not None
                        else None
                    )
                    if jid:
                        metadata["journal_id"] = jid
                    if account:
                        metadata["account_id"] = account
                    if account_desc:
                        metadata["account_desc"] = account_desc
                    if extra_desc:
                        metadata["extra_desc"] = extra_desc
                    if counter_account_desc:
                        metadata["counter_account_desc"] = counter_account_desc
                    transactions.append(
                        _enrich_transaction(
                            Transaction(
                                date=d,
                                amount=float(amt),
                                description=desc.strip(),
                                beneficiary=(
                                    beneficiary.strip() if beneficiary else None
                                ),
                                metadata=metadata,
                            )
                        )
                    )
                except (IndexError, KeyError) as exc:
                    logger.error(
                        "Row parsing failed for %s: columns=%s mapping=%s row=%s error=%s",
                        filename,
                        columns,
                        mapping,
                        row,
                        exc,
                    )
                    continue
        elif name_lower.endswith(".pdf"):
            logger.debug("Processing %s as PDF", filename)
            # Attempt to parse ledger PDFs.  If parse_journal is available,
            # use it; otherwise, fallback to LLM extraction similar to bank.
            parsed_rows: List[Transaction] = []
            if parse_journal is not None:
                try:
                    df = parse_journal(content)
                    if df.height > 0:
                        # parse_journal returns a Polars DataFrame with
                        # columns: movement_number, date, description,
                        # debit, credit, ...
                        columns, _ = get_schema_and_column_names(df)
                        headers = [str(col) for col in columns]
                        mapping = _infer_columns(headers, ledger_keywords)
                        if mapping.get("date") is None or mapping.get("amount") is None:
                            guessed = guess_columns_from_data(df)
                            for key, idx in guessed.items():
                                if mapping.get(key) is None:
                                    mapping[key] = idx
                        resolved = _resolve_mapping(columns, mapping)
                        if account_desc_column and account_desc_column in columns:
                            resolved["account_desc"] = account_desc_column
                        if counter_account_desc_column and counter_account_desc_column in columns:
                            resolved["counter_account_desc"] = counter_account_desc_column
                        if extra_desc_column and extra_desc_column in columns:
                            resolved["extra_desc"] = extra_desc_column
                        _validate_required_columns(resolved)
                        if account_column and account_column in columns:
                            account_col = account_column
                        else:
                            account_col = _resolve_account_col(df)
                        for row in df.iter_rows(named=True):
                            try:
                                d = _parse_date_any(row.get(resolved.get("date")))
                                if not d:
                                    logger.debug(
                                        "Skipping row in %s: invalid date", filename
                                    )
                                    continue
                                if month and d.month != month:
                                    logger.debug(
                                        "Skipping row in %s: month %s != %s",
                                        filename,
                                        d.month,
                                        month,
                                    )
                                    continue
                                if year and d.year != year and d.year != (year % 100):
                                    logger.debug(
                                        "Skipping row in %s: year %s != %s",
                                        filename,
                                        d.year,
                                        year,
                                    )
                                    continue
                                amt = None
                                if "amount" in resolved:
                                    amt = _parse_amount(row.get(resolved["amount"]))
                                if amt is None:
                                    debit = (
                                        _parse_amount(row.get(resolved["debit"]))
                                        if "debit" in resolved
                                        else None
                                    )
                                    credit = (
                                        _parse_amount(row.get(resolved["credit"]))
                                        if "credit" in resolved
                                        else None
                                    )
                                    if debit is not None and credit is not None:
                                        amt = credit - debit
                                    elif credit is not None:
                                        amt = credit
                                    elif debit is not None:
                                        amt = -debit
                                if amt is None:
                                    logger.debug(
                                        "Skipping row in %s: missing amount", filename
                                    )
                                    continue
                                desc = (
                                    str(row.get(resolved["description"]))
                                    if "description" in resolved
                                    else ""
                                )
                                account = (
                                    str(row.get(account_col)).strip()
                                    if account_col and row.get(account_col) is not None
                                    else None
                                )
                                account_desc = (
                                    str(row.get(resolved["account_desc"])).strip()
                                    if "account_desc" in resolved
                                    and row.get(resolved["account_desc"]) is not None
                                    else None
                                )
                                metadata = {"source": filename, "language": language}
                                if account:
                                    metadata["account_id"] = account
                                if account_desc:
                                    metadata["account_desc"] = account_desc
                                # Optional extras if resolved
                                try:
                                    extra_desc = (
                                        str(row.get(resolved["extra_desc"])).strip()
                                        if "extra_desc" in resolved and row.get(resolved["extra_desc"]) is not None
                                        else None
                                    )
                                except Exception:
                                    extra_desc = None
                                try:
                                    counter_account_desc = (
                                        str(row.get(resolved["counter_account_desc"])).strip()
                                        if "counter_account_desc" in resolved and row.get(resolved["counter_account_desc"]) is not None
                                        else None
                                    )
                                except Exception:
                                    counter_account_desc = None
                                if extra_desc:
                                    metadata["extra_desc"] = extra_desc
                                if counter_account_desc:
                                    metadata["counter_account_desc"] = counter_account_desc
                                parsed_rows.append(
                                    _enrich_transaction(
                                        Transaction(
                                            date=d,
                                            amount=float(amt),
                                            description=desc.strip(),
                                            metadata=metadata,
                                        )
                                    )
                                )
                            except (IndexError, KeyError) as exc:
                                logger.error(
                                    "Row parsing failed for %s: columns=%s mapping=%s row=%s error=%s",
                                    filename,
                                    columns,
                                    mapping,
                                    row,
                                    exc,
                                )
                                continue
                except (ValueError, OSError) as exc:
                    logger.warning("parse_journal failed for %s: %s", filename, exc)
                    parsed_rows = []
            if not parsed_rows:
                parsed_rows = _parse_ledger_pdf_text_fallback(
                    content,
                    filename,
                    month,
                    year,
                    language=language,
                )
            # LLM fallback for PDFs if requested.
            needs_llm = not parsed_rows
            if llm and use_llm and needs_llm and extract_pdf_text_with_ocr:
                logger.debug("Skipping legacy LLM ledger fallback for %s", filename)
            for tr in parsed_rows:
                desc = tr.description or ""
                if any(p.search(desc) for p in patterns):
                    logger.debug(
                        "Skipping row in %s: description %r matched ignore pattern",
                        filename,
                        desc,
                    )
                    continue
                transactions.append(tr)
            if not parsed_rows:
                logger.debug("No transactions extracted from %s", filename)
        else:
            logger.debug("Skipping unsupported file %s", filename)
            continue
    return transactions


## duplicate load_bank_files wrapper removed; primary implementation above retains batch LLM


# Override legacy implementation with loader-backed wrapper (extraction complete)
## duplicate load_ledger_files wrapper removed; primary implementation above retains batch LLM


# ------------------------
# Reconciliation helpers
# ------------------------


## moved to src.check_statements.matching: _txns_to_polars, _pairs_from_candidates, _build_bank_candidates


# moved to src.check_statements.matching: _exact_pass


def reconcile_transactions(
    bank: Sequence[Transaction],
    ledger: Sequence[Transaction],
    tolerance: float = 1.0,
    date_window: int = 3,
    beneficiary_mode: str = "soft",
    fuzzy_threshold: float = 70.0,
    group_limit: int = 3,
    group_tolerance: Optional[float] = None,
    use_absolute_amounts: bool = False,
    progress_callback: Optional[Callable[[float, int, int], None]] = None,
    exclude_fees: bool = True,
    fee_mode: Literal["exclude", "match"] = "exclude",
    normalise_strategy: Literal["local"] = "local",
    *,
    llm_wrapper: Any | None = None,
    ledger_exclude_accounts: Iterable[str] | None = None,
    ledger_pre_filtered: bool = False,
    llm_enabled: Optional[bool] = None,
    llm_auto_threshold_abs: Optional[int] = None,
    llm_auto_threshold_pct: Optional[float] = None,
    allow_unique_amount_date: bool = False,
    allow_amount_date_assignment: bool = False,
    allow_fuzzy_margin: bool = False,
    fuzzy_margin_min: float = 15.0,
    fuzzy_threshold_relax: float = 10.0,
    small_candidate_set_k: int = 3,
    allow_reference_substring: bool = False,
    ref_id_min_len: int = 7,
    # Pre-aggregation: conservatively fold fee children into their parent bank row
    net_bank_fees: bool = False,
    # Optional guardrails (defaults preserve behaviour)
    group_candidates_cap: Optional[int] = None,
    max_combos_per_bank: Optional[int] = None,
    group_time_budget_ms: Optional[int] = None,
    # V1 learning (alias-only): disabled by default
    learn_alias_from_unique: bool = True,
    learning_min_support: int = 2,
    learning_budget: int = 20,
) -> Tuple[
    List[Tuple[int, int | None | Tuple[int | None, ...], str]],
    List[int],
    List[int | None],
]:
    """Reconcile two sequences of transactions.

    Reference IDs and normalised beneficiary names are compared before amount and fuzzy description matching.

    Matching occurs in passes:
      0. reference IDs
      1. normalised beneficiary name
      2. exact amount & date window
      3. fuzzy description/beneficiary
      4. group match

    Args:
        bank: Sequence of bank transactions.
        ledger: Sequence of ledger transactions.
        tolerance: Absolute or relative tolerance for single-entry matches.
        date_window: Maximum allowed difference in days between bank and ledger
            dates.
        beneficiary_mode: Beneficiary matching mode ("hard", "soft", "off").
        fuzzy_threshold: Minimum fuzzy match score.
        group_limit: Maximum size of ledger groups to consider.
        group_tolerance: Tolerance applied when comparing the sum of grouped
            ledger amounts against the bank amount. Defaults to ``tolerance``
            when ``None``.
        use_absolute_amounts: Compare amounts using their absolute values,
            allowing matches between opposite-signed transactions.
        progress_callback: Optional callback for progress updates.
        exclude_fees: Whether to handle bank fee transactions specially.
        fee_mode: Strategy for fee handling: ``"exclude"`` drops them from the
            bank list, ``"match"`` creates synthetic ledger entries to match
            against.
        normalise_strategy: Description normalisation strategy. Only local
            cleaning is supported.
        llm_wrapper: Accepted for compatibility. Reconciliation, description
            normalisation, and PDF OCR do not use it for provider API calls.
        ledger_exclude_accounts: Optional iterable of ledger account identifiers
            to exclude from reconciliation.
        ledger_pre_filtered: If ``True``, ``ledger`` has already had
            ``ledger_exclude_accounts`` applied and will not be filtered again.

    Returns:
        matched_pairs: Tuples of bank index, ledger index, and match type. Ledger
            indices refer to the caller's original ledger list; synthetic entries
            are marked with ``None``.
        unmatched_bank: Indices of bank transactions not matched.
        unmatched_ledger: Indices of unmatched ledger transactions or ``None``
            for synthetic entries.
    """
    bank = list(bank)
    ledger = list(ledger)
    # 1) Early prune of non-transaction rows so summary/header lines never reach matching
    original_bank_indices = list(range(len(bank)))
    if bank:
        bank, kept_map, early_dropped = _early_filter_bank_transactions(bank)
        # Compose original index mapping
        original_bank_indices = [original_bank_indices[i] for i in kept_map]
        if early_dropped:
            logger.info(
                "early-final-pass-filter: removed %d non-transaction rows",
                early_dropped,
            )
    # 2) Optional: pre-aggregate bank rows by folding fee children (instant transfer/prepaid/CBILL)
    if net_bank_fees and bank:
        bank, pre_map = _preaggregate_bank_transactions(bank)
        original_bank_indices = [original_bank_indices[i] for i in pre_map]
    original_ledger_indices: List[int | None] = list(range(len(ledger)))

    # Diagnostics: reference-id presence on both sides (helps explain low match rates)
    try:
        bank_ref_rows = sum(1 for t in bank if getattr(t, "reference_ids", []))
        ledger_ref_rows = sum(1 for t in ledger if getattr(t, "reference_ids", []))
        bank_ben_rows = sum(1 for t in bank if (t.beneficiary or "").strip())
        ledger_ben_rows = sum(1 for t in ledger if (t.beneficiary or "").strip())
        bank_iban_rows = sum(1 for t in bank if (t.metadata or {}).get("iban"))
        ledger_iban_rows = sum(1 for t in ledger if (t.metadata or {}).get("iban"))
        logger.info(
            "reconcile presence: refs b=%d/%d l=%d/%d | ben b=%d/%d l=%d/%d | iban b=%d/%d l=%d/%d",
            bank_ref_rows,
            len(bank),
            ledger_ref_rows,
            len(ledger),
            bank_ben_rows,
            len(bank),
            ledger_ben_rows,
            len(ledger),
            bank_iban_rows,
            len(bank),
            ledger_iban_rows,
            len(ledger),
        )
        if ledger_ref_rows == 0:
            logger.warning(
                "reconcile: ledger contains ZERO rows with reference IDs; reference-based auto-matching will be effectively disabled"
            )
    except Exception:  # nosec - diagnostics only
        pass

    if ledger_exclude_accounts and not ledger_pre_filtered:
        exclude_set = set(ledger_exclude_accounts)
        filtered_ledger: List[Transaction] = []
        filtered_indices_l: List[int | None] = []
        for idx, tx in enumerate(ledger):
            meta = tx.metadata if isinstance(tx.metadata, Mapping) else {}
            acc_id = meta.get("account_id") or meta.get("account_identifier")
            if acc_id not in exclude_set:
                filtered_ledger.append(tx)
                filtered_indices_l.append(original_ledger_indices[idx])
        ledger = filtered_ledger
        original_ledger_indices = filtered_indices_l
    elif not ledger_pre_filtered:
        # Defensive fallback: if a single ledger account dominates, filter to it.
        # This only triggers when there is a strong majority to avoid surprising callers.
        counts: dict[Hashable, int] = {}
        indices_by_acc: dict[Hashable, list[int]] = {}
        for idx, tx in enumerate(ledger):
            meta = tx.metadata if isinstance(tx.metadata, Mapping) else {}
            acc_id = meta.get("account_id") or meta.get("account_identifier")
            if acc_id is None:
                continue
            counts[acc_id] = counts.get(acc_id, 0) + 1
            indices_by_acc.setdefault(acc_id, []).append(idx)
        if counts:
            top_acc, top_cnt = max(counts.items(), key=lambda kv: kv[1])
            total_tagged = sum(counts.values())
            if total_tagged > 0 and top_cnt / total_tagged >= 0.8:
                logger.info(
                    "Fallback ledger account filter applied: account=%r share=%.1f%% (tagged=%d)",
                    top_acc,
                    100.0 * top_cnt / max(1, total_tagged),
                    total_tagged,
                )
                keep = set(indices_by_acc.get(top_acc, []))
                filtered_ledger = []
                filtered_indices_l = []
                for idx, tx in enumerate(ledger):
                    if idx in keep:
                        filtered_ledger.append(tx)
                        filtered_indices_l.append(original_ledger_indices[idx])
                ledger = filtered_ledger
                original_ledger_indices = filtered_indices_l

    # Build the list of raw descriptions from bank and ledger transactions and
    # compute the local normalisation map used by fuzzy matching.
    raw_descs = list(
        {(tx.description or "") for tx in bank}
        | {(tx.description or "") for tx in ledger}
    )
    if exclude_fees and fee_mode == "match":
        raw_descs.append("Bank fee")

    # Always compute local normalisations; plugin runtime must not call model APIs.
    norm_map_local: Dict[str, str] = {d: _clean_description_local(d) for d in raw_descs}
    norm_map: Dict[str, str] = dict(norm_map_local)

    if exclude_fees:
        fee_indices: List[int] = []
        patterns = load_fee_patterns()
        # Detect frequently recurring small amounts (likely fees)
        amt_counts: Dict[float, int] = {}
        for t in bank:
            try:
                a = abs(float(t.amount))
                a = round(a, 2)
                amt_counts[a] = amt_counts.get(a, 0) + 1
            except Exception:
                continue
        recurring_fee_amounts: set[float] = {
            a for a, c in amt_counts.items() if c >= 20 and a <= 10.0
        }
        # Dynamically choose fee handling: if many recurring small fees, prefer 'match'
        eff_fee_mode = fee_mode
        if eff_fee_mode == "exclude" and recurring_fee_amounts:
            eff_fee_mode = "match"
        for i, tx in enumerate(bank):
            desc = norm_map.get(tx.description or "", "")
            is_fee_like = any(p.search(desc) for p in patterns)
            try:
                a = round(abs(float(tx.amount)), 2)
            except Exception:
                a = None
            is_recurring_small = a in recurring_fee_amounts if a is not None else False
            if is_fee_like:
                fee_indices.append(i)
                if eff_fee_mode == "match":
                    ledger.append(
                        Transaction(
                            date=tx.date,
                            amount=tx.amount,
                            description="Bank fee",
                            reference_ids=[],
                            beneficiary=None,
                            metadata={"source": {"name": "synthetic_fee"}},
                        )
                    )
                    original_ledger_indices.append(None)
            elif is_recurring_small and eff_fee_mode == "match":
                # Dynamic fee handling: recurring small amounts get synthetic ledger entries
                ledger.append(
                    Transaction(
                        date=tx.date,
                        amount=tx.amount,
                        description="Bank fee (recurring amount)",
                        reference_ids=[],
                        beneficiary=None,
                        metadata={"source": {"name": "synthetic_fee_amount"}},
                    )
                )
                original_ledger_indices.append(None)
        if eff_fee_mode == "exclude" and fee_indices:
            bank = [tx for i, tx in enumerate(bank) if i not in fee_indices]
            original_bank_indices = [
                i for i in original_bank_indices if i not in fee_indices
            ]

    def within_tolerance(a: Transaction, b: Transaction) -> bool:
        if use_absolute_amounts:
            return abs(abs(a.amount) - abs(b.amount)) <= tolerance
        return abs(a.amount - b.amount) <= tolerance

    def within_date(a: Transaction, b: Transaction) -> bool:
        return abs((a.date - b.date).days) <= date_window

    matched_pairs: List[Tuple[int, int | Tuple[int, ...], str]] = []
    used_ledger: set[int] = set()
    bank_dates = [t.date for t in bank]
    ledger_dates = [t.date for t in ledger]
    ref_index: defaultdict[str, List[int]] = defaultdict(list)
    ben_index: defaultdict[str, List[int]] = defaultdict(list)
    # Load learned alias rules (global V1) and apply when indexing beneficiaries
    try:
        from src.check_statements.alias_memory import load_alias_rules, apply_alias_to_norm  # type: ignore

        _alias_map = load_alias_rules()
    except Exception:  # pragma: no cover - optional feature
        _alias_map = {}
    for li, l_txn in enumerate(ledger):
        for ref in l_txn.reference_ids:
            ref_index[ref].append(li)
        if l_txn.beneficiary:
            try:
                key_l = normalise_name(l_txn.beneficiary)
            except Exception:
                key_l = (l_txn.beneficiary or "").strip()
            try:
                key_l = apply_alias_to_norm(key_l, _alias_map) if _alias_map else key_l
            except Exception:
                pass
            ben_index[key_l].append(li)
    for bi, b_txn in enumerate(bank):
        if not b_txn.reference_ids:
            continue
        candidates = set()
        for ref in b_txn.reference_ids:
            candidates.update(ref_index.get(ref, []))
        # Enforce uniqueness after base checks to avoid false positives
        viable: list[int] = []
        for li in candidates:
            if li in used_ledger:
                continue
            l_txn = ledger[li]
            if within_tolerance(b_txn, l_txn) and within_date(b_txn, l_txn):
                viable.append(li)
        if len(viable) == 1:
            matched_pairs.append((bi, viable[0], "reference"))
            used_ledger.add(viable[0])
    matched_bank_indices = {bi for (bi, _, _) in matched_pairs}
    matched_ledger_indices = {li for (_, li, _) in matched_pairs}

    total_passes = 3 if group_limit and group_limit > 1 else 2

    def _update_progress(pass_idx: int, bi: int) -> None:
        if progress_callback is None:
            return
        progress = (pass_idx + (bi + 1) / len(bank)) / total_passes
        progress_callback(progress, len(matched_pairs), bi + 1)

    for bi, b_txn in enumerate(bank):
        if bi in matched_bank_indices or not b_txn.beneficiary:
            continue
        try:
            key = normalise_name(b_txn.beneficiary)
        except Exception:
            key = (b_txn.beneficiary or "").strip()
        try:
            key = apply_alias_to_norm(key, _alias_map) if _alias_map else key
        except Exception:
            pass
        candidates = set(ben_index.get(key, []))
        b_iban = (b_txn.metadata or {}).get("iban")
        viable: list[int] = []
        for li in candidates:
            if li in used_ledger:
                continue
            l_txn = ledger[li]
            l_iban = (l_txn.metadata or {}).get("iban")
            if b_iban and l_iban and b_iban != l_iban:
                continue
            if within_tolerance(b_txn, l_txn) and within_date(b_txn, l_txn):
                viable.append(li)
        if len(viable) == 1:
            best = viable[0]
            matched_pairs.append((bi, best, "beneficiary"))
            used_ledger.add(best)
            matched_bank_indices.add(bi)
            matched_ledger_indices.add(best)
    # Build amount/date candidate sets per bank row
    bank_candidates = _build_bank_candidates(
        bank,
        ledger,
        tolerance,
        date_window=date_window,
        use_absolute_amounts=use_absolute_amounts,
    )
    gtol = group_tolerance if group_tolerance is not None else tolerance

    # After candidate buckets are built, first try exact matches (no need for description normalisation yet).
    _exact_pass(
        bank,
        ledger,
        bank_candidates,
        matched_pairs,
        matched_bank_indices,
        matched_ledger_indices,
        tolerance=tolerance,
        beneficiary_mode=beneficiary_mode,
        fuzzy_threshold=fuzzy_threshold,
        date_window=date_window,
        use_absolute_amounts=use_absolute_amounts,
        update_progress=_update_progress,
    )
    # Fuzzy matching (local/offline normalisation only at this stage)
    _fuzzy_pass(
        bank,
        ledger,
        bank_candidates,
        matched_pairs,
        matched_bank_indices,
        matched_ledger_indices,
        norm_map_local=norm_map_local,
        norm_map=norm_map,
        fuzzy_threshold=fuzzy_threshold,
        update_progress=_update_progress,
    )
    # Group matching before any LLM escalation
    _group_match(
        bank,
        ledger,
        bank_candidates,
        matched_pairs,
        matched_bank_indices,
        matched_ledger_indices,
        group_limit=group_limit,
        tolerance=tolerance,
        group_tolerance=group_tolerance,
        beneficiary_mode=beneficiary_mode,
        fuzzy_threshold=fuzzy_threshold,
        use_absolute_amounts=use_absolute_amounts,
        within_tolerance=within_tolerance,
        within_date=within_date,
        update_progress=_update_progress,
        group_candidates_cap=group_candidates_cap,
        max_combos_per_bank=max_combos_per_bank,
        group_time_budget_ms=group_time_budget_ms,
    )
    # Optional: assign duplicates across amount/date window via greedy nearest-date matching
    if allow_amount_date_assignment:
        _assignment_pass(
            bank,
            ledger,
            bank_candidates,
            matched_pairs,
            matched_bank_indices,
            matched_ledger_indices,
            within_tolerance=within_tolerance,
            within_date=within_date,
        )
    # Adaptive second group pass: if many remain unmatched, allow groups up to 3
    rem_after_group = [i for i in range(len(bank)) if i not in matched_bank_indices]
    if group_limit <= 2 and len(rem_after_group) > 0.30 * max(1, len(bank)):
        _group_match(
            bank,
            ledger,
            bank_candidates,
            matched_pairs,
            matched_bank_indices,
            matched_ledger_indices,
            group_limit=3,
            tolerance=tolerance,
            group_tolerance=group_tolerance,
            beneficiary_mode=beneficiary_mode,
            fuzzy_threshold=fuzzy_threshold,
            use_absolute_amounts=use_absolute_amounts,
            within_tolerance=within_tolerance,
            within_date=within_date,
            update_progress=_update_progress,
            group_candidates_cap=(
                24 if not group_candidates_cap else min(24, int(group_candidates_cap))
            ),
            max_combos_per_bank=(
                3000 if not max_combos_per_bank else min(3000, int(max_combos_per_bank))
            ),
            group_time_budget_ms=(
                500 if not group_time_budget_ms else min(500, int(group_time_budget_ms))
            ),
        )

    # Optional final pass: accept unique amount+date candidates as low-confidence (C-grade)
    if allow_unique_amount_date:
        for bi in range(len(bank)):
            if bi in matched_bank_indices:
                continue
            cands = [
                li for li in bank_candidates[bi] if li not in matched_ledger_indices
            ]
            if len(cands) != 1:
                continue
            li = cands[0]
            # Basic safety: avoid mapping F24 bank entries to non-tax ledger entries
            try:
                b_type = (bank[bi].metadata or {}).get("op_type") or classify_op(
                    bank[bi].description
                )
            except Exception:
                b_type = "OTHER"
            if b_type == "F24":
                try:
                    if not _is_tax_ledger_entry(ledger[li]):
                        continue
                except Exception:
                    continue
            matched_pairs.append((bi, li, "unique"))
            matched_bank_indices.add(bi)
            matched_ledger_indices.add(li)

    # Optional: reference substring fallback (amount/date candidate with long ID substring)
    if allow_reference_substring:
        _reference_substring_pass(
            bank,
            ledger,
            bank_candidates,
            matched_pairs,
            matched_bank_indices,
            matched_ledger_indices,
            within_tolerance=within_tolerance,
            within_date=within_date,
            min_len=int(ref_id_min_len),
        )

    # Optional: accept top fuzzy candidate on small sets with clear margin
    if allow_fuzzy_margin:
        _fuzzy_margin_pass(
            bank,
            ledger,
            bank_candidates,
            matched_pairs,
            matched_bank_indices,
            matched_ledger_indices,
            norm_map_local=norm_map_local,
            norm_map=norm_map,
            fuzzy_threshold=fuzzy_threshold,
            margin_min=float(fuzzy_margin_min),
            small_set_k=int(small_candidate_set_k),
            relax=float(fuzzy_threshold_relax),
        )
    # -------------------------------------------------------------
    # V1 learning scaffold (alias-only, global): collect unique
    # amount+date seeds and persist deterministic alias mappings for future runs.
    # Disabled by default; persists rules but does not re-run matching.
    if learn_alias_from_unique:
        try:
            from src.check_statements.alias_memory import (
                load_alias_rules,
                save_alias_rules,
            )
            from src.check_statements.alias_seed import collect_matched_seed_pairs
        except Exception:  # pragma: no cover - optional feature
            load_alias_rules = lambda: {}  # type: ignore
            save_alias_rules = lambda _m: None  # type: ignore

            def collect_matched_seed_pairs(*_args, **_kwargs):  # type: ignore
                return []

        alias_map = load_alias_rules()

        unique_candidates = _build_bank_candidates(
            bank,
            ledger,
            tolerance,
            date_window=1,
            use_absolute_amounts=use_absolute_amounts,
        )

        seed_pairs = collect_matched_seed_pairs(
            bank,
            ledger,
            matched_pairs,
            unique_candidates,
            exclude_types={"FEE"},
            existing_alias_map=alias_map,
        )

        seeds_count = len(seed_pairs)
        if seeds_count:
            # Prepare beneficiary support for persisted alias updates
            support: dict[tuple[str, str], set[date]] = {}
            for seed in seed_pairs:
                feature = seed.feature_by_field("beneficiary")
                if not feature or not feature.has_both():
                    continue
                b_key = feature.bank.normalized[0]
                l_key = feature.ledger.normalized[0]
                support.setdefault((b_key, l_key), set()).add(seed.date)

            supported: list[tuple[str, str, int]] = [
                (bk, lk, len(ds))
                for (bk, lk), ds in support.items()
                if len(ds) >= int(learning_min_support)
            ]
            supported.sort(key=lambda item: (item[2], len(item[1])), reverse=True)

            updates: dict[str, str] = {}
            for bk, lk, _cnt in supported[: int(learning_budget)]:
                if bk == lk or alias_map.get(bk) == lk:
                    continue
                updates[bk] = lk

            try:
                logger.info(
                    "Alias learning: seeds=%d supported=%d updates=%d",
                    seeds_count,
                    len(supported),
                    len(updates),
                )
            except Exception:
                pass

            if updates:
                alias_map.update(updates)
                try:
                    save_alias_rules(alias_map)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("Alias learning: failed to save rules: %s", exc)

    unmatched_bank = [i for i in range(len(bank)) if i not in matched_bank_indices]
    unmatched_ledger = [
        i for i in range(len(ledger)) if i not in matched_ledger_indices
    ]

    def map_ledger_index(
        idx: int | Tuple[int, ...],
    ) -> int | None | Tuple[int | None, ...]:
        if isinstance(idx, tuple):
            return tuple(original_ledger_indices[i] for i in idx)
        return original_ledger_indices[idx]

    matched_pairs = [
        (original_bank_indices[bi], map_ledger_index(li), how)
        for bi, li, how in matched_pairs
    ]
    unmatched_bank = [original_bank_indices[i] for i in unmatched_bank]
    unmatched_ledger = [map_ledger_index(i) for i in unmatched_ledger]
    return matched_pairs, unmatched_bank, unmatched_ledger


def export_to_excel(
    bank: Sequence[Transaction],
    ledger: Sequence[Transaction],
    matched_pairs: List[Tuple[int, int | None | Tuple[int | None, ...], str]],
    unmatched_bank: List[int],
    unmatched_ledger: List[int | None],
    *,
    final_pass_filter: bool = True,
    settings: dict | None = None,
    diagnostics: dict | None = None,
    stage_flags: Mapping[int, Mapping[str, bool]] | None = None,
) -> bytes:
    """Generate an in-memory Excel report summarising reconciliation results.

    The report contains three sheets:

    * ``matched`` – transactions successfully matched.
    * ``unmatched_bank`` – bank entries without a ledger match.
    * ``unmatched_ledger`` – ledger entries without a bank match.

    Final-pass filter diagnostics are logged but not persisted in the workbook.

    Args:
    bank: Original list of bank transactions.
        ledger: Original list of ledger transactions.
        matched_pairs: Output from ``reconcile_transactions``.
        unmatched_bank: Indices of unmatched bank entries.
        unmatched_ledger: Indices of unmatched ledger entries or ``None`` for
            synthetic entries.
        stage_flags: Optional per-bank mapping of stage pass/fail indicators
            keyed by ``"s1"`` … ``"s8"``. Used to annotate the ``matched`` sheet.

    Returns:
        Binary Excel file data with ``matched`` as the first sheet.
    """
    # Lazy import to avoid heavy dependencies during simple unit tests
    from xlsxwriter import Workbook

    def _source_label(src: Any) -> str:
        if isinstance(src, Mapping):
            return str(src.get("filename") or src.get("name") or src)
        return str(src) if src is not None else ""

    if stage_flags:
        try:
            stage_flag_map: dict[int, Mapping[str, bool]] = dict(stage_flags)
        except Exception:
            stage_flag_map = {}
    else:
        stage_flag_map = {}

    stage_label_by_code = {
        1: "Amount & date window (stage 1)",
        2: "Bank fees and charges (stage 2)",
        3: "Cash withdrawals or deposits (stage 3)",
        4: "Card payments (stage 4)",
        5: "Payroll and taxes (stage 5)",
        6: "Beneficiary name (stage 6)",
        7: "IBAN evidence (stage 7)",
        8: "Reference evidence (stage 8)",
    }

    match_type_to_stage = {
        "assign": 1,
        "exact": 1,
        "fuzzy": 1,
        "fuzzy_margin": 1,
        "ref_substring": 1,
        "group": 1,
        "unique": 1,
        "fix_fee": 2,
        "cash": 3,
        "card": 4,
        "salary_gate": 5,
        "beneficiary": 6,
        "iban": 7,
        "reference": 8,
    }

    stage_evidence_columns = {
        "s3": "cash_like_evidence",
        "s4": "card_payment_evidence",
        "s5": "payroll_tax_evidence",
        "s6": "beneficiary_name_evidence",
    }

    def _stage_details_for_bank(
        bi: int, match_type: str
    ) -> tuple[str, dict[str, bool], bool, bool]:
        entry = stage_flag_map.get(bi)
        if isinstance(entry, Mapping):
            entry_map = {str(k): bool(v) for k, v in entry.items()}
        else:
            entry_map = {}

        stage_code: int | None = None
        if entry_map.get("s2"):
            stage_code = 2
        elif entry_map.get("s1"):
            stage_code = 1
        if stage_code is None:
            stage_code = match_type_to_stage.get(match_type, 1)

        stage_label = stage_label_by_code.get(stage_code, stage_label_by_code[1])
        evidence = {
            column_name: bool(entry_map.get(flag_key))
            for flag_key, column_name in stage_evidence_columns.items()
        }
        iban_stage = bool(entry_map.get("s7"))
        reference_stage = bool(entry_map.get("s8"))
        return stage_label, evidence, iban_stage, reference_stage

    matched_rows: List[dict[str, object]] = []
    for bi, li, how in matched_pairs:
        b = bank[bi]
        ledger_indices = li if isinstance(li, tuple) else (li,)

        bank_date = b.date.date() if isinstance(b.date, datetime) else b.date
        bank_amount = float(b.amount) if b.amount is not None else None
        bank_description = b.description or ""
        bank_beneficiary = b.beneficiary or ""
        bank_source = _source_label(b.metadata.get("source")) or ""
        match_type = how or ""

        stage_label, evidence_flags, stage_iban_flag, stage_reference_flag = (
            _stage_details_for_bank(bi, match_type)
        )
        for li2 in ledger_indices:
            if li2 is None:
                row = {
                    "bank_date": bank_date,
                    "bank_amount": bank_amount,
                    "bank_description": bank_description,
                    "bank_beneficiary": bank_beneficiary,
                    "ledger_date": None,
                    "ledger_amount": None,
                    "ledger_description": "Synthetic fee",
                    "ledger_beneficiary": "",
                    "match_type": match_type,
                    "match_stage": stage_label,
                    "bank_source": bank_source,
                    "ledger_source": "Synthetic fee",
                }
                row.update(evidence_flags)
                row["evidence_reference_id"] = (
                    bool(row.get("evidence_reference_id", False))
                    or stage_reference_flag
                )
                row["evidence_iban"] = (
                    bool(row.get("evidence_iban", False)) or stage_iban_flag
                )
                matched_rows.append(row)
                continue
            l = ledger[li2]
            ledger_date = l.date.date() if isinstance(l.date, datetime) else l.date
            ledger_amount = float(l.amount) if l.amount is not None else None
            ledger_description = l.description or ""
            ledger_beneficiary = l.beneficiary or ""
            ledger_source = _source_label(l.metadata.get("source")) or ""

            # Evidence
            def _ben_score(x: str, y: str) -> float:
                x = (x or "").upper()
                y = (y or "").upper()
                if not x or not y:
                    return 0.0
                sx = set(x.split())
                sy = set(y.split())
                if not sx or not sy:
                    return 0.0
                return round(100.0 * len(sx & sy) / max(len(sx), len(sy)), 1)

            hard = bool(set(b.reference_ids or []) & set(l.reference_ids or []))
            b_iban = (b.metadata or {}).get("iban")
            l_iban = (l.metadata or {}).get("iban")
            iban = bool(b_iban and l_iban and b_iban == l_iban)
            ben_score = _ben_score(b.beneficiary or "", l.beneficiary or "")

            # Auto-post policy (inclusive semantics; amount/date always enforced by matcher)
            policy = (settings or {}).get("auto_post_policy", "ref_or_benef")

            def _auto(policy: str, match_type: str) -> bool:
                if policy == "ref_only":
                    return bool(hard)
                if policy == "ref_or_benef":
                    return bool(hard or iban or ben_score >= 85.0)
                if policy == "iban_benef_only":
                    return bool(iban or ben_score >= 85.0)
                if policy == "unique_only":
                    return match_type in {"unique", "beneficiary", "reference", "exact"}
                return False

            # compute inline where used; keep for readability if needed

            row = {
                "bank_date": bank_date,
                "bank_amount": bank_amount,
                "bank_description": bank_description,
                "bank_beneficiary": bank_beneficiary,
                "ledger_date": ledger_date,
                "ledger_amount": ledger_amount,
                "ledger_description": ledger_description,
                "ledger_beneficiary": ledger_beneficiary,
                "match_type": match_type,
                "match_stage": stage_label,
                "bank_source": bank_source,
                "ledger_source": ledger_source,
                "evidence_reference_id": hard,
                "evidence_iban": iban,
                "beneficiary_score": ben_score,
                "auto_post": _auto(policy, match_type),
            }
            row.update(evidence_flags)
            row["evidence_reference_id"] = (
                bool(row["evidence_reference_id"]) or stage_reference_flag
            )
            row["evidence_iban"] = bool(row["evidence_iban"]) or stage_iban_flag
            matched_rows.append(row)

    unmatched_bank_df_raw = pl.DataFrame(
        [
            {
                "date": bank[i].date,
                "amount": bank[i].amount,
                "description": bank[i].description,
                "beneficiary": bank[i].beneficiary,
                "source": _source_label(bank[i].metadata.get("source")),
            }
            for i in unmatched_bank
        ],
        schema={
            "date": pl.Date,
            "amount": pl.Float64,
            "description": pl.Utf8,
            "beneficiary": pl.Utf8,
            "source": pl.Utf8,
        },
        strict=False,
        ).with_columns(
        pl.col("source").cast(pl.Utf8),
        pl.lit("").alias("notes"),
    )
    unmatched_bank_transactions_count_before_filter = int(
        get_row_count(unmatched_bank_df_raw)
    )
    # Filter non-transaction rows and capture dropped rows + rule stats
    unmatched_bank_df = unmatched_bank_df_raw
    dropped_df: pl.DataFrame | None = pl.DataFrame([])
    rules_counts: dict[str, int] = {}
    dropped_count = 0
    if final_pass_filter:
        # Resolve via public facade so tests can monkeypatch `src.check_statements.clean_bank_not_matched`
        try:
            from src import check_statements as _facade  # type: ignore
            _cbnm = getattr(_facade, "clean_bank_not_matched", clean_bank_not_matched)
        except Exception:  # pragma: no cover
            _cbnm = clean_bank_not_matched
        cleaned_result = _cbnm(
            unmatched_bank_df_raw, return_dropped_rows=True, collect_stats=True
        )
        if (
            isinstance(cleaned_result, tuple)
            and len(cleaned_result) >= 3
        ):
            try:
                unmatched_bank_df, dropped_df, report = cleaned_result  # type: ignore[misc]
                rules_counts = dict(getattr(report, "counts_by_rule", {}) or {})
            except Exception:
                unmatched_bank_df = cleaned_result[0]  # type: ignore[index]
                dropped_df = cleaned_result[1]  # type: ignore[index]
                rules_counts = {}
        elif isinstance(cleaned_result, tuple) and len(cleaned_result) >= 2:
            unmatched_bank_df, dropped_df = cleaned_result[0], cleaned_result[1]
        else:
            unmatched_bank_df = cleaned_result  # type: ignore[assignment]
            dropped_df = pl.DataFrame([])
        dropped_count = int(get_row_count(dropped_df)) if dropped_df is not None else 0
        # Log concise diagnostics to aid UI/tests
        try:
            logger.info(
                "final-pass-filter: removed %d balance-summary rows",
                int(rules_counts.get("drop_summary_headers", 0)),
            )
            logger.info(
                "FinalPassFilter applied: bank_unmatched %d → %d",
                unmatched_bank_transactions_count_before_filter,
                int(get_row_count(unmatched_bank_df)),
            )
        except Exception as e:
            logger.exception("Failed to log FinalPassFilter diagnostics: %s", e)
    else:
        dropped_df = pl.DataFrame([])
        dropped_count = 0
    unmatched_bank_transactions_count_after_filter = int(
        get_row_count(unmatched_bank_df)
    )
    unmatched_ledger_rows: List[dict[str, object]] = []
    for i in unmatched_ledger:
        if i is None:
            unmatched_ledger_rows.append(
                {
                    "date": None,
                    "amount": None,
                    "description": "Synthetic fee",
                    "beneficiary": "",
                    "source": "Synthetic fee",
                }
            )
            continue
        unmatched_ledger_rows.append(
            {
                "date": ledger[i].date,
                "amount": ledger[i].amount,
                "description": ledger[i].description,
                "beneficiary": ledger[i].beneficiary,
                "source": _source_label(ledger[i].metadata.get("source")),
            }
        )

    total_matched_bank = sum(bank[bi].amount for bi, _, _ in matched_pairs)
    total_matched_ledger = sum(
        (
            sum(ledger[i].amount for i in li if i is not None)
            if isinstance(li, tuple)
            else (ledger[li].amount if li is not None else 0)
        )
        for _, li, _ in matched_pairs
    )
    deposits_in_transit = float(
        unmatched_bank_df.get_column("amount").sum()
        if get_row_count(unmatched_bank_df)
        else 0.0
    )
    outstanding_checks = sum(
        ledger[i].amount for i in unmatched_ledger if i is not None
    )
    bank_balance = sum(b.amount for b in bank)
    ledger_balance = sum(l.amount for l in ledger)
    adjusted_bank_balance = bank_balance + deposits_in_transit - outstanding_checks
    adjusted_ledger_balance = ledger_balance - deposits_in_transit + outstanding_checks

    matched_schema = {
        "bank_date": pl.Date,
        "bank_amount": pl.Float64,
        "bank_description": pl.Utf8,
        "bank_beneficiary": pl.Utf8,
        "ledger_date": pl.Date,
        "ledger_amount": pl.Float64,
        "ledger_description": pl.Utf8,
        "ledger_beneficiary": pl.Utf8,
        "match_type": pl.Utf8,
        "match_stage": pl.Utf8,
        "bank_source": pl.Utf8,
        "ledger_source": pl.Utf8,
        "evidence_reference_id": pl.Boolean,
        "evidence_iban": pl.Boolean,
        "beneficiary_score": pl.Float64,
        "auto_post": pl.Boolean,
        "cash_like_evidence": pl.Boolean,
        "card_payment_evidence": pl.Boolean,
        "payroll_tax_evidence": pl.Boolean,
        "beneficiary_name_evidence": pl.Boolean,
    }
    matched_df = _prepare_df_for_excel(
        pl.DataFrame(
            matched_rows,
            schema=matched_schema,
            strict=False,
            infer_schema_length=None,
        )
    )
    unmatched_bank_df = _prepare_df_for_excel(unmatched_bank_df)
    dropped_bank_df: pl.DataFrame | None = None
    if final_pass_filter and dropped_df is not None and get_row_count(dropped_df) > 0:
        try:
            dropped_bank_df = _prepare_df_for_excel(dropped_df)
        except Exception:
            dropped_bank_df = dropped_df
    unmatched_ledger_df = _prepare_df_for_excel(
        pl.DataFrame(
            unmatched_ledger_rows,
            schema={
                "date": pl.Date,
                "amount": pl.Float64,
                "description": pl.Utf8,
                "beneficiary": pl.Utf8,
                "source": pl.Utf8,
            },
            strict=False,
        ).with_columns(
            pl.col("source").cast(pl.Utf8),
            pl.lit("").alias("notes"),
        )
    )

    with io.BytesIO() as buffer:
        workbook = Workbook(buffer, {"in_memory": True})
        try:
            matched_df.write_excel(workbook, worksheet="matched")
            unmatched_bank_df.write_excel(workbook, worksheet="unmatched_bank")
            if dropped_bank_df is not None:
                dropped_bank_df.write_excel(
                    workbook, worksheet="unmatched_bank_dropped"
                )
            unmatched_ledger_df.write_excel(workbook, worksheet="unmatched_ledger")
        finally:
            workbook.close()
        return buffer.getvalue()
