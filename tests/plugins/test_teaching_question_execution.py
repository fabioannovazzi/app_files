"""Exercise first-use question inputs through the current planning stage.

The contract/review fixtures are authored test inputs, never learner decisions.
Answer generation and validation require separate native execution evidence.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import fitz
import pytest

from tests.plugins.test_teaching_kit_execution import (
    _bound_case,
    _complete_teaching_case,
    _read,
    _run,
    _write,
)

LANGUAGES = {
    "it": "Italian",
    "en": "English",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
}


def _contract(language, phase):
    purpose = "Explain the common EU framework for business-to-business late payment."
    if phase == "practice":
        purpose += " Compare it with supply to public authorities."
    return {
        "schema_version": "1.0",
        "question_domain": "legal",
        "generation_route": "codex_direct",
        "document_type": "informational briefing of at most two pages",
        "purpose": purpose,
        "audience": "Professional preparing the fictional Imprese Arco meeting",
        "output_language": LANGUAGES[language],
        "jurisdiction_status": "confirmed",
        "jurisdiction": "European Union framework; national implementation excluded",
        "evidence_display": "inline_citations",
        "validation_profile": "source_identity_support_reasoning_and_judgment",
        "validation_scope": "all_material_claims",
        "correction_policy": "correct_when_supported",
        "judgment_policy": "flag_for_professional_review",
        "adversarial_policy": "not_required",
        "adversarial_rationale": (
            "Informational briefing without an individual entitlement or dispute."
        ),
    }


def _prompt(question, contract):
    return f"""You are a legal professional preparing an informational briefing.
Mandatory output language: {contract['output_language']}.
Jurisdiction assumption: {contract['jurisdiction']}. Never infer law from language.
Research lens: posture is planning_ex_ante; objective is balanced;
scope is domestic_plus_EU with national implementation explicitly excluded here.
Assumed output format: {contract['document_type']}.
Purpose: {contract['purpose']}
Audience: {contract['audience']}.
Generation route: codex_direct; ordinary research is selected for this synthetic
integration check only. The actual lesson retains the user's research choice.
Use the supplied official directive and European Commission guidance. Check
current official sources using the separate qualified source-domain list.
Distinguish original publication, current legal status, and national implementation.
Cross-check substantive claims. Do not invent laws, cases, dates or amendments.
Use citations [1], [2] and a final source section with stable official URLs.
Flag unavailable sources, residual uncertainty and professional-review matters.
Ask at most three clarifying questions only if missing facts change the answer.
Structure the briefing with a concise answer, explanations, required documents,
limitations and source notes. Preserve every material fact and question below.
No individual entitlement, interest calculation, or debt-recovery procedure.
Review all material claims for source identity, support, reasoning and judgment.
Correction policy: correct_when_supported; judgment: flag_for_professional_review.
Informational scope: adversarial_policy not_required. Do not invent an opponent.
Original request, unchanged:
{question}
"""


def _review(contract, phase):
    return {
        "schema_version": "1.0",
        "review_method": "model_led_semantic_conformance_review",
        "dimensions": {
            "question_and_material_facts": {
                "status": "conforms",
                "analysis": (
                    "The full fictional request, date and constraints are preserved. "
                    f"The {phase} request remains informational, not a debt claim."
                ),
            },
            "generation_route": {
                "status": "conforms",
                "analysis": "Ordinary research is a test-fixture choice, not a learner preference.",
            },
            "document_type": {
                "status": "conforms",
                "analysis": "The same short briefing and two-page limit are explicit.",
            },
            "purpose": {"status": "conforms", "analysis": contract["purpose"]},
            "audience": {"status": "conforms", "analysis": contract["audience"]},
            "output_language": {
                "status": "conforms",
                "analysis": f"The prompt requires {contract['output_language']} output.",
            },
            "jurisdiction": {
                "status": "conforms",
                "analysis": "The common EU framework is explicit; no national law is inferred.",
            },
            "evidence_display": {
                "status": "conforms",
                "analysis": "Numbered citations and source notes preserve retrievable references.",
            },
            "research_lens": {
                "status": "conforms",
                "analysis": "Preparatory information does not advance a concrete legal position.",
            },
            "validation_policy": {
                "status": "conforms",
                "analysis": "Every material claim requires source, support, reasoning and judgment review.",
            },
            "source_strategy": {
                "status": "conforms",
                "analysis": "Official directive and guidance are distinct; current status needs review.",
            },
        },
        "overall_status": "conforms",
        "reviewer_action": "accept",
    }


@pytest.mark.parametrize("product", ["vera", "lucia"])
@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_question_kit_preserves_request_and_scope_in_native_planning(
    tmp_path, monkeypatch, product, language, phase
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "quesito-legale-fiscale",
        "prompt-optimizer",
        phase,
        product=product,
        language=language,
    )
    output = Path(run["output_dir"])
    inputs = Path(run["context"]["run_root"]) / "inputs"
    question_name = f"{'question' if phase == 'demo' else 'practice'}-{language}.md"
    question_path = next(inputs.rglob(question_name))
    source = next(inputs.rglob("directive-original-es.pdf"))
    provenance = _read(next(inputs.rglob(f"source-provenance-{language}.json")))
    assert (
        hashlib.sha256(source.read_bytes()).hexdigest()
        == provenance["directive_sha256"]
    )
    with fitz.open(source) as pdf:
        assert pdf.page_count == 10
        assert "Artículo 3" in pdf[4].get_text()
    args = ["--client-engagement", run["context_path"], "--output-dir", output]
    _run(
        "plugins/prompt-optimizer/scripts/inspect_question.py",
        question_path,
        *args,
        "--language",
        language,
    )
    contract = _contract(language, phase)
    (output / "draft_prompt.md").write_text(
        _prompt(question_path.read_text(encoding="utf-8"), contract), encoding="utf-8"
    )
    _write(output / "draft_answer_contract.json", contract)
    _write(output / "draft_prompt_contract_review.json", _review(contract, phase))
    (output / "draft_source_domains.txt").write_text(
        "https://eur-lex.europa.eu\nhttps://europa.eu\nhttps://www.boe.es\n",
        encoding="utf-8",
    )
    _run(
        "plugins/prompt-optimizer/scripts/validate_prompt.py",
        question_path,
        output / "draft_prompt.md",
        *args,
        "--language",
        language,
        "--source-domains-file",
        output / "draft_source_domains.txt",
        "--answer-contract-file",
        output / "draft_answer_contract.json",
        "--prompt-contract-review-file",
        output / "draft_prompt_contract_review.json",
    )
    audit = _read(output / "prompt_audit.json")
    assert audit["status"] == "pass", audit["failed_checks"]
    assert audit["missing_fact_anchors"] == []
    assert audit["answer_contract"]["jurisdiction"] == contract["jurisdiction"]
    assert audit["answer_contract"]["output_language"] == LANGUAGES[language]
    assert audit["answer_contract"]["adversarial_policy"] == "not_required"
    assert (output / "optimized_prompt.md").is_file()
    assert (output / "source_domains.txt").read_text().count("https://") == 3
    assert _read(output / "ui_decisions.json")["status"] == "pending_review"
    assert _read(output / "ui_decisions.json")["decision_count"] == 0
    _complete_teaching_case(run, tmp_path / "case")
