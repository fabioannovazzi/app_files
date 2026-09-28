from __future__ import annotations

"""Snapshot skill IDs and check exact assessment coverage; never judge relevance.

Deterministic handling is justified by mechanically verifiable file hashes and
set equality: it detects forgotten or invented functions without selecting them.
"""

import argparse
import hashlib
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["snapshot", "coverage_errors", "main"]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root: Path) -> dict[str, Any]:
    """Inventory the supplied Vera package or repository plugin directory."""
    root = root.resolve()
    manifest_path = root / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("name") != "vera":
        raise ValueError("Expected a Vera plugin root")
    entries = [
        {
            "function_id": path.parent.name,
            "skill_path": str(path.relative_to(root)),
            "sha256": _digest(path),
        }
        for path in sorted((root / "skills").glob("*/SKILL.md"))
    ]
    if not entries:
        raise ValueError("No Vera skill entrypoints found")
    identity = {"manifest_sha256": _digest(manifest_path), "entries": entries}
    fingerprint = hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "schema": "vera.localization.catalogue.v1",
        "root": str(root),
        "version": manifest.get("version"),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "catalogue_fingerprint": fingerprint,
        **identity,
    }


def coverage_errors(inventory: dict[str, Any], assessment: dict[str, Any]) -> list[str]:
    """Return missing, duplicate, foreign or mismatched catalogue identities."""
    errors: list[str] = []
    if assessment.get("catalogue_fingerprint") != inventory["catalogue_fingerprint"]:
        errors.append("Assessment is bound to a different catalogue snapshot")
    target = assessment.get("target")
    if not isinstance(target, dict) or not target.get("id"):
        errors.append("An explicit target.id is required independently of language")
    rows = assessment.get("rows")
    if not isinstance(rows, list):
        return [*errors, "Assessment rows must be a list"]
    actual = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("function_id"), str):
            errors.append("Each row must contain a string function_id")
        else:
            actual.append(row["function_id"])
    expected = {entry["function_id"] for entry in inventory["entries"]}
    missing = sorted(expected - set(actual))
    extra = sorted(set(actual) - expected)
    duplicates = sorted(key for key, count in Counter(actual).items() if count > 1)
    if missing:
        errors.append("Missing entries: " + ", ".join(missing))
    if extra:
        errors.append("Entries absent from Vera: " + ", ".join(extra))
    if duplicates:
        errors.append("Duplicate entries: " + ", ".join(duplicates))
    return errors


def main() -> int:
    """Write a catalogue or check an authored assessment against it."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("inventory")
    capture.add_argument("--root", type=Path, required=True)
    capture.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("check")
    check.add_argument("--inventory", type=Path, required=True)
    check.add_argument("--assessment", type=Path, required=True)
    check.add_argument(
        "--root", type=Path, help="Also check current catalogue identity"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.command == "inventory":
            result = snapshot(args.root)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, indent=2) + "\n", encoding="utf-8"
            )
            logging.info(
                "Recorded %s entries at %s", len(result["entries"]), args.output
            )
            return 0
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        assessment = json.loads(args.assessment.read_text(encoding="utf-8"))
        errors = coverage_errors(inventory, assessment)
        if (
            args.root
            and snapshot(args.root)["catalogue_fingerprint"]
            != inventory["catalogue_fingerprint"]
        ):
            errors.append("The current catalogue differs from the recorded snapshot")
        for error in errors:
            logging.error(error)
        if errors:
            return 1
        logging.info(
            "Complete coverage: %s entries; no missing, foreign or duplicate IDs",
            len(inventory["entries"]),
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        logging.error("Cannot check catalogue: %s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
