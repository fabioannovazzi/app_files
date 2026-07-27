"""CLI entry point for period-comparison input inspection."""

from __future__ import annotations

import argparse

from period_core import (
    add_common_args,
    configure_logging,
    inspect_period_comparison_inputs,
)


def main() -> int:
    """Run inspection."""

    parser = argparse.ArgumentParser(description="Inspect period-comparison inputs.")
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)
    inspect_period_comparison_inputs(
        args.input_file,
        args.output_dir,
        language=args.language,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
