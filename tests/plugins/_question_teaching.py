"""Reviewed fictional late-payment answer fixtures for full journey regression.

The prose is an authored model contribution, never a shipped lesson answer or
learner approval. The current workflow must inspect, package and export it.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["answer", "review"]

SOURCE_URL = "https://www.boe.es/doue/2011/048/L00001-00010.pdf"
PARAGRAPHS = {
    "en": [
        "EU late-payment framework — Imprese Arco",
        "Fictional meeting briefing. General information, not an assessment of an individual debt. This example explains the supplied Directive 2011/7/EU; national implementation and current amendments must be checked before client use.",
        "The Directive covers payments for commercial transactions supplying goods or services for remuneration between undertakings. Consumer transactions are outside this definition. [1, Articles 1–2]",
        "Interest is due without a reminder when the creditor has fulfilled its contractual and legal obligations and payment is late, unless the debtor is not responsible for the delay. With an agreed payment date, interest starts the following day. Without an agreed term, Article 3 provides a 30-day period, whose starting event depends on receipt of the invoice, goods/services or acceptance. [1, Article 3(1)–(4)]",
        "For business-to-business contracts, the payment period should not exceed 60 calendar days unless a longer period is expressly agreed and is not grossly unfair to the creditor. This is not an unconditional right to insist on 60 days. Statutory interest uses the reference rate plus at least eight percentage points; no rate or interest amount is calculated here. [1, Articles 2(6), 3(5), 7]",
        "When late-payment interest becomes payable, the creditor is entitled to a fixed sum of at least EUR 40 for recovery costs, without a reminder, plus reasonable recovery costs exceeding that sum. Do not apply this rule without checking the underlying conditions and national implementation. [1, Article 6]",
        "Public-authority customers: the general period is 30 days from the applicable event in Article 4(3). Member States may allow up to 60 days for specified public undertakings and recognised public healthcare bodies. An expressly agreed extension must be objectively justified by the contract and cannot exceed 60 days. The business-to-business exception cannot simply be transferred to a public debtor. [1, Article 4(1), (3)–(6)]",
        "Before examining a debt, obtain the contract and amendments, invoice and receipt evidence, delivery or acceptance records, payment history and any dispute correspondence. Identify the debtor, governing national law and relevant dates; for a public customer also check its legal category and any justification for an extended term. These are proposed intake checks, not findings that the fictional association has an enforceable claim.",
        "Limits and next step: no individual entitlement, interest calculation or recovery procedure has been reviewed. The original Spanish official text is the controlling source for this exercise; the Commission guide is explanatory. Check the applicable national implementing law and the current legal version before applying these general rules. A legislative proposal is not an enacted replacement.",
        "Sources",
    ],
}


PARAGRAPHS.update(
    json.loads(
        Path(__file__)
        .with_name("question_teaching_locales.json")
        .read_text(encoding="utf-8")
    )
)

STATUS = {
    "en": "Update check, 23 September 2026: Parliament’s record for proposal 2023/0323(COD) still shows it awaiting the Council’s first-reading position. Do not treat the proposed replacement as enacted law. [2]",
    "it": "Verifica aggiornamenti, 23 settembre 2026: il Parlamento indica ancora la proposta 2023/0323(COD) in attesa della posizione del Consiglio in prima lettura. Non trattare la proposta sostitutiva come legge approvata. [2]",
    "fr": "Vérification au 23 septembre 2026 : le Parlement indique que la proposition 2023/0323(COD) attend encore la position du Conseil en première lecture. Ne la traitez pas comme un remplacement adopté. [2]",
    "de": "Stand der Prüfung am 23. September 2026: Laut Parlament wartet der Vorschlag 2023/0323(COD) auf den Standpunkt des Rates in erster Lesung. Der vorgeschlagene Ersatz ist nicht als verabschiedetes Recht zu behandeln. [2]",
    "es": "Comprobación del 23 de septiembre de 2026: el Parlamento indica que la propuesta 2023/0323(COD) sigue pendiente de la posición del Consejo en primera lectura. No la trates como una norma sustitutiva aprobada. [2]",
}


def answer(language, phase):
    text = PARAGRAPHS[language]
    claims = text[2:6] + ([text[6]] if phase == "practice" else [])
    document = "# " + text[0] + "\n\n" + text[1] + "\n\n"
    document += "\n\n".join(claims + [STATUS[language]] + text[7:9])
    document += (
        "\n\n## "
        + text[9]
        + "\n\n[1] Directive 2011/7/EU, OJ L48, 23 February 2011, pp.1–10. "
        + SOURCE_URL
        + "\n\n[2] European Parliament, procedure 2023/0323(COD), checked 23 September 2026. https://oeil.europarl.europa.eu/oeil/en/procedure-file?reference=2023%2F0323%28COD%29\n"
    )
    return document, claims


def review(language, phase, source_ref, status_ref):
    # Assessments below follow the actual supplied official Spanish PDF, pages5–8.
    # They describe the original directive, not an unverified national entitlement.
    document, claims = answer(language, phase)
    analyses = [
        "Articles 1(2) and 2(1) define remunerated supplies between undertakings or public authorities; no consumer entitlement is inferred.",
        "Article 3(1) preserves performance and debtor-responsibility conditions; 3(3) separates contractual maturity from invoice/delivery/acceptance fallback events. The summary does not flatten these into one invoice-date rule.",
        "Article 3(5) conditions a term above60 days on express agreement and absence of gross unfairness; Article2(6) defines a reference rate plus at least eight percentage points, not eight percent of that rate.",
        "Article6(1) ties the minimum EUR40 to interest becoming payable; paragraphs2–3 cover no reminder and reasonable excess recovery costs. The paragraph preserves those conditions.",
        "Article4 differs from B2B: paragraphs3–4 establish30 days and specified60-day options; paragraph6 permits objectively justified express contractual extension but an absolute60-day cap. It does not assert every public debtor qualifies.",
    ]
    no_issue = [
        {
            "type": "none",
            "explanation": "The bounded description preserves the source conditions.",
            "treatment_action": "none",
            "treatment_status": "not_needed",
            "treatment_explanation": "No correction to this description is needed.",
        }
    ]
    records = []
    for i, claim in enumerate(claims):
        records.append(
            {
                "claim_index": i + 1,
                "claim_text": claim,
                "claim_location": f"Substantive paragraph {i+1}",
                "materiality": "material",
                "source_checks": [
                    {
                        "source_ref": source_ref,
                        "identity_status": "matches_cited_source",
                        "identity_analysis": "The supplied Spanish Official Journal PDF identifies Directive2011/7/EU, OJ L48/1–10; its package SHA is checked before this run.",
                        "authority_relation": "official_full_text",
                        "official_text_access": "obtained",
                        "text_fidelity": "verified_against_official_text",
                        "access_analysis": "Read the supplied BOE-hosted official publication, pages5–8. This is the original text, not national implementing legislation.",
                        "limitations": [
                            "No national implementation or individual entitlement assessed."
                        ],
                        "cited_passage": "",
                    }
                ],
                "support": {"status": "supported", "analysis": analyses[i]},
                "reasoning": {
                    "status": "sound",
                    "analysis": "Describes the stated directive provision conditionally; does not infer a particular client's right.",
                    "supported_premises": [analyses[i]],
                    "missing_premises": [],
                },
                "professional_judgment": {
                    "status": "not_judgment_dependent",
                    "analysis": "The claim is a bounded account of the supplied text. Applying it to a debt is expressly excluded and needs separate professional review.",
                    "factors": [],
                    "alternative_interpretations": [],
                },
                "issues": no_issue,
                "disposition": {
                    "status": "retain",
                    "analysis": "Retain the bounded source description with the explicit application limits.",
                    "revised_claim": "",
                },
                "reviewer_action": "accept",
                "proposed_fix": "",
            }
        )
    import copy

    status_claim = copy.deepcopy(records[0])
    status_claim.update(
        claim_index=len(records) + 1,
        claim_text=STATUS[language],
        claim_location="Dated update check",
    )
    status_claim["source_checks"] = [
        {
            "source_ref": status_ref,
            "identity_status": "matches_cited_source",
            "identity_analysis": "Dated acquisition note identifies the exact official Parliament procedure URL and observed stage.",
            "authority_relation": "official_summary_or_headnote",
            "official_text_access": "obtained",
            "text_fidelity": "corroborated_not_text_verified",
            "access_analysis": "Official live procedure record read through web tool on23 September2026; this regression replays that dated acquisition note, not a fresh web observation.",
            "limitations": [
                "Dated procedural record; recheck during every live lesson."
            ],
            "cited_passage": "Awaiting Council's 1st reading position",
        }
    ]
    status_claim["support"] = {
        "status": "supported",
        "analysis": "The inspected official procedure explicitly reports awaiting Council first reading. It supports the bounded status statement and distinguishing proposal from enactment, not a universal claim that no other amendments exist.",
    }
    status_claim["reasoning"] = {
        "status": "sound",
        "analysis": "Does not convert Parliament first reading into completed legislation.",
        "supported_premises": [
            "The official procedure is pending at the observed date."
        ],
        "missing_premises": [],
    }
    records.append(status_claim)
    return {
        "schema_version": "2.1",
        "language": language,
        "validation_objective": "question_to_validated_answer",
        "coverage_review": {
            "selection_method": "model_led_materiality_review",
            "scope": "all_material_claims",
            "reviewed_sections": [
                "Scope",
                "Interest",
                "Terms",
                "Costs",
                "Public authorities" if phase == "practice" else "B2B",
                "Intake and limitations",
            ],
            "omitted_sections": [],
            "limitations": [
                "Original directive only; current and national law must be checked before use."
            ],
            "analysis": "Read the full briefing. Reviewed each legal proposition; the intake list is a proposed method, not a factual finding.",
            "reviewer_action": "accept",
        },
        "contract_review": {
            **{
                key: {"status": "conforms", "analysis": explanation}
                for key, explanation in {
                    "question_answered": "Covers scope, conditional interest, payment terms and recovery costs; practice additionally contrasts public authorities.",
                    "document_type": "Short informational briefing, with no debt calculation or recovery action.",
                    "audience": "Explains the source rules and proposed document checks for the fictional association meeting.",
                    "evidence_display": "Inline article references map to the supplied official publication.",
                }.items()
            },
            "issues": no_issue,
            "reviewer_action": "accept",
        },
        "claims": records,
        "overall_assessment": {
            "outcome": "no_material_defect_identified",
            "analysis": "Bounded original-text description supported; not a current-law or individual-entitlement certification.",
            "residual_uncertainties": [
                "Current legislative status and applicable national law require a fresh professional check before client use."
            ],
            "professional_review_items": [],
        },
        "document_revision": {
            "status": "not_required",
            "summary": "The limitations are already explicit.",
            "unresolved_changes": [],
        },
        "validated_document": document,
    }
