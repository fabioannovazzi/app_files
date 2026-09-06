"""Prepare and audit the PPTX base used by editable slide merging."""

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
from pathlib import Path

from advisor_case_core import prepare_editable_pptx_merge_input

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run editable PPTX merge-input preflight."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_pptx", type=Path)
    parser.add_argument(
        "--normalized-pptx",
        type=Path,
        help="Normalized PPTX merge base. Defaults to an existing *_normalized_for_merge.pptx sibling when present.",
    )
    parser.add_argument(
        "--skip-normalization-reason",
        help="Required when using a legacy WMF/EMF source without a normalized merge base.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="JSON merge-input report path. Defaults next to the selected merge base.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = prepare_editable_pptx_merge_input(
        args.source_pptx,
        normalized_path=args.normalized_pptx,
        skip_normalization_reason=args.skip_normalization_reason,
        report_path=args.report,
    )

    LOGGER.info("Editable merge base: %s", result.merge_base_path)
    LOGGER.info("Merge-input status: %s", result.status)
    LOGGER.info("Merge-input report: %s", result.report_path)
    if result.merge_base_legacy_media:
        LOGGER.warning(
            "Merge base still has %s legacy WMF/EMF media part(s).",
            len(result.merge_base_legacy_media),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
