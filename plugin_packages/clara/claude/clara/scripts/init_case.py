"""Initialize a Clara case folder."""

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

from advisor_case_core import initialize_case

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run case initialization."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--client", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--audience", default="Decision maker")
    parser.add_argument(
        "--language", default="it", choices=["it", "en", "fr", "de", "es"]
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    initialize_case(
        args.case_dir,
        client=args.client,
        project=args.project,
        objective=args.objective,
        audience=args.audience,
        output_language=args.language,
        overwrite=args.overwrite,
    )
    LOGGER.info("Case workspace ready: %s", args.case_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
