from __future__ import annotations

"""Build outreach queues from public registry or directory source pages."""

import argparse
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.outreach.lead_bank import build_lead_bank_from_sources, load_source_urls

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)

_REGION_COUNTRY_DEFAULTS = {
    "italy": "Italy",
    "spain": "Spain",
    "swiss-romande": "Switzerland",
    "swiss-german": "Switzerland",
    "uk": "United Kingdom",
}


def main() -> int:
    """Run source-first outreach lead-bank discovery."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--region",
        choices=sorted(_REGION_COUNTRY_DEFAULTS),
        help="Queue region. Used for default queue path and country.",
    )
    parser.add_argument(
        "--queue",
        type=Path,
        help="Queue CSV to append. Defaults to data/outreach/queues/<region>.csv.",
    )
    parser.add_argument(
        "--ledger",
        default=Path("data/outreach/outreach_ledger.jsonl"),
        type=Path,
    )
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="Public source URL to scrape. Repeat for multiple sources.",
    )
    parser.add_argument(
        "--url-file",
        action="append",
        default=[],
        type=Path,
        help="Newline-delimited public source URLs to scrape.",
    )
    parser.add_argument(
        "--country",
        default="",
        help="Country label for appended queue rows. Defaults from --region.",
    )
    parser.add_argument("--city", default="", help="Optional city/area label.")
    parser.add_argument(
        "--source-note",
        default="public-directory",
        help="Source note stored with appended rows.",
    )
    parser.add_argument(
        "--use-playwright",
        action="store_true",
        help="Render pages in Chromium before extracting emails.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument(
        "--hash-salt-env",
        default="OUTREACH_HASH_SALT",
        help="Environment variable containing the stable hash salt.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    source_urls = _source_urls_from_args(args.url, args.url_file)
    if not source_urls:
        parser.error("at least one --url or --url-file is required")
    if args.queue is None and not args.region:
        parser.error("--region is required when --queue is omitted")
    if not args.country and not args.region:
        parser.error("--country is required when --region is omitted")
    queue_path = _queue_path(args.queue, args.region)
    country = args.country or _country_for_region(args.region)
    appended_count = build_lead_bank_from_sources(
        source_urls,
        queue_path=queue_path,
        ledger_path=args.ledger,
        country=country,
        city=args.city,
        source_note=args.source_note,
        use_playwright=args.use_playwright,
        timeout_seconds=args.timeout_seconds,
        salt=os.environ.get(args.hash_salt_env, ""),
    )
    LOGGER.info("Appended %s new leads to %s", appended_count, queue_path)
    return 0


def _source_urls_from_args(urls: list[str], url_files: list[Path]) -> tuple[str, ...]:
    source_urls = [url.strip() for url in urls if url.strip()]
    for path in url_files:
        source_urls.extend(load_source_urls(path))
    return tuple(dict.fromkeys(source_urls))


def _queue_path(queue: Path | None, region: str | None) -> Path:
    if queue is not None:
        return queue
    assert region is not None
    return Path("data/outreach/queues") / f"{region}.csv"


def _country_for_region(region: str | None) -> str:
    assert region is not None
    return _REGION_COUNTRY_DEFAULTS[region]


if __name__ == "__main__":
    raise SystemExit(main())
