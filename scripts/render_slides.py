from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.slides.pptx_rasterizer import rasterize_presentation_to_pngs

LOGGER = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render a PPTX or PDF into per-slide PNG files. "
            "When Linux LibreOffice is unavailable under WSL, the renderer falls back "
            "to a Windows LibreOffice installation automatically."
        )
    )
    parser.add_argument("input_path", help="Path to the PPTX or PDF to rasterize.")
    parser.add_argument(
        "--output-dir",
        help=(
            "Directory for the rendered PNG files. Defaults to a sibling directory "
            "named '<input-stem>_rendered'."
        ),
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=1600,
        help="Maximum rasterized image width in pixels (default: 1600).",
    )
    parser.add_argument(
        "--max-height",
        type=int,
        default=900,
        help="Maximum rasterized image height in pixels (default: 900).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    input_path = Path(args.input_path).expanduser().resolve()
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else input_path.parent / f"{input_path.stem}_rendered"
    )
    image_paths = rasterize_presentation_to_pngs(
        input_path,
        output_dir,
        max_width_px=args.max_width,
        max_height_px=args.max_height,
    )
    LOGGER.info(
        "Rendered %s slide image(s) from %s into %s",
        len(image_paths),
        input_path,
        output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
