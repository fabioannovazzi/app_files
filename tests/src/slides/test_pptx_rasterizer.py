from __future__ import annotations

import subprocess
from pathlib import Path

import fitz

from src.slides import pptx_rasterizer


def test_resolve_soffice_binary_prefers_configured_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    candidate = tmp_path / "soffice.exe"
    candidate.write_bytes(b"")

    monkeypatch.setenv("SOFFICE_BINARY", str(candidate))
    monkeypatch.setattr(pptx_rasterizer.shutil, "which", lambda _name: None)
    monkeypatch.setattr(pptx_rasterizer, "_DEFAULT_MACOS_SOFFICE_PATHS", ())
    monkeypatch.setattr(pptx_rasterizer, "_DEFAULT_WINDOWS_SOFFICE_PATHS", ())

    assert pptx_rasterizer.resolve_soffice_binary() == candidate


def test_resolve_soffice_binary_falls_back_to_macos_installation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    candidate = tmp_path / "LibreOffice.app" / "Contents" / "MacOS" / "soffice"
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"")

    monkeypatch.delenv("SOFFICE_BINARY", raising=False)
    monkeypatch.setattr(pptx_rasterizer.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        pptx_rasterizer,
        "_DEFAULT_MACOS_SOFFICE_PATHS",
        (candidate,),
    )
    monkeypatch.setattr(pptx_rasterizer, "_DEFAULT_WINDOWS_SOFFICE_PATHS", ())

    assert pptx_rasterizer.resolve_soffice_binary() == candidate


def test_resolve_soffice_binary_falls_back_to_windows_installation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    candidate = tmp_path / "LibreOffice" / "program" / "soffice.exe"
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"")

    monkeypatch.delenv("SOFFICE_BINARY", raising=False)
    monkeypatch.setattr(pptx_rasterizer.shutil, "which", lambda _name: None)
    monkeypatch.setattr(pptx_rasterizer, "_DEFAULT_MACOS_SOFFICE_PATHS", ())
    monkeypatch.setattr(
        pptx_rasterizer,
        "_DEFAULT_WINDOWS_SOFFICE_PATHS",
        (candidate,),
    )

    assert pptx_rasterizer.resolve_soffice_binary() == candidate


def test_file_uri_for_windows_soffice_uses_wslpath(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "profile"
    path.mkdir()

    def _fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert command[:2] == ["wslpath", "-w"]
        assert check is True
        assert capture_output is True
        assert text is True
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="C:\\Users\\example\\profile\n",
            stderr="",
        )

    monkeypatch.setattr(pptx_rasterizer.subprocess, "run", _fake_run)

    assert (
        pptx_rasterizer._file_uri_for_soffice(path, windows_binary=True)
        == "file:///C:/Users/example/profile"
    )


def test_rasterize_presentation_to_pngs_rasterizes_pdf_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "slides.pdf"
    output_dir = tmp_path / "rendered"

    document = fitz.open()
    try:
        page = document.new_page(width=640, height=360)
        page.insert_text((72, 72), "Slide 1")
        document.save(pdf_path)
    finally:
        document.close()

    image_paths = pptx_rasterizer.rasterize_presentation_to_pngs(pdf_path, output_dir)

    assert image_paths == [output_dir / "slide-1.png"]
    assert image_paths[0].exists()
    assert image_paths[0].stat().st_size > 0


def test_rasterize_presentation_to_pngs_converts_pptx_before_rasterizing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    input_path = tmp_path / "deck.pptx"
    input_path.write_bytes(b"pptx")
    output_dir = tmp_path / "rendered"
    soffice_binary = tmp_path / "LibreOffice" / "program" / "soffice.exe"
    soffice_binary.parent.mkdir(parents=True)
    soffice_binary.write_bytes(b"")
    converted_pdf = tmp_path / "deck-rendered.pdf"
    converted_pdf.write_bytes(b"%PDF-1.4")
    expected_images = [output_dir / "slide-1.png"]
    calls: dict[str, object] = {}

    def _fake_convert(
        presentation_path: Path,
        *,
        soffice_binary: Path,
    ) -> Path:
        calls["presentation_path"] = presentation_path
        calls["soffice_binary"] = soffice_binary
        return converted_pdf

    def _fake_rasterize(
        pdf_path: Path,
        rendered_dir: Path,
        *,
        max_width_px: int,
        max_height_px: int,
    ) -> list[Path]:
        calls["pdf_path"] = pdf_path
        calls["rendered_dir"] = rendered_dir
        calls["max_width_px"] = max_width_px
        calls["max_height_px"] = max_height_px
        return expected_images

    monkeypatch.setattr(pptx_rasterizer, "_convert_presentation_to_pdf", _fake_convert)
    monkeypatch.setattr(pptx_rasterizer, "_rasterize_pdf_to_pngs", _fake_rasterize)

    image_paths = pptx_rasterizer.rasterize_presentation_to_pngs(
        input_path,
        output_dir,
        soffice_binary=soffice_binary,
        max_width_px=1200,
        max_height_px=800,
    )

    assert image_paths == expected_images
    assert calls == {
        "presentation_path": input_path.resolve(),
        "soffice_binary": soffice_binary,
        "pdf_path": converted_pdf,
        "rendered_dir": output_dir.resolve(),
        "max_width_px": 1200,
        "max_height_px": 800,
    }
