"""Prepare an evidence-bound incident alert; never send or modify the registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.operational_incidents.reporting import (
    AlertReview,
    followup_hash,
    render_alert,
)

__all__ = ["main"]


def main() -> None:
    """Inspect exact followup hashes or render one reviewed alert for normal dedup."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incident", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    incident = json.loads(args.incident.read_text())
    result: dict[str, object] | list[dict[str, object]]
    if args.review is None:
        result = [
            {**row, "followup_sha256": followup_hash(row)}
            for row in incident["remedy_followups"]
        ]
    else:
        review = AlertReview.model_validate_json(args.review.read_text())
        ledger = json.loads(args.ledger.read_text()) if args.ledger else {}
        result = render_alert(incident, review, ledger.get("device_labels", {}))
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(content)
        args.output.chmod(0o600)
    else:
        sys.stdout.write(content)


if __name__ == "__main__":
    main()
