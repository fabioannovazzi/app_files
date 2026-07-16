import pytest

from src.parsers.extractors import (
    extract_beneficiary,
    extract_references,
    normalise_name,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  Café du Monde, Inc.  ", "cafedu monde inc"),
        ("FRA-123_45", "fra12345"),  # punctuation removed, digits kept
        ("   ", ""),  # boundary: collapses/strips whitespace to empty
    ],
)
def test_normalise_name_behavior(raw: str, expected: str) -> None:
    # Act
    result = normalise_name(raw)

    # Assert
    assert result == expected
    # Idempotence: normalising again yields the same
    assert normalise_name(result) == result


def test_extract_references_multiple_and_dedup() -> None:
    # Arrange
    text = "Num. Bon. 12345; CRO UIC: 9Z9Z; Invoice INV001; cro: 9Z9Z; REF: X1"

    # Act
    refs = extract_references(text)

    # Assert: preserves first occurrence order and removes duplicates
    assert refs == ["12345", "9Z9Z", "INV001", "X1"]


def test_extract_references_handles_accents_and_languages() -> None:
    # Arrange: "Fatturà" with accent should match Italian invoice pattern
    text = "Pagamento fatturà n. ABC123"

    # Act
    refs = extract_references(text)

    # Assert
    assert refs == ["ABC123"]


def test_extract_references_none_found_returns_empty() -> None:
    # Act
    refs = extract_references("No identifiers present here.")

    # Assert
    assert refs == []


def test_extract_references_bon_sepa_and_rif_variants() -> None:
    # Arrange: typical Italian statement fragments with both Bon.Sepa and RIF.
    text = (
        "DISPOSIZIONE A FAVORE DI EXAMPLE SUPPLIER SRL "
        "Num.Bon.Sepa 240931000123672 – RIF. 24093/0008035071"
    )

    # Act
    refs = extract_references(text)

    # Assert: both identifiers captured
    assert any(r.startswith("240931000123672") for r in refs)
    assert any(r.startswith("24093/0008035071") for r in refs)


def test_extract_beneficiary_golden_italian_with_accents() -> None:
    # Arrange
    text = "Bonifico a favore di José Pérez; CRO 1234"

    # Act
    ben = extract_beneficiary(text)

    # Assert: accents removed, punctuation stripped, lowercased
    assert ben == "jose perez"


def test_extract_beneficiary_german_empfaenger_with_accents() -> None:
    # Arrange: "Empfänger" becomes "Empfanger" after accent stripping
    text = "Empfänger: Müller & Söhne; Betrag 10€"

    # Act
    ben = extract_beneficiary(text)

    # Assert: ampersand treated as punctuation and removed
    assert ben == "muller sohne"


def test_extract_beneficiary_not_found_returns_none() -> None:
    # Act
    ben = extract_beneficiary("Miscellaneous charge for services rendered")

    # Assert
    assert ben is None


def test_extract_references_handles_n_prefix_with_short_leading_segment() -> None:
    # Arrange: typical ledger style with N.<seg>/<invoice>/<line>
    text = "N.23/633546155/001 del 15122023 EXAMPLE SUPPLIER GMBH + CO KG"

    # Act
    refs = extract_references(text)

    # Assert: capture full token starting with the short leading segment
    assert any(r.startswith("23/633546155/001") for r in refs)


def test_extract_references_fe_shorthand_yields_variants() -> None:
    # Arrange
    text = "N.FE_3079_23 del 07122023 COMODITAS SNC"

    # Act
    refs = extract_references(text)

    # Assert: include both compact and expanded year variants
    assert "3079/23" in refs or "3079/2023" in refs


def test_extract_references_does_not_capture_bare_day_numbers() -> None:
    # Arrange
    text = "N.2024/0/7 del 10012024 STUDIO CI.DI.PI. SNC DI CO"

    # Act
    refs = extract_references(text)

    # Assert: should capture the composite N. token, not stray day values like '15' or '07'
    assert any(r.startswith("2024/0/7") for r in refs)
    assert "15" not in refs and "07" not in refs


def test_extract_beneficiary_after_invoice_token_trailing_entity() -> None:
    # Arrange
    text = "N.23/633546155/001 del 15122023 EXAMPLE SUPPLIER GMBH + CO KG"

    # Act
    ben = extract_beneficiary(text)

    # Assert
    assert ben == "example supplier gmbh co kg"


def test_normalise_name_repairs_odd_split() -> None:
    # Arrange
    raw = "CONSORZIO STABI LE"

    # Act
    fixed = normalise_name(raw)

    # Assert
    assert fixed == "consorzio stabile"
