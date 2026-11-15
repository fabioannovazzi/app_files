# Vera Archive search recovery — 0.1.648

The installed 0.1.647 document search rejected all searches when its saved index fingerprint described two top-level scopes and the current configuration included a third. Observed before repair: 20 documents, 88 chunks, last refresh 2026-11-15T08:31:10+00:00, index_requires_refresh=true. The error was reproduced in the supplied panel screenshot for `credito`.

The native search now validates the requested client or explicit whole-archive selection, checks freshness, and conditionally invokes incremental local indexing. The shared writer lock covers a second freshness check after synchronizing the session's scope view, so concurrent recovery reuses the first completed refresh. Healthy search retains its index; source documents are never rewritten. Opening revalidates membership in the same scoped query and checks current file bytes. Failures are not treated as empty results.

This includes the previously installed but unmerged 0.1.647 document-search UI and its tests. The current chat-association branch d4eb8ac31 was integrated, preserving its sidebar and teaching fixes; PR #1005 targets #1003 to keep the dependency explicit. Unrelated primary-checkout and other-task worktrees are untouched.

Observed validation:
- Native navigation and search-continuity suites passed, with five Windows-only skips on macOS. Regressions cover missing index, newly added scope, new-session configuration versus old index, client isolation, changed bytes, unknown client, and concurrent recovery (four calls, one refresh).
- Archive component and concurrency suites passed.
- JavaScript syntax, changed navigation mypy/Bandit, formatting and import checks passed.
- Codex ZIP source parity passed.
- Installed through scripts/install_local_vera.py as vera@mp-vera 0.1.648, package 6de0cc293163cb704dde299f87078f3d8e21ec9d027f5f188a78620b97bbbfc3.
- A fresh installed local MCP process searched the real archive for `credito`, returned six results with index_requires_refresh=false, and opened `2026-07-06 - Cumulo Transizione 5.0 e contributo ISMEA.pdf` with source_verified=true and ISMEA in its passage.

Blocks and recovery:
- Direct helper invocation was refused with “Open the workspace through its local MCP service”; used the supported MCP entry point successfully.
- Native Computer Use access to Codex was refused; no alternate native-control method was used.
- After installation the old chat's MCP connection failed to spawn. The old 0.1.647 cache directory is gone; the referenced Node executable exists. A fresh chat/host connection is needed. Installed-process validation is not visual acceptance of the updated panel.
- Broad package suite: 392 passed, two environment-specific skips and five build/version prerequisite failures. All five failed checks passed after supplying the builds and release versions. All three Codex, ChatGPT and Cowork product packages were built locally. CI subsequently identified an outdated version-only localization catalogue binding; every skill entrypoint hash was compared equal before refreshing that binding.

Privacy outcome: reviewed the new local indexing and app-only result boundary and refreshed dependent source contracts. The operation introduces no model call or external recipient. App metadata contains excerpts; host UI inspection can expose visible text to the host model. No professional pipeline run was created, and no per-run privacy-report delivery was demonstrated by this navigation repair.

No Marketplace upload or publication, merge, or server deployment was performed.

Final installed-process verification repeated on package `6de0cc293163cb704dde299f87078f3d8e21ec9d027f5f188a78620b97bbbfc3`: six results, refresh_required=false, zero scan issues, zero document issues, source_verified=true, and the expected ISMEA passage. The UI/fresh-chat limit remains open; this was a fresh MCP process, not a new host conversation.

Additional release observations: the normal release pipeline required rebuilding three course source-hash records and their dependent onboarding privacy binding after the shared Archive edit. The integrated Clara baseline was 0.1.424, so the final source candidate is 0.1.425 (not the earlier temporary 0.1.423); Lucia is 0.1.254. Neither was installed on this host. The GitHub connector refused PR creation (403); the authenticated CLI created draft PR #1005. Automatic approval review initially refused broad cleanup of generated copies; every generated file was subsequently byte-compared with this task's completed package before the narrower cleanup was accepted. No user source or other task work was discarded.
