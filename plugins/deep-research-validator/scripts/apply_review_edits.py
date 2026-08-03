from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent.parent / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        if str(_vendor_root) not in sys.path:
            sys.path.insert(0, str(_vendor_root))
        break

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from package_validation import (  # noqa: E402
    build_audit,
    render_validation_package,
)
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_workflow_context_for_output,
)

__all__ = ["apply_review_edits", "main"]

FINAL_HANDOFF_ACTION = (
    "Use final_artifacts.json as the reviewed artifact gallery for handoff."
)
COMPLETE_REVIEW_ACTION = "Complete remaining review decisions before final handoff."
REGENERATE_ANSWER_ACTION = (
    "Regenerate the reviewed or corrected answer semantically from the accepted "
    "claim dispositions, then rerun validation packaging."
)
VALIDATED_DOCUMENT_DOCX = "validated_document.docx"


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


def _run_output_file(output_dir: Path, path: Path, label: str) -> Path:
    """Resolve one existing file and keep it inside the selected run output."""

    resolved_output = output_dir.expanduser().resolve()
    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"{label} is unavailable: {exc}") from exc
    if not resolved.is_file() or not resolved.is_relative_to(resolved_output):
        raise ValueError(f"{label} must be a file inside the run output")
    return resolved


def _eligible_claim_fix_effect(effect: dict[str, Any]) -> bool:
    """Return whether a structured claim edit should refresh package Markdown."""

    if effect.get("action") != "edit":
        return False
    if effect.get("artifact_update") != "structured_artifact_updated":
        return False
    if clean_text(effect.get("target_artifact")) != "claims_review.json":
        return False
    if clean_text(effect.get("target_field")) != "proposed_fix":
        return False
    return bool(clean_text(effect.get("edit_value")))


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


def _resolve_input_path(
    output_dir: Path,
    run_intake: dict[str, Any],
    file_name: str,
    *,
    prefer_output_dir: bool = False,
    run_root: Path | None = None,
) -> Path:
    output_candidate = output_dir / file_name
    if prefer_output_dir and output_candidate.exists():
        return output_candidate
    input_paths = run_intake.get("input_paths")
    if isinstance(input_paths, list):
        for raw_path in input_paths:
            if not isinstance(raw_path, str):
                continue
            path = Path(raw_path)
            if path.name != file_name:
                continue
            if run_intake.get("path_reference") == "run_root_relative":
                if run_root is None or path.is_absolute() or ".." in path.parts:
                    raise ValueError("Managed Answer Validator input path is invalid.")
                resolved_root = run_root.expanduser().resolve(strict=True)
                candidate = (resolved_root / path).resolve(strict=True)
                if not candidate.is_relative_to(resolved_root):
                    raise ValueError(
                        "Managed Answer Validator input escapes the current run."
                    )
                candidates = [candidate]
            else:
                candidates = [path] if path.is_absolute() else [output_dir / path]
            candidates.append(output_candidate)
            for candidate in candidates:
                if candidate.exists():
                    return candidate
    return output_candidate


def _application_status(applied: dict[str, Any]) -> str:
    if int(applied.get("blocker_count") or 0) > 0:
        return "blocked"
    if int(applied.get("semantic_regeneration_count") or 0) > 0:
        return "revision_required"
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
    elif status == "revision_required":
        next_actions.append(REGENERATE_ANSWER_ACTION)
    return list(dict.fromkeys(next_actions))


def _required_package_text(candidate_effects: list[dict[str, Any]]) -> list[str]:
    fragments = [
        "# Answer Validation Record",
        "## Assurance Boundary",
        "## Answer Contract",
        "## Answer-Contract Review",
        "## Review Coverage",
        "## Document Inventory",
        "## Claim Assessments",
    ]
    for effect in candidate_effects:
        edit_value = clean_text(effect.get("edit_value"))
        if edit_value:
            fragments.append(edit_value)
    return list(dict.fromkeys(fragments))


def apply_review_edits(
    output_dir: Path,
    applied_decisions_path: Path,
    final_artifacts_path: Path,
    *,
    client_engagement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Refresh deterministic package artifacts after explicit claim JSON edits."""

    output_dir = output_dir.resolve()
    applied_decisions_path = applied_decisions_path.resolve()
    final_artifacts_path = final_artifacts_path.resolve()
    run_intake_path = output_dir / "run_intake.json"
    claims_review_path = output_dir / "claims_review.json"
    validation_audit_path = output_dir / "validation_audit.json"
    validation_package_path = output_dir / "validation_package.md"
    answer_contract_path = output_dir / "answer_contract.json"

    applied = _read_json(applied_decisions_path)
    final_artifacts = _read_json(final_artifacts_path)
    effects = [
        effect for effect in applied.get("effects", []) if isinstance(effect, dict)
    ]
    candidate_effects = [
        effect for effect in effects if _eligible_claim_fix_effect(effect)
    ]
    if not candidate_effects:
        return {
            "ok": True,
            "updated_effect_count": 0,
            "message": "No answer-validation package refresh was required.",
        }

    if not run_intake_path.exists():
        raise FileNotFoundError(run_intake_path)
    if not claims_review_path.exists():
        raise FileNotFoundError(claims_review_path)
    if not answer_contract_path.exists():
        raise FileNotFoundError(answer_contract_path)

    run_intake = _read_json(run_intake_path)
    run_root = (
        Path(str(client_engagement["run_root"]))
        if client_engagement is not None
        else None
    )
    document_inventory_path = _resolve_input_path(
        output_dir,
        run_intake,
        "document_inventory.json",
        run_root=run_root,
    )
    source_inventory_path = _resolve_input_path(
        output_dir,
        run_intake,
        "source_inventory.json",
        run_root=run_root,
    )
    if not document_inventory_path.exists():
        raise FileNotFoundError(document_inventory_path)
    if not source_inventory_path.exists():
        raise FileNotFoundError(source_inventory_path)

    document_inventory = _read_json(document_inventory_path)
    source_inventory = _read_json(source_inventory_path)
    claims_review = _read_json(claims_review_path)
    answer_contract = _read_json(answer_contract_path)
    unresolved_changes = [
        clean_text(value)
        for value in (
            claims_review.get("document_revision", {}).get("unresolved_changes", [])
            if isinstance(claims_review.get("document_revision"), dict)
            else []
        )
        if clean_text(value)
    ]
    for effect in candidate_effects:
        claim_ref = clean_text(effect.get("target_record_id")) or clean_text(
            effect.get("item_id")
        )
        unresolved_changes.append(
            f"Regenerate the answer to apply the reviewed correction for claim {claim_ref}."
        )
    claims_review["document_revision"] = {
        "status": "required",
        "summary": (
            "Reviewer corrections are recorded, but the reviewed or corrected "
            "answer has not yet been semantically regenerated."
        ),
        "unresolved_changes": list(dict.fromkeys(unresolved_changes)),
    }
    claims_review["validated_document"] = ""
    _write_json(claims_review_path, claims_review)
    audit = build_audit(
        document_inventory,
        source_inventory,
        claims_review,
        answer_contract,
        source_base_dir=source_inventory_path.parent,
    )
    package_text = render_validation_package(
        document_inventory,
        source_inventory,
        claims_review,
        audit,
        "",
    )

    backup_outputs: list[dict[str, Any]] = []
    backup = _backup_file(
        output_dir,
        clean_text(candidate_effects[0].get("item_id")),
        "validation_package.md",
    )
    if backup:
        backup_outputs.append(backup)
    for stale_name in ("validated_document.md", VALIDATED_DOCUMENT_DOCX):
        backup = _backup_file(
            output_dir,
            clean_text(candidate_effects[0].get("item_id")),
            stale_name,
        )
        if backup:
            backup_outputs.append(backup)

    _write_json(validation_audit_path, audit)
    validation_package_path.write_text(package_text, encoding="utf-8")
    native_outputs: list[dict[str, Any]] = []
    native_regenerated_paths: list[str] = []
    native_pending = _pending_native_paths(effects)

    downstream_paths = ["validation_audit.json", "validation_package.md"]
    downstream_paths.extend(native_regenerated_paths)
    for effect in candidate_effects:
        effect["downstream_regeneration_status"] = "regenerated"
        effect["downstream_regenerated_paths"] = downstream_paths
        effect["semantic_regeneration_required"] = True
        effect["semantic_regeneration_status"] = "required"

    applied["effects"] = effects
    applied["downstream_regenerated_count"] = len(candidate_effects)
    applied["downstream_regenerated_paths"] = downstream_paths
    applied["native_regeneration_count"] = len(native_pending)
    applied["native_regeneration_paths"] = native_pending
    applied["native_regenerated_count"] = len(native_regenerated_paths)
    applied["native_regenerated_paths"] = native_regenerated_paths
    applied["semantic_regeneration_count"] = len(candidate_effects)
    applied["semantic_regeneration_status"] = "required"
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
    for output in outputs:
        if clean_text(output.get("path")) in {
            "validated_document.md",
            VALIDATED_DOCUMENT_DOCX,
        }:
            output["status"] = "superseded_requires_semantic_regeneration"
    _upsert_output(
        outputs,
        {
            "path": "validation_audit.json",
            "kind": "json",
            "status": "updated_from_review",
            "source_artifact": "claims_review.json",
        },
    )
    _upsert_output(
        outputs,
        {
            "path": "validation_package.md",
            "kind": "md",
            "status": "updated_from_review",
            "source_artifact": "claims_review.json",
            "size_bytes": validation_package_path.stat().st_size,
            "required_text": _required_package_text(candidate_effects),
            "qa_checks": ["nonempty_text", "required_text"],
        },
    )
    for native_output in native_outputs:
        _upsert_output(outputs, native_output)
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
        review_application["native_regeneration_count"] = applied[
            "native_regeneration_count"
        ]
        review_application["native_regeneration_paths"] = native_pending
        review_application["native_regenerated_count"] = applied[
            "native_regenerated_count"
        ]
        review_application["native_regenerated_paths"] = native_regenerated_paths
        review_application["semantic_regeneration_count"] = applied[
            "semantic_regeneration_count"
        ]
        review_application["semantic_regeneration_status"] = "required"
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
        "native_regenerated_paths": native_regenerated_paths,
        "backup_paths": [backup_output["path"] for backup_output in backup_outputs],
        "application_status": applied["application_status"],
        "applied_decisions": applied,
        "final_artifacts": final_artifacts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply answer-validation review edits to downstream artifacts."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--applied-decisions", type=Path)
    parser.add_argument("--final-artifacts", type=Path)
    parser.add_argument(
        "--client-run-preflight-only",
        action="store_true",
        help="Validate the owning running customer-folder run without writing.",
    )
    args = parser.parse_args(argv)
    try:
        client_context = load_client_workflow_context_for_output(
            args.output_dir.expanduser().resolve(),
            expected_workflow_id="deep-research-validator",
        )
    except AssuranceContractError as exc:
        parser.error(str(exc))
    if args.client_run_preflight_only:
        result = {
            "ok": True,
            "schema_version": client_context["schema_version"],
            "workflow_id": client_context["workflow_id"],
            "client_run_id": client_context["run_id"],
        }
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        return 0
    if args.applied_decisions is None or args.final_artifacts is None:
        parser.error(
            "--applied-decisions and --final-artifacts are required unless "
            "--client-run-preflight-only is used"
        )
    try:
        applied_decisions = _run_output_file(
            args.output_dir,
            args.applied_decisions,
            "applied decisions",
        )
        final_artifacts = _run_output_file(
            args.output_dir,
            args.final_artifacts,
            "final artifacts",
        )
    except ValueError as exc:
        parser.error(str(exc))
    result = apply_review_edits(
        args.output_dir,
        applied_decisions,
        final_artifacts,
        client_engagement=client_context,
    )
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
