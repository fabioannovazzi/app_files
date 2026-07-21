# Client Onboarding workflow reference

## Purpose

This component prepares a source-bound onboarding dossier for professional
review. It is a workflow layer, not a CRM, identity provider, screening
service, signature system, or legal-compliance oracle.

## Composition with Client Intake

`client-intake` owns file inventory, OCR, extraction, document classification,
and the first missing-document pass. `client-onboarding` verifies a final-ready
run by stable run ID and exact final-manifest byte hash, then structures
relationship-specific facts and decisions. A structurally valid but non-final
binding blocks export; a malformed, mismatched, or tampered binding is rejected.
When no upstream run exists, the intake must explicitly declare
`standalone_evidence` and explain why. Standalone evidence is never presented as
reviewed Client Intake output.

## State machine

```text
intake_pending
  -> evidence_ready
  -> proposals_ready
  -> written_pending_review
  -> partial_review_applied | blocked | ready_for_professional_export
```

A material edit returns the run to `proposals_ready`. Review history is retained;
regenerated domain artifacts belong in a new run directory. No state means that
a client has been accepted, documents have been signed, a client-ready document
has been generated, or a relationship is active.

## Artifact contract

The review lifecycle is:

1. `run_intake.json`
2. `review_payload.json`
3. `ui_decisions.json`
4. `applied_decisions.json`
5. `final_artifacts.json`

`review_payload.json` includes `source_artifacts`, exact basis hashes, the
upstream-intake verification posture, a privacy notice, and only minimized case
aliases. Full client data remains in private local artifacts.
`review_handoff.md` names the validate, render, save, and apply tools and is
included in `final_artifacts.json` with QA metadata.

The review payload is bound to the exact persisted domain artifacts with
canonical SHA-256 values. File manifests use byte SHA-256 values. A material
upstream, source, or template change breaks the current binding and validation
must fail until regeneration; it does not turn an old acceptance into a current
one.

## Review action semantics

- `accept`: confirm only the proposal displayed in that item.
- `edit`: record an explicit replacement proposal; material edits require a new
  calculation or document version before acceptance.
- `reject`: reject the proposal and keep the item as a blocker.
- `mark_unclear`: record unresolved evidence or meaning and keep the blocker.
- `request_more_documents`: create an explicit evidence request and keep the
  blocker.
- `skip`: do not decide; skipping is never approval.

The apply operation validates run identity, revision, allowed actions, duplicate
IDs, review hash, basis hashes, and dependent blockers before writing. It writes
review manifests only; source facts and legal conclusions are never mutated
silently. Review actions may clear review blockers only. Domain and artifact
blockers remain in the export gate until the underlying package is regenerated.

## Relationship export gate

`final_artifacts.json` keeps three separate blocker sets:

- domain blockers, such as an unresolved Client Intake binding, incomplete
  subject screening, unconfirmed privacy processing decisions, or a Table 1
  decision still open;
- review blockers, created by pending, rejected, unclear, skipped, edited, or
  document-request actions;
- artifact blockers, such as a missing or hash-mismatched required output or an
  unusable template reference for a required document plan.

Marketing-only restrictions carry `marketing_use` scope. A marketing choice of
not requested, refused, or withdrawn never blocks export of the professional
relationship dossier. `ready_for_professional_export` is possible only when the
relationship-scope domain, review, and artifact sets are clear and the required
owner-only outputs match their hashes.

## Screening and privacy contract

The required screening grid is every relevant subject—client, each
representative, and each beneficial owner—crossed with PEP, sanctions, and
country checks. Deterministic validation checks exact coverage, evidence, and
resolution metadata; it never interprets a result or calls an external provider.

Privacy processing decisions keep purpose, controller/processor role, legal
basis or processor authority, retention rule, sources, and confirmation metadata
as separate fields. These values are professional decisions. Marketing consent
has its own record and scope; professional review confirms the accuracy of the
record, not the client's consent itself.

## AML mechanical contract

The CNDCEC 2026 operational guidance describes four client factors (section A)
and six service factors (section B), each scored 1–4 by the professional. The
script checks exact factor sets and arithmetic; it does not select scores.

- Included B: `RS = (A + B) / 10`.
- Professionally confirmed excluded B: `RS = A / 4`.
- `RE = RI × 0.30 + RS × 0.70`.
- Effective-risk thresholds are 1.6, 2.6, and 3.6.
- Table 1 applicability is a separate, mandatory-basis professional assessment.
  `unknown` or proposed status blocks the treatment outcome.
- Once Table 1 is confirmed: non-significant + Table 1 maps to the applicable
  conduct rule; non-significant without Table 1 and little significant map to
  simplified; fairly significant maps to ordinary; very significant maps to
  enhanced.

Confirmed mandatory enhanced triggers cannot be declassified. Unknown trigger
truth blocks the outcome. A one-off relationship has no automatically scheduled
periodic review. An unresolved Table 1 assessment has no schedule. A confirmed
Table 1 conduct rule has no automatically assigned 36/24/12/6-month cadence.
Enhanced ongoing review requires an explicit 6- or 12-month choice.

## Document boundary

Applicability and legal text are semantic decisions. The script never assembles,
renders, or substitutes legal text. It records a local template reference only
after checking its content hash, approval, reuse scope, jurisdiction, language,
review date, and source-basis hash. A mismatch or unusable reference blocks the
affected document plan. The output remains an internal plan, not a signable
draft.
