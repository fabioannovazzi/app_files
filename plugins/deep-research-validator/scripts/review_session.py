from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

__all__ = [
    "ReviewSessionResult",
    "RunIntakeResult",
    "write_review_session_artifacts",
    "write_run_intake",
]

SCHEMA_VERSION = "1.0"
PLUGIN_NAME = "deep-research-validator"
WORKFLOW_NAME = "deep-research-validator"
MAX_CLAIM_ITEMS = 750
MAX_SOURCE_LIMIT_ITEMS = 150


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written before validation packaging."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for one Deep Research validation run."""

    run_id: str
    run_intake_path: Path
    review_payload_path: Path
    ui_decisions_path: Path
    final_artifacts_path: Path
    review_item_count: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-._").lower()
    return slug or "run"


def _run_id(document_inventory_path: Path) -> str:
    timestamp = re.sub(r"[^0-9]", "", _utc_now())
    return f"{PLUGIN_NAME}-{_safe_slug(document_inventory_path.stem)}-{timestamp}"


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def _write_review_handoff_card(
    output_dir: Path,
    *,
    run_id: str,
    title: str,
    validate_tool: str,
    render_tool: str,
    save_tool: str,
    apply_tool: str,
) -> Path:
    path = output_dir / "review_handoff.md"
    lines = [
        f"# {title} Review Handoff",
        "",
        f"- Run ID: `{run_id}`",
        "- Review payload: `review_payload.json`",
        "- Run intake: `run_intake.json`",
        "- Pending decisions: `ui_decisions.json`",
        "- Applied decisions: `applied_decisions.json`",
        "- Final artifacts: `final_artifacts.json`",
        "",
        "## Review In Codex",
        f"1. Validate the payload with `{validate_tool}`.",
        f"2. Render the review workbench with `{render_tool}`.",
        f"3. Save reviewer actions with `{save_tool}`.",
        f"4. Apply reviewer actions with `{apply_tool}`.",
        "",
        "Persistent save/apply requires the MCP or local-server review surface. "
        "Static HTML fallback can copy or download decision JSON only.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _review_handoff_output_record(path: Path) -> dict[str, Any]:
    return {
        "path": path.name,
        "kind": "md",
        "status": "written",
        "required_text": [
            "Review Handoff",
            "review_payload.json",
            "ui_decisions.json",
            "applied_decisions.json",
            "final_artifacts.json",
        ],
        "qa_checks": ["nonempty_text", "required_text"],
    }


def _local_output_refs(final_artifacts_path: Path) -> list[str]:
    refs = [
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "final_artifacts.json",
    ]
    payload = json.loads(final_artifacts_path.read_text(encoding="utf-8"))
    outputs = payload.get("outputs")
    if isinstance(outputs, list):
        for output in outputs:
            if not isinstance(output, dict):
                continue
            path_value = output.get("path")
            if (
                isinstance(path_value, str)
                and path_value.strip()
                and "://" not in path_value
            ):
                refs.append(path_value.strip())
    return list(dict.fromkeys(refs))


def _append_execution_trace(
    run_intake_path: Path,
    final_artifacts_path: Path,
    *,
    command: Sequence[str],
) -> None:
    payload = json.loads(run_intake_path.read_text(encoding="utf-8"))
    data_posture = payload.get("data_posture")
    local_files = (
        data_posture.get("local_files_read") if isinstance(data_posture, dict) else None
    )
    inputs = (
        local_files if isinstance(local_files, list) else payload.get("input_paths", [])
    )
    payload["execution_trace"] = [
        {
            "step_id": f"{WORKFLOW_NAME}_review_session",
            "kind": "deterministic_review_session",
            "status": "passed",
            "execution_location": "local_codex_workspace",
            "command": list(command),
            "inputs": [str(entry) for entry in inputs if entry],
            "outputs": _local_output_refs(final_artifacts_path),
        }
    ]
    _write_json(run_intake_path, payload)


def _as_output_ref(path: str | Path | None, output_dir: Path) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    try:
        return candidate.relative_to(output_dir).as_posix()
    except ValueError:
        return candidate.as_posix()


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _base_item(
    item_id: str,
    item_type: str,
    title: str,
    *,
    allowed_actions: Sequence[str],
    recommended_action: str,
    source_path: str | None = None,
    output_path: str | None = None,
    evidence: Sequence[dict[str, Any]] = (),
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "item_type": item_type,
        "title": title,
        "source_path": source_path,
        "output_path": output_path,
        "allowed_actions": list(allowed_actions),
        "recommended_action": recommended_action,
        "evidence": list(evidence),
        "data": data or {},
        "status": "needs_review",
    }


def _review_columns() -> list[dict[str, str]]:
    return [
        {"field": "item_type", "label": "Type"},
        {"field": "title", "label": "Claim or artifact"},
        {"field": "recommended_action", "label": "Suggested action"},
        {"field": "source_path", "label": "Source"},
        {"field": "output_path", "label": "Output"},
        {"field": "status", "label": "Status"},
    ]


def _claim_item_type(verdict: str) -> str:
    if verdict == "supported":
        return "supported_claim"
    if verdict == "partially_supported":
        return "partially_supported_claim"
    if verdict == "not_supported":
        return "unsupported_claim"
    if verdict == "contradicted":
        return "contradicted_claim"
    if verdict == "uncertain":
        return "uncertain_claim"
    return "claim_review"


def _claim_action(verdict: str) -> str:
    if verdict == "supported":
        return "accept"
    if verdict in {"not_supported", "contradicted"}:
        return "reject"
    if verdict in {"partially_supported", "uncertain"}:
        return "mark_unclear"
    return "mark_unclear"


def _claim_title(claim: dict[str, Any], index: int) -> str:
    claim_index = claim.get("claim_index") or index
    text = _clean_text(claim.get("claim_text"))
    if len(text) > 110:
        text = text[:107].rstrip() + "..."
    return f"Claim {claim_index}: {text or 'Untitled claim'}"


def _claim_items(claims_review: dict[str, Any]) -> list[dict[str, Any]]:
    claims = claims_review.get("claims", [])
    if not isinstance(claims, list):
        return []
    items: list[dict[str, Any]] = []
    for index, claim in enumerate(claims[:MAX_CLAIM_ITEMS], start=1):
        if not isinstance(claim, dict):
            continue
        verdict = _clean_text(claim.get("verdict"))
        claim_data = dict(claim)
        claim_index = claim.get("claim_index") or index
        if claim.get("claim_index") is not None:
            claim_data.update(
                {
                    "target_artifact": "claims_review.json",
                    "target_records_key": "claims",
                    "target_id_field": "claim_index",
                    "target_record_id": str(claim_index),
                    "target_field": "proposed_fix",
                    "edit_hint": (
                        "Editing this claim writes the reviewer correction to "
                        "proposed_fix in claims_review.json for the matching "
                        "claim_index."
                    ),
                }
            )
        items.append(
            _base_item(
                f"claim-{claim_index}",
                _claim_item_type(verdict),
                _claim_title(claim, index),
                output_path="claims_review.json",
                allowed_actions=(
                    "accept",
                    "reject",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ),
                recommended_action=_claim_action(verdict),
                evidence=[
                    {
                        "kind": "claim_vs_citation",
                        "claim_text": claim.get("claim_text"),
                        "verdict": verdict,
                        "source_refs": claim.get("source_refs"),
                        "source_quote": claim.get("source_quote"),
                        "source_support": claim.get("source_support"),
                        "reasoning_review": claim.get("reasoning_review"),
                        "proposed_fix": claim.get("proposed_fix"),
                    }
                ],
                data=claim_data,
            )
        )
    return items


def _source_limit_items(source_inventory: dict[str, Any]) -> list[dict[str, Any]]:
    sources = source_inventory.get("sources", [])
    if not isinstance(sources, list):
        return []
    limited_statuses = {
        "listed_not_fetched",
        "http_error",
        "unreachable",
        "too_short",
        "access_barrier",
        "empty",
    }
    items: list[dict[str, Any]] = []
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            continue
        status = _clean_text(source.get("status"))
        if status not in limited_statuses:
            continue
        title = _clean_text(
            source.get("url") or source.get("path") or source.get("name")
        )
        items.append(
            _base_item(
                f"source-limit-{index}",
                "source_limit",
                title or f"Source limit {index}",
                output_path="source_inventory.json",
                allowed_actions=(
                    "accept",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ),
                recommended_action="request_more_documents",
                evidence=[
                    {
                        "kind": "source_availability",
                        "status": status,
                        "http_status": source.get("http_status"),
                        "error": source.get("error"),
                    }
                ],
                data=dict(source),
            )
        )
        if len(items) >= MAX_SOURCE_LIMIT_ITEMS:
            break
    return items


def _audit_items(audit: dict[str, Any]) -> list[dict[str, Any]]:
    failed = audit.get("failed_checks", [])
    if not isinstance(failed, list):
        return []
    return [
        _base_item(
            f"audit-check-{index}",
            "audit_check",
            str(check),
            output_path="validation_audit.json",
            allowed_actions=("accept", "reject", "edit", "mark_unclear", "skip"),
            recommended_action="reject",
            evidence=[
                {
                    "kind": "validation_audit_check",
                    "status": "fail",
                    "check": check,
                    "invalid_claim_indices": audit.get("invalid_claim_indices"),
                    "missing_claim_text_indices": audit.get(
                        "missing_claim_text_indices"
                    ),
                    "missing_review_indices": audit.get("missing_review_indices"),
                }
            ],
            data={"check": check, "audit": audit},
        )
        for index, check in enumerate(failed, start=1)
    ]


def _artifact_items(paths: dict[str, Path], output_dir: Path) -> list[dict[str, Any]]:
    labels = {
        "claims_review": ("validation_artifact", "Claims review JSON"),
        "validation_audit": ("validation_artifact", "Validation audit JSON"),
        "validated_document": ("validation_artifact", "Validated document Markdown"),
        "validated_document_docx": ("validation_artifact", "Validated document DOCX"),
        "validation_package": ("validation_artifact", "Validation package Markdown"),
    }
    items: list[dict[str, Any]] = []
    for index, (field, (item_type, title)) in enumerate(labels.items(), start=1):
        path_value = paths.get(field)
        if not path_value:
            continue
        path_ref = _as_output_ref(path_value, output_dir)
        exists = Path(path_value).exists()
        items.append(
            _base_item(
                f"artifact-{index}",
                item_type,
                title,
                output_path=path_ref,
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="accept" if exists else "mark_unclear",
                evidence=[
                    {
                        "kind": "artifact_status",
                        "field": field,
                        "path": path_ref,
                        "exists": exists,
                    }
                ],
                data={"field": field, "path": path_ref, "exists": exists},
            )
        )
    return items


def _output_records(output_dir: Path) -> list[dict[str, Any]]:
    review_files = {
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "final_artifacts.json",
    }
    required_text_by_path = {
        "validation_package.md": [
            "# Deep Research Validation Package",
            "## Document Inventory",
            "## Claims Review",
        ]
    }
    outputs: list[dict[str, Any]] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name in review_files:
            continue
        relative = path.relative_to(output_dir).as_posix()
        output = {
            "path": relative,
            "size_bytes": path.stat().st_size,
            "kind": path.suffix.lower().lstrip(".") or "file",
            "status": "written",
        }
        required_text = required_text_by_path.get(relative)
        if required_text:
            output["required_text"] = required_text
            output["qa_checks"] = ["nonempty_text", "required_text"]
        outputs.append(output)
    return outputs


def write_run_intake(
    output_dir: Path,
    *,
    document_inventory_path: Path,
    source_inventory_path: Path,
    claims_review_path: Path,
    document_inventory: dict[str, Any],
    source_inventory: dict[str, Any],
    claims_review: dict[str, Any],
) -> RunIntakeResult:
    """Write run intake before validation package review."""

    run_id = _run_id(document_inventory_path)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": claims_review.get("language", "en"),
        "input_paths": [
            document_inventory_path.as_posix(),
            source_inventory_path.as_posix(),
            claims_review_path.as_posix(),
        ],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "deep_research_validation_review_payload",
        "assumptions": {
            "document_source_name": document_inventory.get("source_name"),
            "document_word_count": document_inventory.get("word_count"),
            "document_url_count": len(document_inventory.get("urls", []) or []),
            "source_count": len(source_inventory.get("sources", []) or []),
            "claim_count": len(claims_review.get("claims", []) or []),
            "validation_objective": claims_review.get("validation_objective"),
        },
        "unresolved_questions": [],
        "dependency_check": {
            "status": "not_run_by_script",
            "note": "Codex should run scripts/check_dependencies.py before helper scripts.",
        },
        "data_posture": {
            "local_files_read": [
                document_inventory_path.as_posix(),
                source_inventory_path.as_posix(),
                claims_review_path.as_posix(),
            ],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "notes": [
                "Validation package scripts read local document inventory, source inventory, and claim review files.",
                "Review payloads expose bounded claim/source evidence for UI review.",
                "No external connector, upload path, remote SQL, or hosted notebook execution is used by default.",
            ],
        },
        "status": "ready_for_validation_package",
    }
    return RunIntakeResult(
        run_id=run_id,
        path=_write_json(output_dir / "run_intake.json", payload),
    )


def write_review_session_artifacts(
    output_dir: Path,
    *,
    run_id: str,
    run_intake_path: Path,
    document_inventory_path: Path,
    source_inventory_path: Path,
    claims_review_path: Path,
    document_inventory: dict[str, Any],
    source_inventory: dict[str, Any],
    claims_review: dict[str, Any],
    audit: dict[str, Any],
    paths: dict[str, Path],
) -> ReviewSessionResult:
    """Write review payload, pending decisions, and final artifacts."""

    items: list[dict[str, Any]] = []
    items.extend(_audit_items(audit))
    items.extend(_claim_items(claims_review))
    items.extend(_source_limit_items(source_inventory))
    items.extend(_artifact_items(paths, output_dir))

    review_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": claims_review.get("language", "en"),
        "source_paths": [
            document_inventory.get("source_name"),
            *(document_inventory.get("urls", []) or []),
        ],
        "review_type": "deep_research_validation_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(),
        "source_artifacts": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "document_inventory": document_inventory_path.as_posix(),
            "source_inventory": source_inventory_path.as_posix(),
            "claims_review_input": claims_review_path.as_posix(),
            "claims_review": _as_output_ref(paths.get("claims_review"), output_dir),
            "validation_audit": "validation_audit.json",
            "validated_document": "validated_document.md",
            "validation_package": "validation_package.md",
        },
        "allowed_actions": [
            "accept",
            "reject",
            "edit",
            "mark_unclear",
            "request_more_documents",
            "skip",
        ],
        "status": "ready_for_review",
        "summary": {
            "audit_status": audit.get("status"),
            "failed_check_count": len(audit.get("failed_checks", []) or []),
            "claim_count": audit.get("claim_count", 0),
            "attention_claim_count": len(
                audit.get("attention_claim_indices", []) or []
            ),
            "source_count": audit.get("source_count", 0),
            "document_url_count": audit.get("document_url_count", 0),
            "quote_match_count": len(audit.get("quote_matches", []) or []),
        },
    }
    review_payload_path = _write_json(
        output_dir / "review_payload.json",
        review_payload,
    )

    ui_decisions_path = _write_json(
        output_dir / "ui_decisions.json",
        {
            "schema_version": SCHEMA_VERSION,
            "plugin": PLUGIN_NAME,
            "workflow": WORKFLOW_NAME,
            "run_id": run_id,
            "decided_at": None,
            "decision_source": "not_collected",
            "review_payload_path": review_payload_path.name,
            "decisions": [],
            "decision_count": 0,
            "status": "pending_review",
        },
    )

    review_handoff_path = _write_review_handoff_card(
        output_dir,
        run_id=run_id,
        title="Deep Research Validator",
        validate_tool="validate_deep_research_review",
        render_tool="render_deep_research_review",
        save_tool="save_deep_research_decisions",
        apply_tool="apply_deep_research_decisions",
    )
    outputs = _output_records(output_dir)
    outputs = [
        output
        for output in outputs
        if not (
            isinstance(output, dict) and output.get("path") == review_handoff_path.name
        )
    ]
    outputs.append(_review_handoff_output_record(review_handoff_path))

    final_artifacts_path = _write_json(
        output_dir / "final_artifacts.json",
        {
            "schema_version": SCHEMA_VERSION,
            "plugin": PLUGIN_NAME,
            "workflow": WORKFLOW_NAME,
            "run_id": run_id,
            "completed_at": _utc_now(),
            "outputs": outputs,
            "caveats": [
                "Semantic claim judgment is Codex-authored; deterministic checks validate structure, verdict fields, and exact quote matches where excerpts are available.",
                "The MCP review payload is bounded; use JSON and Markdown outputs as the complete validation evidence set.",
                "ui_decisions.json is pending until Codex, the MCP widget, or fallback review records decisions.",
            ],
            "next_actions": [
                "Call validate_deep_research_review, then render_deep_research_review when MCP is available.",
                "Review unsupported, contradicted, partially supported, uncertain, and source-limited items before delivery.",
                "Repair claims_review_draft.json and rerun packaging when validation_audit.json fails.",
            ],
            "status": "written_pending_review",
        },
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=[
            "python",
            "plugins/deep-research-validator/scripts/package_validation.py",
        ],
    )

    return ReviewSessionResult(
        run_id=run_id,
        run_intake_path=run_intake_path,
        review_payload_path=review_payload_path,
        ui_decisions_path=ui_decisions_path,
        final_artifacts_path=final_artifacts_path,
        review_item_count=len(items),
    )
