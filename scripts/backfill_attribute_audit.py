from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from modules.pdp.review_constants import (
    add_pdp_store_path_argument,
    enforce_default_pdp_store_path,
)
from modules.pdp.store import PDPStore
from modules.utilities.secrets_loader import load_env_from_secrets_file


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill missing pdp_attribute_audit rows from pdp_attribute_values snapshots."
    )
    add_pdp_store_path_argument(parser)
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        default=None,
        help="Source(s) to backfill (repeatable). Defaults to deterministic + llm.",
    )
    parser.add_argument(
        "--retailer",
        action="append",
        default=None,
        help="Optional retailer scope (repeatable).",
    )
    parser.add_argument(
        "--parent-id",
        action="append",
        dest="parent_ids",
        default=None,
        help="Optional parent_product_id scope (repeatable).",
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

    sources = tuple(args.sources) if args.sources else ("deterministic", "llm")
    retailers = tuple(args.retailer) if args.retailer else None
    parent_ids = tuple(args.parent_ids) if args.parent_ids else None

    inserted = store.backfill_attribute_audit_from_values(
        sources=sources,
        retailers=retailers,
        parent_ids=parent_ids,
    )
    logging.info(
        "Backfill complete (inserted_rows=%s pdp_store_path=%s sources=%s retailers=%s parent_ids=%s)",
        inserted,
        pdp_store_path,
        sources,
        retailers,
        len(parent_ids) if parent_ids else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
