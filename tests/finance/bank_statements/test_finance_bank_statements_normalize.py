import logging
from datetime import date

import pytest

from src.finance.bank_statements.normalize import (
    detect_language,
    detect_number_format,
    parse_date,
)


def test_detect_language_with_english_keywords_returns_en() -> None:
    text = "Date Debit Credit Description Balance"

    result = detect_language(text)

    assert result == "en"


def test_detect_language_with_spanish_keywords_returns_es() -> None:
    text = "Fecha valor Cargo Abono Concepto Moneda"

    result = detect_language(text)

    assert result == "es"


def test_detect_language_uses_langdetect_when_no_keywords(monkeypatch):
    # Arrange: ensure there are no header keywords and stub langdetect
    monkeypatch.setattr(
        "src.finance.bank_statements.normalize.detect", lambda s: "de", raising=False
    )
    text = "hello world this is plain text"

    # Act
    lang = detect_language(text)

    # Assert
    assert lang == "de"


def test_detect_language_falls_back_to_en_on_langdetect_error(monkeypatch):
    # Arrange: no keywords and langdetect raises -> fallback to 'en'
    def _boom(_: str) -> str:  # type: ignore[return-type]
        raise RuntimeError("langdetect failed")

    monkeypatch.setattr(
        "src.finance.bank_statements.normalize.detect", _boom, raising=False
    )

    # Act
    lang = detect_language("just some random words with no headers")

    # Assert
    assert lang == "en"


@pytest.mark.parametrize(
    "value, lang, expected",
    [
        ("01/02/2023", "en", date(2023, 1, 2)),  # month/day for non-dayfirst
        ("01/02/2023", "fr", date(2023, 2, 1)),  # day/month for dayfirst languages
    ],
)
def test_parse_date_respects_dayfirst_hint(
    value: str, lang: str, expected: date
) -> None:
    # Act
    result = parse_date(value, lang)

    # Assert
    assert result == expected


def test_parse_date_fallback_handles_two_digit_year_and_dayfirst(monkeypatch):
    # Arrange: force fallback path by making dateutil.parse raise
    def _raise(*_, **__):
        raise ValueError("force fallback")

    monkeypatch.setattr(
        "src.finance.bank_statements.normalize.dateutil_parse", _raise, raising=False
    )

    # Act
    result = parse_date("1-2-23", "it")  # dayfirst -> 1 Feb 2023

    # Assert
    assert result == date(2023, 2, 1)


def test_parse_date_returns_none_for_unparsable_input():
    # Act
    result = parse_date("not a date", "en")

    # Assert
    assert result is None


def test_parse_date_invalid_string_logs_no_error(caplog):
    """Invalid dates should not log at ERROR level."""
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ValueError):
            parse_date("still not a date", "en")
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


@pytest.mark.parametrize(
    "samples, expected",
    [
        (["1.234,56"], (",", ".")),  # comma decimal, dot thousand
        (["1,234.56"], (".", ",")),  # dot decimal, comma thousand
        (["1234,56"], (",", ".")),  # only comma present => comma decimal
        (["1.234.567"], (".", ",")),  # multiple dots => dot thousand
    ],
)
def test_detect_number_format_infers_separators(samples, expected):
    # Act
    decimal_sep, thousand_sep = detect_number_format(samples)

    # Assert
    assert (decimal_sep, thousand_sep) == expected
