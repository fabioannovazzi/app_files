# Lucia publication preparation — 6 November 2026

## Result

The audited defects are fixed and both editions have been rebuilt as **0.1.216**.
The source branch now includes `origin/main` commit
`39841a28b` (reconciliation evidence and Archive artifact reads), including
`0a73afa8c` (native Archive tutorial handoffs). The prior audit's newer-source
integration gap is resolved. Concurrent uncommitted work in the primary checkout
and other worktrees was not imported, overwritten or removed.

This prepares local release artifacts. It does not claim an uploaded draft,
Marketplace approval/publication, deployment, native Desktop acceptance or
professional approval. No active installation was replaced.

## Artifacts

| Edition | Final filename | SHA-256 |
| --- | --- | --- |
| Full MCP | lucia-full-codex.zip | dd9465befef49daead6ee5530cadd886a92209d3d0e81411291e1ab91fe0a9bc |
| Reduced non-MCP | lucia-marketplace.zip | 2e237b43c54016f0eec06bdee7c769faa7decf56788d32d9af39401f829a2013 |

Review directory:
`/Users/fabio/Documents/GitHub/app_files/build/lucia-publication-preparation-2026-11-06`.
Source remains on `codex/lucia-distribution-editions` in
`/private/tmp/lucia-distribution-editions`; the review pack records the final
commit and per-file package inventory. Both source-parity checks pass.

The 0.1.215 audit candidates are superseded as release candidates; their audit
results remain historical evidence. The earlier deep audit contains the full
workflow inventory, dependency investigation, visual results and failure register.

## Changes since the audit

- Rebased the audited fixes onto current fetched main, preserving the newer
  Archive implementation and shared reporting changes. Overlapping conflicts were
  version/fingerprint metadata, not competing implementation changes. Generated
  privacy contracts were regenerated from the combined source after review.
- Added an actual 512×512 PNG rendered from the maintained Lucia SVG. The reduced
  portable and compatibility manifests reference the packaged PNG. Its file type,
  dimensions and visual appearance were checked; no invented/replacement branding.
- Added reduced-edition review prompts for supported document work and edition-
  specific release notes in both manifests. The reduced projection no longer loses
  all review/publication metadata or relies on full-edition research/Archive copy.
  Country targeting and publisher verification were not invented or overwritten.
- Updated full-edition release notes and incremented Lucia to 0.1.216. The shared
  reporting fix's companion local versions remain Vera 0.1.588 and Clara 0.1.391.
- Isolated injected-transport receipt tests from inherited delivery-mode settings.
  The local-only test still explicitly sets local-only and rejects transport calls.

## Final verification

- Reduced ZIP: **41 passed** (32 exact-package cases and nine projection tests).
- Full ZIP: **121 passed** (32 exact-package cases plus 89 document regressions).
- Every Python module loads: **185 full + 32 reduced**. All **103** CLI probes
  returned expected results. Broad helper probes include help/protocol checks,
  not a claim of 103 complete professional workflows.
- Full MCP: seven owners initialize and discover **63 tools**, matching the
  packaged catalog. Protocol checks are distinct from native panels/fresh chat.
- Updated full Archive runtime: **12 passed**, scoped to the requested Codex
  distribution; Cowork cases were deliberately deselected, not certified here.
- Upstream Archive/reporting regressions: **106 passed**.
- Shared receipt regressions with injected in-memory transports: **18 passed**.
- Final source parity, Black, Isort and four-module Mypy checks pass.
- Broad packaging/update suite: **416 passed, 2 conditional skips**, no failures.
  Skips concern unavailable curated Marketplace installations; they do not certify
  installed-host behavior.
- Reduced portable ZIP checks pass: no root app or MCP/hook registration, valid
  category and text lengths, five supported review prompts and consistent metadata.

The exact package cases run from read-only extractions with spaces and accents,
external output/state directories and the separately provisioned Python runtime.
All six dependency recipe/constraint files match the audited provisioned recipe
byte-for-byte. No repository or installed full plugin supplies candidate imports.
This remains fresh-venv testing on an existing macOS host, not clean-OS acceptance.
The earlier visual evidence applies to unchanged document-rendering code; the new
PNG was separately inspected.

Pipeline and readable privacy-report results remain separate. Tests exercise
local-only lifecycle, reopening, invalid/altered evidence, retry and preservation
of professional outputs. No server receipts, userID linkage or measured model
exposure is claimed.

## Publication surfaces and boundaries

The **full ZIP** is the complete local-MCP distribution for supported desktop
installation/download. It is not represented as a remote-MCP Marketplace package.
The **reduced ZIP** is the skills-only submission candidate; it requires a host
with local Python execution. No hosted executor or generic-chat fallback was added.
The retained six workflows and exclusions are explicit in its listing and skills.

The package references the existing Lucia product page, privacy policy, terms and
support URLs. Their public content was read: the product page describes Lucia,
the privacy notice names Mparanza and Lucia, terms cover downloadable plugins, and
support supplies contact details. These checks establish page availability and
purpose, not a new legal-compliance opinion.

No portal draft was created or changed. Existing verified publisher selection,
country targeting, portal validation/scans and developer attestations must be
checked in the actual submission when publishing. A skills-only package does not
need invented MCP review cases, reviewer credentials or a demo recording. Native
Desktop/fresh-chat, Windows/Linux, clean macOS and independent professional
acceptance remain unverified; they are not represented as completed tests.

The latest read-only live download retrieved here was still **0.1.211**, SHA-256
`d28ac2cc2d217032651c61adc24ab8704283b56989b7172d12894d1bfb99788c`.
Its per-file differences from the final full candidate are retained. It has not
been replaced by this work and does not contain these fixes.

## Blocks and recoveries in this follow-up

| Block | Effect and resolution |
| --- | --- |
| Sandbox denied Git index writes | Approved local Git operation committed owned work and completed its rebase; no remote branch publication/merge |
| Rebase produced 128 JSON conflicts | Inspected overlapping fields; preserved upstream content and candidate versions, then regenerated derived fingerprints/contracts |
| Public-page web reads/DNS unavailable in sandbox | Used approved read-only HTTPS retrieval for the existing product/privacy pages; terms/support were read through web access |
| macOS sips could not decode SVG | Rendered the existing SVG with isolated local Chromium, with network requests denied; inspected the resulting PNG |
| Global local-only setting affected simulated receipt-service tests | Sixteen tests received the intended no-send result instead of their simulated stamp; isolated test environment and reran all 18 with injected transports, passing; no production guard was weakened |
| Source changes made privacy fingerprints stale | Refreshed only records identified as stale after inspecting the combined source; rebuilt contracts and ZIPs |

Previous recovered/expected audit blocks remain documented in the deep audit.
Repository branch/worktree/stash counts and source commit are recorded in the
final summary; all unrelated concurrent work is preserved.
