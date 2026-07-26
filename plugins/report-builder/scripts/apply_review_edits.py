from __future__ import annotations

import sys as _bootstrap_sys  # isort: skip

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__report_builder_no_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/report-builder"
)

import os as _bootstrap_os  # isort: skip

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_ENTRY = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _BOOTSTRAP_ENTRY.st_mode & 0o170000 != 0o100000 or _BOOTSTRAP_ENTRY.st_nlink != 1:
    raise RuntimeError("Report Builder implementation bootstrap is not a real file.")
with open(_BOOTSTRAP_PATH, "rb") as _bootstrap_handle:
    _BOOTSTRAP_BEFORE = _bootstrap_os.fstat(_bootstrap_handle.fileno())
    _BOOTSTRAP_BYTES = _bootstrap_handle.read()
    _BOOTSTRAP_AFTER = _bootstrap_os.fstat(_bootstrap_handle.fileno())
_BOOTSTRAP_IDENTITY = (
    _BOOTSTRAP_ENTRY.st_dev,
    _BOOTSTRAP_ENTRY.st_ino,
    _BOOTSTRAP_ENTRY.st_size,
    _BOOTSTRAP_ENTRY.st_mtime_ns,
)
if (
    _BOOTSTRAP_IDENTITY
    != (
        _BOOTSTRAP_BEFORE.st_dev,
        _BOOTSTRAP_BEFORE.st_ino,
        _BOOTSTRAP_BEFORE.st_size,
        _BOOTSTRAP_BEFORE.st_mtime_ns,
    )
    or _BOOTSTRAP_IDENTITY
    != (
        _BOOTSTRAP_AFTER.st_dev,
        _BOOTSTRAP_AFTER.st_ino,
        _BOOTSTRAP_AFTER.st_size,
        _BOOTSTRAP_AFTER.st_mtime_ns,
    )
    or len(_BOOTSTRAP_BYTES) != _BOOTSTRAP_AFTER.st_size
):
    raise RuntimeError("Report Builder implementation bootstrap changed while read.")
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_report_builder_implementation_bootstrap",
}
# The exact stable single-link bootstrap source is verified above.
exec(  # nosec B102
    compile(_BOOTSTRAP_BYTES, _BOOTSTRAP_PATH, "exec"), _BOOTSTRAP_NAMESPACE
)
_BOOTSTRAP_NAMESPACE["activate_implementation_boundary"]()
_SCRIPTS_DIR = _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__))
if _SCRIPTS_DIR not in _bootstrap_sys.path:
    _bootstrap_sys.path.insert(0, _SCRIPTS_DIR)

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from report_builder_core import (  # noqa: E402
    _public_table_inspection,
    analysis_for_section,
    clean_text,
    inspect_table,
    load_indexed_tables,
    render_markdown,
    selected_sections,
    validate_narrative_numeric_boundary,
    write_json,
    write_numeric_evidence_ledger,
    write_report_docx,
    write_tables_workbook,
)
from report_builder_integrity import (  # noqa: E402
    canonical_json_sha256,
    validate_review_integrity,
)
from report_gates import build_report_assurance_state  # noqa: E402
from review_session import (  # noqa: E402
    build_output_records,
    refresh_review_payload,
)

__all__ = ["apply_review_edits", "main"]

REGENERATE_NATIVE_OUTPUT_ACTION = (
    "Regenerate native DOCX/XLSX/PDF outputs before final handoff."
)
FINAL_HANDOFF_ACTION = (
    "Use final_artifacts.json as the reviewed artifact gallery for handoff."
)
COMPLETE_REVIEW_ACTION = "Complete remaining review decisions before final handoff."


def _audit_notes(language: str, *, numeric_measure_pending: bool) -> list[str]:
    notes = (
        [
            "El texto narrativo lo proporciona Codex en la receta, no los scripts auxiliares.",
            "Revise las secciones sin asignar y los comentarios pendientes de Codex antes del uso final.",
        ]
        if language == "es"
        else [
            "Narrative text is supplied by Codex in the recipe, not by helper scripts.",
            "Review unassigned sections and Codex-pending comments before final use.",
        ]
    )
    if numeric_measure_pending:
        notes.append(
            (
                "Las columnas con apariencia numérica permanecen excluidas de los totales hasta que se revise su función como medidas."
                if language == "es"
                else "Numeric-looking columns remain excluded from totals until their measure role is reviewed."
            )
        )
    return notes


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _read_expected_json(
    path: Path,
    *,
    expected_sha256: str | None,
) -> dict[str, Any]:
    """Read one stable regular-file snapshot and enforce the caller's digest."""

    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular JSON file: {path}")
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError(f"Review application input changed while read: {path.name}")
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(f"Review application input digest is stale: {path.name}")
    payload = json.loads(raw)
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


def _application_status(
    applied: dict[str, Any],
    analysis: dict[str, Any],
    *,
    regenerated_review_pending: bool,
) -> str:
    if int(applied.get("blocker_count") or 0) > 0:
        return "blocked"
    if int(applied.get("native_regeneration_count") or 0) > 0:
        return "partial_review_applied"
    if int(applied.get("decision_count") or 0) < int(applied.get("item_count") or 0):
        return "partial_review_applied"
    if any(
        isinstance(effect, dict)
        and effect.get("action") == "edit"
        and (
            effect.get("artifact_update") != "native_artifact_regenerated"
            or effect.get("terminal_application") is not True
            or not isinstance(effect.get("application_receipt"), dict)
        )
        for effect in applied.get("effects", [])
    ):
        return "partial_review_applied"
    if any(
        isinstance(section, dict)
        and section.get("numeric_measure_status") == "needs_review"
        for section in analysis.get("sections", [])
    ):
        return "partial_review_applied"
    if regenerated_review_pending:
        return "partial_review_applied"
    return "final_ready"


def _next_actions(current: list[Any], status: str) -> list[str]:
    next_actions = [
        clean_text(action)
        for action in current
        if clean_text(action)
        and clean_text(action)
        not in {
            REGENERATE_NATIVE_OUTPUT_ACTION,
            FINAL_HANDOFF_ACTION,
            COMPLETE_REVIEW_ACTION,
        }
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
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    raw_tables = load_indexed_tables(output_dir, persist_source_index=False)
    table_by_id = {clean_text(table.get("table_id")): table for table in raw_tables}
    sections_analysis = [
        analysis_for_section(
            section_key,
            section_recipe,
            table_by_id,
            report_period=clean_text(recipe.get("period")),
        )
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
        "numeric_measure_pending_sections": [
            section["section"]
            for section in sections_analysis
            if section.get("numeric_measure_status") == "needs_review"
        ],
    }
    updated_audit = dict(audit)
    updated_audit.update(
        {
            "table_count": len(raw_tables),
            "section_count": len(sections_analysis),
            "assigned_section_count": len(assigned_sections),
            "missing_section_count": len(missing_sections),
            "missing_sections": missing_sections,
            "numeric_measure_pending_section_count": len(
                analysis["numeric_measure_pending_sections"]
            ),
            "numeric_measure_pending_sections": analysis[
                "numeric_measure_pending_sections"
            ],
            "codex_narrative_sections": sum(
                1
                for section in sections_analysis
                if clean_text(section.get("codex_comment"))
            ),
            "notes": _audit_notes(
                str(analysis["language"]),
                numeric_measure_pending=bool(
                    analysis["numeric_measure_pending_sections"]
                ),
            ),
        }
    )
    return analysis, updated_audit, raw_tables


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
    *,
    expected_applied_sha256: str | None = None,
    expected_final_artifacts_sha256: str | None = None,
) -> dict[str, Any]:
    """Apply explicit Report Builder section edits and regenerate native outputs."""

    output_dir = output_dir.resolve()
    applied_decisions_path = applied_decisions_path.resolve()
    final_artifacts_path = final_artifacts_path.resolve()
    validate_review_integrity(output_dir, source_and_review_only=True)
    recipe_path = output_dir / "used_recipe.json"
    analysis_path = output_dir / "report_analysis.json"
    audit_path = output_dir / "report_audit.json"
    markdown_path = output_dir / "report_draft.md"
    docx_path = output_dir / "report.docx"

    applied = _read_expected_json(
        applied_decisions_path,
        expected_sha256=expected_applied_sha256,
    )
    final_artifacts = _read_expected_json(
        final_artifacts_path,
        expected_sha256=expected_final_artifacts_sha256,
    )
    effects = [
        effect for effect in applied.get("effects", []) if isinstance(effect, dict)
    ]
    edit_effects = [effect for effect in effects if effect.get("action") == "edit"]
    unsupported_edits = [
        clean_text(effect.get("item_id"))
        for effect in edit_effects
        if not _eligible_report_builder_effect(effect)
    ]
    if unsupported_edits:
        raise ValueError(
            "Report Builder edit has no exact native application adapter: "
            f"{unsupported_edits}"
        )
    candidate_effects = [
        effect for effect in effects if _eligible_report_builder_effect(effect)
    ]
    recipe = _read_json(recipe_path)
    analysis = _read_json(analysis_path)
    audit = _read_json(audit_path)
    source_mapping_changed = False
    current_tables: list[dict[str, Any]] = []

    updated_effects: list[dict[str, Any]] = []
    backup_outputs: list[dict[str, Any]] = []
    for effect in candidate_effects:
        section_key = _parse_section_comment_path(
            effect.get("target_path")
        ) or _parse_section_mapping_path(effect.get("target_path"))
        edit_value = clean_text(effect.get("edit_value"))
        if not section_key or not edit_value:
            continue
        sections = recipe.setdefault("sections", {})
        if not isinstance(sections, dict) or section_key not in sections:
            raise ValueError(
                f"Report Builder edit targets an unknown section: {section_key}"
            )
        section_recipe = sections.setdefault(section_key, {})
        if not isinstance(section_recipe, dict):
            raise ValueError(f"Malformed Report Builder section: {section_key}")
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

    if source_mapping_changed:
        analysis, audit, current_tables = _recompute_report_analysis(
            output_dir, recipe, audit
        )
        _validate_source_mapping_effects(updated_effects, analysis)
    else:
        audit["codex_narrative_sections"] = sum(
            1
            for section in analysis.get("sections", [])
            if isinstance(section, dict) and clean_text(section.get("codex_comment"))
        )
    validate_narrative_numeric_boundary(recipe)
    if updated_effects:
        backup = _backup_native(
            output_dir,
            clean_text(updated_effects[0].get("item_id")),
            "report.docx",
        )
        if backup:
            backup_outputs.append(backup)
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
    if source_mapping_changed:
        write_json(
            output_dir / "report_tables.json",
            {
                "tables": [
                    _public_table_inspection(inspect_table(table))
                    for table in current_tables
                ]
            },
        )
        write_tables_workbook(output_dir / "report_tables.xlsx", analysis)
    markdown_path.write_text(render_markdown(recipe, analysis), encoding="utf-8")
    write_report_docx(recipe, analysis, audit, docx_path)
    numeric_evidence = write_numeric_evidence_ledger(output_dir, analysis)
    if numeric_evidence is not None:
        for effect in updated_effects:
            paths = list(effect.get("native_regenerated_paths") or [])
            for generated_path in (
                "numeric_evidence_ledger.json",
                "source_receipts.json",
            ):
                if generated_path not in paths:
                    paths.append(generated_path)
            effect["native_regenerated_paths"] = paths
    sections_by_key = {
        clean_text(section.get("section")): section
        for section in analysis.get("sections", [])
        if isinstance(section, dict)
    }
    for effect in updated_effects:
        target_path = clean_text(effect.get("target_path"))
        section_key = _parse_section_comment_path(
            target_path
        ) or _parse_section_mapping_path(target_path)
        section_recipe = recipe["sections"][section_key]
        section_analysis = sections_by_key.get(section_key)
        expected_value = clean_text(effect.get("edit_value"))
        field_name = (
            "assigned_table"
            if _parse_section_mapping_path(target_path)
            else "codex_comment"
        )
        if (
            clean_text(section_recipe.get(field_name)) != expected_value
            or not isinstance(section_analysis, dict)
            or clean_text(section_analysis.get(field_name)) != expected_value
        ):
            raise ValueError(
                f"Report Builder edit did not survive native regeneration: {target_path}"
            )
        effect["terminal_application"] = True
        regenerated_receipts = []
        for relative_path in effect.get("native_regenerated_paths", []):
            candidate_path = output_dir / clean_text(relative_path)
            candidate = candidate_path.resolve()
            if (
                output_dir not in candidate.parents
                or candidate_path.is_symlink()
                or not candidate.is_file()
            ):
                raise ValueError(
                    "Report Builder regenerated output receipt is missing: "
                    f"{relative_path}"
                )
            regenerated_receipts.append(
                {
                    "path": candidate.relative_to(output_dir).as_posix(),
                    "byte_count": candidate.stat().st_size,
                    "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
                }
            )
        effect["application_receipt"] = {
            "target_path": target_path,
            "applied_value_sha256": hashlib.sha256(
                expected_value.encode("utf-8")
            ).hexdigest(),
            "used_recipe_sha256": hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
            "report_analysis_sha256": hashlib.sha256(
                analysis_path.read_bytes()
            ).hexdigest(),
            "report_draft_sha256": hashlib.sha256(
                markdown_path.read_bytes()
            ).hexdigest(),
            "report_docx_sha256": hashlib.sha256(docx_path.read_bytes()).hexdigest(),
            "regenerated_outputs": regenerated_receipts,
        }
    if source_mapping_changed:
        review_paths = {
            "report_tables": output_dir / "report_tables.json",
            "report_tables_xlsx": output_dir / "report_tables.xlsx",
            "report_analysis": output_dir / "report_analysis.json",
            "report_audit": output_dir / "report_audit.json",
            "used_recipe": output_dir / "used_recipe.json",
            "report_draft": output_dir / "report_draft.md",
            "report_docx": output_dir / "report.docx",
            **(
                {
                    "numeric_evidence": output_dir / "numeric_evidence_ledger.json",
                    "source_receipts": output_dir / "source_receipts.json",
                }
                if numeric_evidence is not None
                else {}
            ),
        }
        refresh_review_payload(
            output_dir,
            analysis=analysis,
            audit=audit,
            recipe=recipe,
            paths=review_paths,
            tables=[
                _public_table_inspection(inspect_table(table))
                for table in current_tables
            ],
        )
    current_review_payload = _read_json(output_dir / "review_payload.json")
    applied["review_payload_sha256"] = canonical_json_sha256(current_review_payload)
    applied.setdefault(
        "decision_review_payload_sha256",
        applied["review_payload_sha256"],
    )

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
    numeric_pending_sections = [
        clean_text(section.get("section"))
        for section in analysis.get("sections", [])
        if isinstance(section, dict)
        and section.get("numeric_measure_status") == "needs_review"
    ]
    applied["numeric_measure_pending_section_count"] = len(numeric_pending_sections)
    applied["numeric_measure_pending_review_count"] = len(numeric_pending_sections)
    applied["numeric_measure_pending_sections"] = numeric_pending_sections
    applied["source_mapping_review_required"] = source_mapping_changed
    applied["application_status"] = _application_status(
        applied,
        analysis,
        regenerated_review_pending=source_mapping_changed,
    )

    outputs = [
        dict(output)
        for output in build_output_records(output_dir, audit, analysis)
        if isinstance(output, dict)
    ]
    for output in outputs:
        if clean_text(output.get("path")) in native_regenerated_paths:
            output["status"] = "updated_from_review"
            output["native_regenerated"] = True
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
        review_application["numeric_measure_pending_section_count"] = len(
            numeric_pending_sections
        )
        review_application["numeric_measure_pending_review_count"] = len(
            numeric_pending_sections
        )
        review_application["numeric_measure_pending_sections"] = (
            numeric_pending_sections
        )
        review_application["source_mapping_review_required"] = source_mapping_changed
    existing_blockers = [
        blocker
        for blocker in final_artifacts.get("blockers", [])
        if isinstance(blocker, dict)
        and blocker.get("kind")
        not in {"numeric_measure_review", "source_mapping_review"}
    ]
    existing_blockers.extend(
        {
            "kind": "numeric_measure_review",
            "section": section,
            "status": "needs_review",
        }
        for section in numeric_pending_sections
    )
    if source_mapping_changed:
        existing_blockers.append(
            {
                "kind": "source_mapping_review",
                "status": "needs_review",
                "review_payload": "review_payload.json",
            }
        )
    final_artifacts["blockers"] = existing_blockers
    assurance_tables = current_tables or load_indexed_tables(
        output_dir,
        persist_source_index=False,
    )
    assurance = build_report_assurance_state(
        analysis,
        assurance_tables,
        applied_decisions=applied,
    )
    final_artifacts["assurance"] = assurance
    final_artifacts["report_ready"] = assurance["report_ready"]
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
    parser.add_argument("--expected-applied-sha256", required=True)
    parser.add_argument("--expected-final-artifacts-sha256", required=True)
    args = parser.parse_args(argv)
    result = apply_review_edits(
        args.output_dir,
        args.applied_decisions,
        args.final_artifacts,
        expected_applied_sha256=args.expected_applied_sha256,
        expected_final_artifacts_sha256=args.expected_final_artifacts_sha256,
    )
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
