"""Normalize legacy WMF/EMF-heavy PPTX decks before editable slide merging."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from advisor_case_core import normalize_legacy_pptx_for_editable_merge

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run legacy PPTX normalization."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_pptx", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="Normalized PPTX path. Defaults to *_normalized_for_merge.pptx next to the source.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="JSON normalization report path. Defaults next to the output deck.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run the LibreOffice round-trip even when no WMF/EMF media are detected.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output path.",
    )
    parser.add_argument(
        "--soffice",
        type=Path,
        help="LibreOffice soffice binary. Defaults to SOFFICE_BINARY, PATH, or common install paths.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = normalize_legacy_pptx_for_editable_merge(
        args.source_pptx,
        output_path=args.output,
        report_path=args.report,
        force=args.force,
        overwrite=args.overwrite,
        soffice_binary=args.soffice,
    )

    action = "Normalized" if result.normalized else "Copied clean"
    LOGGER.info("%s PPTX: %s", action, result.output_path)
    LOGGER.info(
        "Legacy media: %s before, %s after.",
        len(result.legacy_media_before),
        len(result.legacy_media_after),
    )
    if result.legacy_media_after:
        LOGGER.warning(
            "Legacy WMF/EMF media remain; use image fallback for affected slides."
        )
    LOGGER.info("Normalization report: %s", result.report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
