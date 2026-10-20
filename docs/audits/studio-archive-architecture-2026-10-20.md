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

Current user-directed priority: repair and restart workflow one end to end.
The earlier acceptance below covered report delivery/receipt/reopening only
and was too broad when described as a passed workflow. Overall acceptance is
withdrawn: zero workflows are fully accepted. Test two is stopped; the user
will archive that chat, which must not be reopened without a later request.
Preserve the prior first-run outputs and receipt as evidence. A fresh first
test must execute every required stage, deliver usable results and provide
accurate privacy measurements and a verified same-userID server proof.

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
| A24 | Instructions / remaining specialist refresh dependency | The Open-item component skill still said “refresh first if Studio Archive reports changed top-level scopes” in its client-folder gate. A repository-wide skill search found this remaining instance after A12. | The instruction could reintroduce a search-index dependency before selected work. No such stop was observed in test two. | Source now separates selected identity/input validation from content-search refresh. Candidate packaging remains pending. | Selected client identity and input receipts must validate; an unrelated folder change does not require content indexing before reconciliation. |
| A25 | First workflow / skipped required residual worker | The saved semantic status is `prepared`, `worker_required=true`; the test chat deliberately did not launch the worker, interpreting GPT-6.1 Sol as prohibiting the component's Luna step. The installed skill explicitly keeps the main model unchanged while running that separate bounded worker. | The normal residual-resolution path was not exercised. The earlier executable-identity failure therefore has no successful end-to-end replacement evidence from this run. | Unresolved. Fresh first-test acceptance must exercise the intended worker and validate its result, while keeping the main chat on GPT-6.1 Sol. | A main-chat model requirement does not imply a prohibition on the workflow's documented worker. No worker success may be inferred from preparation alone. |
| A26 | First workflow / incomplete producer provenance | The final privacy report has eight derived-output lineage gaps and unmapped emissions. Its available source-cell counts do not establish the unsent remainder. | Report delivery and correct-owner hash verification succeeded, but complete source exposure accounting was not established. | Source repairs now cover tabular inspection, calculation audit, sealed metadata recipe revisions, selected MCP cases and the actual worker submission boundary. Focused transport regressions pass; broader checks, packaging and fresh installed acceptance remain pending. Preserve the incomplete historical report and its proof unchanged. | Allowing a truthful incomplete report avoids suppressing results; it does not make missing measurement coverage a successful end-to-end test. |
| A27 | Usage persistence / native service boundary | Fresh 0.1.444 chat invoked the prescribed shell registration. The database is outside its writable project; a no-write `r+b` probe returned `PermissionError`, errno 1. SQLite read-only `quick_check` is `ok`, and the retained task has no database row. | The test stopped before Archive preparation or accounting. Moving the same command to the coordinator had recovered prior attempts but did not fix normal use. | Added fixed task operations to the existing native reporting service, reusing the same identity/database and task-scoped delivery. CLI diagnostics now retain operation, errno and SQLite error code. Native boundary regressions pass. Fresh 0.1.445 chat verifies start/status/test-outcome delivery under the existing owner and Computer ID; the remaining workflow stopped at A28. | Persistence belongs to the installed service that owns it. No permission expansion, replacement identity, global queue flush or silent loss of reporting is required. |
| A28 | Managed execution / diagnostic persistence | The fresh 0.1.445 chat completed native registration, prepared and started its Archive run, then the ordinary dependency checker returned zero while reporting unavailable incident identity/progress, stderr retention and recovery receipt. The shared launcher writes incident state and diagnostic files under the same user-scoped directory outside the chat's writable project. | The explicit stop-on-error test policy stopped the attempt before inspection or Luna. All selected Python dependencies were importable. | Source repair exposes the existing managed launcher through the installed native service, retains jobs/results across reconnects and pins verified package code. Fourteen process regressions pass, including the reproduced restricted-shell write denial, native persistence, cache removal, failure retention and cancellation of detached descendants. Five reporting regressions verify actual returned output, unknown-output gaps and sealed-result replay. Installed normal-chat acceptance remains outstanding; the preserved Archive run is still running. | The test halt is distinct from an accounting failure. Diagnostic persistence must work without relying on coordinator-only command execution, suppressing warnings or moving private reporter state into client files. Unit fixtures substitute dependency selection, not the real child processes or reporting boundary; they do not establish actual Luna acceptance. |
| A29 | Incident outbox scope / inspected risk | The common launcher calls `record_execution_progress` and `record_success`; the prior implementation could invoke `_flush(state)` on the whole incident outbox. Fourteen retained entries are present: seven reports and seven observed-success entries. | Moving the launcher to a writable native process without addressing this scope could transmit retained historical events excluded from this test's authorization. No such actual-case native helper execution or historical delivery was performed. | Source repair adds a local task scope to newly created events, operation identities, success recovery and delivery selection; it neither relabels nor clears retained entries. Eight new scoped-delivery cases and the expanded 455-test incident suite pass, with 83.29% coverage. The installed native executor carries the retained task UUID into the launcher. The fresh chat restricted managed diagnostic delivery to local-only, so it does not establish current-task external incident delivery. The pre-run historical baseline is `/private/tmp/studio-archive-445-incident-queue-baseline.json`. | This is an inspected delivery-scope risk, not a claim that the stopped test transmitted those events. Existing usage-task delivery is separately scoped and left its six historical events unacknowledged. |
| A30 | Worker preparation coupled to review-clearance choice | The installed specialist required a user-selected minimum certainty before Luna preparation; both `prepare` and `run-all` required `--required-level`. The fresh chat asked that question after producing two deterministic matches and one bank residual. | A choice about removing residuals from the review queue interrupted preparation of the requested draft. Luna and final delivery were not reached. | Source repair makes draft preparation default to `perfect_match`, retaining semantic residuals for review while still running the eligible worker. An explicitly established lower policy remains supported. No human choice is inferred and existing reports are not rewritten. All 68 semantic regressions pass, including omitted CLI policy, explicit clearance and retained classified residuals. Packaging and installed acceptance remain pending. | A clearance decision can affect operational review; it need not block preparing and delivering a draft. Fixed queue behavior follows the explicit authority boundary; semantic judgment remains model-led and the strict reconciliation is unchanged. |
| A31 | Native cancellation / process-group timing | macOS CI repeatedly returned `failed` with `PermissionError: [Errno 1] Operation not permitted` during cancellation. A local reproduction showed `killpg` returns EPERM after individually killing the unreaped group leader; the native service used that order. A 50 ms group-signal delay reproduces the failure through the real native API. | Successful termination could be reported as failed; the fresh acceptance restart was held for diagnosis. | Signal the launcher's group before killing recorded descendants individually, retaining cancellation of detached children and genuine permission errors. The formerly failing scheduling regression and all 72 native reporting tests pass locally. Native reporting also passes on macOS, Windows and Linux at commit `a381adcd5` (B12). | Stop the owned processes and report the actual outcome; do not hide a permission failure or weaken the detached-child assertion. |
| A32 | Semantic result handoff / archived receipt location | `run-all` validates the worker, then its final preparation archives that generation. The command returned counts and current resolution paths but omitted the actual archived worker-receipt paths. The fresh agent guessed a top-level path and failed at H19. | Successful worker execution was followed by a failed diagnostic and no completed delivery. | The API batch now returns the actual archived worker and launch-receipt paths, and the CLI emits them as registered operational metadata. Instructions distinguish the completed batch from terminal `worker_required=false`. The regression opens both returned receipts after final preparation and verifies the worker's graph binding. All 68 semantic checks pass. | Expose the output's actual location; do not create duplicate receipts, weaken validation or infer a generation name. |
| A33 | Model-data accounting / artifact-read routing | The 0.1.448 agent printed inspection previews, audits and receipts through shell Python. The global Vera skill prescribes `read_studio_run_artifact`, but the specialist's immediate read steps did not repeat that route. The failed report records the worker packet while excluding those host reads. | Automatic report generation and server proof do not establish complete source exposure for this attempt. | Added the existing recorded reader at the specialist entrypoint and each relevant read phase. It remains the existing native tool, with the same run IDs and provenance implementation; local calculations and decision-file writes remain local. All 14 Journal-Bank reporting-provenance tests pass, including actual inspection delivery. Fresh ordinary-chat acceptance is still required; historical measurements are not backfilled. | Content returned through the supported reader can be measured exactly. A plugin cannot claim observation of arbitrary shell output outside that boundary. |
| A34 | Model-data accounting / semantic execution artifacts | Extending the real Archive integration test to read the returned worker and launch receipts produced two `derived_output_lineage_unavailable` errors in both native and direct execution. After their repair, reading the current status reproduced a third missing-provenance case. | Even the prescribed recorded read could leave this otherwise successful run's report incomplete. The next installation was held before restarting acceptance. | Register the exact producer-created status and receipt payloads with their serialized byte hashes. These constructors contain operational configuration, counts and hashes rather than source records or worker answers. Registration survives the generation move and does not count preparation as a send. Regressions also edit each artifact afterward and require the report to retain the resulting unknown lineage. All 19 reporting checks and 68 semantic checks pass; fresh installed acceptance remains pending. | Exact producer provenance distinguishes metadata from unaccounted case content; a filename or schema label alone cannot establish that distinction. No prior report is rewritten. |
| A35 | Mapping handoff / copied inspection metadata | The skill lists `potential_monetary_columns` alongside the fields sealed in a mapping receipt. The input contract omits it because the sealer derives it from source bytes. The 0.1.449 agent copied it into its decisions, which were rejected as unknown fields. | The draft could not reach reconciliation despite explicit mapped amount and excluded balance columns. Three new positive regressions reproduce the rejection; a fourth shows it hides the actual undisposed-balance error. | Clarify the input contract and discard this single known informational field from a copy of the decisions before validation. Recompute candidates from the current source as before. Regressions cover correct, empty and stale copied candidates, an undisposed balance that must still reject, and a misspelled unknown decision field that must not be silently ignored. All 27 sealer integration checks pass at 85.91% coverage, and all 20 reporting checks pass. Package verification and installed acceptance are pending. | Source-derived candidates cannot supply review authority. Recomputing them prevents stale values from concealing monetary columns without rejecting harmless copied metadata. Required mapping, exclusions, source-byte checks and relationship policy remain enforced. |
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
| B08 | Latest-runtime CI / coverage selection | Job `118747931359` passed its tests but reported 79.94% coverage against the required 80%. The new source-provenance worker regression was absent from this job's selected files. | CI blocks merging the current commit. | Added the existing real-calculation/worker-submission regression to both compatibility selections. A local run without the optional native probe passed 130 tests, skipped two and still failed coverage at 77.95%; it is not the equivalent native job. With the real installed Codex/macOS isolation probe enabled, 131 tests pass, one unrelated test skips, and coverage is 80.91%. The revised remote CI job still needs to run on the committed change. | Keep the threshold and latest-native-runtime check enabled; neither a passing assertion suite nor a different test selection establishes the required coverage. |
| B09 | Windows acquisition-panel CI / unresolved timeout | Job `118747933133` timed out after five seconds waiting for the save-completion message in the 1180px date-selection test. The other 73 tests passed and coverage reached 80.43%. | The first CI attempt blocked merging. | Inspected the actual save handler and harness. Both viewport cases pass locally in the offline browser harness. Rerun job `118764900003` passes on the unchanged commit. No production UI change or timeout increase has been made. | The current evidence establishes a missed save-completion observation followed by a passing unchanged rerun; its original cause remains unknown. |
| B10 | Cowork package reviewer inventory | The 0.1.446 all-host build stopped in `_reviewer_note` with `KeyError: 'veraExecution'`. | Codex generation had run, but all-host release alignment had not completed. | Added the new service's concrete local-execution/data-boundary description to the reviewer inventory and extended the existing MCP entrypoint checks for its exact packaged path. All-host rebuild and parity checks now pass for Vera 0.1.446, Clara 0.1.324 and Lucia 0.1.148, including packaged MCP startup checks. | A newly exposed service must have an accurate package description; this build failure is not an ordinary-work runtime rejection. |
| B11 | Windows reporting regression / fixture newline conversion | Job `118785741413` passed 164 tests with four skips and 80.71% coverage, but its new streaming-preview assertion expected LF after the fixture wrote text with Windows CRLF conversion. | This CI check blocked merge of `b9071f501`. | Inspected the exact retained output: production streaming preserved `Preview ready\r\n`. Changed the fixture to write explicit UTF-8 bytes and parameterized LF/CRLF preservation; all six reporting-boundary tests pass locally. No production normalization or reporting rule was changed. Windows Archive reporting job `118803974977` passes on `4f2b9257f`. | The expected exact bytes must match the bytes supplied by the fixture on every OS. |
| B12 | macOS native cancellation / incomplete failure evidence | Job `118785739719` passed 70 tests but the cancellation test observed `state=failed` rather than `cancelled`. Its assertion omitted the retained response and any cancellation error. | This CI check blocked merge; a local 71-test pass did not explain the failure. | After the workflow finished, unchanged-commit retry `118800883827` failed again. Diagnostic assertion on commit `4f2b9257f` exposed EPERM in job `118803975719`. The process-group ordering defect was reproduced locally and repaired as A31. Native reporting now passes on macOS (`118813046590`), Windows (`118813046502`) and Linux (`118813046430`) at commit `a381adcd5`. | Preserve the cancellation requirement and obtain concrete error evidence before changing behavior. |
| B13 | CI / cancelled Archive adoption job | At `a381adcd5`, 97 checks passed but macOS Archive adoption job `118813046773` is cancelled. GitHub returns no steps and no available log. | Full required CI is not green; no failing product operation can be identified from this evidence. | Preserve the cancelled result and require this check on the next candidate commit. The cause remains unknown; no product or test change is justified by an empty job result. | A cancelled job is not a passed test or evidence of a specific product defect. |
| H01 | Acceptance host / coordination | `cua.getApp("Codex")` returned `Computer Use is not allowed to use the app 'com.openai.codex' for safety reasons.` The coordinator then unnecessarily waited for a choice about creating an already-authorized separate chat. | Computer Use cannot place a new app window; the extra clarification delayed the first workflow although the supported chat route remained available. | Rechecked the user's earlier explicit separate-chat authorization and created one GPT-6.1 Sol chat using supported chat controls. Chat identifier: `01a15958-0935-7863-bfee-a42fc2fd4763`. New OS-window placement remains unverified. No Computer Use bypass was attempted. | The host restriction applies to Computer Use window control. It does not revoke prior authorization for the supported chat route; waiting for that authorization again was unnecessary. |
| H02 | Host CLI diagnostic | The read-only plugin-list command warned that it could not create PATH aliases (`Operation not permitted`). | No command failure: listings returned exit zero and the enabled 0.1.440, then 0.1.441 registrations. | Continued using the supported CLI without relying on those aliases; no permission change or alternate launcher was needed. | This warning concerns host CLI alias setup, not Archive data, Python capabilities or ordinary workflow acceptance. |
| H03 | First workflow / agent orchestration | The new test chat's `functions.exec` cell had an extra closing parenthesis after a tool-discovery `map(...)`; the retained tool result was `SyntaxError: Unexpected token ')'`. | The whole cell failed parsing before the Vera preflight or any client work ran. The chat stopped and retained `outputs/resoconto-test-01.txt`. | Inspected the exact call and result in the chat transcript. Supplied the corrected single preflight call from the coordinator. The same GPT-6.1 Sol chat resumed and the installed preflight passed, without changing Vera source or case identities. | Rejecting invalid JavaScript is expected. The agent typo is not evidence of a Vera defect; stopping and recording it follows the user's test instruction. |
| H04 | First workflow / reporting transport and host approval | Ordinary usage flush returned exit zero with zero delivered, six queued events and two `URLError` entries. | The test stopped before client access. A public-URL diagnostic reproduced restricted-shell DNS failure; the identical approved escalated diagnostic reached HTTP 404, proving DNS/TLS/HTTP there but not API health. | Automatic approval review rejected the global flush because its queued payload/destination had not been reviewed or specifically authorized. The chat remains stopped. Subsequent read-only inspection found all six queued events belonged to two October 17 Archive Organization tests with prerelease version `0.1.406-folder-intake.1`, rejected by today's event schema. No retry, deletion, rewriting or alternative transmission of those events followed. A21 repairs the independent ordinary-startup coupling. | Preserve queued evidence and respect the host denial. A distinct current-task delivery must use ordinary host permissions; repairing scope does not authorize transmitting the rejected historical queue. |
| H05 | First workflow / persistent-state write access | Fresh 0.1.442 chat `01a1597b-5104-7ea1-b14d-cd58d8415689` verified the exposed version and passed preflight, then its scoped usage start returned `Usage reporting unavailable (OperationalError)` with exit one. | Test stopped before accounting; task UUID `029bab49-839a-4a58-b11f-9ab25ba33c79` was retained in the chat workspace but no row was inserted in the usage database. No historical flush ran. | SQLite `quick_check=ok`; restricted `r+b` access failed with errno 1, while an approved no-write probe succeeded. After direct user authorization was verified, the identical installed start command succeeded through normal host approval in the coordinator chat: one delivered, zero queued. Readback verifies the current event's receipt owner/hash and all six historical payloads unchanged and unacknowledged. | This demonstrates a host write-access restriction without evidence of database corruption or unsupported Python. Successful registration is not accounting or privacy-report acceptance. |
| H06 | Host approval / scoped current-task delivery | Automatic approval review rejected the coordinator's message asking the test chat to request approved execution of the current task's start. Its stated reason was that workflow-test authorization did not specifically authorize lifecycle metadata and the external Mparanza destination. | The scoped retry was not dispatched and the first workflow stopped. | The question named registration/lifecycle metadata, existing installation/computer credentials, the Mparanza endpoint and the 13-test scope, excluding client contents and historical queued events. The user answered “Of course. Go ahead” and subsequently the structured question with “Yes, authorize for these 13 tests”. The original question and direct reply were verified through chat readback before the approved command ran. | Explicit authorization now covers the selected metadata transfer. The historical queue remains excluded; no global retry, alternative transport or payload change was used. |
| H07 | Host approval / delegated authorization provenance | The test chat's escalated command was rejected before process creation because its reviewer considered the detailed approval scope to come from assistant-generated context. | The first workflow stopped again even though the coordinator had received the user's direct answer. | Coordinator readback established the original detailed question and direct human reply, then submitted the identical installed command to normal host review in that chat. Approved execution delivered the event with matching owner/hash. The same test chat resumed the same task; the child rejection remains recorded. | Verify the direct authorization rather than treating a relayed statement as its own proof. A host-approved command after that verification establishes recovery of this step only. |
| H08 | Integration-test host / loopback server | The exact incident CI suite passed 446 checks but the native-identity integration test could not bind its temporary `127.0.0.1` HTTP server: `PermissionError` errno 1. | Local suite failed before that test's simulated guest registration. | The same suite passed all 447 checks through normal approved execution with local socket permission; coverage is 83.13%. The server and credentials are disposable test fixtures, with no live historical queue. | The integration test needs its loopback transport. No product code, test assertion or coverage threshold was changed to accommodate the host restriction. |
| H09 | First workflow / agent file lookup | After reconciliation succeeded, the 0.1.443 test chat searched a nonexistent `modules/journal-bank-reconciliation/vendor/journal_bank_core.py`; `rg` returned exit 2. | The chat stopped before final verification/delivery, preserving the running run and generated workbook. | Inspected the actual installed inventory: the file is `modules/journal-bank-reconciliation/scripts/journal_bank_core.py`. The corrected search passed, followed by fresh material replay through normal semantic preparation, selective case review and exact balance checks. Reconciliation was not rerun. | A failed filename lookup is an agent error, not a failure of the completed calculation or evidence that the validator is absent. |
| H10 | First workflow / interpretation of incomplete measurement | Finalization returned `collection_status=incomplete`, eight `derived_output_lineage_unavailable` entries and `sent_data_has_no_source_coordinates`. The agent treated this as a delivery veto. | The draft remained `ready_for_review` despite successful reconciliation and artifact sealing. | Inspected the reporting contract and regression: incomplete measurement is an explicitly supported report outcome. Resumed normal completion of the same draft; retained every emission, unknown remainder and limitation. No measurements were fabricated or cleared. | Missing source coordinates prevent claims about unsent data. They do not prohibit delivering the draft or a truthful incomplete report. |
| H11 | First workflow / agent chat-read argument | The agent supplied `turnLimit: 12`; the chat tool requires at most 10. | Reading the original metadata authorization failed after Archive completion, so usage completion was deferred. | A direct follow-up supplied 10; the subsequent existing-task completion command returned exit zero. Final selective acknowledgement readback remains part of acceptance. | Invalid tool arguments are an agent error, not a Vera execution block or rejection of the human authorization. |
| H12 | Acceptance coordination / archived chat | A continuation message returned `session ... is archived` after the interrupted final update. | The message was not dispatched. The cause of archival is not established. | Following the user's explicit instruction to continue the goal, restored the same chat with the supported unarchive operation; the continuation was accepted. | Archived-chat lifecycle state is separate from Archive data and from the already completed calculation. |
| H13 | Second workflow / host access to persistent state | The normal installed managed launcher returned `Usage reporting unavailable (OperationalError)` and incident identity, stderr-retention and local-queue permission warnings. | Test two stopped before client/run creation, retaining task UUID `f626e2c6-2a66-414b-8b97-5b6cb377c909`. | The coordinator submitted the identical command through normal host approval under the user's existing metadata authorization. It returned exit zero, one delivered, zero queued, no blocked delivery. The resumed chat independently verified the same task and Computer ID, then created the selected client and engagement. | Host-approved execution succeeded without changing product code, database, payload, task identity or historical queue. The failed command did not expose a precise file/errno; no database corruption is inferred. |
| H14 | Fresh first-workflow restart / usage registration | GPT-6.1 Sol chat `01a15a0a-13ae-7d50-b63c-28af0556f097` verified enabled/exposed Vera 0.1.444, then `workflow_usage.py start` returned exit 1 with `OperationalError` for task `49ae526a-d458-4822-aa14-845c52af4984`. | The chat stopped on the first error, created no Archive run, and did not reach reconciliation or Luna. | Exact command/error retained in the chat's `outputs/resoconto-test-01.txt`; diagnosis and native-service repair tracked as A27. No privileged coordinator registration or historical flush was performed for this attempt. | The requested stop-on-error policy was followed. Installation/preflight success is not end-to-end acceptance. |
| H15 | Fresh first-workflow restart / diagnostic retention | GPT-6.1 Sol chat `01a15a22-fe6a-7c10-890c-046de8587849` verified installed/exposed Vera 0.1.445 and used `vera_workflow_usage` successfully. `check_dependencies.py --module journal-bank-reconciliation` returned exit zero with three reporting warnings. | The chat stopped; new Archive run `run_fcce32052209bfd70fed7b9f` remains running, inspection and Luna were not reached. The chat recorded a failed test outcome, explicitly distinguishing it from the successful dependency check. | Full transcript retained in `outputs/resoconto-test-01.txt`. Coordinator readback independently verifies both current usage-event hashes and owner, and the Computer ID. A28/A29 remain open; no workarounds or historical flush followed. | Native task registration is now evidenced in normal chat. This does not establish complete workflow success or a final report proof. |
| H16 | First workflow 0.1.446 / overly broad test stop instruction | Both native helper jobs completed with exit zero. Inspection returned `needs_review` and `mapping_review_required` for the two sources before ordinary mapping review. The test chat treated this as a terminal block because the coordinator said to stop at the first block. | Run `run_dc4bca5ce9f23591afe81f5a` stopped before specialist step 4; no reconciliation or Luna execution occurred. | Verified that the installed specialist explicitly assigns routine mapping review to the agent and prescribes it after inspection. Clarified the test instruction and resumed the same run, retaining the stop and its cause. No product code, mapping decision, receipt or validation rule was supplied or bypassed. | Reviewing monetary roles prevents treating balances as movements. This is a normal agent work step; an unresolved material ambiguity or failed validation still stops dependent work. The premature stop is a coordination error, not evidence of a new runtime failure. |
| H17 | First workflow 0.1.446 / agent diagnostic context assumption | The resumed chat's read-only Python command accessed `json.loads(context.json)['input_bindings']` and raised `KeyError: 'input_bindings'`, exit 1. | The chat stopped without writing decisions or running calculations and recorded a failed test event on the existing task. | Inspected the saved portable v2 context and the installed loader. `diagnostic_context.load_workflow_context(path, workflow_id='journal-bank-reconciliation')` verified the same run and returned its two hydrated input bindings. Sent this exact read correction and resumed the same run/task, preserving the error. | Stored portable context and verified hydrated context are distinct. This is an agent command error; the existing product loader works and no production change is needed. |
| H18 | First workflow 0.1.446 / wrong interpreter for diagnostic import | After mapping review, sealing, qualification and successful deterministic reconciliation, the chat attempted to import the core with shell Python and got `ModuleNotFoundError: No module named 'fastexcel'`. | The chat stopped and retained all calculation outputs. Luna and final delivery remain unexecuted. | Source inspection confirms the successful reconciliation already invoked material-value replay. The skill now directs fresh verification through the existing managed `semantic_review.py prepare`/`run-all` entrypoints, which replay output receipts and values before worker preparation. Do not install packages in the shell or infer that the managed environment lacks the dependency. | This is an agent execution-path error encouraged by an underspecified library-call instruction; the managed dependency check and calculation both succeeded. |
| H19 | First workflow 0.1.448 / guessed worker-receipt path | Chat `01a15a9f-cd5b-7d03-9a1b-97c2610e8c7c` completed calculation and a validated separate worker, then its ad hoc diagnostic attempted to read `semantic-review/semantic_worker_run.json`. The file had been preserved under `history/generation.40b9669b816c398d898a/`, as final preparation intends. | `FileNotFoundError` stopped the test. Run `run_2d44d601c5b5906ccae17c91` and its usage task were recorded failed; no final reconciliation delivery was accepted. | The chat remained stopped. Independent read-only inspection verifies the worker's four retained artifact hashes and the automatically delivered failed report's server hash/userID. A32 repairs the handoff; A33 addresses unrecorded shell artifact reads. A clean rerun remains required. | This is an agent diagnostic error, not a missing worker execution or lost product evidence. Preserve that distinction and the failed run. |
| H20 | First workflow 0.1.449 / incomplete preflight invocation | Fresh Sol chat `01a15ac2-d4de-7a33-be8a-35a3c323755a` omitted the required `vera` positional argument from `check_installed_product.py`; argparse returned code 2, `the following arguments are required: product`. The coordinator handoff listed flags without a complete command. | The chat stopped before creating an Archive run or reading accounting inputs, and retained resumed/failed usage events on the existing task. | Inspected the parser and verified the complete command in the coordinator with the fresh chat's actual exposed 0.1.449 skill path: exit zero, exactly one enabled installation. Sent that complete invocation to resume the same fresh chat; retain the original failure and observed recovery in its resoconto. No product change or version bump is needed. | The invalid test command does not exercise a Vera workflow. Correct the invocation without weakening installation checks or treating the failed attempt as accepted. |
| H21 | First workflow 0.1.449 / sealer input rejection | After H20 recovered, the chat verified preflight, created `run_5143e87efe17d5e371da5148`, inspected sources and read all six requested artifacts through the recorded reader. Its decision file included `potential_monetary_columns`; sealing returned code 2 and `REVIEW_RECEIPTS_BLOCKED`. | The run and task were marked failed before calculation or worker execution. The chat delivered the automatic failed-run privacy report with a server stamp. | The run stays stopped and unchanged. A35 addresses the mapping handoff. Independent verification confirms receipt `fbe42a9f-2a6c-5b9c-9e0d-b88c4fb1e84a`, SHA-256 `2f5fb6f2355c41fc5db6886835d2f67627a633e4ac92b046bf77e84f9296351f`, and expected userID `0ed4a818-1877-4652-8515-787c64de17a5`. All six reads have verified coverage; the sole unmapped emission is the failed helper's stderr, including its diagnostic pointer. | The report honestly retains `sent_data_has_no_source_coordinates` for that unproven output. Neither the stamp nor correct recorded reads make a failed workflow accepted; do not backfill historical measurements or declare arbitrary stderr metadata. |
| T08 | Coordinator source lookup | Read-only searches included nonexistent `workflow_usage_store.py` and `references/studio-archive-handoff.md`; `rg` reported those paths missing. | No acceptance operation or data write failed. | The first search located the actual SQLite schema in `workflow_usage.py`; inspected it and performed the intended read-only verification. Subsequent reference discovery used the actual file inventory. | Incorrect filename assumptions by the coordinator; no product restriction or repair is inferred. |
| T09 | Acceptance decision / premature advancement | The coordinator marked workflow one accepted after automatic report delivery, same-userID hash verification and read-only reopening, despite known incomplete measurement and an unexecuted required worker. | Workflow two was started too early. | Following the user's challenge, withdrew overall acceptance and stopped test two. The user explicitly prioritizes one fully successful end-to-end test over thirteen partial results. | Receipt validity proves retained report bytes and ownership; it does not prove the omitted workflow stage or missing source coverage. |
| T10 | Reporting regression harness | The first new assertion expected `RunStore.events()` to expose `local_response`, which that read API intentionally removes. A broader combined run subsequently exposed Variance's missing test import isolation (`modules.chart_harness`), while the same Variance tests passed alone. | These checks failed before their intended assertions; neither established a product regression. | Corrected the new assertion to verify the retained payload digest. Imported the existing Variance isolation fixture into its projection test; the same combined suite now passes all 62 checks. No production import path was changed to accommodate the harness. | Tests must use their documented read API and isolate plugin imports. |
| T11 | First-workflow integration fixture | The new fixture initially supplied Archive role `bank` instead of the documented `source` role, then placed `semantic_review` below the reconciliation output rather than using the documented sibling `semantic-review` layout. | The regression stopped during fixture setup, before its intended transport assertion. | Corrected the fixture to use the public import roles and ordinary reconciliation/semantic-review layout. The real calculation, MCP transport and simulated-worker launch regressions now pass. Production role and directory rules were not changed to accommodate test mistakes. | These are fixture defects, not evidence that the ordinary client workflow failed. |
| T12 | Native usage regression fixture | The new test used Clara `variance-analysis` instead of catalogue primary `reporting-engine`, and expected status `product_version` instead of the existing `current_version`. | Three fixture assertions failed; the macOS sandbox/native boundary reproduction itself passed. | Corrected the fixtures to the inspected public catalogue/status contracts. All 46 native reporting regressions now pass. | No product rule was changed to accommodate these test mistakes. |
| T13 | Incident-scope fixture | The new scope regression expected `latest_report_id` on the server's incident-list row; the inspected row stores its reports in `reports`. | Three assertions failed after delivery had occurred in the isolated test store. | Corrected the assertion to `reports[0].report_id`; the 90-test incident suite passes. | A fixture/API mismatch, not an actual retained-queue mutation or product defect. |
| T14 | Native execution fixtures | The first fake runtime returned no component selection, then a failure assertion used queue field `kind` rather than `operation`. New delivery tests also initially assumed Archive start emitted no metadata. | The new regressions failed on incomplete mocks or incorrect assertions. | Supplied the mock's documented component root, used the actual queue field and asserted delivery deltas from the existing Archive metadata baseline. All 13 native-execution process tests and all 12 focused reporting/scope tests pass. | Production logic was not relaxed to accommodate fixture mistakes. The native job's process, diagnostics, retained exit code and reporting boundary remain real in the tests. |
| T15 | Coordinator test host / nested macOS sandbox | Running the sandbox regression inside the already restricted command context returned `sandbox_apply: Operation not permitted`, before its synthetic Python probe could run. | That first invocation could not establish the intended file-write denial. | Ran the isolated suite through normal approved host execution. The actual sandboxed probe then raised `PermissionError`; the separate native service persisted the same synthetic job successfully. No actual-case command, identity or historical queue was used. | Host permission to create a test sandbox is separate from Vera's ordinary-chat execution acceptance. |
| T16 | Coordinator verification sequence / generated source contracts | The combined regression run started after source/version changes but before rebuilding their generated privacy contracts. Three product-report cases rejected stale installed-contract bindings; 378 other tests passed. | That combined invocation was not green. | Refreshed the reviewed manifests and generated contracts, then reran all three affected cases successfully. No contract validator or production rule was weakened. | This was an inconsistent intermediate development tree, not evidence that a fully rebuilt installed candidate failed. Run the final package checks against the completed build. |
| T17 | Cowork package assertions / fixture selection | The full package/privacy suite passed 639 tests and skipped two, but failed assertions expecting no empty Cowork hook manifest and unavailable variance reporting. One setup error came from the coordinator's `--confcutdir=tests/plugins` excluding the shared `vera_workflow_workspace` fixture. Inspection confirmed the intended empty hook map and an automatically generated, closed report for the isolated variance run. | That invocation was not green; none of these results establishes installed acceptance. | Updated only the two outdated assertions to verify the empty hook map and the automatic JSON/Markdown report. All five affected cases pass with the normal repository fixture scope (`/private/tmp/studio-archive-446-cowork-corrections.xml`). | Do not restore missing reporting or alter production code to satisfy obsolete assertions. The fixture error belongs to the verification command. |
| T18 | Draft preparation regression expectations | After changing the default to retain semantic residuals, one old test expected a classified residual to leave review without an explicit policy. Another prepared its synthetic response under the new default but ran the pipeline with an explicit lower policy, correctly causing a stale graph hash. | The first semantic regression invocation passed 66 tests and failed two assertions. | Asserted retention for the default, retained explicit-clearance coverage and used a consistent policy across synthetic preparation/execution. All 68 semantic tests and the full 476-test reconciliation suite pass. | The source-bound graph check was preserved; no stale response was accepted to accommodate the fixture. |
| T19 | Release preparation / candidate version reuse | After committing candidate 0.1.447, the additional cancellation source repair initially retained that candidate version. The package check requires changed plugin source to have a distinct version from HEAD. | The verification run passed 466 checks and failed the version assertion. The candidate had not been installed and no chat test had started. | Assigned the combined candidate Vera 0.1.448; the exact version check passes. Rebuilding all host artifacts before installation. | Distinct installable versions prevent Codex from reusing same-version cached bytes; this is release preparation, not an added ordinary-workflow gate. |
| T20 | Handoff regression / receipt-schema assertion | The new readable-path assertion initially expected the inner launcher's `vera.luna_launch_receipt.v1` schema on the component's wrapper receipt. The actual wrapper uses `journal_bank.semantic_launch_receipt.v1`. | The first run passed 67 semantic checks and failed that assertion. | Inspected the retained wrapper schema and corrected the test expectation. All 68 semantic checks pass; no production validation was changed to satisfy the test. | Verify the actual published artifact contract rather than guessing a similarly named nested receipt. |
| T21 | Candidate build / review order | Regenerating courses after the privacy-source refresh updated the Journal-Bank course's source binding, making the governing `local-onboarding` fingerprint stale. | The all-host builder stopped before completing the candidate; nothing was installed or tested in a new chat. | Compared the generated course against HEAD: only `sources` differs; the index binds that course. Refreshed the inspected source record after generation and restarted the builder. | Source fingerprints must describe the final generated inputs; no course content or professional judgment was reclassified to bypass the check. |
| T22 | Preservation check / whole-queue equality | The coordinator compared the entire incident outbox with its original 14-item baseline after H21. The queue now has 15 items, so that assertion failed. | The check did not establish that historical items changed. | Compared exact per-item hashes: all 14 original hashes are present unchanged, plus report `5879b56b-5dcd-4ba2-a2e1-4b6cb80e0111` scoped to the current test task, version 0.1.449. Its payload contains technical metadata and byte counts, without the selected client name/path, filenames or raw stderr. No queue mutation or flush followed this inspection. | Historical preservation is equality of the retained historical items, not a prohibition on recording a new current-task incident. |

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
- Commit `edb8384453aecd91204a4f3bf35c52bdade78952` is pushed to draft PR #884;
  its fresh CI is running. The supported local installation enabled 0.1.443,
  and all 2,181 cache files match the tested ZIP with no extras. Fresh GPT-6.1
  Sol chat `01a159a9-c6eb-7131-bc27-ceb3d0046094` verified the exposed version
  and successfully read `outputs/inspection.json` relative to the selected
  run, recovering A22. Agent mapping receipts were sealed; repeat inspection
  emitted three bank and two journal rows with no A23 warning.
  Reconciliation returned two matches, one unmatched bank row and zero unmatched
  journal rows. H09 stopped final verification; the same chat has been resumed
  with the inspected correct path. No completed-run or report acceptance is
  claimed, and no second workflow has started.

- The same 0.1.443 chat subsequently completed the preserved run and delivered
  the reconciliation draft: two matches, a 5 EUR bank commission still open,
  and verified closing balances of 1,295 EUR versus 1,300 EUR. This is draft
  delivery, not a claim of full reconciliation or professional adoption.
  The automatic final privacy report was included in the chat's response:
  32 recorded emissions and 90,310 characters, with incomplete measurement
  explicitly disclosed. Unsent source data remains unknown.
- Independently ran the installed `archive_report_receipt.py verify` against
  the saved final report and explicitly supplied Vera userID
  `0ed4a818-1877-4652-8515-787c64de17a5`. It returned `verified` for the same
  Archive run, revision 2, receipt `50ead784-dd72-5d8f-bcf1-e04764e9556f`,
  SHA-256 `8d8c808a64ac792523d3a9b086b17e2ae334fa9003d72499549e727799b822d8`.
  This verifies report bytes and ownership, not completeness of source-cell
  measurement or provider receipt. Read-only reopening and final usage
  acknowledgement remain to be checked before advancing to workflow two.
- Current exact-commit CI on `edb8384453aecd91204a4f3bf35c52bdade78952`
  has 17 successful workflows and two still running, with no failures.
- First workflow acceptance subsequently passed: normal reopening of the
  saved draft and privacy report succeeded without recalculation. Independent
  before/after hashes of all 61 retained non-database run files were identical,
  with no added files. The scoped usage task is completed, sequence 2, with
  server acknowledgement and no selected-task queue. Final event:
  `fc3742b5-f3cb-4462-aa95-4becadd4a33c`, payload SHA-256
  `9d26c0ed4928c93c165a992ffeb62ed59e00083c460baddcab0e065a389084e7`.
  All six excluded historical events remain byte-identical and unacknowledged.
  Acceptance covers automatic report delivery, correct-userID server proof
  and read-only reopening; it does not claim complete source-cell measurement.
- Only after the first chat became idle and these checks passed, started
  workflow two (`open-item-reconciliation`) in separate GPT-6.1 Sol chat
  `01a159bb-06db-7ae1-9316-bfca6b698e60`. Its requested synthetic case has
  three initial receivables and two subsequent receipts, including one partial
  payment. It has verified exposed Vera 0.1.443. Result/report acceptance is
  pending; no third workflow has started.

## First-workflow repair after withdrawn acceptance

Vera 0.1.444 was installed and independently verified before a fresh GPT-6.1 Sol
chat started. That attempt stopped at H14 before accounting. No workflow is
accepted. Test two remains stopped and must not be reopened.

- Real CLI inspection reproduced missing preview provenance. The producer now
  registers the cells in its bounded tabular preview before delivery; preparation
  alone counts no source exposure. Tests cover one and thirty source rows,
  the twenty-row preview bound, and an unmapped private column that remains local.
- The collector now recognizes concatenated exact producer-declared status
  lines. An additional undeclared line still makes the report incomplete and
  retains its payload hash. Journal-bank's known operational log messages now
  register their exact emitted text.
- Registered complete text artifacts can carry verified producer provenance.
  A partial read cannot inherit the complete artifact's source selections.
  The reconciliation audit and technical review-note producers use the same
  mechanism. A real three-bank-row/two-journal-row calculation produces two
  matches and the expected unmatched fee, with twenty mapped cells exposed
  when the audit is read and five private-column cells remaining local.
- The focused automatic-reporting and producer-projection combination passes
  62 tests. JUnit: `/private/tmp/studio-archive-first-producer-repair.xml`.
  This is source regression evidence, not installed end-to-end acceptance.
- Sealed mapping recipes retain their metadata provenance only when the exact
  parent was producer-registered metadata and the edit adds mapping/review
  metadata. Unknown extra recipe content cannot inherit this declaration.
- The normalizer now records transaction field origins locally. The real MCP
  bridge uses these origins for the selected case fields, including optional
  identifiers. Review packets must match a producer-recorded private packet;
  edited or unknown packets remain unaccounted for rather than being certified.
  Source coordinates and private-packet digests stay in app-only metadata.
- The worker launcher registers the exact submitted prompt/schema against
  selected candidate rows. The macOS launch-path regression uses a simulated
  model response and counts four cells from the one unmatched bank row, leaving
  twenty-one cells local. This does not establish that a real Luna call ran.
- The broader reconciliation, reporting, MCP minimization and producer suite
  passed all 573 tests, with no failures or skips:
  `/private/tmp/studio-archive-first-workflow-repair.xml`.
- The exact reporting CI selection, including the new journal-bank regressions,
  passed 163 tests with 81.58% coverage. Source quality checks pass Black, Isort,
  Mypy and Bandit at the medium/high threshold. JUnit:
  `/private/tmp/studio-archive-444-reporting-coverage.xml`.
- A further regression covers the first case's explicit exclusion of opening
  and running balance columns. It seals the agent's reviewed mapping, reconciles
  two movements and retains the unmatched fee. Reading the audit exposes 45
  mapped cells while 15 balance/private-note cells remain local:
  `/private/tmp/studio-archive-first-balance-exclusions.xml`.
- Candidate versions: Vera 0.1.444, Clara 0.1.322, Lucia 0.1.146,
  Journal-Bank 0.1.71 and Open-item 0.1.60-tabular-source.12. Only PR #884 was
  open at preflight; main remained `2d628d2ecae9ae9e447ff03353a05ec694755fc3`.
- B01/B02 recurred during packaging: the first component build found stale
  generated source contracts; the product build then stopped at stale course
  provenance. Rebuilt the contracts and courses and inspected the resulting
  delta. Twenty-one course files changed only verified source hashes and the
  newly imported `archive_cli.py`/`archive_projection.py` dependencies; lesson
  content is unchanged. All 55 localization entrypoint IDs, paths and hashes
  remain identical; only the product-manifest catalogue binding was refreshed.
- Reviewed/refreshed 21 affected privacy records, including five dependent
  catalogue/course records. All three registers validate. Codex, ChatGPT upload,
  Cowork and Antigravity builds and source-parity checks pass for all products.
  Final package/privacy regressions passed 569 tests with two expected missing
  curated-installation skips (`/private/tmp/studio-archive-444-package-privacy.xml`).
  Marketplace was untouched.
- Supported installation enabled `vera@mp-vera` at 0.1.444. All 2,181 cached
  files matched the candidate ZIP, without extras; ZIP SHA-256
  `74e8892d6a7d455e96740bc4bbcf77229536fd0e93179d6ed34077c9a799a7f4`.
- The fresh chat `01a15a0a-13ae-7d50-b63c-28af0556f097` stopped at H14.
  Read-only diagnosis found no saved usage row and no database corruption.
  The native service repair preserves the existing identity and database; it
  accepts only fixed start/record/status/task-scoped flush operations.
  Its 46 passing regressions cover real local HTTP delivery, owner/computer
  binding, replay without duplication, unchanged historical queue/identity,
  rejected command/global-queue inputs, structured storage errors, and the
  reproduced macOS restricted-shell/native-service boundary.
  Evidence: `/private/tmp/studio-archive-native-usage.xml`.
- A27 broader reporting regressions passed 292 tests with no failures/skips
  (`/private/tmp/studio-archive-445-usage-regression.xml`). The exact usage
  coverage selection plus native tests passed 163 tests at 93.49% coverage
  (`/private/tmp/studio-archive-445-usage-coverage.xml`), including three added
  task-scoped retry and snapshot-integrity regressions. Black, Isort, Mypy,
  Bandit and Node syntax checks pass for the changed source.
- Candidate Vera 0.1.445, Clara 0.1.323 and Lucia 0.1.147 packages built and
  align across Codex, ChatGPT upload, Cowork and Antigravity. Reviewed/refreshed
  24 affected privacy records plus five catalogue/course dependants. The native
  route retains the same fixed endpoint, identities and task metadata fields;
  it adds no professional-file or command input. The Geneva catalogue retains
  all 55 IDs/paths; only Vera's reporting instructions changed, leaving the
  authored jurisdictional assessments unchanged.
- Final package/privacy checks passed 569 tests with two expected absent curated
  installation skips (`/private/tmp/studio-archive-445-package-privacy.xml`).
  Source/package parity passes for every affected host. The seven native usage
  snapshot inputs match the real generated package index for all three products.
- B06 recurred while committing this repair: an empty index lock dated 17:40:25
  blocked staging. Normal host process inspection found no Git process/open
  owner; rechecked the unchanged old empty file and removed only that lock.
- Supported installation enabled Vera 0.1.445; all 2,181 cache files match the
  checked ZIP without extras. ZIP SHA-256:
  `d6eccbb255dc3436b152ee3194222c84063d7c3f2c546f5111a83c15c6f6b91f`.
  Repair commit `77ed7eda069cd405402ff9c8dca6201de0d99537` is pushed to draft
  PR #884; remote CI is still running. No production deployment occurred.
- Fresh chat `01a15a22-fe6a-7c10-890c-046de8587849` independently discovered and
  used the native usage tool. Task `49ae526a-d458-4822-aa14-845c52af4984`
  has acknowledged `started` and `failed` test events. Both stored receipt
  owners equal `0ed4a818-1877-4652-8515-787c64de17a5` and both payload
  hashes match exactly. The server status verifies Computer ID
  `fefc8400-dae2-4384-b4f5-ae24b9f49d11`. The six historical usage events
  remain unacknowledged. This establishes A27's normal-chat recovery only.
- The same fresh chat recovered the existing client/engagement/input receipts
  and created run `run_fcce32052209bfd70fed7b9f`, then stopped at H15.
  Its automatic initial privacy report records zero sends, an active run and
  no requested server receipt. It is not a final report or acceptance proof.
- Remaining work includes A28/A29 and fresh normal chat
  acceptance. The fresh first run must then execute
  its required worker, deliver and reopen its results, and verify the new final
  report against the correct userID. Preserve the earlier report unchanged.

### Candidate 0.1.446 verification

- Native execution: 14 passing process tests and five reporting-boundary tests.
  Eight task-scoped incident tests also pass. Evidence is retained in
  `/private/tmp/studio-archive-446-native-execution-final.xml` and
  `/private/tmp/studio-archive-446-reporting-final.xml`.
- Expanded incident verification: 455 tests pass, with 83.29% coverage
  (`/private/tmp/studio-archive-446-incidents-coverage.xml`). The first restricted
  invocation could not bind the isolated localhost test server; normal approved
  host execution passed without changing the test or production code.
- Package/privacy verification: the full invocation passed 639 tests and skipped
  two; the two failures and one fixture setup error are recorded as T17. All five
  affected cases subsequently pass. The three earlier stale-contract failures
  also pass after the reviewed rebuild, as recorded in T16.
- Source quality and shared-runtime synchronization pass. All-host builds and
  package parity pass for Vera 0.1.446, Clara 0.1.324 and Lucia 0.1.148.
  Native reporting regressions are included in three-OS CI.
- Repair commit `b9071f501` is pushed to draft PR #884. Supported installation
  enables Vera 0.1.446; all 2,183 cache files match the generated ZIP exactly,
  with no extras. ZIP SHA-256:
  `7d8e95af16edc88afb68cf834e338f03631d22f5e9c374bb130aa961f962dbb5`.
- Fresh GPT-6.1 Sol chat `01a15a69-648b-7f32-ad1f-5bdd725ad1e3`
  independently verified enabled/exposed 0.1.446, delivered a resumed event on
  the retained task and recovered the existing client/engagement. It created
  run `run_dc4bca5ce9f23591afe81f5a` without altering prior runs. Native dependency
  job `6e739181-ec7d-444d-b075-b3de9d9ae72c` and inspection job
  `6c052def-38ec-4822-be03-1b48b2983dcb` completed with exit zero, passing the
  previously failing persistence boundary. Its later stops are recorded as
  H16/H17; the accounting result, actual worker and final report remain unproven.
- Before committing, B06 recurred as an unchanged empty Git index lock dated
  19:12. Host process and open-file inspection found no owner or Git process;
  removal is limited to that rechecked stale file.
- These are implementation and package results. No pipeline is accepted.
  Fresh installed GPT-6.1 Sol execution, automatic report delivery/reopening and
  correct-owner server proof remain required. Test two stays stopped for the
  user to archive.

### Candidate 0.1.447 verification

- The draft-preparation repair passes the full 476-test reconciliation suite
  (`/private/tmp/studio-archive-447-journal-bank.xml`), including 68 semantic
  regressions. These include omitted policy, explicit clearance and unchanged
  strict ledgers; worker responses are simulated in those unit tests.
- The initial native-reporting CI selection passed all 71 tests locally
  (`/private/tmp/studio-archive-447-native-host-repro.xml`), but remote retries
  reproduced B12. After exposing the error and reproducing A31 locally, the
  cancellation repair passes all 72 tests, including the new scheduling case
  (`/private/tmp/studio-archive-cancellation-fixed.xml`). Six reporting-boundary
  cases pass, including literal LF/CRLF streaming bytes. Updated remote CI
  remains required.
- Vera 0.1.447, including Journal-Bank 0.1.72, builds and passes all-host package
  parity. Clara 0.1.324 and Lucia 0.1.148 are unchanged. Package/privacy
  verification passes 569 tests with two absent-curated-installation skips
  (`/private/tmp/studio-archive-447-package-privacy.xml`). Black, Isort, Mypy
  and Bandit pass for the changed source.
- Reviewed the model-data disclosure delta: the worker payload projection,
  evidence checks, destinations and strict reconciliation remain unchanged.
  The recorded default controls retention in the review queue, without implying
  user approval. Refreshed five directly affected privacy records and one course
  dependency; all 55 Geneva wrapper entrypoint bytes/dispositions are retained.
- All 14 historical incident item hashes remain unchanged. No pipeline is
  accepted. Installing the candidate and repeating normal-chat acceptance,
  actual Luna execution, automatic report delivery/reopening and correct-owner
  server verification remain required.

### Candidate 0.1.448 verification

- This candidate combines draft preparation from 0.1.447 with A31's corrected
  cancellation order; Journal-Bank remains 0.1.72. The actual cancellation
  scheduling regression failed before the repair and passes afterward, with
  all 72 native reporting tests. Black, Isort, Mypy and Bandit pass.
- The cancellation package check passed 466 cases and failed only T19's version
  check. That exact case passes after the bump. The rebuilt 0.1.448 candidate
  passes all 73 release, privacy and version checks
  (`/private/tmp/studio-archive-448-release-privacy.xml`). Its 55 Geneva wrapper
  entrypoints and all jurisdiction dispositions remain unchanged.
- All host packages build and pass source-parity checks. Installed `vera@mp-vera` is enabled at
  0.1.448, and all 2,183 cache files match the generated ZIP byte for byte.
  ZIP SHA-256: `ecd0f1be6156a04c46c471765136963b7b38a851bd53868ce1b226c72e9d5eff`.
  A sandboxed inventory initially warned about remote-catalog access; the same
  read under normal host access confirms one enabled Vera without that warning.
- All 14 historical incident item hashes still match their pre-test baseline.
- Native reporting passes on macOS, Windows and Linux at `a381adcd5`.
- Fresh GPT-6.1 Sol chat `01a15a9f-cd5b-7d03-9a1b-97c2610e8c7c` completed
  reconciliation and an actual, validated separate worker. It then stopped at
  H19's incorrect diagnostic path. Run `run_2d44d601c5b5906ccae17c91` is failed;
  its saved calculation and worker evidence remain unchanged.
- The failed run automatically delivered its privacy report and server stamp.
  Independent verification confirms receipt `3486dd50-2a46-53f0-9463-57ad2dcecab8`,
  report SHA-256 `7de955f1ab97f009a60aa53a8174fbbb48144b4f9d38f8d2d708a0444b157739`
  and userID `0ed4a818-1877-4652-8515-787c64de17a5`. Worker response, event-log,
  stderr and launch-receipt hashes also match the retained worker record.
  These proofs do not cover the shell reads at A33 or establish workflow success.
  No pipeline is accepted.

### Candidate 0.1.449 verification

- Vera 0.1.449 / Journal-Bank 0.1.73 returns the worker's actual archived
  receipt paths and puts recorded artifact reads in the immediate specialist
  steps. The initial candidate passed 68 semantic checks, 14 reporting checks
  and 464 package/privacy/release checks, with all-host package parity.
- The additional A34 integration checks exposed missing execution-artifact
  provenance before installation. Source now records the exact producer bytes
  for both receipts and the status file. All 19 reporting checks and all 68
  semantic checks pass, including three edited-artifact negatives. Rebuilt
  packages pass all-host source parity. Final package/privacy/update checks
  pass 481 cases, with two absent-curated-installation skips.
  Black, Isort and Mypy pass. Bandit reports no medium/high findings;
  its existing low-severity `subprocess` import advisory remains.
- The single changed Geneva wrapper entrypoint has been rebound without
  changing jurisdiction dispositions. Compiled course content is unchanged
  apart from source fingerprints. No new professional or course acceptance
  is claimed.
- The tested source is committed as `76cefa08f`. The existing local
  `vera@mp-vera` installation is enabled at 0.1.449; all 2,183 cached files match
  ZIP SHA-256 `87674905795b1c40df85e348b1b8baceb93c7f0117ffdc5395fc79cce73938be`.
  Fresh Sol chat `01a15ac2-d4de-7a33-be8a-35a3c323755a` recovered H20's preflight
  invocation error and then stopped at H21's mapping-sealer rejection.
  Run `run_5143e87efe17d5e371da5148` is failed and preserved. Its automatic
  report's hash and expected owner independently verify, while its one
  unaccounted stderr emission remains explicitly incomplete. Test two stays
  stopped; no pipeline is accepted.

### Candidate 0.1.450 verification

- Vera 0.1.450 / Journal-Bank 0.1.74 repairs A35's copied source-metadata
  handoff. The four reproduced failures now pass as part of 12 focused sealer
  checks. Two real CSV integration cases verify reconciliation and complete
  recorded-read provenance with and without copied monetary candidates.
- Black, Isort, Mypy and Bandit pass. All 55 Geneva wrapper entrypoints and
  their jurisdiction dispositions are unchanged. Course generation precedes
  the inspected privacy-source refresh to avoid T21's ordering failure.
- All 27 sealer integration checks pass at 85.91% coverage, including source,
  Codex and Cowork paths. All 20 Journal-Bank provenance checks pass.
- All-host builds and parity pass. Package/privacy/update checks pass 481 cases
  with two absent-curated-installation skips.
  The enabled installation remains
  0.1.449; no new test chat has started and no pipeline is accepted.

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
