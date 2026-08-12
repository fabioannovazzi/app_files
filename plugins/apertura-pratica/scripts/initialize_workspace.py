from __future__ import annotations

import argparse
import logging
from pathlib import Path

from apertura_pratica_core import ValidationError, initialize_workspace


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Initialize one Lucia matter-opening run."
    )
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--opening-mode",
        required=True,
        choices=("new_client_new_matter", "existing_client_new_matter"),
    )
    parser.add_argument("--client-reference", required=True)
    parser.add_argument("--matter-reference", required=True)
    parser.add_argument(
        "--language", default="it", choices=("it", "en", "fr", "de", "es")
    )
    args = parser.parse_args()
    try:
        root = initialize_workspace(
            args.output_dir,
            opening_mode=args.opening_mode,
            client_reference=args.client_reference,
            matter_reference=args.matter_reference,
            language=args.language,
        )
    except ValidationError as exc:
        logging.error("%s", exc)
        return 2
    logging.info("Initialized %s", root)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
