# Studio Archive hardening goal

Review all four functions: finding documents, organizing existing files, retaining
new work, and restoring saved work. External communications and Drive access are
separate integration boundaries. This review does not treat existing tests or
execution blocks as product requirements.

## Required invariants

- Preserve original inputs and newer destination work.
- Bind every mutation and recovery to the selected client, engagement and job.
- Repeating a request after a lost response does not duplicate committed work.
- Interrupted writes retain a valid prior state or a resumable, explicit state.
- Report success only after verifying the resulting files and records.
- Reporting failures are visible separately and do not block useful work.
- Search results identify stale, incomplete or unavailable evidence honestly.
- Organization applies only approved changes; rollback preserves later edits.

## Work sequence

1. Review inventory and dependency/caller map; inspect recovery and file moves first.
2. Failure injection at write/commit boundaries, including actual process exit.
3. Repair confirmed defects and add behavior-based regressions.
4. Finish search, lifecycle, external integration, instruction and packaging review.
5. Measure representative scale, exercise available installed-product workflows,
   and record Windows/Drive/two-machine acceptance separately.
6. Align public HTML explanations; complete release checks and deployment.

## Evidence discipline

`review-inventory.json` records exact source identities and review status. Pending
entries are not reviewed. Findings must name a reproduced harm, affected path,
repair and test. Environment limitations remain explicit and cannot become a
claim of compatibility or professional acceptance. No customer data or external
messages are needed for synthetic failure tests. No Marketplace publication.

## Current findings

See `findings.json` for the current defect register and `progress.md` for tested
results. Repairs are local until release evidence proves otherwise. The register
distinguishes reproduced defects, verified preservation boundaries and open
investigations; a passing unit suite is not installed-product acceptance.

## Acceptance still pending

Scoped first-pass code review and the source-level failure matrix are recorded.
Fresh-chat candidate behavior, release checks and deployment remain pending. Windows installed-host behavior, live Drive behavior
and simultaneous cloud-sync computers remain unverified external-environment gaps.

A local macOS scale probe of 5,000 small text documents across 100 clients is
recorded in `scale-result.json`; it is not OCR, large-file, network-filesystem or
Windows performance evidence. Referenced installed-thread results are recorded in
`referenced-installed-assessment.json`; they do not establish acceptance of the
current candidate. Source tests are recorded separately from installed outcomes.
