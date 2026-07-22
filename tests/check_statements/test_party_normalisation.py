from __future__ import annotations

import pytest

from src.check_statements.party_normalisation import _clean_party_for_evidence


@pytest.mark.parametrize("language", ("es", "es-ES"))
def test_clean_party_for_evidence_removes_spanish_payment_and_bank_noise(
    language: str,
) -> None:
    narrative = "TRANSFERENCIA BANCO SANTANDER ACME SL " "COMISIÓN DE SERVICIO 1,20 EUR"

    result = _clean_party_for_evidence(narrative, language)

    assert "acme" in result.split()
    assert "transferencia" not in result
    assert "banco" not in result
    assert "santander" not in result
    assert "comision" not in result
