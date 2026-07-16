from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from docx import Document

__all__ = ["apply_review_edits", "main"]

SUMMARY_DOCX = "concordato_review_summary.docx"
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


def _safe_item_id(value: object) -> str:
    text = clean_text(value) or "item"
    cleaned = "".join(char if char.isalnum() or char in "._-" else "-" for char in text)
    return cleaned.strip("-") or "item"


def _backup_file(output_dir: Path, item_id: str, target_name: str) -> dict[str, Any]:
    source = output_dir / target_name
    if not source.exists():
        return {}
    suffix = source.suffix or ".docx"
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


def _memo_effects(effects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        effect
        for effect in effects
        if effect.get("action") == "edit"
        and clean_text(effect.get("item_id")) == "codex-review-memo"
        and clean_text(effect.get("edit_value"))
    ]


def _summary_docx_requested(output_dir: Path, final_artifacts: dict[str, Any]) -> bool:
    if (output_dir / SUMMARY_DOCX).exists():
        return True
    outputs = final_artifacts.get("outputs")
    if not isinstance(outputs, list):
        return False
    return any(
        isinstance(output, dict) and clean_text(output.get("path")) == SUMMARY_DOCX
        for output in outputs
    )


def _visible_memo_lines(markdown_text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^[-*]\s+", "", line)
        if line:
            lines.append(line)
    return lines


def _required_docx_text(memo_text: str) -> list[str]:
    fragments = ["Memo revisore Codex"]
    fragments.extend(_visible_memo_lines(memo_text))
    return list(dict.fromkeys(fragments))


def _append_memo_to_summary_docx(path: Path, memo_text: str) -> None:
    document = Document(path)
    document.add_heading("Memo revisore Codex", level=1)
    for raw_line in memo_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading_match = re.match(r"^#{1,6}\s+(.*)$", line)
        if heading_match:
            document.add_heading(heading_match.group(1).strip(), level=2)
            continue
        bullet_match = re.match(r"^[-*]\s+(.*)$", line)
        if bullet_match:
            document.add_paragraph(bullet_match.group(1).strip(), style="List Bullet")
            continue
        document.add_paragraph(line)
    document.save(path)


def _write_review_memo(
    output_dir: Path,
    effect: dict[str, Any],
    memo_text: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    target_name = clean_text(effect.get("target_artifact")) or "codex_run_review.md"
    target_path = output_dir / target_name
    backup_output = _backup_file(
        output_dir,
        clean_text(effect.get("item_id")),
        target_name,
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_existed = target_path.exists()
    target_path.write_text(memo_text, encoding="utf-8")
    revision_artifact = clean_text(effect.get("revision_artifact"))
    effect["target_artifact"] = target_name
    effect["artifact_update"] = (
        "target_artifact_updated" if target_existed else "target_artifact_created"
    )
    if revision_artifact:
        effect["promoted_from_revision"] = revision_artifact
    if backup_output:
        effect["original_artifact_backup"] = backup_output["path"]
    return (
        {
            "path": target_name,
            "kind": target_path.suffix.lstrip(".") or "md",
            "status": "updated_from_review",
            "item_id": clean_text(effect.get("item_id")),
            "size_bytes": target_path.stat().st_size,
            "required_text": [memo_text],
            "qa_checks": ["nonempty_text", "required_text"],
        },
        backup_output or None,
    )


def _pending_native_paths(effects: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for effect in effects:
        if not effect.get("requires_native_regeneration"):
            continue
        raw_paths = effect.get("derived_native_regeneration_paths")
        if not isinstance(raw_paths, list):
            raw_paths = [effect.get("target_artifact")]
        for raw_path in raw_paths:
            text = clean_text(raw_path)
            if text:
                paths.append(text)
    return list(dict.fromkeys(paths))


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
        if clean_text(action) != REGENERATE_NATIVE_OUTPUT_ACTION
    ]
    if status == "final_ready":
        next_actions.append(FINAL_HANDOFF_ACTION)
    elif status == "partial_review_applied":
        next_actions.append(COMPLETE_REVIEW_ACTION)
    return list(dict.fromkeys(action for action in next_actions if action))


def apply_review_edits(
    output_dir: Path,
    applied_decisions_path: Path,
    final_artifacts_path: Path,
) -> dict[str, Any]:
    """Refresh Concordato native handoff artifacts after reviewed memo edits."""

    output_dir = output_dir.resolve()
    applied_decisions_path = applied_decisions_path.resolve()
    final_artifacts_path = final_artifacts_path.resolve()
    applied = _read_json(applied_decisions_path)
    final_artifacts = _read_json(final_artifacts_path)
    effects = [
        effect for effect in applied.get("effects", []) if isinstance(effect, dict)
    ]
    candidate_effects = _memo_effects(effects)
    if not candidate_effects:
        return {
            "ok": True,
            "updated_effect_count": 0,
            "message": "No Concordato memo refresh was required.",
            "applied_decisions": applied,
            "final_artifacts": final_artifacts,
        }
    if not _summary_docx_requested(output_dir, final_artifacts):
        return {
            "ok": True,
            "updated_effect_count": 0,
            "message": "No Concordato summary DOCX is available to refresh.",
            "applied_decisions": applied,
            "final_artifacts": final_artifacts,
        }

    docx_path = output_dir / SUMMARY_DOCX
    if not docx_path.exists():
        raise FileNotFoundError(docx_path)

    memo_text = clean_text(candidate_effects[-1].get("edit_value"))
    memo_output, memo_backup_output = _write_review_memo(
        output_dir,
        candidate_effects[-1],
        memo_text,
    )
    backup_output = _backup_file(
        output_dir,
        clean_text(candidate_effects[-1].get("item_id")),
        SUMMARY_DOCX,
    )
    _append_memo_to_summary_docx(docx_path, memo_text)

    native_regenerated_paths = [SUMMARY_DOCX]
    native_pending = [
        path
        for path in _pending_native_paths(effects)
        if path not in set(native_regenerated_paths)
    ]
    for effect in candidate_effects:
        effect["native_regeneration_status"] = "regenerated"
        effect["native_regenerated_paths"] = native_regenerated_paths

    applied["effects"] = effects
    applied["native_regeneration_count"] = len(native_pending)
    applied["native_regeneration_paths"] = native_pending
    applied["native_regenerated_count"] = len(native_regenerated_paths)
    applied["native_regenerated_paths"] = native_regenerated_paths
    target_update_paths = list(applied.get("target_update_paths") or [])
    if memo_output["path"] not in target_update_paths:
        target_update_paths.append(memo_output["path"])
    applied["target_update_paths"] = target_update_paths
    applied["target_update_count"] = len(target_update_paths)
    original_backup_paths = list(applied.get("original_backup_paths") or [])
    if memo_backup_output and memo_backup_output["path"] not in original_backup_paths:
        original_backup_paths.append(memo_backup_output["path"])
    if backup_output and backup_output["path"] not in original_backup_paths:
        original_backup_paths.append(backup_output["path"])
    applied["original_backup_paths"] = original_backup_paths
    applied["application_status"] = _application_status(applied)

    outputs = [
        output
        for output in final_artifacts.get("outputs", [])
        if isinstance(output, dict)
    ]
    _upsert_output(outputs, memo_output)
    if memo_backup_output:
        _upsert_output(outputs, memo_backup_output)
    _upsert_output(
        outputs,
        {
            "path": SUMMARY_DOCX,
            "kind": "docx",
            "status": "updated_from_review",
            "native_regenerated": True,
            "source_artifact": "codex_run_review.md",
            "size_bytes": docx_path.stat().st_size,
            "required_text": _required_docx_text(memo_text),
            "qa_checks": ["nonempty_text", "required_text"],
        },
    )
    if backup_output:
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
        review_application["native_regeneration_paths"] = native_pending
        review_application["native_regenerated_count"] = applied[
            "native_regenerated_count"
        ]
        review_application["native_regenerated_paths"] = native_regenerated_paths
        review_application["target_update_count"] = applied["target_update_count"]
        review_application["target_update_paths"] = target_update_paths
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
        "backup_paths": [backup_output["path"]] if backup_output else [],
        "application_status": applied["application_status"],
        "applied_decisions": applied,
        "final_artifacts": final_artifacts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply Concordato review edits to downstream artifacts."
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
