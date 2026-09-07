#!/usr/bin/env python3
"""Validate one packaged professional-communication run mechanically."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from PIL import Image
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from workflow_core import (
    atomic_write_json,
    canonical_digest,
    file_digest,
    fresh_package_review_decision,
    load_json,
    package_digest,
    recompute_contribution_digest,
    require_accepted_package_review,
    require_accepted_render_review,
    require_accepted_reviews,
    utc_now,
    validate_input_integrity,
    verify_package_manifest,
    verify_visual_manifest,
    workflow_lock,
)

__all__ = ["validate_run", "main"]

LOGGER = logging.getLogger(__name__)


def validate_run(run_dir: Path) -> list[str]:
    """Validate exact current bytes and finalize only after every check succeeds."""

    root = run_dir.resolve()
    with workflow_lock(root):
        return _validate_run_locked(root)


def _validate_run_locked(root: Path) -> list[str]:
    """Validate and finalize while the run writer lock prevents state races."""

    errors: list[str] = []
    decisions: dict[str, dict[str, object]] = {}
    try:
        source_register = load_json(root / "source_register.json")
        workbench = load_json(root / "content_workbench.json")
        final = load_json(root / "final_artifacts.json")
    except (OSError, ValueError) as exc:
        return [str(exc)]

    try:
        input_digest = validate_input_integrity(root)
    except (OSError, ValueError) as exc:
        input_digest = ""
        errors.append(str(exc))
    try:
        contribution_digest = recompute_contribution_digest(root)
    except (OSError, ValueError) as exc:
        contribution_digest = ""
        errors.append(str(exc))
    try:
        decisions = require_accepted_reviews(root, workbench["required_review_scopes"])
    except ValueError as exc:
        errors.append(str(exc))
    if final.get("input_digest") != input_digest:
        errors.append("final_artifacts.json is stale for the current prepared inputs")
    if final.get("contribution_digest") != contribution_digest:
        errors.append("final_artifacts.json is stale for the current contribution")
    current_package_digest = package_digest(final)
    if final.get("package_digest") != current_package_digest:
        errors.append("final_artifacts.json package digest mismatch")

    needs_render = bool(
        workbench["contribution"]["recommendation"] == "publish"
        and (
            workbench["contribution"]["visual_story"]["slides"]
            or "client_circular"
            in load_json(root / "run_intake.json")["requested_channels"]
        )
    )
    if needs_render:
        try:
            verify_visual_manifest(root)
            require_accepted_render_review(root)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    package_review: dict[str, object] | None = None
    review_binding: dict[str, object] = {}
    try:
        verify_package_manifest(root)
        if workbench["contribution"]["recommendation"] == "no_publish":
            # Exact internal-record checks need no second semantic decision.
            # Publishable packages still require review of their exact bytes.
            allowed = {
                "technical_basis",
                "answer_contract",
                "claim_model_assessment",
                "editorial_model_assessment",
                "no_publication_recommendation",
                "artifact_card",
            }
            outputs = final.get("outputs", [])
            if (
                len(outputs) != len(allowed)
                or {o.get("kind") for o in outputs} != allowed
            ):
                raise ValueError(
                    "No-publication package must contain only its six internal records"
                )
            contribution = workbench["contribution"]
            if contribution["channel_drafts"] or contribution["visual_story"]["slides"]:
                raise ValueError(
                    "No-publication contribution contains communication drafts"
                )
            recommendation = next(
                o for o in outputs if o["kind"] == "no_publication_recommendation"
            )
            text = (root / recommendation["path"]).read_text(encoding="utf-8")
            if (
                text.partition("\n")[2].strip()
                != contribution["recommendation_reason"].strip()
            ):
                raise ValueError(
                    "No-publication record differs from the accepted decision"
                )
            existing = fresh_package_review_decision(root)
            if existing and existing.get("decision") != "accepted":
                raise ValueError(
                    "Explicit packaged-output return or rejection remains unresolved"
                )
            review_binding = {
                "review_basis": "accepted_no_publication_decision_and_internal_record_validation",
                "semantic_review_event_ids": {
                    scope: event["event_id"] for scope, event in decisions.items()
                },
            }
        else:
            package_review = require_accepted_package_review(root)
            review_binding = {
                "package_review_event_id": package_review["event_id"],
                "package_review_artifact_digest": package_review["artifact_digest"],
            }
    except (OSError, ValueError) as exc:
        errors.append(str(exc))

    for row in [*source_register["sources"], *source_register["history"]]:
        path = Path(row["snapshot_path"])
        if not path.is_file():
            errors.append(f"Missing input snapshot: {path}")
        elif file_digest(path) != row["sha256"]:
            errors.append(f"Input snapshot hash mismatch: {path}")
    logo = source_register.get("brand_logo")
    if isinstance(logo, dict):
        path = Path(logo["snapshot_path"])
        if not path.is_file() or file_digest(path) != logo["sha256"]:
            errors.append("Brand logo snapshot is missing or changed")

    output_paths: set[str] = set()
    for output in final.get("outputs", []):
        relative = output.get("path")
        if not isinstance(relative, str) or relative in output_paths:
            errors.append(f"Invalid or duplicate output path: {relative}")
            continue
        output_paths.add(relative)
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            errors.append(f"Output escapes run directory: {relative}")
            continue
        if not path.is_file():
            errors.append(f"Missing final output: {relative}")
            continue
        if file_digest(path) != output.get("sha256"):
            errors.append(f"Final output hash mismatch: {relative}")
        if path.stat().st_size != output.get("size_bytes"):
            errors.append(f"Final output size mismatch: {relative}")
        if path.suffix.lower() in {".md", ".txt", ".html"}:
            text = path.read_text(encoding="utf-8")
            for required in output.get("required_text", []):
                if required and required not in text:
                    errors.append(
                        f"Required text missing from {relative}: {required[:80]}"
                    )
        if path.suffix.lower() == ".png":
            with Image.open(path) as image:
                if image.size != (1080, 1350):
                    errors.append(
                        f"Unexpected PNG dimensions for {relative}: {image.size}"
                    )
        if path.suffix.lower() == ".pdf" and path.read_bytes()[:5] != b"%PDF-":
            errors.append(f"Invalid PDF header: {relative}")
        elif path.suffix.lower() == ".pdf":
            try:
                reader = PdfReader(str(path))
                if reader.is_encrypted or not reader.pages:
                    errors.append(f"Unreadable or empty PDF: {relative}")
                elif not any(
                    (page.extract_text() or "").strip() for page in reader.pages
                ):
                    errors.append(f"PDF has no extractable review text: {relative}")
                for page in reader.pages:
                    width = float(page.mediabox.width)
                    height = float(page.mediabox.height)
                    if abs(width - 595.276) > 2 or abs(height - 841.89) > 2:
                        errors.append(
                            f"Unexpected PDF page size for {relative}: "
                            f"{width} x {height}"
                        )
                        break
            except (OSError, ValueError, PdfReadError) as exc:
                errors.append(f"Invalid PDF structure for {relative}: {exc}")

    expected_status = (
        "no_publication_recommended"
        if workbench["contribution"]["recommendation"] == "no_publish"
        else "final_ready"
    )
    if final.get("validation_target_status") != expected_status:
        errors.append(
            f"Unexpected validation target: {final.get('validation_target_status')}"
        )
    if final.get("status") not in {"validation_pending", expected_status}:
        errors.append(f"Unexpected final status: {final.get('status')}")
    receipt = final.get("validation_receipt")
    if final.get("status") == expected_status:
        if not isinstance(receipt, dict):
            errors.append("Finalized package has no validation receipt")
        else:
            receipt_body = {
                key: value for key, value in receipt.items() if key != "receipt_digest"
            }
            if canonical_digest(receipt_body) != receipt.get("receipt_digest"):
                errors.append("Validation receipt digest mismatch")
            if receipt.get("package_digest") != current_package_digest:
                errors.append("Validation receipt is stale for the current package")
            if receipt.get("input_digest") != input_digest:
                errors.append("Validation receipt is stale for current inputs")
            if receipt.get("contribution_digest") != contribution_digest:
                errors.append("Validation receipt is stale for current contribution")
            if any(receipt.get(key) != value for key, value in review_binding.items()):
                errors.append("Validation receipt is stale for packaged-output review")
    if not errors and final.get("status") == "validation_pending":
        receipt_body = {
            "schema_version": 1,
            "validator": "professional_communication_validator_v2",
            "input_digest": input_digest,
            "contribution_digest": contribution_digest,
            "package_digest": current_package_digest,
            **review_binding,
            "validated_at": utc_now(),
        }
        final["validation_receipt"] = {
            **receipt_body,
            "receipt_digest": canonical_digest(receipt_body),
        }
        final["status"] = expected_status
        atomic_write_json(root / "final_artifacts.json", final)
    return errors


def main(argv: list[str] | None = None) -> int:
    """Validate one run and report every mechanical defect."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    errors = validate_run(args.run_dir)
    if errors:
        for error in errors:
            LOGGER.error("VALIDATION_ERROR: %s", error)
        return 1
    LOGGER.info("OK: professional communication run is mechanically valid")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
