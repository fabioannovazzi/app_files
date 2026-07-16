from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import fitz

__all__ = [
    "SofficeNotFoundError",
    "rasterize_presentation_to_pngs",
    "resolve_soffice_binary",
]

LOGGER = logging.getLogger(__name__)
_DEFAULT_MACOS_SOFFICE_PATHS = (
    Path("/opt/homebrew/bin/soffice"),
    Path("/usr/local/bin/soffice"),
    Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
)
_DEFAULT_WINDOWS_SOFFICE_PATHS = (
    Path("/mnt/c/Program Files/LibreOffice/program/soffice.exe"),
    Path("/mnt/c/Program Files (x86)/LibreOffice/program/soffice.exe"),
)


class SofficeNotFoundError(RuntimeError):
    """Raised when no LibreOffice executable is available for PPTX conversion."""


def resolve_soffice_binary() -> Path:
    """Resolve a usable LibreOffice executable from Linux or Windows."""

    configured = str((os.environ.get("SOFFICE_BINARY") or "").strip())
    if configured:
        candidate = Path(configured)
        if candidate.exists():
            return candidate

    for binary_name in ("soffice", "libreoffice"):
        resolved = shutil.which(binary_name)
        if resolved:
            return Path(resolved)

    for candidate in _DEFAULT_MACOS_SOFFICE_PATHS:
        if candidate.exists():
            return candidate

    for candidate in _DEFAULT_WINDOWS_SOFFICE_PATHS:
        if candidate.exists():
            return candidate
    raise SofficeNotFoundError(
        "No LibreOffice executable found. Install LibreOffice or set SOFFICE_BINARY."
    )


def _is_windows_soffice(soffice_binary: Path) -> bool:
    """Return whether the resolved LibreOffice binary is a Windows executable."""

    return soffice_binary.suffix.lower() == ".exe"


def _path_for_soffice(path: Path, *, windows_binary: bool) -> str:
    """Convert a path for use with the selected LibreOffice executable."""

    if not windows_binary:
        return str(path)
    completed = subprocess.run(
        ["wslpath", "-w", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _file_uri_for_soffice(path: Path, *, windows_binary: bool) -> str:
    """Build a file URI accepted by the selected LibreOffice executable."""

    if not windows_binary:
        return path.resolve().as_uri()
    windows_path = _path_for_soffice(path, windows_binary=True).replace("\\", "/")
    if not windows_path.startswith("/"):
        windows_path = "/" + windows_path
    return f"file://{windows_path}"


def _windows_accessible_temp_root(anchor_path: Path) -> Path:
    """Resolve a temp root that Windows LibreOffice can access from WSL."""

    resolved = anchor_path.resolve()
    for parent in (resolved, *resolved.parents):
        if str(parent).startswith("/mnt/") and parent.exists():
            candidate = parent / ".tmp_soffice"
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
    fallback = Path.cwd() / "tmp" / "soffice"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _convert_presentation_to_pdf(
    input_path: Path,
    *,
    soffice_binary: Path,
) -> Path:
    """Convert a PPTX to PDF through LibreOffice and return the persisted PDF path."""

    windows_binary = _is_windows_soffice(soffice_binary)
    temp_root = (
        _windows_accessible_temp_root(input_path.parent) if windows_binary else None
    )
    with tempfile.TemporaryDirectory(
        prefix="soffice_profile_",
        dir=str(temp_root) if temp_root is not None else None,
    ) as profile_dir:
        with tempfile.TemporaryDirectory(
            prefix="soffice_convert_",
            dir=str(temp_root) if temp_root is not None else None,
        ) as output_dir:
            profile_path = Path(profile_dir).resolve()
            output_path = Path(output_dir).resolve()
            command = [
                str(soffice_binary),
                f"-env:UserInstallation={_file_uri_for_soffice(profile_path, windows_binary=windows_binary)}",
                "--invisible",
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf",
                "--outdir",
                _path_for_soffice(output_path, windows_binary=windows_binary),
                _path_for_soffice(input_path.resolve(), windows_binary=windows_binary),
            ]
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
            pdf_path = output_path / f"{input_path.stem}.pdf"
            if completed.returncode != 0 or not pdf_path.exists():
                raise RuntimeError(
                    "LibreOffice failed to convert presentation to PDF: "
                    f"{completed.stderr.strip() or completed.stdout.strip() or 'unknown error'}"
                )
            persisted_pdf_path = (
                temp_root / f"{input_path.stem}-rendered.pdf"
                if temp_root is not None
                else input_path.with_suffix(".rendered.pdf")
            )
            shutil.copy2(pdf_path, persisted_pdf_path)
            return persisted_pdf_path


def _scale_for_pdf_page(
    page: fitz.Page, *, max_width_px: int, max_height_px: int
) -> float:
    """Compute a scale that keeps a PDF page within the requested raster bounds."""

    rect = page.rect
    if rect.width <= 0 or rect.height <= 0:
        return 1.0
    width_scale = max_width_px / float(rect.width)
    height_scale = max_height_px / float(rect.height)
    return max(0.1, min(width_scale, height_scale))


def _rasterize_pdf_to_pngs(
    pdf_path: Path,
    output_dir: Path,
    *,
    max_width_px: int,
    max_height_px: int,
) -> list[Path]:
    """Rasterize a PDF file into one PNG per page."""

    output_dir.mkdir(parents=True, exist_ok=True)
    image_paths: list[Path] = []
    document = fitz.open(pdf_path)
    try:
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            scale = _scale_for_pdf_page(
                page,
                max_width_px=max_width_px,
                max_height_px=max_height_px,
            )
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image_path = output_dir / f"slide-{page_index + 1}.png"
            pixmap.save(str(image_path))
            image_paths.append(image_path)
    finally:
        document.close()
    return image_paths


def rasterize_presentation_to_pngs(
    input_path: Path,
    output_dir: Path,
    *,
    max_width_px: int = 1600,
    max_height_px: int = 900,
    soffice_binary: Path | None = None,
) -> list[Path]:
    """Rasterize a PPTX or PDF into per-slide PNGs.

    For PPTX inputs, Linux ``soffice`` is preferred; when unavailable under WSL,
    a Windows LibreOffice installation is used transparently.
    """

    resolved_input = input_path.resolve()
    if not resolved_input.exists():
        raise FileNotFoundError(f"Presentation not found: {resolved_input}")
    if resolved_input.suffix.lower() == ".pdf":
        return _rasterize_pdf_to_pngs(
            resolved_input,
            output_dir.resolve(),
            max_width_px=max_width_px,
            max_height_px=max_height_px,
        )
    if resolved_input.suffix.lower() != ".pptx":
        raise ValueError(f"Unsupported presentation input: {resolved_input.suffix}")
    resolved_soffice = soffice_binary or resolve_soffice_binary()
    pdf_path = _convert_presentation_to_pdf(
        resolved_input,
        soffice_binary=resolved_soffice,
    )
    LOGGER.info("Rasterizing %s through %s", resolved_input, resolved_soffice)
    return _rasterize_pdf_to_pngs(
        pdf_path,
        output_dir.resolve(),
        max_width_px=max_width_px,
        max_height_px=max_height_px,
    )
