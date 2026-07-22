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
PLUGIN_NAME = "variance-analysis"
WORKFLOW_NAME = "variance-analysis"
MAX_DRIVER_ROWS = 50
MAX_ARTIFACT_ITEMS = 200
MAX_FOLLOWUP_ITEMS = 50

_REVIEW_COPY: dict[str, dict[str, Any]] = {
    "en": {
        "product_title": "Variance Analysis",
        "handoff_title": "Review Handoff",
        "run_id": "Run ID",
        "review_payload": "Review payload",
        "run_intake": "Run intake",
        "pending_decisions": "Pending decisions",
        "applied_decisions": "Applied decisions",
        "final_artifacts": "Final artifacts",
        "review_in_codex": "Review In Codex",
        "validate_step": "Validate the payload with `{tool}`.",
        "render_step": "Render the review workbench with `{tool}`.",
        "save_step": "Save reviewer actions with `{tool}`.",
        "apply_step": "Apply reviewer actions with `{tool}`.",
        "columns": (
            "Type",
            "Element",
            "Suggested action",
            "Source",
            "Output",
            "Status",
        ),
        "driver_row": "Driver row {index}",
        "driver_rows_truncated": "Variance driver rows truncated in widget",
        "artifact": "Artifact",
        "followup": "Follow-up {index}",
        "context_title": "Standard variance context",
        "dependency_note": (
            "Codex should run scripts/check_dependencies.py before helper scripts."
        ),
        "data_posture_notes": [
            "Variance scripts read the source table and optional recipe locally and write bounded review artifacts.",
            "No external connector, upload path, remote SQL, or hosted notebook execution is used by default.",
        ],
        "caveats": [
            "Chart payloads are bounded for review; use variance_results.csv and context files as the full source set.",
            "ui_decisions.json is pending until Codex, MCP UI, or fallback review records decisions.",
        ],
        "next_actions": [
            "Render review_payload.json with the MCP widget when available.",
            "Use the standard variance context before interpreting chart pixels.",
            "Write codex_business_analysis.md from reviewed source artifacts and caveats.",
        ],
    },
    "es": {
        "product_title": "Análisis de variaciones",
        "handoff_title": "Entrega para revisión",
        "run_id": "ID de ejecución",
        "review_payload": "Datos de revisión",
        "run_intake": "Datos de ejecución",
        "pending_decisions": "Decisiones pendientes",
        "applied_decisions": "Decisiones aplicadas",
        "final_artifacts": "Artefactos finales",
        "review_in_codex": "Revisión en Codex",
        "validate_step": "Valide los datos con `{tool}`.",
        "render_step": "Abra el área de revisión con `{tool}`.",
        "save_step": "Guarde las decisiones del revisor con `{tool}`.",
        "apply_step": "Aplique las decisiones del revisor con `{tool}`.",
        "columns": (
            "Tipo",
            "Elemento",
            "Acción sugerida",
            "Fuente",
            "Salida",
            "Estado",
        ),
        "driver_row": "Fila de factor {index}",
        "driver_rows_truncated": (
            "Filas de factores de variación acotadas en el widget"
        ),
        "artifact": "Artefacto",
        "followup": "Seguimiento {index}",
        "context_title": "Contexto estándar de variaciones",
        "dependency_note": (
            "Codex debe ejecutar scripts/check_dependencies.py antes de los scripts auxiliares."
        ),
        "data_posture_notes": [
            "Los scripts de variaciones leen localmente la tabla fuente y la receta opcional y generan artefactos acotados para la revisión.",
            "De forma predeterminada no se utilizan conectores externos, rutas de carga, SQL remoto ni cuadernos alojados.",
        ],
        "caveats": [
            "Los datos de los gráficos están acotados para la revisión; utilice variance_results.csv y los archivos de contexto como conjunto completo de fuentes.",
            "ui_decisions.json permanece pendiente hasta que Codex, la interfaz MCP o la revisión alternativa registren las decisiones.",
        ],
        "next_actions": [
            "Cuando esté disponible, abra review_payload.json con el widget MCP.",
            "Utilice el contexto estándar de variaciones antes de interpretar los píxeles de los gráficos.",
            "Redacte codex_business_analysis.md a partir de los artefactos fuente revisados y las salvedades.",
        ],
    },
}


def _normalize_language(language: object | None) -> str:
    text = str(language or "en").strip().lower().replace("_", "-")
    code = text.split("-", 1)[0]
    return code if code in _REVIEW_COPY else "en"


def _review_copy(language: object | None) -> dict[str, Any]:
    return _REVIEW_COPY[_normalize_language(language)]


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written before the heavy variance run."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for one variance-analysis run."""

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


def _write_review_handoff_card(
    output_dir: Path,
    *,
    run_id: str,
    language: str,
) -> Path:
    copy = _review_copy(language)
    path = output_dir / "review_handoff.md"
    lines = [
        f"# {copy['product_title']} · {copy['handoff_title']}",
        "<!-- review-contract: Review Handoff -->",
        "",
        f"- {copy['run_id']}: `{run_id}`",
        f"- {copy['review_payload']}: `review_payload.json`",
        f"- {copy['run_intake']}: `run_intake.json`",
        f"- {copy['pending_decisions']}: `ui_decisions.json`",
        f"- {copy['applied_decisions']}: `applied_decisions.json`",
        f"- {copy['final_artifacts']}: `final_artifacts.json`",
        "",
        f"## {copy['review_in_codex']}",
        f"1. {copy['validate_step'].format(tool='validate_variance_analysis_review')}",
        f"2. {copy['render_step'].format(tool='render_variance_analysis_review')}",
        f"3. {copy['save_step'].format(tool='save_variance_analysis_decisions')}",
        f"4. {copy['apply_step'].format(tool='apply_variance_analysis_decisions')}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _review_handoff_output_record(path: Path, language: str) -> dict[str, Any]:
    copy = _review_copy(language)
    localized_required_text = (
        [copy["handoff_title"], copy["review_in_codex"]]
        if _normalize_language(language) == "es"
        else []
    )
    return {
        "path": path.name,
        "kind": "md",
        "status": "written",
        "required_text": [
            "Review Handoff",
            *localized_required_text,
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


def _data_posture(
    input_path: Path, recipe_path: Path | None, language: str
) -> dict[str, Any]:
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
        "notes": list(_review_copy(language)["data_posture_notes"]),
    }


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
    fields = (
        "item_type",
        "title",
        "recommended_action",
        "source_path",
        "output_path",
        "status",
    )
    labels = _review_copy(language)["columns"]
    return [
        {"field": field, "label": str(label)}
        for field, label in zip(fields, labels, strict=True)
    ]


def _num(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _top_driver_rows(result_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(
        result_rows,
        key=lambda row: abs(_num(row.get("total_delta"))),
        reverse=True,
    )
    return list(rows[:MAX_DRIVER_ROWS])


def _driver_items(
    result_rows: Sequence[dict[str, Any]], language: str
) -> list[dict[str, Any]]:
    copy = _review_copy(language)
    items: list[dict[str, Any]] = []
    for index, row in enumerate(_top_driver_rows(result_rows), start=1):
        dimensions = [
            key
            for key in row
            if key
            not in {
                "amount_baseline",
                "amount_comparison",
                "total_delta",
                "price_variance",
                "volume_variance",
                "mix_variance",
                "component_reconciliation_delta",
                "net_delta",
                "margin_delta",
            }
            and not key.startswith("margin_")
        ]
        title_parts = [
            str(row.get(dimension))
            for dimension in dimensions[:3]
            if row.get(dimension) not in (None, "")
        ]
        title = " / ".join(title_parts) or str(copy["driver_row"]).format(index=index)
        items.append(
            _base_item(
                f"variance-driver-{index}",
                "variance_driver",
                title,
                output_path="variance_results.csv",
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action=(
                    "mark_unclear"
                    if abs(_num(row.get("component_reconciliation_delta"))) > 0.01
                    else "accept"
                ),
                references=[
                    {
                        "kind": "variance_components",
                        "total_delta": row.get("total_delta"),
                        "price_variance": row.get("price_variance"),
                        "volume_variance": row.get("volume_variance"),
                        "mix_variance": row.get("mix_variance"),
                        "component_reconciliation_delta": row.get(
                            "component_reconciliation_delta"
                        ),
                    }
                ],
                data=dict(row),
            )
        )
    if len(result_rows) > MAX_DRIVER_ROWS:
        items.append(
            _base_item(
                "variance-drivers-truncated",
                "review_artifact",
                str(copy["driver_rows_truncated"]),
                output_path="variance_results.csv",
                allowed_actions=("accept", "mark_unclear", "skip"),
                recommended_action="mark_unclear",
                data={
                    "shown_count": MAX_DRIVER_ROWS,
                    "total_count": len(result_rows),
                    "full_results": "variance_results.csv",
                },
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


def _artifact_title(record: dict[str, Any], language: str) -> str:
    chart_type = record.get("chart_type")
    artifact_id = record.get("artifact_id")
    return str(
        chart_type
        or artifact_id
        or record.get("path")
        or _review_copy(language)["artifact"]
    )


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
                output_path=str(record.get("pack_path") or record.get("path") or ""),
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
                or str(_review_copy(language)["followup"]).format(index=index)
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


def _standard_context_summary(standard_context: dict[str, Any]) -> dict[str, Any]:
    totals = standard_context.get("totals") or {}
    dominant = standard_context.get("dominant_component") or {}
    return {
        "total_delta": totals.get("total_delta"),
        "amount_baseline": totals.get("amount_baseline"),
        "amount_comparison": totals.get("amount_comparison"),
        "component_sum": totals.get("component_sum"),
        "other_residual": totals.get("other_residual"),
        "dominant_component": dominant,
    }


def write_run_intake(
    output_dir: Path,
    input_path: Path,
    *,
    recipe_path: Path | None,
    recipe: dict[str, Any],
    source_row_count: int,
) -> RunIntakeResult:
    """Write run intake before the heavy legacy variance calculation."""

    language = _normalize_language(recipe.get("language"))
    copy = _review_copy(language)
    run_id = _run_id(input_path)
    options = recipe.get("options") or {}
    mappings = recipe.get("mappings") or {}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "input_paths": [input_path.as_posix()],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "variance_chart_report_payload",
        "data_posture": _data_posture(input_path, recipe_path, language),
        "assumptions": {
            "source_row_count": source_row_count,
            "recipe_path": recipe_path.as_posix() if recipe_path else None,
            "mappings": mappings,
            "comparison_basis": options.get("comparison_basis"),
            "period_comparison_mode": options.get("period_comparison_mode"),
            "currency": options.get("currency") or "EUR",
            "root_cause_bridge": options.get("root_cause_bridge"),
            "root_cause_bridge_alternative_sweep": options.get(
                "root_cause_bridge_alternative_sweep"
            ),
            "root_cause_component_bridge": options.get("root_cause_component_bridge"),
            "waterfall_chart": options.get("waterfall_chart"),
            "waterfall_small_multiples": options.get("waterfall_small_multiples"),
        },
        "unresolved_questions": [],
        "dependency_check": {
            "status": "not_run_by_script",
            "note": copy["dependency_note"],
        },
        "status": "ready_for_variance_run",
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
    result_rows: Sequence[dict[str, Any]],
    audit: dict[str, Any],
) -> ReviewSessionResult:
    """Write chart/report review payload, pending decisions, and artifacts."""

    language = _normalize_language(recipe.get("language"))
    copy = _review_copy(language)
    outputs = _output_records(output_dir)
    standard_context = _load_json(output_dir / "standard_variance_context.json")
    standard_summary = _standard_context_summary(standard_context)
    items: list[dict[str, Any]] = []
    items.extend(_driver_items(result_rows, language))
    items.extend(_artifact_items({"artifacts": outputs}, language))
    items.append(
        _base_item(
            "standard-variance-context",
            "context_artifact",
            str(copy["context_title"]),
            output_path="standard_variance_context.json",
            allowed_actions=("accept", "edit", "mark_unclear", "skip"),
            recommended_action="accept" if standard_context else "mark_unclear",
            data=standard_context,
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
    mappings = recipe.get("mappings") or {}
    options = recipe.get("options") or {}
    review_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "source_paths": [input_path.as_posix()],
        "review_type": "variance_chart_report_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(language),
        "source_artifacts": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "recipe": _as_output_ref(recipe_path, output_dir),
            "used_recipe": "used_recipe.json",
            "variance_results": "variance_results.csv",
            "variance_audit": "variance_audit.json",
            "variance_summary": "variance_summary.md",
            "standard_context": "standard_variance_context.json",
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
            "result_row_count": len(result_rows),
            "chart_count": chart_count,
            "table_count": table_count,
            "comparison_basis": options.get("comparison_basis"),
            "period_comparison_mode": options.get("period_comparison_mode"),
            "baseline_period": mappings.get("baseline_period"),
            "comparison_period": mappings.get("comparison_period"),
            "amount_column": mappings.get("amount_column"),
            "dimensions": mappings.get("dimensions") or [],
            "currency": options.get("currency") or "EUR",
            **standard_summary,
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
        language=language,
    )
    outputs = _output_records(output_dir)
    outputs = [
        output
        for output in outputs
        if not (
            isinstance(output, dict) and output.get("path") == review_handoff_path.name
        )
    ]
    outputs.append(_review_handoff_output_record(review_handoff_path, language))

    final_artifacts_path = _write_json(
        output_dir / "final_artifacts.json",
        {
            "schema_version": SCHEMA_VERSION,
            "plugin": PLUGIN_NAME,
            "workflow": WORKFLOW_NAME,
            "run_id": run_id,
            "completed_at": _utc_now(),
            "outputs": outputs,
            "caveats": list(copy["caveats"]),
            "next_actions": list(copy["next_actions"]),
            "status": "written_pending_review",
        },
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=["python", "plugins/variance-analysis/scripts/run_variance.py"],
    )

    return ReviewSessionResult(
        run_intake_path=run_intake_path,
        review_payload_path=review_payload_path,
        ui_decisions_path=ui_decisions_path,
        final_artifacts_path=final_artifacts_path,
        review_item_count=len(items),
    )
