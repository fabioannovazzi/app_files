"""Apply validated Codex mappings to the existing server-backed PDP store."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from attribute_reporting import (
    validate_mapping_payloads,
    validate_mapping_review_payloads,
    verify_mapping_tasks_against_source,
)

__all__ = ["main", "mapping_record_specs"]

LOGGER = logging.getLogger(__name__)


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    if payload.get("schema_version") != (
        "attribute_reporting.validated_mapping_decisions.v1"
    ):
        raise ValueError("Unsupported validated mapping schema")
    if payload.get("status") != "valid":
        raise ValueError("Mapping payload is not validated")
    return payload


def _stable_validation(payload: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "schema_version",
        "taxonomy_snapshot",
        "agent",
        "tasks_sha256",
        "decisions_sha256",
        "status",
        "mapping_count",
        "mappings",
    )
    return {key: payload.get(key) for key in keys}


def _private_receipt_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    for parent in (resolved.parent, *resolved.parent.parents):
        if (parent / ".git").exists():
            raise ValueError(
                "Mapping apply receipts cannot be written inside a Git workspace"
            )
    return resolved


def _write_receipt(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically replace a local apply receipt."""

    path.parent.mkdir(parents=True, exist_ok=True)
    operation_id = str(payload.get("operation_id") or "pending")
    temporary = path.with_name(f".{path.name}.{operation_id}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _preflight_receipt(
    path: Path,
    receipt: Mapping[str, Any],
) -> None:
    """Create a durable pending receipt before consulting the target database."""

    operation_id = str(receipt["operation_id"])
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            raise ValueError("Existing mapping receipt is not a JSON object")
        if existing.get("operation_id") != operation_id:
            raise ValueError("Existing mapping receipt belongs to another operation")
        if existing.get("status") not in {"applied", "pending"}:
            raise ValueError("Existing mapping receipt has an invalid status")
    _write_receipt(path, {**dict(receipt), "status": "pending"})


def _configure_app_import(app_root: Path) -> None:
    root_text = str(app_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)


def _single_value_for_mapping(
    mapping: Mapping[str, Any],
) -> tuple[str | None, str | None, str]:
    status = str(mapping["status"])
    if status == "mapped":
        labels = mapping.get("value_labels")
        if not isinstance(labels, list) or len(labels) != 1:
            raise ValueError("Single-select mapping requires one validated value")
        return str(labels[0]), None, "codex_mapped"
    if status == "oov_candidate":
        return "not in taxonomy", str(mapping["oov_candidate"]), "codex_oov_candidate"
    if status == "no_value":
        return None, None, "codex_no_value"
    return None, None, "codex_unable_to_determine"


def mapping_record_specs(mapping: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expand one validated mapping into exact persisted attribute cells."""
    selection = str(mapping.get("selection") or "single")
    if selection == "single":
        value, oov_candidate, decision_rule = _single_value_for_mapping(mapping)
        return [
            {
                "attribute_id": str(mapping["attribute_id"]),
                "attribute_label": str(mapping.get("attribute_label") or ""),
                "value": value,
                "oov_candidate": oov_candidate,
                "note": (
                    None if mapping["status"] == "mapped" else str(mapping["status"])
                ),
                "decision_rule": decision_rule,
                "leaf_value_id": mapping.get("value_id"),
            }
        ]
    if selection != "multi":
        raise ValueError(f"Unsupported mapping selection: {selection}")

    allowed_values = mapping.get("allowed_values")
    selected_ids = mapping.get("value_ids")
    if not isinstance(allowed_values, list) or not isinstance(selected_ids, list):
        raise ValueError(
            "Multi-select mapping requires validated allowed/selected values"
        )
    selected = {str(value) for value in selected_ids}
    status = str(mapping["status"])
    base_attribute_id = str(mapping["attribute_id"])
    base_label = str(mapping.get("attribute_label") or base_attribute_id)
    specs: list[dict[str, Any]] = []
    for item in allowed_values:
        if not isinstance(item, dict):
            raise ValueError("Multi-select allowed value is invalid")
        leaf_id = str(item["id"])
        leaf_label = str(item["label"])
        specs.append(
            {
                "attribute_id": f"{base_attribute_id}__{leaf_id}",
                "attribute_label": f"{base_label}: {leaf_label}",
                "value": (
                    "True" if status == "mapped" and leaf_id in selected else "False"
                ),
                "oov_candidate": None,
                "note": None if status == "mapped" else status,
                "decision_rule": "codex_multi_leaf",
                "leaf_value_id": leaf_id,
            }
        )
    flags = {
        "unknown": status in {"no_value", "unable_to_determine"},
        "other": False,
        "not_in_taxonomy": status == "oov_candidate",
    }
    for suffix, enabled in flags.items():
        specs.append(
            {
                "attribute_id": f"{base_attribute_id}__{suffix}",
                "attribute_label": f"{base_label}: {suffix.replace('_', ' ')}",
                "value": "True" if enabled else "False",
                "oov_candidate": (
                    str(mapping.get("oov_candidate") or "")
                    if suffix == "not_in_taxonomy" and enabled
                    else None
                ),
                "note": None if status == "mapped" else status,
                "decision_rule": "codex_multi_state",
                "leaf_value_id": suffix,
            }
        )
    return specs


def main() -> int:
    """Validate taxonomy freshness and atomically append values plus audit rows."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("validated_mappings", type=Path)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--mapping-review", type=Path, required=True)
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        payload = _load_payload(args.validated_mappings)
        app_root = args.app_root.expanduser().resolve()
        _configure_app_import(app_root)
        from modules.add_attributes.attribute_taxonomy import (  # noqa: PLC0415
            get_runtime_attribute_taxonomy,
        )
        from modules.pdp.review_constants import (  # noqa: PLC0415
            DEFAULT_PDP_STORE_PATH,
            enforce_default_pdp_store_path,
        )
        from modules.pdp.store import (  # noqa: PLC0415
            AttributeAuditRecord,
            AttributeValueRecord,
            PDPStore,
        )

        taxonomy = get_runtime_attribute_taxonomy()
        tasks = json.loads(args.tasks.read_text(encoding="utf-8"))
        decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
        mapping_review = json.loads(args.mapping_review.read_text(encoding="utf-8"))
        if not all(
            isinstance(item, dict) for item in (tasks, decisions, mapping_review)
        ):
            raise ValueError(
                "Mapping task, decision, and review files must contain objects"
            )
        expected = validate_mapping_payloads(
            tasks,
            decisions,
            taxonomy=taxonomy,
        )
        if _stable_validation(payload) != _stable_validation(expected):
            raise ValueError(
                "Validated mappings do not match the supplied task and decision files"
            )
        if payload.get("validation_sha256") != expected["validation_sha256"]:
            raise ValueError("Validated mapping checksum does not match")
        review_validation = validate_mapping_review_payloads(
            tasks,
            decisions,
            payload,
            mapping_review,
            taxonomy=taxonomy,
        )
        if review_validation["review_state"] not in {
            "approved",
            "approved_with_caveats",
        }:
            raise ValueError(
                "Independent semantic mapping review does not approve application"
            )
        source_scope = verify_mapping_tasks_against_source(tasks, taxonomy)
        receipt_path = _private_receipt_path(args.receipt)

        snapshot = expected["taxonomy_snapshot"]
        current_version = str(taxonomy.get("version") or "")
        current_sha256 = _canonical_sha256(taxonomy)

        updated_at = datetime.now(timezone.utc).isoformat()
        value_records = []
        audit_records = []
        for raw_mapping in expected.get("mappings") or []:
            mapping = dict(raw_mapping)
            for spec in mapping_record_specs(mapping):
                value_records.append(
                    AttributeValueRecord(
                        retailer=str(mapping["retailer"]),
                        row_type=str(mapping["row_type"]),
                        parent_product_id=str(mapping["parent_product_id"]),
                        variant_id=str(mapping.get("variant_id") or ""),
                        category_key=str(mapping["category_key"]),
                        attribute_id=str(spec["attribute_id"]),
                        attribute_label=str(spec["attribute_label"]) or None,
                        value=spec["value"],
                        oov_candidate=spec["oov_candidate"],
                        note=spec["note"],
                        source="codex",
                        updated_at=updated_at,
                    )
                )
                audit_records.append(
                    AttributeAuditRecord(
                        timestamp=updated_at,
                        source="codex",
                        row_type=str(mapping["row_type"]),
                        retailer=str(mapping["retailer"]),
                        parent_product_id=str(mapping["parent_product_id"]),
                        variant_id=str(mapping.get("variant_id") or ""),
                        attribute_id=str(spec["attribute_id"]),
                        value=spec["value"],
                        decision_rule=str(spec["decision_rule"]),
                        evidence_json=json.dumps(
                            {
                                "task_id": mapping["task_id"],
                                "base_attribute_id": mapping["attribute_id"],
                                "leaf_value_id": spec["leaf_value_id"],
                                "selected_value_ids": mapping["value_ids"],
                                "selected_value_labels": mapping["value_labels"],
                                "taxonomy_version": snapshot["version"],
                                "taxonomy_sha256": snapshot["sha256"],
                                "tasks_sha256": expected["tasks_sha256"],
                                "decisions_sha256": expected["decisions_sha256"],
                                "validation_sha256": expected["validation_sha256"],
                                "mapping_review_sha256": review_validation[
                                    "mapping_review_sha256"
                                ],
                                "mapping_review_validation_sha256": review_validation[
                                    "review_validation_sha256"
                                ],
                                "mapping_review_state": review_validation[
                                    "review_state"
                                ],
                                "mapping_reviewer": review_validation["reviewer"],
                                "source_scope": source_scope,
                                "reason": mapping["reason"],
                                "confidence": mapping["confidence"],
                                "agent": expected["agent"],
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        category_key=str(mapping["category_key"]),
                    )
                )
        operation_id = _canonical_sha256(
            {
                "validation_sha256": expected["validation_sha256"],
                "mapping_review_validation_sha256": review_validation[
                    "review_validation_sha256"
                ],
            }
        )
        receipt = {
            "schema_version": "attribute_reporting.mapping_apply_receipt.v1",
            "operation_id": operation_id,
            "started_at": updated_at,
            "mapping_count": expected["mapping_count"],
            "attribute_value_record_count": len(value_records),
            "source": "codex",
            "taxonomy_version": current_version,
            "taxonomy_sha256": current_sha256,
            "tasks_sha256": expected["tasks_sha256"],
            "decisions_sha256": expected["decisions_sha256"],
            "validation_sha256": expected["validation_sha256"],
            "mapping_review_sha256": review_validation["mapping_review_sha256"],
            "mapping_review_validation_sha256": review_validation[
                "review_validation_sha256"
            ],
            "mapping_review_state": review_validation["review_state"],
            "mapping_reviewer": review_validation["reviewer"],
            "source_scope": source_scope,
            "validated_mappings": str(args.validated_mappings.resolve()),
            "tasks": str(args.tasks.resolve()),
            "decisions": str(args.decisions.resolve()),
            "mapping_review": str(args.mapping_review.resolve()),
        }
        _preflight_receipt(receipt_path, receipt)

        store_path = enforce_default_pdp_store_path(DEFAULT_PDP_STORE_PATH)
        store = PDPStore(store_path)
        wrote_database = store.upsert_attribute_values_with_audit(
            value_records,
            audit_records,
            operation_id=operation_id,
            reject_existing_source_values=True,
        )
        _write_receipt(
            receipt_path,
            {
                **receipt,
                "status": "applied",
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "database_write": "applied" if wrote_database else "already_applied",
            },
        )
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        LOGGER.error("Mapping apply failed: %s", exc)
        return 1
    LOGGER.info(
        "Applied %s validated Codex mapping decisions as %s attribute records",
        expected["mapping_count"],
        len(value_records),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
