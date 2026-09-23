"""Exercise first-use question inputs through the current planning stage.

The contract/review fixtures are authored test inputs, never learner decisions.
Answer generation and validation require separate native execution evidence.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import fitz
import pytest

from tests.plugins._teaching_release import prepared_kit, record_native_check
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
@prepared_kit("vera/quesito-legale-fiscale", "lucia/quesito-legale-fiscale")
def test_question_kit_preserves_request_and_scope_in_native_planning(
    tmp_path, monkeypatch, product, language, phase
):
    _execute_planning(tmp_path, monkeypatch, product, language, phase)


def _execute_planning(tmp_path, monkeypatch, product, language, phase, prior=None):
    if prior is None:
        run = _bound_case(
            tmp_path,
            monkeypatch,
            "quesito-legale-fiscale",
            "prompt-optimizer",
            phase,
            product=product,
            language=language,
        )
    else:
        import importlib.util

        from courseware.library import CourseLibrary

        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location(
            "question_practice_ledger",
            root / "plugins/studio-archive/scripts/client_ledger.py",
        )
        ledger = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ledger)
        context = prior["context"]
        case = tmp_path / "case"
        kit = CourseLibrary(
            root / "plugins" / product, {"quesito-legale-fiscale"}
        ).render("quesito-legale-fiscale", language, tmp_path / "practice-kit")
        imported = [
            ledger.import_document(
                case, context["client_id"], context["engagement_id"], Path(p), "source"
            )
            for p in kit["practice_files"]
        ]
        version = _read(root / "plugins" / product / ".codex-plugin/plugin.json")[
            "version"
        ]
        prepared = ledger.prepare_run(
            case,
            context["client_id"],
            context["engagement_id"],
            "prompt-optimizer",
            version,
            input_ids=[v["receipt"]["input_id"] for v in imported],
            purpose="Revise the fictional briefing while preserving its first version",
        )
        run = ledger.start_run(
            case, context["engagement_id"], prepared["run"]["run_id"]
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
    return run


@pytest.mark.parametrize("product", ["vera", "lucia"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
@pytest.mark.parametrize("language", LANGUAGES)
def test_question_kit_exports_actual_reviewed_answer(
    tmp_path, monkeypatch, record_property, product, phase, language
):
    """Complete the planning-to-validation handoff with real local packaging.

    All supported languages follow the same actual inspection and packaging pipeline.
    This regression does not establish learner or professional approval.
    """
    prior = None
    preserved = {}
    if phase == "practice":
        prior = _execute_answer(tmp_path, monkeypatch, product, "demo", language)
        preserved = {
            p: p.read_bytes()
            for p in (tmp_path / "case").rglob("runs/*/**/*")
            if p.is_file()
        }
        assert preserved
    run = _execute_answer(tmp_path, monkeypatch, product, phase, language, prior)
    if prior:
        assert run["context"]["engagement_id"] == prior["context"]["engagement_id"]
        assert run["context"]["run_id"] != prior["context"]["run_id"]
        assert all(p.read_bytes() == content for p, content in preserved.items())
    record_native_check(
        record_property,
        root=Path(__file__).resolve().parents[2],
        product=product,
        workflow="quesito-legale-fiscale",
        language=language,
        phase=phase,
    )


def _execute_answer(tmp_path, monkeypatch, product, phase, language, prior=None):
    from tests.plugins._question_teaching import answer, review

    planning = _execute_planning(tmp_path, monkeypatch, product, language, phase, prior)
    import importlib.util

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "question_delivery_ledger",
        root / "plugins/studio-archive/scripts/client_ledger.py",
    )
    ledger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger)
    context = planning["context"]
    case = tmp_path / "case"
    document, _ = answer(language, phase)
    draft = tmp_path / f"{phase}-authored-answer.md"
    draft.write_text(document, encoding="utf-8")
    source = next(
        Path(v["path"])
        for v in context["input_bindings"]
        if v["path"].endswith("directive-original-es.pdf")
    )
    imported = [
        ledger.import_document(
            case, context["client_id"], context["engagement_id"], p, "source"
        )
        for p in (
            draft,
            source,
            root / "tests/fixtures/teaching_question/legislative-status-2026-09-23.md",
        )
    ]
    version = _read(root / "plugins" / product / ".codex-plugin/plugin.json")["version"]
    prepared = ledger.prepare_run(
        case,
        context["client_id"],
        context["engagement_id"],
        "deep-research-validator",
        version,
        input_ids=[v["receipt"]["input_id"] for v in imported],
        purpose="Actual fictional answer validation; no learner approval",
    )
    run = ledger.start_run(case, context["engagement_id"], prepared["run"]["run_id"])
    output = Path(run["output_dir"])
    bindings = run["context"]["input_bindings"]
    answer_path = next(
        Path(v["path"]) for v in bindings if v["path"].endswith("authored-answer.md")
    )
    source_path = next(Path(v["path"]) for v in bindings if v["path"].endswith(".pdf"))
    status_path = next(
        Path(v["path"])
        for v in bindings
        if v["path"].endswith("legislative-status-2026-09-23.md")
    )
    common = ["--client-engagement", run["context_path"], "--output-dir", output]
    _run(
        "plugins/deep-research-validator/scripts/inspect_document.py",
        answer_path,
        *common,
    )
    _run(
        "plugins/deep-research-validator/scripts/inspect_sources.py",
        output / "document_inventory.json",
        *common,
        "--source-file",
        source_path,
        "--source-file",
        status_path,
        "--no-fetch",
    )
    inventory = _read(output / "source_inventory.json")
    official = next(
        s
        for s in inventory["sources"]
        if s.get("kind") == "file" and s.get("status") == "available"
    )
    _write(
        output / "claims_review_draft.json",
        review(
            language,
            phase,
            official["source_id"],
            next(
                s["source_id"]
                for s in inventory["sources"]
                if s.get("kind") == "file" and "legislative-status" in str(s)
            ),
        ),
    )
    _write(output / "answer_contract.json", _contract(language, phase))
    _run(
        "plugins/deep-research-validator/scripts/package_validation.py",
        output / "document_inventory.json",
        output / "source_inventory.json",
        output / "claims_review_draft.json",
        *common,
        "--answer-contract-file",
        output / "answer_contract.json",
        "--docx",
    )
    audit = _read(output / "validation_audit.json")
    assert audit["status"] == "record_complete", audit
    assert (output / "validated_document.docx").is_file()
    assert (output / "validated_document.md").read_text() == document
    assert len(_read(output / "claims_review.json")["claims"]) == (
        6 if phase == "practice" else 5
    )
    assert _read(output / "ui_decisions.json")["status"] == "pending_review"
    _complete_teaching_case(run, case)
    return run
