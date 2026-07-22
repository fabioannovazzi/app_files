from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.check_statements.classify import _lex_for, classify_op, is_tax_ledger_entry


@pytest.mark.parametrize(
    ("description", "expected_operation"),
    (
        ("Pago de impuestos a la AEAT", "F24"),
        ("Adeudo domiciliado de electricidad", "SDD"),
        ("Transferencia bancaria recibida", "BONIFICO"),
        ("Retirada de efectivo en cajero automático", "ATM"),
        ("Pago con tarjeta VISA", "CARD"),
        ("Comisión de mantenimiento de cuenta", "FEE"),
        ("Remesa de recibos", "RIBA"),
    ),
)
def test_classify_op_uses_spanish_lexicon(
    description: str, expected_operation: str
) -> None:
    result = classify_op(description, lang="es")

    assert result == expected_operation


def test_classify_op_accepts_regional_spanish_language_code() -> None:
    result = classify_op("Ingreso de efectivo en cajero", lang="es-ES")

    assert result == "ATM"


def test_spanish_lexicon_contains_payroll_terms() -> None:
    result = _lex_for("es")

    assert "NOMINA" in result["payroll_tokens"]


def test_is_tax_ledger_entry_uses_spanish_language_metadata() -> None:
    transaction = SimpleNamespace(
        description="Pago trimestral",
        metadata={"language": "es", "account_desc": "Retenciones e impuestos"},
    )

    result = is_tax_ledger_entry(transaction)

    assert result is True
