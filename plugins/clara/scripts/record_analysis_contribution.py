"""Commit one model-authored advisory evidence, claim, and judgement bundle."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from advisor_case_core import CaseWorkspaceError, record_analysis_contribution

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _load_bundle(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CaseWorkspaceError("analysis contribution must be a JSON object")
    allowed = {"evidence_receipts", "claims", "judgement_entries"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise CaseWorkspaceError(
            "unknown analysis contribution fields: " + ", ".join(unknown)
        )
    for field in allowed:
        value = payload.get(field, [])
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            raise CaseWorkspaceError(f"{field} must be an array of objects")
    if not payload.get("claims"):
        raise CaseWorkspaceError("analysis contribution requires at least one claim")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("contribution_json", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        payload = _load_bundle(args.contribution_json)
        result = record_analysis_contribution(
            args.case_dir,
            evidence_receipts=payload.get("evidence_receipts", []),
            claims=payload.get("claims", []),
            judgement_entries=payload.get("judgement_entries", []),
        )
    except (CaseWorkspaceError, OSError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.error("Analysis contribution failed: %s", exc)
        return 1
    LOGGER.info(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
