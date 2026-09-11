#!/usr/bin/env python3
"""Prepare a source-verified budgeting report for host-managed Sites publication."""

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
import logging
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPTS_DIR.parent
for _vendor_root in (
    PLUGIN_ROOT / "vendor/modules",
    PLUGIN_ROOT.parent / "_shared/vendor/modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        sys.path.insert(0, str(_vendor_root))
        break

from management_control_core import load_json  # noqa: E402
from management_site import prepare_site  # noqa: E402
from vera_assurance import load_client_engagement_context_file  # noqa: E402

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Check client scope and prepare the exact report for its declared audience."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--commentary", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audience", required=True)
    parser.add_argument("--client-engagement", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="management-control-pack",
            input_paths=[
                *args.input,
                args.recipe,
                args.pack,
                *([args.commentary] if args.commentary else []),
            ],
            output_dir=args.output_dir,
        )
        prepare_site(
            inputs=args.input,
            recipe=load_json(args.recipe),
            pack=load_json(args.pack),
            output=args.output_dir,
            audience=args.audience,
            commentary=load_json(args.commentary) if args.commentary else None,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    logging.getLogger(__name__).info(
        "Prepared the report for Sites: %s", args.output_dir
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
