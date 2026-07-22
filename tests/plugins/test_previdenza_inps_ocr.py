from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "previdenza-inps"
SCRIPTS_ROOT = PLUGIN_ROOT / "scripts"


def _load_script(module_name: str) -> ModuleType:
    scripts_path = str(SCRIPTS_ROOT)
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    path = SCRIPTS_ROOT / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(
        f"previdenza_inps_ocr_{module_name}", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_blank_pdf(path: Path, *, page_count: int = 1) -> Path:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=200, height=200)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def _write_text_pdf(path: Path, text: str) -> Path:
    fitz = pytest.importorskip("fitz")
    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), text)
        document.save(path)
    finally:
        document.close()
    return path


def _write_multiframe_tiff(path: Path) -> Path:
    image_module = pytest.importorskip("PIL.Image")
    first = image_module.new("RGB", (32, 32), "white")
    second = image_module.new("RGB", (32, 32), "black")
    try:
        first.save(path, save_all=True, append_images=[second], format="TIFF")
    finally:
        first.close()
        second.close()
    return path


def _successful_ocr(text: str, *, network_used: bool = False) -> dict[str, Any]:
    return {
        "text": text,
        "status": "ok",
        "engine": "paddle_ocr",
        "language": "it",
        "line_count": 1,
        "warnings": [],
        "model_source": "local_cache",
        "network_used": network_used,
    }


def test_scanned_pdf_ocr_preserves_page_locators_and_partial_status(
    tmp_path: Path, monkeypatch: Any
) -> None:
    case_core = _load_script("case_core")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _write_blank_pdf(input_dir / "scansione.pdf", page_count=2)
    monkeypatch.setattr(
        case_core,
        "_render_pdf_page",
        lambda _path, page_index: f"page-{page_index + 1}".encode(),
    )
    monkeypatch.setattr(
        case_core,
        "_run_local_ocr",
        lambda image_bytes, **_kwargs: _successful_ocr(image_bytes.decode()),
    )

    result = case_core.extract_case_documents(input_dir, output_dir)

    fragments = result.inventory["evidence_fragments"]
    assert [fragment["evidence_id"] for fragment in fragments] == [
        "DOC-001#page-1",
        "DOC-001#page-2",
    ]
    assert [fragment["extraction_method"] for fragment in fragments] == [
        "paddle_ocr",
        "paddle_ocr",
    ]
    assert all(
        "ocr_text_requires_visual_confirmation" in fragment["limitations"]
        for fragment in fragments
    )
    report = json.loads(result.extraction_report_path.read_text(encoding="utf-8"))
    assert report["status"] == "partial_evidence"
    assert report["ocr_attempted_page_count"] == 2
    assert report["ocr_successful_page_count"] == 2
    evidence_markdown = result.extracted_evidence_path.read_text(encoding="utf-8")
    assert "Extraction method: `paddle_ocr`" in evidence_markdown
    assert "`ocr_text_requires_visual_confirmation`" in evidence_markdown


def test_sparse_embedded_pdf_text_triggers_ocr_and_stays_partial(
    tmp_path: Path, monkeypatch: Any
) -> None:
    case_core = _load_script("case_core")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _write_text_pdf(input_dir / "scansione-con-layer.pdf", "x")
    ocr_calls: list[bytes] = []
    monkeypatch.setattr(case_core, "_render_pdf_page", lambda *_args: b"page")

    def _ocr(image_bytes: bytes, **_kwargs: Any) -> dict[str, Any]:
        ocr_calls.append(image_bytes)
        return _successful_ocr("Testo completo riconosciuto dalla pagina")

    monkeypatch.setattr(case_core, "_run_local_ocr", _ocr)

    result = case_core.extract_case_documents(input_dir, output_dir)

    assert ocr_calls == [b"page"]
    fragment = result.inventory["evidence_fragments"][0]
    assert fragment["extraction_method"] == "paddle_ocr"
    assert "embedded_text_below_ocr_quality_threshold" in fragment["limitations"]
    assert "ocr_text_requires_visual_confirmation" in fragment["limitations"]
    assert fragment["ocr"]["embedded_text_character_count"] == 1
    report = json.loads(result.extraction_report_path.read_text(encoding="utf-8"))
    assert report["status"] == "partial_evidence"


def test_sufficient_embedded_pdf_text_skips_ocr(
    tmp_path: Path, monkeypatch: Any
) -> None:
    case_core = _load_script("case_core")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _write_text_pdf(
        input_dir / "testo-nativo.pdf",
        "Questo documento contiene un livello testuale nativo completo e leggibile.",
    )

    def _fail_if_called(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("Sufficient embedded text must not invoke OCR")

    monkeypatch.setattr(case_core, "_run_local_ocr", _fail_if_called)

    result = case_core.extract_case_documents(input_dir, output_dir)

    fragment = result.inventory["evidence_fragments"][0]
    assert fragment["extraction_method"] == "embedded_text"
    assert fragment["limitations"] == []
    report = json.loads(result.extraction_report_path.read_text(encoding="utf-8"))
    assert report["status"] == "ready_for_fact_structuring"


def test_image_ocr_keeps_local_provenance_and_records_actual_network_use(
    tmp_path: Path, monkeypatch: Any
) -> None:
    case_core = _load_script("case_core")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "pagina.png").write_bytes(b"synthetic-image")
    monkeypatch.setattr(
        case_core,
        "_run_local_ocr",
        lambda _image_bytes, **_kwargs: _successful_ocr(
            "Testo della scansione", network_used=True
        ),
    )

    result = case_core.extract_case_documents(
        input_dir,
        output_dir,
        allow_ocr_model_download=True,
    )

    fragment = result.inventory["evidence_fragments"][0]
    assert fragment["evidence_id"] == "DOC-001#page-1"
    assert fragment["ocr"]["model_source"] == "local_cache"
    assert fragment["ocr"]["network_used"] is True
    assert result.inventory["ocr"]["network_used"] is True


def test_multiframe_tiff_preserves_one_page_locator_per_frame(
    tmp_path: Path, monkeypatch: Any
) -> None:
    case_core = _load_script("case_core")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _write_multiframe_tiff(input_dir / "scansione.tiff")
    ocr_calls: list[bytes] = []

    def _ocr(image_bytes: bytes, **_kwargs: Any) -> dict[str, Any]:
        ocr_calls.append(image_bytes)
        return _successful_ocr(f"Pagina {len(ocr_calls)} della scansione")

    monkeypatch.setattr(case_core, "_run_local_ocr", _ocr)

    result = case_core.extract_case_documents(input_dir, output_dir)

    document = result.inventory["documents"][0]
    fragments = result.inventory["evidence_fragments"]
    assert len(ocr_calls) == 2
    assert document["page_count"] == 2
    assert document["ocr_attempted_page_count"] == 2
    assert [fragment["evidence_id"] for fragment in fragments] == [
        "DOC-001#page-1",
        "DOC-001#page-2",
    ]


def test_missing_local_ocr_models_is_an_explicit_nonfatal_limitation(
    tmp_path: Path, monkeypatch: Any
) -> None:
    case_core = _load_script("case_core")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _write_blank_pdf(input_dir / "scansione.pdf")
    monkeypatch.setattr(case_core, "_render_pdf_page", lambda *_args: b"page")
    monkeypatch.setattr(
        case_core,
        "_run_local_ocr",
        lambda _image_bytes, **_kwargs: {
            **_successful_ocr(""),
            "status": "models_unavailable",
        },
    )

    result = case_core.extract_case_documents(input_dir, output_dir)

    fragment = result.inventory["evidence_fragments"][0]
    assert fragment["extraction_method"] == "none"
    assert "ocr_models_unavailable" in fragment["limitations"]
    assert "empty_text_possible_scan" in fragment["limitations"]
    assert fragment["ocr"]["status"] == "models_unavailable"
    assert fragment["ocr"]["network_used"] is False
    report = json.loads(result.extraction_report_path.read_text(encoding="utf-8"))
    assert report["status"] == "blocked_input"
    assert report["ocr_successful_page_count"] == 0


def test_no_ocr_never_calls_adapter_and_records_disabled_posture(
    tmp_path: Path, monkeypatch: Any
) -> None:
    inventory_case = _load_script("inventory_case")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _write_blank_pdf(input_dir / "scansione.pdf")

    original_extract = inventory_case.extract_case_documents

    def _fail_if_called(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("OCR adapter must not be called with --no-ocr")

    monkeypatch.setitem(original_extract.__globals__, "_run_local_ocr", _fail_if_called)

    def _assert_ocr_disabled(*args: Any, **kwargs: Any) -> Any:
        assert kwargs["enable_ocr"] is False
        return original_extract(*args, **kwargs)

    monkeypatch.setattr(inventory_case, "extract_case_documents", _assert_ocr_disabled)

    exit_code = inventory_case.main(
        [str(input_dir), "--output-dir", str(output_dir), "--no-ocr"]
    )

    assert exit_code == 2
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    assert run_intake["data_posture"]["network_calls_by_scripts"] is False
    assert run_intake["data_posture"]["ocr"]["enabled"] is False
    assert run_intake["data_posture"]["ocr"]["model_download_allowed"] is False
    assert run_intake["data_posture"]["ocr"]["attempt_location"] == "not_run"
    assert run_intake["data_posture"]["ocr"]["visual_confirmation_required"] is False


def test_ocr_optional_requirements_have_import_mappings() -> None:
    checker = _load_script("check_dependencies")
    requirements = (PLUGIN_ROOT / "requirements-ocr.txt").read_text(encoding="utf-8")

    declared = {
        checker._requirement_name(line)
        for line in requirements.splitlines()
        if checker._requirement_name(line)
    }

    assert declared <= set(checker.PACKAGE_IMPORTS)


def test_model_download_route_choice_is_persisted_before_extraction(
    tmp_path: Path, monkeypatch: Any
) -> None:
    inventory_case = _load_script("inventory_case")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    observed_preflight: list[dict[str, Any]] = []

    def _fail_after_preflight(*_args: Any, **_kwargs: Any) -> Any:
        observed_preflight.append(
            json.loads((output_dir / "run_intake.json").read_text(encoding="utf-8"))
        )
        raise FileNotFoundError("synthetic extraction failure")

    monkeypatch.setattr(inventory_case, "extract_case_documents", _fail_after_preflight)

    exit_code = inventory_case.main(
        [
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--allow-ocr-model-download",
        ]
    )

    assert exit_code == 1
    preflight = observed_preflight[0]
    assert preflight["status"] == "inventory_in_progress"
    assert preflight["data_posture"]["ocr"]["model_download_allowed"] is True
    assert "model_download_approval_id" not in preflight["data_posture"]["ocr"]
    final_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    assert final_intake["status"] == "inventory_failed"
    assert final_intake["failure"]["error_type"] == "FileNotFoundError"
