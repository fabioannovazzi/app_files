# Vera MCP process reduction — 26 October 2026

Candidate: Vera 0.1.494. Source changes and local packages are prepared; this
record does not establish deployment, installation or fresh-chat acceptance.

Component MCP services now load the existing reporting bridge in the launcher
process and start their server directly. Product MCP services run in the launcher
process. The persistent Python gateway and its old-release routing are removed.
The native Python job service retains its two execution processes and existing
job persistence. No accounting workflow, model payload or external destination
is changed by this launch-path change.

Startup package inventory and SHA-256 checks run synchronously in Node. The
existing component validators still require single-link implementation files.
When a host installs a component with hardlinks, its verified component files
are copied to a private temporary directory, removed on normal service exit;
there is no additional process. Forced termination can leave this temporary
copy. Ordinary single-link installations execute in place.

An update during MCP use can require reopening the chat. The bridge does not
replay an interrupted mutation. It no longer routes reviews to the version
previously bound to an Archive run. Native calculation-job ownership remains
separate and unchanged.

## Measured process counts

The isolated comparison uses the built Codex ZIP, with the previous launchers
from the branch's base commit restored for the baseline. MCP initialize and
complete tools/list replies are required for every registered local service.
Each cohort is closed before starting the next. Only probe descendants are
counted, using OS PID and parent-PID relationships.

| Cohort | All 25 services | Earlier 24-service selection | Processes remaining after close |
| --- | ---: | ---: | ---: |
| Previous launchers | 93 | 89 | 0 |
| Direct launchers | 45 | 43 | 0 |
| Direct launchers, hardlinked installation | 45 | 43 | 0 |

The earlier selection excludes the colliding varianceAnalysisWidgets entry.
The 89-to-43 change removes 46 resident processes (51.7%) from that selection.
This is a per-service-set measurement, not a measurement of every installed
Codex chat or of system memory consumption.

Raw measurement: `outputs/vera-mcp-process-overhead-20261026/process-counts.json`.

## Clara and Lucia inspection

Clara's two registered local MCP services use two resident Node processes.
Lucia's six registered local MCP services use ten resident Node processes:
three component launcher/server pairs, one assurance filtering/server pair,
and two direct services. Neither product registers Vera's persistent update
snapshot owner or release-routing gateway. Shared incident and course helpers
start Python synchronously only for a requested operation; their process ends
with that call. The managed Python launcher also explicitly restricts shared
release snapshots to Vera.

The extracted Clara 0.1.347 and Lucia 0.1.176 packages both completed initialize
and tools/list for every registered service, with zero descendants remaining
after connection closure. No analogous persistent update-protection mechanism
was found to remove, so this change does not alter their launch paths.
Evidence: `outputs/vera-mcp-process-overhead-20261026/clara-lucia-process-counts.json`.

## Validation and encountered blocks

- Runtime, native execution, Archive emission, workspace, studio-work and
  research-source regression run: 190 tests passed. The additional hardlink
  regression and icon tests also passed (20 tests in the focused run).
- Real extracted-package probes passed for ordinary and hardlinked packages;
  all selected services initialized and returned their tool lists.
- Codex, upload-format, Cowork and Antigravity packages were rebuilt. The
  product release `--check` verifies source parity and version alignment.
- Required package, update-notification and extracted-MCP startup suites: 425 passed, 2 skipped. The skipped installed-Marketplace comparisons have no matching local cache and do not establish Marketplace installation acceptance.
- Black, Isort, Bandit, Node syntax checks and the 30-file runtime Mypy check passed.
- Restricted-shell runtime tests initially could not exercise process-group
  cancellation and nested macOS sandboxing. The same isolated regressions
  passed with those host capabilities available; production code was not
  changed to accommodate the test environment.
- The initial measurement used macOS's `/var` temporary alias. The existing
  verifier rejected its symlink ancestor. Resolving the probe's own temporary
  path fixed the fixture; both old and new launchers then passed.
- Privacy generation initially found the deleted gateway and stale source
  fingerprints. The governed paths and Vera's code-lifetime description were
  updated after inspecting the source diff, then the fingerprints and derived
  contracts were refreshed. This was agent review. The registry's fixed
  `privacy-surface-review` reviewer tag is not a claim of human approval.
- The first broad package run lacked ignored Clara and Lucia archive fixtures
  in the new worktree. It was interrupted, those source-derived prerequisites
  were built, and the required suite passed on rerun.
- `codex plugin list --json` could not provide an installed-version inventory:
  the existing mp-clara and mp-lucia source paths have no supported marketplace
  manifest; the restricted-shell remote catalog request also failed. Neither
  registration was modified. Current enabled-installation acceptance remains
  unverified.

The primary checkout's unrelated work and the other active task's branch and
worktree were preserved. Marketplace publication is outside this change.
