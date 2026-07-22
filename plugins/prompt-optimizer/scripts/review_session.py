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
PLUGIN_NAME = "prompt-optimizer"
WORKFLOW_NAME = "prompt-optimizer"


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written before prompt validation packaging."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for one optimized prompt package."""

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


def _run_id(question_text: str) -> str:
    timestamp = re.sub(r"[^0-9]", "", _utc_now())
    words = "-".join(question_text.strip().split()[:6])
    return f"{PLUGIN_NAME}-{_safe_slug(words)}-{timestamp}"


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
        {"field": "title", "label": "Prompt item"},
        {"field": "recommended_action", "label": "Suggested action"},
        {"field": "source_path", "label": "Source"},
        {"field": "output_path", "label": "Output"},
        {"field": "status", "label": "Status"},
    ]


def _audit_items(audit: dict[str, Any]) -> list[dict[str, Any]]:
    failed = audit.get("failed_checks", [])
    if not isinstance(failed, list):
        return []
    return [
        _base_item(
            f"audit-check-{index}",
            "audit_check",
            str(check),
            output_path="prompt_audit.json",
            allowed_actions=("accept", "reject", "edit", "mark_unclear", "skip"),
            recommended_action="reject",
            evidence=[
                {
                    "kind": "prompt_audit_check",
                    "status": "fail",
                    "check": check,
                    "missing_fact_anchors": audit.get("missing_fact_anchors"),
                    "missing_explicit_questions": audit.get(
                        "missing_explicit_questions"
                    ),
                }
            ],
            data={"check": check, "audit": audit},
        )
        for index, check in enumerate(failed, start=1)
    ]


def _artifact_items(paths: dict[str, Path], output_dir: Path) -> list[dict[str, Any]]:
    labels = {
        "optimized_prompt": ("prompt_artifact", "Optimized prompt"),
        "prompt_audit": ("review_artifact", "Prompt audit JSON"),
        "prompt_package": ("review_artifact", "Prompt package Markdown"),
        "source_domains": ("source_domain_artifact", "Source domains"),
        "source_domains_comma": ("source_domain_artifact", "Source domains comma list"),
        "readme_human": ("review_artifact", "Human README"),
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


def _source_artifacts(
    paths: dict[str, Path],
    output_dir: Path,
    *,
    run_intake_path: Path,
) -> dict[str, str]:
    """Inventory the deterministic files that back the review payload."""

    artifacts: dict[str, str] = {}
    run_intake_ref = _as_output_ref(run_intake_path, output_dir)
    if run_intake_path.is_file() and run_intake_ref is not None:
        artifacts["run_intake"] = run_intake_ref
    for field, path in paths.items():
        path_ref = _as_output_ref(path, output_dir)
        if Path(path).is_file() and path_ref is not None:
            artifacts[field] = path_ref
    return artifacts


def _output_records(output_dir: Path) -> list[dict[str, Any]]:
    review_files = {
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "final_artifacts.json",
    }
    required_text_by_path = {
        "prompt_package.md": [
            "# Prompt Optimizer Package",
            "## Deterministic Research Lens",
            "## What to Use",
        ],
        "README_HUMAN.md": [
            "# How to use these files",
            "Paste `optimized_prompt.md` into Deep Research.",
        ],
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
    question_text: str,
    prompt_text: str,
    language: str,
    source_domains: Sequence[str],
) -> RunIntakeResult:
    """Write run intake before deterministic prompt validation."""

    run_id = _run_id(question_text)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "input_paths": [],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "prompt_optimizer_review_payload",
        "assumptions": {
            "question_character_count": len(question_text),
            "prompt_character_count": len(prompt_text),
            "source_domain_count": len(source_domains),
            "language": language,
        },
        "unresolved_questions": [],
        "dependency_check": {
            "status": "not_run_by_script",
            "note": "Codex should run scripts/check_dependencies.py before helper scripts.",
        },
        "data_posture": {
            "local_files_read": [],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "notes": [
                "Prompt validation receives question and prompt text from the current Codex/user workflow.",
                "The deterministic script does not read source files, call model APIs, use connectors, or upload data.",
            ],
        },
        "status": "ready_for_prompt_validation",
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
    question_text: str,
    audit: dict[str, Any],
    paths: dict[str, Path],
) -> ReviewSessionResult:
    """Write review payload, pending decisions, and final artifact inventory."""

    items: list[dict[str, Any]] = []
    items.extend(_audit_items(audit))
    items.extend(_artifact_items(paths, output_dir))

    review_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": audit.get("language", "auto"),
        "source_paths": [],
        "review_type": "prompt_optimizer_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(),
        "source_artifacts": _source_artifacts(
            paths,
            output_dir,
            run_intake_path=run_intake_path,
        ),
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
            "source_domain_count": len(audit.get("source_domains", []) or []),
            "requires_phased_workflow": audit.get("requires_phased_workflow"),
            "topic_flags": audit.get("topic_flags", []),
            "question_preview": _clean_text(question_text)[:180],
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
        title="Prompt Optimizer",
        validate_tool="validate_prompt_optimizer_review",
        render_tool="render_prompt_optimizer_review",
        save_tool="save_prompt_optimizer_decisions",
        apply_tool="apply_prompt_optimizer_decisions",
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
                "Angle and jurisdiction choices remain Codex/user intake decisions; this widget reviews the generated package, not the pre-draft choices.",
                "Deterministic validation checks structure, fact anchors, source-domain sidecars, and required prompt controls.",
                "ui_decisions.json is pending until Codex, the MCP widget, or fallback review records decisions.",
            ],
            "next_actions": [
                "Call validate_prompt_optimizer_review, then render_prompt_optimizer_review when MCP is available.",
                "Repair draft_prompt.md and rerun validation if prompt_audit.json fails.",
                "Use optimized_prompt.md in Deep Research and source_domains_comma.txt in the websites field.",
            ],
            "status": "written_pending_review",
        },
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=["python", "plugins/prompt-optimizer/scripts/validate_prompt.py"],
    )

    return ReviewSessionResult(
        run_id=run_id,
        run_intake_path=run_intake_path,
        review_payload_path=review_payload_path,
        ui_decisions_path=ui_decisions_path,
        final_artifacts_path=final_artifacts_path,
        review_item_count=len(items),
    )
