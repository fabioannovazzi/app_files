#!/usr/bin/env python3
"""Record visible evidence of an explicitly approved send or publication."""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

from workflow_core import (
    atomic_write_json,
    load_json,
    utc_now,
    validate_finalized_package,
    workflow_lock,
)

__all__ = ["record_external_delivery", "main"]

LOGGER = logging.getLogger(__name__)
ALLOWED_ACTIONS = {"email_sent", "website_published", "social_published", "uploaded"}


def record_external_delivery(
    run_dir: Path,
    *,
    action: str,
    destination: str,
    visible_receipt: str,
    confirmed_by: str,
    confirmed_by_user: bool,
) -> Path:
    """Persist user-confirmed external evidence without storing credentials."""

    if not confirmed_by_user:
        raise ValueError("External delivery recording requires --confirmed-by-user")
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"Unsupported external action: {action}")
    if not all(value.strip() for value in (destination, visible_receipt, confirmed_by)):
        raise ValueError("Destination, visible receipt, and confirmer are required")
    if re.search(r"(?i)(?:token|code|key|secret|signature)=", visible_receipt):
        raise ValueError(
            "Visible receipt must not contain credential-like query parameters"
        )

    root = run_dir.resolve()
    with workflow_lock(root):
        intake = load_json(root / "run_intake.json")
        final = load_json(root / "final_artifacts.json")
        package_digest = validate_finalized_package(root)
        route = intake["external_routes"]["send_or_publish"]
        if not route["selected"] or not (
            route.get("approved_by") and route.get("approved_at")
        ):
            raise ValueError(
                "Send or publish route was not explicitly selected and approved"
            )
        expected_destination = str(route.get("destination") or "").strip()
        if expected_destination and expected_destination != destination.strip():
            raise ValueError("Destination differs from the approved intake route")

        path = root / "external_delivery.json"
        if path.exists():
            raise ValueError(
                "External delivery is already recorded; do not overwrite evidence"
            )
        payload = {
            "schema_version": 1,
            "workflow": "comunicazione-professionale",
            "run_id": intake["run_id"],
            "input_digest": final["input_digest"],
            "contribution_digest": final["contribution_digest"],
            "package_digest": package_digest,
            "validation_receipt_digest": final["validation_receipt"]["receipt_digest"],
            "action": action,
            "destination": destination.strip(),
            "visible_receipt": visible_receipt.strip(),
            "confirmed_by": confirmed_by.strip(),
            "confirmed_at": utc_now(),
        }
        return atomic_write_json(path, payload)


def main(argv: list[str] | None = None) -> int:
    """Record one confirmed external action."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--action", choices=sorted(ALLOWED_ACTIONS), required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--visible-receipt", required=True)
    parser.add_argument("--confirmed-by", required=True)
    parser.add_argument("--confirmed-by-user", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = record_external_delivery(
            args.run_dir,
            action=args.action,
            destination=args.destination,
            visible_receipt=args.visible_receipt,
            confirmed_by=args.confirmed_by,
            confirmed_by_user=args.confirmed_by_user,
        )
    except (OSError, ValueError) as exc:
        LOGGER.error("EXTERNAL_DELIVERY_RECORD_FAILED: %s", exc)
        return 1
    LOGGER.info("Recorded external delivery evidence: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
