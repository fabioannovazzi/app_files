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

__all__ = [
    "check_dependencies",
    "component_root",
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


def check_dependencies(requirements: Path | Sequence[Path]) -> list[str]:
    """Return package names whose import targets are unavailable."""

    requirement_files = (
        [requirements] if isinstance(requirements, Path) else list(requirements)
    )
    missing: list[str] = []
    seen_missing: set[str] = set()
    for path in requirement_files:
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
    requirement_files = selected_requirement_files(
        args.requirements,
        include_optional=args.include_optional,
    )
    missing = check_dependencies(requirement_files)
    if missing:
        LOGGER.error("Missing dependencies: %s", ", ".join(missing))
        LOGGER.error(
            "Checked requirement files: %s",
            ", ".join(str(path) for path in requirement_files),
        )
        return 1
    LOGGER.info("All Clara dependencies are available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
