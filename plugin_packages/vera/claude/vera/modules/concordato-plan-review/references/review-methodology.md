> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Concordato Preventivo Review Methodology

## Scope

This workflow structures the professional review of an Italian `concordato
preventivo`. It is not a generic report builder, a legal-opinion engine, or a
plan-attestation engine. The qualified professional remains responsible for
the legal, accounting, tax, feasibility, and evidence-sufficiency judgments.

## Review sequence

Review the case in this order:

1. **Procedure and framework** — identify debtor, court, reference, stage,
   plan type, cut-off, governing framework, and authority as-of date.
2. **Document perimeter** — identify every captured document, its semantic
   role, version, authoritative purpose, and any missing or conflicting
   version.
3. **Proposal and plan** — assess whether proposal, plan mechanics, timing,
   assumptions, and distributions are internally consistent.
4. **Creditor perimeter and treatment** — review completeness, priority,
   classes, voting treatment, recovery, timing, disputes, and evidence.
5. **Voting and homologation** — review voting perimeter, majorities,
   objections, cram-down or cross-class effects where professionally relevant,
   and current homologation status.
6. **Liquidation alternative** — review the comparator and the evidence for
   estimated liquidation recoveries.
7. **Sources, uses, and feasibility** — review operating cash, disposals,
   external contributions, financing, costs, distributions, funding gap,
   liquidity bridge, and milestones.
8. **Attestation and consistency** — compare the professional attestation with
   the plan, proposal, accounting records, and supporting schedules.
9. **Tax, social-security, and accounting matters** — keep these as explicit
   professional questions; do not infer them from keywords or balances.
10. **Issues and conclusion** — record gaps, contradictions, assumptions,
   follow-up, and responsible professional judgment.

## Evidence contract

Every semantic conclusion must state a `judgment_basis` and refer to captured
source artifacts with precise locators where available: page, section,
paragraph, sheet, cell, table, or row. A file name is not evidence of a
document role. An equal amount is not evidence that two statements have the
same meaning.

Use status values such as `missing`, `partial`, `unclear`, `gap`, and
`not_assessed` when the evidence does not support a stronger conclusion.
Do not manufacture completeness.

## Deterministic schedules

After a reviewer confirms the semantic model, code may calculate:

- creditor and class claim totals;
- proposed and liquidation recovery totals and percentages;
- plan-versus-liquidation deltas;
- sources, uses, surplus/shortfall, and funding gap;
- period cash bridges and minimum closing cash;
- date ordering and exact arithmetic consistency;
- optional plan-to-support amount differences.

These are mechanical observations. They do not establish priority, class
validity, compliance, feasibility, creditor best interest, or attestation
adequacy.

## Primary workpaper standard

The professional workpaper should make the following reviewable:

- procedure identity and framework;
- authoritative document set and version gaps;
- creditor-level and class-level treatment;
- liquidation comparator;
- sources and uses;
- liquidity and distributions over time;
- milestones and assumptions;
- all required review questions;
- issues, evidence requests, and owner/status;
- exact mechanical checks and limitations;
- numerical tie-out only as an appendix.

## Review UI contract

`review_payload.json` is the bounded UI contract. The first rows must concern
semantic model status, procedure, professional questions, issues, creditor
class treatment, and mechanical checks. Source inventory and amount matching
remain supporting rows.

Applying UI decisions records reviewer actions. It does not silently rewrite
the sealed semantic model or grant publication authority.

## Validation standard

Synthetic and adversarial tests establish schema, arithmetic, receipt, and
failure behavior. They do not establish field performance. Before claiming
real-case generality, use a previously unseen real case and have a qualified
professional compare the complete output with an independently prepared
review.
