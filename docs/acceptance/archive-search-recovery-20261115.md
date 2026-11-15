# Vera Archive search recovery — 0.1.648

The installed 0.1.647 document search rejected all searches when its saved index fingerprint described two top-level scopes and the current configuration included a third. Observed before repair: 20 documents, 88 chunks, last refresh 2026-11-15T08:31:10+00:00, index_requires_refresh=true. The error was reproduced in the supplied panel screenshot for `credito`.

The native search now validates the requested client or explicit whole-archive selection, checks freshness, and conditionally invokes incremental local indexing. The shared writer lock covers a second freshness check after synchronizing the session's scope view, so concurrent recovery reuses the first completed refresh. Healthy search retains its index; source documents are never rewritten. Opening revalidates membership in the same scoped query and checks current file bytes. Failures are not treated as empty results.

This includes the previously installed but unmerged 0.1.647 document-search UI and its tests. The base includes the existing chat-association commit 62d312f32; that dependency must be reconciled before merging. Unrelated primary-checkout and other-task worktrees are untouched.

Observed validation:
- Native navigation and search-continuity suites passed, with five Windows-only skips on macOS. Regressions cover missing index, newly added scope, new-session configuration versus old index, client isolation, changed bytes, unknown client, and concurrent recovery (four calls, one refresh).
- Archive component and concurrency suites passed.
- JavaScript syntax, changed navigation mypy/Bandit, formatting and import checks passed.
- Codex ZIP source parity passed.
- Installed through scripts/install_local_vera.py as vera@mp-vera 0.1.648, package 0a8633729a35c76d20d4884b30fd6e65f80dc228f428d48591541d24a01416ff.
- A fresh installed local MCP process searched the real archive for `credito`, returned six results with index_requires_refresh=false, and opened `2026-07-06 - Cumulo Transizione 5.0 e contributo ISMEA.pdf` with source_verified=true and ISMEA in its passage.

Blocks and recovery:
- Direct helper invocation was refused with “Open the workspace through its local MCP service”; used the supported MCP entry point successfully.
- Native Computer Use access to Codex was refused; no alternate native-control method was used.
- After installation the old chat's MCP connection failed to spawn. The old 0.1.647 cache directory is gone; the referenced Node executable exists. A fresh chat/host connection is needed. Installed-process validation is not visual acceptance of the updated panel.
- Broad package-suite outcome and other host builds are still pending at this checkpoint.

Privacy outcome: reviewed the new local indexing and app-only result boundary and refreshed dependent source contracts. The operation introduces no model call or external recipient. App metadata contains excerpts; host UI inspection can expose visible text to the host model. No professional pipeline run was created, and no per-run privacy-report delivery was demonstrated by this navigation repair.

No Marketplace upload or publication, merge, or server deployment was performed.
