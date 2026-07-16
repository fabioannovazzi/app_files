import sys
from datetime import date
from pathlib import Path

import pytest

# Ensure 'src' is on sys.path so absolute imports like 'journal_ingest.*' resolve
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

def _ensure_minimal_journal_ingest_modules() -> None:
    """Provide minimal stubs if an external 'journal_ingest' shadows the repo.

    The tested functions don't use these pieces, but the module import requires
    them to exist. When the real package is importable from 'src', this is a no-op.
    """

    try:
        # If the real package is available and has the expected symbols, keep it
        from journal_ingest.config import get_recipe as _gr  # type: ignore
        from journal_ingest.core import ParserConfidenceError, ValidationError  # type: ignore
        from journal_ingest.router import Router  # type: ignore
        from journal_ingest.strategies import (  # type: ignore
            JournalStrategyTableArea,
            JournalStrategyTextLayout,
            TablePDFParser,
            TextPDFParser,
        )
        return
    except Exception:
        pass

    import types

    ji = types.ModuleType("journal_ingest")
    # Mark as a package so submodule imports work
    ji.__path__ = []  # type: ignore[attr-defined]

    cfg = types.ModuleType("journal_ingest.config")

    def get_recipe(_name: str):  # minimal stub
        return {"name": _name}

    cfg.get_recipe = get_recipe  # type: ignore[attr-defined]

    core = types.ModuleType("journal_ingest.core")

    class ParserConfidenceError(Exception):
        pass

    class ValidationError(Exception):
        pass

    core.ParserConfidenceError = ParserConfidenceError  # type: ignore[attr-defined]
    core.ValidationError = ValidationError  # type: ignore[attr-defined]

    router = types.ModuleType("journal_ingest.router")

    class Router:  # minimal stub
        def __init__(self, *_, **__):
            pass

        def route(self, *_: object, **__: object):
            raise ParserConfidenceError("stub")

    router.Router = Router  # type: ignore[attr-defined]

    strategies = types.ModuleType("journal_ingest.strategies")

    class _Dummy:
        def __init__(self, *_, **__):
            pass

        def probe(self, *_, **__):
            return 0.0

    strategies.JournalStrategyTableArea = _Dummy  # type: ignore[attr-defined]
    strategies.JournalStrategyTextLayout = _Dummy  # type: ignore[attr-defined]
    strategies.TablePDFParser = _Dummy  # type: ignore[attr-defined]
    strategies.TextPDFParser = _Dummy  # type: ignore[attr-defined]

    sys.modules["journal_ingest"] = ji
    sys.modules["journal_ingest.config"] = cfg
    sys.modules["journal_ingest.core"] = core
    sys.modules["journal_ingest.router"] = router
    sys.modules["journal_ingest.strategies"] = strategies

def _import_targets():
    # Import lazily to avoid module-level import issues during collection
    _ensure_minimal_journal_ingest_modules()
    from modules.process_pdf_journal import logic

    return logic.parse_amount, logic.parse_date_str, logic.parse_number_token


@pytest.mark.parametrize(
    "token, expected",
    [
        ("1,234.56", 1234.56),  # US style: comma thousands, dot decimal
        ("1.234,56", 1234.56),  # EU style: dot thousands, comma decimal
        (".5", 0.5),            # leading decimal dot
        (",5", 0.5),            # leading decimal comma
        ("1\u00a0234,56", 1234.56),  # NBSP thousands separator
    ],
)
def test_parse_number_token_detects_decimal_and_thousands(token: str, expected: float):
    # Act
    parse_amount, parse_date_str, parse_number_token = _import_targets()
    result = parse_number_token(token)

    # Assert
    assert isinstance(result, float)
    assert result == pytest.approx(expected, rel=0, abs=1e-12)


@pytest.mark.parametrize(
    "token",
    ["", "—", "no digits", "-"],
)
def test_parse_number_token_invalid_returns_none(token: str):
    # Act
    parse_amount, parse_date_str, parse_number_token = _import_targets()
    result = parse_number_token(token)

    # Assert
    assert result is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2024-08-27", date(2024, 8, 27)),  # %Y-%m-%d
        ("27/08/2024", date(2024, 8, 27)),  # %d/%m/%Y
        ("08/27/2024", date(2024, 8, 27)),  # %m/%d/%Y
        ("27.08.2024", date(2024, 8, 27)),  # %d.%m.%Y
        ("2024/08/27", date(2024, 8, 27)),  # %Y/%m/%d
        (" 2024-08-27 ", date(2024, 8, 27)),  # leading/trailing whitespace
    ],
)
def test_parse_date_str_supports_multiple_formats(text: str, expected: date):
    # Act
    parse_amount, parse_date_str, parse_number_token = _import_targets()
    result = parse_date_str(text)

    # Assert
    assert result == expected


@pytest.mark.parametrize("text", ["not a date", "31/02/2024", "", "2024-13-01"])
def test_parse_date_str_invalid_returns_none(text: str):
    # Act
    parse_amount, parse_date_str, parse_number_token = _import_targets()
    result = parse_date_str(text)

    # Assert
    assert result is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1.234,56", 1234.56),
        ("-1.234,56", -1234.56),
    ],
)
def test_parse_amount_handles_italian_formatting(text: str, expected: float):
    # Act
    parse_amount, parse_date_str, parse_number_token = _import_targets()
    result = parse_amount(text)

    # Assert
    assert isinstance(result, float)
    assert result == pytest.approx(expected, rel=0, abs=1e-12)


@pytest.mark.parametrize("text", ["", "-", "—", "abc"])
def test_parse_amount_blanks_and_invalid_return_none(text: str):
    # Act
    parse_amount, parse_date_str, parse_number_token = _import_targets()
    result = parse_amount(text)

    # Assert
    assert result is None
