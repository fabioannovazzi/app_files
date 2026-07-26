# Vera · Concordato Preventivo Review

## Product contract

`concordato-plan-review` means a review of an Italian **concordato
preventivo** case. It does not mean a generic numerical tie-out that happens to
use files from one concordato engagement.

The capability helps a qualified professional organize and review:

- the procedure, proposal, plan, and independent-professional attestation;
- the complete document and creditor perimeters;
- creditor priority, class, treatment, timing, and plan-versus-liquidation
  outcome;
- plan sources and uses;
- continuity or liquidation economics;
- liquidity, distributions, milestones, and sensitivities;
- voting, majorities, objections, and homologation status;
- consistency among the proposal, plan, attestation, accounting evidence, and
  supporting schedules;
- open issues, unsupported assumptions, contradictions, and missing evidence.

It does not issue a legal opinion, attest the plan, authenticate the reviewer,
or decide whether statutory requirements are met.

## Semantic review contract

Codex proposes a structured case model after reading the supplied evidence. A
qualified reviewer confirms or edits it. The reviewed model records:

1. the applicable legal framework and its as-of date;
2. procedure identity, stage, plan type, cut-off, and currency;
3. every supplied document and its semantic role;
4. creditor population status and creditor-level treatment;
5. plan sources and uses;
6. liquidity schedule and plan milestones;
7. review questions and professional assessments;
8. assumptions and issue register;
9. exact evidence references and the reviewer basis for semantic judgments.

The model deliberately allows `unclear`, `missing`, `partial`, and
`not_assessed`. Missing evidence must remain visible; code must not fill gaps
with inferred legal or accounting conclusions.

## Deterministic versus judgment boundary

Deterministic code is used only where correctness is mechanically verifiable:

- file capture, hashes, receipts, and closed output boundaries;
- schema and evidence-reference validation;
- exact decimal arithmetic;
- creditor and class aggregation;
- recovery percentages;
- plan-versus-liquidation differences;
- sources-and-uses totals and funding gap;
- period cash bridges and minimum liquidity;
- exact amount matching as an appendix control;
- reproducible CSV, JSON, XLSX, DOCX, and review-session rendering.

Codex and the qualified reviewer own:

- selection and interpretation of the governing framework;
- document meaning and authoritative versions;
- creditor status, priority, class, voting treatment, and legal relevance;
- whether evidence supports a plan assertion;
- feasibility, sustainability, materiality, and going-concern implications;
- legal, tax, and social-security conclusions;
- issue severity, required follow-up, and final professional conclusions.

Deterministic checks may identify an arithmetic inconsistency or missing
required field. They may not convert that observation into a legal conclusion.

## Workflow

### 1. Inspection

The first run captures the supplied folder, extracts text and numeric
candidates, and writes:

- the source inventory and byte receipts;
- an unreviewed document-perimeter template;
- an unreviewed Concordato Preventivo case-model template;
- the existing numeric-role and amount-disposition template.

Filename cues may be displayed as non-authoritative hints. They cannot make a
source operative.

### 2. Semantic modeling

Codex reads the material, prepares the case model, records evidence locators
and judgment bases, and presents unresolved semantic choices to the reviewer.

The reviewer confirms the model by creating a source-bound semantic decision
receipt. A model is not operative merely because it is valid JSON.

### 3. Mechanical review

With a reviewed model, code produces:

- normalized case model and semantic-check register;
- creditor-level and class-level treatment schedules;
- sources-and-uses schedule;
- liquidity bridge;
- primary Concordato review workbook;
- Concordato review summary;
- numerical tie-out appendix;
- review payload, decisions, assurance envelope, and closed output receipt.

### 4. Professional review

The review surface leads with procedure, creditor treatment, feasibility,
review questions, and issues. Numerical matches remain available as supporting
evidence. Final readiness remains withheld until professional review and any
required approval are recorded.

## Primary output model

The normalized case model uses schema
`concordato.preventivo.case.v1`. Its top-level sections are:

- `legal_framework`
- `procedure`
- `document_perimeter`
- `creditor_population`
- `sources_and_uses`
- `liquidity`
- `milestones`
- `review_questions`
- `assumptions`
- `issues`

Every semantic assessment carries a `judgment_basis`. Evidence references use
captured `source_artifact_ref` values and explicit page, sheet, cell, section,
or paragraph locators.

## Acceptance standard

The capability is not complete until tests demonstrate:

- a direct-continuity case with multiple creditor classes;
- a liquidation case with a liquidation comparator;
- a mixed or indirect-continuity case;
- missing attestation or creditor evidence;
- equal amounts in unrelated contexts;
- sources-and-uses imbalance;
- cash-bridge inconsistency;
- non-Italian filenames and arbitrary company names;
- rejection of unreviewed, stale, or source-unbound semantic models;
- preservation of the existing exact-arithmetic and assurance replay controls.

Synthetic fixtures establish contract behavior only. A separate, independently
reviewed holdout of a previously unseen real case remains necessary before
claiming field validation or generality on real Concordato Preventivo work.
