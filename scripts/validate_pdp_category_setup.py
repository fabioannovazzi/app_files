from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.add_attributes.pdp_attribute_export import validate_category_setup
from modules.pdp.review_constants import (
    add_pdp_store_path_argument,
    enforce_default_pdp_store_path,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight-check retailer/category setup before running export_pdp_attributes."
        )
    )
    parser.add_argument("--retailer", required=True, help="Retailer key.")
    parser.add_argument("--category", required=True, help="Normalized category key.")
    add_pdp_store_path_argument(parser)
    parser.add_argument(
        "--links-path",
        type=Path,
        default=Path("data/pdp/links.json"),
        help="Path to links.json.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Optional discovery run folder to validate listing/filter capture too.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = validate_category_setup(
        pdp_store_path=enforce_default_pdp_store_path(args.pdp_store_path),
        retailer=args.retailer,
        category_key=args.category,
        links_path=args.links_path,
        run_dir=args.run_dir,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
