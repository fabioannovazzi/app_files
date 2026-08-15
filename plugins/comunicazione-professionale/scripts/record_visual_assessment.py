#!/usr/bin/env python3
"""Record a model-led assessment of exact rendered professional visuals."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from workflow_core import (
    atomic_write_json,
    canonical_digest,
    load_json,
    prompt_template_digest,
    recompute_contribution_digest,
    utc_now,
    validate_schema,
    verify_model_phase_packet,
    verify_visual_manifest,
    verify_visual_preview_manifest,
    workflow_lock,
)

__all__ = ["record_visual_assessment", "main"]

LOGGER = logging.getLogger(__name__)


def record_visual_assessment(
    run_dir: Path,
    assessment_path: Path,
    *,
    provider: str,
    model: str,
    qa_preview: bool,
) -> Path:
    """Bind one semantic visual assessment to exact current image bytes."""

    root = run_dir.resolve()
    with workflow_lock(root):
        assessment = load_json(assessment_path)
        validate_schema(assessment, "visual_assessment.schema.json")
        protocol = assessment["assessment_protocol"]
        template_digest = prompt_template_digest(
            "visual_assessment", protocol["assessment_template_version"]
        )
        if protocol["template_sha256"] != template_digest:
            raise ValueError("Visual-assessment template digest mismatch")
        workbench = load_json(root / "content_workbench.json")
        recompute_contribution_digest(root)
        expected_state = "qa_preview" if qa_preview else "accepted_semantics"
        manifest_digest = (
            verify_visual_preview_manifest(root)
            if qa_preview
            else verify_visual_manifest(root)
        )
        phase_packet = verify_model_phase_packet(root, "visual_assessment")
        if phase_packet.get("render_state") != expected_state:
            raise ValueError("Visual model phase packet render_state mismatch")
        if phase_packet.get("manifest_digest") != manifest_digest:
            raise ValueError(
                "Visual model phase packet is stale for the current render"
            )
        if assessment["run_id"] != workbench["run_id"]:
            raise ValueError("Visual assessment run_id does not match contribution")
        if assessment["render_state"] != expected_state:
            raise ValueError("Visual assessment render_state does not match manifest")
        if assessment["assessed_manifest_digest"] != manifest_digest:
            raise ValueError("Visual assessment is stale for the current render")
        prior_sessions = {
            workbench["model_provenance"]["generator"]["session_id"],
            workbench["model_provenance"]["claim_assessor"]["assessor_session_id"],
            workbench["model_provenance"]["editorial_assessor"]["assessor_session_id"],
            workbench["model_provenance"]["editorial_assessor"][
                "qualification_session_id"
            ],
        }
        if protocol["assessor_session_id"] in prior_sessions:
            raise ValueError(
                "Visual assessment must use a host session distinct from generation, claim, editorial, and benchmark passes"
            )
        preview_record_path = root / "visual_preview_assessment_record.json"
        if not qa_preview and preview_record_path.is_file():
            preview_record = load_json(preview_record_path)
            preview_session = (
                preview_record.get("assessment", {})
                .get("assessment_protocol", {})
                .get("assessor_session_id")
            )
            if preview_session == protocol["assessor_session_id"]:
                raise ValueError(
                    "Release visual assessment must use a fresh session after preview assessment"
                )
        slide_count = len(workbench["contribution"]["visual_story"]["slides"])
        assessed_indices = [
            row["slide_index"] for row in assessment["slide_assessments"]
        ]
        if assessed_indices != list(range(1, slide_count + 1)):
            raise ValueError(
                "Visual assessment must cover every slide once and in order"
            )
        if assessment["verdict"] == "ready" and any(
            row["verdict"] in {"weak", "redundant"}
            for row in assessment["slide_assessments"]
        ):
            raise ValueError(
                "Ready visual assessment cannot contain weak or redundant slides"
            )
        manifest_name = (
            "visual_preview_manifest.json" if qa_preview else "visual_manifest.json"
        )
        manifest = load_json(root / manifest_name)
        documents = [
            (row["path"], row["layout_validation"]["page_count"])
            for row in manifest["outputs"]
            if row.get("kind") == "client_circular_pdf"
        ]
        assessed_documents = [
            (row["path"], row["assessed_page_count"])
            for row in assessment["document_assessments"]
        ]
        if assessed_documents != documents:
            raise ValueError(
                "Visual assessment must cover every rendered document page once and in order"
            )
        if assessment["verdict"] == "ready" and any(
            row["verdict"] != "ready" for row in assessment["document_assessments"]
        ):
            raise ValueError(
                "Ready visual assessment cannot contain a non-ready document"
            )
        record: dict[str, Any] = {
            "schema_version": 1,
            "workflow": "comunicazione-professionale",
            "run_id": workbench["run_id"],
            "assessment": assessment,
            "model_provenance": {
                "provider": provider,
                "model": model,
                "template_version": protocol["assessment_template_version"],
                "template_sha256": template_digest,
                "assessor_session_id": protocol["assessor_session_id"],
                "execution_mode": "isolated_host_session_attestation",
                "provider_authenticated": False,
            },
            "recorded_at": utc_now(),
        }
        record["record_digest"] = canonical_digest(record)
        output = root / (
            "visual_preview_assessment_record.json"
            if qa_preview
            else "visual_assessment_record.json"
        )
        if output.exists():
            raise ValueError(
                "Visual assessment already exists; supersede the contribution for a new exact render"
            )
        return atomic_write_json(output, record)


def main(argv: list[str] | None = None) -> int:
    """Record one exact-render visual assessment."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--qa-preview", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = record_visual_assessment(
            args.run_dir,
            args.assessment,
            provider=args.provider,
            model=args.model,
            qa_preview=args.qa_preview,
        )
    except (OSError, ValueError) as exc:
        LOGGER.error("VISUAL_ASSESSMENT_RECORD_FAILED: %s", exc)
        return 1
    LOGGER.info("Recorded visual assessment: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
