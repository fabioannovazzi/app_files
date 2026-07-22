"""Inventory local CCIAA/DIRE evidence and optionally OCR image screenshots locally."""

from __future__ import annotations

import argparse
import importlib
import logging
import mimetypes
import sys
from pathlib import Path
from typing import Any

from case_core import (
    PLUGIN_NAME,
    ensure_safe_output_dir,
    iso_now,
    load_json_object,
    safe_identifier,
    sha256_bytes,
    sha256_file,
    write_private_json,
    write_private_text,
)
from pypdf import PdfReader

__all__ = ["inventory_case", "main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 25_000_000
TEXT_SUFFIXES = {".csv", ".html", ".json", ".md", ".txt", ".xml"}
IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def _update_run_intake(
    output_dir: Path,
    *,
    input_dir: Path,
    run_id: str,
    records: list[dict[str, Any]],
    use_ocr: bool,
) -> None:
    path = output_dir / "run_intake.json"
    if not path.exists():
        return
    payload = load_json_object(path)
    if payload.get("plugin") != PLUGIN_NAME or payload.get("run_id") != run_id:
        raise ValueError("run_intake.json belongs to another run")
    input_path = input_dir.resolve().as_posix()
    input_paths = payload.get("input_paths")
    if not isinstance(input_paths, list):
        input_paths = []
    if input_path not in input_paths:
        input_paths.append(input_path)
    payload["input_paths"] = input_paths
    data_posture = payload.get("data_posture")
    if not isinstance(data_posture, dict):
        data_posture = {}
    data_posture["local_files_read"] = [
        {
            "id": record["document_id"],
            "sha256": record["sha256"],
            "size_bytes": record["size_bytes"],
        }
        for record in records
        if record.get("sha256")
    ]
    data_posture.setdefault("external_connectors_used", [])
    data_posture.setdefault("upload_paths_used", [])
    data_posture.setdefault("hosted_notebook_execution_used", False)
    data_posture.setdefault("remote_sql_execution_used", False)
    payload["data_posture"] = data_posture
    trace = payload.get("execution_trace")
    if not isinstance(trace, list):
        trace = []
    trace.append(
        {
            "step_id": f"inventory_case_{len(trace) + 1}",
            "kind": "deterministic_local_inventory",
            "command": [
                "python",
                "scripts/inventory_case.py",
                input_path,
                "--output-dir",
                output_dir.as_posix(),
                "--run-id",
                run_id,
                *([] if use_ocr else ["--no-ocr"]),
            ],
            "execution_location": "local_python",
            "status": "passed",
            "inputs": [
                {"id": record["document_id"], "sha256": record.get("sha256")}
                for record in records
            ],
            "outputs": [
                "local_evidence_inventory.json",
                *[
                    str(record["text_path"])
                    for record in records
                    if record.get("text_path")
                ],
            ],
        }
    )
    payload["execution_trace"] = trace
    write_private_json(path, payload)


def _load_ocr_adapter() -> Any | None:
    candidates = [
        PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
        PLUGIN_ROOT / "vendor" / "modules",
        PLUGIN_ROOT.parent.parent / "vendor" / "modules",
    ]
    for candidate in candidates:
        if candidate.is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    try:
        return importlib.import_module("vera_ocr")
    except ModuleNotFoundError as exc:
        if exc.name == "vera_ocr":
            return None
        raise


def _extract_pdf_text(path: Path) -> tuple[str, list[str], int]:
    reader = PdfReader(path)
    fragments: list[str] = []
    limitations: list[str] = []
    for page_index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            fragments.append(f"[PAGE {page_index}]\n{text}")
        else:
            limitations.append(f"page_{page_index}_empty_text_possible_scan")
    return "\n\n".join(fragments), limitations, len(reader.pages)


def _ocr_image(
    path: Path,
    *,
    language: str,
    cache_dir: Path | None,
    allow_model_download: bool,
) -> dict[str, Any]:
    adapter = _load_ocr_adapter()
    if adapter is None:
        return {
            "status": "runtime_unavailable",
            "text": "",
            "warnings": ["vera_ocr_adapter_unavailable"],
            "engine": "paddleocr",
            "network_used": False,
        }
    result = adapter.extract_text_from_image_bytes(
        path.read_bytes(),
        language=language,
        cache_dir=cache_dir,
        allow_model_download=allow_model_download,
    )
    return {
        "status": str(getattr(result, "status", "inference_failed")),
        "text": str(getattr(result, "text", "")),
        "warnings": list(getattr(result, "warnings", ())),
        "engine": str(getattr(result, "engine", "paddleocr")),
        "network_used": bool(getattr(result, "network_used", False)),
        "model_source": str(getattr(result, "model_source", "")),
        "model_names": list(getattr(result, "model_names", ())),
        "model_revisions": list(getattr(result, "model_revisions", ())),
        "runtime_versions": list(getattr(result, "runtime_versions", ())),
    }


def inventory_case(
    input_dir: Path,
    output_dir: Path,
    *,
    run_id: str,
    language: str = "it",
    use_ocr: bool = True,
    ocr_cache_dir: Path | None = None,
    allow_ocr_model_download: bool = False,
    ocr_model_download_approval_id: str | None = None,
) -> dict[str, Any]:
    """Inventory regular local files without semantic legal classification."""

    run_id = safe_identifier(run_id, field="run_id")
    if input_dir.is_symlink() or not input_dir.is_dir():
        raise ValueError("input directory must be a regular local directory")
    if (
        allow_ocr_model_download
        and not str(ocr_model_download_approval_id or "").strip()
    ):
        raise ValueError(
            "--allow-ocr-model-download requires --ocr-model-download-approval-id"
        )
    safe_output = ensure_safe_output_dir(output_dir, plugin_root=PLUGIN_ROOT)
    extracted_dir = safe_output / "extracted"
    extracted_dir.mkdir(mode=0o700, exist_ok=True)
    extracted_dir.chmod(0o700)
    if allow_ocr_model_download:
        write_private_json(
            safe_output / "ocr_model_download_authorization.json",
            {
                "schema_version": "1.0",
                "plugin": PLUGIN_NAME,
                "run_id": run_id,
                "recorded_at": iso_now(),
                "approval_id": str(ocr_model_download_approval_id).strip(),
                "model_download_allowed": True,
                "case_content_network_transfer": False,
            },
        )
    records: list[dict[str, Any]] = []
    ocr_attempts = 0
    ocr_successes = 0
    model_network_used = False
    for index, path in enumerate(sorted(input_dir.rglob("*")), start=1):
        if path.is_dir():
            continue
        relative = path.relative_to(input_dir).as_posix()
        record: dict[str, Any] = {
            "document_id": f"DOC-{index:03d}",
            "relative_path": relative,
            "source_path": path.resolve().as_posix(),
            "mime_type": mimetypes.guess_type(path.name)[0]
            or "application/octet-stream",
            "size_bytes": path.lstat().st_size,
            "sha256": None,
            "extraction_status": "not_supported",
            "text_path": None,
            "text_sha256": None,
            "page_count": None,
            "limitations": [],
            "semantic_classification": "not_performed",
        }
        if path.is_symlink():
            record["limitations"].append("symlink_not_followed")
            records.append(record)
            continue
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            record["limitations"].append("not_regular_or_exceeds_size_limit")
            records.append(record)
            continue
        record["sha256"] = sha256_file(path)
        text = ""
        suffix = path.suffix.lower()
        if suffix in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            record["extraction_status"] = "readable_text"
        elif suffix == ".pdf":
            try:
                text, limitations, page_count = _extract_pdf_text(path)
            except (OSError, ValueError) as exc:
                record["limitations"].append(
                    f"pdf_extraction_failed:{type(exc).__name__}"
                )
            else:
                record["limitations"].extend(limitations)
                record["page_count"] = page_count
                record["extraction_status"] = (
                    "readable_text" if text else "possible_image_only_pdf"
                )
        elif suffix in IMAGE_SUFFIXES and use_ocr:
            ocr_attempts += 1
            result = _ocr_image(
                path,
                language=language,
                cache_dir=ocr_cache_dir,
                allow_model_download=allow_ocr_model_download,
            )
            text = result.pop("text")
            record["ocr"] = result
            record["extraction_status"] = result["status"]
            record["limitations"].extend(result.get("warnings", []))
            record["limitations"].append("ocr_text_requires_visual_confirmation")
            model_network_used = model_network_used or bool(result.get("network_used"))
            if result["status"] in {"ok", "success"} and text.strip():
                ocr_successes += 1
        elif suffix in IMAGE_SUFFIXES:
            record["extraction_status"] = "ocr_disabled"
            record["limitations"].append("image_requires_local_ocr_or_visual_review")
        if text.strip():
            text_path = extracted_dir / f"{record['document_id']}.txt"
            write_private_text(text_path, text.strip() + "\n")
            record["text_path"] = text_path.relative_to(safe_output).as_posix()
            record["text_sha256"] = sha256_bytes(text_path.read_bytes())
        records.append(record)
    status = "complete"
    if any(record["limitations"] for record in records):
        status = "partial_evidence"
    payload = {
        "schema_version": "1.0",
        "plugin": PLUGIN_NAME,
        "run_id": run_id,
        "created_at": iso_now(),
        "input_dir": input_dir.resolve().as_posix(),
        "output_dir": safe_output.as_posix(),
        "status": status,
        "document_count": len(records),
        "documents": records,
        "semantic_classification": "not_performed",
        "ocr": {
            "enabled": use_ocr,
            "engine": "paddleocr" if use_ocr else "disabled",
            "attempted_image_count": ocr_attempts,
            "successful_image_count": ocr_successes,
            "case_content_network_transfer": False,
            "model_download_allowed": allow_ocr_model_download,
            "model_download_approval_id": ocr_model_download_approval_id,
            "model_network_used": model_network_used,
            "visual_confirmation_required": ocr_attempts > 0,
        },
    }
    write_private_json(safe_output / "local_evidence_inventory.json", payload)
    _update_run_intake(
        safe_output,
        input_dir=input_dir,
        run_id=run_id,
        records=records,
        use_ocr=use_ocr,
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    """Inventory one local evidence folder."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--language", default="it")
    parser.add_argument("--no-ocr", action="store_true")
    parser.add_argument("--ocr-cache-dir", type=Path)
    parser.add_argument("--allow-ocr-model-download", action="store_true")
    parser.add_argument("--ocr-model-download-approval-id")
    args = parser.parse_args(argv)
    try:
        payload = inventory_case(
            args.input_dir,
            args.output_dir,
            run_id=args.run_id,
            language=args.language,
            use_ocr=not args.no_ocr,
            ocr_cache_dir=args.ocr_cache_dir,
            allow_ocr_model_download=args.allow_ocr_model_download,
            ocr_model_download_approval_id=args.ocr_model_download_approval_id,
        )
    except (OSError, ValueError) as exc:
        LOGGER.error("INVENTORY_BLOCKED: %s", exc)
        return 2
    LOGGER.info(
        "Inventory %s: %s documents, %s OCR images",
        payload["status"],
        payload["document_count"],
        payload["ocr"]["attempted_image_count"],
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
