"""Persist Clara inclusion-review bundles from a semantic review plan."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from advisor_case_core import CaseWorkspaceError, apply_inclusion_bundles

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _read_bundles(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("bundles"), list):
        return payload["bundles"]
    raise CaseWorkspaceError("bundles JSON must be a list or an object with bundles")


def main() -> int:
    """Apply a model/Codex-authored inclusion-bundle plan."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument(
        "--bundles-json",
        required=True,
        type=Path,
        help="JSON list or object with bundles: title, optional id, entry_ids.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        result = apply_inclusion_bundles(
            args.case_dir,
            _read_bundles(args.bundles_json),
        )
    except (CaseWorkspaceError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    LOGGER.info("Inclusion bundles: %s", result.bundles_path)
    LOGGER.info("Bundle count: %s", result.bundle_count)
    LOGGER.info("Bundled entries: %s", result.bundled_entry_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
