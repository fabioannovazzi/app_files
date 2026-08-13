from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_script(module_name: str, script_path: Path):
    sys.path.insert(0, str(script_path.parent))
    try:
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(script_path.parent))


def _answer_contract(generation_route: str, document_type: str) -> dict[str, str]:
    return {
        "schema_version": "1.0",
        "question_domain": "legal",
        "generation_route": generation_route,
        "document_type": document_type,
        "purpose": "Answer the supplied legal question",
        "audience": "Client",
        "output_language": "English",
        "jurisdiction_status": "confirmed",
        "jurisdiction": "Italian law",
        "evidence_display": "inline_citations",
        "validation_profile": "source_identity_support_reasoning_and_judgment",
        "validation_scope": "all_material_claims",
        "correction_policy": "correct_when_supported",
        "judgment_policy": "flag_for_professional_review",
    }


def _prompt_contract_review() -> dict[str, Any]:
    dimensions = {
        dimension: {
            "status": "conforms",
            "analysis": "The prompt semantically conforms to this dimension.",
        }
        for dimension in (
            "question_and_material_facts",
            "generation_route",
            "document_type",
            "purpose",
            "audience",
            "output_language",
            "jurisdiction",
            "evidence_display",
            "research_lens",
            "validation_policy",
            "source_strategy",
        )
    }
    return {
        "schema_version": "1.0",
        "review_method": "model_led_semantic_conformance_review",
        "dimensions": dimensions,
        "overall_status": "conforms",
        "reviewer_action": "accept",
    }


def _claims_review(document_type: str) -> dict[str, Any]:
    return {
        "schema_version": "2.1",
        "language": "en",
        "validation_objective": "question_to_validated_answer",
        "coverage_review": {
            "selection_method": "model_led_materiality_review",
            "scope": "all_material_claims",
            "reviewed_sections": ["Full answer"],
            "omitted_sections": [],
            "limitations": [],
            "analysis": "All material claims were selected semantically.",
            "reviewer_action": "accept",
        },
        "contract_review": {
            "question_answered": {
                "status": "conforms",
                "analysis": "The answer addresses the question.",
            },
            "document_type": {
                "status": "conforms",
                "analysis": f"The answer is a {document_type}.",
            },
            "audience": {
                "status": "conforms",
                "analysis": "The answer is suitable for the client.",
            },
            "evidence_display": {
                "status": "conforms",
                "analysis": "The answer uses the contracted citations.",
            },
            "issues": [
                {
                    "type": "none",
                    "explanation": "No contract defect was identified.",
                    "treatment_action": "none",
                    "treatment_status": "not_needed",
                    "treatment_explanation": "No treatment is required.",
                }
            ],
            "reviewer_action": "accept",
        },
        "claims": [
            {
                "claim_index": 1,
                "claim_text": "Alfa S.r.l. must file the response within 30 days.",
                "claim_location": "Paragraph 1",
                "materiality": "material",
                "source_checks": [
                    {
                        "source_ref": "source-001",
                        "identity_status": "matches_cited_source",
                        "identity_analysis": "This is the authority cited in the answer.",
                        "authority_relation": "official_full_text",
                        "official_text_access": "obtained",
                        "text_fidelity": "verified_against_official_text",
                        "access_analysis": "The official full text was obtained directly.",
                        "limitations": [],
                        "cited_passage": "The response must be filed within 30 days.",
                    }
                ],
                "support": {
                    "status": "supported",
                    "analysis": "The authority establishes the same deadline.",
                },
                "reasoning": {
                    "status": "sound",
                    "analysis": "The deadline follows directly from the rule.",
                    "supported_premises": ["The response deadline is 30 days."],
                    "missing_premises": [],
                },
                "professional_judgment": {
                    "status": "not_judgment_dependent",
                    "analysis": "No discretionary application is needed.",
                    "factors": [],
                    "alternative_interpretations": [],
                },
                "issues": [
                    {
                        "type": "none",
                        "explanation": "No claim defect was identified.",
                        "treatment_action": "none",
                        "treatment_status": "not_needed",
                        "treatment_explanation": "No treatment is required.",
                    }
                ],
                "disposition": {
                    "status": "retain",
                    "analysis": "The claim can be retained.",
                    "revised_claim": "",
                },
                "reviewer_action": "accept",
                "proposed_fix": "",
            }
        ],
        "overall_assessment": {
            "outcome": "no_material_defect_identified",
            "analysis": "No material defect was identified.",
            "residual_uncertainties": [],
            "professional_review_items": [],
        },
        "document_revision": {
            "status": "not_required",
            "summary": "No revision is required.",
            "unresolved_changes": [],
        },
        "validated_document": "Alfa S.r.l. must file the response within 30 days.",
    }


@pytest.mark.parametrize(
    ("generation_route", "document_type"),
    [
        ("codex_direct", "one-page legal letter"),
        ("chatgpt_deep_research", "legal research report"),
    ],
)
def test_question_to_validated_answer_pipeline(
    generation_route: str,
    document_type: str,
) -> None:
    prompt_mod = _load_script(
        f"vera_pipeline_prompt_{generation_route}",
        ROOT / "plugins" / "prompt-optimizer" / "scripts" / "validate_prompt.py",
    )
    validator_mod = _load_script(
        f"vera_pipeline_validator_{generation_route}",
        ROOT
        / "plugins"
        / "deep-research-validator"
        / "scripts"
        / "package_validation.py",
    )
    question = (
        "Under Italian law, when must Alfa S.r.l. answer the demand received in 2026?"
    )
    prompt = f"""
You are an Italian lawyer. Mandatory output language: English.
Legal framework: use Italian law.
Research lens: posture is defensive advice, objective is timely response, scope is Italian law.
Produce a {document_type} for the client.
Preserve Alfa S.r.l. and 2026 and determine the response deadline.
Use official sources, legislation, case law, and stable URLs.
Use citations [1] and a final notes section.
Ask clarifying questions only if essential facts are missing.
Structure the output with analysis and conclusions, and flag uncertainty.
"""
    contract = _answer_contract(generation_route, document_type)

    prompt_audit = prompt_mod.validate_prompt_text(
        question,
        prompt,
        answer_contract=contract,
        prompt_contract_review=_prompt_contract_review(),
        language="en",
    )
    validation_audit = validator_mod.build_audit(
        {"character_count": 64, "urls": []},
        {
            "sources": [
                {
                    "source_id": "source-001",
                    "status": "available",
                    "excerpt": "The response must be filed within 30 days.",
                }
            ]
        },
        _claims_review(document_type),
        contract,
    )

    assert prompt_audit["status"] == "pass"
    assert prompt_audit["answer_contract"]["generation_route"] == generation_route
    assert validation_audit["record_integrity_status"] == "record_complete"
    assert validation_audit["delivery_readiness"] == "reviewed_answer_ready"


def test_semantic_evaluation_corpus_covers_distinct_boundaries() -> None:
    corpus_path = (
        ROOT
        / "plugins"
        / "deep-research-validator"
        / "evals"
        / "semantic_validation_cases.json"
    )

    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    boundaries = {case["boundary"] for case in corpus["cases"]}

    assert corpus["schema_version"] == "1.0"
    assert {
        "semantic_entailment",
        "negation",
        "time_and_modality",
        "qualification_and_missing_premise",
        "source_identity",
        "professional_judgment",
    } <= boundaries
