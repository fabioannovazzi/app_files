"""Prepare Clara for the first senior-partner kickoff."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from advisor_case_core import CaseWorkspaceError, prepare_clara_kickoff

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _load_json_list(path: Path | None) -> list[Any]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise CaseWorkspaceError(f"{path} must contain a JSON list")
    return payload


def main() -> int:
    """Run Clara kickoff preparation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument(
        "--industry-context-json",
        type=Path,
        default=None,
        help="Optional JSON list of concise industry-context notes.",
    )
    parser.add_argument(
        "--external-research-json",
        type=Path,
        default=None,
        help="Optional JSON list of {title, url, takeaway} research notes.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = prepare_clara_kickoff(
        args.case_dir,
        industry_context=_load_json_list(args.industry_context_json),
        external_research=_load_json_list(args.external_research_json),
    )
    LOGGER.info("Clara mandate: %s", result.mandate_path)
    LOGGER.info("Kickoff preparation: %s", result.preparation_path)
    LOGGER.info("Materials considered: %s", result.material_count)
    LOGGER.info("Research notes recorded: %s", result.baseline_source_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
