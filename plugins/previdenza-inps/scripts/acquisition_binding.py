"""Build immutable acquisition-provenance bindings for an INPS case run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

__all__ = [
    "AcquisitionBindingError",
    "build_acquisition_binding",
    "compare_acquisition_bindings",
]


class AcquisitionBindingError(ValueError):
    """Raised when local acquisition provenance is missing or inconsistent."""


_KNOWN_CHANNELS = {
    "inps_conditional_browser_capture",
    "inps_registered_local_export",
}
_KNOWN_CONNECTORS = {"inps_browser_read_only"}
_EXTERNAL_ROUTE_FIELDS = {
    "route",
    "destination_or_origin",
    "payload_category",
    "network_used",
    "access_basis",
}
_OCR_PROJECTION_FIELDS = (
    "enabled",
    "engine",
    "language",
    "attempt_location",
    "attempted_page_count",
    "successful_page_count",
    "case_content_network_transfer",
    "model_download_allowed",
    "model_network_used",
    "visual_confirmation_required",
)


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise AcquisitionBindingError(f"{label} must be a regular local file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcquisitionBindingError(f"{label} must contain readable JSON") from exc
    if not isinstance(value, dict):
        raise AcquisitionBindingError(f"{label} must contain a JSON object")
    return value


def _string_set(value: Any, *, field: str, allowed: set[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise AcquisitionBindingError(f"{field} must be an array of strings")
    if len(value) != len(set(value)):
        raise AcquisitionBindingError(f"{field} must not contain duplicates")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise AcquisitionBindingError(f"{field} contains an unsupported value")
    return sorted(value)


def _boolean(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise AcquisitionBindingError(f"{field} must be boolean")
    return value


def _external_routes(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AcquisitionBindingError(
            "data_posture.external_routes_used must be an array"
        )
    routes: list[dict[str, Any]] = []
    for index, record in enumerate(value):
        field = f"data_posture.external_routes_used[{index}]"
        if not isinstance(record, dict) or set(record) != _EXTERNAL_ROUTE_FIELDS:
            raise AcquisitionBindingError(f"{field} has invalid fields")
        if record.get("route") != "inps_browser_read_only":
            raise AcquisitionBindingError(f"{field}.route is unsupported")
        for name in ("destination_or_origin", "payload_category"):
            if not isinstance(record.get(name), str) or not record[name].strip():
                raise AcquisitionBindingError(f"{field}.{name} must be non-empty")
        if record.get("network_used") is not True:
            raise AcquisitionBindingError(f"{field}.network_used must be true")
        access_basis = record.get("access_basis")
        if access_basis is not None and (
            not isinstance(access_basis, str) or not access_basis.strip()
        ):
            raise AcquisitionBindingError(
                f"{field}.access_basis must be null or non-empty"
            )
        routes.append(dict(record))
    return routes


def _receipt(
    posture: dict[str, Any], *, name: str, channel: str
) -> dict[str, Any] | None:
    value = posture.get(name)
    channels = posture["acquisition_channels_used"]
    if value is None:
        if channel in channels:
            raise AcquisitionBindingError(f"data_posture.{name} is required")
        return None
    if not isinstance(value, dict) or not value:
        raise AcquisitionBindingError(f"data_posture.{name} must be an object")
    if channel not in channels:
        raise AcquisitionBindingError(
            f"data_posture.{name} requires acquisition channel {channel}"
        )
    manifest_hash = value.get("manifest_sha256")
    if (
        not isinstance(manifest_hash, str)
        or len(manifest_hash) != 64
        or any(character not in "0123456789abcdef" for character in manifest_hash)
    ):
        raise AcquisitionBindingError(
            f"data_posture.{name}.manifest_sha256 must be lowercase SHA-256"
        )
    return value


def _acquisition_projection(run_intake: dict[str, Any]) -> dict[str, Any]:
    if run_intake.get("plugin") != "previdenza-inps":
        raise AcquisitionBindingError('run_intake.plugin must be "previdenza-inps"')
    if run_intake.get("workflow") != "previdenza-inps":
        raise AcquisitionBindingError('run_intake.workflow must be "previdenza-inps"')
    if run_intake.get("status") != "inventory_complete":
        raise AcquisitionBindingError("run_intake.status must be inventory_complete")
    run_id = run_intake.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise AcquisitionBindingError("run_intake.run_id must be non-empty")
    posture_value = run_intake.get("data_posture")
    if not isinstance(posture_value, dict):
        raise AcquisitionBindingError("run_intake.data_posture must be an object")
    posture = dict(posture_value)
    channels = _string_set(
        posture.get("acquisition_channels_used"),
        field="data_posture.acquisition_channels_used",
        allowed=_KNOWN_CHANNELS,
    )
    connectors = _string_set(
        posture.get("external_connectors_used"),
        field="data_posture.external_connectors_used",
        allowed=_KNOWN_CONNECTORS,
    )
    external_routes = _external_routes(posture.get("external_routes_used"))
    posture["acquisition_channels_used"] = channels
    capture_receipt = _receipt(
        posture,
        name="portal_capture_receipt",
        channel="inps_conditional_browser_capture",
    )
    export_receipt = _receipt(
        posture,
        name="portal_export_receipt",
        channel="inps_registered_local_export",
    )
    if capture_receipt is not None and connectors != ["inps_browser_read_only"]:
        raise AcquisitionBindingError(
            "portal capture requires the inps_browser_read_only connector"
        )
    if capture_receipt is None and connectors:
        raise AcquisitionBindingError(
            "external connector posture requires a portal capture receipt"
        )
    if capture_receipt is not None and len(external_routes) != 1:
        raise AcquisitionBindingError(
            "portal capture requires one factual external route record"
        )
    if capture_receipt is not None and external_routes:
        route = external_routes[0]
        if route["destination_or_origin"] != capture_receipt.get("approved_origin"):
            raise AcquisitionBindingError(
                "portal capture route origin must match its receipt"
            )
        if (
            route["payload_category"]
            != "visible_page_content_received_from_selected_tab"
        ):
            raise AcquisitionBindingError(
                "portal capture route payload category is unsupported"
            )
        if capture_receipt.get("route_selected") is not True:
            raise AcquisitionBindingError(
                "portal capture receipt must record route selection"
            )
    if capture_receipt is None and external_routes:
        raise AcquisitionBindingError(
            "external route record requires a portal capture receipt"
        )
    local_only = _boolean(posture.get("local_only"), field="data_posture.local_only")
    network_calls = _boolean(
        posture.get("network_calls_by_scripts"),
        field="data_posture.network_calls_by_scripts",
    )
    ocr_value = posture.get("ocr")
    if not isinstance(ocr_value, dict):
        raise AcquisitionBindingError("data_posture.ocr must be an object")
    ocr = {name: ocr_value.get(name) for name in _OCR_PROJECTION_FIELDS}
    ocr_network = ocr.get("model_network_used") is True
    if connectors and (local_only or not network_calls):
        raise AcquisitionBindingError(
            "external connector use must remain non-local and network-recorded"
        )
    if ocr_network and (local_only or not network_calls):
        raise AcquisitionBindingError(
            "OCR model network use must remain non-local and network-recorded"
        )
    return {
        "schema_version": run_intake.get("schema_version"),
        "plugin": "previdenza-inps",
        "workflow": "previdenza-inps",
        "run_id": run_id.strip(),
        "status": "inventory_complete",
        "created_at": run_intake.get("created_at"),
        "completed_at": run_intake.get("completed_at"),
        "reference_date": run_intake.get("reference_date"),
        "data_posture": {
            "local_only": local_only,
            "network_calls_by_scripts": network_calls,
            "network_access_allowed_for_model_weights": posture.get(
                "network_access_allowed_for_model_weights"
            ),
            "acquisition_channels_used": channels,
            "external_connectors_used": connectors,
            "external_routes_used": external_routes,
            "portal_capture_receipt": capture_receipt,
            "portal_export_receipt": export_receipt,
            "ocr": ocr,
        },
    }


def build_acquisition_binding(
    file_inventory_path: Path, run_intake_path: Path
) -> dict[str, Any]:
    """Bind exact inventory bytes and fixed acquisition posture for later audits.

    The deterministic projection is justified by auditability: package-owned trace
    fields may evolve, while acquisition channels, route facts, and receipts must not.
    """

    inventory = _load_object(file_inventory_path, label="file_inventory.json")
    run_intake = _load_object(run_intake_path, label="run_intake.json")
    if inventory.get("schema_version") is None:
        raise AcquisitionBindingError("file_inventory.json lacks schema_version")
    projection = _acquisition_projection(run_intake)
    receipts: list[dict[str, str]] = []
    posture = projection["data_posture"]
    for name in ("portal_capture_receipt", "portal_export_receipt"):
        receipt = posture[name]
        if receipt is not None:
            receipts.append({"kind": name, "sha256": _canonical_sha256(receipt)})
    source_file_hash = _file_sha256(run_intake_path)
    core = {
        "schema_version": "1.0",
        "run_id": projection["run_id"],
        "file_inventory_sha256": _file_sha256(file_inventory_path),
        "run_intake_acquisition_sha256": _canonical_sha256(projection),
        "portal_receipts": receipts,
    }
    return {
        **core,
        "run_intake_source_sha256": source_file_hash,
        "binding_sha256": _canonical_sha256(core),
    }


def compare_acquisition_bindings(
    expected: Any, current: dict[str, Any]
) -> list[dict[str, str]]:
    """Return fail-closed issues for any immutable acquisition mismatch."""

    if not isinstance(expected, dict):
        return [
            {
                "code": "missing_acquisition_binding",
                "field": "case_records.validation.acquisition_binding",
                "message": "Validated case records must bind inventory and acquisition posture.",
            }
        ]
    issues: list[dict[str, str]] = []
    for name in (
        "run_id",
        "file_inventory_sha256",
        "run_intake_acquisition_sha256",
        "portal_receipts",
        "binding_sha256",
    ):
        if expected.get(name) != current.get(name):
            issues.append(
                {
                    "code": f"acquisition_{name}_mismatch",
                    "field": f"case_records.validation.acquisition_binding.{name}",
                    "message": "Acquisition provenance changed after case-record validation.",
                }
            )
    return issues
