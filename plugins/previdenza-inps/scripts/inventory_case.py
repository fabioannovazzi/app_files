#!/usr/bin/env python3
"""Inventory and extract local documents for an INPS case review."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from capture_portal_snapshot import MANIFEST_NAME as PORTAL_CAPTURE_MANIFEST_NAME
from capture_portal_snapshot import SCREENSHOT_NAME as PORTAL_SCREENSHOT_NAME
from capture_portal_snapshot import VISIBLE_TEXT_NAME as PORTAL_VISIBLE_TEXT_NAME
from capture_portal_snapshot import (
    PortalCaptureError,
    verify_portal_snapshot,
)
from case_core import ensure_safe_output_dir, extract_case_documents, write_json
from register_portal_export import MANIFEST_NAME as PORTAL_EXPORT_MANIFEST_NAME
from register_portal_export import MANIFEST_TYPE as PORTAL_EXPORT_MANIFEST_TYPE
from register_portal_export import PortalExportError, verify_portal_export

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PORTAL_CAPTURE_RESERVED_NAMES = frozenset(
    {
        PORTAL_CAPTURE_MANIFEST_NAME,
        PORTAL_SCREENSHOT_NAME,
        PORTAL_VISIBLE_TEXT_NAME,
    }
)
PORTAL_EXPORT_RECEIPT_MARKERS = frozenset(
    {
        "manifest_type",
        "source_origin",
        "authority",
        "processing_approval",
        "safety",
        "artifacts",
        "registration_id",
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


def _named_paths(input_dir: Path, names: frozenset[str]) -> set[Path]:
    """Find connector-controlled names recursively without following file links."""

    root = input_dir.expanduser().resolve()
    if not root.is_dir():
        return set()
    folded_names = {name.casefold() for name in names}
    return {path for path in root.rglob("*") if path.name.casefold() in folded_names}


def _looks_like_portal_export_receipt(path: Path) -> bool:
    """Detect private export receipts by their fixed structural markers.

    This deterministic gate is justified by auditability: connector approval
    metadata must never silently become ordinary case evidence merely because a
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
    ocr_language: str,
    portal_capture: dict[str, Any] | None,
    portal_export: dict[str, Any] | None,
) -> dict[str, Any]:
    """Create the durable preflight record before any optional model download."""

    connector_used = portal_capture is not None
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "plugin": "previdenza-inps",
        "workflow": "previdenza-inps",
        "status": "inventory_in_progress",
        "run_id": (
            "previdenza-inps-" f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        ),
        "created_at": _utc_now(),
        "input_paths": [args.input_dir.expanduser().resolve().as_posix()],
        "output_dir": output_dir.as_posix(),
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
        "processing_authorization": {
            "studio_processing_authorized": False,
            "model_processing_approved": False,
            "processor_scope": None,
            "approved_by_id": None,
            "approved_by_role": None,
            "recorded_at": None,
            "basis": None,
            "personal_data_minimized": False,
        },
        "data_posture": {
            "local_only": not args.allow_ocr_model_download and not connector_used,
            "network_calls_by_scripts": connector_used,
            "network_access_allowed_for_model_weights": (args.allow_ocr_model_download),
            "local_files_read": [args.input_dir.expanduser().resolve().as_posix()],
            "model_excerpts_sent": [],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "semantic_model_processing": "not_authorized_by_inventory_step",
            "ocr": {
                "enabled": not args.no_ocr,
                "engine": "paddleocr",
                "language": ocr_language,
                "attempt_location": "not_run",
                "attempted_page_count": 0,
                "successful_page_count": 0,
                "case_content_network_transfer": False,
                "model_download_allowed": args.allow_ocr_model_download,
                "model_download_approval_id": (
                    args.ocr_model_download_approval_id or None
                ),
                "model_network_used": False,
                "visual_confirmation_required": None,
            },
        },
    }
    if portal_capture is None and portal_export is None:
        return payload

    posture = payload["data_posture"]
    posture["acquisition_channels_used"] = []
    payload["execution_trace"] = []

    if portal_export is not None:
        processing = portal_export["processing_approval"]
        authority = portal_export["authority"]
        payload["processing_authorization"].update(
            {
                "studio_processing_authorized": True,
                "approved_by_id": processing["approved_by_id"],
                "approved_by_role": processing["approved_by_role"],
                "recorded_at": processing["recorded_at"],
                "basis": processing["approval_basis"],
            }
        )
        posture["acquisition_channels_used"].append("inps_official_user_export")
        posture["portal_export_receipt"] = {
            "registration_id": portal_export["registration_id"],
            "registered_at": portal_export["created_at"],
            "source_origin": portal_export["source_origin"],
            "manifest_sha256": portal_export["manifest_sha256"],
            "artifact_count": len(portal_export["artifacts"]),
            "human_authority_confirmed": authority["human_authority_confirmed"],
            "profile_authority_confirmed": authority["profile_authority_confirmed"],
            "delegation_authority_confirmed": authority[
                "delegation_authority_confirmed"
            ],
            **portal_export["safety"],
        }
        payload["execution_trace"].append(
            {
                "step_id": "previdenza_inps_portal_export_registration",
                "kind": "deterministic_export_registration",
                "status": "passed",
                "execution_location": "local_codex_workspace",
                "command": "python scripts/register_portal_export.py",
                "inputs": ["user_downloaded_official_portal_exports"],
                "outputs": [
                    "portal_export_manifest",
                    "registered_portal_exports",
                ],
            }
        )

    if portal_capture is None:
        return payload

    approval = portal_capture["approval"]
    payload["processing_authorization"].update(
        {
            "studio_processing_authorized": True,
            "approved_by_id": approval["approved_by"],
            "approved_by_role": approval["approved_by_role"],
            "recorded_at": approval["approved_at"],
            "basis": approval["processing_authority_basis"],
        }
    )
    posture["acquisition_channels_used"].append("inps_conditional_browser_capture")
    posture["external_connectors_used"] = ["inps_browser_read_only"]
    posture["external_execution_approval"] = {
        "approved": True,
        "approved_at": approval["approved_at"],
        "approved_by": approval["approved_by"],
        "reason": approval["reason"],
        "scope": approval["scope"],
    }
    posture["portal_capture_receipt"] = {
        "capture_id": portal_capture["capture_id"],
        "captured_at": portal_capture["captured_at"],
        "approved_origin": portal_capture["approved_origin"],
        "source_url_sha256": portal_capture["source_url_sha256"],
        "manifest_sha256": portal_capture["manifest_sha256"],
        "case_content_uploaded": False,
        "browser_state_exported": False,
        "navigation_performed": False,
        "page_actions_performed": False,
        "own_or_authorized_credentials_confirmed": approval[
            "own_or_authorized_credentials_confirmed"
        ],
        "human_access_authority_confirmed": approval[
            "human_access_authority_confirmed"
        ],
        "human_access_authority_basis_sha256": hashlib.sha256(
            approval["human_access_authority_basis"].encode("utf-8")
        ).hexdigest(),
        "portal_profile_authority_confirmed": approval[
            "portal_profile_authority_confirmed"
        ],
        "portal_profile_authority_basis_sha256": hashlib.sha256(
            approval["portal_profile_authority_basis"].encode("utf-8")
        ).hexdigest(),
        "delegation_or_subject_authority_confirmed": approval[
            "delegation_or_subject_authority_confirmed"
        ],
        "delegation_or_subject_authority_basis_sha256": hashlib.sha256(
            approval["delegation_or_subject_authority_basis"].encode("utf-8")
        ).hexdigest(),
        "client_data_processing_authorized_confirmed": approval[
            "client_data_processing_authorized_confirmed"
        ],
        "portal_capture_permission_confirmed": True,
        "portal_permission_basis_sha256": hashlib.sha256(
            approval["portal_permission_basis"].encode("utf-8")
        ).hexdigest(),
    }
    payload["execution_trace"].append(
        {
            "step_id": "previdenza_inps_portal_capture",
            "kind": "read_only_browser_capture",
            "status": "passed",
            "execution_location": "external_connector",
            "command": "python scripts/capture_portal_snapshot.py",
            "inputs": ["approved_open_browser_tab"],
            "outputs": [
                PORTAL_CAPTURE_MANIFEST_NAME,
                "portal_full_page.png",
                PORTAL_VISIBLE_TEXT_NAME,
            ],
        }
    )
    return payload


def _load_portal_capture(
    input_dir: Path, manifest_path: Path | None
) -> dict[str, Any] | None:
    """Verify and load an explicitly declared portal capture receipt."""

    resolved_input = input_dir.expanduser().resolve()
    expected_manifest = resolved_input / PORTAL_CAPTURE_MANIFEST_NAME
    reserved_paths = _named_paths(input_dir, PORTAL_CAPTURE_RESERVED_NAMES)
    if manifest_path is None:
        if reserved_paths:
            raise PortalCaptureError(
                "portal capture artifacts are a reserved atomic set and require "
                "the exact root manifest via --portal-capture-manifest"
            )
        return None

    resolved_manifest = manifest_path.expanduser().resolve()
    if resolved_manifest != expected_manifest:
        raise PortalCaptureError(
            "--portal-capture-manifest must identify the manifest inside input_dir"
        )
    expected_reserved = {
        resolved_input / PORTAL_CAPTURE_MANIFEST_NAME,
        resolved_input / PORTAL_SCREENSHOT_NAME,
        resolved_input / PORTAL_VISIBLE_TEXT_NAME,
    }
    resolved_reserved = {path.expanduser().resolve() for path in reserved_paths}
    if resolved_reserved != expected_reserved:
        raise PortalCaptureError(
            "portal capture artifacts must be the exact atomic set at input_dir root"
        )
    verify_portal_snapshot(resolved_input)
    try:
        payload = json.loads(resolved_manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PortalCaptureError("portal capture manifest is unreadable") from exc
    if not isinstance(payload, dict):
        raise PortalCaptureError("portal capture manifest must contain an object")
    payload["manifest_sha256"] = hashlib.sha256(
        resolved_manifest.read_bytes()
    ).hexdigest()
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
    parser.add_argument("--language", choices=("it", "en", "fr", "de"), default="it")
    parser.add_argument("--reference-date", default="")
    parser.add_argument(
        "--portal-capture-manifest",
        type=Path,
        help=(
            "Verified portal_capture_manifest.json inside input_dir; required "
            "for an authorized read-only browser capture."
        ),
    )
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
        choices=("it", "en", "fr", "de"),
        help="OCR language; defaults to --language.",
    )
    parser.add_argument("--ocr-cache-dir", type=Path)
    parser.add_argument("--ocr-detection-model-dir", type=Path)
    parser.add_argument("--ocr-recognition-model-dir", type=Path)
    parser.add_argument(
        "--allow-ocr-model-download",
        action="store_true",
        help="Allow downloading OCR model weights after explicit approval.",
    )
    parser.add_argument(
        "--ocr-model-download-approval-id",
        default="",
        help="Stable actor or approval ID required when model download is allowed.",
    )
    args = parser.parse_args(argv)
    if args.portal_capture_manifest and args.portal_export_manifest:
        parser.error(
            "--portal-capture-manifest and --portal-export-manifest are mutually exclusive"
        )
    if (
        args.allow_ocr_model_download
        and not args.ocr_model_download_approval_id.strip()
    ):
        parser.error(
            "--ocr-model-download-approval-id is required with "
            "--allow-ocr-model-download"
        )
    if (
        args.ocr_model_download_approval_id.strip()
        and not args.allow_ocr_model_download
    ):
        parser.error(
            "--ocr-model-download-approval-id requires " "--allow-ocr-model-download"
        )

    ocr_language = args.ocr_language or args.language

    try:
        portal_capture = _load_portal_capture(
            args.input_dir, args.portal_capture_manifest
        )
        portal_export = _load_portal_export(args.input_dir, args.portal_export_manifest)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1

    try:
        output_dir = ensure_safe_output_dir(args.output_dir, plugin_root=PLUGIN_ROOT)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1

    run_intake = _initial_run_intake(
        args, output_dir, ocr_language, portal_capture, portal_export
    )
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
            visual_confirmation_methods=(
                {
                    args.input_dir.expanduser().resolve()
                    / PORTAL_VISIBLE_TEXT_NAME: "browser_visible_text"
                }
                if portal_capture is not None
                else None
            ),
            excluded_paths=(
                {
                    (
                        args.portal_capture_manifest.expanduser().resolve()
                        if args.portal_capture_manifest is not None
                        else (
                            args.portal_export_manifest.expanduser().resolve()
                            if args.portal_export_manifest is not None
                            else args.input_dir.expanduser().resolve()
                            / PORTAL_CAPTURE_MANIFEST_NAME
                        )
                    )
                }
                if portal_capture is not None or portal_export is not None
                else None
            ),
            ocr_excluded_paths=(
                {args.input_dir.expanduser().resolve() / PORTAL_SCREENSHOT_NAME}
                if portal_capture is not None
                else None
            ),
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
