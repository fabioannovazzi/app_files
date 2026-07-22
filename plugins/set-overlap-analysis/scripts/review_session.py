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

_REVIEW_COPY: dict[str, dict[str, Any]] = {
    "en": {
        "product_title": "Set Overlap Analysis",
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
            "Overlap item",
            "Suggested action",
            "Source",
            "Output",
            "Status",
        ),
        "set": "Set {index}",
        "set_items": "{name}: {count} items",
        "intersection": "Intersection {index}",
        "intersection_items": "{name}: {count} items",
        "pair_items": "{left} + {right}: {count} shared items",
        "artifact": "Artifact {index}",
        "context_title": "Set overlap context",
        "audit_title": "Set overlap audit",
        "dependency_note": (
            "Codex should run scripts/check_dependencies.py before helper scripts."
        ),
        "data_posture_notes": [
            "Set-overlap scripts read the source table and optional recipe locally and write bounded review artifacts.",
            "No external connector, upload path, remote SQL, or hosted notebook execution is used by default.",
        ],
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
    },
    "es": {
        "product_title": "Análisis de solapamiento de conjuntos",
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
            "Elemento de solapamiento",
            "Acción sugerida",
            "Fuente",
            "Salida",
            "Estado",
        ),
        "set": "Conjunto {index}",
        "set_items": "{name}: {count} elementos",
        "intersection": "Intersección {index}",
        "intersection_items": "{name}: {count} elementos",
        "pair_items": "{left} + {right}: {count} elementos compartidos",
        "artifact": "Artefacto {index}",
        "context_title": "Contexto del solapamiento de conjuntos",
        "audit_title": "Auditoría del solapamiento de conjuntos",
        "dependency_note": (
            "Codex debe ejecutar scripts/check_dependencies.py antes de los scripts auxiliares."
        ),
        "data_posture_notes": [
            "Los scripts de solapamiento leen localmente la tabla fuente y la receta opcional y generan artefactos acotados para la revisión.",
            "De forma predeterminada no se utilizan conectores externos, rutas de carga, SQL remoto ni cuadernos alojados.",
        ],
        "caveats": [
            "Utilice las tablas CSV y set_overlap_context.json antes de interpretar los píxeles de Venn o UpSet.",
            "El diagrama de Venn solo es válido cuando se han representado exactamente dos o tres conjuntos seleccionados.",
            "ui_decisions.json permanece pendiente hasta que Codex, la interfaz MCP o la revisión alternativa registren las decisiones.",
        ],
        "next_actions": [
            "Ejecute validate_set_overlap_review y, cuando MCP esté disponible, render_set_overlap_review.",
            "Revise las mayores intersecciones exactas y los solapamientos por pares antes de la interpretación final.",
            "Registre las decisiones aceptadas, editadas o rechazadas antes de considerar revisado el paquete de solapamiento.",
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
        f"1. {copy['validate_step'].format(tool='validate_set_overlap_review')}",
        f"2. {copy['render_step'].format(tool='render_set_overlap_review')}",
        f"3. {copy['save_step'].format(tool='save_set_overlap_decisions')}",
        f"4. {copy['apply_step'].format(tool='apply_set_overlap_decisions')}",
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


def _as_output_ref(path: str | Path | None, output_dir: Path) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    try:
        return candidate.relative_to(output_dir).as_posix()
    except ValueError:
        return candidate.as_posix()


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


def _set_summary_items(context: dict[str, Any], language: str) -> list[dict[str, Any]]:
    copy = _review_copy(language)
    rows = [row for row in context.get("set_summary", []) if isinstance(row, dict)]
    rows.sort(key=lambda row: _num(row.get("item_count")), reverse=True)
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        set_name = str(
            row.get("set")
            or row.get("Retailer")
            or str(copy["set"]).format(index=index)
        )
        selected = bool(row.get("selected", True))
        items.append(
            _base_item(
                f"set-summary-{index}",
                "set_summary",
                str(copy["set_items"]).format(
                    name=set_name,
                    count=int(_num(row.get("item_count"))),
                ),
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


def _intersection_items(context: dict[str, Any], language: str) -> list[dict[str, Any]]:
    copy = _review_copy(language)
    rows = [row for row in context.get("intersections", []) if isinstance(row, dict)]
    rows.sort(key=lambda row: _num(row.get("item_count")), reverse=True)
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:MAX_INTERSECTION_ITEMS], start=1):
        title = str(
            row.get("intersection") or str(copy["intersection"]).format(index=index)
        )
        item_count = int(_num(row.get("item_count")))
        items.append(
            _base_item(
                f"intersection-{index}",
                "overlap_intersection",
                str(copy["intersection_items"]).format(
                    name=title,
                    count=item_count,
                ),
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


def _pair_items(context: dict[str, Any], language: str) -> list[dict[str, Any]]:
    copy = _review_copy(language)
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
                str(copy["pair_items"]).format(
                    left=left,
                    right=right,
                    count=item_count,
                ),
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


def _artifact_items(manifest: dict[str, Any], language: str) -> list[dict[str, Any]]:
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
                output_path
                or str(_review_copy(language)["artifact"]).format(index=index),
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

    language = _normalize_language(recipe.get("language"))
    copy = _review_copy(language)
    run_id = _run_id(input_path)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "input_paths": [input_path.as_posix()],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "set_overlap_review_payload",
        "data_posture": _data_posture(input_path, recipe_path, language),
        "assumptions": {
            "source_row_count": source_row_count,
            "recipe_path": recipe_path.as_posix() if recipe_path else None,
            "mappings": recipe.get("mappings") or {},
            "options": recipe.get("options") or {},
        },
        "unresolved_questions": [],
        "dependency_check": {
            "status": "not_run_by_script",
            "note": copy["dependency_note"],
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

    language = _normalize_language(recipe.get("language"))
    copy = _review_copy(language)
    outputs = _output_records(output_dir)
    items: list[dict[str, Any]] = []
    items.extend(_set_summary_items(context, language))
    items.extend(_intersection_items(context, language))
    items.extend(_pair_items(context, language))
    items.extend(_chart_items(context))
    items.extend(_artifact_items({"artifacts": outputs}, language))
    items.append(
        _base_item(
            "set-overlap-context",
            "context_artifact",
            str(copy["context_title"]),
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
            str(copy["audit_title"]),
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
        "language": language,
        "source_paths": [input_path.as_posix()],
        "review_type": "set_overlap_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(language),
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
