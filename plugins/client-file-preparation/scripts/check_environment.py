from __future__ import annotations

import argparse
import importlib.util
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Dependency", "check_dependencies", "main"]


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
        install_hint="python -m pip install -r requirements-ocr.txt",
    ),
    Dependency(
        label="PaddleOCR",
        module="paddleocr",
        required_for="OCR locale",
        install_hint="python -m pip install -r requirements-ocr.txt",
    ),
    Dependency(
        label="PaddlePaddle",
        module="paddle",
        required_for="runtime OCR locale",
        install_hint="python -m pip install -r requirements-ocr.txt",
    ),
)

PDF_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".heic"}


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


def _folder_has_pdf_or_images(folder: Path | None) -> bool:
    if folder is None:
        return False
    if not folder.exists() or not folder.is_dir():
        return False
    return any(
        path.is_file() and path.suffix.lower() in PDF_EXTENSIONS
        for path in folder.rglob("*")
    )


def check_dependencies(
    require_ocr: bool = False,
    requirement_files: list[Path] | None = None,
) -> tuple[list[Dependency], list[Dependency]]:
    """Return available and missing dependencies."""

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


def _print_report(available: list[Dependency], missing: list[Dependency]) -> None:
    print("# Controllo ambiente Client File Preparation")
    print()
    if available:
        print("Disponibili:")
        for dependency in available:
            print(f"- {dependency.label} ({dependency.required_for})")
        print()
    if missing:
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
        print("Ambiente pronto.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verifica le dipendenze locali del plugin Client File Preparation."
    )
    parser.add_argument(
        "--folder",
        type=Path,
        default=None,
        help="Cartella cliente. Se contiene PDF/immagini, viene richiesto OCR.",
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

    require_ocr = args.require_ocr or _folder_has_pdf_or_images(args.folder)
    available, missing = check_dependencies(require_ocr=require_ocr)
    _print_report(available, missing)

    if not missing:
        return 0

    core_missing = [
        dependency for dependency in missing if dependency in CORE_DEPENDENCIES
    ]
    return 2 if core_missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
