from __future__ import annotations

import importlib.util
from pathlib import Path

HELPERS = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "audit-reconciliation"
    / "scripts"
    / "reconciliation_helpers.py"
)


def load_helpers():
    spec = importlib.util.spec_from_file_location(
        "audit_reconciliation_helpers", HELPERS
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_document_key_numeric_year_suffix_matches_invoice_series_alias():
    helpers = load_helpers()

    assert helpers.document_key("1524-23", "") == "1524|2023"
    assert "1524|2023" in helpers.record_document_keys({"document_key": "1524FE|2023"})


def test_side_aware_match_uses_expected_side_amount():
    helpers = load_helpers()
    open_item = {"document_key": "INV120|2023", "amount": "77032.64"}
    closure = {
        "document_key": "INV120|2023",
        "supplier_amount": "77032.64",
        "customer_amount": "1079.41",
    }

    assert helpers.side_aware_closure_match(open_item, closure, "supplier")


def test_side_aware_match_rejects_opposite_side_invoice_collision():
    helpers = load_helpers()
    open_item = {"document_key": "INV120|2023", "amount": "77032.64"}
    closure = {
        "document_key": "INV120|2023",
        "side": "customer",
        "customer_amount": "77032.64",
        "bank_amount": "77032.64",
        "description": "bank receipt for receivable invoice",
    }

    assert not helpers.side_aware_closure_match(open_item, closure, "supplier")


def test_grouped_factor_external_total_can_match_without_side_line():
    helpers = load_helpers()
    open_item = {"document_key": "INV-GROUP|2023", "amount": "359421.75"}
    closure = {
        "document_key": "INV-GROUP|2023",
        "evidence_type": "external_factoring",
        "bank_amount": "320848.61",
        "factor_amount": "38573.14",
        "description": "settlement through external operator",
    }

    assert helpers.side_aware_closure_match(open_item, closure, "customer")


def test_reconcile_uses_grouped_external_total_with_expected_side():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [
            {
                "record_id": "open-1",
                "document_key": "INV-GROUP|2023",
                "amount": "359421.75",
                "expected_side": "customer",
            }
        ],
        [
            {
                "record_id": "factor-1",
                "document_key": "INV-GROUP|2023",
                "evidence_type": "external_factoring",
                "bank_amount": "320848.61",
                "factor_amount": "38573.14",
                "description": "external operator settlement",
            }
        ],
    )

    assert rows[0]["reconciliation_status"] == "closed"
    assert rows[0]["matched_evidence_id"] == "factor-1"
    assert rows[0]["rule_applied"] == "factoring_with_bank_or_external_support"
    assert rows[0]["matched_evidence_type"] == "external_factoring"
    assert "bank_amount=320848.61" in rows[0]["matched_evidence_amounts"]


def test_pro_soluto_factoring_document_reference_can_close_partial_advance():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [
            {
                "record_id": "open-1",
                "document_key": "INV-PARTIAL|2023",
                "amount": "53609.37",
                "expected_side": "customer",
            }
        ],
        [
            {
                "record_id": "factor-1",
                "document_key": "INV-PARTIAL|2023",
                "evidence_type": "external_factoring",
                "amount": "42887.49",
                "description": "external factoring advance tied to the invoice",
            }
        ],
        {"factoring_pro_soluto_closes_item": True},
    )

    assert rows[0]["reconciliation_status"] == "closed"
    assert rows[0]["matched_evidence_id"] == "factor-1"
    assert rows[0]["rule_applied"] == "factoring_with_bank_or_external_support"


def test_partial_bank_payment_does_not_close_as_factoring():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [
            {
                "record_id": "open-1",
                "document_key": "INV-PARTIAL|2023",
                "amount": "53609.37",
                "expected_side": "customer",
            }
        ],
        [
            {
                "record_id": "bank-1",
                "document_key": "INV-PARTIAL|2023",
                "evidence_type": "external_bank",
                "amount": "42887.49",
                "description": "partial bank movement",
            }
        ],
    )

    assert rows[0]["reconciliation_status"] == "unresolved"


def test_partial_factoring_does_not_close_when_pro_soluto_assumption_disabled():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [
            {
                "record_id": "open-1",
                "document_key": "INV-PARTIAL|2023",
                "amount": "53609.37",
                "expected_side": "customer",
            }
        ],
        [
            {
                "record_id": "factor-1",
                "document_key": "INV-PARTIAL|2023",
                "evidence_type": "external_factoring",
                "amount": "42887.49",
            }
        ],
        {"factoring_pro_soluto_closes_item": False},
    )

    assert rows[0]["reconciliation_status"] == "unresolved"


def test_external_total_does_not_override_opposite_side_amount():
    helpers = load_helpers()
    open_item = {"document_key": "INV-GROUP|2023", "amount": "359421.75"}
    closure = {
        "document_key": "INV-GROUP|2023",
        "supplier_amount": "359421.75",
        "bank_amount": "320848.61",
        "factor_amount": "38573.14",
        "description": "factoring pro soluto settlement through external operator",
    }

    assert not helpers.side_aware_closure_match(open_item, closure, "customer")


def test_grouped_factor_external_total_still_requires_document_key_by_default():
    helpers = load_helpers()
    open_item = {"document_key": "INV-GROUP|2023", "amount": "359421.75"}
    closure = {
        "document_key": "INV9999|2023",
        "bank_amount": "320848.61",
        "factor_amount": "38573.14",
        "description": "factoring pro soluto settlement through external operator",
    }

    assert not helpers.side_aware_closure_match(open_item, closure, "customer")


def test_factor_keywords_are_operator_generic_not_case_specific():
    helpers = load_helpers()

    assert helpers.has_factor_reference("cessione credito pro-soluto")
    assert helpers.has_factor_reference("factoring settlement")
    assert helpers.has_factor_reference("cession de créance sans recours")
    assert helpers.has_factor_reference("Forderungsabtretung ohne Regress")
    assert not helpers.has_factor_reference("OperatorX settlement")
    assert helpers.has_factor_reference(
        "OperatorX settlement",
        extra_keywords=["OperatorX"],
    )
    assert "factoring_or_advance" in helpers.codex_review_flags(
        {"description": "cessione credito pro-soluto"}
    )


def test_classify_evidence_type_supports_non_italian_compensation_terms():
    helpers = load_helpers()

    assert (
        helpers.classify_evidence_type("ledger", "dokumentierte Verrechnung")
        == "compensation"
    )
    assert (
        helpers.classify_evidence_type("ledger", "documented set-off agreement")
        == "compensation"
    )


def test_missing_evidence_message_uses_report_language():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "INV1|2023", "amount": "100.00"}],
        [
            {
                "record_id": "po-1",
                "evidence_type": "payment_order",
                "document_keys": "INV1|2023",
                "amount": "100.00",
            }
        ],
        {"report_language": "en_US"},
    )

    assert "bank statement" in rows[0]["missing_evidence"]


def test_invoice_refs_in_unallocated_bank_row_create_non_closing_candidate():
    helpers = load_helpers()
    reconciliation_rows = [
        {
            "record_id": "open-377",
            "document_key": "377FE|2023",
            "amount": "100.00",
            "reconciliation_status": "needs_evidence",
        },
        {
            "record_id": "open-378",
            "document_key": "378FE|2023",
            "amount": "200.00",
            "reconciliation_status": "unresolved",
        },
    ]
    evidence_rows = [
        {
            "record_id": "bank-1",
            "source_role": "bank_statement",
            "evidence_type": "unallocated_external_bank",
            "posting_date": "2023-04-11",
            "amount": "300.00",
            "description": "ANTICIPO SU DOCUMENTI ANT. FTT. 377-378",
        }
    ]

    candidates = helpers.bank_allocation_candidates(
        reconciliation_rows,
        evidence_rows,
        {"scope_year": "2023", "cutoff_date": "2023-12-31"},
    )

    assert candidates[0]["candidate_type"] == "invoice_refs_in_bank_description"
    assert candidates[0]["candidate_confidence"] == "high"
    assert candidates[0]["candidate_open_row_count"] == 2
    assert candidates[0]["candidate_amount_match"] == "YES"
    assert candidates[0]["does_not_change_status"] == "YES"


def test_batch_id_candidate_links_bank_to_payment_order_without_closing_rows():
    helpers = load_helpers()
    reconciliation_rows = [
        {
            "record_id": "open-1515",
            "document_key": "1515|2023",
            "amount": "120.00",
            "reconciliation_status": "needs_evidence",
        },
        {
            "record_id": "closed-1516",
            "document_key": "1516|2023",
            "amount": "180.00",
            "reconciliation_status": "closed",
        },
    ]
    evidence_rows = [
        {
            "record_id": "bank-distinta-7",
            "source_role": "bank_statement",
            "evidence_type": "unallocated_external_bank",
            "posting_date": "2023-05-10",
            "amount": "120.00",
            "batch_id": "distinta:7",
            "description": "S.DO DIST.PG.7 EXAMPLE SUPPLIER",
        },
        {
            "record_id": "po-1515",
            "source_role": "payment_order",
            "evidence_type": "payment_order_bridge",
            "document_key": "1515|2023",
            "amount": "120.00",
            "batch_id": "distinta:7",
        },
        {
            "record_id": "po-1516",
            "source_role": "payment_order",
            "evidence_type": "payment_order_bridge",
            "document_key": "1516|2023",
            "amount": "180.00",
            "batch_id": "distinta:7",
        },
    ]

    candidates = helpers.bank_allocation_candidates(
        reconciliation_rows,
        evidence_rows,
        {"scope_year": "2023", "cutoff_date": "2023-12-31"},
    )

    batch = next(
        row for row in candidates if row["candidate_type"] == "batch_id_candidate"
    )
    assert batch["candidate_open_record_ids"] == "open-1515"
    assert batch["candidate_open_row_count"] == 1
    assert batch["candidate_bank_matches_nonclosed_open_total"] == "YES"
    assert "closed-1516" not in batch["candidate_open_record_ids"]


def test_unallocated_bank_pool_candidate_keeps_generic_transfer_visible():
    helpers = load_helpers()
    candidates = helpers.bank_allocation_candidates(
        [
            {
                "record_id": "open-1",
                "document_key": "1|2023",
                "amount": "100.00",
                "reconciliation_status": "unresolved",
            }
        ],
        [
            {
                "record_id": "bank-generic",
                "source_role": "bank_statement",
                "evidence_type": "unallocated_external_bank",
                "posting_date": "2023-06-01",
                "amount": "1000.00",
                "description": "ACCONTO FATTURE CONTROPARTE",
            }
        ],
        {"scope_year": "2023", "cutoff_date": "2023-12-31"},
    )

    assert candidates[0]["candidate_type"] == "unallocated_counterparty_bank_pool"
    assert candidates[0]["candidate_confidence"] == "low"
    assert candidates[0]["candidate_open_row_count"] == 0


def test_probable_bank_candidate_can_promote_open_rows_when_enabled():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [
            {"record_id": "open-377", "document_key": "377FE|2023", "amount": "100.00"},
            {"record_id": "open-378", "document_key": "378FE|2023", "amount": "200.00"},
        ],
        [
            {
                "record_id": "bank-1",
                "source_role": "bank_statement",
                "evidence_type": "unallocated_external_bank",
                "posting_date": "2023-04-11",
                "amount": "300.00",
                "description": "ANTICIPO SU DOCUMENTI ANT. FTT. 377-378",
            }
        ],
        {
            "scope_year": "2023",
            "cutoff_date": "2023-12-31",
            "promote_probable_bank_payments": True,
        },
    )

    assert {row["reconciliation_status"] for row in rows} == {"probable_payment"}
    assert {row["rule_applied"] for row in rows} == {"probable_bank_payment_candidate"}
    assert rows[0]["matched_evidence_type"] == "probable_external_bank"
    assert rows[0]["probable_bank_confidence"] == "high"
    assert rows[0]["prior_reconciliation_status"] == "unresolved"
    assert "pagamento bancario probabile" in rows[0]["missing_evidence"]


def test_exact_probable_bank_candidate_can_close_when_configured():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [
            {"record_id": "open-377", "document_key": "377FE|2023", "amount": "100.00"},
            {"record_id": "open-378", "document_key": "378FE|2023", "amount": "200.00"},
        ],
        [
            {
                "record_id": "bank-1",
                "source_role": "bank_statement",
                "evidence_type": "unallocated_external_bank",
                "posting_date": "2023-04-11",
                "amount": "300.00",
                "description": "PAGAMENTO FTT. 377-378",
            }
        ],
        {
            "scope_year": "2023",
            "cutoff_date": "2023-12-31",
            "promote_probable_bank_payments": True,
            "probable_bank_exact_matches_close": True,
        },
    )

    assert {row["reconciliation_status"] for row in rows} == {"closed"}
    assert {row["rule_applied"] for row in rows} == {
        "external_bank_exact_allocation_match"
    }
    assert rows[0]["matched_evidence_reference"] == "id=bank-1"


def test_closed_factor_row_exposes_supporting_bank_reference():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [
            {
                "record_id": "open-factor",
                "document_key": "INV1|2023",
                "amount": "100.00",
                "expected_side": "customer",
            }
        ],
        [
            {
                "record_id": "factor-1",
                "document_key": "INV1|2023",
                "evidence_type": "external_factoring",
                "amount": "80.00",
                "description": "Cessione pro-soluto factor",
            },
            {
                "record_id": "zzz-bank-1",
                "source_role": "bank_statement",
                "evidence_type": "external_bank",
                "document_key": "INV1|2023",
                "amount": "80.00",
                "source_file": "bank.pdf",
                "source_page": "3",
                "source_row": "12",
                "posting_date": "2023-04-11",
                "description": "Bonifico factor",
            },
        ],
        {"factoring_pro_soluto_closes_item": True},
    )

    assert rows[0]["reconciliation_status"] == "closed"
    assert rows[0]["matched_evidence_id"] == "factor-1"
    assert rows[0]["supporting_bank_record_id"] == "zzz-bank-1"
    assert "file=bank.pdf" in rows[0]["supporting_bank_reference"]


def test_external_evidence_summary_separates_cash_settlement_from_advances():
    helpers = load_helpers()
    rows = [
        {
            "record_id": "bank-direct",
            "source_role": "bank_statement",
            "evidence_type": "unallocated_external_bank",
            "posting_date": "2023-04-01",
            "amount": "100.00",
            "description": "BONIFICO o/c: CUSTOMER A FAVORE DI COMPANY",
        },
        {
            "record_id": "bank-factor",
            "source_role": "bank_statement",
            "evidence_type": "external_bank",
            "posting_date": "2023-04-02",
            "amount": "80.00",
            "description": "BONIFICO o/c: FACTOR A FAVORE DI COMPANY FACTORCO FT. 1",
        },
        {
            "record_id": "bank-advance",
            "source_role": "bank_statement",
            "evidence_type": "unallocated_external_bank",
            "posting_date": "2023-04-03",
            "amount": "50.00",
            "description": "ANTICIPO SU DOCUMENTI ANTICIPO FATTURE CUSTOMER",
        },
        {
            "record_id": "bank-repayment",
            "source_role": "bank_statement",
            "evidence_type": "external_bank",
            "posting_date": "2023-04-04",
            "amount": "30.00",
            "description": "RIENTRO ANTICIPO/FINANZIAMENTO FATT. 1 CUSTOMER",
        },
    ]

    detail = helpers.external_evidence_detail_rows(
        rows,
        {
            "scope_year": "2023",
            "cutoff_date": "2023-12-31",
            "counterparty_keywords": ["customer"],
            "factoring_operator_keywords": ["factorco"],
            "own_party_keywords": ["company"],
            "factoring_pro_soluto_closes_item": True,
        },
    )
    summary = {
        row["external_category"]: row
        for row in helpers.external_evidence_summary(detail)
    }

    assert (
        summary["direct_counterparty_bank_receipt"][
            "settlement_effect_signed_net_debit_minus_credit"
        ]
        == "-100.00"
    )
    assert (
        summary["factor_operator_cash_inflow"][
            "settlement_effect_signed_net_debit_minus_credit"
        ]
        == "-80.00"
    )
    assert (
        summary["bank_advance_credit"][
            "settlement_effect_signed_net_debit_minus_credit"
        ]
        == "0.00"
    )
    assert summary["bank_advance_repayment"]["cash_flow_signed_total"] == "-30.00"
    assert (
        summary["TOTAL"]["settlement_effect_signed_net_debit_minus_credit"] == "-180.00"
    )


def test_explicit_document_key_alias_can_bridge_source_numbering():
    helpers = load_helpers()
    open_item = {
        "document_key": "SRC-001|2023",
        "document_keys": "SRC-001|2023; ERP-001|2023",
    }
    evidence = {"document_key": "ERP-001|2023"}

    assert helpers.document_keys_match(open_item, evidence)


def test_unrelated_document_keys_do_not_match_without_explicit_alias():
    helpers = load_helpers()
    open_item = {"document_key": "120V1|2023"}
    evidence = {"document_key": "220FE|2023"}

    assert not helpers.document_keys_match(open_item, evidence)


def test_document_date_mismatch_rejects_non_external_numeric_alias():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [
            {
                "record_id": "open-late-22",
                "document_key": "22FE|2023",
                "document_date": "2023-12-28",
                "amount": "100.00",
            }
        ],
        [
            {
                "record_id": "po-early-22",
                "source_role": "payment_order",
                "evidence_type": "payment_order_bridge",
                "document_key": "22|2023",
                "document_date": "2023-01-13",
                "amount": "100.00",
            }
        ],
    )

    assert rows[0]["reconciliation_status"] == "unresolved"
    assert rows[0]["rule_applied"] == "unresolved"


def test_document_date_match_allows_internal_alias_support():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [
            {
                "record_id": "open-425",
                "document_key": "425FE|2023",
                "document_date": "2023-03-31",
                "amount": "100.00",
            }
        ],
        [
            {
                "record_id": "ledger-425-v1",
                "source_role": "ledger",
                "evidence_type": "internal_booking",
                "document_key": "425V1|2023",
                "document_date": "2023-03-31",
                "amount": "100.00",
            }
        ],
    )

    assert rows[0]["reconciliation_status"] == "open_supported"
    assert rows[0]["rule_applied"] == "internal_booking_open_support"


def test_grouped_open_item_splits_keep_group_support_rule():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [
            {
                "record_id": "open-425-a",
                "source_file": "open.pdf",
                "source_side": "customer",
                "expected_side": "customer",
                "document_key": "425FE|2023",
                "document_date": "2023-03-31",
                "amount": "36.00",
            },
            {
                "record_id": "open-425-b",
                "source_file": "open.pdf",
                "source_side": "customer",
                "expected_side": "customer",
                "document_key": "425FE|2023",
                "document_date": "2023-03-31",
                "amount": "64.00",
            },
        ],
        [
            {
                "record_id": "ledger-425-v1",
                "source_role": "ledger",
                "evidence_type": "internal_booking",
                "document_key": "425V1|2023",
                "document_date": "2023-03-31",
                "amount": "100.00",
            }
        ],
    )

    assert {row["rule_applied"] for row in rows} == {
        "grouped_open_amount_internal_booking_support"
    }
    assert all(
        "group_open_amount_total=100.00" in row["matched_evidence_amounts"]
        for row in rows
    )


def test_external_bank_match_does_not_use_bank_movement_date_as_invoice_date():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [
            {
                "record_id": "open-22",
                "document_key": "22FE|2023",
                "document_date": "2023-01-13",
                "amount": "100.00",
            }
        ],
        [
            {
                "record_id": "bank-22",
                "source_role": "bank_statement",
                "evidence_type": "external_bank",
                "document_key": "22|2023",
                "document_date": "2023-02-15",
                "amount": "100.00",
                "source_file": "bank.pdf",
            }
        ],
    )

    assert rows[0]["reconciliation_status"] == "closed"
    assert rows[0]["rule_applied"] == "external_bank_match"


def test_factor_operator_keywords_are_case_configuration():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "INV1|2023", "amount": "100.00"}],
        [
            {
                "record_id": "factor-1",
                "document_key": "INV1|2023",
                "amount": "100.00",
                "description": "OperatorX settlement",
            }
        ],
        {"factoring_operator_keywords": ["OperatorX"]},
    )

    assert rows[0]["reconciliation_status"] == "closed"
    assert rows[0]["evidence_level"] == "configured_strong"


def test_payment_order_alone_does_not_close_item():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "INV1|2023", "amount": "100.00"}],
        [
            {
                "record_id": "po-1",
                "evidence_type": "payment_order",
                "document_keys": "INV1|2023",
                "amount": "100.00",
            }
        ],
    )

    assert rows[0]["reconciliation_status"] == "needs_evidence"
    assert rows[0]["rule_applied"] == "payment_order_only"
    assert "estratto conto" in rows[0]["missing_evidence"]


def test_unallocated_external_bank_requires_allocation_and_beats_open_support():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "INV1|2023", "amount": "100.00"}],
        [
            {
                "record_id": "booking-1",
                "evidence_type": "internal_booking",
                "document_key": "INV1|2023",
                "amount": "100.00",
            },
            {
                "record_id": "bank-unallocated-1",
                "evidence_type": "unallocated_external_bank",
                "document_key": "INV1|2023",
                "amount": "500.00",
                "source_file": "bank.pdf",
            },
        ],
    )

    assert rows[0]["reconciliation_status"] == "needs_evidence"
    assert rows[0]["rule_applied"] == "unallocated_external_bank_requires_allocation"
    assert "allocato" in rows[0]["missing_evidence"]


def test_grouped_payment_order_closes_when_batch_total_matches_bank():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "INV1|2023", "amount": "100.00"}],
        [
            {
                "record_id": "po-1",
                "evidence_type": "payment_order",
                "document_keys": "INV1|2023",
                "amount": "100.00",
                "batch_id": "BATCH-1",
                "batch_total": "250.00",
            },
            {
                "record_id": "bank-1",
                "evidence_type": "external_bank",
                "batch_id": "BATCH-1",
                "amount": "250.00",
                "posting_date": "2023-11-15",
            },
        ],
        {"cutoff_date": "2023-12-31"},
    )

    assert rows[0]["reconciliation_status"] == "closed"
    assert rows[0]["rule_applied"] == "grouped_payment_external_match"
    assert rows[0]["matched_evidence_id"] == "bank-1"


def test_grouped_payment_order_closes_unallocated_bank_by_amount_and_value_date():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "1524FE|2023", "amount": "100.00"}],
        [
            {
                "record_id": "po-1",
                "evidence_type": "payment_order_bridge",
                "document_key": "1524|2023",
                "amount": "100.00",
                "batch_total": "250.00",
                "value_date": "2023-11-15",
            },
            {
                "record_id": "bank-1",
                "source_role": "bank_statement",
                "evidence_type": "unallocated_external_bank",
                "amount": "250.00",
                "value_date": "2023-11-15",
            },
        ],
        {"cutoff_date": "2023-12-31"},
    )

    assert rows[0]["reconciliation_status"] == "closed"
    assert rows[0]["rule_applied"] == "grouped_payment_external_match"
    assert rows[0]["matched_evidence_id"] == "bank-1"


def test_grouped_bridge_does_not_close_with_different_document_specific_bank_row():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "1629|2023", "amount": "5381.02"}],
        [
            {
                "record_id": "bridge-1629",
                "evidence_type": "factoring_bridge",
                "document_key": "1629|2023",
                "amount": "30700.74",
                "posting_date": "2023-05-19",
                "description": "INCASSATA FATTURA FACTORCO 1629",
            },
            {
                "record_id": "bank-363",
                "source_role": "bank_statement",
                "evidence_type": "external_bank",
                "document_key": "363|2023",
                "amount": "30700.74",
                "posting_date": "2023-05-19",
                "description": "FACTORCO FT. 363",
            },
        ],
        {"cutoff_date": "2023-12-31", "factoring_pro_soluto_closes_item": True},
    )

    assert rows[0]["reconciliation_status"] == "needs_evidence"
    assert rows[0]["rule_applied"] == "factoring_bridge_only"


def test_grouped_payment_order_with_mismatched_line_amount_does_not_close():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "1349FE|2023", "amount": "27459.82"}],
        [
            {
                "record_id": "po-1",
                "evidence_type": "payment_order_bridge",
                "document_key": "1349|2023",
                "amount": "843.52",
                "batch_total": "5558.37",
                "value_date": "2023-12-06",
            },
            {
                "record_id": "bank-1",
                "source_role": "bank_statement",
                "evidence_type": "unallocated_external_bank",
                "amount": "5558.37",
                "value_date": "2023-12-06",
            },
        ],
        {"cutoff_date": "2023-12-31"},
    )

    assert rows[0]["reconciliation_status"] == "needs_evidence"
    assert rows[0]["rule_applied"] == "payment_order_amount_mismatch"


def test_factoring_bridge_closes_by_default_when_tied_to_bank_statement_payment():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "1387FE|2023", "amount": "359421.75"}],
        [
            {
                "record_id": "journal-factor",
                "source_role": "journal",
                "evidence_type": "factoring_bridge",
                "document_key": "1387FE|2023",
                "amount": "359421.75",
                "posting_date": "2023-12-06",
                "description": "Cessione cred. pro-soluto FACTORCO",
            },
            {
                "record_id": "bank-factor",
                "source_role": "bank_statement",
                "evidence_type": "external_bank",
                "amount": "359421.75",
                "posting_date": "2023-12-06",
                "description": "Bonifico da factor",
            },
        ],
        {"cutoff_date": "2023-12-31"},
    )

    assert rows[0]["reconciliation_status"] == "closed"
    assert rows[0]["evidence_level"] == "strong_external"
    assert rows[0]["rule_applied"] == "grouped_payment_external_match"
    assert rows[0]["matched_evidence_id"] == "bank-factor"


def test_factoring_bridge_alone_does_not_close_item():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "1387FE|2023", "amount": "359421.75"}],
        [
            {
                "record_id": "journal-factor",
                "source_role": "journal",
                "evidence_type": "factoring_bridge",
                "document_key": "1387FE|2023",
                "amount": "35942.17",
                "description": "Cessione cred. pro-soluto FACTORCO",
            }
        ],
        {"cutoff_date": "2023-12-31"},
    )

    assert rows[0]["reconciliation_status"] == "needs_evidence"
    assert rows[0]["rule_applied"] == "factoring_bridge_only"


def test_post_cutoff_external_evidence_is_excluded():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "INV1|2023", "amount": "100.00"}],
        [
            {
                "record_id": "bank-1",
                "evidence_type": "external_bank",
                "document_key": "INV1|2023",
                "amount": "100.00",
                "posting_date": "2024-01-04",
            }
        ],
        {"cutoff_date": "2023-12-31", "post_cutoff_events_excluded": True},
    )

    assert rows[0]["reconciliation_status"] == "unresolved"
    assert rows[0]["rule_applied"] == "unresolved"


def test_post_cutoff_candidates_report_later_matching_evidence():
    helpers = load_helpers()

    candidates = helpers.post_cutoff_evidence_candidates(
        [
            {
                "record_id": "open-1",
                "source_file": "open.pdf",
                "source_page": "1",
                "source_row": "10",
                "document_key": "INV1|2023",
                "document_no": "INV1",
                "document_date": "2023-12-20",
                "amount": "100.00",
            }
        ],
        [
            {
                "record_id": "bank-1",
                "source_file": "bank.pdf",
                "source_page": "2",
                "source_row": "20",
                "source_role": "bank_statement",
                "evidence_type": "external_bank",
                "document_key": "INV1|2023",
                "amount": "100.00",
                "posting_date": "2024-01-04",
                "description": "Bonifico fattura INV1",
            }
        ],
        {"cutoff_date": "2023-12-31", "post_cutoff_events_excluded": True},
    )

    assert len(candidates) == 1
    assert candidates[0]["evidence_date"] == "2024-01-04"
    assert candidates[0]["exact_amount_match"] == "YES"
    assert "Candidato successivo al cut-off" in candidates[0]["review_use"]


def test_documented_compensation_can_close_without_bank_when_allowed():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "INV1|2023", "amount": "100.00"}],
        [
            {
                "record_id": "comp-1",
                "evidence_type": "compensation",
                "document_key": "INV1|2023",
                "amount": "100.00",
                "description": "documented compensation agreement",
            }
        ],
        {"compensation_requires_bank": False},
    )

    assert rows[0]["reconciliation_status"] == "closed"
    assert rows[0]["evidence_level"] == "documented_compensation"


def test_compensation_requires_external_support_when_configured():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "INV1|2023", "amount": "100.00"}],
        [
            {
                "record_id": "comp-1",
                "evidence_type": "compensation",
                "document_key": "INV1|2023",
                "amount": "100.00",
                "description": "documented compensation agreement",
            }
        ],
        {"compensation_requires_bank": True},
    )

    assert rows[0]["reconciliation_status"] == "needs_evidence"
    assert rows[0]["rule_applied"] == "compensation_needs_external_support"


def test_internal_accounting_only_does_not_close_item():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "INV1|2023", "amount": "100.00"}],
        [
            {
                "record_id": "journal-1",
                "evidence_type": "internal_accounting",
                "document_key": "INV1|2023",
                "amount": "100.00",
            }
        ],
    )

    assert rows[0]["reconciliation_status"] == "needs_evidence"
    assert rows[0]["rule_applied"] == "internal_accounting_only"


def test_internal_booking_supports_open_item_position():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "INV1|2023", "amount": "100.00"}],
        [
            {
                "record_id": "booking-1",
                "evidence_type": "internal_booking",
                "document_key": "INV1|2023",
                "amount": "100.00",
            }
        ],
    )

    assert rows[0]["reconciliation_status"] == "open_supported"
    assert rows[0]["rule_applied"] == "internal_booking_open_support"


def test_internal_booking_can_support_residual_open_balance_by_document_key():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [
            {
                "record_id": "open-1",
                "document_key": "INV1|2023",
                "amount": "25.00",
                "expected_side": "customer",
            }
        ],
        [
            {
                "record_id": "booking-1",
                "evidence_type": "internal_booking",
                "document_key": "INV1|2023",
                "amount": "100.00",
                "side": "customer",
            }
        ],
    )

    assert rows[0]["reconciliation_status"] == "open_supported"
    assert rows[0]["rule_applied"] == "internal_booking_open_support"


def test_internal_closure_without_external_requires_evidence_and_beats_booking():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "INV1|2023", "amount": "100.00"}],
        [
            {
                "record_id": "booking-1",
                "evidence_type": "internal_booking",
                "document_key": "INV1|2023",
                "amount": "100.00",
            },
            {
                "record_id": "closure-1",
                "evidence_type": "internal_closure",
                "document_key": "INV1|2023",
                "amount": "100.00",
            },
        ],
    )

    assert rows[0]["reconciliation_status"] == "needs_evidence"
    assert rows[0]["rule_applied"] == "internal_closure_without_external"
    assert rows[0]["matched_evidence_id"] == "closure-1"


def test_internal_closure_with_matching_side_requires_evidence():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [
            {
                "record_id": "open-1",
                "document_key": "INV1|2023",
                "amount": "100.00",
                "expected_side": "customer",
            }
        ],
        [
            {
                "record_id": "closure-1",
                "evidence_type": "internal_closure",
                "document_key": "INV1|2023",
                "amount": "100.00",
                "side": "customer",
            },
        ],
    )

    assert rows[0]["reconciliation_status"] == "needs_evidence"
    assert rows[0]["rule_applied"] == "internal_closure_without_external"


def test_external_evidence_beats_internal_closure():
    helpers = load_helpers()
    rows = helpers.reconcile_open_items(
        [{"record_id": "open-1", "document_key": "INV1|2023", "amount": "100.00"}],
        [
            {
                "record_id": "closure-1",
                "evidence_type": "internal_closure",
                "document_key": "INV1|2023",
                "amount": "100.00",
            },
            {
                "record_id": "bank-1",
                "evidence_type": "external_bank",
                "document_key": "INV1|2023",
                "amount": "100.00",
                "source_file": "bank.pdf",
            },
        ],
    )

    assert rows[0]["reconciliation_status"] == "closed"
    assert rows[0]["matched_evidence_id"] == "bank-1"
    assert rows[0]["rule_applied"] == "external_bank_match"


def test_reconciliation_checks_pass_for_complete_output():
    helpers = load_helpers()
    open_items = [
        {"record_id": "open-1", "document_key": "INV1|2023", "amount": "100.00"}
    ]
    rows = helpers.reconcile_open_items(
        open_items,
        [
            {
                "record_id": "bank-1",
                "evidence_type": "external_bank",
                "document_key": "INV1|2023",
                "amount": "100.00",
                "source_file": "bank.pdf",
                "source_page": "1",
            }
        ],
    )

    checks = helpers.reconciliation_checks(open_items, rows)

    assert helpers.checks_pass(checks)


def test_reconciliation_checks_catch_closed_rows_without_reference():
    helpers = load_helpers()
    open_items = [{"record_id": "open-1"}]
    rows = [
        {
            "record_id": "open-1",
            "reconciliation_status": "closed",
            "rule_applied": "direct_external_or_documented",
            "matched_evidence_reference": "",
        }
    ]

    checks = helpers.reconciliation_checks(open_items, rows)

    assert not helpers.checks_pass(checks)
    assert any(
        check["check"] == "closed_rows_have_evidence_reference"
        and check["status"] == "FAIL"
        for check in checks
    )


def test_codex_review_sample_includes_high_value_and_risk_rows():
    helpers = load_helpers()
    rows = [
        {
            "record_id": "small",
            "amount": "10.00",
            "rule_applied": "direct_external_or_documented",
        },
        {
            "record_id": "large",
            "amount": "999999.00",
            "rule_applied": "direct_external_or_documented",
        },
        {
            "record_id": "bridge",
            "amount": "20.00",
            "rule_applied": "payment_order_only",
        },
    ]

    sample = helpers.codex_review_sample(rows, sample_size=2, high_value_count=1)
    ids = {row["record_id"] for row in sample}

    assert {"large", "bridge"}.issubset(ids)


def test_codex_review_packet_covers_required_rows_and_random_sample():
    helpers = load_helpers()
    rows = [
        {
            "record_id": "bank-closed",
            "amount": "100.00",
            "reconciliation_status": "closed",
            "rule_applied": "external_bank_match",
            "matched_evidence_type": "external_bank",
        },
        {
            "record_id": "factor-closed",
            "amount": "200.00",
            "reconciliation_status": "closed",
            "rule_applied": "factoring_with_bank_or_external_support",
            "matched_evidence_type": "external_factoring",
        },
        {
            "record_id": "comp-closed",
            "amount": "300.00",
            "reconciliation_status": "closed",
            "rule_applied": "documented_compensation",
            "matched_evidence_type": "compensation",
        },
        {
            "record_id": "largest-open",
            "amount": "9999.00",
            "reconciliation_status": "needs_evidence",
            "rule_applied": "internal_closure_without_external",
        },
        {
            "record_id": "challenged",
            "document_key": "INV-CHALLENGED|2023",
            "amount": "10.00",
            "reconciliation_status": "unresolved",
            "rule_applied": "unresolved",
        },
    ]
    rows.extend(
        {
            "record_id": f"random-{idx}",
            "document_key": f"RANDOM-{idx}|2023",
            "amount": str(idx),
            "reconciliation_status": "unresolved",
            "rule_applied": "unresolved",
        }
        for idx in range(10)
    )

    packet = helpers.build_codex_review_packet(
        rows,
        high_value_count=2,
        random_count=3,
        challenged_rows=["INV-CHALLENGED|2023"],
    )
    ids = {row["record_id"] for row in packet}
    random_count = sum(
        "stable_random" in row["review_selection_reason"] for row in packet
    )

    assert {
        "largest-open",
        "comp-closed",
        "bank-closed",
        "factor-closed",
        "challenged",
    }.issubset(ids)
    assert random_count >= 3
    assert all(row["review_status"] == "PENDING" for row in packet)
    assert all(row["review_instruction"] for row in packet)
    assert helpers.checks_pass(
        helpers.codex_review_checks(
            rows,
            packet,
            high_value_count=2,
            random_count=3,
            challenged_rows=["INV-CHALLENGED|2023"],
        )
    )


def test_codex_review_checks_fail_on_completed_review_pending_or_fail():
    helpers = load_helpers()
    rows = [
        {
            "record_id": "open-1",
            "amount": "100.00",
            "reconciliation_status": "unresolved",
            "rule_applied": "unresolved",
        }
    ]
    packet = helpers.build_codex_review_packet(rows, high_value_count=1, random_count=0)

    pending_checks = helpers.codex_review_checks(
        rows,
        packet,
        require_completed_review=True,
        high_value_count=1,
        random_count=0,
    )
    assert any(
        check["check"] == "codex_review_completed" and check["status"] == "FAIL"
        for check in pending_checks
    )

    failed_packet = [dict(packet[0], review_status="FAIL")]
    failed_checks = helpers.codex_review_checks(
        rows,
        failed_packet,
        high_value_count=1,
        random_count=0,
    )
    assert any(
        check["check"] == "codex_review_no_failed_rows" and check["status"] == "FAIL"
        for check in failed_checks
    )


def test_additional_deterministic_analyses_explain_open_items():
    helpers = load_helpers()
    open_items = [
        {
            "record_id": "open-1",
            "source_role": "open_items",
            "document_key": "INV1|2023",
            "document_no": "INV1",
            "document_date": "2023-01-15",
            "amount": "1000.00",
        },
        {
            "record_id": "open-2",
            "source_role": "open_items",
            "document_key": "INV2|2023",
            "document_no": "INV2",
            "document_date": "2023-12-20",
            "amount": "200.00",
        },
    ]
    evidence_rows = [
        {
            "record_id": "ledger-1",
            "source_role": "ledger",
            "evidence_type": "internal_closure",
            "document_key": "INV1|2023",
            "posting_date": "2023-12-15",
            "amount": "-1000.00",
            "description": "storno giroconto fattura INV1",
        },
        {
            "record_id": "bank-1",
            "source_role": "bank_statement",
            "evidence_type": "external_bank",
            "document_key": "INV2|2023",
            "posting_date": "2023-12-29",
            "amount": "200.00",
        },
    ]
    reconciliation_rows = helpers.reconcile_open_items(
        open_items,
        evidence_rows,
        {"cutoff_date": "2023-12-31"},
    )

    aging = helpers.open_item_aging_summary(
        reconciliation_rows,
        {"cutoff_date": "2023-12-31"},
    )
    signals = helpers.review_signal_rows(
        reconciliation_rows,
        {"cutoff_date": "2023-12-31", "review_high_value_threshold": "500"},
    )
    concentration = helpers.evidence_concentration_summary(reconciliation_rows)
    source_map = helpers.document_source_map(
        open_items, evidence_rows, reconciliation_rows
    )
    reversals = helpers.reversal_or_compensation_candidates(
        reconciliation_rows,
        evidence_rows,
        {"cutoff_date": "2023-12-31"},
    )
    cutoff_rows = helpers.cutoff_window_movements(
        open_items,
        evidence_rows,
        {"cutoff_date": "2023-12-31", "cutoff_window_days": "20"},
    )

    assert any(row["aging_bucket"] == "181-365" for row in aging)
    assert signals[0]["record_id"] == "open-1"
    assert any(row["support_bucket"] == "bank" for row in concentration)
    assert any(
        row["document_key"] == "INV1|2023" and row["ledger_rows"] == 1
        for row in source_map
    )
    assert reversals[0]["open_record_id"] == "open-1"
    assert "opposite_sign_amount" in reversals[0]["candidate_reasons"]
    assert {row["record_id"] for row in cutoff_rows} >= {"ledger-1", "bank-1", "open-2"}
