"""Build decision-pack outputs from client-pack-ready judgement."""

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

from advisor_case_core import build_decision_pack

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run decision-pack rendering."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = build_decision_pack(args.case_dir, output_dir=args.output_dir)
    LOGGER.info(
        "Decision pack built: Markdown=%s DOCX=%s Workpaper=%s ready=%s pending_excluded=%s",
        result.markdown_path,
        result.docx_path,
        result.workpaper_markdown_path,
        result.approved_count,
        result.pending_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
