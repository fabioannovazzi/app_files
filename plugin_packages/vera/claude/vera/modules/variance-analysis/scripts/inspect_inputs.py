"""Inspect a sales variance CSV/XLSX file and suggest deterministic mappings."""

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

from variance_core import (
    add_common_args,
    configure_logging,
    inspect_variance_inputs,
    is_vera_managed_host,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent.parent / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        if str(_vendor_root) not in sys.path:
            sys.path.insert(0, str(_vendor_root))
        break

from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run variance input inspection."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", type=Path, help="CSV/XLSX sales file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Folder where inspection.json and suggested_recipe.json will be written.",
    )
    parser.add_argument("--recipe", type=Path, help="Optional existing recipe JSON.")
    parser.add_argument(
        "--client-engagement",
        type=Path,
        required=False,
        help=(
            "Optional absolute Studio Archive context.json. Vera requires it; "
            "standalone and Clara runs may omit it."
        ),
    )
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)

    if is_vera_managed_host() and args.client_engagement is None:
        parser.error("--client-engagement is required by the Vera packaged inspector")
    client_engagement = None
    if args.client_engagement is not None:
        input_paths = [args.input_file]
        if args.recipe is not None:
            input_paths.append(args.recipe)
        try:
            client_engagement = load_client_engagement_context_file(
                args.client_engagement,
                expected_workflow_id="variance-analysis",
                input_paths=input_paths,
                output_dir=args.output_dir,
            )
        except AssuranceContractError as exc:
            parser.error(str(exc))

    result = inspect_variance_inputs(
        args.input_file,
        args.output_dir,
        args.recipe,
        language=args.language,
        client_engagement=client_engagement,
    )
    LOGGER.info("input_rows=%s", result.payload["row_count"])
    LOGGER.info("warnings=%s", len(result.payload["warnings"]))
    LOGGER.info("wrote %s", args.output_dir / "inspection.json")
    LOGGER.info("wrote %s", args.output_dir / "suggested_recipe.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
