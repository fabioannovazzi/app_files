"""CLI entry point for mix-contribution chart generation."""

from __future__ import annotations

import argparse

from mix_core import add_common_args, configure_logging, run_mix_contribution


def main() -> int:
    """Run the mix-contribution workflow."""

    parser = argparse.ArgumentParser(description="Run mix-contribution charts.")
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)
    run_mix_contribution(
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
