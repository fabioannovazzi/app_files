"""Strategies for extracting transactions from bank statements."""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from typing import List, Protocol

import pdfplumber
from decimal import Decimal

from .bank_statement_locale import DATE_PATTERNS, NEGATIVE_HINTS, POSITIVE_HINTS
from .lexicon import Lexicon
from .model import BankTransaction
from .normalize import combine_debit_credit, detect_language, parse_amount, parse_date

logger = logging.getLogger(__name__)


class StatementParsingStrategy(Protocol):
    """Protocol for statement parsing strategies."""

    name: str

    def can_handle(self, doc: pdfplumber.PDF) -> float:
        """Return confidence that this strategy can parse the document."""

    def parse(self, doc: pdfplumber.PDF) -> List[BankTransaction]:
        """Parse the document into transactions."""


@dataclass
class LayoutAwareTextStrategy:
    name: str = "layout-text"

    def can_handle(self, doc: pdfplumber.PDF) -> float:  # pragma: no cover - heuristics
        first = doc.pages[0].extract_text() or ""
        lex = Lexicon()
        text = " ".join(first.lower().split())
        if any(re.search(pat, text) for pat in lex.header_patterns):
            return 0.9
        return 0.6 if first.strip() else 0.0

    def parse(self, doc: pdfplumber.PDF) -> List[BankTransaction]:
        lines_by_page: List[tuple[int, List[str]]] = []
        counts: dict[str, int] = {}
        for page in doc.pages:
            text = page.extract_text(layout=True, x_tolerance=2, y_tolerance=2) or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            logger.info("page %s: %s lines", page.page_number, len(lines))
            lines_by_page.append((page.page_number, lines))
            for ln in set(lines):
                counts[ln] = counts.get(ln, 0) + 1
        noise = {
            ln for ln, c in counts.items() if c > 1 or re.match(r"^(Mod\.|Pag\.)", ln)
        }
        clean_lines: List[tuple[int, str]] = []
        for page_no, lines in lines_by_page:
            for ln in lines:
                if ln in noise:
                    continue
                clean_lines.append((page_no, ln))
        date_re = re.compile("|".join(p.pattern for p in DATE_PATTERNS))
        rows: List[tuple[int, str]] = []
        current: str | None = None
        current_page = 0
        for page_no, ln in clean_lines:
            if date_re.match(ln):
                if current:
                    rows.append((current_page, current.strip()))
                current = ln
                current_page = page_no
            else:
                if current:
                    current += " " + ln
        if current:
            rows.append((current_page, current.strip()))
        logger.info("candidate rows: %s", len(rows))
        lang = detect_language(clean_lines[0][1] if clean_lines else "")
        transactions: List[BankTransaction] = []
        number_re = re.compile(r"[+-]?\d[\d.,]*")
        debug_rows: List[dict[str, object]] = []
        for page_no, raw in rows:
            parts = raw.split()
            if not parts or not date_re.match(parts[0]):
                continue
            posted = parse_date(parts[0], lang)
            if posted is None:
                continue
            value_date = None
            idx = 1
            if idx < len(parts) and date_re.match(parts[idx]):
                value_date = parse_date(parts[idx], lang)
                if value_date is not None:
                    idx += 1
            num_indices = [i for i, p in enumerate(parts[idx:]) if number_re.match(p)]
            debit = credit = None
            desc_start = idx
            if len(num_indices) >= 2:
                debit = parts[idx + num_indices[0]]
                credit = parts[idx + num_indices[1]]
                desc_start = idx + num_indices[1] + 1
                debit_amt = parse_amount(debit, lang)
                credit_amt = parse_amount(credit, lang)
                amount = credit_amt - debit_amt
            elif len(num_indices) == 1:
                amount_str = parts[idx + num_indices[0]]
                desc_start = idx + num_indices[0] + 1
                amount = parse_amount(amount_str, lang)
                desc_lower = " ".join(parts[desc_start:]).lower()
                if any(h in desc_lower for h in NEGATIVE_HINTS):
                    amount = -abs(amount)
                elif any(h in desc_lower for h in POSITIVE_HINTS):
                    amount = abs(amount)
            else:
                continue
            desc = " ".join(parts[desc_start:]).strip()
            transactions.append(
                BankTransaction(
                    posted_date=posted,
                    value_date=value_date,
                    description=desc,
                    amount=amount,
                    currency=None,
                    raw={"row": raw},
                    source_page=page_no,
                )
            )
            debug_rows.append({"page": page_no, "row": raw})
        logger.info("valid rows: %s", len(transactions))
        self.debug_rows = debug_rows  # type: ignore[attr-defined]
        return transactions


@dataclass
class TabularExtractionStrategy:
    name: str = "tabular"

    def can_handle(self, doc: pdfplumber.PDF) -> float:  # pragma: no cover - heuristics
        for page in doc.pages:
            if page.extract_table():
                return 0.8
        return 0.0

    def parse(self, doc: pdfplumber.PDF) -> List[BankTransaction]:
        lex = Lexicon()
        transactions: List[BankTransaction] = []
        for page in doc.pages:
            table = page.extract_table()
            if not table:
                continue
            # Keep track of transaction indices for this page to allow enrichment later
            start_idx = len(transactions)
            header_idx = None
            for idx, row in enumerate(table):
                text = " ".join(c.lower() for c in row if c)
                for pat in lex.header_patterns:
                    if re.search(pat, text):
                        header_idx = idx
                        break
                if header_idx is not None:
                    break
            if header_idx is None:
                continue
            header = [c.lower() if c else "" for c in table[header_idx]]
            for row in table[header_idx + 1 :]:
                raw = {header[i]: row[i] for i in range(len(header))}
                posted = parse_date(row[0], "en")
                if posted is None:
                    continue
                amount = None
                if "debit" in header and "credit" in header:
                    debit = row[header.index("debit")]
                    credit = row[header.index("credit")]
                    amount = combine_debit_credit(debit, credit, "en")
                elif "amount" in header:
                    amount = parse_amount(row[header.index("amount")], "en")
                if amount is None:
                    continue
                desc = (
                    row[header.index("description")] if "description" in header else ""
                )
                currency = (
                    row[header.index("currency")] if "currency" in header else None
                )
                transactions.append(
                    BankTransaction(
                        posted_date=posted,
                        value_date=None,
                        description=desc,
                        amount=amount,
                        currency=currency,
                        raw=raw,
                        source_page=page.page_number,
                    )
                )
            # Enrichment: many banks place references/IBAN on continuation lines
            # outside the table. Merge those lines into the description by
            # reconstructing line-based rows from page text and matching on
            # (date, amount).
            try:
                text = (
                    page.extract_text(layout=True, x_tolerance=2, y_tolerance=2) or ""
                )
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                # Build merged rows keyed by (date, amount)
                date_re = re.compile("|".join(p.pattern for p in DATE_PATTERNS))
                number_re = re.compile(r"[+-]?\d[\d.,]*")
                merged: list[tuple[str, str, str]] = (
                    []
                )  # (date_token, amount_token, desc)
                current: str | None = None
                for ln in lines:
                    if date_re.match(ln):
                        if current:
                            # finalise previous
                            parts = current.split()
                            dt = parts[0] if parts else ""
                            nums = [m.group(0) for m in number_re.finditer(current)]
                            amt_tok = nums[-1] if nums else ""
                            desc_txt = current
                            merged.append((dt, amt_tok, desc_txt))
                        current = ln
                    else:
                        if current:
                            current += " " + ln
                if current:
                    parts = current.split()
                    dt = parts[0] if parts else ""
                    nums = [m.group(0) for m in number_re.finditer(current)]
                    amt_tok = nums[-1] if nums else ""
                    desc_txt = current
                    merged.append((dt, amt_tok, desc_txt))

                # Map merged rows to parsed numeric values for matching
                def _parse_amt(tok: str) -> Decimal | None:
                    try:
                        return parse_amount(tok, "en")
                    except Exception:
                        return None

                merged_parsed: list[tuple[str, Decimal | None, str]] = [
                    (dt, _parse_amt(amt_tok), desc_txt)
                    for (dt, amt_tok, desc_txt) in merged
                ]

                # Update descriptions of transactions from this page when we find a confident match
                for i in range(start_idx, len(transactions)):
                    t = transactions[i]
                    key_dt = t.posted_date.strftime("%d/%m/%Y") if t.posted_date else ""
                    for dt, amt, desc_txt in merged_parsed:
                        if not dt or not key_dt:
                            continue
                        if dt != key_dt:
                            continue
                        if amt is None:
                            continue
                        # Match amount sign and absolute value
                        try:
                            if (Decimal(0) <= t.amount < 0) or (
                                Decimal(0) >= t.amount > 0
                            ):
                                pass  # ignore impossible
                        except Exception:
                            pass
                        if abs(abs(t.amount) - abs(amt)) <= Decimal("0.01"):
                            # Merge continuation details if not already present
                            if desc_txt and desc_txt not in (t.description or ""):
                                t.description = (
                                    (t.description or "") + " " + desc_txt
                                ).strip()
                            break
            except Exception:
                # Enrichment is best-effort; never fail parsing on this step
                pass
        return transactions


@dataclass
class OCRStrategy:
    name: str = "ocr"

    def can_handle(self, doc: pdfplumber.PDF) -> float:  # pragma: no cover - heuristics
        total_chars = sum(len(page.extract_text() or "") for page in doc.pages)
        return 0.5 if total_chars < 20 else 0.0

    def parse(
        self, doc: pdfplumber.PDF
    ) -> List[BankTransaction]:  # pragma: no cover - optional
        try:
            from PIL import Image
            from modules.slides.ocr import extract_text_from_image_bytes
        except Exception as e:
            logging.exception(e)
            return []
        texts = []
        for page in doc.pages:
            img = page.to_image(resolution=300).original
            pil_image = img if isinstance(img, Image.Image) else Image.fromarray(img)
            image_buf = io.BytesIO()
            pil_image.save(image_buf, format="PNG")
            text = extract_text_from_image_bytes(
                image_buf.getvalue(),
                lang="eng",
                preprocess_profile="document_scan",
                allow_preprocess_fallback=True,
            )
            texts.append(text)
        fake_pdf = pdfplumber.open(io.BytesIO("\n".join(texts).encode()))
        return LayoutAwareTextStrategy().parse(fake_pdf)


STRATEGIES: List[StatementParsingStrategy] = [
    LayoutAwareTextStrategy(),
    TabularExtractionStrategy(),
    OCRStrategy(),
]


def choose_strategy(doc: pdfplumber.PDF) -> StatementParsingStrategy:
    """Return the strategy with the highest `can_handle` score."""
    best = STRATEGIES[0]
    best_score = 0.0
    for strat in STRATEGIES:
        score = strat.can_handle(doc)
        logger.info("strategy %s scored %.2f", strat.name, score)
        if score > best_score:
            best_score = score
            best = strat
    logger.info("chosen strategy %s (%.2f)", best.name, best_score)
    return best
