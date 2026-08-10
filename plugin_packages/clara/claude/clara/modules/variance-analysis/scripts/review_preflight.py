"""Validate the managed Vera run that owns Variance Analysis review outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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

from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_workflow_context_for_output,
)

__all__ = ["main"]


def main() -> int:
    """Return the exact running client identity for an output directory."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--client-run-preflight-only", action="store_true")
    args = parser.parse_args()
    if not args.client_run_preflight_only:
        parser.error("--client-run-preflight-only is required")
    try:
        context = load_client_workflow_context_for_output(
            args.output_dir,
            expected_workflow_id="variance-analysis",
        )
    except AssuranceContractError as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "ok": True,
                "schema_version": context["schema_version"],
                "workflow_id": context["workflow_id"],
                "client_run_id": context["run_id"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
