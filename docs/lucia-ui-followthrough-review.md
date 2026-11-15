# Lucia UI follow-through review — 0.1.254

The Archive panel previously sent users to a new chat even when the matter already had documents or saved conversations. The matter-review panel saved decisions without a direct continuation action, and studio instructions presented secondary file and configuration controls alongside the main work.

## Changes

- Archive now reads the selected matter through the maintained archive API, lists saved documents and existing conversation links, and opens an exact verified document reference. Other formats and revisions are expandable. Missing files and chat links remain visible; a new chat is a secondary action.
- Matter review now offers **Continue in chat** for the current saved review. The explicit request identifies the run directory, review hash and saved-decision hash. Unsaved edits hide the action. Saving does not apply decisions or accept an engagement; a host without messaging shows a copyable request.
- Studio instructions show name, purpose, checks and positions directly. Workflow options, questions and sources, template/output options and file/version actions use expandable sections. Save is primary until a version exists; Use becomes primary after saving.

All three surfaces remain local MCP Apps. Archive document data stays in app metadata; the explicit matter continuation adds only its locator/hash context to the model message. Privacy source reviews and generated contracts were refreshed for these changes. This is a source/data-path review, not a professional workflow privacy-report delivery test.

## Validation and limits

- Focused Archive, matter, playbook and update-notification regressions pass (54 passed, 2 skipped).
- The wider Lucia/package/update-notification run covered 443 tests: 439 passed, two skipped and two initial failures. Both failures passed on targeted rerun after the corrections below (441 passing tests in total).
- Codex and Cowork package source-parity checks pass, including local MCP startup checks. The final full `build_product_release.py vera lucia clara` run passes course/privacy alignment and Codex, Cowork and Antigravity builds.
- Python formatting/import checks and whitespace checks pass.
- CUA exercised the packaged resources through a clearly labelled synthetic local host. Real local MCP saves were used for instructions and matter decisions. Archive data and host navigation acknowledgements were synthetic.
- Observed: save enables instruction use; a saved matter review offers continuation; clicking sends the exact saved locator/hash context; editing hides continuation. Archive document/chat clicks issue the expected file-open/link requests. The narrow instruction layout remains usable.
- Native Codex application control was unavailable. Neither native document opening nor existing-chat navigation has been accepted on this host. The standalone Playwright browser regression was updated for the collapsed File/version section but was not run locally; CUA provided the browser interaction evidence.
- Locally installed candidate: `lucia@mp-lucia` 0.1.254 is installed and enabled in local configuration, all 553 packaged files match cache, and seven existing local MCP launchers were updated. The remote catalog also reports Marketplace 0.1.230 as enabled, while local configuration explicitly disables that registration. The current chat exposes an older skill path, so active selection and installed fresh-chat acceptance remain outstanding.

## Recovered validation failures

1. Course/source fingerprints became stale after the shared matter-review asset changed. The course index, review receipt and governed privacy fingerprints were updated after source inspection; package generation then passed.
2. Cowork initially omitted the new UI-label asset. The builder now includes it; subsequent package startup and parity checks pass.
3. A clean worktree lacked cross-product package prerequisites. Those packages were generated before repeating comparisons.
4. The cross-product test expected two Vera-only reconciliation drivers inside Lucia despite their intentional exclusion by the existing builder. The test now excludes exactly those drivers and continues comparing the shared component bytes. Both the corrected Codex comparison and Cowork comparison pass.

5. GitHub release alignment found one additional stale course source binding for `scripts/matter_mcp.py`. Regenerating the catalog corrected that exact binding; course-catalog and privacy-contract checks now pass. The installed package was refreshed and all 553 files verified again.

6. The accounting/reporting CI job caught an outdated matter-panel generator. Native continuation markup, behavior and labels now live in the generator sources. The builder reproduces the already-tested widget byte for byte, without changing the standalone page. The exact failing suite passes locally (254 tests), and course/privacy checks remain clean.

No public deployment or Marketplace publication is claimed by this review.
