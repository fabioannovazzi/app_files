#!/usr/bin/env python3
"""Inventory and extract local documents for an INPS case review."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from case_core import ensure_safe_output_dir, extract_case_documents, write_json
from register_portal_export import MANIFEST_NAME as PORTAL_EXPORT_MANIFEST_NAME
from register_portal_export import MANIFEST_TYPE as PORTAL_EXPORT_MANIFEST_TYPE
from register_portal_export import PortalExportError, verify_portal_export

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent.parent / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        if str(_vendor_root) not in sys.path:
            sys.path.insert(0, str(_vendor_root))
        break

from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
    validate_client_workflow_run,
)

PORTAL_EXPORT_RECEIPT_MARKERS = frozenset(
    {
        "schema_version",
        "manifest_type",
        "registration_id",
        "created_at",
        "source_origin",
        "safety",
        "artifacts",
    }
)
PORTAL_PRIVATE_RECEIPT_NAMES = frozenset(
    {
        "inps_capture_approval.json",
        "inps_capture_receipt.json",
        "inps_export_approval.json",
        "inps_export_receipt.json",
        "inps_portal_capture_approval.json",
        "inps_portal_capture_receipt.json",
        "inps_portal_export_approval.json",
        "inps_portal_export_manifest.json",
        "inps_portal_export_receipt.json",
        "portal_capture_approval.json",
        "portal_capture_receipt.json",
        "portal_export_approval.json",
        "portal_export_manifest.json",
        "portal_export_receipt.json",
    }
)
MAX_PRIVATE_RECEIPT_INSPECTION_BYTES = 1024 * 1024
PORTAL_EXPORT_ARTIFACT_PREFIX = "inps-export-"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_relative_path(path: Path, run_root: Path) -> str:
    """Return a portable path anchored to the current workflow run."""

    resolved_root = run_root.expanduser().resolve(strict=True)
    resolved_path = path.expanduser().resolve(strict=True)
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise ValueError("workflow path is outside the current run") from exc


def _authorize_managed_ocr_paths(
    args: argparse.Namespace,
    context: dict[str, Any],
) -> None:
    """Require every possible OCR write target to stay in current-run outputs.

    This deterministic boundary is justified by security and auditability: path
    ancestry and model-download destinations are mechanically verifiable before
    an OCR adapter can create cache or model files.
    """

    if args.allow_ocr_model_download and args.ocr_cache_dir is None:
        raise AssuranceContractError(
            "managed OCR model download requires --ocr-cache-dir inside the "
            "current run outputs"
        )
    if args.ocr_cache_dir is not None:
        try:
            validate_client_workflow_run(
                context,
                expected_workflow_id="previdenza-inps",
                output_dir=args.ocr_cache_dir,
            )
        except AssuranceContractError as exc:
            raise AssuranceContractError(
                "OCR cache path must stay inside the current run outputs"
            ) from exc
    for label, path in (
        ("OCR detection model", args.ocr_detection_model_dir),
        ("OCR recognition model", args.ocr_recognition_model_dir),
    ):
        if path is None:
            continue
        try:
            validate_client_workflow_run(
                context,
                expected_workflow_id="previdenza-inps",
                output_dir=path,
            )
            continue
        except AssuranceContractError:
            pass
        try:
            validate_client_workflow_run(
                context,
                expected_workflow_id="previdenza-inps",
                input_paths=[path],
            )
        except AssuranceContractError as exc:
            raise AssuranceContractError(
                f"{label} path must be an exact receipt or stay inside the "
                "current run outputs"
            ) from exc


def _named_paths(input_dir: Path, names: frozenset[str]) -> set[Path]:
    """Find connector-controlled names recursively without following file links."""

    root = input_dir.expanduser().resolve()
    if not root.is_dir():
        return set()
    folded_names = {name.casefold() for name in names}
    return {path for path in root.rglob("*") if path.name.casefold() in folded_names}


def _looks_like_portal_export_receipt(path: Path) -> bool:
    """Detect private export receipts by their fixed structural markers.

    This deterministic gate is justified by auditability: registration and
    provenance metadata must never silently become ordinary case evidence because a
    manifest type was altered. It does not interpret document meaning.
    """

    if path.is_symlink() or not path.is_file():
        return True
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_PRIVATE_RECEIPT_INSPECTION_BYTES + 1)
    except OSError:
        return True

    inspected = raw[:MAX_PRIVATE_RECEIPT_INSPECTION_BYTES]
    try:
        payload = json.loads(inspected.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, dict):
        keys = set(map(str, payload))
        if payload.get("manifest_type") == PORTAL_EXPORT_MANIFEST_TYPE:
            return True
        if len(keys.intersection(PORTAL_EXPORT_RECEIPT_MARKERS)) >= 2:
            return True

    raw_markers = sum(
        f'"{marker}"'.encode("utf-8") in inspected
        for marker in PORTAL_EXPORT_RECEIPT_MARKERS
    )
    return raw_markers >= 2


def _portal_export_receipt_paths(input_dir: Path) -> set[Path]:
    """Return nested or root private portal receipt candidates."""

    root = input_dir.expanduser().resolve()
    if not root.is_dir():
        return set()
    private_names = {name.casefold() for name in PORTAL_PRIVATE_RECEIPT_NAMES}
    candidates: set[Path] = set()
    for path in root.rglob("*"):
        name = path.name.casefold()
        if name in private_names:
            candidates.add(path)
        elif name == PORTAL_EXPORT_MANIFEST_NAME and _looks_like_portal_export_receipt(
            path
        ):
            candidates.add(path)
    return candidates


def _portal_export_artifact_paths(input_dir: Path) -> set[Path]:
    """Find registrar-controlled artifacts, including incomplete copy outputs."""

    root = input_dir.expanduser().resolve()
    if not root.is_dir():
        return set()
    return {
        path
        for path in root.rglob("*")
        if path.name.casefold().startswith(PORTAL_EXPORT_ARTIFACT_PREFIX)
    }


def _initial_run_intake(
    args: argparse.Namespace,
    output_dir: Path,
    context: dict[str, Any],
    ocr_language: str,
    portal_export: dict[str, Any] | None,
) -> dict[str, Any]:
    """Create the durable preflight record before any optional model download."""

    connector_used = False
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "plugin": "previdenza-inps",
        "workflow": "previdenza-inps",
        "status": "inventory_in_progress",
        "run_id": context["run_id"],
        "created_at": context["created_at"],
        "path_reference": "run_root_relative",
        "input_paths": [_run_relative_path(args.input_dir, Path(context["run_root"]))],
        "output_dir": _run_relative_path(output_dir, Path(context["run_root"])),
        "working_language": args.language,
        "reference_date": args.reference_date or None,
        "assumptions": [],
        "material_decisions": {
            "professional_question_confirmed": False,
            "framework_confirmed": False,
            "period_scope_confirmed": False,
            "ambiguous_terms_resolved": False,
        },
        "decision_log": [],
        "data_posture": {
            "local_only": not args.allow_ocr_model_download and not connector_used,
            "network_calls_by_scripts": connector_used,
            "network_access_allowed_for_model_weights": (args.allow_ocr_model_download),
            "local_files_read": [
                _run_relative_path(args.input_dir, Path(context["run_root"]))
            ],
            "external_connectors_used": [],
            "external_routes_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "semantic_model_processing": "outside_inventory_script",
            "ocr": {
                "enabled": not args.no_ocr,
                "engine": "paddleocr",
                "language": ocr_language,
                "attempt_location": "not_run",
                "attempted_page_count": 0,
                "successful_page_count": 0,
                "case_content_network_transfer": False,
                "model_download_allowed": args.allow_ocr_model_download,
                "model_network_used": False,
                "visual_confirmation_required": None,
            },
        },
    }
    if portal_export is None:
        return payload

    posture = payload["data_posture"]
    posture["acquisition_channels_used"] = []
    payload["execution_trace"] = []

    if portal_export is not None:
        posture["acquisition_channels_used"].append("inps_registered_local_export")
        posture["portal_export_receipt"] = {
            "registration_id": portal_export["registration_id"],
            "registered_at": portal_export["created_at"],
            "source_origin": portal_export["source_origin"],
            "manifest_sha256": portal_export["manifest_sha256"],
            "artifact_count": len(portal_export["artifacts"]),
            **portal_export["safety"],
        }
        payload["execution_trace"].append(
            {
                "step_id": "previdenza_inps_portal_export_registration",
                "kind": "deterministic_export_registration",
                "status": "passed",
                "execution_location": "cowork_connected_folder",
                "command": "python scripts/register_portal_export.py",
                "inputs": ["locally_supplied_official_portal_exports"],
                "outputs": [
                    "portal_export_manifest",
                    "registered_portal_exports",
                ],
            }
        )

    return payload


def _load_portal_export(
    input_dir: Path, manifest_path: Path | None
) -> dict[str, Any] | None:
    """Verify and load an explicitly declared official-export receipt."""

    resolved_input = input_dir.expanduser().resolve()
    expected_manifest = resolved_input / PORTAL_EXPORT_MANIFEST_NAME
    receipt_paths = _portal_export_receipt_paths(input_dir)
    artifact_paths = _portal_export_artifact_paths(input_dir)
    if manifest_path is None:
        if receipt_paths or artifact_paths:
            raise PortalExportError(
                "registered portal export receipts or artifacts require the exact "
                "root manifest via --portal-export-manifest"
            )
        return None

    resolved_manifest = manifest_path.expanduser().resolve()
    if resolved_manifest != expected_manifest:
        raise PortalExportError(
            "--portal-export-manifest must identify manifest.json inside input_dir"
        )
    if {path.expanduser().resolve() for path in receipt_paths} != {expected_manifest}:
        raise PortalExportError(
            "nested or additional private portal receipts are not allowed"
        )
    payload = verify_portal_export(resolved_input)
    payload["manifest_sha256"] = hashlib.sha256(
        resolved_manifest.read_bytes()
    ).hexdigest()
    return payload


def main(argv: list[str] | None = None) -> int:
    """Write the deterministic evidence inventory for one input folder."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument(
        "--language", choices=("it", "en", "fr", "de", "es"), default="it"
    )
    parser.add_argument("--reference-date", default="")
    parser.add_argument(
        "--portal-export-manifest",
        type=Path,
        help=(
            "Verified manifest.json created by register_portal_export.py inside "
            "input_dir."
        ),
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="Do not attempt local PaddleOCR on scanned PDF pages or images.",
    )
    parser.add_argument(
        "--ocr-language",
        choices=("it", "en", "fr", "de", "es"),
        help="OCR language; defaults to --language.",
    )
    parser.add_argument("--ocr-cache-dir", type=Path)
    parser.add_argument("--ocr-detection-model-dir", type=Path)
    parser.add_argument("--ocr-recognition-model-dir", type=Path)
    parser.add_argument(
        "--allow-ocr-model-download",
        action="store_true",
        help="Explicitly select the optional OCR model-weight download route.",
    )
    args = parser.parse_args(argv)
    input_paths = [args.input_dir]
    if args.portal_export_manifest is not None:
        input_paths.append(args.portal_export_manifest)
    try:
        context = load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="previdenza-inps",
            input_paths=input_paths,
            output_dir=args.output_dir,
        )
        _authorize_managed_ocr_paths(args, context)
    except AssuranceContractError as exc:
        LOGGER.error("CLIENT_ENGAGEMENT_BLOCKED: %s", exc)
        return 1
    ocr_language = args.ocr_language or args.language

    try:
        portal_export = _load_portal_export(args.input_dir, args.portal_export_manifest)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1

    try:
        output_dir = ensure_safe_output_dir(args.output_dir, plugin_root=PLUGIN_ROOT)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1

    run_intake = _initial_run_intake(args, output_dir, context, ocr_language, portal_export)
    write_json(output_dir / "run_intake.json", run_intake)
    try:
        result = extract_case_documents(
            args.input_dir,
            output_dir,
            enable_ocr=not args.no_ocr,
            ocr_language=ocr_language,
            allow_ocr_model_download=args.allow_ocr_model_download,
            ocr_cache_dir=args.ocr_cache_dir,
            ocr_detection_model_dir=args.ocr_detection_model_dir,
            ocr_recognition_model_dir=args.ocr_recognition_model_dir,
            visual_confirmation_methods=None,
            excluded_paths=(
                {args.portal_export_manifest.expanduser().resolve()}
                if args.portal_export_manifest is not None
                else None
            ),
            ocr_excluded_paths=None,
            input_dir_reference=_run_relative_path(
                args.input_dir, Path(context["run_root"])
            ),
            output_dir_reference=_run_relative_path(
                output_dir, Path(context["run_root"])
            ),
            allow_implicit_ocr_model_paths=False,
        )
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        run_intake["status"] = "inventory_failed"
        run_intake["completed_at"] = _utc_now()
        run_intake["failure"] = {"error_type": type(exc).__name__}
        write_json(output_dir / "run_intake.json", run_intake)
        LOGGER.error("%s", exc)
        return 1

    ocr_summary = result.inventory["ocr"]
    data_posture = run_intake["data_posture"]
    connector_used = bool(data_posture["external_connectors_used"])
    data_posture["local_only"] = not ocr_summary["network_used"] and not connector_used
    data_posture["network_calls_by_scripts"] = (
        ocr_summary["network_used"] or connector_used
    )
    ocr_posture = data_posture["ocr"]
    ocr_posture["attempt_location"] = (
        "local_process" if ocr_summary["attempted_page_count"] else "not_run"
    )
    ocr_posture["attempted_page_count"] = ocr_summary["attempted_page_count"]
    ocr_posture["successful_page_count"] = ocr_summary["successful_page_count"]
    ocr_posture["model_network_used"] = ocr_summary["network_used"]
    ocr_posture["visual_confirmation_required"] = bool(
        ocr_summary["visual_confirmation_required_fragment_count"]
    )
    run_intake["status"] = "inventory_complete"
    run_intake["completed_at"] = _utc_now()
    write_json(output_dir / "run_intake.json", run_intake)
    LOGGER.info(
        "Inventoried %s document(s); %s readable.",
        result.inventory["document_count"],
        result.inventory["readable_document_count"],
    )
    return 0 if result.inventory["readable_document_count"] else 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
