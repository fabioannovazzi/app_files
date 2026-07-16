"""Command-line entry point for deterministic statement tables."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from statement_core import run_statement_analysis

__all__ = ["main"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_file", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, default=None)
    parser.add_argument("--language", default="en", choices=("en", "it", "fr", "de"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the statement table generator."""

    args = parse_args(argv or sys.argv[1:])
    result = run_statement_analysis(
        args.source_file,
        args.output_dir,
        args.recipe,
        language=args.language,
    )
    payload = {
        "status": "ok",
        "html_path": str(result.html_path),
        "csv_path": str(result.csv_path),
        "context_path": str(result.context_path),
        "manifest_path": str(result.manifest_path),
        "row_count": len(result.rows),
    }
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

