from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from apertura_pratica_core import ValidationError, prepare_review


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the Lucia legal matter-opening review package."
    )
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    try:
        result = prepare_review(args.run_dir)
    except ValidationError as exc:
        logging.error("%s", exc)
        return 2
    logging.info("%s", json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
