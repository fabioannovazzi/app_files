"""Orchestrator deciding which extraction strategy to use."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

# New agentic parser for PDFs
from finance.bank_statements.agentic_parser import AgenticStatementParser, ParserConfig
from finance.bank_statements.model import BankTransaction

from modules.utilities.utils import get_schema_and_column_names

from .ingest import Document, DocumentIngestor
from .llm_page_classifier import LLMPageClassifier
from .locale_utils import detect_currency, detect_language
from .page_classifier import PageClassifier
from .row_filters import filter_rows
from .schema import Transaction
from .strategies import (
    strategy_line_heuristics,
    strategy_llm_blocks,
    strategy_table_layout,
)
from parsers.extractors import extract_beneficiary, extract_references

logger = logging.getLogger(__name__)


@dataclass
class Diagnostics:
    language: str = ""
    currency: str = ""
    strategy_used: str = ""
    rows: int = 0
    page_details: List[Dict[str, object]] = field(default_factory=list)


class StatementExtractor:
    """Main entry point for statement extraction."""

    def orchestrate(
        self, file_path: str, config: dict
    ) -> Tuple[List[Transaction], Diagnostics]:
        suffix = Path(file_path).suffix.lower()
        if suffix == ".pdf":
            ingestor = DocumentIngestor()
            document = ingestor.ingest(file_path)
            classifier = PageClassifier()
            llm_classifier = LLMPageClassifier()
            kept_pages: List[str] = []
            page_details: List[Dict[str, object]] = []
            n_pages = len(document.pages)
            for idx, text in enumerate(document.pages):
                label, conf, details = classifier.classify(
                    text,
                    lang_hint=config.get("lang"),
                    page_index=idx,
                    is_last_page=idx == n_pages - 1,
                )
                if label != "transaction" and conf < 0.8:
                    excerpt_lines = text.splitlines()
                    snippet = "\n".join(
                        excerpt_lines[:5]
                        + excerpt_lines[
                            len(excerpt_lines) // 2 : len(excerpt_lines) // 2 + 5
                        ]
                        + excerpt_lines[-5:]
                    )
                    llm_label, llm_conf = llm_classifier.classify_excerpt(
                        snippet, locale=config.get("lang")
                    )
                    if llm_label == "summary" and llm_conf >= 0.8:
                        label, conf = llm_label, llm_conf
                if label == "summary" and conf >= 0.8:
                    page_details.append(
                        {"label": label, "confidence": conf, "details": details}
                    )
                    continue
                kept_pages.append(text)
                page_details.append(
                    {"label": label, "confidence": conf, "details": details}
                )
            document.pages = kept_pages
            parser = AgenticStatementParser(
                ParserConfig(language_hint=config.get("lang"))
            )
            rows, rep = parser.parse(file_path)
            page_map: Dict[int, List[BankTransaction]] = {}
            for r in rows:
                if r.source_page and r.source_page - 1 < len(page_details):
                    if page_details[r.source_page - 1]["label"] == "summary":
                        continue
                page_map.setdefault(r.source_page, []).append(r)
            tx: List[Transaction] = []
            for page_no, entries in page_map.items():
                raw_rows = [
                    f"{e.posted_date or ''} {e.description} {e.amount}" for e in entries
                ]
                kept_rows = filter_rows(raw_rows, lang_hint=config.get("lang"))
                kept_iter = iter(kept_rows)
                current = next(kept_iter, None)
                kept_count = 0
                for entry, raw in zip(entries, raw_rows):
                    if current is not None and raw == current:
                        # Best-effort enrichment from description text
                        desc_text = entry.description or ""
                        refs = extract_references(desc_text)
                        ben = extract_beneficiary(desc_text)
                        # Fallback to parser-provided counterparty if beneficiary not found
                        if not ben and getattr(entry, "counterparty", None):
                            ben = entry.counterparty  # type: ignore[attr-defined]
                        tx.append(
                            Transaction(
                                booking_date=entry.posted_date,
                                value_date=entry.value_date,
                                description=entry.description,
                                amount=entry.amount,
                                currency=entry.currency or "",
                                reference_ids=refs,
                                beneficiary=ben,
                                raw_page=entry.source_page,
                                raw_source="pdf",
                                confidence=entry.confidence,
                            )
                        )
                        kept_count += 1
                        current = next(kept_iter, None)
                detail = page_details[page_no - 1]
                detail["kept_rows"] = kept_count
                detail["dropped_rows"] = len(raw_rows) - kept_count
                logger.info(
                    "page %s classified %s %.2f kept %s dropped %s",
                    page_no,
                    detail["label"],
                    detail["confidence"],
                    kept_count,
                    len(raw_rows) - kept_count,
                )
            diag = Diagnostics(
                language=config.get("lang", ""),
                currency=config.get("currency", ""),
                strategy_used="agentic",
                rows=len(tx),
                page_details=page_details,
            )
            return tx, diag

        ingestor = DocumentIngestor()
        document = ingestor.ingest(file_path)
        text_for_lang = "\n".join(document.pages) if document.pages else ""
        if not text_for_lang and document.tables:
            text_for_lang = " ".join(
                str(c) for c in get_schema_and_column_names(document.tables[0])[0]
            )
        lang = config.get("lang") or detect_language(text_for_lang)[0]
        currency = config.get("currency") or detect_currency(text_for_lang)
        diag = Diagnostics(language=lang, currency=currency)
        strategies = [
            strategy_table_layout,
            strategy_line_heuristics,
            strategy_llm_blocks,
        ]
        for strat in strategies:
            rows = strat(document, lang)
            if len(rows) > 0:
                diag.strategy_used = strat.__name__
                diag.rows = len(rows)
                return rows, diag
        return [], diag
