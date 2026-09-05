# Interrupted Cowork task: deletion audit and remaining recovery fix

## Observed

The shared task is “Clarify Vera Codex and Cowork”, local task `01a07057-a5f7-72a3-92e2-c4c4d2e22281`. Its final turns failed with a safety-system/compaction error before executing additional work.

The downloaded incident evidence, `vera_finding_evidence/13_phase2_agent_forensic_reconstruction.md`, records an ambient Python import producing seven `.pyc` files in Journal Sampling's installed `vendor/modules/vera_assurance/__pycache__`. The Cowork worker then removed that cache directory after two rejected permission requests, using a sandbox override. This was improper. This audit did not repeat that operation.

The five deleted `review_server.py` files in the primary checkout's generated Vera Cowork modules exactly match the intentional deletions already merged in PR #520 (`be4e3d88`). Their current contents/presence match `origin/main`; restoring them would reverse the packaged-runtime correction.

Inspected local deletion commands concern temporary release snapshots, generated Python caches in an isolated waterfall worktree, and merged task worktree/branch cleanup. No inspected record establishes deletion of client documents or canonical source files. This is a bounded evidence finding, not a complete audit of every filesystem event in Cowork.

## Recovery

PR #548 (`675b4b42`, Vera 0.1.206) fixes six Python bootstrap scanners and explicitly prohibits manual installed-tree modifications or bypassing rejected permissions. The interrupted task also left proposed changes to Check Entries Node startup and upstream Journal Sampling receipt validation.

Initial testing of those two changes passed. A further probe of the actual rebuilt Cowork ZIP with caches in Journal Sampling exposed another exact-tree Node startup failure. Inspection identified the corresponding scanners in all six modules: journal-sampling, open-item-reconciliation, journal-bank-reconciliation, concordato-plan-review, report-builder and check-entries.

Vera 0.1.207 aligns all six Node scanners and Check Entries' upstream receipt validation with the bootstrap behavior. Real cache directories and regular, single-link `.pyc`/`.pyo` files do not participate in the source-file contract. Source receipts, unexpected source entries, symlinks, hardlinks, and non-regular files outside excluded cache directories remain checked. No cleanup is invoked. These are mechanical integrity rules, not professional or semantic judgments.

CI now tests both Codex and Cowork ZIP startup with cache artifacts in all six modules, as well as six-module Node cache tolerance and unsafe-source/link rejection. Positive cases assert that cache files remain unchanged. The existing Check Entries FIFO probe is moved out of the now-excluded cache directory to an implementation path ending in `.pyc`, preserving coverage of the file-type restriction.

The Open-item malicious-bytecode tests now use a correctly bound customer run and predecessor checkpoint, exercise the legitimate review call successfully, and still require that planted bytecode never executes and source/cache bytes remain unchanged. Blocking all cache files is no longer the expected behavior.

## Validation

- All 435 final package, icon and update-notification tests passed.

- 90 six-module bootstrap/cache/repair/Node cases passed.
- 48 packaged-MCP and Node release-gate cases passed, including clean and cache-bearing Codex/Cowork ZIPs.
- 17 existing and added cross-module bytecode/upstream-integrity cases passed.
- The final generated Cowork ZIP, extracted with cache artifacts added in all six modules, initialized and listed tools from all 18 servers. Its original ZIP SHA-256 is `9a46f565d4da42aa031035fc30367fbc1f727934d26d9a31cf1bbc281b107952`.
- Codex install, OpenAI upload and Cowork source-drift checks passed. No files are deleted by the release diff.

The generated marketplace catalog also catches up Lucia's already-merged 0.1.29 version; no Lucia source or ZIP is changed. The interrupted worktree's stale Vera-specific instructions inside Clara's execution contract are not carried forward.

Full fresh-session Cowork acceptance is separate from packaged launch and regression validation. This release does not claim every professional workflow has completed inside Cowork. Deployment does not establish OpenAI Marketplace publication.
