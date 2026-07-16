import pytest

# Prefer canonical import; fall back to src-layout if needed
try:  # pragma: no cover - import resolution
    from bank_ingestion.check_statements.filters import (
        is_header_footer,
        is_summary_or_notice,
        is_total_or_balance_only,
    )
except ModuleNotFoundError:  # pragma: no cover
    from src.bank_ingestion.check_statements.filters import (  # type: ignore
        is_header_footer,
        is_summary_or_notice,
        is_total_or_balance_only,
    )


@pytest.mark.parametrize(
    "lang,text",
    [
        ("en", "Account SUMMARY and fees"),  # case-insensitive match
        ("it", "Riepilogo movimenti"),
        ("de", "Gebühren Mitteilung"),  # includes accented keyword
        ("fr", "Frais de service"),
    ],
)
def test_is_summary_or_notice_detects_keywords(lang: str, text: str) -> None:
    # Act
    result = is_summary_or_notice(text, lang)

    # Assert
    assert result is True


def test_is_summary_or_notice_unknown_language_returns_false() -> None:
    # Act
    result = is_summary_or_notice("summary of charges", "es")

    # Assert
    assert result is False


@pytest.mark.parametrize(
    "y_pos,page_height,expected",
    [
        (69.999, 1000.0, True),   # inside header band (< 7%)
        (70.0, 1000.0, False),     # exactly at band boundary -> not header/footer
        (930.0, 1000.0, False),    # exactly at lower boundary of footer band
        (930.001, 1000.0, True),   # inside footer band (> 93%)
    ],
)
def test_is_header_footer_band_boundaries(y_pos: float, page_height: float, expected: bool) -> None:
    # Act
    result = is_header_footer(y_pos, page_height)

    # Assert
    assert result is expected


@pytest.mark.parametrize(
    "text",
    [
        "Total fees",  # starts with keyword
        "  SALDO finale",  # leading spaces + case-insensitive
        "Balance 2023-12-01",  # date present but still startswith keyword
        "totale importi",  # Italian variant
    ],
)
def test_is_total_or_balance_only_matches_startswith_keywords(text: str) -> None:
    # Act
    result = is_total_or_balance_only(text)

    # Assert
    assert result is True


def test_is_total_or_balance_only_false_when_keyword_not_at_start() -> None:
    # Act
    result = is_total_or_balance_only("Account total for period")

    # Assert
    assert result is False
