"""Inspect candidate input data for scatter and bubble chart generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from scatter_bubble_core import (
    SCHEMA_VERSION,
    available_analysis_context,
    build_recipe,
    default_output_dir,
    read_table,
    write_json,
)
from modules.utilities.helpers import get_schema_and_column_names


def main() -> int:
    """Write inferred mappings for a candidate input file."""

    parser = argparse.ArgumentParser(description="Inspect scatter/bubble inputs.")
    parser.add_argument("input_file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--language", default="en")
    args = parser.parse_args()

    frame = read_table(args.input_file)
    recipe = build_recipe(args.input_file, frame, language=args.language)
    columns, schema = get_schema_and_column_names(frame)
    inspection = {
        "schema_version": SCHEMA_VERSION,
        "input_file": str(args.input_file),
        "row_count": frame.height,
        "column_count": frame.width,
        "columns": columns,
        "schema": schema,
        "available_analysis_context": available_analysis_context(frame),
        "suggested_mappings": recipe["mappings"],
        "suggested_options": recipe["options"],
    }
    output_dir = args.output_dir or default_output_dir(args.input_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "inspection.json", inspection)
    write_json(output_dir / "suggested_recipe.json", recipe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
