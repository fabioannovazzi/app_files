from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
ROOT_PATH = str(ROOT_DIR)
if ROOT_PATH in sys.path:
    sys.path.remove(ROOT_PATH)
sys.path.insert(0, ROOT_PATH)

from modules.pdp.review_constants import (
    add_pdp_store_path_argument,
    enforce_default_pdp_store_path,
)
from modules.pdp.store import PDPStore
from modules.utilities.secrets_loader import load_env_from_secrets_file


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Re-materialize raw retailer filter observations as taxonomy-aligned "
            "pdp_attribute_values rows."
        )
    )
    add_pdp_store_path_argument(parser)
    parser.add_argument(
        "--retailer",
        action="append",
        required=True,
        help="Retailer key to normalize. Repeat to include multiple retailers.",
    )
    parser.add_argument(
        "--category",
        action="append",
        required=True,
        dest="categories",
        help="Category key to normalize. Repeat to include multiple categories.",
    )
    parser.add_argument(
        "--append-only",
        action="store_true",
        help=(
            "Do not remove existing source=retailer_filter rows before writing "
            "normalized rows. The default replaces the requested retailer/category "
            "scope so stale display-label attribute IDs are removed."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s:%(lineno)d | %(message)s",
    )
    args = _parse_args(argv)
    load_env_from_secrets_file()
    pdp_store_path = enforce_default_pdp_store_path(args.pdp_store_path)
    store = PDPStore(pdp_store_path)

    total_rows = 0
    replace_existing = not bool(args.append_only)
    for retailer in args.retailer:
        for category in args.categories:
            row_count = store.materialize_retailer_filter_attributes(
                retailer=retailer,
                category_key=category,
                replace_existing=replace_existing,
            )
            total_rows += row_count
            logging.info(
                "Normalized retailer filter attributes "
                "(retailer=%s category=%s rows=%s replace_existing=%s).",
                retailer,
                category,
                row_count,
                replace_existing,
            )
            gaps = store.retailer_filter_normalization_gaps(
                retailer=retailer,
                category_key=category,
            )
            if gaps:
                logging.warning(
                    "Retailer filter normalization found taxonomy gaps "
                    "(retailer=%s category=%s gap_count=%s).",
                    retailer,
                    category,
                    len(gaps),
                )
                for gap in gaps[:20]:
                    logging.warning(
                        "Filter taxonomy gap: attribute_id=%s value=%s rows=%s reason=%s",
                        gap["attribute_id"],
                        gap["value"],
                        gap["row_count"],
                        gap["reason"],
                    )
                if len(gaps) > 20:
                    logging.warning(
                        "Suppressed %s additional filter taxonomy gap(s).",
                        len(gaps) - 20,
                    )
    logging.info(
        "Retailer filter normalization complete "
        "(total_rows=%s pdp_store_path=%s).",
        total_rows,
        pdp_store_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
