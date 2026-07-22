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
PLUGIN_NAME = "period-comparison"
WORKFLOW_NAME = "period-comparison"
MAX_MONTHLY_ROWS = 80
MAX_WINDOW_ROWS = 20
MAX_ARTIFACT_ITEMS = 250
MAX_FOLLOWUP_ITEMS = 50


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written before period-comparison rendering."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for one period-comparison run."""

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
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
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


def _as_output_ref(path: Path | None, output_dir: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(output_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _data_posture(input_path: Path, recipe_path: Path | None) -> dict[str, Any]:
    local_files = [input_path.as_posix()]
    if recipe_path is not None:
        local_files.append(recipe_path.as_posix())
    return {
        "local_files_read": local_files,
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
        {"field": "title", "label": "Element"},
        {"field": "recommended_action", "label": "Suggested action"},
        {"field": "source_path", "label": "Source"},
        {"field": "output_path", "label": "Output"},
        {"field": "status", "label": "Status"},
    ]


def _monthly_items(monthly_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(
        monthly_rows,
        key=lambda row: abs(_num(row.get("delta"))),
        reverse=True,
    )[:MAX_MONTHLY_ROWS]
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        title = str(row.get("Date") or row.get("month") or f"Month {index}")
        current = _num(row.get("AC") if "AC" in row else row.get("current_amount"))
        previous = _num(row.get("PY") if "PY" in row else row.get("previous_amount"))
        delta = current - previous
        items.append(
            _base_item(
                f"period-movement-{index}",
                "period_movement",
                title,
                output_path="period_comparison_monthly.csv",
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="mark_unclear" if abs(previous) < 1e-9 else "accept",
                references=[
                    {
                        "kind": "period_movement",
                        "current_amount": current,
                        "previous_amount": previous,
                        "delta": delta,
                        "delta_percent": (
                            (delta / previous * 100) if abs(previous) >= 1e-9 else None
                        ),
                    }
                ],
                data=dict(row),
            )
        )
    if len(monthly_rows) > MAX_MONTHLY_ROWS:
        items.append(
            _base_item(
                "period-movements-truncated",
                "review_artifact",
                "Period movement rows truncated in widget",
                output_path="period_comparison_monthly.csv",
                allowed_actions=("accept", "mark_unclear", "skip"),
                recommended_action="mark_unclear",
                data={
                    "shown_count": MAX_MONTHLY_ROWS,
                    "total_count": len(monthly_rows),
                    "full_results": "period_comparison_monthly.csv",
                },
            )
        )
    return items


def _window_items(by_period_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, row in enumerate(by_period_rows[:MAX_WINDOW_ROWS], start=1):
        title = str(row.get("window") or f"Window {index}")
        items.append(
            _base_item(
                f"period-window-{index}",
                "period_window",
                title,
                output_path="period_comparison_by_period.csv",
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="accept",
                references=[
                    {
                        "kind": "period_window",
                        "current": row.get("current"),
                        "previous": row.get("previous"),
                        "delta": row.get("delta"),
                        "delta_percent": row.get("delta_percent"),
                    }
                ],
                data=dict(row),
            )
        )
    return items


def _artifact_item_type(record: dict[str, Any]) -> str:
    kind = str(record.get("kind") or "")
    if kind in {"charts", "png", "html"}:
        return "chart_artifact"
    if kind in {"contexts", "json"}:
        return "context_artifact"
    if kind in {"briefs", "reports", "tables", "md", "docx", "csv", "xlsx"}:
        return "report_artifact"
    return "review_artifact"


def _artifact_title(record: dict[str, Any]) -> str:
    chart_type = record.get("chart_type")
    artifact_id = record.get("artifact_id")
    return str(chart_type or artifact_id or record.get("path") or "Artifact")


def _artifact_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    records = [
        record for record in manifest.get("artifacts", []) if isinstance(record, dict)
    ][:MAX_ARTIFACT_ITEMS]
    items: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        item_type = _artifact_item_type(record)
        missing = record.get("status") not in {"copied", "written"}
        items.append(
            _base_item(
                f"artifact-{index}",
                item_type,
                _artifact_title(record),
                source_path=str(record.get("source_path") or ""),
                output_path=str(record.get("pack_path") or record.get("path") or ""),
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="mark_unclear" if missing else "accept",
                data=dict(record),
            )
        )
    return items


def _followup_items(followups: dict[str, Any]) -> list[dict[str, Any]]:
    requests = [
        item for item in followups.get("requests", []) if isinstance(item, dict)
    ][:MAX_FOLLOWUP_ITEMS]
    return [
        _base_item(
            f"followup-{index}",
            "followup_request",
            str(request.get("request_id") or f"Follow-up {index}"),
            output_path="",
            allowed_actions=("accept", "reject", "edit", "mark_unclear", "skip"),
            recommended_action="mark_unclear",
            data=dict(request),
        )
        for index, request in enumerate(requests, start=1)
    ]


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
    """Write run intake before the chart package is rendered."""

    run_id = _run_id(input_path)
    options = recipe.get("options") or {}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": recipe.get("language") or "en",
        "input_paths": [input_path.as_posix()],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "period_comparison_chart_report_payload",
        "data_posture": _data_posture(input_path, recipe_path),
        "assumptions": {
            "source_row_count": source_row_count,
            "recipe_path": recipe_path.as_posix() if recipe_path else None,
            "mappings": recipe.get("mappings") or {},
            "currency": options.get("currency") or "EUR",
            "period_comparison_mode": options.get("period_comparison_mode"),
            "period_window": options.get("period_window"),
            "charts": options.get("charts"),
            "small_multiples": options.get("small_multiples", True),
            "small_multiples_dimension": options.get("small_multiples_dimension"),
        },
        "unresolved_questions": [],
        "dependency_check": {
            "status": "not_run_by_script",
            "note": "Codex should run scripts/check_dependencies.py before helper scripts.",
        },
        "status": "ready_for_period_comparison_run",
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
    monthly_rows: Sequence[dict[str, Any]],
    by_period_rows: Sequence[dict[str, Any]],
    audit: dict[str, Any],
) -> ReviewSessionResult:
    """Write chart/report review payload, pending decisions, and artifacts."""

    outputs = _output_records(output_dir)
    period_context = _load_json(output_dir / "period_comparison_context.json")
    items: list[dict[str, Any]] = []
    items.extend(_monthly_items(monthly_rows))
    items.extend(_window_items(by_period_rows))
    items.extend(_artifact_items({"artifacts": outputs}))
    items.append(
        _base_item(
            "period-comparison-context",
            "context_artifact",
            "Period comparison context",
            output_path="period_comparison_context.json",
            allowed_actions=("accept", "edit", "mark_unclear", "skip"),
            recommended_action="accept" if period_context else "mark_unclear",
            data=period_context,
        )
    )

    chart_count = sum(
        1
        for item in outputs
        if isinstance(item, dict) and item.get("kind") in {"png", "html"}
    )
    table_count = sum(
        1
        for item in outputs
        if isinstance(item, dict) and item.get("kind") in {"csv", "xlsx"}
    )
    options = recipe.get("options") or {}
    comparison = period_context.get("comparison") or {}
    totals = period_context.get("totals") or {}
    selection = period_context.get("small_multiples_selection") or {}
    review_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "source_paths": [input_path.as_posix()],
        "review_type": "period_comparison_chart_report_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(),
        "source_artifacts": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "recipe": _as_output_ref(recipe_path, output_dir),
            "used_recipe": "used_recipe.json",
            "monthly_results": "period_comparison_monthly.csv",
            "by_period_results": "period_comparison_by_period.csv",
            "period_comparison_audit": "period_comparison_audit.json",
            "period_comparison_summary": "period_comparison_summary.md",
            "period_context": "period_comparison_context.json",
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
            "monthly_row_count": len(monthly_rows),
            "window_row_count": len(by_period_rows),
            "chart_count": chart_count,
            "table_count": table_count,
            "period_comparison_mode": options.get("period_comparison_mode"),
            "current_period": (comparison.get("current") or {}).get("year"),
            "previous_period": (comparison.get("previous") or {}).get("year"),
            "current_total": totals.get("current"),
            "previous_total": totals.get("previous"),
            "delta": totals.get("delta"),
            "delta_percent": totals.get("delta_percent"),
            "currency": options.get("currency") or "EUR",
            "small_multiples_dimension": selection.get("dimension"),
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
                "Chart payloads are bounded for review; use CSV tables and context files as the full source set.",
                "ui_decisions.json is pending until Codex, MCP UI, or fallback review records decisions.",
            ],
            "next_actions": [
                "Render review_payload.json with the MCP widget when available.",
                "Use period_comparison_context.json before interpreting chart pixels.",
                "Write codex_business_analysis.md from reviewed source artifacts and caveats.",
            ],
            "status": "written_pending_review",
        },
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=[
            "python",
            "plugins/period-comparison/scripts/run_period_comparison.py",
        ],
    )

    return ReviewSessionResult(
        run_intake_path=run_intake_path,
        review_payload_path=review_payload_path,
        ui_decisions_path=ui_decisions_path,
        final_artifacts_path=final_artifacts_path,
        review_item_count=len(items),
    )
