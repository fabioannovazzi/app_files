"""Copy a downloaded or local file into the right Clara case folder."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from advisor_case_core import CASE_FILE_KINDS, MATERIAL_TYPES, copy_case_file

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run case-file copy and optional material registration."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("source_file", type=Path)
    parser.add_argument(
        "--kind",
        default="auto",
        choices=sorted(CASE_FILE_KINDS),
        help="Routing hint. Auto infers from extension and filename.",
    )
    parser.add_argument(
        "--register",
        action="store_true",
        help="Register the copied file in material_registry.json.",
    )
    parser.add_argument(
        "--title",
        help="Material title to use when --register is set.",
    )
    parser.add_argument(
        "--material-type",
        choices=sorted(MATERIAL_TYPES),
        help="Material type override to use when --register is set.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing destination file with the same name.",
    )
    parser.add_argument(
        "--skip-legacy-pptx-normalization",
        action="store_true",
        help="Do not auto-create a normalized merge-ready sibling for WMF/EMF-heavy PPTX presentation files.",
    )
    parser.add_argument(
        "--soffice",
        type=Path,
        help="LibreOffice soffice binary for legacy PPTX normalization.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = copy_case_file(
        args.case_dir,
        args.source_file,
        kind=args.kind,
        register=args.register,
        title=args.title,
        material_type=args.material_type,
        overwrite=args.overwrite,
        normalize_legacy_pptx=not args.skip_legacy_pptx_normalization,
        soffice_binary=args.soffice,
    )

    action = "Copied" if result.copied else "Already present"
    LOGGER.info("%s %s file to %s.", action, result.kind, result.destination_path)
    if result.registered_material is not None:
        LOGGER.info(
            "Registered material %s.",
            result.registered_material["id"],
        )
    if result.legacy_pptx_normalization is not None:
        normalization = result.legacy_pptx_normalization
        LOGGER.info(
            "Normalized legacy PPTX for editable merge: %s.",
            normalization.output_path,
        )
        LOGGER.info("Normalization report: %s.", normalization.report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
