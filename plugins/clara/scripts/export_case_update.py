"""Export a Clara update package for another local workspace."""

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

from advisor_case_core import export_case_update

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run deterministic case-update export."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--exporter", default="")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = export_case_update(
        args.case_dir,
        package_path=args.out,
        exporter=args.exporter,
    )
    LOGGER.info("Exported case update: %s", result.package_path)
    LOGGER.info(
        "Included %s material(s), %s evidence receipt(s), %s claim(s), "
        "%s judgement entrie(s), %s open question(s), %s case issue(s), "
        "%s file(s).",
        result.material_count,
        result.evidence_count,
        result.claim_count,
        result.judgement_count,
        result.open_question_count,
        result.issue_count,
        result.included_file_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
