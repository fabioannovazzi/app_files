"""Validate Claude mapping decisions against a pinned taxonomy snapshot."""

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

from attribute_reporting import ContractError, validate_mapping_decisions

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Validate and normalize mapping decisions."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", type=Path)
    parser.add_argument("decisions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = validate_mapping_decisions(args.tasks, args.decisions, args.output)
    except ContractError as exc:
        LOGGER.error("Mapping validation failed: %s", exc)
        return 1
    LOGGER.info("Validated %s Claude mapping decisions", result["mapping_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
