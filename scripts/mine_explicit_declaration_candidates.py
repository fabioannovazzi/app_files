from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path
from typing import Sequence

from modules.add_attributes.attribute_taxonomy import get_attribute_taxonomy
from modules.add_attributes.explicit_candidate_mining import (
    load_parent_pdp_text_rows,
    mine_explicit_declaration_candidates,
)
from modules.add_attributes.explicit_declaration_classifier import (
    load_explicit_declaration_rules,
)
from modules.pdp.review_constants import (
    add_pdp_store_path_argument,
    enforce_default_pdp_store_path,
)
from modules.pdp.store import PDPStore
from modules.utilities.secrets_loader import load_env_from_secrets_file

LOGGER = logging.getLogger(__name__)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Mine phrase candidates for explicit declaration rules and persist "
            "them to the review queue."
        )
    )
    add_pdp_store_path_argument(parser)
    parser.add_argument(
        "--retailer",
        action="append",
        help="Optional retailer scope (repeatable).",
    )
    parser.add_argument(
        "--category",
        action="append",
        help="Optional normalized category scope (repeatable).",
    )
    parser.add_argument(
        "--min-sample-count",
        type=int,
        default=3,
        help="Minimum supporting sample count before a candidate is queued.",
    )
    parser.add_argument(
        "--max-snippets",
        type=int,
        default=5,
        help="Maximum snippets stored per candidate.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level (default: INFO).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(levelname)s %(name)s:%(lineno)d | %(message)s",
    )
    load_env_from_secrets_file()
    pdp_store_path = enforce_default_pdp_store_path(args.pdp_store_path)

    source_df = load_parent_pdp_text_rows(
        pdp_store_path,
        retailers=tuple(args.retailer) if args.retailer else None,
        categories=tuple(args.category) if args.category else None,
    )
    if source_df.is_empty():
        LOGGER.info("No parent PDP rows available for candidate mining.")
        return 0

    taxonomy = get_attribute_taxonomy()
    rules = load_explicit_declaration_rules()
    mined = mine_explicit_declaration_candidates(
        source_df,
        taxonomy=taxonomy,
        rules=rules,
        min_sample_count=max(1, int(args.min_sample_count)),
        max_snippets_per_candidate=max(1, int(args.max_snippets)),
    )

    if not mined:
        LOGGER.info("No new explicit declaration candidates mined.")
        return 0

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    store = PDPStore(pdp_store_path)
    rows = [
        {
            "candidate_id": candidate.candidate_id,
            "category_key": candidate.category_key,
            "attribute_id": candidate.attribute_id,
            "proposed_value": candidate.proposed_value,
            "pattern": candidate.pattern,
            "pattern_type": candidate.pattern_type,
            "sample_count": candidate.sample_count,
            "sample_snippets": list(candidate.sample_snippets),
            "estimated_conflict_rate": candidate.estimated_conflict_rate,
            "status": candidate.status,
            "created_at": now,
            "updated_at": now,
        }
        for candidate in mined
    ]
    changed = store.upsert_explicit_rule_candidates(rows)
    LOGGER.info(
        "Persisted explicit declaration candidates: mined=%s, store_changes=%s",
        len(mined),
        changed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
