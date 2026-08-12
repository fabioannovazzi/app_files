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

from history_privacy import (
    MECHANICAL_STRIPPING_VERSION,
    extract_history_text,
    strip_mechanical_identifiers,
)
from workflow_core import (
    PLUGIN_ROOT,
    PROMPT_TEMPLATES,
    atomic_write_json,
    atomic_write_text,
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


def _prepare_stripped_history(
    history: list[dict[str, Any]],
    *,
    staging_dir: Path,
    final_run_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Strip explicit-format identifiers before the selected model sees history."""

    model_inputs: list[dict[str, Any]] = []
    mapping_entries: list[dict[str, Any]] = []
    placeholders: dict[tuple[str, str], str] = {}
    counters: dict[str, int] = {}
    for row in history:
        committed_snapshot = Path(row["snapshot_path"])
        staging_snapshot = staging_dir / committed_snapshot.relative_to(final_run_dir)
        raw_text = extract_history_text(staging_snapshot)
        stripped_text, entries, placeholders, counters = strip_mechanical_identifiers(
            raw_text,
            existing_placeholders=placeholders,
            counters=counters,
        )
        stripped_path = staging_dir / "history-model-inputs" / f"{row['id']}.txt"
        atomic_write_text(stripped_path, stripped_text)
        for entry in entries:
            mapping_entries.append({"history_id": row["id"], **entry})
        model_inputs.append(
            {
                "id": row["id"],
                "channel": row["channel"],
                **(
                    {"published_at": row["published_at"]}
                    if row.get("published_at")
                    else {}
                ),
                "path": str(
                    (
                        final_run_dir / "history-model-inputs" / stripped_path.name
                    ).resolve()
                ),
                "sha256": file_digest(stripped_path),
                "size_bytes": stripped_path.stat().st_size,
                "mechanical_stripping_version": MECHANICAL_STRIPPING_VERSION,
            }
        )
    mapping = {
        "schema_version": 1,
        "workflow": "comunicazione-professionale",
        "run_id": final_run_dir.name,
        "local_only": True,
        "never_include_in_model_context": True,
        "mechanical_stripping_version": MECHANICAL_STRIPPING_VERSION,
        "entries": mapping_entries,
    }
    stable_mapping = {
        key: value for key, value in mapping.items() if key != "mapping_digest"
    }
    mapping["mapping_digest"] = canonical_digest(stable_mapping)
    return model_inputs, mapping


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
            history_model_inputs, history_identity_map = _prepare_stripped_history(
                history,
                staging_dir=staging_dir,
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
                    "raw_history_sent_to_model": False,
                    "mechanically_stripped_history_model_context_limited_to_one_pseudonymization_pass": bool(
                        history
                    ),
                    "downstream_history_requires_complete_pseudonymized_documents": bool(
                        history
                    ),
                    "local_identity_map_kept_out_of_model_context": bool(history),
                    "automatic_anonymization_before_selected_runtime": False,
                    "mechanical_identifier_stripping_before_selected_runtime": bool(
                        history
                    ),
                    "helper_scripts_call_models": False,
                    "helper_scripts_use_connectors": False,
                },
                "execution_trace": [
                    {
                        "step_id": "prepare-run",
                        "kind": "local_input_snapshot",
                        "status": "completed",
                        "execution_location": "local_codex_workspace",
                        "command": "python scripts/prepare_run.py --workspace <workspace> --intake <intake>",
                        "inputs": [str(intake_path.resolve())],
                        "outputs": [
                            "run_intake.json",
                            "source_register.json",
                            *(
                                ["history_pseudonymization_packet.json"]
                                if history
                                else []
                            ),
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
            if history:
                history_identity_map["input_digest"] = input_digest
                stable_history_identity_map = {
                    key: value
                    for key, value in history_identity_map.items()
                    if key != "mapping_digest"
                }
                history_identity_map["mapping_digest"] = canonical_digest(
                    stable_history_identity_map
                )
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
                "history_context": (
                    {
                        "status": "preparation_required",
                        "history_ids": [row["id"] for row in history],
                        "raw_history_paths_included": False,
                        "identity_mapping_included": False,
                        "purpose": "studio_voice_and_format_learning_only",
                        "pseudonymization_packet_path": str(
                            (run_dir / "history_pseudonymization_packet.json").resolve()
                        ),
                    }
                    if history
                    else {
                        "status": "not_applicable",
                        "history_ids": [],
                        "raw_history_paths_included": False,
                        "identity_mapping_included": False,
                        "purpose": "studio_voice_and_format_learning_only",
                    }
                ),
                "existing_studio_profile": studio_profile,
                "brand_profile": brand_profile,
                "artifact_schemas": {
                    name: str((PLUGIN_ROOT / "schemas" / filename).resolve())
                    for name, filename in {
                        "answer_contract": "answer_contract.schema.json",
                        "history_pseudonymization": "history_pseudonymization.schema.json",
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
                    if kind != "history_pseudonymization"
                },
                "instructions": [
                    "Use semantic judgment for topic relevance, source authority, meaning, claims, voice, and no_publish.",
                    "Do not treat file registration or source-ID closure as semantic support.",
                    "Use the selected studio examples to propose or follow the studio format without copying passages.",
                    "When no prior Studio communication is selected, distinguish user-supplied format facts from Vera default proposals and never claim observed history.",
                    "When prior communications are selected, do not generate until history_context is ready; use only its complete recorded pseudonymized documents and never open raw or mechanically stripped history or the local identity map downstream.",
                    "A schedule is not evidence that communication is worthwhile.",
                    "Creative Production is an optional art-direction route, never a source of claims or exact public copy; use it only when explicitly selected and continue with Vera's internal renderer when unavailable.",
                ],
            }
            atomic_write_json(staging_dir / "run_intake.json", intake_payload)
            atomic_write_json(staging_dir / "source_register.json", source_register)
            if history:
                atomic_write_json(
                    staging_dir / "history_identity_map.json",
                    history_identity_map,
                )
                atomic_write_json(
                    staging_dir / "history_pseudonymization_packet.json",
                    {
                        "schema_version": 1,
                        "workflow": "comunicazione-professionale",
                        "run_id": intake["run_id"],
                        "input_digest": input_digest,
                        "purpose": "complete_document_pseudonymization_for_studio_voice_and_format_learning",
                        "history_documents": history_model_inputs,
                        "raw_history_paths_included": False,
                        "identity_mapping_included": False,
                        "local_preprocessing": {
                            "version": MECHANICAL_STRIPPING_VERSION,
                            "categories": [
                                "email",
                                "phone",
                                "tax_id",
                                "bank_account",
                                "case_number",
                            ],
                            "semantic_identifiers_remain_for_model_pseudonymization": True,
                        },
                        "artifact_schema": str(
                            (
                                PLUGIN_ROOT
                                / "schemas"
                                / "history_pseudonymization.schema.json"
                            ).resolve()
                        ),
                        "model_pass_template": {
                            "version": PROMPT_TEMPLATES["history_pseudonymization"][0],
                            "path": str(
                                PROMPT_TEMPLATES["history_pseudonymization"][
                                    1
                                ].resolve()
                            ),
                            "sha256": prompt_template_digest(
                                "history_pseudonymization",
                                PROMPT_TEMPLATES["history_pseudonymization"][0],
                            ),
                        },
                    },
                )
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
