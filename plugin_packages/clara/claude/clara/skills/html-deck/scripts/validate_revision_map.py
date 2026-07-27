#!/usr/bin/env python3
"""Validate a preservation-aware revision map against a Clara HTML baseline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from html_deck_revision import (
    inspect_deck,
    load_json_object,
    render_json,
    validate_revision_map,
    write_json_report,
)

__all__ = ["main"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("revision_map", type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        baseline = inspect_deck(args.baseline)
        payload = load_json_object(args.revision_map)
        report = validate_revision_map(payload, baseline)
        if args.report:
            write_json_report(args.report, report)
        sys.stdout.write(render_json(report))
        return 0 if report["result"] == "pass" else 1
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
