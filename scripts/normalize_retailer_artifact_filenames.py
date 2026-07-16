from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

LOGGER = logging.getLogger(__name__)

DEFAULT_ROOTS = (
    Path("data/pdp/discovery_runs/cdp"),
    Path("data/pdp/discovery_runs/ulta"),
    Path("data/pdp/discovery_runs/kiko_filters"),
    Path("data/pdp/retailer_filter_evidence"),
)
FILENAME_MIGRATIONS = {
    "listing_observations.csv": "retailer_listing_observations.csv",
    "classification.csv": "retailer_listing_classification.csv",
    "filter_surfaces.csv": "retailer_filter_surfaces.csv",
    "filter_observations.csv": "retailer_filter_observations.csv",
    "sitemap_observations.csv": "retailer_sitemap_observations.csv",
    "sitemap_missing_products.csv": "retailer_sitemap_missing_products.csv",
}

__all__ = ["main"]


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rename retailer discovery CSV artifacts to canonical filenames."
    )
    parser.add_argument(
        "--roots",
        nargs="*",
        type=Path,
        default=list(DEFAULT_ROOTS),
        help="Roots to scan for legacy retailer discovery CSV names.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned changes without renaming files.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _rename_file(source: Path, target: Path, *, dry_run: bool) -> str:
    if not target.exists():
        if dry_run:
            return "would_rename"
        source.replace(target)
        return "renamed"

    if source.read_bytes() == target.read_bytes():
        if dry_run:
            return "would_remove_duplicate"
        source.unlink()
        return "removed_duplicate"

    return "conflict"


def _normalize_root(root: Path, *, dry_run: bool) -> dict[str, int]:
    counts = {
        "renamed": 0,
        "removed_duplicate": 0,
        "conflict": 0,
        "would_rename": 0,
        "would_remove_duplicate": 0,
    }
    if not root.is_dir():
        return counts

    for legacy_name, canonical_name in FILENAME_MIGRATIONS.items():
        for source in sorted(root.rglob(legacy_name)):
            target = source.with_name(canonical_name)
            result = _rename_file(source, target, dry_run=dry_run)
            counts[result] += 1
            if result == "conflict":
                LOGGER.warning(
                    "Cannot rename %s because %s exists with different content.",
                    source,
                    target,
                )
            else:
                LOGGER.info("%s: %s -> %s", result, source, target.name)
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    total = {
        "renamed": 0,
        "removed_duplicate": 0,
        "conflict": 0,
        "would_rename": 0,
        "would_remove_duplicate": 0,
    }
    for root in args.roots:
        counts = _normalize_root(root, dry_run=bool(args.dry_run))
        for key, value in counts.items():
            total[key] += value
    LOGGER.info("Retailer artifact filename normalization complete: %s", total)
    return 1 if total["conflict"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
