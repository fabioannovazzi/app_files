"""Build report artifacts for the Build Report Codex plugin."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_builder_core import add_common_args, build_report, configure_logging


def main() -> int:
    """Run deterministic report rendering."""

    parser = argparse.ArgumentParser(
        description="Build report_analysis.json, report_draft.md, report.docx, and audit outputs."
    )
    add_common_args(parser)
    parser.add_argument(
        "--recipe",
        type=Path,
        default=None,
        help="Editable recipe JSON produced by inspect_inputs.py.",
    )
    args = parser.parse_args()
    configure_logging(args.verbose)
    result = build_report(
        args.input_path,
        args.output_dir,
        recipe_path=args.recipe,
        language=args.language,
        document_language=args.document_language,
        report_type=args.report_type,
    )
    print(
        "OK: built report draft; "
        f"Markdown={result.markdown_path} DOCX={result.docx_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
