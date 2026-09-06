"""CLI entry point for scatter and bubble chart generation."""

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
