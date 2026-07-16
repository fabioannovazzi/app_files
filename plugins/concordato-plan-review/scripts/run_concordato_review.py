from __future__ import annotations

import argparse
from pathlib import Path

from concordato_plan_core import configure_logging, run_concordato_review


def main() -> int:
    """Run the concordato plan deterministic review helper."""

    parser = argparse.ArgumentParser(
        description="Inspect a concordato plan folder and prepare tie-out workpapers."
    )
    parser.add_argument("input_dir", type=Path, help="Folder containing plan sources.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Folder where review artifacts will be written.",
    )
    parser.add_argument(
        "--reference-date",
        default="",
        help="Reference date or cut-off, for example 2026-03-31.",
    )
    parser.add_argument("--language", default="it", help="Working language.")
    parser.add_argument(
        "--document-language",
        default="auto",
        help="Source document language, or auto.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1.0,
        help="Maximum absolute difference for candidate amount matches.",
    )
    parser.add_argument(
        "--max-rows-per-sheet",
        type=int,
        default=5000,
        help="Maximum rows to scan in each workbook sheet.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    configure_logging(args.verbose)
    run = run_concordato_review(
        args.input_dir,
        args.output_dir,
        reference_date=args.reference_date,
        language=args.language,
        document_language=args.document_language,
        tolerance=args.tolerance,
        max_rows_per_sheet=args.max_rows_per_sheet,
    )
    print(f"OK: wrote review artifacts to {run.output_dir}")
    print(f"Files inspected: {len(run.inventory)}")
    print(f"Amount candidates: {len(run.amount_candidates)}")
    print(f"Candidate matches: {len(run.exact_matches)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
