"""Prepare an attribute-reporting run from an existing evidence package."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from attribute_reporting import ContractError, prepare_run

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run the deterministic preparation stage."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--author-agent-id", required=True)
    parser.add_argument("--preview-rows", type=int, default=12)
    parser.add_argument(
        "--mapping-provenance-dir",
        type=Path,
        help=(
            "Directory containing the four reviewed mapping artifacts. "
            "If omitted, provenance at the evidence-package root is copied automatically."
        ),
    )
    parser.add_argument(
        "--download-receipt",
        type=Path,
        help=(
            "Checksum download receipt written by server_bridge_client.py. "
            "Required with server mapping provenance."
        ),
    )
    parser.add_argument(
        "--extraction-receipt",
        type=Path,
        help=(
            "Safe-extraction receipt written by server_bridge_client.py. "
            "Required with server mapping provenance."
        ),
    )
    parser.add_argument(
        "--no-work-workset",
        type=Path,
        help=(
            "Public server workset with status no_work and zero unresolved tasks. "
            "Requires the preliminary download and extraction receipts; mapping "
            "authoring, review, submission, and rebuild are then not applicable."
        ),
    )
    parser.add_argument(
        "--require-browser-qa",
        action="store_true",
        help="Require a current desktop/mobile browser_qa.json before a final verdict.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = prepare_run(
            args.package_dir,
            args.output_dir,
            author_agent_id=args.author_agent_id,
            preview_rows=args.preview_rows,
            require_browser_qa=args.require_browser_qa,
            mapping_provenance_dir=args.mapping_provenance_dir,
            download_receipt_path=args.download_receipt,
            extraction_receipt_path=args.extraction_receipt,
            no_work_workset_path=args.no_work_workset,
        )
    except ContractError as exc:
        LOGGER.error("Preparation failed: %s", exc)
        return 1
    LOGGER.info("Prepared attribute-reporting run at %s", result["output_dir"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
