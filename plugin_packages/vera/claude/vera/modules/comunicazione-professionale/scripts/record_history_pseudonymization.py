#!/usr/bin/env python3
"""Record complete model-pseudonymized derivatives of selected communications."""

from __future__ import annotations

import argparse
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from workflow_core import (
    atomic_write_json,
    atomic_write_text,
    canonical_digest,
    file_digest,
    load_json,
    prompt_template_digest,
    utc_now,
    validate_history_pseudonymization_payload,
    validate_input_integrity,
    workflow_lock,
)

__all__ = ["record_history_pseudonymization", "main"]

LOGGER = logging.getLogger(__name__)


def _assessment_required_model_task_packet(
    packet: dict[str, Any], *, record_path: Path, record: dict[str, Any]
) -> dict[str, Any]:
    """Keep generation blocked until an independent derivative-only review."""

    updated = dict(packet)
    updated["history_context"] = {
        "status": "privacy_assessment_required",
        "pending_record_path": str(record_path.resolve()),
        "pending_record_digest": record["record_digest"],
        "history_ids": [item["history_id"] for item in record["history_items"]],
        "raw_history_paths_included": False,
        "identity_mapping_included": False,
        "purpose": "studio_voice_and_format_learning_only",
        "privacy_assessment_packet_path": str(
            (record_path.parent / "history_privacy_assessment_packet.json").resolve()
        ),
    }
    return updated


def record_history_pseudonymization(
    run_dir: Path,
    pseudonymization_path: Path,
    *,
    provider: str,
    model: str,
    session_id: str,
    recorded_by: str,
) -> Path:
    """Validate, split, and bind one isolated semantic pseudonymization result."""

    root = run_dir.resolve()
    with workflow_lock(root):
        validate_input_integrity(root)
        source_register = load_json(root / "source_register.json")
        if not source_register["history"]:
            raise ValueError(
                "History pseudonymization is not applicable without selected history"
            )
        final_record_path = root / "history_pseudonymization_record.json"
        if final_record_path.exists():
            raise ValueError(
                "History pseudonymization is already recorded for this run"
            )
        pending_documents_dir = root / "history-pseudonymized-candidate"
        pending_map_path = root / "history_identity_map.pending.json"
        pending_record_path = root / "history_pseudonymization_record.pending.json"
        assessment_packet_path = root / "history_privacy_assessment_packet.json"
        for stale_path in (
            pending_map_path,
            pending_record_path,
            assessment_packet_path,
        ):
            stale_path.unlink(missing_ok=True)
        if pending_documents_dir.exists():
            if pending_documents_dir.is_symlink() or not pending_documents_dir.is_dir():
                raise ValueError("Unsafe pending history candidate path")
            shutil.rmtree(pending_documents_dir)
        result = load_json(pseudonymization_path)
        source = pseudonymization_path.expanduser().resolve(strict=True)
        if source.is_relative_to(root):
            raise ValueError(
                "History-pseudonymization input must be outside the run before recording"
            )
        validate_history_pseudonymization_payload(
            result,
            run_dir=root,
            source_register=source_register,
        )
        normalized_session_id = session_id.strip()
        if len(normalized_session_id) < 8:
            raise ValueError(
                "History-pseudonymization session id must identify one exact host session"
            )

        staging_dir = Path(
            tempfile.mkdtemp(prefix=".history-pseudonymization.", dir=root)
        )
        installed_documents = False
        installed_map = False
        installed_record = False
        installed_packet = False
        try:
            documents_dir = staging_dir / "documents"
            document_records: list[dict[str, Any]] = []
            for item in result["history_items"]:
                destination = documents_dir / f"{item['history_id']}.txt"
                atomic_write_text(destination, item["pseudonymized_document"])
                document_records.append(
                    {
                        "history_id": item["history_id"],
                        "channel": item["channel"],
                        "path": str(
                            (
                                root / "history-pseudonymized" / destination.name
                            ).resolve()
                        ),
                        "sha256": file_digest(destination),
                        "size_bytes": destination.stat().st_size,
                        "transformations_summary": item["transformations_summary"],
                        "residual_identification_risk": item[
                            "residual_identification_risk"
                        ],
                    }
                )

            current_local_map = load_json(root / "history_identity_map.json")
            local_map_path = staging_dir / "history_identity_map.json"
            local_map = {
                "schema_version": 1,
                "workflow": "comunicazione-professionale",
                "run_id": result["run_id"],
                "input_digest": result["input_digest"],
                "local_only": True,
                "never_include_in_downstream_model_context": True,
                "mechanical_mapping": current_local_map["entries"],
                "semantic_mapping": result["identity_mapping"],
            }
            stable_local_map = {
                key: value
                for key, value in local_map.items()
                if key != "mapping_digest"
            }
            local_map["mapping_digest"] = canonical_digest(stable_local_map)
            atomic_write_json(local_map_path, local_map)

            provenance = {
                "provider": provider,
                "model": model,
                "template_version": "professional-communication-history-pseudonymization-v1",
                "template_sha256": prompt_template_digest(
                    "history_pseudonymization",
                    "professional-communication-history-pseudonymization-v1",
                ),
                "session_id": normalized_session_id,
                "execution_mode": "isolated_host_session_attestation",
                "provider_authenticated": False,
                "recorded_by": recorded_by,
                "recorded_at": utc_now(),
            }
            record: dict[str, Any] = {
                "schema_version": 1,
                "workflow": "comunicazione-professionale",
                "run_id": result["run_id"],
                "input_digest": result["input_digest"],
                "purpose": result["purpose"],
                "history_items": document_records,
                "pseudonymization_assessment": result["pseudonymization_assessment"],
                "limitations": result["limitations"],
                "identity_mapping_path": str(
                    (root / "history_identity_map.json").resolve()
                ),
                "identity_mapping_digest": local_map["mapping_digest"],
                "identity_mapping_in_downstream_context": False,
                "model_provenance": provenance,
            }
            record["record_digest"] = canonical_digest(record)
            atomic_write_json(staging_dir / "record.json", record)

            assessment_packet = {
                "schema_version": 1,
                "workflow": "comunicazione-professionale",
                "run_id": result["run_id"],
                "input_digest": result["input_digest"],
                "pseudonymization_record_digest": record["record_digest"],
                "purpose": "independent_residual_identification_review_before_downstream_use",
                "history_documents": [
                    {
                        **{
                            key: row[key]
                            for key in (
                                "history_id",
                                "channel",
                                "sha256",
                                "size_bytes",
                            )
                        },
                        "path": str(
                            (pending_documents_dir / Path(row["path"]).name).resolve()
                        ),
                    }
                    for row in document_records
                ],
                "raw_history_paths_included": False,
                "mechanically_stripped_paths_included": False,
                "identity_mapping_included": False,
                "pseudonymization_transcript_included": False,
                "model_pass_template": {
                    "version": "professional-communication-history-privacy-assessment-v1",
                    "path": str(
                        (
                            Path(__file__).resolve().parents[1]
                            / "prompts"
                            / "history-privacy-assessment-v1.md"
                        ).resolve()
                    ),
                    "sha256": prompt_template_digest(
                        "history_privacy_assessment",
                        "professional-communication-history-privacy-assessment-v1",
                    ),
                },
                "artifact_schema": str(
                    (
                        Path(__file__).resolve().parents[1]
                        / "schemas"
                        / "history_privacy_assessment.schema.json"
                    ).resolve()
                ),
            }
            assessment_packet["packet_digest"] = canonical_digest(assessment_packet)
            atomic_write_json(staging_dir / "assessment-packet.json", assessment_packet)

            final_documents_dir = root / "history-pseudonymized"
            if final_documents_dir.exists():
                raise ValueError("Pseudonymized history directory already exists")
            documents_dir.replace(pending_documents_dir)
            installed_documents = True
            local_map_path.replace(pending_map_path)
            installed_map = True
            (staging_dir / "record.json").replace(pending_record_path)
            installed_record = True
            (staging_dir / "assessment-packet.json").replace(assessment_packet_path)
            installed_packet = True
            packet_path = root / "model_task_packet.json"
            packet = load_json(packet_path)
            atomic_write_json(
                packet_path,
                _assessment_required_model_task_packet(
                    packet,
                    record_path=pending_record_path,
                    record=record,
                ),
            )
        except (OSError, ValueError):
            if installed_documents and pending_documents_dir.exists():
                shutil.rmtree(pending_documents_dir)
            if installed_record:
                pending_record_path.unlink(missing_ok=True)
            if installed_map:
                pending_map_path.unlink(missing_ok=True)
            if installed_packet:
                assessment_packet_path.unlink(missing_ok=True)
            raise
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
        return pending_record_path


def main(argv: list[str] | None = None) -> int:
    """Record one ready history-pseudonymization result."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--pseudonymization", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--recorded-by", required=True)
    args = parser.parse_args(argv)
    try:
        path = record_history_pseudonymization(
            args.run_dir,
            args.pseudonymization,
            provider=args.provider,
            model=args.model,
            session_id=args.session_id,
            recorded_by=args.recorded_by,
        )
    except (OSError, ValueError) as exc:
        LOGGER.error("HISTORY_PSEUDONYMIZATION_RECORD_FAILED: %s", exc)
        return 1
    LOGGER.info("Recorded history pseudonymization: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
