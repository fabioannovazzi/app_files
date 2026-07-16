from __future__ import annotations

"""Delete raw outreach email addresses after hashes have been recorded."""

import argparse
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.outreach import scrub_raw_emails

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run the outreach email scrubber CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--files", required=True, nargs="+", type=Path)
    parser.add_argument(
        "--hash-salt-env",
        default="OUTREACH_HASH_SALT",
        help="Environment variable containing the stable hash salt used in prep.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    salt = os.environ.get(args.hash_salt_env, "")
    total_count = 0
    for path in args.files:
        scrubbed_count = scrub_raw_emails(path, ledger_path=args.ledger, salt=salt)
        total_count += scrubbed_count
        LOGGER.info("Deleted %s raw emails from %s", scrubbed_count, path)
    LOGGER.info("Deleted %s raw outreach emails", total_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
