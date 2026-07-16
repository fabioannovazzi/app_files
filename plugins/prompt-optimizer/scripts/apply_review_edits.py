from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_prompt import (  # noqa: E402
    render_prompt_package,
    validate_prompt_text,
    write_json,
)

__all__ = ["apply_review_edits", "main"]

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


def _eligible_optimized_prompt_effect(effect: dict[str, Any]) -> bool:
    """Return whether a prompt edit should refresh dependent package artifacts."""

    if effect.get("action") != "edit":
        return False
    if effect.get("artifact_update") != "target_artifact_updated":
        return False
    if clean_text(effect.get("target_artifact")) != "optimized_prompt.md":
        return False
    return bool(clean_text(effect.get("edit_value")))


def _safe_item_id(value: object) -> str:
    text = clean_text(value) or "item"
    cleaned = "".join(char if char.isalnum() or char in "._-" else "-" for char in text)
    return cleaned.strip("-") or "item"


def _backup_file(output_dir: Path, item_id: str, target_name: str) -> dict[str, Any]:
    source = output_dir / target_name
    if not source.exists():
        return {}
    suffix = source.suffix or ".md"
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


def _extract_markdown_section(markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    start = markdown.find(marker)
    if start == -1:
        return ""
    body_start = start + len(marker)
    next_heading = markdown.find("\n## ", body_start)
    section = (
        markdown[body_start:]
        if next_heading == -1
        else markdown[body_start:next_heading]
    )
    return section.strip()


def _question_text(output_dir: Path, run_intake: dict[str, Any]) -> str:
    package_path = output_dir / "prompt_package.md"
    if package_path.exists():
        section = _extract_markdown_section(
            package_path.read_text(encoding="utf-8"),
            "Source Question",
        )
        if section:
            return section
    assumptions = run_intake.get("assumptions")
    if isinstance(assumptions, dict):
        for key in ("question_text", "source_question", "question_preview"):
            value = clean_text(assumptions.get(key))
            if value:
                return value
    raise ValueError(
        "Cannot refresh Prompt Optimizer package without a Source Question section."
    )


def _language(run_intake: dict[str, Any], audit: dict[str, Any]) -> str:
    return (
        clean_text(audit.get("language"))
        or clean_text(run_intake.get("language"))
        or clean_text((run_intake.get("assumptions") or {}).get("language"))
        or "auto"
    )


def _application_status(applied: dict[str, Any]) -> str:
    if int(applied.get("blocker_count") or 0) > 0:
        return "blocked"
    if int(applied.get("native_regeneration_count") or 0) > 0:
        return "partial_review_applied"
    if int(applied.get("decision_count") or 0) < int(applied.get("item_count") or 0):
        return "partial_review_applied"
    return "final_ready"


def _next_actions(current: list[Any], status: str) -> list[str]:
    next_actions = [clean_text(action) for action in current if clean_text(action)]
    if status == "final_ready":
        next_actions.append(FINAL_HANDOFF_ACTION)
    elif status == "partial_review_applied":
        next_actions.append(COMPLETE_REVIEW_ACTION)
    return list(dict.fromkeys(next_actions))


def _first_prompt_line(prompt_text: str) -> str:
    for line in prompt_text.splitlines():
        value = line.strip()
        if value:
            return value
    return ""


def _package_required_text(audit: dict[str, Any]) -> list[str]:
    fragments = ["# Prompt Optimizer Package", "## What to Use"]
    fragments.extend(str(domain) for domain in audit.get("source_domains") or [])
    return list(
        dict.fromkeys(
            clean_text(fragment) for fragment in fragments if clean_text(fragment)
        )
    )


def apply_review_edits(
    output_dir: Path,
    applied_decisions_path: Path,
    final_artifacts_path: Path,
) -> dict[str, Any]:
    """Refresh prompt validation outputs after an explicit optimized-prompt edit."""

    output_dir = output_dir.resolve()
    applied_decisions_path = applied_decisions_path.resolve()
    final_artifacts_path = final_artifacts_path.resolve()
    run_intake_path = output_dir / "run_intake.json"
    prompt_path = output_dir / "optimized_prompt.md"
    audit_path = output_dir / "prompt_audit.json"
    package_path = output_dir / "prompt_package.md"
    source_domains_path = output_dir / "source_domains.txt"
    source_domains_comma_path = output_dir / "source_domains_comma.txt"

    applied = _read_json(applied_decisions_path)
    final_artifacts = _read_json(final_artifacts_path)
    effects = [
        effect for effect in applied.get("effects", []) if isinstance(effect, dict)
    ]
    candidate_effects = [
        effect for effect in effects if _eligible_optimized_prompt_effect(effect)
    ]
    if not candidate_effects:
        return {
            "ok": True,
            "updated_effect_count": 0,
            "message": "No Prompt Optimizer downstream refresh was required.",
        }

    if not run_intake_path.exists():
        raise FileNotFoundError(run_intake_path)
    if not prompt_path.exists():
        raise FileNotFoundError(prompt_path)
    if not audit_path.exists():
        raise FileNotFoundError(audit_path)

    run_intake = _read_json(run_intake_path)
    previous_audit = _read_json(audit_path)
    question_text = _question_text(output_dir, run_intake)
    prompt_text = prompt_path.read_text(encoding="utf-8").strip()
    language = _language(run_intake, previous_audit)
    audit = validate_prompt_text(question_text, prompt_text, language=language)
    audit["language"] = language
    if previous_audit.get("review_session"):
        audit["review_session"] = previous_audit["review_session"]

    package_text = render_prompt_package(question_text, prompt_text, audit)
    source_domains = [str(domain) for domain in audit.get("source_domains") or []]

    backup_outputs: list[dict[str, Any]] = []
    item_id = clean_text(candidate_effects[0].get("item_id"))
    for target_name in (
        "prompt_audit.json",
        "prompt_package.md",
        "source_domains.txt",
        "source_domains_comma.txt",
    ):
        backup = _backup_file(output_dir, item_id, target_name)
        if backup:
            backup_outputs.append(backup)

    write_json(audit_path, audit)
    package_path.write_text(package_text, encoding="utf-8")
    source_domains_path.write_text("\n".join(source_domains) + "\n", encoding="utf-8")
    source_domains_comma_path.write_text(
        ", ".join(source_domains) + "\n", encoding="utf-8"
    )

    downstream_paths = [
        "prompt_audit.json",
        "prompt_package.md",
        "source_domains.txt",
        "source_domains_comma.txt",
    ]
    for effect in candidate_effects:
        effect["downstream_regeneration_status"] = "regenerated"
        effect["downstream_regenerated_paths"] = downstream_paths

    applied["effects"] = effects
    applied["downstream_regenerated_count"] = len(candidate_effects)
    applied["downstream_regenerated_paths"] = downstream_paths
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
    first_prompt_line = _first_prompt_line(prompt_text)
    _upsert_output(
        outputs,
        {
            "path": "optimized_prompt.md",
            "kind": "md",
            "status": "updated_from_review",
            "required_text": [first_prompt_line] if first_prompt_line else [],
            "qa_checks": ["nonempty_text", "required_text"],
        },
    )
    _upsert_output(
        outputs,
        {
            "path": "prompt_audit.json",
            "kind": "json",
            "status": "updated_from_review",
            "source_artifact": "optimized_prompt.md",
        },
    )
    _upsert_output(
        outputs,
        {
            "path": "prompt_package.md",
            "kind": "md",
            "status": "updated_from_review",
            "source_artifact": "optimized_prompt.md",
            "size_bytes": package_path.stat().st_size,
            "required_text": _package_required_text(audit),
            "qa_checks": ["nonempty_text", "required_text"],
        },
    )
    for target_path in ("source_domains.txt", "source_domains_comma.txt"):
        _upsert_output(
            outputs,
            {
                "path": target_path,
                "kind": "txt",
                "status": "updated_from_review",
                "source_artifact": "optimized_prompt.md",
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
        review_application["downstream_regenerated_count"] = applied[
            "downstream_regenerated_count"
        ]
        review_application["downstream_regenerated_paths"] = downstream_paths
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
        "downstream_regenerated_paths": downstream_paths,
        "backup_paths": [backup_output["path"] for backup_output in backup_outputs],
        "application_status": applied["application_status"],
        "applied_decisions": applied,
        "final_artifacts": final_artifacts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply Prompt Optimizer review edits to downstream artifacts."
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
