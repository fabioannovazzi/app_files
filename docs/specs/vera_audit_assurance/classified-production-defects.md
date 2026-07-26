# Classified repository defects

Date: 2026-07-25

Status: all eight root causes remediated and regression-tested; historical
failure evidence retained below.

This ledger separates production or source-contract defects from repaired test
drift. It is not a full-suite pass and does not authorize changing production
files.

## Evidence sets

| Evidence | Result | JUnit SHA-256 |
| --- | --- | --- |
| Complete 100% traversal with eight preclassified controls deselected | 7,338 tests; 4 failed, 580 skipped, 0 errors | `d6f001ceef5277b3ea7065795c0c3947abf181c7019a56e840ee887241142f84` |
| Preclassified current controls | 8/8 failed | `d8a660049773f566417566cee90e48aa5fdbd282e9c58b145312a415c98a66fd` |
| Reconciliation tail | 4 tests; 2 passed, 2 failed | `2bb834ee3b91242f195fcf8ac25392450605f675ed23e84e5a08e8218a6d00f6` |
| Corrected test-contract regression | 587 tests; 482 passed, 105 skipped, 0 failures/errors | `00ccd035d766284a38ad451e3dc4826789098826e7485ea8a4cc012d0fdab930` |

The ten retained failing controls map to the eight root causes below.

## D1 — slope-plot string aggregation

- Surface: `modules/data/time_series_data_prep.py`
- Control:
  `test_prepare_data_for_slope_plot_pivots_metric_and_label_and_drops_zero_sum`
- Observed: `prepare_data_for_slope_plot` pivots both the numeric metric and the
  string label using `agg_func="sum"`. Polars raises
  `InvalidOperationError: sum operation not supported for dtype str`.
- Contract: numeric values may be summed; categorical display labels require a
  deterministic non-numeric aggregation with an explicit duplicate policy.
- Minimum remediation: select and document a deterministic label aggregation
  that rejects or resolves conflicting labels without coercing strings into a
  numeric operation.
- Validation: positive single-label and repeated-identical-label cases, plus a
  conflicting-label negative and the complete slope-plot test file.

## D2 — stale Clara hosted-service privacy reviews

- Surface: `plugins/clara/privacy/hosted-services`
- Control:
  `test_clara_privacy_register_covers_every_user_facing_skill_and_is_fresh`
- Observed: the deterministic validator reports stale source fingerprints for
  `hosted-interviews`, `hosted-voice`, `plugin-feedback`,
  `plugin-update-check`, and `retail-data`.
- Contract: a fingerprint may be refreshed only after reviewing the changed
  source surface; a mechanical refresh alone is not evidence of review.
- Minimum remediation: inspect each source diff against its privacy contract,
  update the review record if the contract remains accurate, and then run the
  validator's approved refresh path.
- Validation: complete Clara privacy validator and focused privacy tests.

## D3 — new-client audit fixture has no editable AML proposal

- Surface: `scripts/audit_local_review_workbench_writeback.py`
- Control: `test_new_client_fixture_uses_real_proposal_only_contract`
- Observed: `_write_new_client_fixture` initializes and packages a blank real
  case, then searches the generated review payload for an editable
  `aml_risk_factor`; the generated payload contains none.
- Contract: the write-back audit needs a real proposal-only item and may not
  invent an item directly in the review payload.
- Minimum remediation: construct the smallest valid new-client input through
  the public initialization/input contract that causes the packager to emit an
  editable AML proposal, then retain the current search and assertion.
- Validation: the focused control and the complete audit-writeback test file.

## D4 — Vera video-guide specification and constant disagree

- Surface: `scripts/build_vera_youtube_video_guides.py` and
  `static/shared/video-production/vera-missing-guides.json`
- Controls:
  `test_language_filter_preserves_existing_manifest_entries` and
  `test_unknown_language_filter_is_rejected`
- Observed: the clean specification omits thirteen localizations still required
  by `EXPECTED_LOCALIZATIONS`: five `new-client/core`, four non-Italian
  `new-client/italy`, and four non-Italian
  `check-entries/italy-fatturapa` editions. The source-agreement failure occurs
  before language-filter validation.
- Unknown: current evidence does not establish whether the specification or
  the constant is the intended product scope.
- Minimum remediation: make one explicit product-scope decision, update the
  non-authoritative side, and retain the equality guard.
- Validation: complete video-guide builder tests and manifest/source-drift
  checks.

## D5 — empty workbench decisions omit schema-2 digest binding

- Surface: `scripts/serve_review_workbench.py`
- Controls: `test_local_review_workbench_injects_browser_write_bridge` and
  `test_local_review_workbench_routes_save_and_apply_to_plugin_mcp`
- Observed: `_empty_ui_decisions` copies the review schema and run identity but
  omits `review_payload_content_sha256`. Check Entries schema 2.0 requires that
  field to equal `review_payload.content_sha256`; render and save/apply reject
  the empty state as bound to a different payload.
- Contract: even an empty decision set must be cryptographically bound to the
  exact review payload when that payload exposes a content digest.
- Minimum remediation: conditionally copy
  `review_payload.content_sha256` into
  `ui_decisions.review_payload_content_sha256`; do not synthesize a digest when
  the payload contract does not expose one.
- Validation: both failing controls, all ten currently passing workbench
  controls, and Check Entries MCP review-contract tests.

## D6 — browser payload retains a private intake client name

- Surface: `scripts/serve_review_workbench.py`
- Control:
  `test_phase_one_local_workbench_uses_sanitized_and_script_safe_payload`
- Observed: `_sanitize_browser_payload` redacts absolute paths but transforms
  `Francesco Private Client /Users/private/customer` into
  `Francesco Private Client <local-path>`, leaving the private client name in
  the browser session.
- Contract: server-owned intake assumptions and local paths must not enter the
  browser payload. Separately reviewed user-facing fields in the review payload
  are not automatically equivalent to server-owned intake assumptions.
- Minimum remediation: define field-aware redaction for private
  `run_intake.assumptions` values before recursively sanitizing paths; do not
  globally remove every `client_name` field from reviewed display content.
- Validation: the failing privacy control, malicious-script escaping control,
  and the complete local-workbench test file.

## D7 — synthetic fee is not an exact strong-signal match

- Surface: `src/check_statements_logic.py` and
  `src/check_statements/matching.py`
- Control: `test_reconcile_transactions_marks_synthetic_fee`
- Observed: `fee_mode="match"` appends a synthetic ledger entry whose metadata
  source is `synthetic_fee`. `_exact_pass` treats a `FEE` type as consistent
  but grants no fee-specific score or strong signal, so the otherwise exact
  amount/date pair remains unmatched.
- Contract: a deliberately generated synthetic fee must retain a deterministic
  one-to-one link to the source bank fee; generic amount/date coincidence must
  not become a strong signal for unrelated rows.
- Minimum remediation: retain explicit synthetic provenance that identifies
  the originating bank row and admit only that bound pair as the fee-specific
  exact signal. Preserve the external `None` ledger index for a synthetic
  endpoint.
- Validation: the failing control, duplicate same-day/same-amount fee
  negatives, unrelated fee-like descriptions, evidence-reuse negatives, and
  the complete reconciliation file.

## D8 — adaptive group pass reports progress backwards

- Surface: `src/check_statements_logic.py`
- Control: `test_reconcile_progress_callback_reports_executed_passes`
- Observed: with `group_limit=2`, exact, fuzzy, and first group passes consume a
  three-pass denominator and reach `1.0`. The adaptive second group pass then
  reuses the group callback index, producing the sequence
  `[1/6, 2/6, 5/6, 1.0, 5/6, 1.0]`.
- Contract: progress is monotonic, bounded in `[0, 1]`, and reaches `1.0` only
  after the last executed pass.
- Minimum remediation: reserve a fourth pass slot whenever the adaptive
  `group_limit=3` retry is eligible; use a distinct pass index for that retry,
  and explicitly complete at `1.0` when the retry is not needed.
- Validation: adaptive-run, non-adaptive-run, empty-input, and early-match
  progress cases plus the complete reconciliation file.

## Remediation closure

All eight root causes were remediated without adding an orchestrator:

| Root cause | Closure |
| --- | --- |
| D1 | Numeric slope values remain summed; repeated identical labels collapse deterministically; conflicting labels fail explicitly. |
| D2 | Every changed Clara hosted-service surface was reviewed and its source fingerprint refreshed. |
| D3 | The real new-client write-back fixture now selects an emitted editable AML factor section instead of assuming a case-specific item type. |
| D4 | The builder now follows the reviewed 21-localization product specification and retains its equality guard. |
| D5 | Empty schema-2 decisions copy the exact review-payload content digest when the payload exposes one. |
| D6 | Browser payloads remove server-owned intake assumptions while raw MCP arguments retain the trusted server context. |
| D7 | Synthetic fees carry exact originating-bank-row authority; caller-forged provenance is ignored and same-day/equal-amount coincidence remains insufficient. |
| D8 | Adaptive reconciliation passes have distinct monotonic progress slots and report `1.0` only after executed work completes. |

Focused closure evidence includes 6/6 slope-label tests, 13/13 Clara privacy
tests, 20/20 local-workbench/write-back tests, 15/15 video-guide tests, and
92/92 statement-reconciliation tests. The later uncapped coverage traversal
executed 7,373 tests with one stale Journal Sampling privacy fingerprint and
no other failure; coverage passed at 80.32%. After reviewing the intervening
interpreter-selection change, that fingerprint was refreshed and the complete
21-test Vera privacy gate and 253-test package gate passed.

Those repository and package totals are historical closure evidence for that
source state. Current 2026-07-26 remediation evidence is recorded in
`completion-audit.md`; it includes a 7,398-test clean collection boundary and a
270-test clean release surface, but not a current green repository-wide runtime
traversal.

## Remediation organization

Production changes should be split by surface and reviewed separately:

1. reconciliation correctness: D7 and D8;
2. shared local-review correctness/privacy: D3, D5, and D6;
3. reporting and release maintenance: D1, D2, and D4.

The retained rule remains that focused tests alone are insufficient. Closure
also requires affected-file regression, static checks, an uncapped repository
traversal, and the repository coverage threshold.
