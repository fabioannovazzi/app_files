import sys
from pathlib import Path

import pytest

# Ensure the 'src' package root is importable for journal_ingest
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from journal_ingest.core.parser import BaseJournalParser


class _SimpleParser(BaseJournalParser):
    """Minimal concrete parser used to validate BaseJournalParser contracts."""

    def probe(self, file_bytes: bytes, meta=None) -> float:  # type: ignore[override]
        # Return 1.0 when a sentinel appears, else 0.0
        return 1.0 if b"ok" in file_bytes else 0.0

    def parse(self, file_bytes: bytes, meta=None):  # type: ignore[override]
        # Yield a simple, deterministic dictionary per input
        text = file_bytes.decode("utf-8", errors="ignore")
        yield {"line": text, "has_meta": meta is not None}


def test_base_class_is_abstract():
    # Cannot instantiate the abstract base without implementing required methods
    with pytest.raises(TypeError):
        BaseJournalParser()  # type: ignore[abstract]


@pytest.mark.parametrize(
    "payload, expected",
    [
        (b"contains ok marker", 1.0),
        (b"no match here", 0.0),
    ],
)
def test_probe_returns_float_within_bounds_and_expected_value(payload: bytes, expected: float):
    parser = _SimpleParser()
    score = parser.probe(payload, meta={"hint": "x"})
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
    assert score == expected


@pytest.mark.parametrize(
    "meta, expected_flag",
    [
        (None, False),
        ({}, True),
    ],
)
def test_parse_yields_iterable_of_dicts_and_respects_optional_meta(meta, expected_flag):
    parser = _SimpleParser()
    rows = list(parser.parse(b"hello", meta=meta))
    assert rows == [{"line": "hello", "has_meta": expected_flag}]
