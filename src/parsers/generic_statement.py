"""Generic bank statement parser with hybrid strategies."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

import pdfplumber

from finance.bank_statements.ignore_patterns import ALL_PATTERNS

from .extractors import extract_beneficiary, extract_references
from .keywords import KEYWORDS
from .normalization import (
    DATE_RE,
    EU_NUMBER_RE,
    INT_NUMBER_RE,
    US_NUMBER_RE,
    extract_dates,
    infer_direction,
    parse_amount_any,
    parse_date_token,
)

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """Return a lowercase ASCII representation of *text*."""

    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )


def _is_non_transaction(text: str) -> bool:
    """Check if *text* matches any configured non-transaction pattern."""

    norm = _normalize(text)
    return any(pat.search(norm) for pat in ALL_PATTERNS)


@dataclass
class StatementRow:
    """Structured representation of a transaction row."""

    booking_date: date
    value_date: Optional[date]
    amount: Decimal
    direction: str
    currency: Optional[str]
    description: str
    counterparty: Optional[str]
    beneficiary: Optional[str]
    method: Optional[str]
    reference_ids: List[str] = field(default_factory=list)
    raw_lines: List[str] = field(default_factory=list)


class LLMRowRepair:
    """LLM-assisted repair for ambiguous rows (best-effort)."""

    SYSTEM_PROMPT = (
        "You parse single bank statement rows from noisy PDF text fragments. "
        "Return strict JSON with fields: booking_date, value_date, amount (as number), "
        "currency (3-letter), direction (debit|credit), counterparty, method, "
        "reference_ids[]. If uncertain, leave field null and never fabricate."
    )

    def __init__(
        self,
        deterministic_only: bool = False,
        llm_wrapper: object | None = None,
    ) -> None:
        self.deterministic_only = deterministic_only
        self.llm_wrapper = llm_wrapper
        try:  # optional dependency
            from modules.llm.model_router import query_llm_return_json
        except Exception as e:  # pragma: no cover - optional
            logging.exception(e)
            query_llm_return_json = None  # type: ignore
        self._llm = query_llm_return_json

    def repair(self, row: StatementRow) -> StatementRow:
        if self.deterministic_only or not self._llm or not self.llm_wrapper:
            return row
        try:
            payload = {"lines": row.raw_lines}
            response = self._llm(
                self.llm_wrapper,
                "generic-statement-row",
                self.SYSTEM_PROMPT,
                str(payload),
                tools=None,
            )
            if isinstance(response, dict):
                booking = response.get("booking_date") or None
                value = response.get("value_date") or None
                amount = response.get("amount")
                direction = response.get("direction")
                currency = response.get("currency")
                if booking:
                    row.booking_date = parse_date_token(str(booking))
                if value:
                    row.value_date = parse_date_token(str(value))
                if amount is not None:
                    row.amount = Decimal(str(amount))
                if direction:
                    row.direction = direction
                if currency:
                    row.currency = str(currency)
                row.counterparty = response.get("counterparty") or row.counterparty
                row.beneficiary = response.get("beneficiary") or row.beneficiary
                if row.counterparty and not row.beneficiary:
                    row.beneficiary = row.counterparty
                row.method = response.get("method") or row.method
                if isinstance(response.get("reference_ids"), list):
                    row.reference_ids.extend(
                        str(r) for r in response.get("reference_ids") if r
                    )
        except Exception as e:  # pragma: no cover - best effort
            logging.exception(e)
            logger.debug("LLM repair failed: %s", e)
        return row


class GenericStatementParser:
    """Hybrid parser for multilingual bank statements."""

    def __init__(
        self,
        deterministic_only: bool = False,
        progress_callback: (
            Callable[[float, int, Tuple[date, date]], None] | None
        ) = None,
        strict: bool = False,
        llm_wrapper: object | None = None,
    ) -> None:
        """Create a parser.

        Args:
            deterministic_only: Disable LLM-based repair when ``True``.
            progress_callback: Optional function called after each page with
                ``(file_progress, rows_so_far, date_range)``.
            strict: Propagate parsing errors instead of suppressing them.
            llm_wrapper: Optional LLM wrapper for repair calls.
        """
        self.deterministic_only = deterministic_only
        self.progress_callback = progress_callback
        self.strict = strict
        self.repair = LLMRowRepair(deterministic_only, llm_wrapper=llm_wrapper)

    def parse(
        self,
        file_path: str,
        locale_hint: str | None = None,
        progress_callback: (
            Callable[[float, int, Tuple[date, date]], None] | None
        ) = None,
    ) -> List[StatementRow]:
        """Parse the given PDF file and return statement rows.

        Args:
            file_path: Path to the PDF to parse.
            locale_hint: Optional language hint for downstream components.
            progress_callback: Optional function invoked after each page with
                ``(file_progress, rows_so_far, date_range)``. Overrides the
                callback passed at construction time.
        """
        p = Path(file_path)
        if p.suffix.lower() != ".pdf":
            raise ValueError("Only PDF files are supported")
        rows: List[StatementRow] = []
        cb = progress_callback or self.progress_callback
        with pdfplumber.open(p) as pdf:
            total_pages = len(pdf.pages) or 1
            rows_so_far = 0
            min_date: date | None = None
            max_date: date | None = None
            for page_idx, page in enumerate(pdf.pages):
                before = len(rows)
                text = page.extract_text() or ""
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                lines = self._filter_lines(lines)
                table_rows = self._try_table(page)
                if table_rows:
                    rows.extend(table_rows)
                else:
                    rows.extend(self._parse_lines(lines, locale_hint, None))
                new_rows = rows[before:]
                for r in new_rows:
                    rows_so_far += 1
                    if min_date is None or r.booking_date < min_date:
                        min_date = r.booking_date
                    if max_date is None or r.booking_date > max_date:
                        max_date = r.booking_date
                if cb:
                    file_progress = (page_idx + 1) / total_pages
                    try:
                        cb(file_progress, rows_so_far, (min_date, max_date))
                    except Exception as e:
                        logging.exception(e)
                        logger.warning(
                            "progress callback failed on page %s; ignoring callback error",
                            page_idx + 1,
                            exc_info=True,
                        )
        logger.info("parsed %d rows from %s", len(rows), file_path)
        return rows

    # -- segmentation helpers -------------------------------------------------
    # Summary or footer markers. Many statements prefix opening/closing balance
    # lines (e.g. "SALDO INIZIALE", "CHIUSURA") with a date and amount. Allow
    # for these optional tokens so such lines are filtered out before parsing
    # transactions.
    SUMMARY_RE = re.compile(
        r"^\s*(?:"
        # Optional date and amount before balance keywords
        r"(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\s+)?(?:-?[0-9.,\s]+)?\s*"
        r"(?:saldo(?:\s+iniziale|\s+finale|\s+liquido\s+finale|\s+contabile\s+finale)?|chiusura(?:\s+contabile)?)"
        r"|mod\."
        r"|riepilogo(?:\s+movimenti|\s+competenze)?"
        r"|riassunto"
        r"|elementi\s+per\s+il\s+conteggio(?:\s+delle\s+competenze)?"
        r"|totale"
        r"|interessi"
        r"|spese"
        r"|imposte?"
        r"|saldo\s+liquido\s+finale"
        r"|saldo\s+contabile\s+finale"
        r"|summary"
        r"|totals?"
        r"|overall"
        r"|interest\s+summary"
        r"|fees\s+summary"
        r"|tax\s+summary"
        r"|balance\s+summary"
        r"|zusammenfassung"
        r"|ubersicht"
        r"|zins"
        r"|gebuhren"
        r"|gebuehren"
        r"|steuern"
        r"|saldo"
        r"|schlusssaldo"
        r"|recapitulatif"
        r"|resume"
        r"|recap"
        r"|interets"
        r"|frais"
        r"|impots"
        r"|solde\s+final"
        r"|resumen(?:\s+de\s+movimientos|\s+de\s+comisiones)?"
        r"|resumen"
        r"|intereses"
        r"|comisiones"
        r"|impuestos"
        r"|saldo\s+final"
        r"|totalenumeri"
        r")",
        re.I,
    )

    PAGE_RE = re.compile(
        r"^\s*(?:pag(?:ina)?\.?:?|page)\s*\d+(?:\s*(?:di|of)\s*\d+)?\s*$",
        re.I,
    )

    DATE_LINE_RE = re.compile(r"^\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}")

    def _filter_lines(self, lines: Iterable[str]) -> List[str]:
        """Remove summary, footer, and pagination lines from the PDF text."""

        filtered: List[str] = []
        for ln in lines:
            stripped = ln.strip()
            if not stripped:
                continue
            norm = _normalize(stripped)
            # Skip opening/closing balance lines and other known non-transactions.
            if (
                _is_non_transaction(norm)
                or self.SUMMARY_RE.match(norm)
                or self.PAGE_RE.match(norm)
                or norm.startswith("saldo iniziale")
                or norm.startswith("saldo finale")
            ):
                continue
            filtered.append(stripped)
        return filtered

    # -- strategy: table -------------------------------------------------------
    def _try_table(self, page: pdfplumber.page.Page) -> List[StatementRow]:
        table_rows: List[StatementRow] = []
        try:
            tables = page.extract_tables() or []
        except Exception as e:
            logging.exception(e)
            tables = []
        # Helper to attempt enrichment from free text by merging continuation lines
        def _enrich_from_text(rows: List[StatementRow]) -> None:
            try:
                text = page.extract_text(layout=True, x_tolerance=2, y_tolerance=2) or page.extract_text() or ""
                if not text:
                    return
                raw_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                # Build segments starting with a date token and carrying following lines
                segments: List[str] = []
                current: str | None = None
                for ln in raw_lines:
                    if self.DATE_LINE_RE.match(ln):
                        if current:
                            segments.append(current)
                        current = ln
                    else:
                        if current:
                            current += " " + ln
                if current:
                    segments.append(current)

                # Pre-parse segments into (date_str, amount_abs, text)
                parsed_segments: List[Tuple[str, Decimal | None, str]] = []
                for seg in segments:
                    # First date-like token in the segment
                    m = DATE_RE.search(seg)
                    dtok = m.group(0) if m else ""
                    # Heuristic: last number-looking token is the amount
                    token_match = (
                        EU_NUMBER_RE.search(seg)
                        or US_NUMBER_RE.search(seg)
                        or INT_NUMBER_RE.search(seg)
                    )
                    amt_val: Decimal | None = None
                    if token_match:
                        try:
                            amt_val = parse_amount_any(token_match.group(0))
                        except Exception:
                            amt_val = None
                    parsed_segments.append((dtok, amt_val, seg))

                # Match each table row by (booking date string, absolute amount)
                for r in rows:
                    try:
                        dtok = r.booking_date.strftime("%d/%m/%Y") if r.booking_date else ""
                    except Exception:
                        dtok = ""
                    for (sd, sa, stext) in parsed_segments:
                        if not sd or not dtok or sd != dtok:
                            continue
                        if sa is None:
                            continue
                        try:
                            if abs(abs(r.amount) - abs(sa)) <= Decimal("0.01"):
                                if stext and stext not in r.description:
                                    r.description = (r.description + " " + stext).strip()
                                # Also refresh extracted fields from the richer text
                                if not r.reference_ids:
                                    r.reference_ids = extract_references(r.description)
                                if not r.beneficiary:
                                    ben = extract_beneficiary(r.description)
                                    r.beneficiary = ben
                                    r.counterparty = r.counterparty or ben
                                break
                        except Exception:
                            continue
            except Exception:
                # Best-effort enrichment; never break table parsing
                return
        for tbl in tables:
            if not tbl or len(tbl) < 2:
                continue
            # Gracefully handle missing or non-string header cells.
            # Some PDFs yield ``None`` or numeric objects in the header row,
            # which previously triggered ``AttributeError`` when calling
            # ``lower``. Coerce each cell to ``str`` and substitute empty
            # strings for ``None`` so that subsequent ``index`` lookups can
            # safely fail with ``ValueError`` when expected header labels are
            # absent.
            raw_header = [str(c) if c is not None else "" for c in tbl[0]]
            header = [
                (
                    unicodedata.normalize("NFKD", str(c))
                    .encode("ascii", "ignore")
                    .decode("ascii")
                    .lower()
                    .strip()
                )
                for c in raw_header
            ]
            # Flexible header detection across languages
            def _find_idx(names: list[str]) -> int | None:
                for i, h in enumerate(header):
                    for n in names:
                        if n in h:
                            return i
                return None
            date_aliases = [
                "data",
                "date",
                "fecha",
                "datum",
                "comptable",
                "operation",
                "buchung",
            ]
            amount_aliases = ["importo", "amount", "betrag", "importe", "montant"]
            debit_aliases = ["uscite", "addebito", "debit", "abbuchung", "cargo", "soll"]
            credit_aliases = ["entrate", "accredito", "credit", "gutschrift", "abono", "haben"]
            desc_aliases = [
                "descrizione",
                "causale",
                "description",
                "beschreibung",
                "concepto",
                "verwendungszweck",
                "libelle",
            ]
            d_idx = _find_idx(date_aliases)
            amt_idx = _find_idx(amount_aliases)
            deb_idx = _find_idx(debit_aliases)
            cre_idx = _find_idx(credit_aliases)
            # Require a date column and either 'amount' or both debit/credit
            if d_idx is None or (amt_idx is None and (deb_idx is None or cre_idx is None)):
                continue
            # Best-effort description column
            desc_idx = _find_idx(desc_aliases)
            for row in tbl[1:]:
                d_str = row[d_idx]
                if not d_str:
                    continue
                # Determine amount from single amount column or debit/credit pair
                a_val: Decimal | None = None
                if amt_idx is not None:
                    a_str = row[amt_idx]
                    if not a_str:
                        continue
                    try:
                        a_val = parse_amount_any(str(a_str))
                    except Exception as e:
                        logging.exception(e)
                        a_val = None
                else:
                    d_col = row[deb_idx] if deb_idx is not None else None
                    c_col = row[cre_idx] if cre_idx is not None else None
                    try:
                        d_amt = parse_amount_any(str(d_col)) if d_col else None
                        c_amt = parse_amount_any(str(c_col)) if c_col else None
                    except Exception as e:
                        logging.exception(e)
                        d_amt = c_amt = None
                    if d_amt is None and c_amt is None:
                        continue
                    if d_amt and (c_amt is None or float(abs(d_amt)) > 0.0):
                        a_val = -abs(d_amt)
                    elif c_amt is not None:
                        a_val = abs(c_amt)
                if a_val is None:
                    continue
                try:
                    d = parse_date_token(str(d_str))
                except Exception as e:
                    logging.exception(e)
                    continue
                # Build description: prefer a detected description column, else join the rest
                if desc_idx is not None:
                    desc = str(row[desc_idx] or "").strip()
                else:
                    excl = {d_idx}
                    if amt_idx is not None:
                        excl.add(amt_idx)
                    if deb_idx is not None:
                        excl.add(deb_idx)
                    if cre_idx is not None:
                        excl.add(cre_idx)
                    desc = " ".join(
                        str(c) for i, c in enumerate(row) if i not in excl and c is not None
                    ).strip()
                if not desc or _is_non_transaction(desc):
                    continue
                direction = "credit" if a_val >= 0 else "debit"
                ben = extract_beneficiary(desc)
                table_rows.append(
                    StatementRow(
                        booking_date=d,
                        value_date=None,
                        amount=abs(a_val),
                        direction=direction,
                        currency=None,
                        description=desc,
                        counterparty=ben,
                        beneficiary=ben,
                        method=None,
                        reference_ids=extract_references(desc),
                        raw_lines=[" ".join(str(c) for c in row if c)],
                    )
                )
            if table_rows:
                # Attempt a single pass of enrichment from page text
                _enrich_from_text(table_rows)
                break
        return table_rows

    # -- strategy: text --------------------------------------------------------
    def _parse_lines(
        self,
        lines: List[str],
        lang: str | None = None,
        currency_hint: str | None = None,
    ) -> List[StatementRow]:
        rows_so_far: List[StatementRow] = []
        current_raw_lines: List[str] = []
        for line in lines:
            if self.DATE_LINE_RE.match(line):
                if current_raw_lines:
                    row = self._build_row(current_raw_lines, lang, currency_hint)
                    if (
                        row
                        and row.description
                        and not _is_non_transaction(row.description)
                    ):
                        rows_so_far.append(row)
                current_raw_lines = [line]
            else:
                if current_raw_lines:
                    current_raw_lines.append(line)
        if current_raw_lines:
            row = self._build_row(current_raw_lines, lang, currency_hint)
            if row and row.description and not _is_non_transaction(row.description):
                rows_so_far.append(row)
        return rows_so_far

    def _build_row(
        self,
        lines: List[str],
        lang: str | None = None,
        currency_hint: str | None = None,
    ) -> Optional[StatementRow]:
        tokens = lines[0].split()
        dates = extract_dates(tokens[:3])
        if not dates:
            return None
        booking = dates[0]
        value = dates[1] if len(dates) > 1 else None
        amt = None
        amt_token = None
        amt_line_idx = 0
        for idx, ln in enumerate(lines[:3]):
            clean = DATE_RE.sub("", ln)
            amt_candidate = parse_amount_any(clean)
            if amt_candidate is not None:
                token_match = (
                    EU_NUMBER_RE.search(clean)
                    or US_NUMBER_RE.search(clean)
                    or INT_NUMBER_RE.search(clean)
                )
                if token_match:
                    amt_token = token_match.group()
                amt = amt_candidate
                amt_line_idx = idx
                break
        if amt is None:
            for ln in lines[3:5]:
                clean = DATE_RE.sub("", ln)
                amt_candidate = parse_amount_any(clean)
                if amt_candidate is not None:
                    token_match = (
                        EU_NUMBER_RE.search(clean)
                        or US_NUMBER_RE.search(clean)
                        or INT_NUMBER_RE.search(clean)
                    )
                    if token_match:
                        amt_token = token_match.group()
                    amt = amt_candidate
                    break
        if (
            amt is not None
            and abs(amt) > Decimal("100000000")
            and (amt_token and "," not in amt_token and "." not in amt_token)
        ):
            amt = None
        description = " ".join(ln.strip() for ln in lines).strip()
        if amt is None and not re.search(r"[A-Za-z]", DATE_RE.sub("", description)):
            return None
        direction = "credit" if (amt or Decimal(0)) >= 0 else "debit"
        inferred = infer_direction(description)
        if inferred:
            direction = inferred
        ben = extract_beneficiary(description)
        row = StatementRow(
            booking_date=booking,
            value_date=value,
            amount=abs(amt) if amt is not None else Decimal(0),
            direction=direction,
            currency=None,
            description=description,
            counterparty=ben,
            beneficiary=ben,
            method=None,
            reference_ids=extract_references(description),
            raw_lines=lines,
        )
        if amt is None or not inferred:
            row = self.repair.repair(row)
        if not row.reference_ids:
            row.reference_ids = extract_references(row.description)
        if not row.counterparty and not row.beneficiary:
            ben = extract_beneficiary(row.description)
            row.counterparty = ben
            row.beneficiary = ben
        elif not row.beneficiary and row.counterparty:
            row.beneficiary = row.counterparty
        return row


def extract_statement_rows(
    file_path: str,
    *,
    locale: str | None = None,
    deterministic_only: bool = False,
    llm_wrapper: object | None = None,
) -> List[StatementRow]:
    """Convenience wrapper matching the legacy public surface."""
    parser = GenericStatementParser(
        deterministic_only=deterministic_only, llm_wrapper=llm_wrapper
    )
    return parser.parse(file_path, locale_hint=locale)
