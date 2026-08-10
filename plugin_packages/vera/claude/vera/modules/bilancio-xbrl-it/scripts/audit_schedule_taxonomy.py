#!/usr/bin/env python3
"""Audit the versioned schedule adapter against a locked taxonomy catalogue."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

from schedule_taxonomy_adapter import build_schedule_table_inventory

__all__ = ["audit_schedule_taxonomy", "main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULE_PACK = PLUGIN_ROOT / "rulepacks" / "it" / "schedule-taxonomy-2026.1.json"
EXPECTED_SCHEDULE_TYPES = {
    "EQUITY",
    "FIXED_ASSETS",
    "GUARANTEES_COMMITMENTS",
    "INVENTORIES",
    "PAYABLES",
    "PROVISIONS",
    "RECEIVABLES",
    "TAXES",
    "TFR",
}


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Audit input must be a regular local file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Audit JSON input must contain an object")
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_schedule_taxonomy(
    catalogue: Mapping[str, Any], rule_pack: Mapping[str, Any]
) -> dict[str, Any]:
    """Return structural closure evidence for all configured schedule tables."""

    forms: dict[str, Any] = {}
    issues: list[str] = []
    for form in ("ORDINARY", "ABBREVIATED", "MICRO"):
        inventory = build_schedule_table_inventory(catalogue, rule_pack, form)
        observed_types = set(inventory["schedules"])
        if observed_types != EXPECTED_SCHEDULE_TYPES:
            issues.append(f"{form} schedule types differ: {sorted(observed_types)}")
        schedules = {}
        for schedule_type, policy in inventory["schedules"].items():
            roots = [str(item["root"]) for item in policy["tables"]]
            concepts = {
                str(item["xbrl_concept"]) for item in policy["allowed_concepts"]
            }
            if policy["strategy"] == "TABLE_FACTS" and (not roots or not concepts):
                issues.append(f"{form} {schedule_type} has no table facts")
            if policy["strategy"] == "TEXT_ONLY" and (roots or concepts):
                issues.append(
                    f"{form} {schedule_type} text-only policy has table facts"
                )
            schedules[schedule_type] = {
                "strategy": policy["strategy"],
                "table_roots": roots,
                "unique_allowed_fact_concepts": len(concepts),
            }
        forms[form] = {
            "inventory_sha256": inventory["inventory_sha256"],
            "schedules": schedules,
        }
    return {
        "schema_version": 1,
        "audit_id": "BILANCIO_SCHEDULE_TAXONOMY_2026.1",
        "taxonomy_id": str(catalogue["taxonomy_id"]),
        "taxonomy_package_sha256": str(catalogue["taxonomy_package_sha256"]),
        "rule_pack_id": str(rule_pack["id"]),
        "forms": forms,
        "issues": issues,
        "status": "PASS" if not issues else "FAIL",
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run the audit and write its deterministic report."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--rule-pack", type=Path, default=DEFAULT_RULE_PACK)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        catalogue = _read_json(args.catalogue)
        rule_pack = _read_json(args.rule_pack)
        result = audit_schedule_taxonomy(catalogue, rule_pack)
        result["catalogue_sha256"] = _sha256_file(args.catalogue)
        result["rule_pack_sha256"] = _sha256_file(args.rule_pack)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info("Schedule taxonomy audit %s", result["status"])
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
