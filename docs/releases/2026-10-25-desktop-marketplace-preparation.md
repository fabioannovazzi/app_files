# Desktop package preparation, 25 October 2026

Prepared from the `codex/https-reporting` release source, with one version per
product across Codex, Cowork, Antigravity and the separate OpenAI upload:

| Product | Version | Codex/local MCP registrations | Remote MCP registrations |
| --- | --- | ---: | ---: |
| Vera | 0.1.492 | 25 | 0 |
| Clara | 0.1.347 | 2 | 0 |
| Lucia | 0.1.175 | 6 | 0 |

Cowork omits the OpenAI course-chat service, giving 24, 1 and 5 local
registrations respectively. Ordinary HTTPS reporting is retained; zero remote
MCP does not mean zero network traffic.

## OpenAI ZIPs

Use `plugin_packages/clara/clara-chatgpt-upload.zip` and
`plugin_packages/lucia/lucia-chatgpt-upload.zip` for the requested Marketplace
preparation. The native install ZIPs remain separate. Public uploads include:

- Agent Plugins 1.0 root `plugin.json` and `mcp.json`, plus the existing
  compatibility manifests needed by installed helpers.
- Explicit `stdio` transports, `${PLUGIN_ROOT}` launch paths and desktop
  execution metadata, with the existing local service inventory preserved.
- Source-owned listing text, icons, support/privacy/terms URLs, selected
  reviewer prompts and release notes. No invented publication country
  selections, commerce declarations, reviewer credentials or demo URL.
- No root `.app.json`, non-null app declarations or lifecycle hooks.

The current OpenAI instructions explicitly direct allowlisted local-MCP
publishers to the portal's **Skills only** upload option. This is the portal
category; it does not describe the package as containing no local MCP.

References inspected on 25 October 2026:

- <https://developers.openai.com/plugins/deploy/desktop-only>
- <https://developers.openai.com/plugins/build/plugins>
- <https://developers.openai.com/plugins/deploy/submission>

The product, support, privacy and terms URLs returned HTTP 200 without login.
The privacy URL redirects to the product's zero-retention policy. Source
checks and packaged MCP startup are mechanical evidence, not proof of a clean
installed desktop conversation or Marketplace approval.

## Remaining submission evidence

No Marketplace draft, upload, submission or publication is part of this task.
The submitting organization's local-MCP allowlisting has not been verified.
The user has no demo recording; `demo_recording_url` remains absent. The saved
portal version's review requirements, any required per-server review cases,
and clean installed-desktop workflow acceptance have not been verified. The
three included reviewer prompts are drafts, not passed review cases.

## Release check repair

The previous release CI failed on a stale teaching-course review digest.
All 58 exact historical course snapshots were located by their recorded SHA256.
Their complete payloads, excluding `sources`, are identical to the current
lessons. The records preserve all original editorial and output judgments and
add a bounded source-inventory rebinding. The proof is in
`2026-10-25-desktop-course-source-bindings.json`. Fresh native demo/practice
execution remains required by the existing CI gate. No review requirement was
disabled and no new learner or professional acceptance was claimed.

The first local rebuild reached the Antigravity stage before the course-record
refresh made the governed privacy fingerprints stale. After inspecting that
metadata-only change, the local-onboarding and learn-with-clara fingerprints
were refreshed without altering their data-flow declarations. The final
all-host rebuild supersedes that interrupted build.

## Verification completed

The canonical all-product build and all-host source-parity checks passed.
The final Clara/Lucia upload metadata and both official JSON schemas were
checked again after rebuilding those two uploads. All eight local servers
returned real MCP initialization/tool lists: 11 Clara tools and 74 Lucia tools,
all with boolean read-only, destructive and open-world annotations.

The package/update regression run recorded 429 passes, one skip and two failed
new metadata assertions. Those assertions exposed that the native package's
submission-directory exclusion also hid the new upload metadata. The builder
now reads that metadata directly from its source file. All 24 affected checks
then passed, including the two prior failures; both rebuilt uploads passed
source-parity and schema validation. The unchanged teaching-review/icon source
checks passed 39 tests. Black, Isort and Mypy passed; Bandit found no medium or
high issue in the changed Python builder.

The ZIPs copied into the primary checkout are generated from this release
worktree, not from the primary checkout's unrelated uncommitted source edits.
`plugin_packages/desktop-release-preparation.json` records the exact source
commit and archive hashes. Website deployment and Marketplace actions are
separate and have not been performed by this preparation task.
