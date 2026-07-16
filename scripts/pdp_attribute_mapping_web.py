from __future__ import annotations

"""Run only the website-search PDP attribute enrichment step."""

import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from modules.pdp.attribute_mapping_runner import run_attribute_mapping_web
from modules.utilities.secrets_loader import load_env_from_secrets_file


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run only the website-search PDP attribute enrichment step."
    )
    parser.add_argument(
        "--retailer",
        action="append",
        default=None,
        help=(
            "Limit enrichment to one retailer. Repeat to include multiple "
            "retailers. Other retailers are preserved in the shared output cache."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Run the web-search attribute mapper using the mapped PDP cache."""
    args = _parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    load_env_from_secrets_file()
    run_attribute_mapping_web(retailers=args.retailer)


if __name__ == "__main__":
    main()
