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
PLUGIN_NAME = "distribution-analysis"
WORKFLOW_NAME = "distribution-analysis"
MAX_SUMMARY_ROWS = 80
MAX_ARTIFACT_ITEMS = 300
MAX_FOLLOWUP_ITEMS = 50


_SPANISH_ALIASES = {"es", "spa", "spanish", "espanol", "español"}


def _language_code(value: Any) -> str:
    """Normalize Spanish aliases while preserving every other recipe language."""

    language = str(value or "en").strip() or "en"
    normalized = language.lower().replace("_", "-")
    if normalized.split("-", 1)[0] in _SPANISH_ALIASES:
        return "es"
    return language


def _is_spanish(language: str) -> bool:
    return language == "es"


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written before distribution rendering."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for one distribution run."""

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


def _review_columns(language: str) -> list[dict[str, str]]:
    if _is_spanish(language):
        return [
            {"field": "item_type", "label": "Tipo"},
            {"field": "title", "label": "Elemento"},
            {"field": "recommended_action", "label": "Acción sugerida"},
            {"field": "source_path", "label": "Fuente"},
            {"field": "output_path", "label": "Salida"},
            {"field": "status", "label": "Estado"},
        ]
    return [
        {"field": "item_type", "label": "Type"},
        {"field": "title", "label": "Element"},
        {"field": "recommended_action", "label": "Suggested action"},
        {"field": "source_path", "label": "Source"},
        {"field": "output_path", "label": "Output"},
        {"field": "status", "label": "Status"},
    ]


def _summary_items(
    summary_rows: Sequence[dict[str, Any]],
    *,
    metric: str,
    language: str,
) -> list[dict[str, Any]]:
    rows = sorted(
        summary_rows,
        key=lambda row: abs(_num(row.get("max")) - _num(row.get("min"))),
        reverse=True,
    )[:MAX_SUMMARY_ROWS]
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        fallback = f"Periodo {index}" if _is_spanish(language) else f"Period {index}"
        period = str(row.get("Period") or row.get("period") or fallback)
        items.append(
            _base_item(
                f"distribution-summary-{index}",
                "distribution_summary",
                period,
                output_path="distribution_summary.csv",
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action=(
                    "mark_unclear" if _num(row.get("rows")) == 0 else "accept"
                ),
                references=[
                    {
                        "kind": "distribution_statistics",
                        "metric": metric,
                        "rows": row.get("rows"),
                        "mean": row.get("mean"),
                        "median": row.get("median"),
                        "std": row.get("std"),
                        "min": row.get("min"),
                        "max": row.get("max"),
                    }
                ],
                data=dict(row),
            )
        )
    return items


def _artifact_item_type(record: dict[str, Any]) -> str:
    kind = str(record.get("kind") or "")
    if kind in {"chart", "charts"}:
        return "chart_artifact"
    if kind in {"context", "contexts"}:
        return "context_artifact"
    if kind in {"brief", "briefs", "report", "reports", "table", "tables"}:
        return "report_artifact"
    return "review_artifact"


def _artifact_title(record: dict[str, Any], language: str) -> str:
    chart_type = record.get("chart_type")
    artifact_id = record.get("artifact_id")
    fallback = "Artefacto" if _is_spanish(language) else "Artifact"
    return str(chart_type or artifact_id or record.get("path") or fallback)


def _artifact_output_path(record: dict[str, Any]) -> str:
    return str(record.get("pack_path") or record.get("path") or "")


def _artifact_items(manifest: dict[str, Any], language: str) -> list[dict[str, Any]]:
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
                _artifact_title(record, language),
                source_path=str(record.get("source_path") or ""),
                output_path=_artifact_output_path(record),
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="mark_unclear" if missing else "accept",
                data=dict(record),
            )
        )
    return items


def _followup_items(followups: dict[str, Any], language: str) -> list[dict[str, Any]]:
    requests = [
        item for item in followups.get("requests", []) if isinstance(item, dict)
    ][:MAX_FOLLOWUP_ITEMS]
    return [
        _base_item(
            f"followup-{index}",
            "followup_request",
            str(
                request.get("request_id")
                or request.get("type")
                or (
                    f"Seguimiento {index}"
                    if _is_spanish(language)
                    else f"Follow-up {index}"
                )
            ),
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
    """Write run intake before the legacy distribution package is rendered."""

    run_id = _run_id(input_path)
    options = recipe.get("options") or {}
    language = _language_code(recipe.get("language"))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "input_paths": [input_path.as_posix()],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "distribution_chart_report_payload",
        "data_posture": _data_posture(input_path, recipe_path),
        "assumptions": {
            "source_row_count": source_row_count,
            "recipe_path": recipe_path.as_posix() if recipe_path else None,
            "mappings": recipe.get("mappings") or {},
            "currency": options.get("currency") or "EUR",
            "charts": options.get("charts"),
            "selected_periods": options.get("selected_periods"),
            "small_multiples": options.get("small_multiples", True),
            "small_multiples_dimension": options.get("small_multiples_dimension"),
        },
        "unresolved_questions": [],
        "dependency_check": {
            "status": "not_run_by_script",
            "note": (
                "Codex debe ejecutar scripts/check_dependencies.py antes de los scripts auxiliares."
                if _is_spanish(language)
                else "Codex should run scripts/check_dependencies.py before helper scripts."
            ),
        },
        "status": "ready_for_distribution_run",
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
    summary_rows: Sequence[dict[str, Any]],
    audit: dict[str, Any],
) -> ReviewSessionResult:
    """Write chart/report review payload, pending decisions, and artifacts."""

    language = _language_code(recipe.get("language"))
    outputs = _output_records(output_dir)
    distribution_context = _load_json(output_dir / "distribution_context.json")
    mappings = recipe.get("mappings") or {}
    metric = str(mappings.get("metric_column") or "")
    items: list[dict[str, Any]] = []
    items.extend(_summary_items(summary_rows, metric=metric, language=language))
    items.extend(_artifact_items({"artifacts": outputs}, language))
    items.append(
        _base_item(
            "distribution-context",
            "context_artifact",
            (
                "Contexto de distribución"
                if _is_spanish(language)
                else "Distribution context"
            ),
            output_path="distribution_context.json",
            allowed_actions=("accept", "edit", "mark_unclear", "skip"),
            recommended_action="accept" if distribution_context else "mark_unclear",
            data=distribution_context,
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
    chart_audits = audit.get("charts") if isinstance(audit.get("charts"), list) else []
    options = recipe.get("options") or {}
    widest = max(
        summary_rows,
        key=lambda row: abs(_num(row.get("max")) - _num(row.get("min"))),
        default={},
    )
    review_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "source_paths": [input_path.as_posix()],
        "review_type": "distribution_chart_report_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(language),
        "source_artifacts": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "recipe": _as_output_ref(recipe_path, output_dir),
            "used_recipe": "used_recipe.json",
            "summary_table": "distribution_summary.csv",
            "canonical_table": "distribution_canonical.csv",
            "distribution_audit": "distribution_audit.json",
            "distribution_summary": "distribution_summary.md",
            "distribution_context": "distribution_context.json",
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
            "summary_row_count": len(summary_rows),
            "chart_count": chart_count,
            "table_count": table_count,
            "metric": metric,
            "distribution_dimension": mappings.get("distribution_dimension"),
            "selected_periods": options.get("selected_periods") or [],
            "widest_period": widest.get("Period") or widest.get("period"),
            "widest_range": _num(widest.get("max")) - _num(widest.get("min")),
            "currency": options.get("currency") or "EUR",
            "legacy_chart_attempt_count": len(chart_audits),
            "legacy_chart_written_count": sum(
                1
                for chart_audit in chart_audits
                if isinstance(chart_audit, dict)
                and chart_audit.get("status") == "written_legacy"
            ),
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
            "caveats": (
                [
                    "Los datos de los gráficos están acotados para la revisión; utilice las tablas CSV y los archivos de contexto como conjunto completo de fuentes.",
                    "ui_decisions.json queda pendiente hasta que Codex, la interfaz MCP o la revisión alternativa registren las decisiones.",
                ]
                if _is_spanish(language)
                else [
                    "Chart payloads are bounded for review; use CSV tables and context files as the full source set.",
                    "ui_decisions.json is pending until Codex, MCP UI, or fallback review records decisions.",
                ]
            ),
            "next_actions": (
                [
                    "Renderice review_payload.json con el widget MCP cuando esté disponible.",
                    "Consulte distribution_context.json antes de interpretar los píxeles de los gráficos.",
                    "Redacte codex_business_analysis.md o actualice el informe del cliente a partir de las fuentes revisadas y las advertencias.",
                ]
                if _is_spanish(language)
                else [
                    "Render review_payload.json with the MCP widget when available.",
                    "Use distribution_context.json before interpreting chart pixels.",
                    "Write codex_business_analysis.md or update the client report from reviewed source artifacts and caveats.",
                ]
            ),
            "status": "written_pending_review",
        },
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=["python", "plugins/distribution-analysis/scripts/run_distribution.py"],
    )

    return ReviewSessionResult(
        run_intake_path=run_intake_path,
        review_payload_path=review_payload_path,
        ui_decisions_path=ui_decisions_path,
        final_artifacts_path=final_artifacts_path,
        review_item_count=len(items),
    )
