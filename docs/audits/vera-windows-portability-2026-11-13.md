# Vera portable intake and retained work — 2026-11-13

## Observed defects and scope

The work-folder CLI wrote Unicode JSON through the process default stdout encoding. A legacy Windows code page can reject ordinary names and paths. The managed helper environment also inherited that encoding. Reconciliation intake accepted typed Excel dates but rejected equivalent explicit timestamp text. Saved-work continuation depended on secondary Archive lookup state when that state was unavailable.

The prior Windows temporary-file failures ended at `tempfile.mkstemp`; their exact paths and Windows error numbers were absent. Path length is not a confirmed cause of those incidents. The shared ledger now retains the underlying OS exception and reports errno, WinError, parent existence and path length when temporary-file creation fails. It does not select a different studio destination.

## Changes

- Integrated the pending Archive continuity source changes onto the 0.1.627 checkpoint-recovery release. Normal setup establishes one selected location; retained identity or the verified canonical context carries work across stages and reopening. A failed secondary lookup write remains separately recorded. Cross-run selection and tampered contexts remain rejected.
- Work-folder JSON is ASCII-escaped and decodes losslessly. The shared managed Python boundary explicitly uses UTF-8 for helper stdin/stdout/stderr and UTF-8 mode; its dependency-result decoder uses the same format. This boundary is shared by Vera, Clara and Lucia.
- Intake normalizes explicit year-first local timestamp text and typed dates to the same calendar date. It records the source value/type/column/row and the normalized value without changing admitted files. Ambiguous day/month dates still use the reviewed convention. Invalid calendar dates and invalid time fields still fail qualification.
- Runtime collection preserves indexed historical reconciliation component bytes outside the execution store. Receipt replay can read this archive after idle release collection; it validates the index and exact historical receipts and never launches archived code. Unavailable preservation storage keeps the original code in place.

## Verification and limits

The continuity matrix imports synthetic bank workbooks and a PDF journal, prepares source-linked bank copies, seals the preparation, admits the next stage, reconciles, runs labelled fixture model transport, delivers the final four-sheet workbook, verifies EUR 100 on both sides and zero difference, completes the run and reopens it. Cases cover normal configuration, configuration loss, a different configured default, retained lookup and unavailable lookup with explicit context, across ordinary, Unicode and deep paths.

The CI matrix runs this workflow on Windows and Linux under cp1252 and UTF-8, alongside file-identity, historical checkpoint replay, code-retention and direct intake date regressions. CI results are recorded after the candidate completes. The actual Windows incidents remain unverified until the affected host and original task are exercised. Synthetic model transport is not live-model or native-panel acceptance.

Local privacy-report creation and delivery receipts are checked independently of accounting completion. Fixture remote stamping remains pending/offline; no live userID/server-signature verification is claimed. Customer documents, run identifiers and paths are excluded from this report, fixtures and PR content.

Candidate packages: Vera 0.1.628, Clara 0.1.416, Lucia 0.1.240. No Marketplace action is part of this release.

## Local candidate results

- 613 Archive regressions passed; the final continuity suite passed 24 cases.
- 157 selected date regressions passed; 59 combined continuity, retrieval and file-identity tests passed before the final additions.
- Extended reconciliation invocation: 586 passed and eight failed. Five failures lacked the then-unbuilt Cowork archive, two could not start sandbox-exec under the outer host sandbox, and one MCP preflight result differed. With complete packages and the native test context, the complete 37-test receipt suite and that MCP case passed (38 total). The MCP preflight failure did not recur; its cause is not established.
- 70 execution-store regressions passed; eight Windows-only cases were skipped on macOS and are included in native Windows CI.
- Real helper subprocess Unicode transport and historical implementation replay passed five focused cases, including replay from the historical archive.
- Black, Isort, Mypy on seven implementation files, Bandit at medium/high severity and JavaScript syntax checks passed.
- Codex, upload, Cowork and Antigravity builds completed for all three candidate versions; native local MCP startup checks passed. Final package test/drift results follow in the release record.

The first native CI matrix could not create the synthetic PDF because its setup omitted the already declared ReportLab test dependency. A Windows-only fixture write also omitted UTF-8, and the shared MCP test client relied on the host decoder. The setup now installs ReportLab; fixture files and MCP JSON decoding explicitly use UTF-8, and the native result assertion requires the exact Unicode text. Production code was not changed for these harness defects. Initial package CI also identified the stale onboarding fingerprint after the source-only course review records were added; those fingerprints and archives are regenerated before final CI acceptance.

The second native matrix exposed a production defect in bank working-copy preparation: its evidence JSON used the Windows default file encoding and failed for a Unicode source path. The writer now explicitly uses UTF-8; the complete-workflow regression verifies the exact original path and source hash in that JSON. Separately, test artifact declarations and reads now use the contract's POSIX relative-path format, and the fixture model reads packet JSON as UTF-8. The rejected backslash declarations came from the fixture, not a newly inferred product path-length defect.

A focused cp1252-default reproduction also failed while saving a prompt containing `Caffè 東京 ↳`; the full workflow then exposed the same missing encoding in grouped-review output JSON. Prompt, retained evidence, grouped-review JSON, native launch receipt and PDF recipe reads/writes now explicitly use UTF-8. Regression coverage verifies the exact text through model input, saved result and receipt replay. Both audited 0.1.625 and 0.1.627 owned implementations can be replayed and explicitly resumed by the current code; original bytes and receipts remain unchanged, and source/binding/receipt tampering still prevents launch. This is not an external runtime version allowlist.

After these corrections, all 51 continuity/retrieval tests passed both normally and with a cp1252 default for text files. All 85 grouped-review, retrieval and bank-first tests passed. Black, Isort, Mypy and Bandit passed on the additionally changed implementation files. Read-only replay using the assembled Codex package verified the retained original checkpoint without a worker call or file changes; source-tree execution alone does not have the assembled package's receipt layout and is not used as package acceptance.
