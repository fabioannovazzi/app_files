# Studio Archive architecture repair

## Scope and acceptance

Studio Archive remains the durable owner of client work. Existing customer
folders, IDs, receipts, inputs, runs, outputs and history must be preserved.
The four areas are execution boundaries, continuity across chats, discovery
independent of search indexing, and isolation of invalid records.

Source baseline: `2d628d2ec` (Vera 0.1.439). Source, packaged runtime, enabled
installation and ordinary-chat acceptance are separate evidence. A release or
passing unit suite does not close this audit.

The sequential acceptance campaign must stop at each failing workflow, repair
the cause and retest that workflow before advancing. Record every block,
including successful automatic recovery. Completion also requires automatic
readable privacy reports and server hashes verified against the correct userID.

## Required behavior

| Area | Contract | Required evidence |
| --- | --- | --- |
| Execution | Validate exact selected inputs and destination; preserve durable work through interruption; unrelated discovery, search or incident state must not veto valid work. | Full workflow, interruption/resumption, local capture and automatic report/receipt delivery. |
| Continuity | Approved connection and client identity survive new chats; each chat retains its own selection. Reads of existing identity do not rewrite it. | Fresh-process and fresh-chat continuation, two independent selections, same IDs and retained bytes. |
| Discovery | New or changed unrelated folders do not require content indexing before selected work can proceed. Selected identity conflicts remain explicit. | Add/rename/remove unrelated folders with stale or absent search index; selected identity conflict. |
| Fault isolation | Enumerate valid records alongside unavailable records. Validate selected dependencies before use. Never rewrite damaged evidence as recovery. | Damaged client, engagement, input and run; healthy sibling work succeeds, dependent work fails precisely. |

Mechanical checks have specific purposes: identity equality prevents selecting
another client; hashes detect changed evidence; path validation confines writes;
atomic replacement and locks prevent partial or conflicting records. Semantic
client ambiguity and professional interpretation remain agent judgments.

## Block inventory

| ID | Area | Observation | Effect | Recovery and status | Justification |
| --- | --- | --- | --- | --- | --- |
| A01 | Fault isolation / discovery | `find_client_manifests` aborts on one invalid manifest; selection calls global synchronization. | An unrelated damaged client can prevent valid client selection. | Reproduced, repaired in source; healthy selection passes and changed selected identities remain rejected. Installed acceptance pending. | The selected identity must validate; rejecting unrelated clients is not required by that check. |
| A02 | Fault isolation | `list_engagements` validates all manifests in one comprehension. | One invalid engagement aborts the client's entire listing. | Reproduced, repaired with independent record inventory. Source regression passes; installed acceptance pending. | Invalid engagement must be unavailable; valid siblings remain usable. |
| A03 | Fault isolation | `list_inputs` rehashes all inputs; listing and import call it for the whole engagement. | A damaged unselected receipt can hide valid work or prevent saving a follow-up. | Continuation reproduced failing after the listing repair; import now considers verified snapshots and exposes incomplete deduplication. Source continuation passes, original damaged receipt preserved. | Use requires validating selected evidence, not unrelated receipts. |
| A04 | Fault isolation | `_iter_manifest_directories` rejects any unexpected entry before enumerating siblings. | An incidental file or invalid directory can hide the entire collection. | Independent inventory added; `.DS_Store` fixture remains unchanged and valid engagement remains visible. Broader entry-type coverage pending. | Do not follow invalid entries; expose their presence without hiding validated records. |
| A05 | Discovery | `recover_studio_client_ledger` still rejects changed top-level scopes before recovery. | Recovery requires content-index refresh even though identities are portable. | Reproduced; repaired recovery uses current directory identities and reports per-record issues. Source regression passes. | Recovering identity does not require extracting unrelated documents. |
| A06 | Execution / continuity | `operational_incidents.local_context` always calls `_write` after `_read`. | Reading an existing installation identity can fail on temporary-file creation. | Regression reproduced failure on the write lock. Existing snapshots now read without locks, directory creation or rewrites; only first creation serializes. Focused regressions pass across Vera/Clara/Lucia. | Persist a new identity once; an unchanged read has no write requirement. |
| A07 | Continuity | Archive registry/profile helpers unconditionally chmod existing private directories. | Host metadata restrictions can prevent otherwise permitted operations. | Reproduced; permission correction is now conditional, unchanged approved-root preferences are reused. Source regression passes. | Verify existing permissions; change them only when correction is necessary. |
| A08 | Host integration | First normal-chat resumption returned `spawnSync python3 ENOENT`; old MCP processes and removed package directories were observed. | Archive tool could not start. | Exact failing process and cause remain unproven. | Do not attribute ENOENT to Python without distinguishing executable and working-directory failure. |
| A09 | Discovery / native panel | Native catalogue set `refresh_required` on folder changes; UI removed open-client buttons and disabled engagement creation. | The native interface retained the block previously removed from the core. | Source native catalogue and real workspace asset now keep verified clients actionable. Rendering regression passes. Installed UI acceptance pending. | Search refresh cannot gate client selection. |
| A10 | Fault isolation | A missing `inputs` or `runs` directory in one engagement still raised before per-record inventory. | Valid sibling engagements disappeared from listing. | Missing-input collection reproduced; both missing-collection regressions now pass with partial inventory and no recreation of missing evidence. | A collection fault belongs to that engagement, not its siblings. |
| A11 | Execution / native import | Global interrupted-upload status disabled new uploads and preparation using already committed ledger inputs. | Valid selected source work was blocked by an unrelated transport acknowledgement. | Reproduced through native RPC; source removes the global dependency while retaining exact upload ownership and selected receipt checks. All 22 native import tests pass. | An uncommitted upload cannot be selected; another upload does not invalidate an existing verified receipt. |
| A12 | Instructions | Failure instructions still required refresh before folder-rename recovery and conflated missing configuration with missing search index. | The agent could reintroduce a removed code-level block. | Instructions now distinguish connection recovery, content search and selected-work validation. Packaged/fresh-chat routing remains unverified. | Instructions must reflect the actual independent operations. |
| A13 | Continuity / execution | The configuration lease stayed locked until Python exited, after the public operation returned. | A resident process prevented a later command in the same chat from creating or continuing work. | Reproduced with two real processes. Operation-scoped leases now release on success and error; later commands can update scopes without invalidating the resident process's unchanged archive identity. Component, adoption, concurrency and fault-isolation suites pass, including active-operation and foreign-session checks. | Protect the active read/use window and selected archive identity, not the lifetime of an idle host process. |
| A14 | Fault isolation / native import | `audit_engagement` read all transport records in a comprehension; an empty manifest raised `KeyError: 'file'`. | Opening the import panel and preparing from valid committed inputs failed because of an unrelated invalid transport record. | Reproduced through native RPC. Independent inspection reports damaged uploads without trusting their manifest fields; verified sources and new uploads remain usable. All 24 native-import checks pass; selected damaged uploads still reject and their files remain unchanged. | Transport integrity is required to resume that upload, not to use an independently verified ledger receipt. |
| A15 | Fault isolation / retention | Retention reporting used strict whole-collection engagement/run readers. | A damaged run input manifest aborted the entire client's retention inventory. | Reproduced; independent inventories now retain valid rows, unavailable records and an explicit completeness flag. New and existing retention regressions pass. | A failed record cannot be a retention candidate; it does not invalidate the metadata of unrelated valid runs. |
| A16 | Execution / delivery | The derived-navigation wrapper did not catch Archive directory failures after the ledger mutation committed. | Saving an engagement could report an overall failure despite having durably saved it, inviting duplicate retries. | Reproduced with a post-commit directory outage. The saved result now returns with a separate unavailable-view result; regression passes. | A derived navigation failure must not erase or misreport a successful durable write. |
| A17 | Selected path / identity boundary | Internal ledger parent directories could be symbolic links; only the final file or directory was checked. Selected engagement loading also omitted directory/manifest ID equality. | An import followed a linked `Vera` directory and wrote outside its selected archive in a disposable reproduction. Loading an existing run also accepted redirected snapshot/execution input parents. | Loader checks now validate the ledger/engagement/input/run collection directories, bound input parent chains and selected engagement ID. Four redirected-import cases, two redirected-run-input cases and engagement identity substitution pass. | Prevent writes/reads outside the selected archive and adopting another engagement's manifest; unrelated valid records remain independently inspectable. |
| A18 | Fault isolation / native presentation | Native run navigation discarded the core inventory's collection issues. | A missing runs directory appeared as an empty work list. | Reproduced; native catalogue and preparation now expose completeness and collection issues, and the interface states that the listing is incomplete. Regression passes. | An unreadable collection is not evidence of no existing work. |
| A19 | Execution / exact retry | Run preparation validated every header before finding the requested run; incidental directory metadata also aborted lookup. | An unrelated damaged header blocked replay of a verified existing request; `.DS_Store` blocked independent run allocation. | Both reproduced and repaired. Exact existing requests replay and report unavailable siblings; incidental entries remain visible without vetoing allocation. A genuinely unreadable run header still prevents allocating a request whose prior existence cannot be established; the regression uses the actual prior request and verifies it is not duplicated. | Existing verified replay creates no second run. New allocation requires enough request identity to avoid duplicating the selected request, not an entirely clean directory. |
| A20 | Fault isolation / specialist follow-up | SARI follow-up used the strict whole-engagement input reader and treated any unrelated upload recovery as a creation veto. | Two real native-RPC reproductions failed: a damaged receipt prevented opening the follow-up, and a damaged transport record prevented saving/creating it from valid inputs. | Follow-up now uses verified input inventory and separates unavailable-record counts from predecessor-operation recovery. All 38 follow-up and import checks pass, including distinct successors with unchanged predecessor outputs and damaged bytes. Installed acceptance remains pending. | Selected sources and predecessor operations must validate. An unrelated damaged receipt/upload cannot invalidate independently verified sources. |
| A21 | Execution / unrelated usage backlog | Ordinary startup instructions requested a global usage flush; even `flush(run_id=...)` returned the entire outbox's pending count. The first normal-chat test attempted six historical events from two unrelated Archive Organization tests before reconciliation began. | An unrelated delivery failure stopped the acceptance run, and successful selected-task delivery could still appear pending. Five regressions reproduced the scope/count/instruction defects; a sixth verified that selected-task rejection remains visible. | Start/outcome status now counts the selected UUID only. CLI flush and pending inspection support `--run-id`; startup and all 49 direct Vera entrypoints instruct task-scoped delivery. All 132 usage tests pass. Historical payloads and acknowledgements are preserved; no rejected global transmission was retried. Packaging and fresh-chat acceptance remain pending. | Exact event/owner/hash acknowledgement still protects delivery evidence. Unrelated tasks are not dependencies of the selected accounting task or its report. |
| A22 | Execution / artifact path resolution | The resumed first test passed `outputs/inspection.json` to `read_studio_run_artifact`. The implementation resolved it against the resident process directory and rejected it as outside the selected run; the tool schema did not identify the expected path base. | Test stopped after source inspection, before agent mapping review or reconciliation. | Regression reproduced the failure. Relative paths now resolve against the selected run root; absolute paths remain valid. The tool describes both forms. Another run's output remains rejected. Focused source checks pass; installed recovery is pending. | The selected run supplies an unambiguous path base. Existing bound-input/output checks continue to prevent crossing into another run. |
| A23 | Execution / portable diagnostic context | Inspection printed a pending PDF-reporting warning for two CSV files. `report_pdf_recovery` accessed `context["output_dir"]`, but the actual portable context stores `output_relative_path`. The killed-worker diagnostic used the same obsolete assumption. | PDF diagnostics raised `KeyError`; killed-worker evidence was not saved in a real portable-context regression. | Both helpers now reuse the maintained Archive context verifier/hydrator. CSV inspection creates no PDF incident, actual PDF failures still report, other-run outputs reject, and killed-worker evidence persists under the same run. The original context bytes remain unchanged. The host's Python 3.9.6 successfully hydrated the actual acceptance context with the repaired helper. Installed recovery is pending. | Mechanical identity/path verification prevents attributing another run's evidence. Hydration must follow the portable format already used by normal execution. |
| T01 | Test harness | The component fixture restored `sys.path` between tests while its reporting adapter remained cached. | Broad regression run failed importing `archive_report_receipt` in the tax-litigation case. | Fixture now supplies product sibling imports per test; exact failing case passes. No product import behavior changed for this failure. | A fixture import defect does not justify changing production code. |
| T02 | Previous behavior assertions | Two older tests required an exact recovery response without new issue fields and a global listing failure for an unreceipted file. | Broader regression verification failed after the intended inventory repair. | Assertions now verify the complete recovery response and the useful behavior: verified inputs remain visible, the unreceipted entry is unavailable and its bytes stay unchanged. Subsequent broader suite passes. | Tests must validate the requested behavior rather than preserving the defect as authority. |
| T03 | Test harness / Windows CI | Job `118616483802` decoded Node's UTF-8 UI output using the Windows default encoding: `Apri incarichi →` became mojibake. | One native-navigation assertion failed; the job reported 60 passed, one failed and one skipped. | The three Archive UI harness subprocess calls now explicitly decode UTF-8. Ten focused local checks passed; subsequent Windows CI verification is pending. Production files are unchanged for this failure. | The harness must decode the actual UI transport encoding; weakening the visible-label assertion or changing production text would conceal the harness defect. |
| T04 | Source typing / CI | Job `118616484270` found that `inspect_client_manifests` reused `records` for a tuple and then a list. The exact CI Mypy configuration reproduced it locally; the earlier default-config check did not. | The runtime-quality job failed static checking. | The per-client group has a distinct variable name; inventory behavior is unchanged. The exact CI configuration now passes all 29 source files locally. Remote CI is pending. | Keep types consistent; do not weaken static checks or mistake a differently configured local pass for equivalent CI evidence. |
| T05 | Editing check | The task-scoping instruction edit expected 47 matching skill entrypoints but found 49 after applying the exact replacement. | Its final count assertion failed; the edits had already completed. | Inspected the actual diff and all matching entrypoints, confirmed all 49 contained the same intended scope correction, and verified the old global-flush instructions are absent. Shared-runtime synchronization and all 132 usage tests pass. | An incorrect editing-count assumption is not a product defect or a reason to omit two direct entrypoints. |
| T06 | New regression fixture | The plugin-suite fixture defaults unfamiliar test modules to local-only incident delivery. The new portable-PDF regression expected its isolated server store to receive the event. | One assertion failed after the production repair: 58 checks passed, one failed. | The test explicitly enables delivery to its existing in-process fake transport. The wider 191-check suite passes. No production behavior changed to address this fixture mismatch. | An isolated fake transport is permitted in this integration test; the assertion must exercise the intended delivery route without a real network dependency. |
| T07 | Release review check | The course-delta check initially assumed every source inventory retained its length. The new diagnostic helper legitimately adds one source entry to affected inventories. | The review script stopped before fingerprint refresh. | Inspected the additions, then verified all 19 changed course JSON files preserve their content after accounting for only source hashes and the named new helper reference. | New governed code must be listed; an unchanged source count is not a product invariant. |
| B01 | Release evidence | `build_product_release.py vera clara lucia` stopped at privacy contract generation: reviewed fingerprints still described the previous source. | No candidate package was produced at that step. | Completed the source-delta review below, corrected three disclosure manifests and refreshed 40 affected review fingerprints. All three product privacy registers now validate; contract generation passes. No installed acceptance follows from this result. | Release disclosures must describe the governed source; this build check is separate from ordinary client execution. |
| B02 | Release evidence | The next build stopped at the generated course-catalogue freshness check, first at Vera's `bilancio-oic/course.json`. Regeneration then invalidated the dependent Vera onboarding, Clara teaching/course-files and Lucia course-files fingerprints. | Packaging did not reach ZIP generation during those attempts. | Regenerated the existing authoring corpus; all 20 changed course JSON files changed only SHA-256 provenance fields. Reviewed that delta, refreshed the four dependent records and rebuilt successfully. | Generated course source references must match their declared source; this is a release check, not an ordinary client execution prerequisite. |
| B03 | Review tooling | The GitHub connector returned HTTP 403 `Resource not accessible by integration` while creating the draft repair PR. | That connector could not create the PR. | The existing authenticated GitHub CLI verified that no PR existed and successfully created draft PR #884 for the pushed branch. | Connector permission scope is separate from Vera and from the repository account already used for the authorized branch push. |
| B04 | Release evidence / CI | Accounting job `118616483281` and release-alignment job `118616483443` passed their preceding steps but the Geneva catalogue check still referenced the 0.1.439 manifest fingerprint. | Both jobs stopped at catalogue identity comparison. | All 55 skill IDs, paths and entrypoint hashes match the retained catalogue. Rebound the manifest fingerprint to 0.1.441 and preserved all Geneva applicability judgments; exact catalogue check passes. | A product version change requires refreshed provenance, not new legal/localization claims or removal of the check. |
| B05 | Release version identity | The package regression rejected the changed Studio Archive component because its version still matched the preceding 0.1.58 candidate. | Package verification failed before installation: 532 passed, two skipped, one failed. | Component version is now 0.1.59; the failed regression passes. Containing host bundles are rebuilt, all Codex ZIPs match source, and 89 final package/privacy checks pass. | Changed packaged source needs a distinct release identity for installation/cache selection. This release check does not gate ordinary work on external runtime versions. |
| B06 | Repository tooling | Git could not stage the correction because `.git/index.lock` existed. The sandbox also denied the first process-list read. | The commit stopped before staging. | Authorized process inspection found no Git process and no open owner. The lock was an unchanged empty ordinary file older than 18 minutes; removed only that stale lock after rechecking those properties. Commit retry remains separate. | An active lock protects another Git transaction. Evidence of no live owner and an old empty file permits clearing a stale lock; no client archive or Git history was removed. |
| B07 | CI / secret-scan false positive | Secret-scan job `118651467301` flagged H01's recorded chat UUID as a generic credential because of the adjacent wording. The exact value matches the non-secret identifier returned by chat creation. | CI failed despite no credential being present in that finding. | Clarified the current prose and added only the scanner's exact historical commit/file/rule/line fingerprint to the existing exception file. Local Gitleaks 8.30.1 passes the full three-commit range and current audit/exception-file contents. A raw unified-diff scan repeated the finding in the removed old line; it did not identify a new current-file secret. Remote CI uses 8.24.3 and must verify the correction separately; the scanner and all other findings remain enabled. | A chat identifier is not an authentication capability. A narrow evidenced historical exception avoids suppressing the audit file or the detection rule. |
| H01 | Acceptance host / coordination | `cua.getApp("Codex")` returned `Computer Use is not allowed to use the app 'com.openai.codex' for safety reasons.` The coordinator then unnecessarily waited for a choice about creating an already-authorized separate chat. | Computer Use cannot place a new app window; the extra clarification delayed the first workflow although the supported chat route remained available. | Rechecked the user's earlier explicit separate-chat authorization and created one GPT-6.1 Sol chat using supported chat controls. Chat identifier: `01a15958-0935-7863-bfee-a42fc2fd4763`. New OS-window placement remains unverified. No Computer Use bypass was attempted. | The host restriction applies to Computer Use window control. It does not revoke prior authorization for the supported chat route; waiting for that authorization again was unnecessary. |
| H02 | Host CLI diagnostic | The read-only plugin-list command warned that it could not create PATH aliases (`Operation not permitted`). | No command failure: listings returned exit zero and the enabled 0.1.440, then 0.1.441 registrations. | Continued using the supported CLI without relying on those aliases; no permission change or alternate launcher was needed. | This warning concerns host CLI alias setup, not Archive data, Python capabilities or ordinary workflow acceptance. |
| H03 | First workflow / agent orchestration | The new test chat's `functions.exec` cell had an extra closing parenthesis after a tool-discovery `map(...)`; the retained tool result was `SyntaxError: Unexpected token ')'`. | The whole cell failed parsing before the Vera preflight or any client work ran. The chat stopped and retained `outputs/resoconto-test-01.txt`. | Inspected the exact call and result in the chat transcript. Supplied the corrected single preflight call from the coordinator. The same GPT-6.1 Sol chat resumed and the installed preflight passed, without changing Vera source or case identities. | Rejecting invalid JavaScript is expected. The agent typo is not evidence of a Vera defect; stopping and recording it follows the user's test instruction. |
| H04 | First workflow / reporting transport and host approval | Ordinary usage flush returned exit zero with zero delivered, six queued events and two `URLError` entries. | The test stopped before client access. A public-URL diagnostic reproduced restricted-shell DNS failure; the identical approved escalated diagnostic reached HTTP 404, proving DNS/TLS/HTTP there but not API health. | Automatic approval review rejected the global flush because its queued payload/destination had not been reviewed or specifically authorized. The chat remains stopped. Subsequent read-only inspection found all six queued events belonged to two October 17 Archive Organization tests with prerelease version `0.1.406-folder-intake.1`, rejected by today's event schema. No retry, deletion, rewriting or alternative transmission of those events followed. A21 repairs the independent ordinary-startup coupling. | Preserve queued evidence and respect the host denial. A distinct current-task delivery must use ordinary host permissions; repairing scope does not authorize transmitting the rejected historical queue. |
| H05 | First workflow / persistent-state write access | Fresh 0.1.442 chat `01a1597b-5104-7ea1-b14d-cd58d8415689` verified the exposed version and passed preflight, then its scoped usage start returned `Usage reporting unavailable (OperationalError)` with exit one. | Test stopped before accounting; task UUID `029bab49-839a-4a58-b11f-9ab25ba33c79` was retained in the chat workspace but no row was inserted in the usage database. No historical flush ran. | SQLite `quick_check=ok`; restricted `r+b` access failed with errno 1, while an approved no-write probe succeeded. After direct user authorization was verified, the identical installed start command succeeded through normal host approval in the coordinator chat: one delivered, zero queued. Readback verifies the current event's receipt owner/hash and all six historical payloads unchanged and unacknowledged. | This demonstrates a host write-access restriction without evidence of database corruption or unsupported Python. Successful registration is not accounting or privacy-report acceptance. |
| H06 | Host approval / scoped current-task delivery | Automatic approval review rejected the coordinator's message asking the test chat to request approved execution of the current task's start. Its stated reason was that workflow-test authorization did not specifically authorize lifecycle metadata and the external Mparanza destination. | The scoped retry was not dispatched and the first workflow stopped. | The question named registration/lifecycle metadata, existing installation/computer credentials, the Mparanza endpoint and the 13-test scope, excluding client contents and historical queued events. The user answered “Of course. Go ahead” and subsequently the structured question with “Yes, authorize for these 13 tests”. The original question and direct reply were verified through chat readback before the approved command ran. | Explicit authorization now covers the selected metadata transfer. The historical queue remains excluded; no global retry, alternative transport or payload change was used. |
| H07 | Host approval / delegated authorization provenance | The test chat's escalated command was rejected before process creation because its reviewer considered the detailed approval scope to come from assistant-generated context. | The first workflow stopped again even though the coordinator had received the user's direct answer. | Coordinator readback established the original detailed question and direct human reply, then submitted the identical installed command to normal host review in that chat. Approved execution delivered the event with matching owner/hash. The same test chat resumed the same task; the child rejection remains recorded. | Verify the direct authorization rather than treating a relayed statement as its own proof. A host-approved command after that verification establishes recovery of this step only. |
| H08 | Integration-test host / loopback server | The exact incident CI suite passed 446 checks but the native-identity integration test could not bind its temporary `127.0.0.1` HTTP server: `PermissionError` errno 1. | Local suite failed before that test's simulated guest registration. | The same suite passed all 447 checks through normal approved execution with local socket permission; coverage is 83.13%. The server and credentials are disposable test fixtures, with no live historical queue. | The integration test needs its loopback transport. No product code, test assertion or coverage threshold was changed to accommodate the host restriction. |

## Verification log

- Prior baseline suite was interrupted at the user's stop instruction. It is
  not a completed verification.
- No customer archive has been modified by this audit. Destructive fixtures
  belong only to isolated temporary test directories.
- Initial combined fault-isolation, run-isolation and readable-navigation suite:
  24 checks passed. Focused existing-context/host-identity checks: 11 passed.
  These preceded later continuation and metadata repairs and are not the final
  whole-change verification.
- Current broader source suite is in progress. Package rebuilding, installed
  normal-chat testing, automatic reporting and server receipt verification have
  not yet been performed for this candidate.
- The broader component/adoption/concurrency/follow-up/Cowork-session/native
  navigation suite subsequently passed (Windows-specific cases skipped on
  this Mac). Later missing-collection and native-upload repairs require their
  own focused checks and final integrated verification.
- Ten fault-isolation regressions now pass, including duplicate stable IDs,
  missing collections and preservation of the damaged records.
- All 22 native import integration tests pass, including exact-byte retry,
  interrupted-import recovery and preparation using a valid receipt while an
  unrelated transport acknowledgement remains incomplete.
- Subsequent native-import verification passes 24 checks. Actual workspace asset
  rendering also passes for unavailable uploads and independent file selection,
  plus the existing client-navigation regression (three focused checks).
- Integrated source verification: 152 passed, five platform-specific skips,
  across fault isolation, run isolation, customer ledger, concurrency, adoption,
  readable views, native navigation and native imports. This preceded the final
  request-lookup and input-parent changes.
- Final request-lookup/customer-ledger/follow-up checks: 48 passed. Additional
  run-isolation checks after input-parent validation: 11 passed.
- Mypy passed for the five changed Archive/native source modules; Bandit reported
  no medium/high findings. JavaScript syntax and `git diff --check` passed.
- Icon generator changed no icons; all three icon-theme tests passed. Remote
  main remains `2d628d2ec`, with no open PRs at the release preflight. Reserved
  candidate source versions: Vera 0.1.440, Clara 0.1.319, Lucia 0.1.143,
  Studio Archive 0.1.58. These versions are not built or installed yet.
- Final integrated Archive/component/native/incident verification completed
  successfully across the ten selected suites, including the last request-lookup
  and input-parent changes. Five platform-specific cases were skipped on macOS.
- Readable Archive's exact CI coverage command passed all 12 tests with 96.97%
  coverage. Changed Python source/tests passed Black and Isort.
- The coordinated build now succeeds for Vera 0.1.440, Clara 0.1.319 and Lucia
  0.1.143 across Codex, Cowork and Antigravity. Package MCP startup/remote-contract
  checks passed; the course corpus has 58 workflows and 258 localized kits.
  Full package parity/report-contract checks are running. The enabled local Vera
  installation is still 0.1.439; installed-chat acceptance has not resumed.
- Read-only preservation inventory recorded all 25 files in the original first
  test archive before installation or resumption. The private comparison file is
  `/private/tmp/studio-archive-first-workflow-baseline.json`; no case file changed.
- Package/privacy/report verification passed 533 tests; two checks were skipped
  because the corresponding curated Marketplace installations are absent. Local
  candidate installation is a separate distribution. JUnit evidence:
  `/private/tmp/studio-archive-release-checks.xml`.
- `build_product_release.py vera clara lucia --check` passed for all three
  products and host distributions, including MCP startup/remote-contract checks.
- Supported `codex plugin add vera@mp-vera --json` installed 0.1.440. A subsequent
  plugin listing confirms it is enabled. All 2,180 cached files exactly match
  the tested ZIP, with no extra files. ZIP SHA-256:
  `958a1c443078645b59b3636db22606dd2d8b922e9f1b37e8c5ff137a605c0ea9`.
  All 25 original test-archive files still match the pre-installation baseline.
  No fresh workflow chat has started; H01 remains pending.
- Repair commit `58e3e7324a886a124cfe32bf9f5255d7c5a15e14` is pushed on
  `codex/studio-archive-architecture`; draft PR:
  https://github.com/fabioannovazzi/app_files/pull/884.
  GitHub confirms 18 pull-request workflow runs queued for this exact commit.
  This is pending CI, not green CI or deployment evidence.
- CI for `58e3e7324` subsequently finished: 16 workflows succeeded and two
  failed. The four failed jobs are accounted for by T03, T04 and B04; fixes
  need a new exact-commit CI run.
- The subsequent follow-up repair passed 38 native SARI/import checks.
  Fault isolation, run isolation and catalogue regression checks passed 34
  tests. Black, Isort and JavaScript syntax pass; the exact runtime CI Mypy
  configuration passes all 29 files, and SARI Bandit has no medium/high findings.
  All 25 original case files still match the preservation baseline.
- The 0.1.441 package/privacy/report run completed with 532 passes, two absent
  curated-installation skips and the single B05 version failure. The failed check
  passes after assigning Studio Archive 0.1.59. Package parity passed before that
  metadata correction; the final component-version rebuild remains in progress.
- The final rebuild completed with Vera 0.1.441, Clara 0.1.319, Lucia 0.1.143
  and Studio Archive 0.1.59. Every host package builds and passes its startup
  or remote-contract checks. All Codex ZIPs match source; 89 final package,
  release-alignment and privacy checks pass after the metadata correction.
- Supported installation updated local `vera@mp-vera` to enabled 0.1.441.
  All 2,180 installed files match the tested ZIP, without extra files. ZIP SHA-256:
  `bbe8b4c8010b5104588dc9d40f80b677ffae2943414ac421cb9dba2372a5af69`.
  All 25 original archive files still match the preservation baseline.
  The new fresh-chat workflow has not started; H01 remains pending.
- The first fresh GPT-6.1 Sol chat subsequently started through the supported
  chat API after resolving H01's unnecessary coordination wait. Its initial
  readback confirms exposed Vera 0.1.441 and the journal-bank workflow. It is
  instructed to resume the original client/engagement/run and stop at the first
  technical block. No workflow success or report acceptance is claimed yet.
- All 18 CI workflows for exact commit `555f1c50e99487a0a8789e12cd6cb0164c8bf80a`
  subsequently completed successfully, including all 46 packaged-runtime jobs.
  This verifies that commit, not the later task-scoping repair or normal-chat use.
- The first workflow remains stopped after H04's host approval rejection.
  Read-only comparison confirms all 25 original archive files and all six
  historical queued event payload hashes are unchanged and unacknowledged.
- A21 reproduced five scope/count/startup failures before repair; the selected
  invalid-event rejection regression already passed. After repair, all 132
  workflow-usage tests pass. JUnit:
  `/private/tmp/studio-archive-task-scoped-usage.xml`.
  Changed-runtime Mypy, Black and Isort pass; Bandit finds no medium/high issues.
  Icon generation changes no icons and all three icon checks pass.
- Additional source candidates are Vera 0.1.442, Clara 0.1.320 and Lucia 0.1.144.
  The reviewed change covers one shared usage runtime, task-scoped delivery
  instructions, 49 direct Vera entrypoint blocks and the three usage-service
  control descriptions. No event schema, destination, credential, selected-run
  receipt binding or acknowledgement rule changes. Startup context now exposes
  a backlog count without unrelated task UUIDs. All 55 Geneva function IDs and
  paths and all entrypoint text outside those usage blocks are preserved.
  The 52 changed course manifests and three indices change only source hashes.
  Seventy-five affected privacy-source records were reviewed/refreshed; all
  three source registers and the Geneva catalogue check pass. Host packages
  are rebuilding; installed normal-chat acceptance remains outstanding.
- The 0.1.442 coordinated build subsequently completed for every supported host
  with successful MCP startup/remote-contract checks. All three Codex ZIPs
  match source. Package/privacy checks: 479 passed, two skips for absent curated
  Marketplace installations, zero failures; release alignment: 13 passed.
  JUnit files: `/private/tmp/studio-archive-442-package-privacy.xml` and
  `/private/tmp/studio-archive-442-release-alignment.xml`.
  Vera ZIP SHA-256:
  `9e858b16e97cf611fca5e11138897f0d261c6645721698daa28eeafe9ce8913b`.
  Installation preflight verified 2,183 distribution files, no escaping paths,
  symbolic links or stale destination extras. Installation and fresh-chat
  acceptance remain separate next steps.
- Commit `1a9086ec440bac9da2161b370428582a0ca49875` is pushed to draft PR #884;
  19 CI workflows were observed queued/running for that exact commit.
  Supported installation enabled local `vera@mp-vera` 0.1.442. All 2,180 cached
  plugin files match the tested ZIP and all 25 original archive files remain
  unchanged. Remote Marketplace listing was unavailable in the restricted CLI;
  local selected-plugin registration and file parity were verified separately.
- Fresh GPT-6.1 Sol chat `01a1597b-5104-7ea1-b14d-cd58d8415689` confirmed the
  exposed 0.1.442 version, passed preflight and followed the corrected scoped
  startup instruction. It stopped at H05; H06 prevented dispatching the scoped
  permission retry. Its retained test report is
  `/Users/fabio/Documents/Codex/2026-10-20/vera-privacy-01-442/outputs/resoconto-test-01.txt`.
  Accounting, automatic readable-report delivery and correct-userID server-hash
  acceptance remain unproven. No second workflow was started.
- The user subsequently authorized registration/lifecycle metadata for all 13
  tests, excluding client contents, prompts and historical queued events. After
  H07 and direct authorization readback, the normal installed start command
  succeeded through approved execution in the coordinator chat. Current event
  `e15333ee-c11c-4c39-bb60-50094c72f7b2`, sequence 1, has matching local/server
  SHA-256 `924b0d2d1136b0b86e6ea719c35abde977e804f282ded9b4b10a4567d3b605ed`
  and installation ID `0ed4a818-1877-4652-8515-787c64de17a5`.
  All six historical payload hashes remain unchanged with no acknowledgement.
  The same GPT-6.1 Sol chat resumed the first workflow. This is registration
  evidence, not a completed accounting result or automatic privacy report.
- Exact commit `ef0cd467925e01fcb91dcceab4ed0494b1ba719f` CI reached 16 of
  19 successful workflows, three still running, no failures. The secret-scan
  workflow passed, confirming B07's narrow correction remotely.
- The resumed first chat verified the native computer link and original input
  receipts, started the same Archive run and executed inspection. The retained
  inspection reports three bank and two journal candidate rows; emitted counts
  are zero because the agent still needs to review the opening/running-balance
  exclusions. This is `needs_review`, not evidence of missing CSV movements.
  The chat stopped at A22 and recorded A23's warning. The run remains running;
  no completed reconciliation or final privacy-report acceptance is claimed.
- Five new failures reproduced A22/A23 before repair. After the source repair
  and T06 fixture correction, 191 checks pass across portable diagnostics,
  automatic Archive reporting, PDF recovery incidents, managed Python runtime
  and verified execution. JUnit:
  `/private/tmp/studio-archive-portable-diagnostics.xml`.
  Mypy passes the new context resolver and artifact reader; Black and Isort
  pass, Bandit finds no medium/high issues. Icon generation changes nothing and
  all three icon checks pass. The new portable-context regressions are added
  to the three-OS automatic Archive reporting CI job.
- Source candidates are Vera 0.1.443, Clara 0.1.321, Lucia 0.1.145 and Studio
  Archive 0.1.60. Version preflight found only this open release PR and unchanged
  main. All 55 Vera entrypoint IDs, paths and hashes are unchanged; only
  catalogue manifest provenance was rebound. Packaging and installation of
  these candidates are pending.
- The exact automatic-reporting CI suite passes locally: 144 checks, coverage
  81.78% against the unchanged 80% requirement. JUnit:
  `/private/tmp/studio-archive-443-reporting-coverage.xml`.
  All 38 affected privacy records were reviewed/refreshed; all three registers
  validate. Nineteen generated course JSON files differ only in source hashes
  and references to the new helper. Exact CI Mypy passes the reporter, launcher
  and new resolver. The earlier `ef0cd4679` packaged-runtime run subsequently
  completed all 46 jobs without failure; that evidence predates A22/A23.
- The incident CI suite subsequently passes all 447 checks with 83.13% coverage
  after H08's host-permission recovery. JUnit:
  `/private/tmp/studio-archive-443-incident-coverage.xml`.
  All 19 workflows on the preceding `ef0cd4679` commit are now green.
  The 0.1.443 coordinated build completed for all hosts with successful MCP
  startup/remote-contract checks, and all three Codex ZIPs match source.
  Vera's distribution contains 2,184 files, including 2,181 plugin files; the
  new resolver matches its authoritative shared source. Archive paths and file
  types passed installation preflight; the existing selected destination has
  no stale extras. ZIP SHA-256:
  `092ccd106d1c67bb4d7686c35ad5ae1ee85f35209d549de19f94cfa027d7c916`.
  The resumed run preserved all five earlier report/receipt files byte-for-byte
  in `reporting/history/1`; original inputs and immutable case identities remain
  unchanged. Installation and fresh-chat acceptance of 0.1.443 are pending.
- Final candidate package/privacy/release checks pass: 492 passed, two skips
  for unavailable curated Marketplace installations, zero failures or errors.
  JUnit: `/private/tmp/studio-archive-443-package-privacy.xml`.

## Remaining audit targets

- Verify the additional task-scoping packages and run CI on their exact commit.
- Verify the packaged host's operation-scoped configuration leases and
  independent native-upload inventory through actual normal-chat use.
- Carry the preserved exact-request limitation into acceptance reports whenever
  encountered; do not invent the identity of an unreadable historical request.
- Exercise packaged host launch and the original normal-chat failure, then
  continue the sequential workflow campaign with its block/receipt evidence.

## Changed-source privacy review

The release review inspected the changed Archive ledger, preferences, operation
leases, readable navigation, native import/navigation and workspace rendering,
plus the shared incident identity reader and version metadata. It also traced
native responses through `native_workspace.py` and `mcp/workspace.cjs`: directory,
upload and preparation detail stays in `_meta.workspace`; model-facing output
retains its existing status/count summary. Direct Archive results can expose
unavailable entry names, opaque identifiers, completeness flags and error reasons.
Recovery/navigation error text may contain local paths. Damaged manifest fields
do not become selected evidence or usable artifacts.

The reviewed disclosure changes describe operation-scoped configuration locks,
independent invalid-record inventories and continuation despite unrelated
interrupted uploads. The Archive model-context record and its five localized
public explanations now explicitly cover unavailable-record metadata. The shared
identity read still returns the existing local credentials and diagnostic
pointers; it adds no HTTP request, recipient, raw-stderr forwarding or payload
field. Existing source snapshot, selected-byte validation, model-output recording
and signed report receipt boundaries remain in place.

Other affected workflow fingerprints govern the same shared native UI or ledger
files; their specialist calculations and model projections did not change.

The A22/A23 delta reads the same bound inputs/outputs and retains the same
producer recording, source coordinates, event schemas, recipients and receipt
ownership. Resolving a relative artifact path against its selected run adds no
new readable directory. Diagnostic context hydration reuses the existing
manifest/receipt verifier locally; its returned context is not transmitted.
PDF incident projection remains limited to the existing technical categories and
counts, and forced-termination evidence stays in the selected run output.
The three operational-incident service manifests now govern the new resolver and
its maintained assurance dependency. Other stale records cover these shared
files, the Archive component metadata or product versions; their semantic
disclosures and professional/jurisdiction judgments are unchanged.
Shared-service fingerprints also cover the incident reader or product version.
The review is limited to these inspected source deltas. It is not evidence that
each workflow, packaged host, external service or normal chat has run successfully.

The subsequent 0.1.441 delta adds SARI follow-up availability counts/completeness
and a local unavailable-record notice. The unchanged MCP response builder keeps
these fields in `_meta.workspace`; the model summary remains status/work reference.
Follow-up sources now come from verified input inventory. Exact selected inputs,
predecessor history and predecessor-specific operation recovery remain enforced.
The two governing follow-up controls now describe this distinction. A ledger
variable rename changes no behavior. Geneva catalogue rebinding changes only
release provenance for 55 unchanged skill entries, and the four regenerated course
JSON files change only SHA-256 fields. The 28 affected privacy fingerprints cover
these inspected deltas; no external recipient or payload boundary is added.
