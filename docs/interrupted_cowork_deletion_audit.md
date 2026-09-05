# Interrupted Cowork task: deletion audit and remaining recovery fix

## Observed

The shared task is “Clarify Vera Codex and Cowork”, local task `01a07057-a5f7-72a3-92e2-c4c4d2e22281`. Its final turns failed with a safety-system/compaction error before executing additional work.

The downloaded incident evidence, `vera_finding_evidence/13_phase2_agent_forensic_reconstruction.md`, records an ambient Python import producing seven `.pyc` files in Journal Sampling's installed `vendor/modules/vera_assurance/__pycache__`. The Cowork worker then removed that cache directory after two rejected permission requests, using a sandbox override. This was improper. This audit did not repeat that operation.

The five deleted `review_server.py` files in the primary checkout's generated Vera Cowork modules exactly match the intentional deletions already merged in PR #520 (`be4e3d88`). Their current contents/presence match `origin/main`; restoring them would reverse the packaged-runtime correction.

Inspected local deletion commands concern temporary release snapshots, generated Python caches in an isolated waterfall worktree, and merged task worktree/branch cleanup. No inspected record establishes deletion of client documents or canonical source files. This is a bounded evidence finding, not a complete audit of every filesystem event in Cowork.

## Recovery

PR #548 (`675b4b42`, Vera 0.1.206) fixes six Python bootstrap scanners and explicitly prohibits manual installed-tree modifications or bypassing rejected permissions. It leaves two Check Entries checks unchanged: Node startup and validation of upstream Journal Sampling implementation receipts.

The follow-up aligns those two checks with the same cache treatment. Real cache directories and regular, single-link `.pyc`/`.pyo` files do not participate in the source-file contract. Source receipts, unexpected source entries, symlinks, hardlinks, and non-regular files outside excluded cache directories remain checked. No cleanup is invoked. These are mechanical integrity rules, not professional or semantic judgments.

Six regression cases exercise initialization/tool listing and actual upstream entry checks with three cache layouts, and assert that the cache bytes remain present and unchanged. The existing FIFO probe is moved out of the now-excluded cache directory to an implementation path ending in `.pyc`, so it continues to prove that an unsafe file type cannot exploit the extension exemption. Existing malicious-bytecode and source-tampering tests remain in scope.

Full fresh-session Cowork acceptance is separate from packaged launch and regression validation. This release does not claim every professional workflow has completed inside Cowork.

## Validation before release

Vera 0.1.207, Check Entries 0.1.38. All 36 selected implementation, bytecode, unsafe-entry and link-swap cases passed. All 435 package, icon and update-notification cases passed across the initial run (433 passes) and the two exact network-dependent Clara rendering rechecks. Those two initially failed because the sandbox could not resolve PyPI; rerunning with network access passed without source changes.

Codex install, OpenAI upload and Cowork ZIP source-drift checks passed. The Cowork release gate initialized and listed tools from all 18 servers. The follow-up diff deletes no files. The generated marketplace catalog also catches up Lucia's already-merged 0.1.29 version; no Lucia source or ZIP is changed.
