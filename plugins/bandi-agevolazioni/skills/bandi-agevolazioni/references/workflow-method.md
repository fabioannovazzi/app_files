# Bandi e agevolazioni — operating method

This reference governs the semantic work. Scripts enforce contracts and never
decide legal meaning.

Before a specific call is selected, follow `opportunity-radar.md` and
`source-first-discovery.md`. Source-plan selection, source relevance,
opportunity lifecycle and amendment meaning, compatibility,
economic assumptions, application complexity and recommended action are
model-led proposals. Coverage counts, reference closure, lifecycle-history
preservation, exact query-dimension claim closure, query-scoped selection
reference closure, temporal-window containment, source-first execution
ordering, cursor preservation, append-only revision storage, exact range
subtraction, review binding and recomputable handoff hashes are mechanical
controls. The code never infers which source covers a territory or category.

## 1. Source baseline and conflicts

Build the baseline from the formal call, formal amendments, incorporated acts,
annexes, official forms and portal instructions, and then official FAQs. Record
issuer, publication and effective dates, authority role, exact bytes, and
explicit relationships. Do not infer a universal legal hierarchy from document
labels. A formal amendment may change the call when its text and applicability
support that conclusion; an FAQ is clarifying evidence and never silently
amends a formal act.

When sources appear inconsistent, create a `source_conflict` issue. Quote or
hash-locate both passages, state the dates and roles, propose the significance
with model-led reasoning, and require professional resolution. Keep the issue
open until the professional accepts a supported resolution or marks the dossier
not ready. A deterministic validator checks only that references close and that
open review issues block a ready disposition.

## 2. Atomic requirements

Create one requirement for one testable proposition. Separate eligibility,
exclusion, cost, document, deadline, procedure, form, and narrative duties.
Every requirement needs an exact source fragment, an applicability statement,
expected evidence, and professional confirmation. Do not collapse several
conditions into one conclusion or import a rule from another call.

Store the exact excerpt text beside its UTF-8 SHA-256. The deterministic hash
protects the stored excerpt from unnoticed change; it does not prove that the
excerpt was extracted correctly from a PDF or that it supports the proposed
meaning. The professional confirms that source, locator, excerpt, and
interpretation match.

## 3. Facts and assessments

Record company, financial, quotation, declaration, and project facts with an
as-of date, evidence IDs, kind, and review status. Model inferences and user
assertions stay visibly distinct from document observations. A ready applicable
assessment needs confirmed facts and one reviewed source-backed requirement.
Keep documentary readiness separate from outcome.

Create those structured facts in a client-evidence mapping session limited to
the selected evidence. End that session after recording the contribution. Every
later assessment contribution uses a new operator-attested session reference
and receives only its task-specific reference closure. If the packet is
insufficient, stop and request the exact additional subjects or evidence. For
an over-limit structured collection, the professional supplies exact IDs from
that collection; those IDs scope only that collection while other required
collections stay complete. Do not reuse the mapping session or infer from
omitted content.

Only two deterministic rule families are allowed: exact comparison of confirmed
finite decimal strings and exact comparison of confirmed ISO dates. The
professional supplies the result-to-outcome mapping; the validator recomputes
the comparison and rejects disagreement. Eligibility meaning, source selection,
and cost classification remain model-led.

The deterministic families have these bounded justifications:

- `exact_decimal_compare` is deterministic because finite decimal ordering is
  mechanically exact, reproducible across runs, and useful for audit of a
  professionally selected threshold. The rule never chooses the operands,
  threshold, legal meaning, or assessment mapping.
- `exact_date_compare` is deterministic because ISO calendar-date ordering is
  mechanically exact and reproducible after the professional has selected the
  legally relevant dates. The rule never decides which date governs, whether a
  deadline applies, or the legal effect of the comparison.
- Schema, reference, hash, path, review-freshness, status, secret-key, and
  packaging checks are deterministic because their correctness follows from a
  closed technical contract, and reproducibility or security requires the same
  result for the same bytes. They do not replace semantic review.

## 4. Documents, costs, forms, and narrative

Build the document checklist from confirmed requirements. Classify each cost
against its exact cost requirement and quotation/evidence; never generalize from
keywords. Cross-reference form and narrative fields to facts and requirements.
Declaration acceptance, signature, payment, saving, and transmission controls
remain empty and manual.

For each narrative, separate sourced factual claims, professional judgments,
and drafting choices. Do not add unsupported benefits, impacts, dates, jobs,
amounts, or commitments.

## 5. Cross-document consistency

Create explicit consistency checks for identity and registration data, dates,
financial figures, requested amount and cost totals, quotations, declarations,
project descriptions, and repeated portal fields. Model reasoning proposes
whether evidence is consistent, conflicting, or requires verification. A ready
dossier requires confirmed `consistent` or reasoned `not_applicable` checks.

## 6. Missing information and red flags

Create issues for missing evidence, ambiguous applicability, source or fact
conflicts, exclusion risk, cost risk, expired or inconsistent dates, document
defects, unsupported narrative claims, and portal uncertainty. Do not hide an
open `review_required` or `blocking` issue in prose. Both block ready status.

## 7. Simulated authority review

After the dossier is otherwise complete, review it from the issuing authority's
perspective. Create explicit checks for every eligibility and exclusion result,
document and signature requirement, cost line, total, declaration, narrative,
deadline, and portal field. This is model-led adversarial review, not a claim
about the authority's eventual decision. Record pass, fail, verify, or reasoned
not-applicable outcomes. Professional review is required before the simulation
can be `reviewed` and `pass`.

## 8. Portal and handoff boundary

Produce a manual field map containing the portal label, proposed non-protected
value, source facts, requirement links, readiness, and rationale. Never receive
credentials or session material and never interact with a live application.
The authorized person performs authentication, declarations, signature, save,
payment, and transmission.

Package only after deterministic validation passes. The dossier remains a
professional-review artifact with `ready_to_file=false`. Studio Archive owns
the final artifact declaration and retention lifecycle; do not invent a local
retention period or claim control over provider-account retention.
The package manifest seals the intake, source register, workbench, intelligence
register, review log, run state, validation audit, and rendered dossier so a
post-validation change cannot be silently packaged.

Review-log identity is deliberately bounded: the user must explicitly confirm
each recorded decision, while reviewer ID and role remain locally asserted and
are not authenticated by this workflow. Do not describe that metadata as an
authenticated signature, professional identity proof, or filing approval.
