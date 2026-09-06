#!/usr/bin/env python3
"""Inspect a small deterministic sample from explicitly named source columns."""

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
        # Standalone components retain their host's dependency setup.
        if any(
            (_p / "components.json").is_file()
            for _p in _Path(__file__).resolve().parents
        ):
            raise SystemExit(
                "Managed Python launcher is missing; rebuild the plugin package."
            )

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from variance_core import is_vera_managed_host, read_table, write_json

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent.parent / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        if str(_vendor_root) not in sys.path:
            sys.path.insert(0, str(_vendor_root))
        break

from vera_assurance import AssuranceContractError, load_client_engagement_context_file

MAX_COLUMNS = 12
MAX_ROWS = 10


def inspect_columns(input_path: Path, columns: Sequence[str], output_path: Path) -> dict:
    requested = list(dict.fromkeys(item.strip() for item in columns if item.strip()))
    if not requested or len(requested) > MAX_COLUMNS:
        raise ValueError(f"request 1 to {MAX_COLUMNS} explicit columns")
    frame = read_table(input_path)
    unknown = sorted(set(requested) - set(frame.columns))
    if unknown:
        raise ValueError(f"unknown source columns: {unknown}")
    payload = {
        "schema_version": "vera.variance_targeted_column_inspection.v1",
        "source_row_count": frame.height,
        "sample_row_limit": MAX_ROWS,
        "sample_behavior": "first_rows_source_order_no_sampling_inference",
        "columns": requested,
        "sample_rows": frame.select(requested).head(MAX_ROWS).to_dicts(),
    }
    write_json(output_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--column", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--client-engagement", type=Path)
    args = parser.parse_args(argv)
    try:
        if is_vera_managed_host() and args.client_engagement is None:
            raise ValueError("Vera targeted inspection requires --client-engagement")
        if args.client_engagement is not None:
            load_client_engagement_context_file(
                args.client_engagement,
                expected_workflow_id="variance-analysis",
                input_paths=[args.input],
                output_dir=args.output.parent,
            )
        payload = inspect_columns(args.input, args.column, args.output)
    except (AssuranceContractError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, "sample_rows": len(payload["sample_rows"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
