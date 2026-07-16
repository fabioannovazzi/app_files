from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

import pytest

# Ensure 'src' on path
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import statements.orchestrator as orch_mod
from finance.bank_statements.model import BankTransaction


class _StubIngestor:
    def ingest(self, file_path: str):
        # Minimal Document with a single kept page
        return SimpleNamespace(pages=["02/04/2024 example page with transactions"])


class _StubClassifier:
    def classify(
        self, text: str, lang_hint: str | None, page_index: int, is_last_page: bool
    ):
        # Always treat as transaction page with high confidence
        return ("transaction", 0.99, {"mock": True})


class _StubLLMClassifier:
    def classify_excerpt(self, snippet: str, locale: str | None):
        # Never override heuristic classification
        return ("transaction", 0.99)


class _StubAgentic:
    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    def parse(self, path: str) -> Tuple[List[BankTransaction], Any]:
        # Return a single transaction with multi-line style description
        desc = (
            "DISPOSIZIONE A FAVORE DI EXAMPLE SUPPLIER SRL "
            "Num. Bonifico 240938080014162-484842052630 IT05387 – RIF. 24093/0008035071"
        )
        tx = BankTransaction(
            posted_date=date(2024, 4, 2),
            value_date=date(2024, 4, 2),
            description=desc,
            amount=Decimal("-100.00"),
            currency="EUR",
            counterparty=None,
            reference=None,
            raw={},
            source_page=1,
            line_no=1,
            confidence=1.0,
        )
        report = SimpleNamespace(pages_total=1, pages_parsed=1, by_strategy={"stub": 1})
        return [tx], report


def test_orchestrator_enriches_beneficiary_and_references(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # Patch the components used by the orchestrator
    monkeypatch.setattr(orch_mod, "DocumentIngestor", lambda: _StubIngestor())
    monkeypatch.setattr(orch_mod, "PageClassifier", lambda: _StubClassifier())
    monkeypatch.setattr(orch_mod, "LLMPageClassifier", lambda: _StubLLMClassifier())
    monkeypatch.setattr(
        orch_mod, "AgenticStatementParser", lambda *a, **k: _StubAgentic()
    )

    # Create a fake PDF path to satisfy suffix checks
    fake_pdf = tmp_path / "example-bank.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4\n%stub")

    rows, diag = orch_mod.StatementExtractor().orchestrate(
        str(fake_pdf), {"lang": "it"}
    )

    assert len(rows) == 1
    row = rows[0]
    # Beneficiary normalised
    assert row.beneficiary == "example supplier srl"
    # References should contain both the long bonifico number and the RIF.
    assert any("240938080014162-484842052630" in r for r in row.reference_ids)
    assert any("24093/0008035071" in r for r in row.reference_ids)
    # Diagnostics present
    assert diag.strategy_used == "agentic"
