"""CLI entry point for distribution chart generation."""

from __future__ import annotations

import argparse

from distribution_core import (
    add_common_args,
    configure_logging,
    default_output_dir,
    run_distribution,
)


def main() -> int:
    """Run the distribution workflow."""

    parser = argparse.ArgumentParser(description="Run legacy distribution charts.")
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)
    run_distribution(
        args.input_file,
        args.output_dir or default_output_dir(args.input_file),
        args.recipe,
        language=args.language,
        currency=args.currency,
        artifact_mode=args.artifact_mode,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
