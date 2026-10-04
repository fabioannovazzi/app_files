# Scissione case and review contract

Author: Mparanza development; 2026-09-29; initial implementation for review.
Requirements: recovered Discord message 1554534739514359879 and scissione v0.1
specification/test documents. Original package hash and acceptance scope are in
`docs/vera_scissione_implementation.md` in the repository.

`synthetic-case.json` is the executable structural example, not a live client.
Replace its zero evidence digest with the actual source's SHA-256, and its path
with the exact run-input relative path returned by Studio Archive. Never copy
its authority, status or professional conclusions to a real case.

The single `case` object is authoritative. Derived schedules are projections;
do not keep independent editable facts, decisions or allocations files alongside
it. A stored revision contains case, dependency fingerprints, exact approvals,
change impact, schedules and unresolved issues. Its canonical SHA-256 identifies
the full version. `previous_sha256` links its predecessor.
`engine_version` records the calculation/review contract version and participates
in every fingerprint; a changed engine requires fresh review of carried decisions.
When adding physical evidence, prepare a new run with the finalized same-engagement
prior revision as an upstream artifact. `previous_revision_path` in the prepare
request identifies its relative input path. A JSON imported as an ordinary source
cannot manufacture this handoff. Evidence identities include content and locators,
not the execution folder location, so unchanged evidence remains reusable.

Each record has stable `id`, `kind`, `status` (`known`, `unknown`, `contested`),
explicit `material`, `entity_ids`, `evidence_ids`, `depends_on` and `data`.
Common references must resolve and the dependency graph must be acyclic.
Kinds are fact, allocation, liability, ownership, valuation, tax_position, rule,
decision, deadline and document. Data beyond the explicitly validated contracts
is model-authored evidence; the software does not validate its professional meaning.

`route_record`, `perimeter_record`, `calculation_record` identify decisions.
Every decision records choice, rationale and alternatives. The route records the
exact jurisdiction/accounting/operation/beneficiary scope. The perimeter lists
its required records and depends on them. Include material contracts, off-ledger
risks and unexamined areas as appropriate; do not infer this list from balances.
The calculation depends on the route, ownership, valuation and all allocations.

Amounts and fractions are decimal strings with no exponent; EUR is explicit at
case level. Unknown amounts are null. Allocation rows distinguish asset/liability
side, before/transferred/remaining values for book/tax/economic bases, source and
destination entity. Ownership uses positive fractions summing exactly to 1;
shareholder tax cost is a separate nullable amount. Economic values include an
explicit bridge for costs/synergies or other approved changes. Units, quantum and
rounding (`half_even` or `half_up`) are explicit calculation assumptions. Residuals
block a technically prepared status even when they net to zero across owners.

Rules retain act, article, paragraph, version, scope, source_status, effective_from,
applicable_from and state. The state is candidate, source_checked,
professional_review_pending, superseded or withdrawn. Professional approval is
a separate version-bound record; it is never a state supplied by the model or
automatically promoted by tests. Date applicability is not selected by code.

Review request (only after actual confirmation of the exact displayed version):

```json
{
  "revision_sha256": "exact current revision hash",
  "record_ids": ["route", "ownership"],
  "reviewer": "actual responsible professional",
  "role": "declared professional role",
  "reviewed_at": "2026-09-29T19:00:00+02:00",
  "rationale": "actual reason and limits of confirmation"
}
```

Approval records attest a declared review, not provider-signed identity or legal
correctness. Local file hashes detect accidental changes; they are not protection
against an attacker who can rewrite the whole case folder and all hashes.

Outputs: `scissione_current.json`, then immutable `scissione_versions/<digest>/`
containing revision.json, review.md/html, ownership_before_after.json,
allocations.json, change_impact.json and artifact_manifest.json. A new revision
never overwrites earlier documents or approvals. No watcher or scheduled legal
update service is installed. A professional/model initiates source review and
supplies changed records; the helper traverses the explicit dependencies.
