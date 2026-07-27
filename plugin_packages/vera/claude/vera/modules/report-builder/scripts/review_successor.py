"""Deterministic replay of Report Builder review successor state.

This module proves that persisted application effects, material edit receipts,
and delivery status derive from the recorded review decisions and current
prepared artifacts.  It does not authenticate who recorded those decisions;
reviewer identity remains an external authority boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

__all__ = ["validate_review_successor"]

SCHEMA_VERSION = "report_builder.review_successor_validation.v1"
ACTION_STATUSES = {
    "accept": "accepted",
    "reject": "rejected",
    "edit": "edited",
    "mark_unclear": "needs_evidence",
    "request_more_documents": "needs_evidence",
    "skip": "skipped",
}
FOLLOWUP_ACTIONS = frozenset({"reject", "mark_unclear", "request_more_documents"})
DECISION_REQUIRED_FIELDS = frozenset(
    {
        "item_id",
        "item_type",
        "title",
        "action",
        "status",
        "decided_at",
    }
)
DECISION_OPTIONAL_FIELDS = frozenset(
    {
        "reviewer_note",
        "edit_value",
        "requested_documents",
        "followup_context",
    }
)
UI_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "plugin",
        "workflow",
        "run_id",
        "review_payload_sha256",
        "decided_at",
        "decision_source",
        "review_payload_path",
        "decisions",
        "decision_count",
        "item_count",
        "status",
    }
)
UI_OPTIONAL_FIELDS = frozenset({"reviewer"})
INTEGRITY_SCHEMA = "report_builder.review_integrity.v4"
HISTORY_SCHEMA = "report_builder.review_history_entry.v2"
INTEGRITY_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "source_index",
        "predecessor_checkpoint",
        "protected_files",
        "payload_digests",
        "implementation_artifact_refs",
        "implementation_receipts",
        "prepared_validation",
        "physical_paths",
        "physical_directories",
        "content_sha256",
    }
)


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return payload


def _require_exact_fields(
    value: Mapping[str, Any],
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
    *,
    label: str,
) -> None:
    observed = set(value)
    if not required <= observed or observed - required - optional:
        raise ValueError(f"Report Builder {label} fields are not exact.")


def _safe_item_id(value: object) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", _clean_text(value))
    return cleaned.strip("-")[:80] or "item"


def _string_list(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"Report Builder {label} must be a string list.")
    if len(value) != len(set(value)):
        raise ValueError(f"Report Builder {label} contains duplicates.")
    return value


def _review_items(review_payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw_items = review_payload.get("items")
    if not isinstance(raw_items, list) or not all(
        isinstance(item, dict) for item in raw_items
    ):
        raise ValueError("Report Builder review items are malformed.")
    items = {
        _clean_text(item.get("id")): item
        for item in raw_items
        if _clean_text(item.get("id"))
    }
    if len(items) != len(raw_items):
        raise ValueError("Report Builder review item identities are not unique.")
    if review_payload.get("item_count") != len(raw_items):
        raise ValueError("Report Builder review item count is stale.")
    return items


def _validate_decision(
    decision: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    decided_at: object,
) -> None:
    _require_exact_fields(
        decision,
        DECISION_REQUIRED_FIELDS,
        DECISION_OPTIONAL_FIELDS,
        label="decision",
    )
    action = _clean_text(decision.get("action"))
    allowed = item.get("allowed_actions")
    if (
        not isinstance(allowed, list)
        or action not in ACTION_STATUSES
        or action not in allowed
        or decision.get("item_id") != item.get("id")
        or decision.get("item_type") != item.get("item_type")
        or decision.get("title") != item.get("title")
        or decision.get("status") != ACTION_STATUSES[action]
        or decision.get("decided_at") != decided_at
    ):
        raise ValueError("Report Builder decision is not review-payload-derived.")
    if action == "edit" and not _clean_text(decision.get("edit_value")):
        raise ValueError("Report Builder edit decision has no value.")
    for field in ("reviewer_note", "edit_value"):
        if field in decision and not isinstance(decision[field], str):
            raise ValueError(f"Report Builder decision {field} is malformed.")
    if "requested_documents" in decision:
        _string_list(
            decision["requested_documents"],
            label="decision requested_documents",
        )
    if "followup_context" in decision and not isinstance(
        decision["followup_context"], Mapping
    ):
        raise ValueError("Report Builder decision followup_context is malformed.")


def _validate_ui_state(
    review_payload: Mapping[str, Any],
    ui_decisions: Mapping[str, Any],
) -> list[dict[str, Any]]:
    _require_exact_fields(
        ui_decisions,
        UI_REQUIRED_FIELDS,
        UI_OPTIONAL_FIELDS,
        label="UI decision",
    )
    items = _review_items(review_payload)
    raw_decisions = ui_decisions.get("decisions")
    if not isinstance(raw_decisions, list) or not all(
        isinstance(decision, dict) for decision in raw_decisions
    ):
        raise ValueError("Report Builder UI decisions are malformed.")
    decision_ids = [_clean_text(decision.get("item_id")) for decision in raw_decisions]
    count = len(raw_decisions)
    expected_status = (
        "pending_review"
        if count == 0
        else "reviewed" if count == len(items) else "partial_review"
    )
    decided_at = ui_decisions.get("decided_at")
    if (
        ui_decisions.get("schema_version") != review_payload.get("schema_version")
        or ui_decisions.get("plugin") != review_payload.get("plugin")
        or ui_decisions.get("workflow") != review_payload.get("workflow")
        or ui_decisions.get("run_id") != review_payload.get("run_id")
        or ui_decisions.get("review_payload_sha256")
        != _canonical_sha256(review_payload)
        or ui_decisions.get("review_payload_path") != "review_payload.json"
        or not _clean_text(ui_decisions.get("decision_source"))
        or ui_decisions.get("decision_count") != count
        or ui_decisions.get("item_count") != len(items)
        or ui_decisions.get("status") != expected_status
        or len(decision_ids) != len(set(decision_ids))
        or (count == 0 and decided_at is not None)
        or (count > 0 and not _clean_text(decided_at))
    ):
        raise ValueError("Report Builder UI decision state is not rederived.")
    if "reviewer" in ui_decisions and not _clean_text(ui_decisions["reviewer"]):
        raise ValueError("Report Builder reviewer reference is malformed.")
    for decision in raw_decisions:
        item = items.get(_clean_text(decision.get("item_id")))
        if item is None:
            raise ValueError("Report Builder decision item does not exist.")
        _validate_decision(decision, item, decided_at=decided_at)
    return raw_decisions


def _item_target(item: Mapping[str, Any], *names: str) -> str | None:
    data = item.get("data")
    data_mapping = data if isinstance(data, Mapping) else {}
    for name in names:
        value = _clean_text(data_mapping.get(name))
        if value:
            return value
    return None


def _expected_effect_authority(
    decision: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    applied_at: object,
) -> dict[str, Any]:
    target_artifact = (
        _item_target(item, "target_artifact")
        or _clean_text(item.get("output_path"))
        or _item_target(item, "path")
    )
    expected: dict[str, Any] = {
        "item_id": decision["item_id"],
        "item_type": decision["item_type"],
        "title": decision["title"],
        "action": decision["action"],
        "status": decision["status"],
        "applied_at": applied_at,
        "applied": True,
        "requires_followup": decision["action"] in FOLLOWUP_ACTIONS,
        "target_artifact": target_artifact or None,
        "target_path": (
            _item_target(item, "target_path", "field_path", "field") or None
        ),
        "target_id_field": (
            _item_target(item, "target_id_field", "record_id_field") or None
        ),
        "target_record_id": (
            _item_target(item, "target_record_id", "record_id") or None
        ),
        "target_field": (_item_target(item, "target_field", "edit_field") or None),
        "target_records_key": (
            _item_target(item, "target_records_key", "records_key") or None
        ),
        "source_path": _clean_text(item.get("source_path")) or None,
    }
    for field in DECISION_OPTIONAL_FIELDS:
        if field in decision:
            expected[field] = decision[field]
    return expected


def _validate_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    content = path.read_bytes()
    if receipt.get("path") != path.name and receipt.get("path") != path.as_posix():
        raise ValueError("Report Builder successor receipt path is stale.")
    if (
        receipt.get("byte_count") != len(content)
        or receipt.get("sha256") != hashlib.sha256(content).hexdigest()
    ):
        raise ValueError("Report Builder successor receipt bytes are stale.")


def _validate_review_history(
    output_dir: Path,
    applied: Mapping[str, Any],
) -> list[str]:
    raw_paths = applied.get("review_history_paths", [])
    if (
        not isinstance(raw_paths, list)
        or not all(isinstance(path, str) for path in raw_paths)
        or len(raw_paths) != len(set(raw_paths))
    ):
        raise ValueError("Report Builder review history paths are malformed.")
    for relative_path in raw_paths:
        match = re.fullmatch(
            r"revisions/history/application__([0-9a-f]{64})\.json",
            relative_path,
        )
        if match is None:
            raise ValueError("Report Builder review history path is not canonical.")
        history = _read_object(output_dir / relative_path)
        expected_fields = {
            "schema_version",
            "archived_at",
            "predecessor_checkpoint",
            "predecessor_integrity",
            "run_intake",
            "review_payload",
            "ui_decisions",
            "applied_decisions",
            "final_artifacts",
            "content_sha256",
        }
        content = dict(history)
        digest = content.pop("content_sha256", None)
        replayed = _canonical_sha256(content)
        predecessor_checkpoint = _clean_text(history.get("predecessor_checkpoint"))
        predecessor_integrity = history.get("predecessor_integrity")
        if (
            set(history) != expected_fields
            or history.get("schema_version") != HISTORY_SCHEMA
            or not _clean_text(history.get("archived_at"))
            or re.fullmatch(r"[0-9a-f]{64}", predecessor_checkpoint) is None
            or not isinstance(predecessor_integrity, Mapping)
            or not isinstance(history.get("run_intake"), Mapping)
            or not isinstance(history.get("review_payload"), Mapping)
            or not isinstance(history.get("ui_decisions"), Mapping)
            or not isinstance(history.get("applied_decisions"), Mapping)
            or not isinstance(history.get("final_artifacts"), Mapping)
            or digest != replayed
            or match.group(1) != replayed
        ):
            raise ValueError("Report Builder review history entry is stale.")
        if (
            set(predecessor_integrity) != INTEGRITY_FIELDS
            or predecessor_integrity.get("schema_version") != INTEGRITY_SCHEMA
            or predecessor_integrity.get("content_sha256") != predecessor_checkpoint
        ):
            raise ValueError(
                "Report Builder predecessor integrity checkpoint is stale."
            )
        predecessor_content = dict(predecessor_integrity)
        predecessor_content.pop("content_sha256")
        if _canonical_sha256(predecessor_content) != predecessor_checkpoint:
            raise ValueError(
                "Report Builder predecessor integrity checkpoint is stale."
            )
        payload_digests = predecessor_integrity.get("payload_digests")
        archived_payloads = {
            "run_intake": history["run_intake"],
            "review_payload": history["review_payload"],
            "ui_decisions": history["ui_decisions"],
            "applied_decisions": history["applied_decisions"],
            "final_artifacts": history["final_artifacts"],
        }
        if (
            not isinstance(payload_digests, Mapping)
            or set(payload_digests) != set(archived_payloads)
            or any(
                payload_digests.get(name) != _canonical_sha256(value)
                for name, value in archived_payloads.items()
            )
        ):
            raise ValueError("Report Builder predecessor payload receipts are stale.")
        prior_review = history["review_payload"]
        prior_ui = history["ui_decisions"]
        prior_applied = history["applied_decisions"]
        prior_final = history["final_artifacts"]
        prior_decisions = _validate_ui_state(prior_review, prior_ui)
        source_mapping_review_required = (
            prior_applied.get("source_mapping_review_required") is True
        )
        if (
            prior_applied.get("run_id") != prior_review.get("run_id")
            or prior_applied.get("review_payload_sha256")
            != _canonical_sha256(prior_review)
            or (
                not source_mapping_review_required
                and (
                    prior_applied.get("decisions") != prior_decisions
                    or prior_applied.get("decision_count") != len(prior_decisions)
                )
            )
            or (
                source_mapping_review_required
                and (
                    prior_decisions
                    or prior_ui.get("decision_count") != 0
                    or re.fullmatch(
                        r"[0-9a-f]{64}",
                        _clean_text(
                            prior_applied.get("decision_review_payload_sha256")
                        ),
                    )
                    is None
                )
            )
            or prior_applied.get("item_count") != prior_review.get("item_count")
            or prior_final.get("run_id") != prior_review.get("run_id")
        ):
            raise ValueError("Report Builder predecessor review application is stale.")
        protected_files = predecessor_integrity.get("protected_files")
        if not isinstance(protected_files, list) or not all(
            isinstance(receipt, Mapping) for receipt in protected_files
        ):
            raise ValueError(
                "Report Builder predecessor protected receipts are malformed."
            )
        receipts_by_path = {
            _clean_text(receipt.get("path")): receipt for receipt in protected_files
        }
        required_receipts = {
            "run_intake.json",
            "review_payload.json",
            "ui_decisions.json",
            "applied_decisions.json",
            "final_artifacts.json",
        }
        if len(receipts_by_path) != len(
            protected_files
        ) or not required_receipts <= set(receipts_by_path):
            raise ValueError(
                "Report Builder predecessor protected receipts are incomplete."
            )
        outputs = prior_final.get("outputs")
        if not isinstance(outputs, list):
            raise ValueError("Report Builder predecessor final outputs are malformed.")
        for output in outputs:
            if not isinstance(output, Mapping):
                raise ValueError(
                    "Report Builder predecessor final outputs are malformed."
                )
            output_path = _clean_text(output.get("path"))
            receipt = receipts_by_path.get(output_path)
            if (
                receipt is None
                or output.get("size_bytes") != receipt.get("byte_count")
                or output.get("sha256") != receipt.get("sha256")
            ):
                raise ValueError(
                    "Report Builder predecessor material-output receipt is stale."
                )
    return raw_paths


def _validate_retained_review_paths(applied: Mapping[str, Any]) -> list[str]:
    raw_paths = applied.get("retained_review_paths", [])
    if (
        not isinstance(raw_paths, list)
        or not all(isinstance(path, str) for path in raw_paths)
        or len(raw_paths) != len(set(raw_paths))
        or any(
            re.fullmatch(
                r"revisions/(?:report__[A-Za-z0-9._-]+\.txt|"
                r"originals/report__[A-Za-z0-9._-]+\.docx)",
                path,
            )
            is None
            for path in raw_paths
        )
    ):
        raise ValueError("Report Builder retained review paths are malformed.")
    return raw_paths


def _validate_edit_effect(
    output_dir: Path,
    effect: Mapping[str, Any],
    *,
    source_mapping_changed: bool,
    numeric_present: bool,
) -> list[str]:
    target_path = _clean_text(effect.get("target_path"))
    expected_field = (
        "assigned_table" if target_path.endswith(".assigned_table") else "codex_comment"
    )
    if (
        effect.get("target_artifact") != "report.docx"
        or not re.fullmatch(
            rf"sections\.[A-Za-z0-9_]+\.{expected_field}",
            target_path,
        )
        or effect.get("artifact_update") != "native_artifact_regenerated"
        or effect.get("requires_native_regeneration") is not False
        or effect.get("native_regeneration_status") != "regenerated"
        or effect.get("terminal_application") is not True
    ):
        raise ValueError("Report Builder edit successor is not terminal.")
    expected_paths = (
        [
            "used_recipe.json",
            "report_analysis.json",
            "report_audit.json",
            "report_tables.json",
            "report_tables.xlsx",
            "report_draft.md",
            "report.docx",
        ]
        if source_mapping_changed
        else [
            "used_recipe.json",
            "report_analysis.json",
            "report_draft.md",
            "report.docx",
        ]
    )
    if numeric_present:
        expected_paths.extend(["numeric_evidence_ledger.json", "source_receipts.json"])
    if effect.get("native_regenerated_paths") != expected_paths:
        raise ValueError("Report Builder edit regenerated path set is stale.")
    item_id = _clean_text(effect.get("item_id"))
    revision_path = f"revisions/report__{_safe_item_id(item_id)}.txt"
    if effect.get("revision_artifact") != revision_path or (
        output_dir / revision_path
    ).read_text(encoding="utf-8") != effect.get("edit_value"):
        raise ValueError("Report Builder edit revision is not decision-derived.")
    receipt = effect.get("application_receipt")
    if not isinstance(receipt, Mapping):
        raise ValueError("Report Builder edit application receipt is missing.")
    expected_receipt_fields = {
        "target_path",
        "applied_value_sha256",
        "used_recipe_sha256",
        "report_analysis_sha256",
        "report_draft_sha256",
        "report_docx_sha256",
        "regenerated_outputs",
    }
    if set(receipt) != expected_receipt_fields:
        raise ValueError("Report Builder edit application receipt is not exact.")
    expected_hashes = {
        "target_path": target_path,
        "applied_value_sha256": hashlib.sha256(
            _clean_text(effect.get("edit_value")).encode("utf-8")
        ).hexdigest(),
        "used_recipe_sha256": hashlib.sha256(
            (output_dir / "used_recipe.json").read_bytes()
        ).hexdigest(),
        "report_analysis_sha256": hashlib.sha256(
            (output_dir / "report_analysis.json").read_bytes()
        ).hexdigest(),
        "report_draft_sha256": hashlib.sha256(
            (output_dir / "report_draft.md").read_bytes()
        ).hexdigest(),
        "report_docx_sha256": hashlib.sha256(
            (output_dir / "report.docx").read_bytes()
        ).hexdigest(),
    }
    if any(receipt.get(key) != value for key, value in expected_hashes.items()):
        raise ValueError("Report Builder edit application receipt is stale.")
    raw_outputs = receipt.get("regenerated_outputs")
    if not isinstance(raw_outputs, list) or len(raw_outputs) != len(expected_paths):
        raise ValueError("Report Builder regenerated receipt set is not exact.")
    for relative_path, output_receipt in zip(
        expected_paths,
        raw_outputs,
        strict=True,
    ):
        if not isinstance(output_receipt, Mapping):
            raise ValueError("Report Builder regenerated receipt is malformed.")
        if output_receipt.get("path") != relative_path:
            raise ValueError("Report Builder regenerated receipt order is stale.")
        content = (output_dir / relative_path).read_bytes()
        if (
            output_receipt.get("byte_count") != len(content)
            or output_receipt.get("sha256") != hashlib.sha256(content).hexdigest()
        ):
            raise ValueError("Report Builder regenerated receipt bytes are stale.")
    return expected_paths


def _expected_application_status(
    applied: Mapping[str, Any],
    analysis: Mapping[str, Any],
    *,
    source_mapping_changed: bool,
) -> str:
    if int(applied.get("blocker_count") or 0) > 0:
        return "blocked"
    if int(applied.get("native_regeneration_count") or 0) > 0:
        return "partial_review_applied"
    if int(applied.get("decision_count") or 0) < int(applied.get("item_count") or 0):
        return "partial_review_applied"
    effects = applied.get("effects")
    if not isinstance(effects, list):
        raise ValueError("Report Builder successor effects are malformed.")
    if any(
        isinstance(effect, Mapping)
        and effect.get("action") == "edit"
        and (
            effect.get("artifact_update") != "native_artifact_regenerated"
            or effect.get("terminal_application") is not True
            or not isinstance(effect.get("application_receipt"), Mapping)
        )
        for effect in effects
    ):
        return "partial_review_applied"
    sections = analysis.get("sections")
    if isinstance(sections, list) and any(
        isinstance(section, Mapping)
        and section.get("numeric_measure_status") == "needs_review"
        for section in sections
    ):
        return "partial_review_applied"
    if source_mapping_changed:
        return "partial_review_applied"
    return "final_ready"


def _validate_applied_state(
    output_dir: Path,
    review_payload: Mapping[str, Any],
    ui_decisions: Mapping[str, Any],
    applied: Mapping[str, Any],
    analysis: Mapping[str, Any],
    final_artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    items = _review_items(review_payload)
    raw_decisions = applied.get("decisions")
    raw_effects = applied.get("effects")
    if (
        not isinstance(raw_decisions, list)
        or not all(isinstance(decision, dict) for decision in raw_decisions)
        or not isinstance(raw_effects, list)
        or not all(isinstance(effect, dict) for effect in raw_effects)
        or len(raw_decisions) != len(raw_effects)
    ):
        raise ValueError("Report Builder applied successor is malformed.")
    decision_ids = [_clean_text(decision.get("item_id")) for decision in raw_decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise ValueError("Report Builder applied decisions are not unique.")
    applied_at = applied.get("applied_at")
    if not _clean_text(applied_at):
        raise ValueError("Report Builder applied timestamp is missing.")
    for decision in raw_decisions:
        item = items.get(_clean_text(decision.get("item_id")))
        if item is None:
            raise ValueError("Report Builder applied decision item does not exist.")
        _validate_decision(
            decision,
            item,
            decided_at=decision.get("decided_at"),
        )
    source_mapping_changed = any(
        effect.get("action") == "edit"
        and re.fullmatch(
            r"sections\.[A-Za-z0-9_]+\.assigned_table",
            _clean_text(effect.get("target_path")),
        )
        for effect in raw_effects
    )
    if source_mapping_changed:
        if (
            ui_decisions.get("decision_source") != "not_collected_after_regeneration"
            or ui_decisions.get("decisions") != []
            or ui_decisions.get("status") != "pending_review"
        ):
            raise ValueError("Report Builder regenerated review state is stale.")
    elif raw_decisions != ui_decisions.get("decisions"):
        raise ValueError(
            "Report Builder applied decisions do not derive from UI decisions."
        )
    numeric_present = (output_dir / "numeric_evidence_ledger.json").is_file()
    union_regenerated_paths: set[str] = set()
    edit_effects: list[Mapping[str, Any]] = []
    for decision, effect in zip(raw_decisions, raw_effects, strict=True):
        item = items[_clean_text(decision.get("item_id"))]
        expected = _expected_effect_authority(
            decision,
            item,
            applied_at=applied_at,
        )
        authority_fields = (
            {key: value for key, value in expected.items() if key != "source_path"}
            if source_mapping_changed
            else expected
        )
        if any(effect.get(key) != value for key, value in authority_fields.items()):
            raise ValueError(
                "Report Builder application effect is not decision-derived."
            )
        if decision.get("action") == "edit":
            edit_effects.append(effect)
            union_regenerated_paths.update(
                _validate_edit_effect(
                    output_dir,
                    effect,
                    source_mapping_changed=source_mapping_changed,
                    numeric_present=numeric_present,
                )
            )
        else:
            expected_update = (
                "decision_manifest_only"
                if effect.get("target_artifact")
                else "review_record_only"
            )
            if effect.get("artifact_update") != expected_update:
                raise ValueError(
                    "Report Builder non-edit effect is not decision-derived."
                )
    numeric_pending = [
        _clean_text(section.get("section"))
        for section in analysis.get("sections", [])
        if isinstance(section, Mapping)
        and section.get("numeric_measure_status") == "needs_review"
    ]
    revision_paths = [
        f"revisions/report__{_safe_item_id(effect.get('item_id'))}.txt"
        for effect in edit_effects
    ]
    backup_paths = (
        [
            "revisions/originals/"
            f"report__{_safe_item_id(edit_effects[0].get('item_id'))}.docx"
        ]
        if edit_effects
        else []
    )
    review_history_paths = _validate_review_history(output_dir, applied)
    retained_review_paths = _validate_retained_review_paths(applied)
    predecessor_checkpoint = applied.get("predecessor_checkpoint")
    if review_history_paths:
        latest_history = _read_object(output_dir / review_history_paths[-1])
        if (
            not isinstance(predecessor_checkpoint, str)
            or re.fullmatch(r"[0-9a-f]{64}", predecessor_checkpoint) is None
            or latest_history.get("predecessor_checkpoint") != predecessor_checkpoint
        ):
            raise ValueError("Report Builder applied predecessor checkpoint is stale.")
    elif predecessor_checkpoint is not None:
        raise ValueError("Report Builder applied predecessor checkpoint is unexpected.")
    applied_item_count = (
        applied.get("item_count") if source_mapping_changed else len(items)
    )
    if not isinstance(applied_item_count, int) or applied_item_count < len(
        raw_decisions
    ):
        raise ValueError("Report Builder applied item count is malformed.")
    expected_values: dict[str, Any] = {
        "schema_version": review_payload.get("schema_version"),
        "plugin": review_payload.get("plugin"),
        "workflow": review_payload.get("workflow"),
        "run_id": review_payload.get("run_id"),
        "review_payload_sha256": _canonical_sha256(review_payload),
        "decision_count": len(raw_decisions),
        "item_count": applied_item_count,
        "blocker_count": sum(
            decision.get("action") in FOLLOWUP_ACTIONS for decision in raw_decisions
        ),
        "numeric_measure_pending_review_count": len(numeric_pending),
        "numeric_measure_pending_section_count": len(numeric_pending),
        "numeric_measure_pending_sections": numeric_pending,
        "revision_count": len(revision_paths),
        "revision_paths": revision_paths,
        "target_update_count": 0,
        "target_update_paths": [],
        "structured_update_count": 0,
        "structured_update_paths": [],
        "native_regeneration_count": 0,
        "native_regeneration_paths": [],
        "native_regenerated_count": len(edit_effects),
        "native_regenerated_paths": sorted(union_regenerated_paths),
        "original_backup_paths": backup_paths,
        "source_mapping_review_required": source_mapping_changed,
        "predecessor_checkpoint": predecessor_checkpoint,
        "review_history_paths": review_history_paths,
        "retained_review_paths": retained_review_paths,
    }
    if any(applied.get(key) != value for key, value in expected_values.items()):
        raise ValueError("Report Builder applied successor counters are stale.")
    review_binding = applied.get("review_payload")
    if not isinstance(review_binding, Mapping) or review_binding != {
        "path": "review_payload.json",
        "item_count": applied_item_count,
        "review_type": review_payload.get("review_type"),
    }:
        raise ValueError("Report Builder applied review binding is stale.")
    if not source_mapping_changed:
        if (
            applied.get("decision_source") != ui_decisions.get("decision_source")
            or applied.get("decision_review_payload_sha256")
            != _canonical_sha256(review_payload)
            or applied.get("reviewer") != ui_decisions.get("reviewer")
        ):
            raise ValueError("Report Builder applied decision authority is stale.")
    elif not re.fullmatch(
        r"[0-9a-f]{64}",
        _clean_text(applied.get("decision_review_payload_sha256")),
    ):
        raise ValueError("Report Builder predecessor decision digest is malformed.")
    expected_status = _expected_application_status(
        applied,
        analysis,
        source_mapping_changed=source_mapping_changed,
    )
    if applied.get("application_status") != expected_status:
        raise ValueError("Report Builder application status is not rederived.")
    review_application = final_artifacts.get("review_application")
    if not isinstance(review_application, Mapping):
        raise ValueError("Report Builder final successor state is missing.")
    final_expected = {
        "status": expected_status,
        "review_status": expected_status,
    }
    if any(final_artifacts.get(key) != value for key, value in final_expected.items()):
        raise ValueError("Report Builder final status is not successor-derived.")
    application_expected = {
        "applied_at": applied_at,
        "application_status": expected_status,
        "decision_count": len(raw_decisions),
        "item_count": applied_item_count,
        "blocker_count": expected_values["blocker_count"],
        "numeric_measure_pending_review_count": len(numeric_pending),
        "revision_count": len(revision_paths),
        "revision_paths": revision_paths,
        "target_update_count": 0,
        "target_update_paths": [],
        "structured_update_count": 0,
        "structured_update_paths": [],
        "native_regeneration_count": 0,
        "native_regeneration_paths": [],
        "native_regenerated_count": len(edit_effects),
        "native_regenerated_paths": sorted(union_regenerated_paths),
        "original_backup_paths": backup_paths,
        "numeric_measure_pending_section_count": len(numeric_pending),
        "numeric_measure_pending_sections": numeric_pending,
        "source_mapping_review_required": source_mapping_changed,
        "predecessor_checkpoint": predecessor_checkpoint,
        "review_history_paths": review_history_paths,
        "retained_review_paths": retained_review_paths,
        "applied_decisions_path": "applied_decisions.json",
    }
    if any(
        review_application.get(key) != value
        for key, value in application_expected.items()
    ):
        raise ValueError("Report Builder final application projection is stale.")
    return {
        "state": "applied",
        "decision_count": len(raw_decisions),
        "effect_count": len(raw_effects),
        "application_status": expected_status,
        "source_mapping_review_required": source_mapping_changed,
    }


def validate_review_successor(
    output_dir: Path,
    *,
    analysis: Mapping[str, Any],
    review_payload: Mapping[str, Any] | None = None,
    final_artifacts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Re-derive the current recorded-decision successor and its status."""

    root = Path(output_dir)
    review = (
        dict(review_payload)
        if isinstance(review_payload, Mapping)
        else _read_object(root / "review_payload.json")
    )
    final = (
        dict(final_artifacts)
        if isinstance(final_artifacts, Mapping)
        else _read_object(root / "final_artifacts.json")
    )
    ui = _read_object(root / "ui_decisions.json")
    ui_state = _validate_ui_state(review, ui)
    applied_path = root / "applied_decisions.json"
    if applied_path.is_file():
        state = _validate_applied_state(
            root,
            review,
            ui,
            _read_object(applied_path),
            analysis,
            final,
        )
    else:
        state = {
            "state": "reviewed" if ui_state else "pending",
            "decision_count": len(ui_state),
            "effect_count": 0,
            "application_status": None,
            "source_mapping_review_required": False,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        **state,
        "reviewer_authentication": "not_established",
    }
