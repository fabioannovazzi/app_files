"""Build Clara's budget report using the shared management-control calculation core."""

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

__all__ = ["main"]

CLARA_ROOT = Path(__file__).resolve().parents[3]
COMPONENT = next(
    (
        candidate
        for candidate in (
            CLARA_ROOT / "modules/management-control-pack",
            CLARA_ROOT.parent / "management-control-pack",
        )
        if candidate.is_dir()
    ),
    CLARA_ROOT / "modules/management-control-pack",
)
sys.path.insert(0, str(COMPONENT / "scripts"))
for _vendor in (
    COMPONENT / "vendor/modules",
    CLARA_ROOT.parent / "_shared/vendor/modules",
):
    if (_vendor / "reporting_table.py").is_file():
        sys.path.insert(0, str(_vendor))
        break

from management_control_core import (  # noqa: E402
    build_inspection,
    build_management_pack,
    load_json,
    load_source_tables,
    write_json,
)
from management_delivery import write_pack_outputs  # noqa: E402
from management_site import prepare_site  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Inspect, calculate or prepare a reviewed report without a Vera client binding."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "run", "site"))
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--recipe", type=Path)
    parser.add_argument("--pack", type=Path)
    parser.add_argument("--commentary", type=Path)
    parser.add_argument("--audience")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output_dir.exists():
            raise ValueError(
                "Use a fresh report output folder; preserve earlier reports."
            )
        if args.action == "inspect":
            inspection, controls, template = build_inspection(
                load_source_tables(args.input)
            )
            args.output_dir.mkdir(parents=True)
            write_json(args.output_dir / "inspection.json", inspection)
            write_json(args.output_dir / "mapping_control.json", controls)
            write_json(args.output_dir / "recipe_template.json", template)
        elif args.recipe is None:
            raise ValueError("A reviewed --recipe is required.")
        elif args.action == "run":
            pack = build_management_pack(
                load_source_tables(args.input), load_json(args.recipe)
            )
            write_pack_outputs(
                pack,
                inputs=args.input,
                recipe_path=args.recipe,
                output_dir=args.output_dir,
            )
            return 2 if pack["status"] == "blocked" else 0
        elif args.pack is None or args.audience is None:
            raise ValueError("Sites preparation requires --pack and --audience.")
        else:
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
        "Wrote budget report artifacts: %s", args.output_dir
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
