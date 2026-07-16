from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.category_keys import canonical_category_keys
from modules.pdp.postgres_compat import connect_pdp_database, is_postgres_enabled
from modules.pdp.review_constants import (
    add_pdp_store_path_argument,
    enforce_default_pdp_store_path,
)
from modules.pdp.store import PDPStore
from modules.pdp.vince_catalog import VINCE_CATEGORY_KEY, VINCE_RETAILER
from modules.pdp.vince_filter_discovery import build_vince_filter_records
from modules.utilities.secrets_loader import load_env_from_secrets_file

LOGGER = logging.getLogger(__name__)
DEFAULT_EVIDENCE_ROOT = Path("data/pdp/retailer_filter_evidence")


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize Vince PDP site filters as retailer_filter attribute "
            "observations for parsed parent products."
        ),
    )
    add_pdp_store_path_argument(parser)
    parser.add_argument(
        "--categories",
        nargs="*",
        default=(VINCE_CATEGORY_KEY,),
        help="Category keys to materialize (default: low_top_sneakers).",
    )
    parser.add_argument(
        "--filter-families",
        nargs="*",
        default=None,
        help="Optional semantic filter/attribute families to keep.",
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
            raw_rows = conn.execute(query, (VINCE_RETAILER,)).fetchall()
    except Exception as exc:
        LOGGER.warning("Unable to load Vince parent rows: %s", exc)
        return rows

    for parent_id, pdp_url, raw_extras in raw_rows:
        extras = _parse_extras(raw_extras)
        category_key = str(extras.get("category_key") or VINCE_CATEGORY_KEY)
        category_key = category_key.strip().lower()
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


def _write_evidence(
    *,
    evidence_root: Path,
    crawl_ts: str,
    surfaces: Sequence[object],
    observations: Sequence[object],
    parent_count: int,
    materialized_attribute_rows: int,
) -> Path:
    run_dir = (
        evidence_root / VINCE_RETAILER / crawl_ts.replace(":", "").replace("+", "Z")
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
        "retailer": VINCE_RETAILER,
        "crawl_ts": crawl_ts,
        "parent_rows": parent_count,
        "surface_rows": len(surface_rows),
        "observation_rows": len(observation_rows),
        "materialized_attribute_rows": materialized_attribute_rows,
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return run_dir


def _require_postgres(pdp_store_path: Path) -> None:
    if not is_postgres_enabled():
        raise SystemExit(
            "PDP Postgres is not configured. Open the tunnel/load secrets first; "
            "this workflow does not use a local local PDP database fallback."
        )
    with connect_pdp_database(pdp_store_path) as conn:
        conn.execute("SELECT 1").fetchone()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    _configure_logging()
    load_env_from_secrets_file()
    pdp_store_path = enforce_default_pdp_store_path(args.pdp_store_path)
    _require_postgres(pdp_store_path)
    categories = canonical_category_keys(VINCE_RETAILER, args.categories)
    crawl_ts = args.crawl_ts or dt.datetime.now(dt.timezone.utc).isoformat()
    parents = _load_parent_rows(pdp_store_path, categories=categories)
    surfaces, observations = build_vince_filter_records(
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
    # Discovery captures full PLP filter memberships before PDP parsing; this
    # script adds PDP-derived memberships. Materialize the combined retailer /
    # category evidence so the cache gets the richer site filter coverage.
    materialized = store.materialize_retailer_filter_attributes(
        retailer=VINCE_RETAILER,
        category_key=VINCE_CATEGORY_KEY,
    )
    evidence_dir = _write_evidence(
        evidence_root=args.evidence_root,
        crawl_ts=crawl_ts,
        surfaces=surfaces,
        observations=observations,
        parent_count=len(parents),
        materialized_attribute_rows=materialized,
    )
    LOGGER.info(
        (
            "Materialized Vince filters: parents=%d surfaces=%d observations=%d "
            "attribute_rows=%d evidence=%s"
        ),
        len(parents),
        len(surfaces),
        len(observations),
        materialized,
        evidence_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
