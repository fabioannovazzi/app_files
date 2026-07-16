import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

import pytest

# Ensure the 'src' package root is importable for journal_ingest
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from journal_ingest.core import ParserConfidenceError
from journal_ingest.core.parser import BaseJournalParser
from journal_ingest.router.router import Router


class _FixedScoreParser(BaseJournalParser):
    """Minimal parser that returns a predetermined probe score and records inputs."""

    def __init__(self, score: float) -> None:
        self._score = score
        self.probed_with: list[tuple[bytes, Mapping[str, Any] | None]] = []

    def probe(self, file_bytes: bytes, meta: Mapping[str, Any] | None = None) -> float:  # type: ignore[override]
        self.probed_with.append((file_bytes, meta))
        return self._score

    def parse(self, file_bytes: bytes, meta: Mapping[str, Any] | None = None) -> Iterable[dict[str, Any]]:  # type: ignore[override]
        yield {"len": len(file_bytes), "has_meta": meta is not None}


@pytest.mark.parametrize(
    "scores, threshold, expected_index",
    [
        # First parser equals threshold – should be selected
        ([0.60, 0.90], 0.60, 0),
        # First parser above threshold – should be selected (even if later also qualifies)
        ([0.70, 0.80], 0.60, 0),
        # First below, second above – second should be selected
        ([0.10, 0.65], 0.60, 1),
    ],
)
def test_route_selects_first_parser_meeting_threshold_and_passes_args(scores, threshold, expected_index):
    file_bytes = b"dummy-pdf-bytes"
    meta = {"source": "unit-test"}
    parsers = [_FixedScoreParser(s) for s in scores]
    router = Router(parsers, threshold=threshold)

    selected = router.route(file_bytes, meta=meta)

    # Asserts: correct parser instance is returned
    assert selected is parsers[expected_index]
    # And probe received the exact arguments
    assert parsers[expected_index].probed_with[-1] == (file_bytes, meta)


def test_route_raises_when_all_below_threshold_and_invokes_agent(monkeypatch):
    parsers = [_FixedScoreParser(0.10), _FixedScoreParser(0.59)]
    router_called = {"count": 0}

    def failing_agent(file_bytes: bytes, meta: Mapping[str, Any] | None) -> None:
        router_called["count"] += 1
        raise RuntimeError("agent error for test")

    router = Router(parsers, threshold=0.60, agent=failing_agent)

    with pytest.raises(ParserConfidenceError):
        router.route(b"bytes", meta=None)

    # Agent should be invoked exactly once when no parser meets threshold
    assert router_called["count"] == 1

