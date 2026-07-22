from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from new_client_core import (  # noqa: E402
    AML_A_FACTOR_IDS,
    AML_B_FACTOR_IDS,
    AML_TRIGGER_IDS,
    SCHEMA_VERSION,
    SCREENING_TYPES,
    SUPPORTED_JURISDICTIONS,
    SUPPORTED_LANGUAGES,
    ValidationError,
    ensure_private_output_directory,
    validate_new_client_input,
    write_private_json,
)

__all__ = ["build_parser", "build_template", "initialize_case", "main"]


def _factor(factor_id: str) -> dict[str, Any]:
    return {
        "factor_id": factor_id,
        "score": 1,
        "assessment_status": "proposed",
        "basis": "Initial placeholder; assess and document the professional basis.",
        "evidence_ids": [],
    }


def _identity_document() -> dict[str, Any]:
    return {
        "verification_status": "unknown",
        "document_type": None,
        "document_number": None,
        "issuer": None,
        "issued_on": None,
        "expires_on": None,
        "verified_on": None,
        "verification_method": None,
        "evidence_ids": [],
    }


def build_template(
    client_reference: str,
    *,
    client_type: str,
    engagement_kind: str,
    assessment_date: str,
    jurisdiction: str = "IT",
    language: str = "it",
) -> dict[str, Any]:
    """Build a valid intake template whose unresolved decisions remain explicit."""

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "jurisdiction": jurisdiction,
        "language": language,
        "processing_authority": {
            "status": "pending",
            "scope": "new_client_professional_setup",
            "runtime": "local_codex_workspace",
            "minimization": "structured_facts_and_selected_excerpts",
            "external_transfer_authorized": False,
            "authorized_by": None,
            "authorized_by_role": None,
            "authorized_at": None,
        },
        "client_file_preparation_binding": {
            "mode": "standalone_evidence",
            "reason": (
                "No reviewed Client File Preparation run is bound; evidence is recorded "
                "directly for this new-client case."
            ),
            "evidence_ids": [],
        },
        "client_reference": client_reference,
        "client_type": client_type,
        "tax_facts": {
            "codice_fiscale": {
                "value": None,
                "verification_status": "unknown",
                "evidence_ids": [],
            },
            "partita_iva": {
                "value": None,
                "verification_status": "unknown",
                "evidence_ids": [],
            },
        },
        "party_facts": [
            {
                "fact_id": "party-fact-01",
                "fact_code": "registered_identity",
                "value": None,
                "verification_status": "unknown",
                "evidence_ids": [],
            }
        ],
        "party_identity_document": _identity_document(),
        "representatives": [],
        "representative_posture": {
            "status": "pending",
            "executor_reference": None,
            "basis": "Confirm whether a representative or executor is required.",
            "evidence_ids": [],
            "confirmed_by_role": None,
            "confirmed_at": None,
        },
        "beneficial_owners": [],
        "ownership_status": {
            "status": "pending",
            "basis": "Confirm the beneficial-ownership posture for this client.",
            "evidence_ids": [],
            "confirmed_by_role": None,
            "confirmed_at": None,
        },
        "screening_results": [
            {
                "screening_id": f"screening-{screening_type}",
                "subject_reference": client_reference,
                "screening_type": screening_type,
                "source_reference": None,
                "checked_at": None,
                "outcome": "unknown",
                "review_status": "proposed",
                "evidence_ids": [],
                "professional_resolution": {
                    "status": "unresolved",
                    "relationship_decision": None,
                    "basis": "Professional screening resolution required.",
                    "confirmed_by_role": None,
                    "confirmed_at": None,
                    "evidence_ids": [],
                },
            }
            for screening_type in SCREENING_TYPES
        ],
        "engagement": {
            "kind": engagement_kind,
            "start_date": assessment_date,
            "services": [
                {
                    "service_id": "service-01",
                    "description": "Describe the proposed professional service.",
                    "assessment_status": "proposed",
                }
            ],
            "terms": {
                "review_status": "incomplete",
                "duration_months": None,
                "notice_days": None,
                "advance_amount": None,
                "currency": "EUR",
                "payment_terms": None,
                "indexation_basis": None,
                "insurance_reference": None,
            },
        },
        "privacy_processing_decisions": [
            {
                "decision_id": "privacy-processing-01",
                "purpose": "Define the professional-service processing purpose.",
                "role": "undetermined",
                "controller_legal_basis": None,
                "processor_authority_reference": None,
                "retention": {
                    "status": "undetermined",
                    "period_or_criteria": None,
                },
                "source_ids": ["gdpr_regulation", "cndcec_privacy_guide_2025"],
                "review_status": "proposed",
                "confirmed_by_role": None,
                "confirmed_at": None,
            }
        ],
        "marketing_consent": {
            "scope": "marketing_only",
            "request_status": "not_requested",
            "choice": None,
            "purposes": [],
            "channels": [],
            "requested_at": None,
            "recorded_at": None,
            "withdrawn_at": None,
            "evidence_ids": [],
            "review_status": "not_required",
            "confirmed_by_role": None,
            "confirmed_at": None,
        },
        "evidence_register": [],
        "applicability": [
            {
                "topic": "mandate",
                "applicability_status": "unclear",
                "review_status": "proposed",
                "basis": "Professional applicability review required.",
                "source_ids": [],
                "case_fact_ids": ["party-fact-01"],
            },
            {
                "topic": "privacy_notice",
                "applicability_status": "unclear",
                "review_status": "proposed",
                "basis": "Professional applicability review required.",
                "source_ids": ["gdpr_regulation", "cndcec_privacy_guide_2025"],
                "case_fact_ids": ["party-fact-01"],
            },
            {
                "topic": "ai_transparency_notice",
                "applicability_status": "unclear",
                "review_status": "proposed",
                "basis": "Professional applicability review required.",
                "source_ids": ["italian_law_132_2025_article_13"],
                "case_fact_ids": ["party-fact-01"],
            },
            {
                "topic": "article_28_terms",
                "applicability_status": "unclear",
                "review_status": "proposed",
                "basis": "Controller/processor role analysis required.",
                "source_ids": ["gdpr_regulation", "cndcec_privacy_guide_2025"],
                "case_fact_ids": ["party-fact-01"],
            },
            {
                "topic": "aml_assessment",
                "applicability_status": "unclear",
                "review_status": "proposed",
                "basis": "Professional AML scope and applicability review required.",
                "source_ids": [
                    "d_lgs_231_2007",
                    "cndcec_regole_tecniche_2025",
                    "cndcec_indicazioni_operative_2026",
                ],
                "case_fact_ids": ["party-fact-01"],
            },
        ],
        "template_references": [],
        "aml": {
            "assessment_date": assessment_date,
            "inherent_risk": 1,
            "inherent_risk_status": "proposed",
            "section_b_mode": "full",
            "section_b_exclusion_confirmation": None,
            "factors_a": [_factor(factor_id) for factor_id in AML_A_FACTOR_IDS],
            "factors_b": [_factor(factor_id) for factor_id in AML_B_FACTOR_IDS],
            "mandatory_enhanced_triggers": [
                {
                    "trigger_id": trigger_id,
                    "status": "unknown",
                    "review_status": "proposed",
                    "basis": "Professional finding required.",
                    "evidence_ids": [],
                }
                for trigger_id in AML_TRIGGER_IDS
            ],
            "table_1_assessment": {
                "status": "unknown",
                "review_status": "proposed",
                "basis": "Professional Table 1 applicability assessment required.",
                "confirmed_by_role": None,
                "confirmed_at": None,
            },
            "current_verification_mode": None,
            "enhanced_review_interval_months": None,
        },
    }
    return validate_new_client_input(payload)


def initialize_case(
    case_dir: Path,
    *,
    client_reference: str,
    client_type: str = "company",
    engagement_kind: str = "ongoing",
    assessment_date: str | None = None,
    jurisdiction: str = "IT",
    language: str = "it",
    overwrite: bool = False,
) -> Path:
    """Create an owner-only editable new-client input outside the repository."""

    resolved_dir = ensure_private_output_directory(case_dir)
    target = resolved_dir / "new_client_input.json"
    if target.exists() and not overwrite:
        raise ValidationError(
            f"{target} already exists; pass --overwrite to replace this intake file."
        )
    date_value = assessment_date or datetime.now(timezone.utc).date().isoformat()
    payload = build_template(
        client_reference,
        client_type=client_type,
        engagement_kind=engagement_kind,
        assessment_date=date_value,
        jurisdiction=jurisdiction,
        language=language,
    )
    return write_private_json(target, payload)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(
        description="Initialize a private Vera new-client case intake."
    )
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
    parser.add_argument("--language", choices=SUPPORTED_LANGUAGES, default="it")
    parser.add_argument("--jurisdiction", choices=SUPPORTED_JURISDICTIONS, default="IT")
    parser.add_argument("--assessment-date")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the initialization command."""

    args = build_parser().parse_args(argv)
    try:
        path = initialize_case(
            args.case_dir,
            client_reference=args.client_reference,
            client_type=args.client_type,
            engagement_kind=args.engagement_kind,
            assessment_date=args.assessment_date,
            jurisdiction=args.jurisdiction,
            language=args.language,
            overwrite=args.overwrite,
        )
    except ValidationError as exc:
        sys.stdout.write(json.dumps({"status": "error", "error": str(exc)}) + "\n")
        return 2
    sys.stdout.write(
        json.dumps(
            {
                "status": "new_client_input_initialized",
                "path": path.as_posix(),
                "file_mode": "0600",
                "directory_mode": "0700",
            }
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
