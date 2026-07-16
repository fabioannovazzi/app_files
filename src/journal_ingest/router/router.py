from __future__ import annotations

import logging
import os
from typing import Any, Mapping, Sequence

from journal_ingest.core import BaseJournalParser, ParserConfidenceError


class Router:
    """Select the first parser above the confidence threshold."""

    def __init__(
        self,
        parsers: Sequence[BaseJournalParser],
        threshold: float = 0.6,
        agent: Any | None = None,
    ) -> None:
        self.parsers = list(parsers)
        self.threshold = threshold
        self.agent = agent

    def route(
        self, file_bytes: bytes, meta: Mapping[str, Any] | None = None
    ) -> BaseJournalParser:
        debug = os.getenv("DEBUG_JOURNAL_PARSER", "").lower() == "true"
        best_score = 0.0
        best_parser: BaseJournalParser | None = None
        logger = logging.getLogger(__name__)
        for parser in self.parsers:
            score = parser.probe(file_bytes, meta)
            if debug:
                logger.info("strategy %s scored %.2f", parser.__class__.__name__, score)
            if score >= self.threshold:
                if debug:
                    logger.info(
                        "selected %s with score %.2f",
                        parser.__class__.__name__,
                        score,
                    )
                return parser
            if score > best_score:
                best_score = score
                best_parser = parser
        if self.agent is not None and best_score < self.threshold:
            try:  # pragma: no cover - external agent may fail
                self.agent(file_bytes, meta)
            except Exception as e:  # noqa: BLE001  # nosec B110
                logging.exception(e)
                if debug:
                    logger.info("agent invocation failed", exc_info=True)
        if debug and best_parser is not None:
            logger.info(
                "best strategy %s scored %.2f below threshold %.2f",
                best_parser.__class__.__name__,
                best_score,
                self.threshold,
            )
        raise ParserConfidenceError(
            f"No parser scored above threshold {self.threshold}"
        )
