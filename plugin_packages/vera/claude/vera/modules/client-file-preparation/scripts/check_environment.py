from __future__ import annotations

import argparse
import importlib.util
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from managed_ocr_runtime import OCR_SETUP_PROMPT, activate_ocr_runtime

__all__ = ["Dependency", "check_dependencies", "input_requires_ocr", "main"]


PACKAGE_IMPORTS = {
    "pillow": "PIL",
    "pymupdf": "fitz",
    "paddlepaddle": "paddle",
}


@dataclass(frozen=True)
class Dependency:
    """One local dependency needed by the plugin."""

    label: str
    module: str | None = None
    command: str | None = None
    required_for: str = "core"
    install_hint: str = ""

    def available(self) -> bool:
        """Return whether the Python module or command is available."""

        if self.module is not None:
            return importlib.util.find_spec(self.module) is not None
        if self.command is not None:
            return shutil.which(self.command) is not None
        return False


CORE_DEPENDENCIES = (
    Dependency(
        label="pdfplumber",
        module="pdfplumber",
        required_for="PDF testuali",
        install_hint="python -m pip install -r requirements.txt",
    ),
    Dependency(
        label="PyMuPDF",
        module="fitz",
        required_for="PDF testuali e rendering pagine",
        install_hint="python -m pip install -r requirements.txt",
    ),
)

OCR_DEPENDENCIES = (
    Dependency(
        label="Pillow",
        module="PIL",
        required_for="gestione immagini OCR",
    ),
    Dependency(
        label="PaddleOCR",
        module="paddleocr",
        required_for="OCR locale",
    ),
    Dependency(
        label="PaddlePaddle",
        module="paddle",
        required_for="runtime OCR locale",
    ),
)

IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".png", ".tif", ".tiff"}
PDF_EXTENSION = ".pdf"


def plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def requirement_name(line: str) -> str:
    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def import_name(package_name: str) -> str:
    return PACKAGE_IMPORTS.get(package_name.lower(), package_name.replace("-", "_"))


def dependencies_from_requirements(requirement_files: list[Path]) -> list[Dependency]:
    dependencies: list[Dependency] = []
    for requirements_file in requirement_files:
        for line in requirements_file.read_text(encoding="utf-8").splitlines():
            package = requirement_name(line)
            if not package:
                continue
            dependencies.append(
                Dependency(
                    label=package,
                    module=import_name(package),
                    required_for=requirements_file.name,
                    install_hint=f"python -m pip install -r {requirements_file.name}",
                )
            )
    return dependencies


def selected_requirement_files(explicit_files: list[str]) -> list[Path]:
    root = plugin_root()
    if explicit_files:
        files = [root / name for name in explicit_files]
    else:
        files = [root / "requirements.txt"]
    return [path for path in files if path.exists()]


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


def _input_files(source: Path | None) -> list[Path]:
    if source is None:
        return []
    root = source.expanduser()
    if root.is_symlink() or not root.exists():
        return []
    if root.is_file():
        return [root]
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.rglob("*") if path.is_file() and not path.is_symlink()),
        key=lambda path: str(path).casefold(),
    )


def input_requires_ocr(source: Path | None) -> bool:
    """Return whether an input contains an image or visual-only PDF."""

    for path in _input_files(source):
        extension = path.suffix.lower()
        if extension in IMAGE_EXTENSIONS:
            return True
        if extension == PDF_EXTENSION and _pdf_requires_ocr(path):
            return True
    return False


def _activate_shared_ocr_runtime() -> None:
    requirements_path = plugin_root() / "requirements-ocr.txt"
    if not requirements_path.is_file():
        return
    activate_ocr_runtime(requirements_path)


def check_dependencies(
    require_ocr: bool = False,
    requirement_files: list[Path] | None = None,
) -> tuple[list[Dependency], list[Dependency]]:
    """Return available and missing dependencies."""

    if require_ocr:
        _activate_shared_ocr_runtime()
    if requirement_files is not None:
        dependencies = dependencies_from_requirements(requirement_files)
    else:
        dependencies = list(CORE_DEPENDENCIES)
        if require_ocr:
            dependencies.extend(OCR_DEPENDENCIES)
    available: list[Dependency] = []
    missing: list[Dependency] = []
    for dependency in dependencies:
        if dependency.available():
            available.append(dependency)
        else:
            missing.append(dependency)
    return available, missing


def _print_report(
    available: list[Dependency],
    missing: list[Dependency],
    *,
    require_ocr: bool = False,
) -> None:
    print("# Controllo ambiente Client File Preparation")
    print()
    if available:
        print("Disponibili:")
        for dependency in available:
            print(f"- {dependency.label} ({dependency.required_for})")
        print()
    if missing:
        if require_ocr and any(
            dependency in OCR_DEPENDENCIES for dependency in missing
        ):
            print(f"OCR_SETUP_REQUIRED: {OCR_SETUP_PROMPT}")
            print()
        print("Mancanti:")
        for dependency in missing:
            print(f"- {dependency.label} ({dependency.required_for})")
        print()
        hints = sorted(
            {
                dependency.install_hint
                for dependency in missing
                if dependency.install_hint
            }
        )
        if hints:
            print("Comandi suggeriti:")
            for hint in hints:
                print(f"- {hint}")
            print()
    else:
        if require_ocr:
            print(
                "OCR_REQUIRED: contenuto visivo senza testo rilevato; "
                "il runtime PaddleOCR condiviso è pronto."
            )
            print()
        print("Ambiente pronto.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verifica le dipendenze locali del plugin Client File Preparation."
    )
    parser.add_argument(
        "--folder",
        type=Path,
        default=None,
        help=(
            "File o cartella cliente. Immagini e pagine PDF senza testo "
            "utilizzabile richiedono automaticamente OCR."
        ),
    )
    parser.add_argument(
        "--require-ocr",
        action="store_true",
        help="Richiede anche le dipendenze OCR.",
    )
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Specific requirements file under the plugin root. May be passed more than once.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    requirement_files = selected_requirement_files(args.requirements)
    if args.requirements and not requirement_files:
        print("MISSING_REQUIREMENTS_FILE: no requested requirements file found")
        return 1
    if args.requirements:
        available, missing = check_dependencies(requirement_files=requirement_files)
        _print_report(available, missing)
        return 0 if not missing else 1

    require_ocr = args.require_ocr or input_requires_ocr(args.folder)
    available, missing = check_dependencies(require_ocr=require_ocr)
    _print_report(available, missing, require_ocr=require_ocr)

    if not missing:
        return 0

    core_missing = [
        dependency for dependency in missing if dependency in CORE_DEPENDENCIES
    ]
    return 2 if core_missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
