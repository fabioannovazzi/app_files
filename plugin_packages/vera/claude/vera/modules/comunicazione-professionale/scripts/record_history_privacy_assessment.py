#!/usr/bin/env python3
"""Record independent history privacy review and unlock generation safely."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from workflow_core import (
    atomic_write_json,
    canonical_digest,
    downstream_history_items,
    file_digest,
    load_json,
    prompt_template_digest,
    utc_now,
    validate_history_privacy_assessment,
    validate_input_integrity,
    workflow_lock,
)

__all__ = ["record_history_privacy_assessment", "main"]

LOGGER = logging.getLogger(__name__)


def _cleanup_entries(root: Path) -> list[dict[str, Any]]:
    """Describe transient files before deletion without retaining their text."""

    targets = [
        root / "history_pseudonymization_packet.json",
        root / "history_privacy_assessment_packet.json",
    ]
    model_inputs = root / "history-model-inputs"
    if model_inputs.is_dir():
        targets.extend(
            sorted(path for path in model_inputs.iterdir() if path.is_file())
        )
    entries: list[dict[str, Any]] = []
    for path in targets:
        if not path.is_file() or path.is_symlink():
            continue
        entries.append(
            {
                "path": str(path.relative_to(root)),
                "sha256": file_digest(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return entries


def _delete_transient_inputs(root: Path, entries: list[dict[str, Any]]) -> None:
    """Delete only the exact transient paths described by the cleanup receipt."""

    for entry in entries:
        relative = Path(str(entry["path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("History cleanup target escapes the run")
        unresolved = root / relative
        if unresolved.is_symlink():
            raise ValueError("History cleanup target must not be a symlink")
        path = unresolved.resolve()
        if not path.is_relative_to(root):
            raise ValueError("History cleanup target escapes the run")
        if not path.is_file():
            continue
        if path.stat().st_size != entry["size_bytes"]:
            raise ValueError("History cleanup target size changed")
        if file_digest(path) != entry["sha256"]:
            raise ValueError("History cleanup target digest changed")
        path.unlink(missing_ok=True)
    model_inputs = root / "history-model-inputs"
    if model_inputs.exists():
        if model_inputs.is_symlink() or not model_inputs.is_dir():
            raise ValueError("History model-input directory is unsafe")
        if any(model_inputs.iterdir()):
            raise ValueError("History model-input directory contains unexpected files")
        model_inputs.rmdir()


def _ready_model_task_packet(
    packet: dict[str, Any],
    *,
    pseudonymization_record: dict[str, Any],
    privacy_record: dict[str, Any],
) -> dict[str, Any]:
    """Expose only accepted derivatives to the generation phase."""

    updated = dict(packet)
    updated["phase"] = "generation"
    updated["history_context"] = {
        "status": "ready",
        "record_digest": pseudonymization_record["record_digest"],
        "privacy_assessment_record_digest": privacy_record["record_digest"],
        "history_ids": [
            item["history_id"] for item in pseudonymization_record["history_items"]
        ],
        "pseudonymized_documents": downstream_history_items(pseudonymization_record),
        "raw_history_paths_included": False,
        "identity_mapping_included": False,
        "purpose": "studio_voice_and_format_learning_only",
    }
    return updated


def _cleanup_after_acceptance(
    root: Path,
    *,
    run_id: str,
    input_digest: str,
) -> None:
    """Delete transient history inputs and record an exact local receipt."""

    cleanup_path = root / "history_cleanup_receipt.json"
    cleanup_preexisted = cleanup_path.is_file()
    if cleanup_preexisted:
        cleanup_receipt = load_json(cleanup_path)
        if cleanup_receipt.get("run_id") != run_id:
            raise ValueError("History cleanup receipt run_id mismatch")
        if cleanup_receipt.get("input_digest") != input_digest:
            raise ValueError("History cleanup receipt input binding mismatch")
        cleanup_entries = cleanup_receipt["deleted_artifacts"]
    else:
        cleanup_entries = _cleanup_entries(root)
        cleanup_receipt = {
            "schema_version": 1,
            "workflow": "comunicazione-professionale",
            "run_id": run_id,
            "input_digest": input_digest,
            "reason": "transient_history_model_inputs_no_longer_required_after_independent_privacy_review",
            "deleted_artifacts": cleanup_entries,
            "raw_history_snapshots_deleted": False,
            "identity_mapping_deleted": False,
        }
    _delete_transient_inputs(root, cleanup_entries)
    if not cleanup_preexisted:
        cleanup_receipt["cleaned_at"] = utc_now()
        cleanup_receipt["cleanup_digest"] = canonical_digest(cleanup_receipt)
        atomic_write_json(cleanup_path, cleanup_receipt)


def _unlock_generation(
    root: Path,
    *,
    pseudonymization_record: dict[str, Any],
    privacy_record: dict[str, Any],
) -> None:
    """Expose only the accepted derivative projection after cleanup succeeds."""

    packet_path = root / "model_task_packet.json"
    packet = load_json(packet_path)
    atomic_write_json(
        packet_path,
        _ready_model_task_packet(
            packet,
            pseudonymization_record=pseudonymization_record,
            privacy_record=privacy_record,
        ),
    )


def _resume_finalization(
    root: Path,
    *,
    assessment: dict[str, Any],
) -> Path:
    """Finish cleanup and task routing after an interrupted accepted promotion."""

    final_record_path = root / "history_privacy_assessment_record.json"
    final_pseudonymization_path = root / "history_pseudonymization_record.json"
    if not final_pseudonymization_path.is_file():
        raise ValueError("Final history pseudonymization record is missing")
    privacy_record = load_json(final_record_path)
    expected_privacy_digest = str(privacy_record.get("record_digest") or "")
    stable_privacy = {
        key: value for key, value in privacy_record.items() if key != "record_digest"
    }
    if expected_privacy_digest != canonical_digest(stable_privacy):
        raise ValueError("History privacy assessment record digest mismatch")
    if canonical_digest(privacy_record.get("assessment")) != canonical_digest(
        assessment
    ):
        raise ValueError("A different history privacy assessment is already recorded")
    pseudonymization_record = load_json(final_pseudonymization_path)
    expected_pseudonymization_digest = str(
        pseudonymization_record.get("record_digest") or ""
    )
    stable_pseudonymization = {
        key: value
        for key, value in pseudonymization_record.items()
        if key != "record_digest"
    }
    if expected_pseudonymization_digest != canonical_digest(stable_pseudonymization):
        raise ValueError("History pseudonymization record digest mismatch")
    if privacy_record.get("pseudonymization_record_digest") != (
        pseudonymization_record["record_digest"]
    ):
        raise ValueError("History privacy assessment binding mismatch")
    _cleanup_after_acceptance(
        root,
        run_id=str(privacy_record["run_id"]),
        input_digest=str(privacy_record["input_digest"]),
    )
    _unlock_generation(
        root,
        pseudonymization_record=pseudonymization_record,
        privacy_record=privacy_record,
    )
    return final_record_path


def record_history_privacy_assessment(
    run_dir: Path,
    assessment_path: Path,
    *,
    provider: str,
    model: str,
    recorded_by: str,
) -> Path:
    """Finalize one independently accepted derivative-only privacy review."""

    root = run_dir.resolve()
    with workflow_lock(root):
        validate_input_integrity(root)
        final_record_path = root / "history_privacy_assessment_record.json"
        assessment = load_json(assessment_path)
        if final_record_path.is_file():
            return _resume_finalization(root, assessment=assessment)
        pending_record_path = root / "history_pseudonymization_record.pending.json"
        pending_map_path = root / "history_identity_map.pending.json"
        pending_documents_dir = root / "history-pseudonymized-candidate"
        assessment_packet_path = root / "history_privacy_assessment_packet.json"
        for required in (
            pending_record_path,
            pending_map_path,
            assessment_packet_path,
        ):
            if not required.is_file():
                raise ValueError(
                    f"Missing pending history privacy artifact: {required.name}"
                )
        if not pending_documents_dir.is_dir() or pending_documents_dir.is_symlink():
            raise ValueError("Missing safe pseudonymized-history candidate directory")

        pseudonymization_record = load_json(pending_record_path)
        assessment_packet = load_json(assessment_packet_path)
        validate_history_privacy_assessment(
            assessment,
            run_dir=root,
            pseudonymization_record=pseudonymization_record,
            assessment_packet=assessment_packet,
        )
        if assessment["verdict"] != "ready":
            raise ValueError(
                "History privacy assessment requires revision before downstream use"
            )

        protocol = assessment["assessment_protocol"]
        privacy_record: dict[str, Any] = {
            "schema_version": 1,
            "workflow": "comunicazione-professionale",
            "run_id": assessment["run_id"],
            "input_digest": assessment["input_digest"],
            "pseudonymization_record_digest": pseudonymization_record["record_digest"],
            "assessment": assessment,
            "model_provenance": {
                "provider": provider,
                "model": model,
                "template_version": protocol["assessment_template_version"],
                "template_sha256": prompt_template_digest(
                    "history_privacy_assessment",
                    protocol["assessment_template_version"],
                ),
                "assessor_session_id": protocol["assessor_session_id"],
                "execution_mode": "isolated_derivative_only_host_session_attestation",
                "provider_authenticated": False,
                "recorded_by": recorded_by,
            },
            "recorded_at": utc_now(),
        }
        privacy_record["record_digest"] = canonical_digest(privacy_record)

        final_documents_dir = root / "history-pseudonymized"
        final_pseudonymization_record_path = (
            root / "history_pseudonymization_record.json"
        )
        if final_documents_dir.exists() or final_pseudonymization_record_path.exists():
            raise ValueError("Final history privacy artifacts already exist")
        current_mechanical_map = load_json(root / "history_identity_map.json")
        installed_documents = False
        installed_map = False
        installed_pseudonymization = False
        installed_privacy = False
        try:
            pending_documents_dir.replace(final_documents_dir)
            installed_documents = True
            pending_map_path.replace(root / "history_identity_map.json")
            installed_map = True
            pending_record_path.replace(final_pseudonymization_record_path)
            installed_pseudonymization = True
            atomic_write_json(final_record_path, privacy_record)
            installed_privacy = True
        except (OSError, ValueError):
            if installed_privacy:
                final_record_path.unlink(missing_ok=True)
            if installed_pseudonymization:
                final_pseudonymization_record_path.replace(pending_record_path)
            if installed_map:
                (root / "history_identity_map.json").replace(pending_map_path)
                atomic_write_json(
                    root / "history_identity_map.json", current_mechanical_map
                )
            if installed_documents:
                final_documents_dir.replace(pending_documents_dir)
            raise
        _cleanup_after_acceptance(
            root,
            run_id=str(assessment["run_id"]),
            input_digest=str(assessment["input_digest"]),
        )
        _unlock_generation(
            root,
            pseudonymization_record=pseudonymization_record,
            privacy_record=privacy_record,
        )
        return final_record_path


def main(argv: list[str] | None = None) -> int:
    """Record one independent ready history privacy assessment."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--recorded-by", required=True)
    args = parser.parse_args(argv)
    try:
        path = record_history_privacy_assessment(
            args.run_dir,
            args.assessment,
            provider=args.provider,
            model=args.model,
            recorded_by=args.recorded_by,
        )
    except (OSError, ValueError) as exc:
        LOGGER.error("HISTORY_PRIVACY_ASSESSMENT_RECORD_FAILED: %s", exc)
        return 1
    LOGGER.info("Recorded independent history privacy assessment: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
