#!/usr/bin/env python3
"""Prepare exact minimized input packets for downstream model phases."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from workflow_core import (
    PLUGIN_ROOT,
    atomic_write_json,
    canonical_digest,
    file_digest,
    load_json,
    model_phase_packet_path,
    prompt_template_digest,
    utc_now,
    validate_answer_contract,
    validate_claim_assurance,
    validate_input_integrity,
    validate_schema,
    verify_history_pseudonymization,
    verify_model_phase_packet,
    verify_visual_manifest,
    verify_visual_preview_manifest,
    workflow_lock,
)

__all__ = ["prepare_model_phase", "main"]

LOGGER = logging.getLogger(__name__)


def _input_row(path: Path, role: str) -> dict[str, Any]:
    """Bind one regular file without copying its contents into the packet."""

    candidate = path.expanduser()
    if candidate.is_symlink():
        raise ValueError(f"Model phase input must not be a symlink: {candidate}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"Model phase input must be a regular file: {resolved}")
    return {
        "role": role,
        "path": str(resolved),
        "sha256": file_digest(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _base_packet(root: Path, phase: str) -> dict[str, Any]:
    intake = load_json(root / "run_intake.json")
    template_version, template_path = {
        "claim_assurance": (
            "professional-communication-claim-assurance-v2",
            PLUGIN_ROOT / "prompts" / "claim-assurance-v2.md",
        ),
        "editorial_assessment": (
            "professional-communication-editorial-v4",
            PLUGIN_ROOT / "prompts" / "editorial-assessment-v4.md",
        ),
        "visual_assessment": (
            "professional-visual-editor-v2",
            PLUGIN_ROOT / "prompts" / "visual-assessment-v2.md",
        ),
    }[phase]
    return {
        "schema_version": 1,
        "workflow": "comunicazione-professionale",
        "run_id": intake["run_id"],
        "input_digest": intake["input_digest"],
        "phase": phase,
        "created_at": utc_now(),
        "history_available_to_phase": False,
        "excluded_data_classes": [
            "raw prior communications",
            "mechanically stripped history intermediates",
            "pseudonymized prior communications",
            "identity mappings",
            "pseudonymization and privacy-review transcripts",
        ],
        "model_pass_template": {
            "version": template_version,
            "path": str(template_path.resolve()),
            "sha256": prompt_template_digest(phase, template_version),
        },
    }


def _claim_packet(
    root: Path,
    *,
    contribution_path: Path,
    answer_contract_path: Path,
) -> dict[str, Any]:
    intake = load_json(root / "run_intake.json")
    source_register = load_json(root / "source_register.json")
    contribution = load_json(contribution_path)
    validate_schema(contribution, "model_contribution.schema.json")
    answer_contract = load_json(answer_contract_path)
    validate_answer_contract(
        answer_contract,
        intake={
            "run_id": intake["run_id"],
            "audience": intake["audience"],
            "language": intake["language"],
            "jurisdiction": intake["jurisdiction"],
        },
    )
    packet = _base_packet(root, "claim_assurance")
    packet["allowed_data_classes"] = [
        "answer contract",
        "proposed contribution",
        "selected current source snapshots",
    ]
    packet["allowed_inputs"] = [
        _input_row(answer_contract_path, "answer_contract"),
        _input_row(contribution_path, "contribution_candidate"),
        *[
            _input_row(Path(row["snapshot_path"]), f"source:{row['id']}")
            for row in source_register["sources"]
        ],
        _input_row(PLUGIN_ROOT / "prompts" / "claim-assurance-v2.md", "phase_prompt"),
        _input_row(
            PLUGIN_ROOT / "schemas" / "claim_assurance.schema.json",
            "output_schema",
        ),
    ]
    packet["instructions"] = [
        "Open only allowed_inputs.",
        "Prior communications are style evidence and are not available to claim assurance.",
        "Assess source identity, semantic support, reasoning, time and modality, and professional judgment separately.",
    ]
    return packet


def _editorial_packet(
    root: Path,
    *,
    contribution_path: Path,
    claim_assurance_path: Path,
) -> dict[str, Any]:
    contribution = load_json(contribution_path)
    validate_schema(contribution, "model_contribution.schema.json")
    assurance = load_json(claim_assurance_path)
    validate_schema(assurance, "claim_assurance.schema.json")
    packet = _base_packet(root, "editorial_assessment")
    packet["allowed_data_classes"] = [
        "proposed contribution",
        "completed claim assurance",
    ]
    packet["allowed_inputs"] = [
        _input_row(contribution_path, "contribution_candidate"),
        _input_row(claim_assurance_path, "claim_assurance"),
        _input_row(
            PLUGIN_ROOT / "prompts" / "editorial-assessment-v4.md",
            "phase_prompt",
        ),
        _input_row(
            PLUGIN_ROOT / "schemas" / "editorial_assessment.schema.json",
            "output_schema",
        ),
    ]
    packet["instructions"] = [
        "Open only allowed_inputs.",
        "Do not open selected current sources or any prior communication; claim assurance already carries the support result.",
        "Assess reader value, specificity, professional limits, channels, and proposed slides independently.",
    ]
    return packet


def _visual_packet(root: Path, *, qa_preview: bool) -> dict[str, Any]:
    manifest_name = (
        "visual_preview_manifest.json" if qa_preview else "visual_manifest.json"
    )
    manifest_digest = (
        verify_visual_preview_manifest(root)
        if qa_preview
        else verify_visual_manifest(root)
    )
    manifest = load_json(root / manifest_name)
    packet = _base_packet(root, "visual_assessment")
    packet["render_state"] = "qa_preview" if qa_preview else "accepted_semantics"
    packet["manifest_digest"] = manifest_digest
    packet["allowed_data_classes"] = [
        "accepted contribution and channel copy",
        "exact visual manifest",
        "exact rendered PNG and PDF outputs",
    ]
    packet["allowed_inputs"] = [
        _input_row(root / "content_workbench.json", "accepted_contribution"),
        _input_row(root / manifest_name, "visual_manifest"),
        *[
            _input_row(
                (
                    Path(row["path"])
                    if Path(row["path"]).is_absolute()
                    else root / row["path"]
                ),
                f"render:{index:03d}",
            )
            for index, row in enumerate(manifest["outputs"], start=1)
        ],
        _input_row(PLUGIN_ROOT / "prompts" / "visual-assessment-v2.md", "phase_prompt"),
        _input_row(
            PLUGIN_ROOT / "schemas" / "visual_assessment.schema.json",
            "output_schema",
        ),
    ]
    packet["instructions"] = [
        "Open only allowed_inputs.",
        "Do not open source files, prior communications, identity mappings, or earlier model transcripts.",
        "Judge the exact rendered bytes against the accepted copy and manifest.",
    ]
    return packet


def prepare_model_phase(
    run_dir: Path,
    phase: str,
    *,
    contribution_path: Path | None = None,
    answer_contract_path: Path | None = None,
    claim_assurance_path: Path | None = None,
    qa_preview: bool = False,
) -> Path:
    """Write and verify one exact minimized phase packet."""

    root = run_dir.resolve()
    with workflow_lock(root):
        validate_input_integrity(root)
        verify_history_pseudonymization(root)
        if phase == "claim_assurance":
            if contribution_path is None or answer_contract_path is None:
                raise ValueError(
                    "Claim assurance requires contribution and answer contract"
                )
            packet = _claim_packet(
                root,
                contribution_path=contribution_path,
                answer_contract_path=answer_contract_path,
            )
        elif phase == "editorial_assessment":
            if contribution_path is None or claim_assurance_path is None:
                raise ValueError(
                    "Editorial assessment requires contribution and claim assurance"
                )
            packet = _editorial_packet(
                root,
                contribution_path=contribution_path,
                claim_assurance_path=claim_assurance_path,
            )
        elif phase == "visual_assessment":
            packet = _visual_packet(root, qa_preview=qa_preview)
        else:
            raise ValueError(f"Unsupported model phase: {phase}")
        packet["packet_digest"] = canonical_digest(packet)
        path = model_phase_packet_path(root, phase)
        atomic_write_json(path, packet)
        verify_model_phase_packet(root, phase)
        return path


def main(argv: list[str] | None = None) -> int:
    """Prepare one minimized downstream model phase packet."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--phase",
        choices=("claim_assurance", "editorial_assessment", "visual_assessment"),
        required=True,
    )
    parser.add_argument("--contribution", type=Path)
    parser.add_argument("--answer-contract", type=Path)
    parser.add_argument("--claim-assurance", type=Path)
    parser.add_argument("--qa-preview", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = prepare_model_phase(
            args.run_dir,
            args.phase,
            contribution_path=args.contribution,
            answer_contract_path=args.answer_contract,
            claim_assurance_path=args.claim_assurance,
            qa_preview=args.qa_preview,
        )
    except (OSError, ValueError) as exc:
        LOGGER.error("MODEL_PHASE_PREPARATION_FAILED: %s", exc)
        return 1
    LOGGER.info("Prepared minimized model phase packet: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
