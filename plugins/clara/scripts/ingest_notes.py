"""Ingest pasted consultant notes into a case workspace."""

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

from advisor_case_core import ingest_note_file, ingest_note_text

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run note ingestion."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--title", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="Pasted note text.")
    source.add_argument("--notes-file", type=Path, help="Existing notes file to index.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.text is not None:
        material = ingest_note_text(args.case_dir, title=args.title, text=args.text)
    else:
        material = ingest_note_file(
            args.case_dir,
            title=args.title,
            notes_file=args.notes_file,
        )
    LOGGER.info("Note registered as %s.", material["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
