"""Delete Clara material records and scrub canonical source references."""

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
import json
import logging
from pathlib import Path

from advisor_case_core import MaterialDeleteResult, delete_materials

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _result_summary(result: MaterialDeleteResult) -> dict[str, object]:
    return {
        "removed_material_ids": list(result.removed_material_ids),
        "missing_material_ids": list(result.missing_material_ids),
        "removed_material_paths": [str(path) for path in result.removed_material_paths],
        "updated_judgement_ids": list(result.updated_judgement_ids),
        "unanchored_judgement_ids": list(result.unanchored_judgement_ids),
        "removed_mandate_source_material_ids": list(
            result.removed_mandate_source_material_ids
        ),
        "removed_mandate_voice_session_paths": list(
            result.removed_mandate_voice_session_paths
        ),
        "removed_preparation_material_anchor_ids": list(
            result.removed_preparation_material_anchor_ids
        ),
        "orphan_candidate_paths": [str(path) for path in result.orphan_candidate_paths],
        "removed_empty_orphan_dirs": [
            str(path) for path in result.removed_empty_orphan_dirs
        ],
        "brief_path": str(result.brief_path),
    }


def main() -> int:
    """Run material deletion."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("material_ids", nargs="+")
    parser.add_argument(
        "--ignore-missing",
        action="store_true",
        help="Do not fail when one of the requested material IDs is absent.",
    )
    parser.add_argument(
        "--remove-empty-orphan-dirs",
        action="store_true",
        help=(
            "Remove empty case-owned orphan directories reported after deletion. "
            "Files and non-empty directories are never deleted."
        ),
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = delete_materials(
        args.case_dir,
        args.material_ids,
        ignore_missing=args.ignore_missing,
        remove_empty_orphan_dirs=args.remove_empty_orphan_dirs,
    )
    LOGGER.info(json.dumps(_result_summary(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
