from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import openpyxl

__all__ = ["apply_review_edits", "main"]

REGENERATE_NATIVE_OUTPUT_ACTION = (
    "Regenerate native DOCX/XLSX/PDF outputs before final handoff."
)
FINAL_HANDOFF_ACTION = (
    "Use final_artifacts.json as the reviewed artifact gallery for handoff."
)
COMPLETE_REVIEW_ACTION = "Complete remaining review decisions before final handoff."


def clean_text(value: object) -> str:
    """Return a stripped string for safe JSON field comparison."""

    return value.strip() if isinstance(value, str) else ""


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _eligible_check_results_effect(effect: dict[str, Any]) -> bool:
    """Return whether a structured CSV edit should refresh the XLSX workbook."""

    if effect.get("action") != "edit":
        return False
    if effect.get("artifact_update") != "structured_artifact_updated":
        return False
    if clean_text(effect.get("target_artifact")) != "check_results.csv":
        return False
    paths = effect.get("derived_native_regeneration_paths")
    if not isinstance(paths, list) or "check_results.xlsx" not in paths:
        return False
    return bool(clean_text(effect.get("edit_value")))


def _safe_item_id(value: object) -> str:
    text = clean_text(value) or "item"
    cleaned = "".join(char if char.isalnum() or char in "._-" else "-" for char in text)
    return cleaned.strip("-") or "item"


def _backup_native(output_dir: Path, item_id: str, target_name: str) -> dict[str, Any]:
    source = output_dir / target_name
    if not source.exists():
        return {}
    suffix = source.suffix or ".xlsx"
    relative = (
        Path("revisions")
        / "originals"
        / f"{source.stem}__{_safe_item_id(item_id)}{suffix}"
    )
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


def _csv_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise ValueError(f"Cannot regenerate workbook from empty CSV: {path}")
    return rows[0], rows[1:]


def _write_check_results_workbook(csv_path: Path, workbook_path: Path) -> int:
    header, rows = _csv_rows(csv_path)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "check_results"
    sheet.append(header)
    for row in rows:
        sheet.append([value if value != "" else None for value in row])
    workbook_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(workbook_path)
    return len(rows)


def _column_letters(index: int) -> str:
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _required_cells_for_effects(
    sheet_name: str,
    header: list[str],
    rows: list[list[str]],
    effects: list[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    cells: dict[str, str] = {}
    for effect in effects:
        structured_update = effect.get("structured_update")
        update = structured_update if isinstance(structured_update, dict) else {}
        id_field = clean_text(update.get("id_field") or effect.get("target_id_field"))
        record_id = clean_text(
            update.get("record_id") or effect.get("target_record_id")
        )
        target_field = clean_text(
            update.get("target_field") or effect.get("target_field")
        )
        edit_value = clean_text(effect.get("edit_value"))
        if not id_field or not record_id or not target_field or not edit_value:
            continue
        if id_field not in header or target_field not in header:
            continue
        id_index = header.index(id_field)
        target_index = header.index(target_field)
        for row_number, row in enumerate(rows, start=2):
            if len(row) <= id_index or str(row[id_index]) != record_id:
                continue
            cell_ref = f"{_column_letters(target_index + 1)}{row_number}"
            cells[cell_ref] = edit_value
            break
    return {sheet_name: cells} if cells else {}


def _effect_native_paths(effect: dict[str, Any]) -> list[str]:
    paths = effect.get("derived_native_regeneration_paths")
    if isinstance(paths, list) and paths:
        return [clean_text(path) for path in paths if clean_text(path)]
    if effect.get("requires_native_regeneration"):
        target = clean_text(effect.get("target_artifact"))
        return [target] if target else []
    return []


def _pending_native_paths(effects: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for effect in effects:
        if not effect.get("requires_native_regeneration"):
            continue
        paths.extend(_effect_native_paths(effect))
    return sorted(dict.fromkeys(paths))


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


def apply_review_edits(
    output_dir: Path,
    applied_decisions_path: Path,
    final_artifacts_path: Path,
) -> dict[str, Any]:
    """Regenerate the Check Entries workbook after explicit CSV review edits."""

    output_dir = output_dir.resolve()
    applied_decisions_path = applied_decisions_path.resolve()
    final_artifacts_path = final_artifacts_path.resolve()
    csv_path = output_dir / "check_results.csv"
    workbook_path = output_dir / "check_results.xlsx"

    applied = _read_json(applied_decisions_path)
    final_artifacts = _read_json(final_artifacts_path)
    effects = [
        effect for effect in applied.get("effects", []) if isinstance(effect, dict)
    ]
    candidate_effects = [
        effect for effect in effects if _eligible_check_results_effect(effect)
    ]
    if not candidate_effects:
        return {
            "ok": True,
            "updated_effect_count": 0,
            "message": "No Check Entries workbook regeneration was required.",
        }

    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    backup_outputs: list[dict[str, Any]] = []
    backup = _backup_native(
        output_dir,
        clean_text(candidate_effects[0].get("item_id")),
        "check_results.xlsx",
    )
    if backup:
        backup_outputs.append(backup)

    header, rows = _csv_rows(csv_path)
    row_count = _write_check_results_workbook(csv_path, workbook_path)
    required_cells = _required_cells_for_effects(
        "check_results",
        header,
        rows,
        candidate_effects,
    )

    for effect in candidate_effects:
        effect["requires_native_regeneration"] = False
        effect["native_regeneration_status"] = "regenerated"
        effect["native_regenerated_paths"] = ["check_results.xlsx"]

    native_pending = _pending_native_paths(effects)
    native_regenerated_paths = ["check_results.xlsx"]
    applied["effects"] = effects
    applied["native_regeneration_count"] = len(native_pending)
    applied["native_regeneration_paths"] = native_pending
    applied["native_regenerated_count"] = len(candidate_effects)
    applied["native_regenerated_paths"] = native_regenerated_paths
    original_backup_paths = list(applied.get("original_backup_paths") or [])
    for backup_output in backup_outputs:
        if backup_output["path"] not in original_backup_paths:
            original_backup_paths.append(backup_output["path"])
    applied["original_backup_paths"] = original_backup_paths
    applied["application_status"] = _application_status(applied)

    outputs = [
        output
        for output in final_artifacts.get("outputs", [])
        if isinstance(output, dict)
    ]
    _upsert_output(
        outputs,
        {
            "path": "check_results.xlsx",
            "kind": "xlsx",
            "status": "updated_from_review",
            "native_regenerated": True,
            "source_artifact": "check_results.csv",
            "source_row_count": row_count,
            "size_bytes": workbook_path.stat().st_size,
            "required_sheets": ["check_results"],
            "required_sheet_headers": {
                "check_results": [value for value in header if value]
            },
            "required_cells": required_cells,
        },
    )
    for backup_output in backup_outputs:
        _upsert_output(outputs, backup_output)
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
        "updated_effect_count": len(candidate_effects),
        "native_regenerated_paths": native_regenerated_paths,
        "backup_paths": [backup_output["path"] for backup_output in backup_outputs],
        "application_status": applied["application_status"],
        "applied_decisions": applied,
        "final_artifacts": final_artifacts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply Check Entries review edits and regenerate native outputs."
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
