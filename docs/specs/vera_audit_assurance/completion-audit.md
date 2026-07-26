# Vera audit-assurance completion audit

Date: 2026-07-26

Status: Workflow remediation and working-tree release artifacts verified;
assurance program not fully promoted.

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
| 11. Privacy, regression, release, and Marketplace checks | pass for the Vera source and working-tree package surfaces; repository-wide runtime gate not current | The complete Vera privacy register is current; all 1,239 workflow cases, 248 cross-workflow cases, and 270 working-tree release-surface cases pass. Both repository archives pass source-drift verification. Repository collection is clean at 7,398 tests. A current repository-wide runtime attempt was stopped at 22% after 31 failures. The sample was subsequently classified: 12 stale or isolation-dependent test defects now pass, 10 tests skip explicitly when optional local PDFs or generated PDP parquet caches are absent, and 9 failures remain in legacy UI tests outside the active product scope. The historical 7,373-test result is not reused as proof of this source state. |

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
Their complete isolated suites collected 1,239 cases without failures, errors,
or skips:

| Workflow | Result |
| --- | --- |
| Audit Reconciliation | 308/308 |
| Journal Sampling | 161/161 |
| Check Entries | 189/189 |
| Journal-Bank Reconciliation | 318/318; Node-backed cases enabled |
| Report Builder | 142/142 |
| Concordato Plan Review | 121/121 |

Additional gates:

| Gate | Result | Evidence SHA-256 |
| --- | --- | --- |
| Audit Reconciliation full workflow | 308 passed | `36ae3330adc852cc945db2e6cec6dadbc0016c5cb0d94bad01639512655d41cd` |
| Journal Sampling full workflow | 161 passed | `cd4182022689b43a3f967cce2f8f47fb419b39890a4832b8d6ddf61f09053946` |
| Check Entries full workflow | 189 passed | `a1ef7ead40b76cd6c9a1637de4c0f8917216369e25ca00c9c63830a2a453de07` |
| Journal-Bank full workflow | 318 passed; no skips | `c76f9b2b743b0fe7c7a8e9e92bf2b524af37ee463d3422d6b3a613e985168ebe` |
| Report Builder full workflow | 142 passed | `74ec7c6da41fbb3dff82c3688a219c669a8b04a369075f16619eb86a1f990e07` |
| Concordato full workflow | 121 passed | `dc2a7060d0b98a92061207ead76543e7b4dfb7c53339fb11a0fbc35d9f096857` |
| Shared/interaction/review-contract gate | 248 passed | `5d6c4f1044b267a748cae29f3458a53606b650bf6eb29b9940e5cc0ef20025bc` |
| Complete Vera privacy register | 21 passed; deterministic validator current | `8dd6b3b1b4b5aef616446399e70cc6fd2befe524fbb82ddd3347a8ab7209c8ef` |
| Working-tree package and update-notification release surface | 270 passed | `a39a29472f9a8738753dcba56992b4f60b8acdad4b5d041f452bed4b44913fb7` |
| Disposable source-projection package check | 270 passed | `7250055879c85f5131cc52e26d653e3d409bad2bc2637b2265ac71f4e04516c8` |
| Shared assurance branch coverage | 81% overall; exact-money module 95% | coverage data `51fd6f7125e7575f3c3d720cf45360453cb5de21d295a327bc6166e08f502b3c` |
| Repository collection boundary | 7,398 tests collected; 0 collection errors | direct clean collection on 2026-07-26 |
| Post-classification failure replay | 62 passed, 10 dependency-gated skips, 0 failures/errors | JUnit SHA-256 `02829e6c1a8f4f4b63cf49463302c46827e9b796452790e9e2ebf536054261cc`; the skips require two optional local PDFs or the generated PDP post-fill parquet cache |
| Legacy UI baseline | 1 passed, 9 failed | JUnit SHA-256 `4d7c875e595fc6517227bcef21b6bbbe1fec26c22984f86c015a9af10875f690`; retained as an explicit out-of-scope baseline rather than hidden or repaired |
| Repository-wide runtime traversal | not current | the 31-failure sample is classified and replayed, but a new uninterrupted all-test run has not been completed after the test-isolation corrections |
| Static/type/security gates | changed files Black/Isort-clean; `mypy src/` passed 143 files; Bandit found no medium/high issues in `src` or changed assurance code | whole-tree Black/Isort remain pre-existing red baselines: Black identified 271 files |
| Marketplace source-drift check | pass in the repository release surface | both install and ChatGPT-upload archives build and verify against current source |

The repository collection and execution boundaries were repaired only in tests: canonical
repository module identities and import paths are restored across collection
and runtime, environment mutations are restored after collection and every
test, vendored module names no longer replace those identities, and a test-only
stub supplies the deleted legacy UI import. Stale self-contained tests for PDF
parsing, Pareto classification, charting, documentation, date parsing, the bank
OCR boundary, stage-count semantics, `BytesIO` position semantics, deployment
permission configuration, and deterministic category ordering were corrected.
PDP review API tests now state their generated-cache prerequisite explicitly
instead of failing with an unexplained 503. A mixed sequence covering the
formerly colliding areas passes, and
`pytest --collect-only --import-mode=importlib` succeeds for 7,398 tests.

The earlier traversals retained in `classified-production-defects.md` exposed
eight production or source-contract root causes: slope-label aggregation,
Clara privacy freshness, the real new-client fixture, video-guide scope,
schema-2 empty-decision binding, browser intake sanitization, synthetic-fee
authority, and adaptive progress ordering. Each was remediated with focused
negative and affected-file regressions. The former 7,373-test/80.32% result is
retained as historical evidence for its earlier source state only. It is not
presented as a current green repository-wide runtime result.

The current remediation also closed two newly reproduced production defects.
An explicit thousands-separator role can no longer be silently reinterpreted as
a decimal role; malformed values abstain before authoritative rows. Concordato
now keeps immutable semantic evidence inside the predecessor assurance
envelope, treats the regenerable summary DOCX as a mutable presentation
artifact closed by the final-output successor, and writes reviewer edits to
envelope-bound artifacts as separate revisions.

Same-interpreter co-loading of the six plugin source trees is not a production
contract. Each uses local execution-boundary module names such as
`implementation_bootstrap`; Python module caching can bind a later test to an
earlier plugin. Marketplace CLI/MCP execution uses one process per plugin.

## Marketplace artifacts

- Source: `plugins/vera`
- Source-derived install archive: 2,326,133 bytes, 434 files, SHA-256
  `82d713daeb24d1d815820b1949ebeb7791afa23eb9f23a93b5d25e3b3cb35bf2`
- Source-derived ChatGPT upload archive: 2,246,597 bytes, 401 files, SHA-256
  `6fc915541a7d6326d459eafb8ad1a6d32d5949c9589ab47de2fa0253f1c6d4d6`
- First/root manifest: `.codex-plugin/plugin.json`
- Projected Vera version: `0.1.40`
- Bytecode/cache or nested-wrapper violations in the declared upload: none

Both source-derived archives were rebuilt in the repository and pass
byte-for-byte source-drift checks. The previously deleted tracked install
archive is restored, the tracked ChatGPT upload matches the current projection,
and the undeclared wrapped `0.1.39` archive was moved to the owner's Trash under
`vera-chatgpt-upload-wrapped-0.1.39-20260726.zip`, where it remains recoverable.
Marketplace acceptance after upload is not observed.

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
3. Deploy the corrected public update manifest through the approved git PR
   workflow; Vera is updated locally from `0.1.38` to the installed Marketplace
   version `0.1.40`, but this audit did not deploy it.

Until items 1-2 close, the strict representative-evaluation goal remains open.
The source-derived Marketplace archives and the repository package directory
are release-ready.
