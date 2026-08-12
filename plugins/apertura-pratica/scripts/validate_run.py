from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from apertura_pratica_core import ValidationError, validate_run, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one Apertura pratica run.")
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    try:
        report = validate_run(args.run_dir)
        write_json(args.run_dir / "validation_report.json", report)
    except ValidationError as exc:
        logging.error("%s", exc)
        return 2
    logging.info("%s", json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] in {"ready_for_review", "ready_to_open"} else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
