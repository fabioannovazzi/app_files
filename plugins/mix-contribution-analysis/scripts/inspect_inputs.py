"""CLI entry point for mix-contribution input inspection."""

from __future__ import annotations

import argparse

from mix_core import add_common_args, configure_logging, inspect_mix_inputs


def main() -> int:
    """Run inspection."""

    parser = argparse.ArgumentParser(description="Inspect mix-contribution inputs.")
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)
    inspect_mix_inputs(
        args.input_file,
        args.output_dir,
        language=args.language,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
