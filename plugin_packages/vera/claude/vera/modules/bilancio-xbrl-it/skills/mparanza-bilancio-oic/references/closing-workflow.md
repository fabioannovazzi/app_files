> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Reviewed closing accounts

Use this path before form selection and mapping when preparing the closing
accounts. It belongs to the existing canonical Bilancio case. Presentation
adjustments remain a separate operation; they are not accounting journal entries.

## Service operations

Use `xbrl_case_analyze` with the current revision and a new idempotency key.
`CaseService` enforces the authenticated tenant, role and revision for every
operation. User text and documents never supply those authenticated identities.

1. `start_closing_workflow`: a reviewer explicitly records
   `accounting_origin` as `CONTABILITA_INTERNA` or `CONTABILITA_ESTERNA`, before
   trial-balance import. This is opening data, not a merits decision.
2. Import the baseline through ordinary document intake. A source with only
   ending balances requires an explicit `column_mapping`. If the source uses
   blank debit/credit balance cells as zero, explicitly supply
   `blank_balance_cells_are_zero: true`; never select this convention merely
   because amounts are missing. Original headers, raw values and source
   coordinates remain available. Opening balances and turnover absent from
   this layout remain `null`, with an explicit unavailable-field list.
3. Attach supporting documents through the existing
   `attach_supporting_document` operation. For selected UTF-8 CSV, Markdown,
   text and JSON documents up to 64 KiB, `CLOSING_EVIDENCE` exposes the complete
   retained untrusted extract, its document identity and hashes. Request exact
   pages using offset/limit; a page exceeding 64 KiB fails and must be narrowed.
   Other files explicitly require qualified extraction through the existing
   PDF or supporting-schedule workflow. Do not claim their contents were read.
4. Interpret documents and evidence sufficiency in the model runtime. Use
   `propose_closing_review` for non-authoritative `FASCICOLO`, `SCREENING` or
   `AREAS` interpretations, carrying `proposal_id`, `kind`, `content`, `reason`
   and registered `evidence_refs`. A suggestion does not change applicability,
   sufficiency, accounts, approvals or client requests.
5. The reviewer records `record_closing_decision`, with `record_id`, `kind`,
   `decision`, `reason` and `evidence_refs`. Optional `effective_date` records
   the date the decision concerns; the actual recording time is always retained.
   Supported kinds are `FASCICOLO`, `SCREENING`, `ADJUSTMENT`, `ISSUE`, `AREAS`,
   `FORM` and `CONTROL_REVIEW`. The service requires reviewer authority.

### Decision payloads

- `FASCICOLO`: `requirements` and explicit `sufficient_to_start`. Each
  requirement has a stable ID, description, reason, evidence references,
  one of the seven documented sufficiency states, and an explicit
  `request_from_client` flag. Only confirmed missing, insufficient or outdated
  evidence may enter the single request draft. A review-required accounting
  issue is routed to an area with an `ISSUE` decision; it is not silently
  turned into a client request. No sending operation exists on this path.
- `SCREENING`: `version_id`, confirmed `convention`, an explicit
  `closing_entries_included` boolean, and individually confirmed `period`,
  `comparative`, `debit_credit`, `closing_entries` checks. The baseline version
  is `baseline`. Missing closing entries open adjustment work; they do not
  permit form selection or mapping. A replacement additionally requires exact
  reconciliation and no unresolved adjustment proposals or reconsideration.
- `ISSUE`: stable `issue_id`, `area_id`, description and `OPEN`, `ROUTED` or
  `RESOLVED` status. Where applicable, include the originating `requirement_id`.
  Routing a litigation issue does not decide whether to recognize a provision.
- `AREAS`: a retained `proposal_id` and reviewed `areas`, each with stable ID,
  label, `ACTIVE` or `EXCLUDED` status and reason. Exclusions are proposals until
  a reviewer confirms them. Optional `open_issues` retain unresolved treatments.
  Absence of an account or document is not proof of non-applicability.
- `FORM`: an eligible `form` after ordinary effective-dated eligibility
  analysis. This records the reviewer choice in the same durable register.
  Opening form and mapping never means that all closing work is complete.
- `CONTROL_REVIEW`: exact current `version_id`, reopened `scopes` and
  registered `workpaper_refs`. Controls cannot resume before replacement
  screening; confirming one scope does not close other scopes or open issues.

## Accounting adjustments and replacement balances

`propose_closing_adjustment` records `proposal_id`, an explicit `subject_key`,
reason, registered evidence and balanced lines with `account_code`, `debit`,
`credit`. Accounts must exist in the baseline. The preparer and approving
reviewer must differ. An `ADJUSTMENT` decision references the proposal and an
explicit `APPROVED` or `REJECTED` outcome. Approval never posts an entry or edits
the supplied source. A second approval of the same proposal is rejected.

For a replacement on the same subject, `supersedes` must identify the one
currently effective decision. A2-bis is the full replacement for A2, not an
increment and never a second valid adjustment for the same subject.

`ingest_closing_trial_balance` accepts a new source path, unique `version_id`
and the explicit source-column conventions. It retains a candidate; ordinary
document reimport cannot bypass this boundary. The engine compares its account
population, exact ending amounts, unchanged comparatives and descriptions with
the baseline plus only currently approved adjustments. Balanced unexplained
changes still fail. A failed candidate never becomes the canonical balance.
Stable account identity follows the reviewed account code even if rows move.

## New evidence and reconsideration

A new supporting document after screening requires review. The model or
preparer identifies the affected treatment; code never classifies its legal or
accounting meaning by keywords.

`open_closing_reconsideration` adds an event with `record_id`, reason,
registered evidence and a `decision` identifying active `decision_ids`, affected
`area_ids` and explicit `scopes`. Scopes use `area:<id>`, `mapping:<code>` and
`validation`. Every affected account mapping and overall validation must be
suspended. Old decisions remain unchanged and consultable.

After professional area review, a replacement adjustment decision may list
`resolves_reconsiderations`. Closing that decision review does **not** resume
the dependent validations: the latest accepted accounts still contain the old
adjustment. A replacement balance must arrive, reconcile and receive a new
professional screening. Only then do dependent controls become
`REVIEW_REQUIRED`; their workpapers and checks must be repeated. Unaffected
form choices, decisions and mappings remain retained. Changed-account mappings
are removed from the accepted mapping set and require renewed review.

The decision register is separately hash-chained inside the canonical case;
each event binds its author/role, reason, documentary hashes, reviewed proposal
and screened version. Loading a case verifies both the ordinary case checksum
and this register. Statuses are projections from later events, never edits of
earlier records. Missing evidence, open professional issues and incomplete
dependent controls block the existing validation and approval route.

## Review and acceptance

Use `CLOSING_OVERVIEW`, `CLOSING_EVIDENCE`, `CLOSING_PROPOSALS`,
`CLOSING_ADJUSTMENTS`, `CLOSING_VERSIONS`, `CLOSING_RECONCILIATION`,
`CLOSING_AREAS` and `CLOSING_DECISIONS` through the existing paginated review
tool. Workflow-guidance packets include bounded closing requirements, open
issues and dependencies with exact available counts; they are suggestions.

The repository runner `scripts/run_bilancio_alfa_v3_acceptance.py` uses the
unchanged Alfa v3 fixtures and persistent `CaseService`, with explicitly
simulated reviewer P1 and preparer C1. It retains checkpoints, execution trace,
source hashes and expected/observed comparisons. E1, E2, 20–22 January and the
post-A2-bis/pre-document-12 suspension are mandatory. Source and packaged-service
acceptance are distinct from an enabled installation or a fresh native-host
run. Alfa does not include tax computation, provision recognition, prior-XBRL
reconciliation, notes or final filing. Those omissions must remain visible.
