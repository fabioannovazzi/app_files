from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.face_mapping_pack import (
    DEFAULT_FACE_CATEGORIES,
    DEFAULT_OUTPUT_ROOT,
    build_face_mapping_review_pack,
    find_latest_face_export,
    find_latest_face_report_dir,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a face-mapping review package for the new Ulta face categories."
    )
    parser.add_argument(
        "--export-path",
        type=Path,
        default=None,
        help="Optional explicit parent export CSV. Defaults to the latest face patch export.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="Optional explicit Ulta face bridge report directory. Defaults to the latest one.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Root folder for generated face-mapping review packs.",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        default=list(DEFAULT_FACE_CATEGORIES),
        help="Category keys to include in the package.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    export_path = args.export_path or find_latest_face_export()
    report_dir = args.report_dir or find_latest_face_report_dir()
    output_dir = build_face_mapping_review_pack(
        export_path=export_path,
        report_dir=report_dir,
        output_root=args.output_root,
        categories=tuple(args.categories),
    )
    print(output_dir.resolve())


if __name__ == "__main__":
    main()
