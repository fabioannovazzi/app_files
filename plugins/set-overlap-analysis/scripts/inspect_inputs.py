"""CLI entry point for set-overlap input inspection."""

from __future__ import annotations

import argparse

from set_overlap_core import (
    add_common_args,
    configure_logging,
    inspect_set_overlap_inputs,
)


def main() -> int:
    """Inspect inputs and write a suggested set-overlap recipe."""

    parser = argparse.ArgumentParser(description="Inspect set-overlap inputs.")
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)
    inspect_set_overlap_inputs(
        args.input_file,
        args.output_dir,
        args.recipe,
        language=args.language,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
