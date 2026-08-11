#!/usr/bin/env python3
"""Prepare one immutable professional-communication run from selected inputs."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from workflow_core import (
    PLUGIN_ROOT,
    PROMPT_TEMPLATES,
    atomic_write_json,
    canonical_digest,
    copy_input_snapshot,
    file_digest,
    load_json,
    load_workspace,
    prompt_template_digest,
    run_dir_from_workspace,
    utc_now,
    validate_schema,
    workflow_lock,
)

__all__ = ["prepare_run", "main"]

LOGGER = logging.getLogger(__name__)


def _approved_route(route: dict[str, Any], label: str) -> None:
    if route["selected"] and not (
        route.get("approved_by") and route.get("approved_at")
    ):
        raise ValueError(f"Selected external route requires approval metadata: {label}")
    if route["selected"] and not str(route.get("destination") or "").strip():
        raise ValueError(
            f"Selected external route requires an exact destination: {label}"
        )


def _snapshot_rows(
    rows: list[dict[str, Any]],
    *,
    kind: str,
    run_dir: Path,
    final_run_dir: Path,
) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    ids: set[str] = set()
    for row in rows:
        identity = row["id"]
        if identity in ids:
            raise ValueError(f"Duplicate {kind} input id: {identity}")
        ids.add(identity)
        snapshot = copy_input_snapshot(
            Path(row["path"]),
            destination_dir=run_dir / "inputs" / kind,
            identity=identity,
        )
        relative = Path(snapshot["snapshot_path"]).relative_to(run_dir)
        snapshot["snapshot_path"] = str((final_run_dir / relative).resolve())
        snapshots.append(
            {key: value for key, value in {**row, **snapshot}.items() if key != "path"}
        )
    return snapshots


def _retarget_snapshot(
    snapshot: dict[str, Any], *, staging_dir: Path, final_run_dir: Path
) -> dict[str, Any]:
    """Replace a staging-only snapshot path with its committed run path."""

    relative = Path(snapshot["snapshot_path"]).relative_to(staging_dir)
    return {**snapshot, "snapshot_path": str((final_run_dir / relative).resolve())}


def prepare_run(workspace: Path, intake_path: Path) -> Path:
    """Create one path-bound run and its immutable source register."""

    workspace_payload = load_workspace(workspace)
    intake = load_json(intake_path)
    validate_schema(intake, "communication_intake.schema.json")
    for label, route in intake["external_routes"].items():
        _approved_route(route, label)
    studio_format_brief = str(intake.get("studio_format_brief") or "").strip()

    workspace_root = workspace.expanduser().resolve()
    run_dir = run_dir_from_workspace(workspace, intake["run_id"])
    runs_root = workspace_root / "runs"
    with workflow_lock(workspace_root):
        if run_dir.exists():
            raise ValueError(f"Run already exists: {run_dir}")
        staging_prefix = f".{intake['run_id']}.preparing-"
        for stale in runs_root.iterdir():
            if not stale.name.startswith(staging_prefix):
                continue
            if stale.is_symlink() or not stale.is_dir():
                raise ValueError(f"Unsafe stale preparation path: {stale}")
            shutil.rmtree(stale)
        staging_dir = Path(
            tempfile.mkdtemp(prefix=f".{intake['run_id']}.preparing-", dir=runs_root)
        )
        os.chmod(staging_dir, 0o700)
        try:
            sources = _snapshot_rows(
                intake["source_inputs"],
                kind="sources",
                run_dir=staging_dir,
                final_run_dir=run_dir,
            )
            history = _snapshot_rows(
                intake["history_inputs"],
                kind="history",
                run_dir=staging_dir,
                final_run_dir=run_dir,
            )

            requested_brand = dict(intake["brand_profile"])
            requested_logo_path = requested_brand.pop("logo_path", None)
            studio_profile_path = workspace_root / "studio_profile.json"
            studio_profile = None
            studio_profile_snapshot = None
            stored_logo_path = None
            stored_logo_sha256 = None
            if studio_profile_path.is_file():
                stored_payload = load_json(studio_profile_path)
                if (
                    stored_payload.get("workspace_id")
                    != workspace_payload["workspace_id"]
                ):
                    raise ValueError(
                        "Stored studio profile belongs to another workspace identity"
                    )
                if stored_payload.get("studio_name") != requested_brand["studio_name"]:
                    raise ValueError("Stored studio profile belongs to another studio")
                stored_brand = stored_payload.get("brand_profile")
                if not isinstance(stored_brand, dict):
                    raise ValueError(
                        "Stored studio profile has no authoritative brand profile"
                    )
                if requested_brand != stored_brand and not (
                    history or studio_format_brief
                ):
                    raise ValueError(
                        "Brand settings differ from the approved Studio profile; selected history or an explicit Studio-format brief is required"
                    )
                brand_profile = (
                    requested_brand if history or studio_format_brief else stored_brand
                )
                profile_copy = copy_input_snapshot(
                    studio_profile_path,
                    destination_dir=staging_dir / "inputs" / "profile",
                    identity="studio-profile",
                )
                studio_profile_snapshot = _retarget_snapshot(
                    profile_copy, staging_dir=staging_dir, final_run_dir=run_dir
                )
                studio_profile = {
                    **studio_profile_snapshot,
                    "payload": stored_payload,
                }
                logo_record = stored_payload.get("brand_assets", {}).get("logo")
                if isinstance(logo_record, dict):
                    relative_logo = logo_record.get("workspace_relative_path")
                    if not isinstance(relative_logo, str):
                        raise ValueError("Stored Studio logo path is invalid")
                    stored_logo_path = (workspace_root / relative_logo).resolve()
                    if not stored_logo_path.is_relative_to(workspace_root):
                        raise ValueError("Stored Studio logo escapes the workspace")
                    stored_logo_sha256 = logo_record.get("sha256")
                    if (
                        not stored_logo_path.is_file()
                        or file_digest(stored_logo_path) != stored_logo_sha256
                    ):
                        raise ValueError("Stored Studio logo is missing or changed")
                current_format_digest = canonical_digest(
                    {
                        "studio_name": stored_payload["studio_name"],
                        "brand_profile": stored_payload["brand_profile"],
                        "brand_assets": stored_payload.get(
                            "brand_assets", {"logo": None}
                        ),
                        "profile": stored_payload["profile"],
                    }
                )
                if current_format_digest != stored_payload.get("format_digest"):
                    raise ValueError("Stored Studio format digest mismatch")
            else:
                brand_profile = requested_brand
            profile_revision_required = bool(
                studio_profile is None or history or studio_format_brief
            )

            selected_logo_path = (
                Path(requested_logo_path) if requested_logo_path else stored_logo_path
            )
            if (
                requested_logo_path
                and stored_logo_path
                and not (history or studio_format_brief)
            ):
                if (
                    file_digest(Path(requested_logo_path).resolve(strict=True))
                    != stored_logo_sha256
                ):
                    raise ValueError(
                        "Studio logo differs from the approved profile; selected history or an explicit Studio-format brief is required"
                    )
            logo_snapshot = None
            if selected_logo_path:
                if selected_logo_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                    raise ValueError("Studio logo must be a PNG or JPEG file")
                logo_copy = copy_input_snapshot(
                    selected_logo_path,
                    destination_dir=staging_dir / "inputs" / "brand",
                    identity="studio-logo",
                )
                logo_snapshot = _retarget_snapshot(
                    logo_copy, staging_dir=staging_dir, final_run_dir=run_dir
                )

            source_register = {
                "schema_version": 1,
                "workflow": "comunicazione-professionale",
                "run_id": intake["run_id"],
                "created_at": utc_now(),
                "sources": sources,
                "history": history,
                "brand_logo": logo_snapshot,
                "studio_profile": studio_profile_snapshot,
            }
            intake_payload = {
                "schema_version": 1,
                "plugin": "comunicazione-professionale",
                "workflow": "comunicazione-professionale",
                "run_id": intake["run_id"],
                "prepared_at": utc_now(),
                "reference_date": intake["reference_date"],
                "language": intake["language"],
                "jurisdiction": intake["jurisdiction"],
                "objective": intake["objective"],
                "audience": intake["audience"],
                "studio_format_brief": studio_format_brief,
                "requested_channels": intake["channels"],
                "visual_requested": intake["visual_requested"],
                "workspace_id": workspace_payload["workspace_id"],
                "workspace_path": workspace_payload["bound_path"],
                "output_dir": str(run_dir),
                "brand_profile": brand_profile,
                "studio_profile": studio_profile,
                "profile_revision_required": profile_revision_required,
                "external_routes": intake["external_routes"],
                "data_posture": {
                    "selected_source_files_snapshotted_locally": len(sources),
                    "selected_prior_communications_snapshotted_locally": len(history),
                    "model_context_may_include_selected_material": True,
                    "automatic_anonymization": False,
                    "helper_scripts_call_models": False,
                    "helper_scripts_use_connectors": False,
                },
                "execution_trace": [
                    {
                        "step_id": "prepare-run",
                        "kind": "local_input_snapshot",
                        "status": "completed",
                        "execution_location": "cowork_connected_folder",
                        "command": "python scripts/prepare_run.py --workspace <workspace> --intake <intake>",
                        "inputs": [str(intake_path.resolve())],
                        "outputs": [
                            "run_intake.json",
                            "source_register.json",
                            "model_task_packet.json",
                        ],
                    }
                ],
            }
            input_digest = canonical_digest(
                {
                    "intake": intake_payload,
                    "source_register": source_register,
                }
            )
            intake_payload["input_digest"] = input_digest
            task_packet = {
                "schema_version": 1,
                "workflow": "comunicazione-professionale",
                "run_id": intake["run_id"],
                "input_digest": input_digest,
                "objective": intake["objective"],
                "audience": intake["audience"],
                "language": intake["language"],
                "jurisdiction": intake["jurisdiction"],
                "reference_date": intake["reference_date"],
                "requested_channels": intake["channels"],
                "visual_requested": intake["visual_requested"],
                "studio_format_brief": studio_format_brief,
                "profile_revision_required": profile_revision_required,
                "source_snapshots": [
                    {
                        key: row[key]
                        for key in (
                            "id",
                            "title",
                            "authority_role",
                            "public_url",
                            "published_at",
                            "snapshot_path",
                            "sha256",
                        )
                        if key in row
                    }
                    for row in sources
                ],
                "history_snapshots": [
                    {
                        key: row[key]
                        for key in (
                            "id",
                            "channel",
                            "published_at",
                            "snapshot_path",
                            "sha256",
                        )
                        if key in row
                    }
                    for row in history
                ],
                "existing_studio_profile": studio_profile,
                "brand_profile": brand_profile,
                "artifact_schemas": {
                    name: str((PLUGIN_ROOT / "schemas" / filename).resolve())
                    for name, filename in {
                        "answer_contract": "answer_contract.schema.json",
                        "model_contribution": "model_contribution.schema.json",
                        "claim_assurance": "claim_assurance.schema.json",
                        "editorial_assessment": "editorial_assessment.schema.json",
                        "visual_assessment": "visual_assessment.schema.json",
                    }.items()
                },
                "model_pass_templates": {
                    kind: {
                        "version": version,
                        "path": str(path.resolve()),
                        "sha256": prompt_template_digest(kind, version),
                    }
                    for kind, (version, path) in PROMPT_TEMPLATES.items()
                },
                "instructions": [
                    "Use semantic judgment for topic relevance, source authority, meaning, claims, voice, and no_publish.",
                    "Do not treat file registration or source-ID closure as semantic support.",
                    "Use the selected studio examples to propose or follow the studio format without copying passages.",
                    "When no prior Studio communication is selected, distinguish user-supplied format facts from Vera default proposals and never claim observed history.",
                    "A schedule is not evidence that communication is worthwhile.",
                    "Creative Production is an optional art-direction route, never a source of claims or exact public copy; use it only when explicitly selected and continue with Vera's internal renderer when unavailable.",
                ],
            }
            atomic_write_json(staging_dir / "run_intake.json", intake_payload)
            atomic_write_json(staging_dir / "source_register.json", source_register)
            atomic_write_json(staging_dir / "model_task_packet.json", task_packet)
            staging_dir.replace(run_dir)
        except (OSError, ValueError):
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            raise
    return run_dir


def main(argv: list[str] | None = None) -> int:
    """Prepare one run from a reviewed intake file."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--intake", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        run_dir = prepare_run(args.workspace, args.intake)
    except (OSError, ValueError) as exc:
        LOGGER.error("RUN_PREPARATION_FAILED: %s", exc)
        return 1
    LOGGER.info("Prepared communication run: %s", run_dir)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
