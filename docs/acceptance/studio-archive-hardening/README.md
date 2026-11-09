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

## Current acceptance and remaining gates

Scoped first-pass code review and the source-level failure matrix are recorded.
Fresh installed Vera 0.1.604 established client isolation, retry reuse, saved-work
completion and reopening. Fresh installed 0.1.605 established restoration of that
same completed run while the original folder was unavailable, reviewed organization,
rollback and preservation of later files on repeated rollback. See the two installed
assessment records for exact identities, recovered blocks and evidence limits.

The 0.1.605 readable privacy report was delivered and reopened unchanged. Measurement
remains explicitly incomplete where source coordinates or derived-output lineage
are unavailable. Remote receipt submission encountered registration rate limiting;
verification found no matching receipt. A subsequent receipt retry requires user
approval after automatic approval review rejected that authenticated submission.

R011 repairs a Windows CI failure in deep-path temporary-directory creation after
those installed checks. Its rebuilt candidates, exact-head CI, current-candidate
acceptance and deployment remain pending. Native Windows installed-host behavior,
live Drive behavior and simultaneous cloud-sync computers remain unverified
external-environment gaps.

A local macOS scale probe of 5,000 small text documents across 100 clients is
recorded in `scale-result.json`; it is not OCR, large-file, network-filesystem or
Windows performance evidence. Referenced installed-thread results are recorded in
`referenced-installed-assessment.json`; they do not establish acceptance of the
current candidate. Source tests are recorded separately from installed outcomes.
