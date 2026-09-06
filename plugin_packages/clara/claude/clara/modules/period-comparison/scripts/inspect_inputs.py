"""CLI entry point for period-comparison input inspection."""

from __future__ import annotations

# Direct CLI calls must select dependencies before importing workflow modules.
if __name__ == "__main__":
    import runpy as _runpy
    from pathlib import Path as _Path

    for _parent in _Path(__file__).resolve().parents:
        _launcher = _parent / "scripts" / "self_relaunch.py"
        if not _launcher.is_file():
            _launcher = _parent / "clara" / "scripts" / "self_relaunch.py"
        if _launcher.is_file():
            _runpy.run_path(str(_launcher))["ensure_running_in_managed_venv"](__file__)
            break
    else:
        # Standalone components retain their host's dependency setup.
        if any(
            (_p / "components.json").is_file()
            for _p in _Path(__file__).resolve().parents
        ):
            raise SystemExit(
                "Managed Python launcher is missing; rebuild the plugin package."
            )

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
