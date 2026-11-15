# Clara Studio Archive release acceptance — 2026-11-14

Release 0.1.421 adds Clara's client and engagement directory panel and binds each
selected engagement to its existing advisory case. Legacy case folders retain
their location. Resumption uses the saved binding and refuses missing or
conflicting identities rather than creating a replacement case.

## Observed acceptance

- Fabio confirmed that the synthetic client and engagement were visible and
  selectable in the installed 0.1.419 panel.
- A separate fresh chat resolved the same client and engagement IDs to the same
  case, reopened its workpaper and readable model-data report, and delivered the
  original signed receipt. All seven original artifact hashes matched; no
  analysis rerun or new receipt was needed.
- Receipt verification returned valid for the retained report digest. The report
  honestly marks model exposure measurements as unavailable, with host-attested
  observations. Usage-event delivery and Computer ID server verification remain
  unverified separately from successful report delivery.
- The old curated 0.1.407 installation was removed with explicit user approval.
  Subsequent plugin inventory contained only the selected local 0.1.419 Clara
  installation. That inventory does not prove an already-open chat refreshed.
- Release 0.1.421 incorporates main after PR #998, regenerated course/privacy metadata,
  the Archive catalog entry and packaging fixes. Its extracted 0.1.421 ZIP passed actual
  MCP initialization, directory creation, engagement creation, case creation,
  process restart, exact-case resumption with unchanged manifest bytes, and
  panel resource/font retrieval. This is packaged protocol acceptance, not a
  second native-host acceptance of 0.1.421.
- The adapter regressions pass at 80.85% coverage. Formatting, import order,
  focused type checks, Bandit and Node syntax checks pass. Final package checks,
  CI and production verification are recorded in the release PR.

## Blocks encountered and recovery

- Restricted filesystem/network calls initially prevented Git setup, case-lock
  writes, plugin inventory and receipt verification. Narrow authorized retries
  succeeded. Native Codex control was denied and the host did not expose the
  panel to Computer Use; Fabio's explicit observation supplies visual evidence.
- Local disabling of curated Clara did not remove it from the host catalog.
  The explicitly authorized uninstall removed the duplicate registration.
- Synthetic usage start initially omitted its run ID; retry retained events.
  Consent remained unset, so transmission and server identity verification are
  still open reporting limitations, not successful delivery claims.
- The synthetic case request supplied a null question ID; the accepted empty
  string allowed the workpaper commit and lineage validation to succeed.
- The report builder required an existing output directory. Creating it allowed
  report delivery. The report MCP was a budget-dashboard opener and rejected the
  privacy report; the installed report helper reopened it successfully instead.
- Package checks initially rejected unclassified panel HTML, an unregistered
  privacy owner, missing skill metadata and a missing reduced-edition omission.
  Explicit source registrations resolved these checks.
- Cowork's projection omitted the shared MCP server. Its package now includes
  the Archive Python helpers and documented CLI fallback without registering
  the Codex-only bridges. Native Cowork execution remains untested.
- Integrating current main produced conflicts limited to generated privacy
  fingerprints. Automatic approval review rejected a combined take-ours refresh
  command. Field-by-field inspection and narrow regeneration preserved current
  source controls and resolved the conflicts without discarding main's changes.
- Shared packaging edits and the new catalog entry stale reviewed source hashes;
  maintained generators refreshed the affected metadata. Course assets required
  regeneration. This refresh records changed bytes, not professional approval.
- Wider tests exposed an obsolete privacy field/path expectation, an omitted
  Archive catalog entry and the old HTML-shell count. The harness now uses the
  current contract; the product catalog includes Archive; the projection test
  explicitly requires the retained panel. A package-directory check run during
  generation required rerunning after the build completed.
- The full package suite expected generic run-review boilerplate in the new
  Archive adapter. Like the existing product adapters, its test now verifies
  the actual shared Archive/case-director routing, preservation of saved work
  and model-data report contract rather than an unrelated output template.
- CI's cross-host service check initially required Clara's Codex-only Archive
  bridges in Cowork. Its expectation now reflects the documented projection
  and explicitly checks that the Archive/case CLI helpers and instructions ship.
- Main advanced during CI when PR #998 merged. Its new Archive session-isolation
  controls and tests are preserved. Conflicting generated artifacts are rebuilt
  from the combined source, and Clara advances to 0.1.421 because main already
  uses 0.1.420. The Archive regressions pass again on that shared runtime.
- The inherited packaged Vera chat-isolation tests initially could not acquire
  the shared runtime's `catalog.lock` under the restricted shell. This was a
  host filesystem denial during installation preparation, before case creation;
  both exact synthetic tests passed with authorized runtime-cache access. The
  other 15 discovery/package checks passed under the original restricted run.
- Cross-platform CI exposed a fixture that reused a private state directory
  across different chat sessions. The new main correctly rejects that ownership
  mismatch; the local host's inherited chat ID had concealed the test defect.
  The fixture now explicitly saves an isolated permanent Archive selection and
  resumes with a different session ID and fresh state directory. All 22 Archive
  tests pass with inherited host IDs removed, at the same 80.85% coverage.
  The extracted 0.1.421 package also passes this distinct-session/state-directory
  resumption and preserves the saved manifest bytes.
- Windows initially reported the new multi-command CI step as successful despite
  pytest failing: its default PowerShell step returned the last command's exit
  code. The step now explicitly uses Bash's stop-on-error behavior on every
  platform, preventing a later syntax check from masking a failed regression.
- Final Git-catalog inspection found that the new Cowork Archive files were
  present in the generated ZIP/directory but absent from the committed catalog
  source. The required release files are now included. A regression inspects
  `git archive HEAD` directly, proving a checkout has the Archive helpers, skill
  and privacy contract without relying on a local rebuild.

Marketplace publication is excluded. Source, server deployment and packaged
protocol tests do not claim an automatic update of the local 0.1.419 installation.
The unrelated primary-checkout changes are preserved.
