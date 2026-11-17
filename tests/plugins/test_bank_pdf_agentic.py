import copy
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def bank_path(monkeypatch):
    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[2] / "plugins/_shared/vendor/modules")
    )


def word(ref, page, row, text, x):
    return dict(
        id=ref,
        page=page,
        row=row,
        text=text,
        x0=str(x),
        x1=str(x + 8),
        top=str(row * 10),
        bottom=str(row * 10 + 5),
    )


class PageClassificationTests(unittest.TestCase):
    def setUp(self):
        self.inventory = {
            "issues": [],
            "pages": [
                {
                    "page": 1,
                    "words": [
                        word("h1", 1, 1, "OVERVIEW", 65),
                        word("s1", 1, 2, "12,00", 45),
                    ],
                },
                {
                    "page": 2,
                    "words": [
                        word("o", 2, 1, "100,00", 45),
                        word("ol", 2, 1, "OPENING", 65),
                        word("d1", 2, 2, "01/10/26", 1),
                        word("a1", 2, 2, "10,00", 25),
                        word("d2", 2, 3, "02/10/26", 1),
                        word("a2", 2, 3, "2,00", 45),
                        word("c", 2, 4, "92,00", 45),
                        word("cl", 2, 4, "CLOSING", 65),
                    ],
                },
                {
                    "page": 3,
                    "words": [
                        word("h3", 3, 1, "INFORMATION", 65),
                        word("n3", 3, 2, "119", 25),
                    ],
                },
            ],
        }
        self.layout = {
            "document_kind": "bank_statement",
            "body": ["0", "100"],
            "columns": {
                "date": ["0", "20"],
                "debit": ["20", "40"],
                "credit": ["40", "60"],
                "description": ["60", "100"],
            },
            "source_sha256": "a" * 64,
            "recovery_currency": "EUR",
            "date_format": "%d/%m/%y",
            "statement_controls": {
                "opening_balance": {"label": ["ol"], "amount": "o", "column": "credit"},
                "closing_balance": {"label": ["cl"], "amount": "c", "column": "credit"},
            },
            "non_movement_pages": [
                {
                    "page": 1,
                    "classification": "bank_overview",
                    "heading": {"refs": ["h1"], "text": "OVERVIEW"},
                    "numeric_refs": ["s1"],
                },
                {
                    "page": 3,
                    "classification": "customer_information",
                    "heading": {"refs": ["h3"], "text": "INFORMATION"},
                    "numeric_refs": ["n3"],
                },
            ],
        }
        self.proposal = {
            "rows": [
                {
                    "amount": "a1",
                    "column": "debit",
                    "date": ["d1"],
                    "value_date": [],
                    "description": [],
                    "reference": [],
                    "balance": None,
                },
                {
                    "amount": "a2",
                    "column": "credit",
                    "date": ["d2"],
                    "value_date": [],
                    "description": [],
                    "reference": [],
                    "balance": None,
                },
            ]
        }

    def run_case(self):
        from vera_journal_pdf.bank import read_bank_pdf

        with (
            patch(
                "vera_journal_pdf.bank.source_inventory", return_value=self.inventory
            ),
            patch("vera_journal_pdf.bank._run_adapter", return_value=self.proposal),
            patch(
                "vera_journal_pdf.recovery._identity",
                return_value={"source_sha256": "a" * 64},
            ),
        ):
            return read_bank_pdf(Path("synthetic.pdf"), self.layout, currency="EUR")

    def assert_blocked(self, reason):
        rows, diag = self.run_case()
        self.assertEqual(rows, [])
        self.assertFalse(diag["accepted"])
        self.assertIn(reason, {x["reason"] for x in diag["unresolved_issues"]})

    def test_source_bound_review_passes_and_preserves_signed_amounts(self):
        rows, diag = self.run_case()
        self.assertTrue(diag["accepted"])
        self.assertEqual([r["amount"] for r in rows], ["-10.00", "2.00"])
        self.assertEqual(len(diag["non_movement_pages"]), 2)

    def test_no_opt_in_keeps_existing_strict_checks(self):
        del self.layout["non_movement_pages"]
        self.assert_blocked("unclaimed_source_amount")

    def test_changed_source_heading_blocks(self):
        self.inventory["pages"][0]["words"][0]["text"] = "CHANGED"
        self.assert_blocked("non_movement_page_heading_mismatch")

    def test_missing_numeric_disposition_blocks(self):
        self.layout["non_movement_pages"][0]["numeric_refs"] = []
        self.assert_blocked("non_movement_page_numeric_coverage_mismatch")

    def test_extra_numeric_reference_blocks(self):
        self.layout["non_movement_pages"][0]["numeric_refs"].append("unknown")
        self.assert_blocked("non_movement_page_numeric_coverage_mismatch")

    def test_duplicate_page_blocks(self):
        self.layout["non_movement_pages"].append(
            copy.deepcopy(self.layout["non_movement_pages"][0])
        )
        self.assert_blocked("invalid_or_duplicate_non_movement_page")

    def test_dated_overview_returns_evidence_for_model_review(self):
        self.inventory["pages"][0]["words"].append(word("sd", 1, 2, "03/10/26", 1))
        rows, diag = self.run_case()
        self.assertTrue(diag["accepted"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            diag["review_signals"],
            [
                {
                    "source_page": 1,
                    "reason": "non_movement_page_has_dates_and_amounts",
                    "classification": "bank_overview",
                }
            ],
        )

    def test_new_numeric_token_requires_new_review(self):
        self.inventory["pages"][0]["words"].append(word("new", 1, 3, "9,00", 45))
        self.assert_blocked("non_movement_page_numeric_coverage_mismatch")

    def test_balance_mismatch_still_blocks(self):
        next(w for w in self.inventory["pages"][1]["words"] if w["id"] == "c")[
            "text"
        ] = "91,99"
        self.assert_blocked("bank_opening_movements_closing_mismatch")

    def test_amount_cannot_be_reused(self):
        self.proposal["rows"].append(copy.deepcopy(self.proposal["rows"][0]))
        self.assert_blocked("duplicate_source_amount")

    def test_control_cannot_come_from_excluded_page(self):
        self.layout["statement_controls"]["opening_balance"] = {
            "label": ["h1"],
            "amount": "s1",
            "column": "credit",
        }
        self.assert_blocked("bank_control_on_non_movement_page")

    def test_invalid_classification_blocks(self):
        self.layout["non_movement_pages"][0]["classification"] = "ignore"
        self.assert_blocked("invalid_non_movement_page_classification")


class MovementBlockTests(PageClassificationTests):
    def setUp(self):
        super().setUp()
        self.layout["movement_strategy"] = "source_blocks"
        w = self.inventory["pages"][1]["words"]
        for token in w:
            token["row"] *= 3
            token["top"] = str(token["row"] * 5)
        w.extend(
            [
                word("t1", 2, 5, "Before", 65),
                word("t2", 2, 6, "Amount", 65),
                word("t3", 2, 7, "After", 65),
                word("t4", 2, 9, "Second", 65),
            ]
        )
        self.proposal["rows"][0].update(
            description=["t1", "t2", "t3"], movement_span=["t1", "t3"]
        )
        self.proposal["rows"][1].update(description=["t4"], movement_span=["d2", "t4"])

    def test_multiline_description_before_amount_is_preserved(self):
        rows, diag = self.run_case()
        self.assertTrue(diag["accepted"], diag["unresolved_issues"])
        self.assertEqual(rows[0]["line_desc"], "Before Amount After")

    def test_omitted_description_token_blocks(self):
        self.proposal["rows"][0]["description"] = ["t1", "t3"]
        self.assert_blocked("bank_movement_text_coverage_mismatch")

    def test_overlapping_movement_blocks(self):
        self.proposal["rows"][1]["movement_span"] = ["t3", "t4"]
        self.assert_blocked("bank_movement_spans_overlap")

    def test_block_cannot_take_statement_control(self):
        self.proposal["rows"][0]["movement_span"] = ["o", "t3"]
        self.assert_blocked("bank_span_crosses_control")

    def test_block_cannot_assign_other_movement_text(self):
        self.proposal["rows"][0]["description"].append("t4")
        self.assert_blocked("bank_text_outside_movement_span")

    def test_amount_must_be_inside_block(self):
        self.proposal["rows"][0]["movement_span"] = ["t1", "d1"]
        self.proposal["rows"][1]["movement_span"] = ["t1", "t3"]
        self.assert_blocked("bank_amount_outside_movement_span")
