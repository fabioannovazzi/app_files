"""Store Clara follow-up questions in a case workspace."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from advisor_case_core import OPEN_QUESTION_STATUSES, add_open_question

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _questions_from_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("questions"), list):
        return payload["questions"]
    raise ValueError("questions JSON must be a list or an object with a questions list")


def _source_entry_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    raise ValueError("source_entry_ids must be a list when provided")


def main() -> int:
    """Run open-question storage."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--questions-json", type=Path)
    source.add_argument("--question")
    parser.add_argument("--why-it-matters", default="")
    parser.add_argument(
        "--source-entry-id",
        action="append",
        default=[],
        help="Judgement entry ID that prompted this question; repeat as needed.",
    )
    parser.add_argument(
        "--status", default="open", choices=sorted(OPEN_QUESTION_STATUSES)
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.questions_json is not None:
        raw_questions = _questions_from_json(args.questions_json)
    else:
        raw_questions = [
            {
                "question": args.question,
                "why_it_matters": args.why_it_matters,
                "status": args.status,
                "source_entry_ids": args.source_entry_id,
            }
        ]

    added = []
    for raw_question in raw_questions:
        if not isinstance(raw_question, dict):
            raise ValueError("each question entry must be an object")
        added.append(
            add_open_question(
                args.case_dir,
                question=str(raw_question.get("question", "")),
                why_it_matters=str(raw_question.get("why_it_matters", "")),
                source_entry_ids=_source_entry_ids(
                    raw_question.get("source_entry_ids", [])
                ),
                status=str(raw_question.get("status", args.status)),
            )
        )

    LOGGER.info("Added %s open question(s).", len(added))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
