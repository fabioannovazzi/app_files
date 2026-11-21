# Archive and Windows runtime repairs — 21 November 2026

## Evidence and scope

The 08:05 Paris incident email and a read-only live queue inspection identified:

- Archive report `121a40b9-69a4-4cf7-b6c3-c9252a0725a1`: `rename-project`
  was not registered by the installed CLI. The deployed source had no such
  command either.
- Archive report `7dfd10af-61b2-4545-b030-7780e662b07e`: repeated 300-second
  connector timeouts, while the maintained CLI could read/copy the selected
  records. The connector's synchronous subprocess calls block its event loop.
  This is reproducible transport starvation, but the retained report does not
  prove that it explains every customer timeout.
- Windows report `047f54c5-828d-4634-b00a-3994cd2b8c61`, Vera 0.1.661:
  `MissingEntrypoint`, followed by four successful helper calls without verified
  original-task recovery. Inspection found that the native opinion route owns
  `scripts/opinion_validation.py` at the product root, whereas an equivalent
  managed invocation with the research module searched the component root.
  The report does not retain the helper name, so this repaired launch defect
  cannot yet be identified as that report's exact cause.
- Windows report `e07b0aa5-550e-42b6-b1a0-e40057e57226`, 10:49 Paris:
  research evidence did not match the declared treatment type. The original
  record and retained stderr are unavailable on this Mac. No evidence supports
  silently changing the treatment or weakening the closure validation.

## Changes

- Added `rename_studio_archive_project(client_id, name)` and the matching
  `rename-project --client-id ... --name ...` CLI command. Stable client and
  engagement IDs, aliases and file bytes survive. An OS no-replace operation
  prevents overwriting a destination created after preflight. Retrying the same
  identity and name recovers an already committed rename. Folder bindings are
  returned for continuation; the derived search index is explicitly stale.
- Archive worker launches and diagnostic recording are asynchronous. Pings and
  correlated progress remain responsive while a worker executes. Operations
  are not killed merely because they take longer than a transport deadline.
  A host imposing an absolute request deadline can still time out; existing
  idempotency keys and retained results remain necessary for recovery.
- The managed launcher recognizes the exact Vera-owned opinion helper when the
  research component selects its dependencies. It does not fall back to arbitrary
  product scripts when a component file is missing. Other products retain their
  own component boundaries.
- Research evidence-mismatch errors identify the declared treatment and required
  evidence types and direct the agent to review the evidence, not relabel it.
- Release versions: Vera 0.1.662, Clara 0.1.431, Lucia 0.1.261;
  Studio Archive 0.1.82 and research validator 0.1.57.

## Privacy

Renaming exposes the requested name, stable client ID, updated folder binding
(including absolute paths), index status and registry synchronization status to
the host model. Private aliases and document bytes are not included. Progress
contains only the caller's correlation token, a counter and a generic message.
No new external recipient or model-data transmission route was introduced.
The selected runtime remains the user's host account. Updated privacy source
records and generated contracts describe these paths separately from execution.

No fresh host-conversation privacy-report delivery or customer Windows workflow
was exercised. Those remain acceptance limits, independently of automated tests.

## Recovered verification blocks

- The new MCP rename test initially combined configuration from different test
  sessions. It now configures, registers and renames through one MCP session.
  The configuration-identity check was preserved.
- An initial tool-list test edit inserted the new name into a call rather than
  the expected tool set. The test was corrected; product behavior was unchanged.
- Package tests initially lacked locally built ZIPs in the new worktree. They
  must run after rebuilding all affected host distributions.
- Three native process/sandbox tests were blocked by the outer macOS sandbox.
  All three passed when rerun with the required OS access.
- The new privacy class initially named a runtime outside the owning manifest's
  declared profiles. Its profile list now follows the existing owning contract.
- A Lucia packaged test launched a component directly without the product
  environment normally supplied by its wrapper. The test now supplies
  `LUCIA_ASSURANCE_HOST=1`; product isolation remains unchanged.
- The full-directory secret scan reported 15 existing matches: 12 SHA-256
  manifest entries, two copies of an ECB series identifier and a fictional
  test idempotency key. All 15 exact lines already existed in the base commit.
- Detailed CI logs exposed 79.80% coverage in the unchanged Clara case wrapper.
  A regression now resumes the same case through its JSON bridge after project
  renaming and verifies its manifest bytes; coverage is 86.87%. Its fixture
  explicitly restores the component import path for each test because pytest
  restores `sys.path` while Python retains the imported module.
- A pre-deployment queue refresh found synthetic Clara report
  `99810eeb-08db-4c99-98c1-5e14a18de15e`, matching the deliberate tampered-package
  fixture. The test used obsolete environment-only reporting settings. It now
  binds explicit local-only settings before the verifier runs and asserts a
  locally queued, unregistered incident. No production integrity/reporting
  policy was weakened and no incident was deleted or marked recovered.

## Local validation

- Archive component: 167 passed; rename regressions: 12 passed, including
  case-only renames, a concurrent destination and registry persistence failure.
- Archive recovery: 588 passed, 1 skipped; required module coverage 89.20%.
- Shared runtime: 364 passed, 8 skipped; coverage 83.29% (minimum 80%).
- Product Archive wrappers and research record/package tests: 85 passed.
- Clara case bridge, including renamed-project resumption: 13 passed with
  86.87% coverage.
- Strict runtime type checks: 30 files passed; the rename helper also passed
  independently. Changed Python formatting/import checks, Node syntax and
  medium/high security checks passed. Icon generation changed no assets;
  its five tests passed.
- CI runs rename and product-owned opinion routing regressions on Windows,
  macOS and Linux. CI outcomes and live deployment evidence are recorded
  separately after the release, not inferred from these local results.

## Remaining customer acceptance

Use a fresh session with the updated installed version. Exercise project rename
and the original Archive read/create calls. For a lost creation reply, retain and
reuse its original idempotency key. Re-run the original Windows opinion with its
original inputs; helper success alone is not task recovery. Inspect the retained
research record before correcting its evidence/treatment declaration. The earlier
Windows schema-canary/incident-state failure still needs its retained diagnostics
from the affected PC; neither this release nor the prior diagnostic release
establishes its root cause. No incident is marked recovered by these code changes.
