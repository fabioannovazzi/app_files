#!/usr/bin/env python3
"""Check dependencies and bundled assets for professional communications."""

from __future__ import annotations

import argparse
import importlib.util
import logging
from pathlib import Path

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_IMPORTS = {
    "jsonschema": "jsonschema",
    "Pillow": "PIL",
    "reportlab": "reportlab",
    "pypdf": "pypdf",
    "fonttools": "fontTools",
}
REQUIRED_FONTS = (
    "InstrumentSans-Regular.ttf",
    "InstrumentSans-SemiBold.ttf",
    "InstrumentSans-Bold.ttf",
)


def main(argv: list[str] | None = None) -> int:
    """Return non-zero when a declared dependency or asset is unavailable."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        type=Path,
        default=PLUGIN_ROOT / "requirements.txt",
    )
    args = parser.parse_args(argv)
    if not args.requirements.is_file():
        LOGGER.error("MISSING_REQUIREMENTS_FILE: %s", args.requirements)
        return 1

    missing = [
        package
        for package, module in REQUIRED_IMPORTS.items()
        if importlib.util.find_spec(module) is None
    ]
    font_root = PLUGIN_ROOT / "assets" / "fonts"
    missing_fonts = [
        name for name in REQUIRED_FONTS if not (font_root / name).is_file()
    ]
    invalid_fonts: list[str] = []
    if "fonttools" not in missing:
        from fontTools.ttLib import TTFont

        required_characters = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzàèéìòù€→"
        )
        for name in REQUIRED_FONTS:
            path = font_root / name
            if not path.is_file():
                continue
            try:
                font = TTFont(path, lazy=True)
                cmap = font.getBestCmap() or {}
                if any(ord(character) not in cmap for character in required_characters):
                    invalid_fonts.append(name)
                font.close()
            except (OSError, ValueError):
                invalid_fonts.append(name)
    if missing or missing_fonts or invalid_fonts:
        for package in missing:
            LOGGER.error("MISSING_DEPENDENCY: %s", package)
        for font in missing_fonts:
            LOGGER.error("MISSING_ASSET: assets/fonts/%s", font)
        for font in invalid_fonts:
            LOGGER.error("INVALID_FONT_ASSET: assets/fonts/%s", font)
        return 1

    LOGGER.info("OK: dependencies and bundled visual assets are available")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
