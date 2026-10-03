#!/usr/bin/env python3
"""Calculate a reviewed costing case in its existing Studio Archive run."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
for vendor in (
    PLUGIN_ROOT / "vendor/modules",
    PLUGIN_ROOT.parent / "_shared/vendor/modules",
):
    if (vendor / "vera_assurance").is_dir():
        sys.path.insert(0, str(vendor))
        break

from costing_core import CostingContractError, require  # noqa: E402
from costing_pack import build_costing_pack  # noqa: E402
from management_control_core import load_json, sha256_file  # noqa: E402
from management_delivery import write_pack_outputs  # noqa: E402
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

__all__ = ["main"]
LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Bind sources, calculate selected methods and persist the standard outputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        context = load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="management-control-pack",
            input_paths=[*args.input, args.case],
            output_dir=args.output_dir,
        )
        require(
            not args.output_dir.exists() or not any(args.output_dir.iterdir()),
            "OUTPUT_EXISTS",
            "Choose a fresh calculation folder; preserve earlier results and reviews",
        )
        payload = load_json(args.case)
        pack = build_costing_pack(payload)
        meta = payload["case"]["meta"]
        require(
            meta["clientId"] == context["client_id"]
            and meta["engagementId"] == context["engagement_id"],
            "CROSS_CLIENT",
            "Costing case belongs to a different client or engagement",
        )
        sources = {sha256_file(path): path for path in args.input}
        require(
            len(sources) == len(args.input),
            "SOURCE",
            "Do not duplicate selected source bytes",
        )
        for evidence in payload["case"]["evidence"]:
            require(
                evidence.get("source_sha256") in sources,
                "SOURCE",
                "Every costing evidence record must identify a selected source by exact SHA-256, including recorded statements and estimates",
            )
        pack["source_lineage"] = {
            f"input_{index:03d}": {
                "source_id": f"input_{index:03d}",
                "sha256": digest,
                "byte_count": path.stat().st_size,
            }
            for index, (digest, path) in enumerate(sources.items(), start=1)
        }
        write_pack_outputs(
            pack, inputs=args.input, recipe_path=args.case, output_dir=args.output_dir
        )
    except (AssuranceContractError, CostingContractError, OSError, ValueError) as exc:
        parser.error(str(exc))
    LOGGER.info("Wrote costing pack with status %s", pack["status"])
    return 2 if pack["status"] == "blocked" else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
