from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.attribute_mapping_paths import get_attribute_mapping_dir  # noqa: E402
from modules.pdp.review_constants import add_pdp_store_path_argument  # noqa: E402
from modules.pdp.ulta_filter_reports import (  # noqa: E402
    build_brand_filter_comparison,
    compute_double_matching_summary,
    latest_ulta_filter_crawl_ts,
    load_parent_mapping_frame,
    load_ulta_filter_observations,
    summarize_brand_filter_comparison,
)
from modules.utilities.secrets_loader import load_env_from_secrets_file  # noqa: E402

DEFAULT_PARENTS_PARQUET = Path(
    get_attribute_mapping_dir() / "postfill_attribute_cache" / "parents.parquet"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Ulta filter reports from persisted discovery observations."
    )
    add_pdp_store_path_argument(parser)
    parser.add_argument(
        "--parents-parquet",
        type=Path,
        default=DEFAULT_PARENTS_PARQUET,
        help="Parent mapping parquet to compare against.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where report artifacts will be written.",
    )
    parser.add_argument(
        "--crawl-ts",
        default=None,
        help="Specific crawl timestamp to report. Defaults to the latest one in the PDP store.",
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        default=None,
        help="Optional category keys to limit the report.",
    )
    parser.add_argument(
        "--brand-contains",
        default="kiko",
        help="Brand substring for the comparison report (default: kiko).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    load_env_from_secrets_file()
    crawl_ts = args.crawl_ts or latest_ulta_filter_crawl_ts(args.pdp_store_path)
    if not crawl_ts:
        raise SystemExit(
            "No retailer_filter_observations found for Ulta in the requested PDP store."
        )

    category_keys = tuple(args.categories) if args.categories else None
    filter_df = load_ulta_filter_observations(
        args.pdp_store_path,
        crawl_ts=crawl_ts,
        category_keys=category_keys,
    )
    parents_df = load_parent_mapping_frame(
        args.parents_parquet,
        retailer="ulta",
        brand_contains=args.brand_contains,
        category_keys=category_keys,
    )

    double_matching = compute_double_matching_summary(filter_df)
    comparison = build_brand_filter_comparison(
        filter_df=filter_df,
        parents_df=parents_df,
    )
    comparison_summary = summarize_brand_filter_comparison(comparison)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    filter_df.write_csv(args.output_dir / "retailer_filter_observations_latest.csv")
    double_matching.write_csv(args.output_dir / "double_matching_summary.csv")
    comparison.write_csv(args.output_dir / "brand_filter_comparison.csv")
    comparison_summary.write_csv(
        args.output_dir / "brand_filter_comparison_summary.csv"
    )

    summary = {
        "crawl_ts": crawl_ts,
        "category_keys": list(category_keys or []),
        "brand_contains": args.brand_contains,
        "filter_rows": filter_df.height,
        "double_matching_rows": double_matching.height,
        "comparison_rows": comparison.height,
    }
    (args.output_dir / "report_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
