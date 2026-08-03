"""Independent deterministic replay of Report Builder prepared/output state.

The replay reconstructs source tables, section analysis, table JSON/XLSX,
Markdown, DOCX, and any numeric evidence ledger from the current receipted
sources and reviewed recipe.  It verifies mechanical equality only; narrative
quality and professional conclusions remain reviewer judgments.
"""

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
import importlib
import json
import shutil
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from .report_gates import build_report_assurance_state
    from .review_successor import validate_review_successor
except ImportError:  # pragma: no cover - supports direct script imports
    from report_gates import build_report_assurance_state
    from review_successor import validate_review_successor

__all__ = ["main", "validate_prepared_report"]

SCHEMA_VERSION = "report_builder.prepared_validation.v1"


def _core() -> Any:
    return importlib.import_module("report_builder_core")


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return payload


def _receipt(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": path.name,
        "byte_count": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _expected_analysis(
    core: Any,
    recipe: dict[str, Any],
    raw_tables: list[dict[str, Any]],
) -> dict[str, Any]:
    table_by_id = {
        core.clean_text(table.get("table_id")): table for table in raw_tables
    }
    sections = [
        core.analysis_for_section(
            section_key,
            section_recipe,
            table_by_id,
            report_period=core.clean_text(recipe.get("period")),
        )
        for section_key, section_recipe in core.selected_sections(recipe).items()
    ]
    assigned = [section for section in sections if section["status"] == "assigned"]
    missing = [
        section["section"] for section in sections if section["status"] != "assigned"
    ]
    numeric_pending = [
        section["section"]
        for section in sections
        if section.get("numeric_measure_status") == "needs_review"
    ]
    return {
        "version": 1,
        "language": recipe.get("language", "en"),
        "document_language": recipe.get("document_language", "auto"),
        "report_type": core.normalize_report_type(recipe.get("report_type")),
        "entity": core.clean_text(recipe.get("entity")),
        "period": core.clean_text(recipe.get("period")),
        "sections": sections,
        "assigned_section_count": len(assigned),
        "missing_sections": missing,
        "numeric_measure_pending_sections": numeric_pending,
    }


def _validate_audit_projection(
    core: Any,
    output_dir: Path,
    audit: Mapping[str, Any],
    analysis: Mapping[str, Any],
    raw_tables: list[dict[str, Any]],
    run_intake: Mapping[str, Any],
    *,
    validate_delivery_state: bool,
) -> None:
    sections = analysis["sections"]
    assigned = [section for section in sections if section["status"] == "assigned"]
    missing = [
        section["section"] for section in sections if section["status"] != "assigned"
    ]
    numeric_pending = [
        section["section"]
        for section in sections
        if section.get("numeric_measure_status") == "needs_review"
    ]
    language = str(analysis.get("language") or "en")
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
    if numeric_pending:
        notes.append(
            (
                "Las columnas con apariencia numérica permanecen excluidas de los totales hasta que se revise su función como medidas."
                if language == "es"
                else "Numeric-looking columns remain excluded from totals until their measure role is reviewed."
            )
        )
    input_paths = run_intake.get("input_paths")
    if not isinstance(input_paths, list) or len(input_paths) != 1:
        raise ValueError("Report Builder audit input identity is stale.")
    review_payload = _read_object(output_dir / "review_payload.json")
    applied_path = output_dir / "applied_decisions.json"
    applied = _read_object(applied_path) if applied_path.is_file() else None
    review_session_item_count = review_payload.get("item_count")
    if applied is not None:
        history_paths = applied.get("review_history_paths", [])
        if not isinstance(history_paths, list):
            raise ValueError("Report Builder audit review history is malformed.")
        if history_paths:
            history_path = Path(str(history_paths[0]))
            if (
                history_path.is_absolute()
                or ".." in history_path.parts
                or "\\" in str(history_paths[0])
            ):
                raise ValueError("Report Builder audit review history is malformed.")
            history = _read_object(output_dir / history_path)
            predecessor_review = history.get("review_payload")
            if not isinstance(predecessor_review, Mapping):
                raise ValueError("Report Builder audit review history is malformed.")
            review_session_item_count = predecessor_review.get("item_count")
        else:
            review_session_item_count = applied.get("item_count")
    expected = {
        "version": 1,
        "status": "draft",
        "input_path": input_paths[0],
        "table_count": len(raw_tables),
        "section_count": len(sections),
        "assigned_section_count": len(assigned),
        "missing_section_count": len(missing),
        "missing_sections": missing,
        "numeric_measure_pending_section_count": len(numeric_pending),
        "numeric_measure_pending_sections": numeric_pending,
        "codex_narrative_sections": sum(
            1 for section in sections if core.clean_text(section.get("codex_comment"))
        ),
        "model_api_calls": 0,
        "notes": notes,
        "review_session": {
            "run_id": run_intake.get("run_id"),
            "run_intake": "run_intake.json",
            "review_payload": "review_payload.json",
            "ui_decisions": "ui_decisions.json",
            "final_artifacts": "final_artifacts.json",
            "review_item_count": review_session_item_count,
        },
    }
    if validate_delivery_state and applied is not None:
        effects = applied.get("effects")
        if not isinstance(effects, list):
            raise ValueError("Report Builder audit review effects are malformed.")
        source_mapping_changed = False
        regenerated_paths: set[str] = set()
        updated_effect_count = 0
        for effect in effects:
            if not isinstance(effect, Mapping) or effect.get("action") != "edit":
                continue
            target_path = str(effect.get("target_path") or "")
            if target_path.endswith(".assigned_table"):
                source_mapping_changed = True
            elif not target_path.endswith(".codex_comment"):
                raise ValueError("Report Builder audit review target is malformed.")
            updated_effect_count += 1
            regenerated_paths.update(
                (
                    "used_recipe.json",
                    "report_analysis.json",
                    "report_audit.json",
                    "report_tables.json",
                    "report_tables.xlsx",
                    "report_draft.md",
                    "report.docx",
                )
                if source_mapping_changed
                else (
                    "used_recipe.json",
                    "report_analysis.json",
                    "report_draft.md",
                    "report.docx",
                )
            )
        expected["review_native_regeneration"] = {
            "status": "regenerated",
            "updated_effect_count": updated_effect_count,
            "outputs": sorted(regenerated_paths),
        }
    elif not validate_delivery_state and "review_native_regeneration" in audit:
        regeneration = audit["review_native_regeneration"]
        if (
            not isinstance(regeneration, Mapping)
            or set(regeneration) != {"status", "updated_effect_count", "outputs"}
            or regeneration.get("status") != "regenerated"
            or not isinstance(regeneration.get("updated_effect_count"), int)
            or isinstance(regeneration.get("updated_effect_count"), bool)
            or regeneration["updated_effect_count"] < 0
            or not isinstance(regeneration.get("outputs"), list)
            or not all(
                isinstance(path, str) for path in regeneration.get("outputs", [])
            )
            or len(regeneration["outputs"]) != len(set(regeneration["outputs"]))
            or not set(regeneration["outputs"])
            <= {
                "used_recipe.json",
                "report_analysis.json",
                "report_audit.json",
                "report_tables.json",
                "report_tables.xlsx",
                "report_draft.md",
                "report.docx",
            }
        ):
            raise ValueError("Report Builder audit review regeneration is malformed.")
        expected["review_native_regeneration"] = dict(regeneration)
    if dict(audit) != expected:
        raise ValueError("Report Builder audit projection is not exactly rederived.")


def _compare_bytes(actual: Path, expected: Path, *, label: str) -> None:
    if actual.read_bytes() != expected.read_bytes():
        raise ValueError(f"Report Builder {label} is not deterministically rederived.")


def _validate_numeric_outputs(
    core: Any,
    output_dir: Path,
    analysis: dict[str, Any],
    replay_dir: Path,
) -> str:
    numeric_path = output_dir / "numeric_evidence_ledger.json"
    receipts_path = output_dir / "source_receipts.json"
    present = (numeric_path.is_file(), receipts_path.is_file())
    if present[0] != present[1]:
        raise ValueError("Report Builder numeric evidence pair is incomplete.")
    numeric_replay = replay_dir / "numeric"
    numeric_replay.mkdir()
    for name in (
        "source_index.json",
        "report_analysis.json",
        "report_tables.xlsx",
        "report_draft.md",
        "report.docx",
    ):
        shutil.copy2(output_dir / name, numeric_replay / name)
    replayed = core.write_numeric_evidence_ledger(
        numeric_replay,
        analysis,
        source_context_dir=output_dir,
    )
    if replayed is None:
        if any(present):
            raise ValueError("Report Builder numeric evidence is unexpectedly present.")
        return "not_applicable"
    if not all(present):
        raise ValueError("Report Builder numeric evidence is missing.")
    _compare_bytes(
        numeric_path,
        numeric_replay / numeric_path.name,
        label="numeric evidence ledger",
    )
    _compare_bytes(
        receipts_path,
        numeric_replay / receipts_path.name,
        label="numeric source receipts",
    )
    return "passed"


def validate_prepared_report(
    output_dir: Path,
    *,
    validate_delivery_state: bool = True,
) -> dict[str, Any]:
    """Re-derive every mechanically controlled prepared/report artifact."""

    root = Path(output_dir).resolve()
    core = _core()
    recipe = _read_object(root / "used_recipe.json")
    analysis = _read_object(root / "report_analysis.json")
    audit = _read_object(root / "report_audit.json")
    run_intake = _read_object(root / "run_intake.json")
    core.validate_narrative_numeric_boundary(recipe)
    raw_tables = core.load_indexed_tables(root, persist_source_index=False)
    expected_tables = {
        "tables": [
            core._public_table_inspection(core.inspect_table(table))
            for table in raw_tables
        ]
    }
    if _read_object(root / "report_tables.json") != expected_tables:
        raise ValueError("Report Builder prepared tables are not source-rederived.")
    expected_analysis = _expected_analysis(core, recipe, raw_tables)
    if analysis != expected_analysis:
        raise ValueError("Report Builder analysis is not source-rederived.")
    _validate_audit_projection(
        core,
        root,
        audit,
        analysis,
        raw_tables,
        run_intake,
        validate_delivery_state=validate_delivery_state,
    )
    successor_validation = (
        validate_review_successor(
            root,
            analysis=analysis,
        )
        if validate_delivery_state
        else None
    )
    if validate_delivery_state:
        final_artifacts = _read_object(root / "final_artifacts.json")
        applied_path = root / "applied_decisions.json"
        applied = _read_object(applied_path) if applied_path.is_file() else None
        assurance = build_report_assurance_state(
            analysis,
            raw_tables,
            applied_decisions=applied,
        )
        if (
            final_artifacts.get("assurance") != assurance
            or final_artifacts.get("report_ready") is not assurance["report_ready"]
        ):
            raise ValueError("Report Builder assurance gates are not rederived.")

    with tempfile.TemporaryDirectory(prefix="report-builder-replay-") as temporary:
        replay_dir = Path(temporary)
        expected_xlsx = replay_dir / "report_tables.xlsx"
        core.write_tables_workbook(expected_xlsx, expected_analysis)
        _compare_bytes(
            root / "report_tables.xlsx",
            expected_xlsx,
            label="table workbook",
        )
        expected_markdown = core.render_markdown(recipe, expected_analysis)
        if (root / "report_draft.md").read_text(encoding="utf-8") != expected_markdown:
            raise ValueError(
                "Report Builder Markdown is not deterministically rederived."
            )
        render_audit = dict(audit)
        if "review_native_regeneration" not in render_audit:
            render_audit.pop("review_session", None)
        expected_docx = replay_dir / "report.docx"
        core.write_report_docx(
            recipe,
            expected_analysis,
            render_audit,
            expected_docx,
        )
        _compare_bytes(root / "report.docx", expected_docx, label="DOCX report")
        numeric_status = _validate_numeric_outputs(
            core,
            root,
            expected_analysis,
            replay_dir,
        )

    controlled_paths = [
        "report_tables.json",
        "report_tables.xlsx",
        "report_analysis.json",
        "report_draft.md",
        "report.docx",
        *(
            ["numeric_evidence_ledger.json", "source_receipts.json"]
            if numeric_status == "passed"
            else []
        ),
    ]
    result = {
        "schema_version": SCHEMA_VERSION,
        "source_table_count": len(raw_tables),
        "section_count": len(expected_analysis["sections"]),
        "numeric_evidence_status": numeric_status,
        "rederived_artifacts": [
            _receipt(root / relative_path) for relative_path in controlled_paths
        ],
    }
    if successor_validation is not None:
        result["review_successor"] = successor_validation
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-derive Report Builder prepared and rendered artifacts."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    result = validate_prepared_report(args.output_dir)
    sys.stdout.write(json.dumps({"ok": True, "validation": result}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
