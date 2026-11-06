# Reconciliation and Archive incident repair — 6 November 2026

## Observed incidents

Production received report `df59288c-0bc1-4c63-b2a4-f0349aa76a7e` at 16:26 Paris. Vera 0.1.579 on Codex/macOS rejected a semantic worker response because an evidence field was not populated. The failing response and its token receipt were discarded. The exact field and verdict cannot therefore be reconstructed. Later artifacts in the original reconciliation show validated retries and an exhaustive review state; this does not by itself close the original incident.

Reports `3f039d55-04ab-4596-aa47-b9ea997675f6`, `9793f579-c72e-4e53-a604-1104001213b9` and `dcc67f10-1af2-4c48-80c2-32b5797029df` came from the enabled Vera 0.1.573 service. The original chat confirms two failed previews of admitted XLS inputs and a third failed read of `outputs/execution-logs/seal-review.log`. That installed measurement adapter lacks XLS support; current main already contains it. Both the installed and current reader omitted the `.log` extension. The run retains failed measurements even after an adapter becomes available. The reader's fallback can return data but reports the resolved measurement as unavailable, including when reopening a closed run.

The additional mapping-receipt rejection at 16:18 concerned an agent-authored exclusion list naming a column absent from the inspected monetary-column set. The original chat corrected the list and continued. The subset check is retained; this repair does not silently accept an uninspected mapping exclusion.

## Changes and justification

- A semantic abstention can cite populated evidence from its bank row and eligible neighboring ledger rows. A suggested match remains restricted to the selected pair. Edge membership and nonempty fields are mechanical checks; the model still decides whether evidence supports a conclusion. A field absent from all eligible records remains rejected.
- Completed worker response, events, stderr and observed usage are retained before semantic acceptance. This is the same narrow repair prepared in PR #961. Invalid answers remain unaccepted and cannot modify strict reconciliation results.
- UTF-8 `.log` artifacts use the existing bounded text-line reader, with the same offsets, limits, source hash and output-size checks.
- An Archive read retries a failed measurement using exactly the retained source SHA-256. Only a failed measurement may become complete in an active run; identity, role and source bytes remain fixed. The previous error and recovered counts are retained as a local event in the same transaction.
- Closed runs retain their original source records and sealed reports. A subsequent successful read creates a separate local delivery receipt.

## Verification and boundaries

The new regressions first reproduced three valid abstention failures and two stale-measurement failures. All seven initial regressions then passed, including rejection of changed input bytes and wholly absent evidence fields.

The Archive suite passed 335 tests with 91.84% coverage across the changed reporting modules. After adding log support, the final focused Archive suites passed 134 tests at 88.46% coverage, including the measurement adapter. A selected semantic subset passed 80 tests but reached only 68.44% coverage. The full reconciliation run exercised 494 tests: 488 passed and six hit the test harness's ten-second MCP subprocess budget. Coverage across journal_bank_core and semantic_review was 82.00% (3,763 of 4,589 statements); the semantic module alone was 74%. All 36 cases in the affected MCP groups then passed with the corrected test budget, including all six timed-out cases. This accounts for all 494 unique tests across the full run and focused rerun; fresh final-head CI remains required.

The current reader measured 75 and 78 rows in the original two XLS files. An isolated copy of the original completed Archive run returned both requested nine-row, four-column previews, recording separate delivery receipts while preserving historical measurement failures and sealed report bytes. An isolated copy of the exact failed log read also returned the selected ten lines and its own late-delivery receipt. These checks verify retained original bytes and recovery behavior, not an update of the user's still-running service.

Local `codex plugin list --json` reports Vera `0.1.573` enabled as `vera@mp-vera`, Clara `0.1.382` and Lucia `0.1.208`. Remote catalogue access was unavailable to that command. Fresh installed-session acceptance and a signed server receipt remain unverified. Production incidents remain open; no successful original-host outcome is manufactured.

The larger reconciliation run encountered six test-harness timeouts, all in the same MCP helper with a ten-second process budget. The first isolated multi-operation case passed in 12.9 seconds with a sixty-second budget; another passed independently in 12.0 seconds. The shared test helper now allows sixty seconds, retaining explicit per-test overrides. Production execution limits are unchanged. Package drift after a final privacy-wording correction is resolved by rebuilding the generated artifacts; it does not establish installed-host acceptance.

The package integrity and update-notification suites passed 415 cases and skipped two environment-dependent checks; one source/ZIP mismatch after the final privacy wording correction passed after regeneration (416 passing unique cases across run and rerun). Black, Isort, Mypy and Bandit checks passed for the changed source and tests. Final all-host source/package parity is recorded in the PR.

## Privacy and release records

No new source fields, recipients or network destinations are introduced. Source-measurement retries and recovery events remain local. Original source hashes, active measurement recovery, closed-report preservation and rejected-worker usage are checked separately from professional task completion. Public data-path descriptions remain applicable; the changed engineering controls and source fingerprints are refreshed.

Course source inventories were regenerated. Every non-source course field was compared with current main and the independently reviewed Archive-repair candidate. Historical editorial/output judgments remain historical; final CI must supply fresh native executions bound to the updated source inventory. The Geneva function inventory retains exactly the same 55 skill entries; only its release-manifest binding changes.

Candidate versions: Vera 0.1.585, Clara 0.1.388, Lucia 0.1.214 and journal-bank-reconciliation 0.1.84. Package/source parity, CI, merge/deployment and installed-session behavior are separate acceptance stages. No Marketplace publication is requested or performed.

## Integration of the merged tutorial repair

While this PR's CI was running without failures, main advanced to `0a73afa8c213eeea728f296b7df6cd5d2a366871` (PR #959). The integration preserves the exact source implementations of both repairs: this PR's four changed reporting/semantic files and main's `archive_core.py` and `local_onboarding_case.py`. Conflicts concerned generated artifacts, release identities, source fingerprints and historical course-review records. Both sets of review notes are retained.

Only three course source inventories required a new combined binding: Open-item reconciliation, Studio Archive and Studio document format. Every non-source course field matches both reviewed heads. The regenerated course catalog initially made two privacy source fingerprints stale; refreshing those bounded source records and regenerating contracts resolved the check. No lesson content or professional acceptance claim was added.

Combined Archive/recovery/tutorial regressions passed 137 tests at 88.71% coverage. All 80 selected semantic-review cases passed. The rebuilt combined packages and fresh CI head must be verified before merge; the earlier head's CI is historical evidence only.
