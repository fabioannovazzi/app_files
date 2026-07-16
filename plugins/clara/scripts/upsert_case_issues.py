"""Create or update Clara cross-interview case issues."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from advisor_case_core import ISSUE_STATUSES, upsert_case_issues

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _issues_from_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("issues"), list):
        return payload["issues"]
    raise ValueError("issues JSON must be a list or an object with an issues list")


def _id_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    raise ValueError("issue evidence/open-test fields must be lists")


def main() -> int:
    """Run case-issue upsert."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--issues-json", type=Path)
    source.add_argument("--title")
    parser.add_argument("--id")
    parser.add_argument("--decision-area", default="")
    parser.add_argument("--current-synthesis", default="")
    parser.add_argument("--evidence-for", action="append", default=[])
    parser.add_argument("--evidence-against", action="append", default=[])
    parser.add_argument("--open-test", action="append", default=[])
    parser.add_argument("--status", default="active", choices=sorted(ISSUE_STATUSES))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.issues_json is not None:
        raw_issues = _issues_from_json(args.issues_json)
    else:
        raw_issues = [
            {
                "id": args.id,
                "title": args.title,
                "decision_area": args.decision_area,
                "current_synthesis": args.current_synthesis,
                "evidence_for": args.evidence_for,
                "evidence_against": args.evidence_against,
                "open_tests": args.open_test,
                "status": args.status,
            }
        ]

    issues = []
    for raw_issue in raw_issues:
        if not isinstance(raw_issue, dict):
            raise ValueError("each issue must be an object")
        issues.append(
            {
                "id": raw_issue.get("id"),
                "title": raw_issue.get("title", ""),
                "decision_area": raw_issue.get("decision_area", ""),
                "current_synthesis": raw_issue.get("current_synthesis", ""),
                "evidence_for": _id_list(raw_issue.get("evidence_for", [])),
                "evidence_against": _id_list(raw_issue.get("evidence_against", [])),
                "open_tests": _id_list(raw_issue.get("open_tests", [])),
                "status": raw_issue.get("status", args.status),
            }
        )

    updated = upsert_case_issues(args.case_dir, issues)
    LOGGER.info("Upserted %s case issue(s).", len(updated))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
