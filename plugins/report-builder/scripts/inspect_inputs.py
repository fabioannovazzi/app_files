"""Inspect financial report inputs for the Build Report Codex plugin."""

from __future__ import annotations

import argparse

from report_builder_core import add_common_args, configure_logging, inspect_inputs


def main() -> int:
    """Run deterministic input inspection."""

    parser = argparse.ArgumentParser(
        description="Inspect report input files and write inspection.json plus suggested_recipe.json."
    )
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)
    result = inspect_inputs(
        args.input_path,
        args.output_dir,
        language=args.language,
        document_language=args.document_language,
        report_type=args.report_type,
    )
    print(
        "OK: inspected "
        f"{result.inspection['table_count']} tables; "
        f"wrote {args.output_dir / 'inspection.json'} and "
        f"{args.output_dir / 'suggested_recipe.json'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
