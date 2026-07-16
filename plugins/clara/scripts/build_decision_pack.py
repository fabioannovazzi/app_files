"""Build decision-pack outputs from client-pack-ready judgement."""

from __future__ import annotations

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
