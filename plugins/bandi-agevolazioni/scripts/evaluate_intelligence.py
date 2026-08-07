#!/usr/bin/env python3
"""Run offline contract evaluations for Bandi intelligence contributions.

This harness measures structural safety, reference closure, normalization, and
expected recommendation families. It does not claim to measure legal accuracy;
live-model semantic evaluation requires reviewed, licensed case material.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from intelligence_contract import (
    build_intelligence_packet,
    validate_intelligence_output,
)

__all__ = ["evaluate_cases", "main"]

LOGGER = logging.getLogger(__name__)


def _synthetic_state() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    excerpt = "Synthetic clause for contract evaluation only."
    intake = {
        "reference_date": "2026-08-07",
        "application": {
            "title": "Synthetic call",
            "issuing_authority": "Synthetic authority",
            "procedure_id": "SYNTH-001",
            "submission_deadline": None,
            "status": "confirmed",
        },
        "project": {
            "title": "Synthetic project",
            "summary": "No reusable eligibility meaning.",
            "requested_amount": "100.00",
            "currency": "EUR",
            "confirmation_status": "confirmed",
        },
        "professional_question": "What requires professional review?",
    }
    sources = {
        "source_set_revision": 1,
        "sources": [
            {
                "source_id": "SRC-SYNTH-001",
                "source_type": "call",
                "title": "Synthetic call",
                "issuer": "Synthetic authority",
                "authority_role": "primary",
                "publication_date": "2026-07-01",
                "effective_from": "2026-07-01",
                "effective_to": None,
                "sha256": "0" * 64,
                "review_status": "reviewed",
                "relationships": [],
            }
        ],
    }
    workbench = {
        "requirements": [
            {
                "requirement_id": "REQ-SYNTH-001",
                "category": "eligibility",
                "statement": "Synthetic requirement with no legal reuse.",
                "source_refs": [
                    {
                        "source_id": "SRC-SYNTH-001",
                        "locator": "synthetic locator",
                        "excerpt": excerpt,
                        "excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
                    }
                ],
                "applicability": "Professional review required.",
                "expected_evidence": ["Synthetic evidence"],
                "review_status": "confirmed",
            }
        ],
        "facts": [],
        "assessments": [],
        "document_checklist": [],
        "expenses": [],
        "form_fields": [],
        "narratives": [],
        "consistency_checks": [],
        "issues": [],
        "authority_simulation": {
            "status": "not_run",
            "reviewer_perspective": "",
            "overall_outcome": "not_run",
            "checks": [],
        },
        "dossier": {"disposition": "review_required"},
    }
    return intake, sources, workbench


def evaluate_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate deterministic public contracts against representative fixtures."""

    intake, sources, workbench = _synthetic_state()
    results: list[dict[str, Any]] = []
    for case in cases:
        packet = build_intelligence_packet(
            intake,
            sources,
            workbench,
            case["task"],
            case.get("subject_ids", []),
        )
        normalized: dict[str, Any] | None = None
        error: str | None = None
        try:
            normalized = validate_intelligence_output(packet, case["output"])
        except ValueError as exc:
            error = str(exc)
        valid = normalized is not None
        expected_valid = bool(case["expected_valid"])
        collections = {
            item.get("target_collection")
            for item in (normalized or {}).get("recommendations", [])
            if item.get("target_collection") is not None
        }
        risk_flags = {
            flag
            for item in (normalized or {}).get("recommendations", [])
            for flag in item.get("risk_flags", [])
        }
        expected_collections = set(case.get("expected_collections", []))
        expected_risks = set(case.get("expected_risk_flags", []))
        passed = (
            valid == expected_valid
            and (not valid or expected_collections <= collections)
            and (not valid or expected_risks <= risk_flags)
            and (
                not valid
                or all(
                    item.get("status") == "MODEL_SUGGESTED"
                    and item.get("requires_review") is True
                    for item in normalized.get("recommendations", [])
                )
            )
        )
        results.append(
            {
                "case_id": case["case_id"],
                "passed": passed,
                "contract_valid": valid,
                "expected_valid": expected_valid,
                "error": error,
            }
        )
    passed_count = sum(item["passed"] for item in results)
    return {
        "schema_version": "1.0",
        "scope": "offline_contract_not_legal_accuracy",
        "case_count": len(results),
        "passed_count": passed_count,
        "pass_rate": passed_count / len(results) if results else 0.0,
        "status": "passed" if passed_count == len(results) and results else "failed",
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path)
    args = parser.parse_args(argv)
    payload = json.loads(args.cases.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("evaluation input must be a JSON array")
    report = evaluate_cases(payload)
    LOGGER.info("%s", json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
