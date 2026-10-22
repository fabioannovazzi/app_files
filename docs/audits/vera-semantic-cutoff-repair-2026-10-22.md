# Open-item semantic receipt repair

The six-case Vera 0.1.473 evaluation remains unchanged. Its cumulative-payment
and overpayment failures led to three source repairs in candidate Vera 0.1.474
(Open-item component 0.1.75).

* Semantic preparation now follows `post_cutoff_events_excluded`, including
  later bank receipts only when the selected scope includes them. The default
  exclusion is preserved. This is an explicit date/perimeter contract, not a
  rule for interpreting a payment's meaning.
* Assurance rederives semantic settlements from their source-bound worker
  evidence. A closed invoice must have zero target residual, while unused cash
  remains an explicit source residual. Hiding that cash, underallocating the
  invoice or changing its face amount is rejected. Unrelated unbalanced ledgers
  do not inherit the residual exception.
* Retained worker response/launch serialization survives sorted prepared JSON
  without discarding byte-hash verification or changing the receipt. Parsed
  evidence must still equal its retained serialization.

## Verification

The two included-later-receipt regressions first failed with `missing_evidence`.
After the date repair, native overpayment artifact generation exposed the
closure/residual and persisted-receipt issues; the regressions exercise those
paths too.

All 207 tests in `test_semantic_resolution.py`, `test_audit_assurance.py` and
`test_reconciliation_workflow.py` passed. The 31 semantic tests include included
and excluded/default cut-off policies, exact residuals, fabricated citations,
wrong parties, reused cash, modified ledgers and persisted response replay.
Black, Isort, Mypy and Bandit passed for the edited Python sources/tests.
Package-integrity and update-notification suites completed with 406 passes and
two optional locally installed curated-marketplace checks skipped. The complete
Vera Codex/Cowork/Antigravity release build and source-drift check also passed.

An additional non-blinded source integration used copies of the original
cases' normalized professional fields and the maintained isolated native worker,
without mocked responses:

| Case | Worker invocation | Native allocations | Unapplied cash |
| --- | --- | --- | --- |
| Cumulative | completed, one batch | 366 + 244, both invoice residuals 0 | 0 |
| Overpayment | completed, one batch | 610, invoice residual 0 | 90 |

Both responses generated native Excel/Word workpapers and survived persisted
assurance replay. The operational workbook contains allocated amounts and zero
invoice residuals. Source-component tests omit original physical source locators;
their source gate is not applicable, ordinary semantic review is withheld, and
reporting is blocked pending review. They are not Archive/installed-host acceptance
and do not invent professional approval or replace the original evaluation.

The current Codex model catalog selected `gpt-6-luna` with high reasoning effort.
Two real ephemeral native invocations returned successfully with retained
launch/response evidence. This is a requested model configuration, not independent
provider attestation of model identity. No direct model API was substituted.

The privacy review retains the same mapped-field packet bounds and recipients.
In-scope later receipts use that existing packet; retained serialization stays
local. Version-dependent service and course metadata are regenerated with the
candidate. No Marketplace publication or revision of the public evaluation is
part of this repair. Fresh enabled-installation and end-to-end acceptance remain
separate release evidence.
