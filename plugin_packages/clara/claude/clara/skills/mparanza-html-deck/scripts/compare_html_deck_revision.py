#!/usr/bin/env python3
"""Compare Clara HTML decks and reject changes outside a revision map."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from html_deck_revision import (
    compare_deck_revision,
    inspect_deck,
    load_json_object,
    render_json,
    write_json_report,
)

__all__ = ["main"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--revision-map", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        before = inspect_deck(args.before)
        after = inspect_deck(args.after)
        payload = load_json_object(args.revision_map)
        report = compare_deck_revision(before, after, payload)
        if args.report:
            write_json_report(args.report, report)
        sys.stdout.write(render_json(report))
        return 0 if report["result"] == "pass" else 1
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
