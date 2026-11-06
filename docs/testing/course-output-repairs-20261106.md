# Course output and Archive handoff follow-up, 6 November 2026

This follow-up is layered on combined course candidate 8633b1d58 (PR 962). Vera 0.1.585 and Clara 0.1.388 are reserved above the intervening Vera 0.1.584 reconciliation candidate. Clara's version accounts for regenerated shared teaching metadata; no additional Clara semantic feature is asserted.

## Repairs

- Treasury scenarios now export separate hypothetical HTML, Markdown, XLSX, daily/weekly CSV and JSON in an immutable hash-keyed tree. The delivery index links those specific exports. The renderer rederives the scenario from its exact baseline and date assumptions before writing. Existing forecast versions and acceptance remain unchanged. Retries reuse verified exports; altered exports are refused. A render failure leaves the baseline and delivery index intact.
- Journal Sampling writes ordinary monetary values as numeric Excel cells while preserving canonical CSV/JSON strings. Values exceeding 15 significant digits or failing decimal roundtrip stay exact text with an explanatory comment. Identifiers remain text. The shared recovery implementation was added to the existing mutation-test matrix, correcting an earlier matrix omission.
- Passive-invoice exception and orphan gross amounts follow the same numeric/precision policy. Matching, semantic packets, worker results and professional conclusions are unchanged.
- Archive Organization's teaching preparation now creates and returns its private archive index, isolated alongside the staged client folder. Its integration test consumes that returned index instead of silently creating the missing index itself. This reproduces and repairs the original inventory handoff failure without replacing the user's configured archive.

## Evidence

- 216 Journal Sampling cases passed, including native workbook readback, assurance, mutation and review transaction checks.
- 11 passive-invoice cases passed, including demo/practice in all five languages and the numeric/large-value regression. Saved real course demo/practice worker results were rendered again without another model invocation; the 488 EUR exception is numeric.
- 63 Treasury cases passed, including scenario readback, unchanged baseline bytes, repeat deduplication, altered-report refusal and render-failure rollback. The original course scenario was independently rederived: 62 daily balances, minimum 16,000 EUR, matching its saved JSON. Its standalone HTML was visually inspected in the in-app browser at the desktop viewport.
- 20 current localized Journal Sampling/Vouching integration cases passed. The Archive Organization private-index repair passed ten demo/practice cases across five languages, including the existing explicitly synthetic review/apply fixtures.
- The original failed Archive Organization demo resumed on the same run after preserving its failure record. Three documents were read, one exact duplicate identified, the actual agent's proposals saved through the native artifact writer, and the pending plan generated. Source MCP view opens its workbench; the run is ready for review. Original-case file moves and professional decisions were not fabricated.

Detailed host proofs and JUnit records remain in the onboarding workspace under `source-retests-20261106` and `work`. They are not published customer files.

## Boundaries and remaining findings

Source tests and package parity do not update the enabled .573/.382/.208 installations or prove a fresh installed Desktop session. No Marketplace publication is authorized.

Read-only reopening was tested against exact run references from retained course execution records, with ambiguous multi-run records excluded rather than guessed. Fifteen native views returned; other records exposed missing native adapters, required canonical case/revision connections, incomplete runs, or persisted report-review authorization failures. These remain separate from numerical success. An earlier preparation-only probe is preserved as diagnostic evidence, not counted as final-course acceptance.

The updated source correctly rejects prior Journal Sampling/Vouching assurance tied to an earlier implementation fingerprint. Existing exports remain unchanged; this is not acceptance of editing or revalidating those old runs with new code. Current-source fresh normalization and handoff cases pass. Native historical-review continuity remains an explicit limitation.

The readable Archive projection still sometimes rejects tutorial client identity. Native panel rendering, Microsoft Excel/Word acceptance, voice, learner comprehension, real professional approval and missing-source completeness are not asserted. Final-head CI and integration of any intervening main release remain required before deployment.
