from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from apertura_pratica_core import ValidationError, apply_decisions


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply explicitly confirmed Apertura pratica review decisions."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("decisions", type=Path)
    parser.add_argument("--confirmed-by-user", action="store_true")
    args = parser.parse_args()
    try:
        receipts = apply_decisions(
            args.run_dir,
            args.decisions,
            confirmed_by_user=args.confirmed_by_user,
        )
    except ValidationError as exc:
        logging.error("%s", exc)
        return 2
    logging.info("%s", json.dumps(receipts, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
