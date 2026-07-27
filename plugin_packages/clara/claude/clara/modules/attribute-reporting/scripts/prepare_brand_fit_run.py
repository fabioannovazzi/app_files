#!/usr/bin/env python3
"""Prepare a local Brand Fit run from checked retailer and server evidence."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from brand_fit import BrandFitContractError, prepare_brand_fit_run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--retailer-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--author-agent-id", required=True)
    parser.add_argument("--download-receipt", type=Path, required=True)
    parser.add_argument("--extraction-receipt", type=Path, required=True)
    parser.add_argument("--skip-browser-qa", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        prepare_brand_fit_run(
            args.package_dir,
            retailer_run_dir=args.retailer_run,
            output_dir=args.output_dir,
            author_agent_id=args.author_agent_id,
            download_receipt_path=args.download_receipt,
            extraction_receipt_path=args.extraction_receipt,
            require_browser_qa=not args.skip_browser_qa,
        )
    except BrandFitContractError as exc:
        logging.error("Brand Fit preparation failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
