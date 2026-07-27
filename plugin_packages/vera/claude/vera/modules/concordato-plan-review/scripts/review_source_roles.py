"""Seal reviewed Concordato source roles and numeric-candidate dispositions."""

from __future__ import annotations

import sys as _bootstrap_sys  # isort: skip

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__concordato_no_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/concordato-plan-review"
)

import os as _bootstrap_os  # isort: skip

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_ENTRY = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _BOOTSTRAP_ENTRY.st_mode & 0o170000 != 0o100000 or _BOOTSTRAP_ENTRY.st_nlink != 1:
    raise RuntimeError("Concordato implementation bootstrap is not a real file.")
with open(_BOOTSTRAP_PATH, "rb") as _bootstrap_handle:
    _BOOTSTRAP_BEFORE = _bootstrap_os.fstat(_bootstrap_handle.fileno())
    _BOOTSTRAP_BYTES = _bootstrap_handle.read()
    _BOOTSTRAP_AFTER = _bootstrap_os.fstat(_bootstrap_handle.fileno())
_BOOTSTRAP_IDENTITY = (
    _BOOTSTRAP_ENTRY.st_dev,
    _BOOTSTRAP_ENTRY.st_ino,
    _BOOTSTRAP_ENTRY.st_size,
    _BOOTSTRAP_ENTRY.st_mtime_ns,
)
if (
    _BOOTSTRAP_IDENTITY
    != (
        _BOOTSTRAP_BEFORE.st_dev,
        _BOOTSTRAP_BEFORE.st_ino,
        _BOOTSTRAP_BEFORE.st_size,
        _BOOTSTRAP_BEFORE.st_mtime_ns,
    )
    or _BOOTSTRAP_IDENTITY
    != (
        _BOOTSTRAP_AFTER.st_dev,
        _BOOTSTRAP_AFTER.st_ino,
        _BOOTSTRAP_AFTER.st_size,
        _BOOTSTRAP_AFTER.st_mtime_ns,
    )
    or len(_BOOTSTRAP_BYTES) != _BOOTSTRAP_AFTER.st_size
):
    raise RuntimeError("Concordato implementation bootstrap changed while read.")
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_concordato_implementation_bootstrap",
}
# The exact stable single-link bootstrap source is verified above.
exec(  # nosec B102
    compile(_BOOTSTRAP_BYTES, _BOOTSTRAP_PATH, "exec"), _BOOTSTRAP_NAMESPACE
)
_BOOTSTRAP_NAMESPACE["activate_implementation_boundary"]()
_SCRIPTS_DIR = _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__))
if _SCRIPTS_DIR not in _bootstrap_sys.path:
    _bootstrap_sys.path.insert(0, _SCRIPTS_DIR)

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Any

from concordato_plan_core import (
    AmountCandidate,
    configure_logging,
    parse_canonical_decimal,
    review_source_roles,
    write_json,
)

LOGGER = logging.getLogger(__name__)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_candidates(path: Path) -> list[AmountCandidate]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        AmountCandidate(
            source_file=str(row["source_file"]),
            source_role="unclassified",
            location=str(row["location"]),
            amount=parse_canonical_decimal(
                str(row["amount"]),
                label="raw candidate amount",
            ),
            token=str(row["token"]),
            context=str(row["context"]),
            source_artifact_ref=str(row["source_artifact_ref"]),
            currency=str(row.get("currency") or "EUR"),
            unit=str(row.get("unit") or "1"),
        )
        for row in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inspection_dir", type=Path)
    parser.add_argument("decisions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    configure_logging(args.verbose)

    inventory = _read_json(args.inspection_dir / "inventory.json")
    audit = _read_json(args.inspection_dir / "run_audit.json")
    decisions = _read_json(args.decisions)
    if (
        not isinstance(inventory, list)
        or not isinstance(audit, dict)
        or not isinstance(decisions, dict)
    ):
        raise ValueError("Inventory, audit, and decisions must be structured JSON")
    source_roles = decisions.get("source_roles")
    dispositions = decisions.get("candidate_dispositions")
    if not isinstance(source_roles, dict) or not isinstance(dispositions, dict):
        raise ValueError(
            "Decisions require source_roles and candidate_dispositions objects"
        )
    recipe = review_source_roles(
        inventory,
        source_roles,
        _read_candidates(args.inspection_dir / "raw_amount_candidates.csv"),
        {str(key): str(value) for key, value in dispositions.items()},
        reviewer_ref=str(decisions.get("reviewer_ref") or ""),
        reviewed_on=str(decisions.get("reviewed_on") or ""),
        reference_date=str(audit.get("reference_date") or ""),
        tolerance=str(audit.get("tolerance") or ""),
    )
    write_json(args.output, recipe)
    LOGGER.info("wrote reviewed source-role recipe to %s", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
