"""Import a Clara update package into this local workspace."""

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

from advisor_case_core import import_case_update

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run deterministic append-only case-update import."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = import_case_update(args.case_dir, args.package)
    LOGGER.info("Imported exchange: %s", result.exchange_id)
    LOGGER.info(
        "Added %s material(s), %s evidence receipt(s), %s claim(s), updated %s claim(s), "
        "%s judgement entrie(s), %s open question(s), %s case issue(s); "
        "skipped %s duplicate(s); logged %s conflict(s).",
        result.imported_material_count,
        result.imported_evidence_count,
        result.imported_claim_count,
        result.updated_claim_count,
        result.imported_judgement_count,
        result.imported_open_question_count,
        result.imported_issue_count,
        result.skipped_count,
        result.conflict_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
