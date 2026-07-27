#!/usr/bin/env python3
"""Check a local Brand Fit report and print its exact direct verdict."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from brand_fit import BrandFitContractError, check_brand_fit_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = check_brand_fit_report(args.output_dir)
    except BrandFitContractError as exc:
        logging.error("Brand Fit checking failed: %s", exc)
        return 1
    logging.info("%s", result["verdict"])
    return 0 if result["verdict"] in {"Correct", "Correct with caveats"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
