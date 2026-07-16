"""CLI entry point for deterministic Venn and UpSet chart generation."""

from __future__ import annotations

import argparse

from set_overlap_core import add_common_args, configure_logging, run_set_overlap


def main() -> int:
    """Run set-overlap analysis."""

    parser = argparse.ArgumentParser(description="Run set-overlap charts.")
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)
    run_set_overlap(
        args.input_file,
        args.output_dir,
        args.recipe,
        language=args.language,
        artifact_mode=args.artifact_mode,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
