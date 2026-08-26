"""Record one model-authored analysis or validation return into a Clara case."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from advisor_case_core import CaseWorkspaceError, record_case_direction_return

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("declared_return_json", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        payload = json.loads(args.declared_return_json.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise CaseWorkspaceError("case-direction return must be a JSON object")
        result = record_case_direction_return(args.case_dir, payload)
    except (CaseWorkspaceError, OSError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.error("Case-direction return failed: %s", exc)
        return 1
    LOGGER.info(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
