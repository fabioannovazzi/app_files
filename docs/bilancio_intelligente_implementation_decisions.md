# Bilancio intelligente — implementation decisions

Status: fixed product decision supplement to
`vera-xbrl-implementation-spec.md` (version 1.0, 5 August 2026).

## Product thesis

The existing bilancio process remains the professional process. Vera makes its
execution intelligent.

The product is not XBRL generation, rare-event detection, or a chatbot added to
accounts-production software. The product is a complete, reviewable bilancio in
which Vera participates across source understanding, classification,
ambiguity, evidence requests, prior-year reuse, schedules, disclosures,
narrative preparation, inconsistency resolution, and professional review.

XBRL remains a required deterministic output adapter. It is necessary plumbing,
not the product identity.

## Interpretation of the original delivery phases

The specification sequences the deterministic accounting core before
model-assisted behavior. That sequencing is retained as an engineering
dependency: exact arithmetic, statutory rules, provenance, validation, and XML
construction must exist before semantic assistance can safely act through the
whole workflow.

It must not be interpreted as a conventional product followed by an optional
“Applied AI” feature. The end-state workflow is intelligent throughout. Each
stage must expose a semantic participation contract and a professional review
boundary:

| Existing stage | Intelligent participation | Authoritative boundary |
| --- | --- | --- |
| Intake | Explain the source interpretation, limitations, and next missing input | Parser and source anchors remain deterministic |
| Mapping | Propose meaning, alternatives, ambiguity, and required evidence | User applies the mapping or split |
| Form analysis | Explain consequences and unresolved decision fields | Effective-dated rule engine determines eligibility; user selects |
| Statements | Explain unusual movements and attention areas | Decimal aggregation and reconciliation determine amounts |
| Schedules | Identify likely evidence and unresolved movement meaning | Explicit source-backed schedule equations determine closure |
| Questionnaire | Prioritize relevant open questions and explain why they matter | Rule pack activates requirements; accepted answers remain user decisions |
| Notes | Draft fluent Italian from accepted facts and compare prior text | Sentence-level provenance and reviewer acceptance control factual text |
| Validation | Explain issues and possible resolution evidence | Validation result and non-overridable blockers remain deterministic |
| Review | Direct attention to consequential decisions and residual uncertainty | Reviewer declaration creates the immutable approval snapshot |
| Export | Explain artifacts and filing boundary | Approved canonical snapshot deterministically renders XBRL |

## Canonical architecture

```text
evidence + reviewed client history
→ task-specific intelligent participation
→ professional decisions and accepted canonical facts
→ deterministic calculations, rules, reconciliations, and validation
→ checksum-bound XBRL render and local processor review
→ immutable professional approval
→ XBRL, preview, workpaper, and other output adapters
```

No model suggestion becomes an accepted fact, changes a workflow gate, approves
the accounts, calculates authoritative totals, or constructs final XML. Model
context is minimum-necessary and document content is untrusted.

## Definition of implementation quality

The thesis is a product decision, not an experiment deciding whether Vera
should pursue intelligent accounts preparation. Evaluation determines whether
the implementation performs the thesis well:

- usefulness and explanation quality of mapping proposals;
- recall of ambiguity and missing evidence;
- relevance and economy of questions;
- safe reuse of prior decisions and text;
- factual fidelity of narrative drafts;
- quality of issue explanations and next-action guidance;
- reduction of repeated decisions and manual investigation;
- accounting, statutory, security, and XBRL correctness;
- preservation of professional judgement and approval authority.

The stable internal module identifier remains `bilancio-xbrl-it` for packaging
and compatibility. The user-facing product name is **Bilancio intelligente**.
