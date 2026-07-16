from __future__ import annotations

import io
import logging
import re
import unicodedata
from typing import Any, Sequence

import polars as pl

from src.check_statements.models import Transaction

__all__ = [
    "build_ledger_account_map",
    "compute_ledger_suggestions",
    "filter_ledger_by_sample",
    "guess_movement_column",
    "ledger_movement_value",
    "make_parse_key",
    "normalise_header_token",
    "read_sample_entries",
]

logger = logging.getLogger(__name__)

_SAMPLE_MOVEMENT_TOKENS = {
    "movementnumber",
    "movementno",
    "movement",
    "numeroregistrazione",
    "numregistrazione",
    "numeroreg",
    "journalid",
    "riga",
    "registrazione",
    "primonota",
}


def build_ledger_account_map(transactions: Sequence[Transaction]) -> dict[Any, str]:
    """Return a mapping of account codes to descriptions."""

    mapping: dict[Any, str] = {}
    for tx in transactions:
        meta = getattr(tx, "metadata", {})
        acc = meta.get("account_id") or meta.get("account_identifier")
        if acc is None:
            continue
        key: Any = acc
        if isinstance(acc, str):
            key = acc.strip().casefold()
            if not key:
                continue
        desc = meta.get("account_desc")
        if isinstance(desc, str):
            desc = desc.strip()
        else:
            desc = ""
        mapping.setdefault(key, desc)
    return mapping


def make_parse_key(
    bank_files: Sequence[Any],
    ledger_files: Sequence[Any],
    account_column: str | None,
    account_desc_column: str | None,
    counter_account_desc_column: str | None,
    extra_desc_column: str | None,
) -> tuple:
    """Return a cache key for the current statement inputs."""

    return (
        tuple((f.name, f.size) for f in bank_files)
        + tuple((f.name, f.size) for f in ledger_files)
        + (
            account_column,
            account_desc_column,
            counter_account_desc_column,
            extra_desc_column,
        )
    )


def normalise_header_token(label: str | None) -> str:
    """Return an alphanumeric lowercase token suitable for header comparisons."""

    if label is None:
        return ""
    normalised = unicodedata.normalize("NFKD", str(label))
    token = "".join(ch for ch in normalised if ch.isalnum()).casefold()
    return token


def read_sample_entries(uploaded: Any) -> pl.DataFrame | None:
    """Return a Polars DataFrame loaded from *uploaded* sample file."""

    if uploaded is None:
        return None
    try:
        data = uploaded.getvalue()
    except Exception as exc:
        logger.exception("Reading sample entries file failed: %s", exc)
        return None
    name = getattr(uploaded, "name", "").lower()
    try:
        if name.endswith(".csv"):
            return pl.read_csv(io.BytesIO(data))
        if name.endswith((".xlsx", ".xls")):
            return pl.read_excel(io.BytesIO(data))
        raise ValueError(f"Unsupported sample file type: {name}")
    except Exception as exc:  # pragma: no cover - depends on polars optional deps
        logger.exception("Parsing sample entries file failed: %s", exc)
        return None


def guess_movement_column(columns: Sequence[str]) -> int:
    """Return an index hint for the movement number column."""

    try:
        tokens = [normalise_header_token(col) for col in columns]
        for idx, token in enumerate(tokens):
            if token in _SAMPLE_MOVEMENT_TOKENS:
                return idx
    except Exception:
        logger.exception("Guessing movement column failed")
    return 0 if columns else -1


def ledger_movement_value(txn: Transaction) -> str | None:
    """Return the movement identifier for *txn* if present."""

    meta = getattr(txn, "metadata", {}) or {}
    if not isinstance(meta, dict):
        return None
    for key, value in meta.items():
        if value is None:
            continue
        if normalise_header_token(str(key)) in _SAMPLE_MOVEMENT_TOKENS:
            text = str(value).strip()
            if text:
                return text
    for candidate in ("journal_id", "movement_number", "movement", "riga"):
        value = meta.get(candidate)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def filter_ledger_by_sample(
    ledger_rows: Sequence[Transaction] | None, sample_movements: set[str]
) -> tuple[list[Transaction], set[str]]:
    """Return ledger rows restricted to *sample_movements* and the matched movement ids."""

    if not ledger_rows:
        return [], set()
    if not sample_movements:
        return list(ledger_rows), set()
    filtered: list[Transaction] = []
    matched: set[str] = set()
    for tx in ledger_rows:
        mov = ledger_movement_value(tx)
        if mov and mov in sample_movements:
            filtered.append(tx)
            matched.add(mov)
    return filtered, matched


def compute_ledger_suggestions(
    ledger_files: list[Any],
    cols: list[str],
    cache: dict[str, dict[str, int | None]] | None = None,
) -> tuple[dict[str, int | None], dict[str, dict[str, int | None]]]:
    """Return suggested indices for ledger selectors using header + content heuristics."""

    if not cols:
        empty = {k: None for k in ("account_index", "account_desc_index", "counter_desc_index", "extra_desc_index")}
        return empty, cache or {}

    cache = cache or {}
    sig = "|".join([str(c).strip().casefold() for c in cols])
    cached = cache.get(sig)
    if cached:
        return dict(cached), cache

    df = None
    try:
        if ledger_files:
            lf = ledger_files[0]
            name = getattr(lf, "name", "").lower()
            data = lf.getvalue() if hasattr(lf, "getvalue") else None
            if data is not None:
                bio = io.BytesIO(data)
                if name.endswith(".csv"):
                    df = pl.read_csv(bio, n_rows=200)
                elif name.endswith((".xlsx", ".xls", ".xlsb")):
                    try:
                        df = pl.read_excel(source=bio, has_header=True, engine="calamine").head(200)
                    except Exception as exc:
                        logger.exception("Failed to sample ledger Excel for mapping: %s", exc)
                        df = None
    except Exception as exc:
        logger.exception("Failed to infer ledger sample for mapping: %s", exc)
        df = None

    def _norm_col_name(name: str) -> str:
        base = str(name or "").strip()
        base = re.sub(r"\s+", " ", base)
        decomposed = unicodedata.normalize("NFKD", base)
        without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
        return without_accents.casefold()

    col_lookup: dict[str, str] = {}
    if df is not None:
        col_lookup = {col: col for col in df.columns}
        for col in list(col_lookup):
            norm = _norm_col_name(col)
            col_lookup.setdefault(norm, col)

    def _resolve_column(name: str) -> str | None:
        if df is None:
            return None
        if name in df.columns:
            return name
        norm_name = _norm_col_name(name)
        return col_lookup.get(norm_name)

    def _col_vals(i: int) -> list[str]:
        if df is None or i >= len(cols):
            return []
        column_name = cols[i]
        resolved = _resolve_column(column_name)
        if resolved is None:
            logger.error("Failed to extract column values for mapping: %s", column_name)
            return []
        try:
            series = df.get_column(resolved).head(200).cast(pl.Utf8, strict=False).fill_null("")
            return [str(x) for x in series.to_list()]
        except Exception as exc:
            logger.exception("Failed to extract column values for mapping: %s", exc)
            return []

    def _is_date_like(name: str) -> bool:
        n = name.casefold()
        return any(t in n for t in ("date", "data", "valuta", "value", "accounting", "contab", "time", "ora"))

    def _is_amount_like(name: str) -> bool:
        n = name.casefold()
        return any(t in n for t in ("amount", "importo", "debit", "credit", "dare", "avere", "saldo", "balance"))

    def _iban_count(values: list[str]) -> int:
        pat = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", re.IGNORECASE)
        return sum(1 for v in values if pat.search(v or ""))

    def _code_score(values: list[str]) -> float:
        tot = 0
        hits = 0
        for value in values:
            s = str(value or "").strip()
            if not s:
                continue
            tot += 1
            compact = len(s.replace(" ", "")) >= 8
            alpha_num_ratio = (sum(ch.isalpha() for ch in s) + sum(ch.isdigit() for ch in s)) / max(1, len(s))
            if compact and alpha_num_ratio > 0.7 and s.count(" ") <= 1:
                hits += 1
        return hits / tot if tot else 0.0

    def _text_richness(values: list[str]) -> float:
        tot = 0
        rich = 0
        for value in values:
            s = str(value or "").strip()
            if not s:
                continue
            tot += 1
            letters = sum(ch.isalpha() for ch in s)
            digits = sum(ch.isdigit() for ch in s)
            if letters > digits:
                rich += 1
        return rich / tot if tot else 0.0

    def _diversity(values: list[str]) -> float:
        vals = [str(v or "").strip() for v in values if str(v or "").strip()]
        if not vals:
            return 0.0
        return len(set(vals)) / len(vals)

    preferred_names = {
        "account_index": ("codice conto", "cod. conto", "numero conto", "num. conto"),
        "account_desc_index": ("descr. conto", "descrizione conto", "descrizione del conto"),
        "counter_desc_index": ("descr. causale", "descrizione causale", "descrizione contropartita"),
        "extra_desc_index": ("descr. agg.", "descrizione agg.", "descrizione aggiuntiva"),
    }

    def _exact_match(targets: tuple[str, ...]) -> int | None:
        lowered = [str(c or "").strip().casefold() for c in cols]
        for target in targets:
            if target in lowered:
                return lowered.index(target)
        return None

    acc_scores: list[tuple[float, int]] = []
    desc_scores: list[tuple[float, int]] = []
    cnt_scores: list[tuple[float, int]] = []
    extra_scores: list[tuple[float, int]] = []
    for i, name in enumerate(cols):
        normalized = str(name or "").casefold()
        vals = _col_vals(i)
        iban = _iban_count(vals)
        code = _code_score(vals)
        text = _text_richness(vals)
        div = _diversity(vals)
        h_acc = any(t in normalized for t in ("iban", "account", "conto", "codice", "c/c", "acct"))
        h_desc = any(t in normalized for t in ("descr", "description", "name"))
        h_cnt = any(t in normalized for t in ("contropart", "controparte", "counterparty", "counter account", "causale"))
        h_extra = any(
            t in normalized
            for t in ("descrizione agg", "descr. agg", "aggiunt", "extra", "note", "notes", "dettagli", "details")
        )
        is_bad = _is_date_like(normalized) or _is_amount_like(normalized)
        acc_score = (5.0 * (1 if h_acc else 0)) + (6.0 if iban > 0 else 0.0) + (3.0 * code) + (1.0 * div) - (
            4.0 if is_bad else 0.0
        )
        acc_scores.append((acc_score, i))
        desc_score = (3.0 * (1 if h_desc else 0)) + (3.0 * text) + (2.0 * div) - (3.0 if is_bad else 0.0)
        desc_scores.append((desc_score, i))
        cnt_score = (4.0 * (1 if h_cnt else 0)) + (2.0 * (1 if h_desc else 0)) + (2.0 * text) + (
            1.0 * div
        ) - (3.0 if is_bad else 0.0)
        cnt_scores.append((cnt_score, i))
        extra_score = (4.0 * (1 if h_extra else 0)) + (1.5 * text) + (1.0 * div) - (2.0 if is_bad else 0.0)
        extra_scores.append((extra_score, i))

    acc_scores.sort(key=lambda x: (-x[0], x[1]))
    account_index = acc_scores[0][1] if acc_scores else None
    forced_account = _exact_match(preferred_names["account_index"])
    if forced_account is not None:
        account_index = forced_account

    def _pick(best_list: list[tuple[float, int]], taken: set[int]) -> int | None:
        for _score, idx in best_list:
            if idx not in taken:
                return idx
        return None

    taken = set([account_index]) if account_index is not None else set()
    desc_scores.sort(key=lambda x: (-x[0], x[1]))
    account_desc_index = _pick(desc_scores, taken)
    forced_desc = _exact_match(preferred_names["account_desc_index"])
    if forced_desc is not None and forced_desc not in taken:
        account_desc_index = forced_desc
    if account_desc_index is not None:
        taken.add(account_desc_index)
    cnt_scores.sort(key=lambda x: (-x[0], x[1]))
    counter_desc_index = _pick(cnt_scores, taken)
    forced_counter = _exact_match(preferred_names["counter_desc_index"])
    if forced_counter is not None and forced_counter not in taken:
        counter_desc_index = forced_counter
    if counter_desc_index is not None:
        taken.add(counter_desc_index)
    extra_scores.sort(key=lambda x: (-x[0], x[1]))
    extra_desc_index = _pick(extra_scores, taken)
    forced_extra = _exact_match(preferred_names["extra_desc_index"])
    if forced_extra is not None and forced_extra not in taken:
        extra_desc_index = forced_extra

    out = {
        "account_index": account_index,
        "account_desc_index": account_desc_index,
        "counter_desc_index": counter_desc_index,
        "extra_desc_index": extra_desc_index,
    }
    cache[sig] = out
    return out, cache
