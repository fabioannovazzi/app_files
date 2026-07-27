"""CLI entry point for distribution input inspection."""

from __future__ import annotations

import argparse

from distribution_core import (
    add_common_args,
    configure_logging,
    default_output_dir,
    inspect_distribution_inputs,
)


def main() -> int:
    """Inspect inputs and write a suggested distribution recipe."""

    parser = argparse.ArgumentParser(description="Inspect distribution inputs.")
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)
    inspect_distribution_inputs(
        args.input_file,
        args.output_dir or default_output_dir(args.input_file),
        args.recipe,
        language=args.language,
        currency=args.currency,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
