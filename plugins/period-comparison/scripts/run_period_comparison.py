"""CLI entry point for period-comparison chart generation."""

from __future__ import annotations

import argparse

from period_core import add_common_args, configure_logging, run_period_comparison


def main() -> int:
    """Run the period-comparison workflow."""

    parser = argparse.ArgumentParser(description="Run period-comparison charts.")
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)
    run_period_comparison(
        args.input_file,
        args.output_dir,
        args.recipe,
        language=args.language,
        currency=args.currency,
        artifact_mode=args.artifact_mode,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
