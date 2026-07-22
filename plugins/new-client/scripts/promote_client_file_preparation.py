from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from initialize_case import build_template  # noqa: E402
from new_client_core import (  # noqa: E402
    SUPPORTED_JURISDICTIONS,
    SUPPORTED_LANGUAGES,
    ValidationError,
    ensure_private_output_directory,
    load_json,
    sha256_file,
    validate_new_client_input,
    verify_client_file_preparation_binding,
    write_private_json,
)

__all__ = ["build_parser", "main", "promote_client_file_preparation"]


def _reviewed_fiscal_items(
    review_payload: Mapping[str, Any], applied_decisions: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Return accepted/edited fiscal fields only; never promote raw proposals."""

    items = {
        item.get("id"): item
        for item in review_payload.get("items", [])
        if isinstance(item, dict)
        and item.get("item_type") == "extracted_fiscal_field"
        and isinstance(item.get("id"), str)
    }
    promoted: list[dict[str, Any]] = []
    for effect in applied_decisions.get("effects", []):
        if not isinstance(effect, dict) or effect.get("action") not in {
            "accept",
            "edit",
        }:
            continue
        item = items.get(effect.get("item_id"))
        if not isinstance(item, dict):
            continue
        data = item.get("data")
        if not isinstance(data, dict):
            continue
        value = effect.get("edit_value") if effect.get("action") == "edit" else None
        if not isinstance(value, str) or not value.strip():
            value = data.get("normalized_value") or data.get("value")
        if not isinstance(value, str) or not value.strip():
            continue
        field_code = data.get("field_code")
        if not isinstance(field_code, str) or not field_code.strip():
            continue
        promoted.append(
            {
                "item_id": effect["item_id"],
                "field_code": field_code.strip(),
                "value": value.strip(),
                "document_kind": str(data.get("document_kind") or "unknown"),
                "confidence": str(data.get("confidence") or "unknown"),
                "source_relative_path": str(
                    data.get("relative_path") or item.get("source_path") or ""
                ),
                "review_action": effect["action"],
            }
        )
    return promoted


def _promote_reviewed_facts(
    intake: dict[str, Any],
    *,
    verified_outputs: Sequence[Mapping[str, Any]],
) -> list[str]:
    outputs_by_path = {record["path"]: record for record in verified_outputs}
    review_record = outputs_by_path.get("review_payload.json")
    applied_record = outputs_by_path.get("applied_decisions.json")
    if review_record is None or applied_record is None:
        raise ValidationError(
            "The final-ready phase-one package lacks reviewed promotion inputs."
        )
    review_payload = load_json(Path(str(review_record["resolved_path"])))
    applied_decisions = load_json(Path(str(applied_record["resolved_path"])))
    if review_payload.get("run_id") != applied_decisions.get("run_id"):
        raise ValidationError(
            "Phase-one review payload and applied decisions use different run IDs."
        )
    promoted = _reviewed_fiscal_items(review_payload, applied_decisions)
    unambiguous_tax_code_values = {
        record["value"]
        for record in promoted
        if record["field_code"].casefold().startswith("codice_fiscale_")
        and "partita_iva" not in record["field_code"].casefold()
    }
    if len(unambiguous_tax_code_values) != 1:
        return []

    evidence_id = "phase1-reviewed-decisions"
    applied_path = Path(str(applied_record["resolved_path"]))
    intake["evidence_register"].append(
        {
            "evidence_id": evidence_id,
            "evidence_type": "reviewed_client_file_preparation_decisions",
            "status": "available",
            "obtained_on": None,
            "expires_on": None,
            "sha256": applied_record["sha256"],
            "local_path": applied_path.as_posix(),
        }
    )
    intake["tax_facts"]["codice_fiscale"] = {
        "value": next(iter(unambiguous_tax_code_values)),
        "verification_status": "reported",
        "evidence_ids": [evidence_id],
    }
    return [evidence_id]


def promote_client_file_preparation(
    final_artifacts_path: Path,
    case_dir: Path,
    *,
    client_reference: str,
    client_type: str = "company",
    engagement_kind: str = "ongoing",
    assessment_date: str | None = None,
    jurisdiction: str | None = None,
    language: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Create a private phase-two starter from a byte-verified final-ready run."""

    manifest_path = final_artifacts_path.expanduser().resolve(strict=True)
    manifest = load_json(manifest_path)
    integrity = manifest.get("integrity")
    if not isinstance(integrity, dict):
        raise ValidationError(
            "Phase-one final_artifacts.json has no integrity envelope."
        )
    package_hash = integrity.get("package_hash")
    if not isinstance(package_hash, str):
        raise ValidationError(
            "Phase-one final_artifacts.json has no integrity.package_hash."
        )
    date_value = assessment_date or datetime.now(timezone.utc).date().isoformat()
    intake = build_template(
        client_reference,
        client_type=client_type,
        engagement_kind=engagement_kind,
        assessment_date=date_value,
        jurisdiction="IT",
        language="it",
    )
    intake["client_file_preparation_binding"] = {
        "mode": "client_file_preparation_run",
        "run_id": manifest.get("run_id"),
        "final_artifacts_path": manifest_path.as_posix(),
        "final_artifacts_sha256": sha256_file(manifest_path),
        "upstream_package_hash": package_hash,
        "promoted_evidence_ids": [],
    }
    validate_new_client_input(intake)
    verification = verify_client_file_preparation_binding(
        intake, base_dir=manifest_path.parent
    )
    if verification.get("final_ready") is not True:
        raise ValidationError(
            "Only a final-ready Client File Preparation run can be promoted."
        )
    outputs_by_path = {
        record["path"]: record for record in verification["verified_outputs"]
    }
    upstream_run_record = outputs_by_path.get("run_intake.json")
    if upstream_run_record is None:
        raise ValidationError("The phase-one package does not contain run_intake.json.")
    upstream_run = load_json(Path(str(upstream_run_record["resolved_path"])))
    upstream_jurisdiction = upstream_run.get("jurisdiction")
    if upstream_jurisdiction == "mixed":
        raise ValidationError(
            "A mixed-jurisdiction file-preparation run cannot be promoted until "
            "the professional isolates an Italy-only run."
        )
    if upstream_jurisdiction != "italy":
        raise ValidationError(
            "No Vera professional-setup country pack is available for the sealed "
            f"phase-one jurisdiction {upstream_jurisdiction!r}."
        )
    if jurisdiction is not None and jurisdiction != "IT":
        raise ValidationError(
            "The requested professional-setup jurisdiction does not match the "
            "sealed Italy phase-one run."
        )
    upstream_language = upstream_run.get("language")
    if upstream_language not in SUPPORTED_LANGUAGES:
        raise ValidationError(
            "The sealed phase-one run does not declare a supported language."
        )
    if language is not None and language != upstream_language:
        raise ValidationError(
            "The requested language must match the sealed phase-one run language."
        )
    intake = build_template(
        client_reference,
        client_type=client_type,
        engagement_kind=engagement_kind,
        assessment_date=date_value,
        jurisdiction="IT",
        language=str(upstream_language),
    )
    intake["client_file_preparation_binding"] = {
        "mode": "client_file_preparation_run",
        "run_id": manifest.get("run_id"),
        "final_artifacts_path": manifest_path.as_posix(),
        "final_artifacts_sha256": sha256_file(manifest_path),
        "upstream_package_hash": package_hash,
        "promoted_evidence_ids": [],
    }
    promoted_evidence_ids = _promote_reviewed_facts(
        intake,
        verified_outputs=verification["verified_outputs"],
    )
    intake["client_file_preparation_binding"][
        "promoted_evidence_ids"
    ] = promoted_evidence_ids
    validate_new_client_input(intake)
    verification = verify_client_file_preparation_binding(
        intake, base_dir=manifest_path.parent
    )
    if verification.get("package_hash") != package_hash.casefold():
        raise ValidationError("Phase-one package changed during promotion.")

    output_dir = ensure_private_output_directory(
        case_dir,
        allowed_existing=("new_client_input.json",) if overwrite else (),
    )
    target = output_dir / "new_client_input.json"
    if target.exists() and not overwrite:
        raise ValidationError(
            f"{target} already exists; pass --overwrite to replace the starter."
        )
    return write_private_json(target, intake)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Promote a byte-verified final-ready Client File Preparation run into "
            "a private Vera New Client starter."
        )
    )
    parser.add_argument("--final-artifacts", required=True, type=Path)
    parser.add_argument("--case-dir", required=True, type=Path)
    parser.add_argument("--client-reference", required=True)
    parser.add_argument(
        "--client-type",
        choices=("individual", "sole_trader", "company", "entity"),
        default="company",
    )
    parser.add_argument(
        "--engagement-kind", choices=("ongoing", "one_off"), default="ongoing"
    )
    parser.add_argument("--assessment-date")
    parser.add_argument("--jurisdiction", choices=SUPPORTED_JURISDICTIONS)
    parser.add_argument("--language", choices=SUPPORTED_LANGUAGES)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        path = promote_client_file_preparation(
            args.final_artifacts,
            args.case_dir,
            client_reference=args.client_reference,
            client_type=args.client_type,
            engagement_kind=args.engagement_kind,
            assessment_date=args.assessment_date,
            jurisdiction=args.jurisdiction,
            language=args.language,
            overwrite=args.overwrite,
        )
    except (OSError, ValidationError) as exc:
        sys.stdout.write(json.dumps({"status": "error", "error": str(exc)}) + "\n")
        return 2
    sys.stdout.write(
        json.dumps(
            {
                "status": "new_client_input_promoted",
                "path": path.as_posix(),
                "file_mode": "0600",
                "directory_mode": "0700",
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
