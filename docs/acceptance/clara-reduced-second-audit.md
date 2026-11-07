# Reduced Clara second independent audit

The corrected ZIP was tested again without changing its bytes:
`clara-marketplace-fixed.zip`, SHA-256
`f86dbc35ca5274e6c55dab43aa83b7fc087d56a1e9352f4317411cb29cc21af0`.
No new functional failure was observed in the paths exercised below. This does not
establish exhaustive correctness or native-host acceptance.

Evidence is retained in
`output/clara-distribution-candidates-2026-11-06/second-audit/`.
The compact machine-readable result is `summary.json`.

## Additional checks

| Check | Actual result | Evidence |
| --- | --- | --- |
| Import every root and retained skill Python module in its own process | 56 loaded, zero errors; isolated Python, path with spaces and accented characters | `imports.json` |
| New dependency environment | Packaged `managed_python_runtime.py install` successfully provisioned a separate temporary runtime from the declared locked recipe | `runtime-install.log`, `fresh-runtime-inventory.json` |
| Repeat all module imports on the new environment | 56 loaded, zero errors | `fresh-runtime-imports.json` |
| Reporting instructions through actual CLI | 24 calls passed across the three workflows: start, repeated start, status, excluded-workflow rejection, completion, local report build and reopen | `failure-paths.json`, per-call stdout/stderr |
| Alternate inputs and failure recovery | 9 calls passed, described below | `recovery-tests.json`, per-call stdout/stderr |
| Full synthetic workflow acceptance on new environment | 27 calls matched expected success/rejection codes | `fresh runtime workflows à/acceptance.json` |
| Original and revised deck browser QA | Each: 151 passed, one inapplicable fragment check, four viewports, eight screenshots | `fresh runtime workflows à/browser-qa.json`, `revision-browser-qa.json` |
| Read-only installation | Managed wrapper produced a validated contract from an installation with directories 0555 and files 0444, writing outputs outside it | `readonly.json` |
| Installed bytes | No packaged file changed; ordinary Python bytecode caches were created in the writable test extraction | `package-immutability.json` |
| Instruction references | Six Markdown relative links resolved; no bundled MCP registration found | Inspected extracted skill tree |

The fresh runtime was created at `/private/tmp/clara-second-audit-runtime/venv`.
It did not replace the active shared runtime. Its observed import path contains
only standard Python locations and its own site-packages. Installation may reuse
host download caches; this is fresh-environment provisioning on this Mac, not a
new-OS test. Existing Python and Chromium were available on the host.

## Recovery results

- Ran the planner through the documented managed-runtime wrapper from outside the
  installation, with spaces and accented characters in paths.
- A changed source amount was rejected on a previously successful output folder.
  The stale canonical contract disappeared, and its previous bytes survived in a
  content-addressed recovery copy. Restoring the valid input recreated the same
  canonical bytes.
- Extracted the claim snapshot from a PowerPoint, then reopened that snapshot
  through the alternative JSON input path. Both checks passed.
- Duplicate claim keys produced a failed claim audit and nonzero exit.
- Changed local report evidence was rejected without rewriting the saved report.
  The `usage-report-html-deck` evidence folder was intentionally altered for this
  negative test; the independent final reports are under `fresh runtime workflows à/privacy`.
- A state path deliberately replaced by a file made task-usage reporting fail.
  The planner still completed with that same unavailable reporting-state setting.
- Repeated startup kept one queued start event per task. Completion added one event.
  Local-only transport left remote status null and events unacknowledged, rather
  than falsely claiming delivery. Local report receipts correctly remained unlinked.

## Privacy/reporting outcome

All three final local reports built, validated and reopened unchanged. Reporting
outcomes remain separate from the successful professional pipelines. Deliberate
invalid reports and changed-evidence tests produced the expected failures. Live
server delivery, signed receipt/userID linkage and provider payload measurement
were not tested or claimed. No external messages were sent.

## Boundaries and repository state

No packaging or product-code change was needed in this second audit. The corrected
ZIP and full website ZIP remain unchanged; neither was published or installed into
the active plugin. Fresh native-chat discovery/routing and Marketplace-host behavior
remain unverified. Cross-platform installation and professional output acceptance
also remain open. The copied synthetic examples do not establish real-client quality.

Repository inventory at completion: 10 local branches, 8 remote branches,
10 registered worktrees, 0 stashes. This audit created none. A concurrent task added
a local branch/worktree during the audit; it was preserved.
