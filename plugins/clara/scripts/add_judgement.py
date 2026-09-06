"""Store Codex-structured judgement entries in a case workspace."""

from __future__ import annotations

# Direct CLI calls must select dependencies before importing workflow modules.
if __name__ == "__main__":
    import runpy as _runpy
    from pathlib import Path as _Path

    for _parent in _Path(__file__).resolve().parents:
        _launcher = _parent / "scripts" / "self_relaunch.py"
        if not _launcher.is_file():
            _launcher = _parent / "clara" / "scripts" / "self_relaunch.py"
        if _launcher.is_file():
            _runpy.run_path(str(_launcher))["ensure_running_in_managed_venv"](__file__)
            break
    else:
        raise SystemExit(
            "Managed Python launcher is missing; rebuild the plugin package."
        )

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from advisor_case_core import JUDGEMENT_KINDS, JUDGEMENT_STATUSES, add_judgement_entries

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _entries_from_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        return payload["entries"]
    raise ValueError("entries JSON must be a list or an object with an entries list")


def main() -> int:
    """Run judgement-entry storage."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--entries-json", type=Path)
    source.add_argument("--text")
    parser.add_argument("--kind", choices=sorted(JUDGEMENT_KINDS))
    parser.add_argument(
        "--status", default="pending", choices=sorted(JUDGEMENT_STATUSES)
    )
    parser.add_argument("--source-material-id", action="append", default=[])
    parser.add_argument("--advisory-claim-id", default="")
    parser.add_argument("--evidence-receipt-id", action="append", default=[])
    parser.add_argument("--rationale", default="")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.entries_json is not None:
        entries = _entries_from_json(args.entries_json)
    else:
        if args.kind is None:
            parser.error("--kind is required when using --text")
        entries = [
            {
                "kind": args.kind,
                "text": args.text,
                "status": args.status,
                "source_material_ids": args.source_material_id,
                "advisory_claim_id": args.advisory_claim_id,
                "evidence_receipt_ids": args.evidence_receipt_id,
                "rationale": args.rationale,
            }
        ]

    added = add_judgement_entries(args.case_dir, entries)
    LOGGER.info(
        "Added %s judgement %s.", len(added), "entry" if len(added) == 1 else "entries"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
