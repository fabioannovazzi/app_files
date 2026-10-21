# Native reconciliation adapters and pending Archive integration

The evaluation campaign remains paused. These are technical host diagnostics,
source regressions and release checks, not professional or fresh installed-plugin
acceptance. No Marketplace version was uploaded, submitted or published.

## Observed host capabilities

Cowork's installed Claude host exposed `Agent` with `description`, `prompt`,
`subagent_type`, `model` and `isolation`. The observed model enum was `sonnet`,
`opus`, `haiku`, `fable`. Its existing Vera passive-invoice agent was listed with
`Read` only. A synthetic general-purpose child requested as `haiku` returned the
constant probe JSON, agent ID `a72e29132d6221f14`, and zero tool uses. The parent
model remained Sonnet 5.5 Medium. This did not prove enforced tool-free operation,
provider model identity, absence of ambient host instructions, or support for
Claude Code's `omitClaudeMd` in Cowork. The adapter therefore uses the actually
observed restricted-agent format and records these limits explicitly.

Diagnostic chat: https://claude.ai/chat/af6ab534-aac1-4943-a890-2296baeadfe2

Antigravity's installed `agy` exposed headless structured output and a current
model catalogue. `agy models --json` was unsupported; plain `agy models` worked.
A synthetic CLI main-agent probe with `tools: []` still advertised a broad tool
set in its init event. Consequently the implementation does not represent that
CLI route as an isolated worker. The native `invoke_subagent` probe accepted
`TypeName`, `Role`, `Prompt`, `Model: flash`, `Workspace: inherit`. Child
`a7905069-c90d-4368-977c-b779b7e4d364` returned the constant JSON and reached
completion. Its returned transcript contained no child tool calls. The actual
schema also exposed `inherit`, `flash_lite`, `flash`, `pro` model tiers. A model
tier request is distinct from provider-attested model identity.

Primary references inspected:
- https://www.antigravity.google/docs/subagents/
- https://www.antigravity.google/docs/cli/headless/
- https://support.claude.com/en/articles/13345190-get-started-with-claude-cowork

No client data or accounting evaluation case was used in these probes. The
existing enabled installations were not modified. The new packaged reviewer
still needs a fresh installed-host campaign when the user resumes it.

## Implementation boundary

The shared policy prepares a host-specific model preference. The current parent
checks its live tool schema and agent listing, invokes one fresh native child,
retains the exact invocation and completion, then resumes the same command.
Missing capability, incomplete output, reused history, changed packets and child
tool use cannot supply an accepted result. No Codex/provider fallback runs.
Open-item allocations and Journal–Bank resolution use their existing independent
source, quote, perimeter, conservation and threshold checks. Preparing a draft
adds no human approval step.

Native receipts are explicitly parent-reported evidence. They contain no invented
Codex OS canaries, ephemeral-transcript claim or provider attestation. Both parent
and child receive the bounded native request. Their reported exposures are recorded
separately with stable event identities; account retention remains host controlled.

## Pending work integrated

All pending work from `codex/open-item-row-counterparties`, including commit
`e919151e5`, was integrated with the current deployed source. This includes source
and workbook provenance, Archive selected-work fault isolation, recoverable report
completion, attachment access checks and native execution reporting. Merge
conflicts in generated files were resolved by rebuilding them. Source conflicts
retained both partial-payment explanation/provenance and semantic allocations.

## Blocks encountered

- Unsupported `agy models --json`: recovered using the installed plain catalogue.
- CLI main-agent tool declaration did not yield a tool-free init: used the actual
  native subagent route and retained the narrower evidence claim.
- A first Journal–Bank resumption regression found no cumulative completed state
  for a pending packet: resumed from the already validated pending graph and
  retained preparation outputs instead. Both host regressions then passed.
- Source/ZIP parity and combined regression results are recorded in the release PR.

- The initial combined check ran while source and packages were changing. Two
  source integrity checks correctly rejected changed helper bytes; nine package
  checks read the previous packages. Three native process checks encountered the
  nested shell sandbox. All fourteen passed against stable rebuilt files with
  native process permissions. No product gate was disabled.
- Antigravity packaging initially omitted the new reviewer because its Codex
  input bundle does not contain Claude agent files. The builder now explicitly
  projects the canonical reviewer source into Antigravity's native format; all
  three Antigravity product builds verified successfully.
- The Cowork package regression caught Codex diagnostic-launcher directions in
  the projected semantic section. Its host projection now directs the parent
  only to the native Agent handoff and same-run resumption. The regression still
  rejects Codex commands/model names and additionally requires the native route.
- The privacy regression still expected the old unavailable-host wording. Review
  also found the old Codex-only Journal–Bank paragraph beside the new handoff
  explanation. All five translations now describe the supported hosts, while
  retaining packet bounds, unchanged deterministic matches and the explicit
  parent/child context, isolation and retention limits. The updated regression
  passed. A package parity check that overlapped the Cowork rebuild is rerun
  against the final stable packages.
- Windows CI exposed a POSIX-separator assumption in the attachment-access test.
  The assertion now compares platform paths, retaining the checks that missing
  chat attachments produce actionable guidance without creating Archive state.
- Windows Archive-session CI also found a directory-mode assertion outside the
  existing POSIX-only file-mode check. Both POSIX mode assertions now share that
  platform condition; normalization, hidden identity fields and idempotence are
  still checked on every platform. All 22 client-identity/routing tests passed
  locally after this test-only correction.
- Integrated Archive projection CI found a real scope-binding defect: the raw
  runner bound tolerance `0.00`, then assurance normalized it to `0`. Identical
  source rows were incorrectly rejected as stale semantic decisions. Population
  binding now uses the same exact validated decimal representation as assurance.
  Regressions accept equivalent spellings and still reject changed tolerance
  values; the 23 semantic component tests passed after the repair.
- Once preparation succeeded, the projection regression exposed the complete
  internal semantic receipt in financial-report assumptions. Its opaque target
  IDs had no professional-report paragraph lineage. The shared Word/Excel
  assumption renderer now leaves that control receipt in canonical evidence,
  preserving its content and existing provenance rules. A regression first
  reproduced the leak; all 50 semantic/report-output checks then passed. The
  57 native intake, reporting, regeneration and bridge checks also passed.
  The complete Archive projection suite then passed all 135 cases, including
  public save/apply, replay, tamper rejection and retained output provenance.
- One macOS producer-reporting CI job was cancelled before execution because
  GitHub could not acquire a hosted ARM runner. A retry on the same commit acquired
  a runner and passed. The connector lacked Actions write permission, so the
  authenticated GitHub CLI performed that retry.
- The integrated accounting CI job exceeded its 60-minute budget after all 453
  Open-item source tests (82.59% coverage), 135 public projection tests and 57
  native intake/regeneration tests passed. Those suites took 13m52s, 29m29s and
  14m10s respectively, leaving no time for the other accounting workflows. The
  workflow now runs three independent matrix jobs: accounting, Open-item
  source/native checks, and public projection. All 30 original steps and their
  commands are retained; every verification step belongs to exactly one job.
  Coverage thresholds and per-job time limits are unchanged.
