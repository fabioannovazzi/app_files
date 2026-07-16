from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.category_keys import canonical_category_keys
from modules.pdp.lorealparis_catalog import (
    LOREALPARIS_RETAILER,
    lorealparis_category_from_url,
)
from modules.pdp.lorealparis_filter_discovery import (
    build_lorealparis_filter_records,
)
from modules.pdp.postgres_compat import connect_pdp_database
from modules.pdp.review_constants import (
    add_pdp_store_path_argument,
    enforce_default_pdp_store_path,
)
from modules.pdp.store import PDPStore
from modules.utilities.secrets_loader import load_env_from_secrets_file

LOGGER = logging.getLogger(__name__)
DEFAULT_EVIDENCE_ROOT = Path("data/pdp/retailer_filter_evidence")


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize L'Oreal Paris PDP site tags as retailer_filter attribute "
            "observations for parsed parent products."
        ),
    )
    add_pdp_store_path_argument(parser)
    parser.add_argument(
        "--categories",
        nargs="*",
        default=("blush", "bronzer"),
        help="Category keys to materialize (default: blush bronzer).",
    )
    parser.add_argument(
        "--filter-families",
        nargs="*",
        default=None,
        help="Optional semantic attribute families to keep.",
    )
    parser.add_argument(
        "--crawl-ts",
        default=None,
        help="Optional crawl timestamp to persist. Defaults to current UTC time.",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=DEFAULT_EVIDENCE_ROOT,
        help=(
            "Directory for JSON evidence artifacts "
            "(default: data/pdp/retailer_filter_evidence)."
        ),
    )
    return parser.parse_args(list(argv))


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def _load_parent_rows(
    pdp_store_path: Path,
    *,
    categories: set[str] | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    query = """
        SELECT parent_product_id, pdp_url, extras
        FROM parent_products
        WHERE retailer = ?
          AND COALESCE(TRIM(parent_product_id), '') <> ''
    """
    try:
        with connect_pdp_database(pdp_store_path) as conn:
            raw_rows = conn.execute(query, (LOREALPARIS_RETAILER,)).fetchall()
    except Exception as exc:
        LOGGER.warning("Unable to load L'Oreal Paris parent rows: %s", exc)
        return rows

    for parent_id, pdp_url, raw_extras in raw_rows:
        category_key = lorealparis_category_from_url(str(pdp_url or "")) or ""
        extras = _parse_extras(raw_extras)
        extras_category = str(extras.get("category_key") or "").strip().lower()
        if extras_category:
            category_key = extras_category
        if categories is not None and category_key not in categories:
            continue
        rows.append(
            {
                "parent_product_id": str(parent_id or "").strip(),
                "pdp_url": str(pdp_url or "").strip(),
                "category_key": category_key,
                "extras": extras,
            }
        )
    return rows


def _parse_extras(raw_value: object) -> Mapping[str, object]:
    if isinstance(raw_value, Mapping):
        return raw_value
    if not isinstance(raw_value, str) or not raw_value.strip():
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, Mapping) else {}


def _write_evidence(
    *,
    evidence_root: Path,
    crawl_ts: str,
    surfaces: Sequence[object],
    observations: Sequence[object],
    parent_count: int,
) -> Path:
    run_dir = (
        evidence_root
        / LOREALPARIS_RETAILER
        / crawl_ts.replace(":", "").replace("+", "Z")
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    surface_rows = [asdict(item) for item in surfaces]
    observation_rows = [asdict(item) for item in observations]
    (run_dir / "retailer_filter_surfaces.json").write_text(
        json.dumps(surface_rows, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (run_dir / "retailer_filter_observations.json").write_text(
        json.dumps(observation_rows, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    summary = {
        "retailer": LOREALPARIS_RETAILER,
        "crawl_ts": crawl_ts,
        "parent_rows": parent_count,
        "surface_rows": len(surface_rows),
        "observation_rows": len(observation_rows),
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return run_dir


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    _configure_logging()
    load_env_from_secrets_file()
    pdp_store_path = enforce_default_pdp_store_path(args.pdp_store_path)
    categories = canonical_category_keys(LOREALPARIS_RETAILER, args.categories)
    crawl_ts = args.crawl_ts or dt.datetime.now(dt.timezone.utc).isoformat()
    parents = _load_parent_rows(pdp_store_path, categories=categories)
    surfaces, observations = build_lorealparis_filter_records(
        parents,
        allowed_categories=sorted(categories) if categories else None,
        allowed_families=args.filter_families,
    )

    store = PDPStore(pdp_store_path)
    store.append_retailer_filter_surfaces(crawl_ts=crawl_ts, surfaces=surfaces)
    store.append_retailer_filter_observations(
        crawl_ts=crawl_ts,
        observations=observations,
    )
    evidence_dir = _write_evidence(
        evidence_root=args.evidence_root,
        crawl_ts=crawl_ts,
        surfaces=surfaces,
        observations=observations,
        parent_count=len(parents),
    )
    LOGGER.info(
        "Materialized L'Oreal Paris filters: parents=%d surfaces=%d observations=%d evidence=%s",
        len(parents),
        len(surfaces),
        len(observations),
        evidence_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
