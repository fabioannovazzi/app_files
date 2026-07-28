"""Check runtime dependencies for Clara."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from managed_ocr_runtime import OCR_SETUP_PROMPT, activate_ocr_runtime

__all__ = [
    "check_dependencies",
    "component_root",
    "input_requires_ocr",
    "import_name",
    "main",
    "requirement_name",
    "selected_requirement_files",
]

LOGGER = logging.getLogger(__name__)
COMPONENTS = (
    "attribute-reporting",
    "reporting-engine",
    "distribution-analysis",
    "funnel-analysis",
    "mix-contribution-analysis",
    "period-comparison",
    "scatter-bubble-analysis",
    "set-overlap-analysis",
    "statement-analysis",
    "variance-analysis",
)
PACKAGE_IMPORTS = {
    "imageio-ffmpeg": "imageio_ffmpeg",
    "opencv-python": "cv2",
    "paddlepaddle": "paddle",
    "pillow": "PIL",
    "pymupdf": "fitz",
    "python-docx": "docx",
    "python-pptx": "pptx",
}
IMAGE_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".heic",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
}
PDF_EXTENSION = ".pdf"


def plugin_root() -> Path:
    """Return the editable Clara plugin root."""

    return Path(__file__).resolve().parents[1]


def component_root(name: str) -> Path:
    """Return the packaged or repository source root for a Clara component."""

    if name not in COMPONENTS:
        raise ValueError(f"Unsupported Clara component: {name}")
    packaged = plugin_root() / "modules" / name
    if packaged.is_dir():
        return packaged
    return plugin_root().parent / name


def requirement_name(line: str) -> str | None:
    """Return the normalized package name from a requirement line."""

    clean = line.split("#", 1)[0].strip()
    if not clean or clean.startswith(("-", "git+", "http://", "https://")):
        return None
    package = re.split(r"\s*(?:===|==|~=|!=|>=|<=|>|<|@|;)\s*", clean, maxsplit=1)[0]
    package = package.split("[", 1)[0].strip().lower()
    return package or None


def import_name(package: str) -> str:
    """Return the module name that should be import-checked for a package."""

    normalized = package.lower()
    return PACKAGE_IMPORTS.get(normalized, normalized.replace("-", "_"))


def _resolve_requirement_file(path: Path) -> Path:
    if path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path
    return plugin_root() / path


def selected_requirement_files(
    requirements: Sequence[Path] | None,
    *,
    include_optional: bool = False,
) -> list[Path]:
    """Return requirement files selected by CLI flags."""

    files: list[Path] = []
    if requirements:
        files.extend(_resolve_requirement_file(path) for path in requirements)
    else:
        files.append(plugin_root() / "requirements.txt")
    if include_optional:
        files.extend(sorted(plugin_root().glob("requirements-*.txt")))

    deduplicated: list[Path] = []
    seen: set[Path] = set()
    for path in files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduplicated.append(path)
    return deduplicated


def _expanded_requirement_files(
    paths: Sequence[Path],
    *,
    seen: set[Path] | None = None,
) -> list[Path]:
    """Return requirement files plus recursive local ``-r`` includes."""

    visited = seen if seen is not None else set()
    expanded: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in visited:
            continue
        visited.add(resolved)
        expanded.append(resolved)
        included: list[Path] = []
        for raw_line in resolved.read_text(encoding="utf-8").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            include = ""
            if line.startswith("-r "):
                include = line[3:].strip()
            elif line.startswith("--requirement "):
                include = line[len("--requirement ") :].strip()
            if include:
                included.append(resolved.parent / include)
        expanded.extend(_expanded_requirement_files(included, seen=visited))
    return expanded


def check_dependencies(requirements: Path | Sequence[Path]) -> list[str]:
    """Return package names whose import targets are unavailable."""

    requirement_files = (
        [requirements] if isinstance(requirements, Path) else list(requirements)
    )
    missing: list[str] = []
    seen_missing: set[str] = set()
    for path in _expanded_requirement_files(requirement_files):
        for line in path.read_text(encoding="utf-8").splitlines():
            package = requirement_name(line)
            if package is None:
                continue
            if importlib.util.find_spec(import_name(package)) is None:
                if package in seen_missing:
                    continue
                missing.append(package)
                seen_missing.add(package)
    return missing


def _text_is_useful(text: str) -> bool:
    """Return whether a native PDF text layer contains substantive text."""

    compact = " ".join(text.split())
    if len(compact) < 40:
        return False
    return sum(character.isalnum() for character in compact) >= 20


def _pdf_requires_ocr(path: Path) -> bool:
    """Detect visual PDF pages without useful native text.

    Native text and visual page content are mechanically inspectable, so this
    deterministic gate is more reliable than semantic or filename inference.
    """

    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        return False

    try:
        with fitz.open(path) as document:
            for page in document:
                if _text_is_useful(page.get_text("text")):
                    continue
                if page.get_images(full=True) or page.get_drawings():
                    return True
    except (OSError, RuntimeError, ValueError):
        return False
    return False


def _input_files(paths: Sequence[Path]) -> list[Path]:
    """Return supported, non-symlink input files in stable order."""

    files: list[Path] = []
    for raw_path in paths:
        path = raw_path.expanduser()
        if path.is_symlink():
            continue
        if path.is_file():
            files.append(path)
            continue
        if path.is_dir():
            files.extend(
                candidate
                for candidate in path.rglob("*")
                if candidate.is_file() and not candidate.is_symlink()
            )
    return sorted(
        (
            path
            for path in files
            if path.suffix.lower() in IMAGE_EXTENSIONS | {PDF_EXTENSION}
        ),
        key=lambda path: str(path).casefold(),
    )


def input_requires_ocr(paths: Sequence[Path]) -> bool:
    """Return whether any supplied image or visual-only PDF requires OCR."""

    for path in _input_files(paths):
        extension = path.suffix.lower()
        if extension in IMAGE_EXTENSIONS:
            return True
        if extension == PDF_EXTENSION and _pdf_requires_ocr(path):
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    """Run the dependency check CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--module",
        choices=COMPONENTS,
        help="Delegate dependency checks to an embedded Clara component.",
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        action="append",
        default=None,
        help="Requirements file to inspect.",
    )
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Also inspect optional requirement files such as requirements-ocr.txt.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        action="append",
        default=None,
        help=(
            "File or folder to inspect. Visual-only PDFs and images automatically "
            "require the shared local OCR runtime."
        ),
    )
    args, remaining = parser.parse_known_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.module is not None:
        root = component_root(args.module)
        checker = root / "scripts" / "check_dependencies.py"
        if not checker.is_file():
            LOGGER.error(
                "Dependency checker not found for %s: %s", args.module, checker
            )
            return 1
        delegated_args = list(remaining)
        for requirement in args.requirements or []:
            delegated_args.extend(("--requirements", str(requirement)))
        if args.include_optional:
            delegated_args.append("--include-optional")
        completed = subprocess.run(
            [sys.executable, str(checker), *delegated_args],
            cwd=root,
            check=False,
        )
        return completed.returncode
    if remaining:
        parser.error(f"unrecognized arguments: {' '.join(remaining)}")
    ocr_required = input_requires_ocr(args.input or [])
    if ocr_required:
        activate_ocr_runtime(plugin_root() / "requirements-ocr.txt")
    requirement_files = selected_requirement_files(
        args.requirements,
        include_optional=args.include_optional or ocr_required,
    )
    missing = check_dependencies(requirement_files)
    if missing:
        if ocr_required:
            LOGGER.error("OCR_SETUP_REQUIRED: %s", OCR_SETUP_PROMPT)
        LOGGER.error("Missing dependencies: %s", ", ".join(missing))
        LOGGER.error(
            "Checked requirement files: %s",
            ", ".join(str(path) for path in requirement_files),
        )
        return 1
    if ocr_required:
        LOGGER.info(
            "OCR_REQUIRED: Visual-only input detected; the shared PaddleOCR "
            "runtime is ready."
        )
    LOGGER.info("All Clara dependencies are available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
