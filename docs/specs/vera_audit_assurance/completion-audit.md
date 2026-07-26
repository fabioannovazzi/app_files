# Vera audit-assurance completion audit

Date: 2026-07-26

Status: Marketplace package ready; assurance program not fully promoted.

This is the requirement-by-requirement close-out for
`vera-audit-assurance-redesign.md`. It records current evidence and does not
turn an unresolved evaluation into a pass.

## Completion criteria

| Criterion | Result | Inspected evidence |
| --- | --- | --- |
| 1. Exact money in all six workflows | pass | Full isolated workflow suites cover strict Decimal parsing, exact differences, tolerances, allocations, residuals, and rendered values. |
| 2. Qualified adapters before source-derived prepared rows | pass for declared adapters | Source and reviewed-decision receipts precede authoritative rows; unsupported inputs abstain. |
| 3. Unsupported layouts emit no plausible prepared facts | pass | Negative fixtures cover ambiguous, malformed, truncated, unsupported, stale, and unreviewed sources. |
| 4. Case-origin assumptions removed or scoped | pass | Filename and layout heuristics remain advisory or are bound to named adapters and reviewed mappings. |
| 5. Shared assurance where genuinely common | pass | Exact money, canonical serialization, receipts, gates, ledgers, relationships, envelopes, and bounded transactions use the shared Vera assurance package. |
| 6. Report Builder material-number closure | pass | Every reviewed material number closes from source through prepared schedules to Markdown, XLSX, and DOCX; formula and rendered-value forgeries fail. |
| 7. Independent gates prevent downstream promotion | pass | Source, preparation, reconciliation, semantic, reporting, and publication states remain separate where applicable; `final_ready` cannot be forged by review acceptance. |
| 8. Representative holdouts and adversarial cases | partial / no promotion | Adversarial suites pass. The historical sealed Journal-Bank v7 holdout remains immutable `NO-GO`; the independently authored sealed v5 successor scored 23/24 and exposed a genuine source-membership outcome defect. The defect is remediated, but its exposed replay cannot promote M7. A separate additive tabular-v7 locale/summary contract is now frozen and implemented: the private real-source rerun qualified 202 bank and all 8,141 journal movements and replayed 83,826 material values, while unmatched rows correctly withheld reconciliation. That known source family is diagnostic evidence only and cannot promote v5 or the additive v7 contract. Concordato now has a bounded real-PDF case with a separately authored attester's report and judicial commissioners' report; only three selected pages were checked and no qualified independent reviewer validated the full population. |
| 9. Review artifacts and judgment boundaries | pass | Deterministic controls do not classify legal, tax, support-sufficiency, narrative, or professional conclusions. |
| 10. Exact rollback without child-accessible recovery authority | pass within bounded contract | Current workflows restore exact canonical bytes and modes after retained attacks. This is not an operating-system sandbox. |
| 11. Privacy, regression, release, and Marketplace checks | pass | The complete Vera privacy register is current; focused, interaction, release, and package gates pass; the final uncapped importlib traversal executed 7,373 tests with 7,364 passed, 9 dependency-gated skips, and no failures or errors; `src` coverage reached 80.32%. |

## M1-M7 disposition

| Module | Result |
| --- | --- |
| M1 precision and abstention | pass for declared workflow contracts |
| M2 reviewed mappings and relationship perimeters | pass |
| M3 receipts, gates, and fresh replay | pass |
| M4 native output addresses and physical closure | pass |
| M5 reviewed formulas, residuals, and forbidden inference | pass where applicable |
| M6 source eligibility and zero rows after failed qualification | pass |
| M7 independent promotion evidence | `NO-GO` for Journal-Bank promotion after an independently authored sealed successor scored 23/24; the later additive-v7 private source diagnostic is complete and replayable but not blind or promotional; Concordato has separate-document numerical support but remains partial pending full-population qualified independent review |

No orchestrator was added.

## Verification record

The six workflow implementations are separate CLI/MCP process boundaries.
Their complete isolated suites collected 1,220 cases without failures or
errors; Journal–Bank accounts for 89 dependency-gated skips:

| Workflow | Result |
| --- | --- |
| Audit Reconciliation | 308/308 plus 32/32 separate root attacks |
| Journal Sampling | 160/160 |
| Check Entries | 189/189 |
| Journal-Bank Reconciliation | 317/317 collected; 228 passed and 89 dependency-gated skips; 0 failures/errors |
| Report Builder | 142/142 |
| Concordato Plan Review | 104/104 |

Additional gates:

| Gate | Result | Evidence SHA-256 |
| --- | --- | --- |
| Shared/interaction/review-contract gate | 213 collected; 158 passed, 55 dependency-gated skips; 0 failures/errors | `da433647a6662fe08488cd66c938fe8583a0ea86a7e9c29c3390789519e805fa` |
| Privacy and assurance-package tests | 23 passed | `96ef6078f32c155a8ceb48d8ced69d636e75ffa0c4047e42df1d52157b7b6ce8` |
| Package and update-notification release tests | 270 passed | `caef8a026d51d641707e16fd4f48ddf579620a9fe0ca2f92269f07e3d11e478b` |
| Corrected test-contract regression | 587 collected; 482 passed, 105 dependency-gated skips; 0 failures/errors | `00ccd035d766284a38ad451e3dc4826789098826e7485ea8a4cc012d0fdab930` |
| Non-blocked local-workbench controls | 10 passed; 3 classified production controls deselected | `2f5675f8626a3e90173ba83dd3f168f331f4071615953b0e8b1b1d09a326dd60` |
| Complete Vera privacy register | 21 passed; deterministic validator current | `72162c137d031ad7d809dbde02cc53ca94885ed8d07eced639f2ad24ff9a5ab3` |
| Complete package gate | 253 passed | `de1dce70994b498e77d32237cfc2637b681e0fb49a76790ec8551be3dc32cef6` |
| Uncapped final repository traversal | 7,373 tests; 7,364 passed, 9 dependency-gated skips; 0 failures/errors | `b4515aebc2172b7894f4d894faf3cdfe8410090bd20be8c9fa51ae079357c72e` |
| Repository `src` coverage | 80.32%; required threshold 80% | coverage traversal JUnit `c94deb613f5998ccc53afcab05a3851fdefd5c717deadbcd16237c078bcc0733`; its sole stale-fingerprint failure was reviewed and closed before the green final traversal |
| Marketplace source-drift check | pass | install and ChatGPT-upload projections both match repository source |

The repository collection boundary was repaired only in tests: canonical
repository module identities and import paths are restored across collection
and runtime, vendored module names no longer replace those identities, and a
test-only stub supplies the deleted legacy UI import. Stale self-contained
tests for PDF parsing, Pareto classification, charting, documentation, date
parsing, layout, the bank OCR boundary, stage-count semantics, `BytesIO`
position semantics, and deterministic category ordering were corrected. A
mixed sequence covering the formerly colliding areas passes, and
`pytest --collect-only --import-mode=importlib` succeeds for more than six
thousand tests.

The earlier traversals retained in `classified-production-defects.md` exposed
eight production or source-contract root causes: slope-label aggregation,
Clara privacy freshness, the real new-client fixture, video-guide scope,
schema-2 empty-decision binding, browser intake sanitization, synthetic-fee
authority, and adaptive progress ordering. Each was remediated with focused
negative and affected-file regressions. The final uncapped traversal contains
no deselection and no failure.

The coverage traversal executed the same 7,373-test population and reached
80.32%. Its only failure was a Journal Sampling privacy fingerprint made stale
by the final interpreter-selection correction. The changed source was reviewed,
the fingerprint was refreshed through the privacy workflow, the complete Vera
privacy gate passed, packages were rebuilt, and the subsequent uncapped
traversal was green.

Same-interpreter co-loading of the six plugin source trees is not a production
contract. Each uses local execution-boundary module names such as
`implementation_bootstrap`; Python module caching can bind a later test to an
earlier plugin. Marketplace CLI/MCP execution uses one process per plugin.

## Marketplace artifact

- Source: `plugins/vera`
- Upload artifact: `plugin_packages/vera/vera-chatgpt-upload.zip`
- Size: 2,218,155 bytes
- Files: 399
- ZIP SHA-256:
  `2ba86cf5cea99d1c3df30f1d5ab600c9545afecc28d5c096050b014c08c12ce0`
- First/root manifest: `.codex-plugin/plugin.json`
- Projected Vera version: `0.1.34`
- Bytecode/cache or nested-wrapper violations: none

The ZIP is structurally ready for Marketplace upload and matches current
repository source. Marketplace acceptance after upload is not yet observed.

## Remaining actions

1. Commission a new genuinely independent, unseen Journal-Bank v6 holdout bound
   to the exact v5 contract and production schemas. Do not reuse or relabel v7
   or the exposed 23/24 successor. Do not use the already exposed private
   localized-date source family as that successor. The exact handoff is ready in
   `journal-bank-v6-holdout-commission.md`.
2. Have a qualified independent reviewer compare the full Concordato candidate
   population or a separately prepared workpaper before claiming source
   sufficiency or broad real-plan generality. The review commission is ready in
   `concordato-full-population-review-commission.md`.
3. Deploy the already-corrected public update manifest through the approved git
   PR workflow; it is updated locally to published Clara `0.1.112` and Vera
   `0.1.31` but was not deployed from this dirty worktree.

Until items 1-2 close, the strict representative-evaluation goal remains open even though the
Marketplace package itself is upload-ready.
