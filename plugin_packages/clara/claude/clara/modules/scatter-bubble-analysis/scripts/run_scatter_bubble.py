"""CLI entry point for scatter and bubble chart generation."""

from __future__ import annotations

import argparse

from scatter_bubble_core import (
    add_common_args,
    configure_logging,
    default_output_dir,
    run_scatter_bubble,
)


def main() -> int:
    """Run the scatter-bubble workflow."""

    parser = argparse.ArgumentParser(description="Run scatter and bubble charts.")
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)
    run_scatter_bubble(
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
