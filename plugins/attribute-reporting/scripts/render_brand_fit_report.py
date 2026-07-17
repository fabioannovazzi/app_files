#!/usr/bin/env python3
"""Render a Codex-authored local Brand Fit report."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from brand_fit import BrandFitContractError, render_brand_fit_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        render_brand_fit_report(args.output_dir)
    except BrandFitContractError as exc:
        logging.error("Brand Fit rendering failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
