from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from report_builder_core import (  # noqa: E402
    analysis_for_section,
    clean_text,
    inspect_table,
    load_tables,
    render_markdown,
    selected_sections,
    write_json,
    write_report_docx,
    write_tables_workbook,
)
from review_session import build_output_records  # noqa: E402

__all__ = ["apply_review_edits", "main"]

REGENERATE_NATIVE_OUTPUT_ACTION = (
    "Regenerate native DOCX/XLSX/PDF outputs before final handoff."
)
FINAL_HANDOFF_ACTION = (
    "Use final_artifacts.json as the reviewed artifact gallery for handoff."
)
COMPLETE_REVIEW_ACTION = "Complete remaining review decisions before final handoff."


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    write_json(path, payload)


def _parse_section_comment_path(target_path: object) -> str | None:
    return _parse_section_field_path(target_path, "codex_comment")


def _parse_section_mapping_path(target_path: object) -> str | None:
    return _parse_section_field_path(target_path, "assigned_table")


def _parse_section_field_path(target_path: object, field_name: str) -> str | None:
    text = clean_text(target_path)
    prefix = "sections."
    suffix = f".{field_name}"
    if not text.startswith(prefix) or not text.endswith(suffix):
        return None
    section_key = text[len(prefix) : -len(suffix)]
    return clean_text(section_key) or None


def _eligible_report_builder_effect(effect: dict[str, Any]) -> bool:
    """Return whether a review edit has the explicit local regeneration contract."""

    if effect.get("action") != "edit":
        return False
    if effect.get("artifact_update") != "native_regeneration_pending":
        return False
    if clean_text(effect.get("target_artifact")) != "report.docx":
        return False
    if not (
        _parse_section_comment_path(effect.get("target_path"))
        or _parse_section_mapping_path(effect.get("target_path"))
    ):
        return False
    return bool(clean_text(effect.get("edit_value")))


def _backup_native(output_dir: Path, item_id: str, target_name: str) -> dict[str, Any]:
    source = output_dir / target_name
    if not source.exists():
        return {}
    stem = source.stem or "report"
    suffix = source.suffix or ".docx"
    safe_item = "".join(
        char if char.isalnum() or char in "._-" else "-" for char in item_id
    )
    relative = Path("revisions") / "originals" / f"{stem}__{safe_item}{suffix}"
    target = output_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copy2(source, target)
    return {
        "path": relative.as_posix(),
        "kind": suffix.lstrip(".") or "file",
        "status": "backup_original",
        "source_artifact": target_name,
        "item_id": item_id,
    }


def _upsert_output(outputs: list[dict[str, Any]], record: dict[str, Any]) -> None:
    path = record.get("path")
    for index, output in enumerate(outputs):
        if isinstance(output, dict) and output.get("path") == path:
            outputs[index] = {**output, **record}
            return
    outputs.append(record)


def _application_status(applied: dict[str, Any]) -> str:
    if int(applied.get("blocker_count") or 0) > 0:
        return "blocked"
    if int(applied.get("native_regeneration_count") or 0) > 0:
        return "partial_review_applied"
    if int(applied.get("decision_count") or 0) < int(applied.get("item_count") or 0):
        return "partial_review_applied"
    return "final_ready"


def _next_actions(current: list[Any], status: str) -> list[str]:
    next_actions = [
        clean_text(action)
        for action in current
        if clean_text(action) and clean_text(action) != REGENERATE_NATIVE_OUTPUT_ACTION
    ]
    if status == "final_ready":
        next_actions.append(FINAL_HANDOFF_ACTION)
    elif status == "partial_review_applied":
        next_actions.append(COMPLETE_REVIEW_ACTION)
    return list(dict.fromkeys(next_actions))


def _recompute_report_analysis(
    output_dir: Path,
    recipe: dict[str, Any],
    audit: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    input_path = Path(clean_text(audit.get("input_path"))).expanduser()
    if not input_path.exists():
        raise FileNotFoundError(
            f"Cannot regenerate Report Builder mapping edits because input_path is missing: {input_path}"
        )
    raw_tables = load_tables(input_path, output_dir)
    table_by_id = {clean_text(table.get("table_id")): table for table in raw_tables}
    sections_analysis = [
        analysis_for_section(section_key, section_recipe, table_by_id)
        for section_key, section_recipe in selected_sections(recipe).items()
    ]
    assigned_sections = [
        section for section in sections_analysis if section["status"] == "assigned"
    ]
    missing_sections = [
        section["section"]
        for section in sections_analysis
        if section["status"] != "assigned"
    ]
    analysis = {
        "version": 1,
        "language": recipe.get("language", "en"),
        "document_language": recipe.get("document_language", "auto"),
        "report_type": recipe.get("report_type", "management_report"),
        "entity": clean_text(recipe.get("entity")),
        "period": clean_text(recipe.get("period")),
        "sections": sections_analysis,
        "assigned_section_count": len(assigned_sections),
        "missing_sections": missing_sections,
    }
    updated_audit = dict(audit)
    updated_audit.update(
        {
            "table_count": len(raw_tables),
            "section_count": len(sections_analysis),
            "assigned_section_count": len(assigned_sections),
            "missing_section_count": len(missing_sections),
            "missing_sections": missing_sections,
            "codex_narrative_sections": sum(
                1
                for section in sections_analysis
                if clean_text(section.get("codex_comment"))
            ),
        }
    )
    write_json(
        output_dir / "report_tables.json",
        {"tables": [inspect_table(table) for table in raw_tables]},
    )
    write_tables_workbook(output_dir / "report_tables.xlsx", analysis)
    return analysis, updated_audit


def _validate_source_mapping_effects(
    effects: Sequence[dict[str, Any]],
    analysis: dict[str, Any],
) -> None:
    sections = {
        clean_text(section.get("section")): section
        for section in analysis.get("sections", [])
        if isinstance(section, dict)
    }
    for effect in effects:
        section_key = _parse_section_mapping_path(effect.get("target_path"))
        if not section_key:
            continue
        section = sections.get(section_key)
        edit_value = clean_text(effect.get("edit_value"))
        if (
            not isinstance(section, dict)
            or section.get("status") != "assigned"
            or clean_text(section.get("assigned_table")) != edit_value
        ):
            raise ValueError(
                "Report Builder source mapping edit must use an exact local table_id: "
                f"{edit_value}"
            )


def apply_review_edits(
    output_dir: Path,
    applied_decisions_path: Path,
    final_artifacts_path: Path,
) -> dict[str, Any]:
    """Apply explicit Report Builder section edits and regenerate native outputs."""

    output_dir = output_dir.resolve()
    applied_decisions_path = applied_decisions_path.resolve()
    final_artifacts_path = final_artifacts_path.resolve()
    recipe_path = output_dir / "used_recipe.json"
    analysis_path = output_dir / "report_analysis.json"
    audit_path = output_dir / "report_audit.json"
    markdown_path = output_dir / "report_draft.md"
    docx_path = output_dir / "report.docx"

    applied = _read_json(applied_decisions_path)
    final_artifacts = _read_json(final_artifacts_path)
    effects = [
        effect for effect in applied.get("effects", []) if isinstance(effect, dict)
    ]
    candidate_effects = [
        effect for effect in effects if _eligible_report_builder_effect(effect)
    ]
    if not candidate_effects:
        return {
            "ok": True,
            "updated_effect_count": 0,
            "message": "No explicit Report Builder native edits were eligible for regeneration.",
        }

    recipe = _read_json(recipe_path)
    analysis = _read_json(analysis_path)
    audit = _read_json(audit_path)
    source_mapping_changed = False

    updated_effects: list[dict[str, Any]] = []
    backup_outputs: list[dict[str, Any]] = []
    backup_written = False

    for effect in candidate_effects:
        section_key = _parse_section_comment_path(
            effect.get("target_path")
        ) or _parse_section_mapping_path(effect.get("target_path"))
        edit_value = clean_text(effect.get("edit_value"))
        if not section_key or not edit_value:
            continue
        sections = recipe.setdefault("sections", {})
        if not isinstance(sections, dict) or section_key not in sections:
            continue
        section_recipe = sections.setdefault(section_key, {})
        if not isinstance(section_recipe, dict):
            continue
        if not backup_written:
            backup = _backup_native(
                output_dir, clean_text(effect.get("item_id")), "report.docx"
            )
            if backup:
                backup_outputs.append(backup)
            backup_written = True
        if _parse_section_mapping_path(effect.get("target_path")):
            section_recipe["assigned_table"] = edit_value
            source_mapping_changed = True
        else:
            section_recipe["codex_comment"] = edit_value
            for section in analysis.get("sections", []):
                if (
                    isinstance(section, dict)
                    and clean_text(section.get("section")) == section_key
                ):
                    section["codex_comment"] = edit_value
        effect["artifact_update"] = "native_artifact_regenerated"
        effect["requires_native_regeneration"] = False
        effect["native_regeneration_status"] = "regenerated"
        effect["native_regenerated_paths"] = (
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
        updated_effects.append(effect)

    if not updated_effects:
        return {
            "ok": True,
            "updated_effect_count": 0,
            "message": "No Report Builder section matched the requested native edits.",
        }

    if source_mapping_changed:
        analysis, audit = _recompute_report_analysis(output_dir, recipe, audit)
        _validate_source_mapping_effects(updated_effects, analysis)
    else:
        audit["codex_narrative_sections"] = sum(
            1
            for section in analysis.get("sections", [])
            if isinstance(section, dict) and clean_text(section.get("codex_comment"))
        )
    audit["review_native_regeneration"] = {
        "status": "regenerated",
        "updated_effect_count": len(updated_effects),
        "outputs": sorted(
            {
                path
                for effect in updated_effects
                for path in effect.get("native_regenerated_paths", [])
                if clean_text(path)
            }
        ),
    }

    _write_json(recipe_path, recipe)
    _write_json(analysis_path, analysis)
    _write_json(audit_path, audit)
    markdown_path.write_text(render_markdown(recipe, analysis), encoding="utf-8")
    write_report_docx(recipe, analysis, audit, docx_path)

    native_pending = [
        clean_text(effect.get("target_artifact"))
        for effect in effects
        if effect.get("artifact_update") == "native_regeneration_pending"
        and effect.get("requires_native_regeneration")
    ]
    native_regenerated_paths = sorted(
        {
            path
            for effect in updated_effects
            for path in effect.get("native_regenerated_paths", [])
            if clean_text(path)
        }
    )
    applied["effects"] = effects
    applied["native_regeneration_count"] = len(native_pending)
    applied["native_regeneration_paths"] = native_pending
    applied["native_regenerated_count"] = len(updated_effects)
    applied["native_regenerated_paths"] = native_regenerated_paths
    original_backup_paths = list(applied.get("original_backup_paths") or [])
    for backup in backup_outputs:
        if backup["path"] not in original_backup_paths:
            original_backup_paths.append(backup["path"])
    applied["original_backup_paths"] = original_backup_paths
    applied["application_status"] = _application_status(applied)

    outputs = [
        output
        for output in final_artifacts.get("outputs", [])
        if isinstance(output, dict)
    ]
    fresh_outputs = {
        clean_text(output.get("path")): output
        for output in build_output_records(output_dir, audit, analysis)
        if isinstance(output, dict)
    }
    for path_value in native_regenerated_paths:
        fresh = dict(fresh_outputs.get(path_value) or {})
        _upsert_output(
            outputs,
            fresh
            | {
                "path": path_value,
                "kind": fresh.get("kind")
                or Path(path_value).suffix.lstrip(".")
                or "file",
                "status": "updated_from_review",
                "native_regenerated": True,
            },
        )
    for backup in backup_outputs:
        _upsert_output(outputs, backup)
    final_artifacts["outputs"] = outputs
    final_artifacts["status"] = applied["application_status"]
    final_artifacts["review_status"] = applied["application_status"]
    review_application = final_artifacts.setdefault("review_application", {})
    if isinstance(review_application, dict):
        review_application["application_status"] = applied["application_status"]
        review_application["native_regeneration_count"] = applied[
            "native_regeneration_count"
        ]
        review_application["native_regeneration_paths"] = applied[
            "native_regeneration_paths"
        ]
        review_application["native_regenerated_count"] = applied[
            "native_regenerated_count"
        ]
        review_application["native_regenerated_paths"] = native_regenerated_paths
        review_application["original_backup_paths"] = original_backup_paths
    final_artifacts["next_actions"] = _next_actions(
        list(final_artifacts.get("next_actions") or []),
        applied["application_status"],
    )

    _write_json(applied_decisions_path, applied)
    _write_json(final_artifacts_path, final_artifacts)
    return {
        "ok": True,
        "updated_effect_count": len(updated_effects),
        "native_regenerated_paths": native_regenerated_paths,
        "backup_paths": [backup["path"] for backup in backup_outputs],
        "application_status": applied["application_status"],
        "applied_decisions": applied,
        "final_artifacts": final_artifacts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply Report Builder review edits and regenerate native outputs."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--applied-decisions", type=Path, required=True)
    parser.add_argument("--final-artifacts", type=Path, required=True)
    args = parser.parse_args(argv)
    result = apply_review_edits(
        args.output_dir,
        args.applied_decisions,
        args.final_artifacts,
    )
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
