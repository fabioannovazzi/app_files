#!/usr/bin/env python3
"""Check declared Bilancio XBRL Italia runtime dependencies."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import re
import sys
from pathlib import Path

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
REQUIRED = {
    "arelle-release": "arelle",
    "defusedxml": "defusedxml",
    "lxml": "lxml",
    "openpyxl": "openpyxl",
    "pdfplumber": "pdfplumber",
    "pymupdf": "fitz",
    "pillow": "PIL",
    "opencv-python-headless": "cv2",
    "paddlepaddle": "paddle",
}
OCR_REQUIREMENTS = "requirements-ocr.txt"
OCR_SETUP_PROMPT = (
    "PaddleOCR is required to read this document. Shall Claude install it now? "
    "The download is about 500 MB."
)


def _requirement_name(line: str) -> str:
    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def _required_imports(requirement_files: list[Path]) -> dict[str, str]:
    required: dict[str, str] = {}
    for requirement_file in requirement_files:
        if not requirement_file.is_file() or requirement_file.is_symlink():
            raise ValueError(
                f"Requirements file is not a regular file: {requirement_file}"
            )
        for line in requirement_file.read_text(encoding="utf-8").splitlines():
            package = _requirement_name(line)
            if package:
                required[package] = REQUIRED.get(package, package.replace("-", "_"))
    return required


def _pdf_requires_ocr(path: Path) -> bool:
    """Return whether a bounded PDF has no useful embedded text."""

    if path.suffix.lower() != ".pdf":
        return False
    if path.is_symlink() or not path.is_file():
        raise ValueError("Dependency-check input must be a regular local file")
    try:
        import pdfplumber  # type: ignore[import-not-found]
    except (ImportError, ModuleNotFoundError):
        return False
    with pdfplumber.open(path) as pdf:
        return not any(
            len((page.extract_text() or "").strip()) >= 40 for page in pdf.pages[:5]
        )


def main(argv: list[str] | None = None) -> int:
    """Return zero when the pinned runtime is available."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Requirements file relative to the plugin root; may be repeated.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Optional PDF input used to detect whether the OCR runtime is required.",
    )
    parser.add_argument(
        "--require-ocr",
        action="store_true",
        help="Check the optional managed PaddleOCR runtime as well as core requirements.",
    )
    args = parser.parse_args(argv)
    if sys.version_info < (3, 10):
        LOGGER.error("Python 3.10 or newer is required")
        return 1
    plugin_root = Path(__file__).resolve().parents[1]
    requirement_files = (
        [plugin_root / value for value in args.requirements]
        if args.requirements
        else [plugin_root / "requirements.txt"]
    )
    try:
        require_ocr = args.require_ocr or (
            args.input is not None and _pdf_requires_ocr(args.input.resolve())
        )
    except (OSError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1
    if require_ocr and plugin_root / OCR_REQUIREMENTS not in requirement_files:
        requirement_files.append(plugin_root / OCR_REQUIREMENTS)
    if require_ocr:
        try:
            from managed_ocr_runtime import activate_ocr_runtime
        except ImportError:
            activate_ocr_runtime = None
        if (
            activate_ocr_runtime is None
            or activate_ocr_runtime(plugin_root / OCR_REQUIREMENTS) is None
        ):
            LOGGER.error("OCR_SETUP_REQUIRED: %s", OCR_SETUP_PROMPT)
            return 1
    try:
        required = _required_imports(requirement_files)
    except (OSError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1
    missing = [
        package
        for package, module in required.items()
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        if require_ocr:
            LOGGER.error("OCR_SETUP_REQUIRED: %s", OCR_SETUP_PROMPT)
            return 1
        LOGGER.error("Missing declared dependencies: %s", ", ".join(missing))
        return 1
    LOGGER.info("All Bilancio XBRL Italia dependencies are importable.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
