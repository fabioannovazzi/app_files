import importlib.util
from pathlib import Path
import pytest
from datetime import date
from decimal import Decimal, InvalidOperation

# Import the target module directly from file to avoid package side-effects
_MODULE_PATH = Path(__file__).resolve().parents[2] / "src" / "statements" / "locale_utils.py"
_SPEC = importlib.util.spec_from_file_location("statements_locale_utils", _MODULE_PATH)
assert _SPEC and _SPEC.loader, "Failed to load statements.locale_utils module spec"
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)  # type: ignore[assignment]


def test_detect_language_english_seeded_returns_en_with_confidence() -> None:
    # Arrange: make langdetect deterministic
    from langdetect import DetectorFactory

    DetectorFactory.seed = 0
    text = (
        "This is a simple sentence written in English about bank statements "
        "and account summaries to help language detection be confident."
    )

    # Act
    lang, conf = mod.detect_language(text)

    # Assert
    assert lang == "en"
    assert isinstance(conf, float) and 0.0 < conf <= 1.0


def test_detect_language_fallback_on_langdetect_exception(monkeypatch) -> None:
    # Arrange: simulate langdetect failure -> function should fallback to ('en', 0.0)
    from langdetect.lang_detect_exception import LangDetectException

    def _boom(_text: str):  # noqa: ANN001
        raise LangDetectException(0, "failed")

    monkeypatch.setattr(mod, "detect_langs", _boom)

    # Act
    lang, conf = mod.detect_language("irrelevant")

    # Assert
    assert (lang, conf) == ("en", 0.0)


@pytest.mark.parametrize(
    "s, locale, expected",
    [
        ("1,234.56", "en", Decimal("1234.56")),
        ("1.234,56", "fr", Decimal("1234.56")),
        ("1 234,56", "fr", Decimal("1234.56")),
        ("(1,234.56)", "en", Decimal("-1234.56")),
        ("1,234.56-", "en", Decimal("-1234.56")),
        ("-1,234.56", "en", Decimal("-1234.56")),
    ],
)
def test_parse_number_handles_locales_and_negatives(s: str, locale: str, expected: Decimal) -> None:
    # Act
    result = mod.parse_number(s, locale)

    # Assert
    assert isinstance(result, Decimal)
    assert result == expected


def test_parse_number_invalid_raises() -> None:
    with pytest.raises(InvalidOperation):
        mod.parse_number("not a number", "en")


@pytest.mark.parametrize(
    "value, locale, expected",
    [
        ("31/12/2023", "en", date(2023, 12, 31)),
        ("15 marzo 2023", "it", date(2023, 3, 15)),
        ("01 mars 2023", "fr", date(2023, 3, 1)),
        ("2023-08-15", "en", date(2023, 8, 15)),
    ],
)
def test_parse_date_parses_common_formats_and_locale_months(value: str, locale: str, expected: date) -> None:
    # Act
    result = mod.parse_date(value, locale)

    # Assert
    assert result == expected


def test_parse_date_invalid_raises() -> None:
    with pytest.raises(ValueError):
        mod.parse_date("not a date", "en")
