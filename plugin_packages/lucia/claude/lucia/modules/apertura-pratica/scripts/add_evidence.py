from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from apertura_pratica_core import ValidationError, add_evidence


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Snapshot one evidence file into an Apertura pratica run."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("--role", required=True)
    args = parser.parse_args()
    try:
        record = add_evidence(args.run_dir, args.source, role=args.role)
    except ValidationError as exc:
        logging.error("%s", exc)
        return 2
    logging.info("%s", json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
