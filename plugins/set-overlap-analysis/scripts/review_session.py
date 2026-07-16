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
PLUGIN_NAME = "set-overlap-analysis"
WORKFLOW_NAME = "set-overlap-analysis"
MAX_INTERSECTION_ITEMS = 120
MAX_PAIR_ITEMS = 80
MAX_ARTIFACT_ITEMS = 300


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written before set-overlap rendering."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for one set-overlap run."""

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


def _run_id(input_path: Path) -> str:
    timestamp = re.sub(r"[^0-9]", "", _utc_now())
    return f"{PLUGIN_NAME}-{_safe_slug(input_path.stem)}-{timestamp}"


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


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


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_output_ref(path: str | Path | None, output_dir: Path) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    try:
        return candidate.relative_to(output_dir).as_posix()
    except ValueError:
        return candidate.as_posix()


def _data_posture(input_path: Path, recipe_path: Path | None) -> dict[str, Any]:
    local_files = [input_path.as_posix()]
    if recipe_path is not None:
        local_files.append(recipe_path.as_posix())
    return {
        "local_files_read": local_files,
        "model_excerpts_sent": [],
        "external_connectors_used": [],
        "upload_paths_used": [],
        "remote_sql_execution_used": False,
        "hosted_notebook_execution_used": False,
        "calculation_mode": "local_deterministic_scripts",
    }


def _num(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _base_item(
    item_id: str,
    item_type: str,
    title: str,
    *,
    allowed_actions: Sequence[str],
    recommended_action: str,
    source_path: str | None = None,
    output_path: str | None = None,
    references: Sequence[dict[str, Any]] = (),
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
        "references": list(references),
        "data": data or {},
        "status": "needs_review",
    }


def _review_columns() -> list[dict[str, str]]:
    return [
        {"field": "item_type", "label": "Type"},
        {"field": "title", "label": "Overlap item"},
        {"field": "recommended_action", "label": "Suggested action"},
        {"field": "source_path", "label": "Source"},
        {"field": "output_path", "label": "Output"},
        {"field": "status", "label": "Status"},
    ]


def _set_summary_items(context: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in context.get("set_summary", []) if isinstance(row, dict)]
    rows.sort(key=lambda row: _num(row.get("item_count")), reverse=True)
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        set_name = str(row.get("set") or row.get("Retailer") or f"Set {index}")
        selected = bool(row.get("selected", True))
        items.append(
            _base_item(
                f"set-summary-{index}",
                "set_summary",
                f"{set_name}: {int(_num(row.get('item_count')))} items",
                output_path="set_overlap_set_summary.csv",
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="accept" if selected else "skip",
                references=[
                    {
                        "kind": "set_summary",
                        "set": set_name,
                        "item_count": row.get("item_count"),
                        "selected": selected,
                    }
                ],
                data=dict(row),
            )
        )
    return items


def _intersection_items(context: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in context.get("intersections", []) if isinstance(row, dict)]
    rows.sort(key=lambda row: _num(row.get("item_count")), reverse=True)
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:MAX_INTERSECTION_ITEMS], start=1):
        title = str(row.get("intersection") or f"Intersection {index}")
        item_count = int(_num(row.get("item_count")))
        items.append(
            _base_item(
                f"intersection-{index}",
                "overlap_intersection",
                f"{title}: {item_count} items",
                output_path="set_overlap_intersections.csv",
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="accept" if item_count else "mark_unclear",
                references=[
                    {
                        "kind": "exact_intersection",
                        "intersection": row.get("intersection"),
                        "set_count": row.get("set_count"),
                        "item_count": row.get("item_count"),
                    }
                ],
                data=dict(row),
            )
        )
    return items


def _pair_items(context: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in context.get("pairwise_overlap", []) if isinstance(row, dict)]
    rows.sort(key=lambda row: _num(row.get("item_count")), reverse=True)
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:MAX_PAIR_ITEMS], start=1):
        left = str(row.get("left_set") or "")
        right = str(row.get("right_set") or "")
        item_count = int(_num(row.get("item_count")))
        items.append(
            _base_item(
                f"pair-overlap-{index}",
                "pair_overlap",
                f"{left} + {right}: {item_count} shared items",
                output_path="set_overlap_pairs.csv",
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="accept" if item_count else "skip",
                references=[
                    {
                        "kind": "pairwise_overlap",
                        "left_set": left,
                        "right_set": right,
                        "item_count": row.get("item_count"),
                    }
                ],
                data=dict(row),
            )
        )
    return items


def _chart_items(context: dict[str, Any]) -> list[dict[str, Any]]:
    chart_audits = (
        context.get("chart_audits")
        if isinstance(context.get("chart_audits"), dict)
        else {}
    )
    items: list[dict[str, Any]] = []
    for index, (chart_name, chart_audit) in enumerate(chart_audits.items(), start=1):
        if not isinstance(chart_audit, dict):
            continue
        artifacts = [
            str(path) for path in chart_audit.get("artifacts", []) if str(path)
        ]
        status = str(chart_audit.get("status") or "unknown")
        items.append(
            _base_item(
                f"chart-{index}",
                "chart_artifact",
                f"{chart_name}: {status}",
                output_path=artifacts[0] if artifacts else None,
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action=(
                    "accept"
                    if status in {"written", "written_html_only"}
                    else "mark_unclear"
                ),
                references=[
                    {
                        "kind": "chart_audit",
                        "chart": chart_name,
                        "status": status,
                        "artifacts": artifacts,
                    }
                ],
                data=dict(chart_audit),
            )
        )
    return items


def _artifact_item_type(record: dict[str, Any]) -> str:
    kind = str(record.get("artifact_type") or record.get("kind") or "")
    if kind in {"chart", "png", "html"}:
        return "chart_artifact"
    if kind in {"context", "contexts", "json"}:
        return "context_artifact"
    if kind in {"table", "tables", "brief", "report", "csv", "xlsx", "md", "docx"}:
        return "report_artifact"
    return "review_artifact"


def _artifact_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    records = [
        record for record in manifest.get("artifacts", []) if isinstance(record, dict)
    ][:MAX_ARTIFACT_ITEMS]
    items: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        output_path = str(record.get("path") or record.get("pack_path") or "")
        items.append(
            _base_item(
                f"artifact-{index}",
                _artifact_item_type(record),
                output_path or f"Artifact {index}",
                output_path=output_path,
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="accept",
                references=[
                    {
                        "kind": "output_artifact",
                        "artifact_type": record.get("artifact_type")
                        or record.get("kind"),
                        "path": output_path,
                    }
                ],
                data=dict(record),
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
    outputs: list[dict[str, Any]] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name in review_files:
            continue
        relative = path.relative_to(output_dir).as_posix()
        outputs.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "kind": path.suffix.lower().lstrip(".") or "file",
                "status": "written",
            }
        )
    return outputs


def write_run_intake(
    output_dir: Path,
    input_path: Path,
    *,
    recipe_path: Path | None,
    recipe: dict[str, Any],
    source_row_count: int,
) -> RunIntakeResult:
    """Write run intake before deterministic set-overlap analysis."""

    run_id = _run_id(input_path)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": recipe.get("language") or "en",
        "input_paths": [input_path.as_posix()],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "set_overlap_review_payload",
        "data_posture": _data_posture(input_path, recipe_path),
        "assumptions": {
            "source_row_count": source_row_count,
            "recipe_path": recipe_path.as_posix() if recipe_path else None,
            "mappings": recipe.get("mappings") or {},
            "options": recipe.get("options") or {},
        },
        "unresolved_questions": [],
        "dependency_check": {
            "status": "not_run_by_script",
            "note": "Codex should run scripts/check_dependencies.py before helper scripts.",
        },
        "status": "ready_for_set_overlap_run",
    }
    return RunIntakeResult(
        run_id=run_id,
        path=_write_json(output_dir / "run_intake.json", payload),
    )


def write_review_session_artifacts(
    output_dir: Path,
    input_path: Path,
    *,
    run_id: str,
    run_intake_path: Path,
    recipe_path: Path | None,
    recipe: dict[str, Any],
    context: dict[str, Any],
    audit: dict[str, Any],
) -> ReviewSessionResult:
    """Write review payload, pending decisions, and final artifact inventory."""

    outputs = _output_records(output_dir)
    items: list[dict[str, Any]] = []
    items.extend(_set_summary_items(context))
    items.extend(_intersection_items(context))
    items.extend(_pair_items(context))
    items.extend(_chart_items(context))
    items.extend(_artifact_items({"artifacts": outputs}))
    items.append(
        _base_item(
            "set-overlap-context",
            "context_artifact",
            "Set overlap context",
            output_path="set_overlap_context.json",
            allowed_actions=("accept", "edit", "mark_unclear", "skip"),
            recommended_action="accept",
            data=context,
        )
    )
    items.append(
        _base_item(
            "set-overlap-audit",
            "review_artifact",
            "Set overlap audit",
            output_path="set_overlap_audit.json",
            allowed_actions=("accept", "edit", "mark_unclear", "skip"),
            recommended_action="accept",
            data=audit,
        )
    )

    chart_count = len(context.get("chart_audits") or {})
    review_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "source_paths": [input_path.as_posix()],
        "review_type": "set_overlap_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(),
        "source_artifacts": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "recipe": _as_output_ref(recipe_path, output_dir),
            "used_recipe": "used_recipe.json",
            "canonical_table": "set_overlap_canonical.csv",
            "set_summary": "set_overlap_set_summary.csv",
            "item_sets": "set_overlap_item_sets.csv",
            "intersections": "set_overlap_intersections.csv",
            "pairs": "set_overlap_pairs.csv",
            "context": "set_overlap_context.json",
            "audit": "set_overlap_audit.json",
            "artifact_zip": "set_overlap_artifacts.zip",
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
            "selected_set_count": len(context.get("selected_sets") or []),
            "selected_sets": context.get("selected_sets") or [],
            "intersection_count": (context.get("row_counts") or {}).get(
                "intersection_count", 0
            ),
            "item_count": (context.get("row_counts") or {}).get("item_count", 0),
            "canonical_memberships": (context.get("row_counts") or {}).get(
                "canonical_memberships", 0
            ),
            "chart_count": chart_count,
            "item_column": (context.get("mappings") or {}).get("item_column"),
            "set_column": (context.get("mappings") or {}).get("set_column"),
            "selected_period": (context.get("options") or {}).get("selected_period"),
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

    final_artifacts_path = _write_json(
        output_dir / "final_artifacts.json",
        {
            "schema_version": SCHEMA_VERSION,
            "plugin": PLUGIN_NAME,
            "workflow": WORKFLOW_NAME,
            "run_id": run_id,
            "completed_at": _utc_now(),
            "outputs": _output_records(output_dir),
            "caveats": [
                "Use CSV tables and set_overlap_context.json before interpreting Venn or UpSet pixels.",
                "Venn is valid only when exactly two or three selected sets were rendered.",
                "ui_decisions.json is pending until Codex, MCP UI, or fallback review records decisions.",
            ],
            "next_actions": [
                "Call validate_set_overlap_review, then render_set_overlap_review when MCP is available.",
                "Review largest exact intersections and pairwise overlaps before final interpretation.",
                "Record accepted/edited/rejected review decisions before treating the overlap package as reviewed.",
            ],
            "status": "written_pending_review",
        },
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=["python", "plugins/set-overlap-analysis/scripts/run_set_overlap.py"],
    )

    return ReviewSessionResult(
        run_id=run_id,
        run_intake_path=run_intake_path,
        review_payload_path=review_payload_path,
        ui_decisions_path=ui_decisions_path,
        final_artifacts_path=final_artifacts_path,
        review_item_count=len(items),
    )
