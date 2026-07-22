from __future__ import annotations

from statements.header_map import map_headers
from statements.page_classifier import PageClassifier
from statements.row_filters import filter_rows, looks_like_summary_row


def test_page_classifier_recognizes_spanish_summary_page() -> None:
    page_text = "\n".join(
        (
            "Resumen mensual",
            "Intereses 12,30 EUR",
            "Comisiones 4,50 EUR",
            "Impuestos 1,20 EUR",
        )
    )

    label, confidence, details = PageClassifier().classify(page_text, lang_hint="es")

    assert label == "summary"
    assert confidence == 0.9
    assert details["summary_cues"] >= 2


def test_page_classifier_recognizes_spanish_transaction_header() -> None:
    page_text = "Fecha Descripción Importe Saldo"

    label, _confidence, details = PageClassifier().classify(page_text, lang_hint="es")

    assert label == "transaction"
    assert details["header_cues"] is True


def test_looks_like_summary_row_recognizes_spanish_prefix() -> None:
    result = looks_like_summary_row("Resumen de comisiones 18,40 EUR", lang="es")

    assert result is True


def test_filter_rows_drops_spanish_summary_and_keeps_transaction() -> None:
    rows = [
        "Resumen de comisiones 18,40 EUR",
        "12/03/2025 Transferencia recibida 120,00 EUR",
    ]

    result = filter_rows(rows, lang_hint="es")

    assert result == ["12/03/2025 Transferencia recibida 120,00 EUR"]


def test_map_headers_recognizes_complete_spanish_statement_header() -> None:
    headers = [
        "Fecha de operación",
        "Fecha valor",
        "Descripción de la operación",
        "Importe",
        "Moneda",
        "Cargo",
        "Abono",
        "Saldo",
        "Número de referencia",
    ]

    result = map_headers(headers, lang="es")

    assert result == {
        "booking_date": 0,
        "value_date": 1,
        "description": 2,
        "amount": 3,
        "currency": 4,
        "debit": 5,
        "credit": 6,
        "balance": 7,
        "reference": 8,
    }
