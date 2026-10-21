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

Current acceptance: **one workflow accepted end to end**, Journal-Bank on
Vera 0.1.451 in fresh GPT-6.1 Sol chat `01a15aff-55ce-7892-b0ad-7631cb0cc496`.
The accepted run is `run_f833545796f658d8aaaba563`; its full evidence and the
recovered verification-network block appear below. Twelve workflows remain.
The earlier partial acceptance remains withdrawn; no earlier failed run was
rewritten or reclassified. The old test-two chat stays stopped and must not be
reopened without a later request. PR #884 passed all 98 checks, merged and was
deployed; the 0.1.452 native service passed in a fresh test-two chat. That chat
stopped before creating sources or an Archive run because the tabular adapter
requires a single counterparty per source. Candidate 0.1.453 repairs that limit
and the subsequent locally reproduced failures described below. It is not yet
accepted in normal chat. The overall goal is active.

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
| A36 | Derived result provenance / partial tabular reads | Test 0.1.450 read `resolution_funnel.json`, `human_review_queue.json` and one row of `relationship_residuals.csv` through the recorded reader. The JSON producers had no source declarations; the collector supported whole-document projections but not selected table cells. | Finalization rejected incomplete measurement after successful reconciliation and validated worker execution. | The repair declares generated summary/review JSON against their actual source fields and exact bytes, and records a per-cell map for the residual CSV. Partial reads consume only selected cell origins, including both amounts behind allocations. Identical bytes at distinct producer paths keep distinct origins; edited artifacts and missing evidence remain unaccounted. Local integration and shared regressions pass; package and fresh-chat acceptance are pending. | Exact bytes and producer coordinates are mechanically verifiable. No business result is reclassified as metadata, no unread row is counted as sent, and no professional approval is added. |
| A37 | Server task-status wording / separate receipt contracts | The current `workflow_status` response correctly reports task completed and Computer ID verified, but also reports the unused legacy usage receipt as missing and suggests manual linkage. `modules/operational_incidents/store.py::_workflow_reporting` still emits that wording and says no local remainder needs no report. The installed contract instead creates an Archive report for every selected run, including full exposure, and requires no separate usage-receipt link. | No block occurred in the accepted run, whose independent Archive receipt verifies. The server recommendation is nevertheless misleading and can reintroduce an unnecessary manual step. | Repaired in source: selected Vera tasks identify `archive_managed` receipt handling and `archive_run` report scope. They no longer infer a missing Archive receipt or require a separate usage link. Historical task links remain visible; Clara/Lucia retain task-owned reporting. Completed/failed/cancelled task regressions pass. Deployment and live readback remain pending. | A legacy usage-receipt absence does not invalidate a verified Archive report. The diagnostic must identify its actual contract and cannot claim the automatic report is missing. |
| H27 | Coordinator native service after update | The coordinator's old native incident binding returns Native incident build index is unavailable. Old 0.1.451 cache roots were removed by the supported installer; read-only process inspection finds resident services at those roots and newer services at 0.1.452. The exact responding PID is unknown. | That coordinator binding cannot read task status. | Current installed public CLI verifies the live task; the new 0.1.452 test chat independently passes native status and registers/fails its own task. No process was killed, index bypassed or cache restored. | A stale binding is supported inference, not proven PID attribution. Fresh-chat native success does not establish that the old binding recovered. |
| H28 | Coordinator acceptance handoff | The new test-two prompt incorrectly locates check_installed_product.py inside the installed plugin; it is a repository helper. | Chat stops before creating a task or inputs. | Correct repository command with the actual exposed 0.1.452 skill path passes in the same chat. The missing path and explicit recovery remain in its report. | This was a coordinator error, not a package incompatibility or a reason to add an execution gate. |
| H29 | Fresh second workflow | Chat 01a15b38-163e-74e1-93ed-8f4c277ff467 stops at A38 after native service, installation and dependency checks pass. An earlier reference read under the wrong skill-relative directory returned ENOENT and was recovered by a bounded component search. Archive reports 29 orphaned profiles but no blocked clients/runs/inputs for the selected engagement. | Task 7857cd53-ddf6-41d4-8339-6cbf110b0e68 ends failed; zero queued task events, verified Computer ID. No new sources, Archive run, accounting deliverables or privacy report. | Repairs stay in the coordinator. A fresh chat after installation must rerun the original two-file case; no artificial per-party file split. | archive_managed identifies reporting ownership and does not prove that a report exists. These results are not an accepted pipeline. |
| H30 | Coordinator pre-install inventory | The first check_installed_product invocation returned Installation verification unavailable with no detailed cause. | Installation remained on hold; the failure was not counted as an installed pass. | The same bundled Codex CLI returned its inventory successfully, and the unmodified checker then verified one enabled Vera 0.1.452 installation with its matching exposed skill. | The first failure mechanism is unknown. No Python/runtime-policy or package-integrity check was weakened. |
| T01 | Test harness | The component fixture restored `sys.path` between tests while its reporting adapter remained cached. | Broad regression run failed importing `archive_report_receipt` in the tax-litigation case. | Fixture now supplies product sibling imports per test; exact failing case passes. No product import behavior changed for this failure. | A fixture import defect does not justify changing production code. |
| T02 | Previous behavior assertions | Two older tests required an exact recovery response without new issue fields and a global listing failure for an unreceipted file. | Broader regression verification failed after the intended inventory repair. | Assertions now verify the complete recovery response and the useful behavior: verified inputs remain visible, the unreceipted entry is unavailable and its bytes stay unchanged. Subsequent broader suite passes. | Tests must validate the requested behavior rather than preserving the defect as authority. |
| T03 | Test harness / Windows CI | Job `118616483802` decoded Node's UTF-8 UI output using the Windows default encoding: `Apri incarichi →` became mojibake. | One native-navigation assertion failed; the job reported 60 passed, one failed and one skipped. | The three Archive UI harness subprocess calls now explicitly decode UTF-8. Ten focused local checks passed; subsequent Windows CI verification is pending. Production files are unchanged for this failure. | The harness must decode the actual UI transport encoding; weakening the visible-label assertion or changing production text would conceal the harness defect. |
| T04 | Source typing / CI | Job `118616484270` found that `inspect_client_manifests` reused `records` for a tuple and then a list. The exact CI Mypy configuration reproduced it locally; the earlier default-config check did not. | The runtime-quality job failed static checking. | The per-client group has a distinct variable name; inventory behavior is unchanged. The exact CI configuration now passes all 29 source files locally. Remote CI is pending. | Keep types consistent; do not weaken static checks or mistake a differently configured local pass for equivalent CI evidence. |
| T05 | Editing check | The task-scoping instruction edit expected 47 matching skill entrypoints but found 49 after applying the exact replacement. | Its final count assertion failed; the edits had already completed. | Inspected the actual diff and all matching entrypoints, confirmed all 49 contained the same intended scope correction, and verified the old global-flush instructions are absent. Shared-runtime synchronization and all 132 usage tests pass. | An incorrect editing-count assumption is not a product defect or a reason to omit two direct entrypoints. |
| T06 | New regression fixture | The plugin-suite fixture defaults unfamiliar test modules to local-only incident delivery. The new portable-PDF regression expected its isolated server store to receive the event. | One assertion failed after the production repair: 58 checks passed, one failed. | The test explicitly enables delivery to its existing in-process fake transport. The wider 191-check suite passes. No production behavior changed to address this fixture mismatch. | An isolated fake transport is permitted in this integration test; the assertion must exercise the intended delivery route without a real network dependency. |
| T07 | Release review check | The course-delta check initially assumed every source inventory retained its length. The new diagnostic helper legitimately adds one source entry to affected inventories. | The review script stopped before fingerprint refresh. | Inspected the additions, then verified all 19 changed course JSON files preserve their content after accounting for only source hashes and the named new helper reference. | New governed code must be listed; an unchanged source count is not a product invariant. |
| A38 | Open-item ordinary CSV intake | Fresh 0.1.452 test two read the published single-party source contract and stopped. Local regressions reproduce rejection of valid mapped party cells for CSV/XLSX populations, bank exports and journals. Preparation also reapplies one source party to all rows. | The requested three-party population and two-party bank export cannot run faithfully. No new Archive run or source was created in the test chat. | Working-tree repair: a reviewed party column with null common party supplies each exact row identity; source replay verifies it and preparation preserves it. Fixed-party, blank-party and forged-row regressions retain their concrete protections. | A normal multi-party export does not require partitioning, invented common identities or human mapping approval. Entity/currency/unit and cross-party allocation checks remain. |
| A39 | Open-item partial settlement cutoff | A local regression with cutoff 2026-09-30 and a 2026-10-10 receipt leaves the invoice unresolved even with post_cutoff_events_excluded=false. Partial promotion unconditionally compares the receipt with the cutoff. | A valid EUR 300 receipt against EUR 800 is ignored. | Working-tree repair respects the selected cutoff policy; included later receipts retain EUR 500 residual, excluded receipts remain excluded. | The calculation must follow the reviewed evidence period instead of silently changing the opening-population cutoff. |
| A40 | Open-item invoice identity | Exact source inspection shows document_key(F001, no date) returns F001/2001, and F002 becomes year 2002. The year is guessed from undelimited sequence digits. | Ordinary bank references do not match their actual 2026 invoices. | Removed the guessed year. A source-number reference without a date joins only one same-party, same-perimeter invoice in the supplied population, without changing source dates or keys. Same-party repeated numbers, including different years, remain unresolved. | Sequence digits do not establish a year. Explicit number/year syntax remains supported; payment amount does not choose between ambiguous invoices. |
| A41 | Open-item partial allocation ownership | A reproduced case with two different parties using the same document key is rejected as ambiguous before party compatibility is considered. | The uniquely owned partial receipt is not allocated. | Working-tree candidate enumeration checks the exact accounting perimeter before testing ownership. Same-party duplicate invoices and reused evidence remain unallocated. | Another party's identical reference cannot create ownership ambiguity or receive the payment. |
| A42 | Open-item Word source-map lineage | A complete local workflow reaches Word replay but a bank-only source group displays zero open amount beside the same printed invoice number as a populated group. The verifier resolves both groups to both source records. | A legitimate zero subtotal fails material-value replay. The initial diagnosis that the renderer changed 1200 to zero was disproved by inspecting the exact source groups. | Source-map groups and Word rows now retain their actual record references. A regression with the same printed numbers in different explicit invoice years checks delivery and replay without merging the records. | Repeated display names cannot substitute for record identity. Numeric replay remains required and unchanged. |
| A43 | Open-item XLSX source parser | Bandit identifies three medium-severity standard ElementTree parses in the bounded XLSX reader. | XML entity expansion remains possible within an otherwise bounded source reader; this was found during code validation, not in the synthetic chat. | Replaced those calls with defusedxml, already present in the shared runtime and declared explicitly for the standalone component. Added a source-level entity rejection regression; no runtime-policy counter changes. | A concrete XML entity hazard justifies the parser behavior. Ordinary workbook values remain admitted. |
| A44 | Native Open-item initial readiness | The native integration test fails on a new started Archive run: context treats the automatically created model-data report pair as interrupted accounting output. | Even draft_save fails before calculation with Existing Open-item outputs or interrupted work require review or recovery. | Candidate 0.1.453 uses the existing archive_reporting_paths ownership contract to separate the exact owned report sidecars from unfinished work. The original native CSV case now calculates; unknown output and pending-intent regressions still retain recovery state, and foreign-run reports are refused. | A new run's automatic reporting is not evidence of interrupted accounting. Actual unowned output or an unfinished request must not be overwritten. |
| A45 | Native Open-item source conventions | The native draft schema excludes tabular and rejects null party_ref; compilation also requires exactly the older text-adapter fields. | The native route cannot retain an ordinary reviewed multi-party CSV selection even after the underlying reader repair. | Candidate accepts the bounded tabular draft and null common party; the unchanged public producer validates the exact completed layout and source cells. Native regression with the original three invoices and two later receipts passes. | Source mapping is reviewed by the agent; fixed schema validation must represent the supported input contract rather than impose a single-party fiction. |
| A46 | Native Open-item review attribution | Native prepare requires human_reviewed=true even for preparing a reviewable draft; the MCP schema also fixes the value to true. | An agent either cannot prepare the requested work or would have to claim a human review that did not occur. | Candidate accepts and persists explicit agent or human source-review attribution; the native regression uses agent.codex and human_reviewed=false, with professional_approval=false. Existing human panel submission remains supported. | Routine source review can be performed by the agent under the user's explicit authorization. Adoption, signing, filing and external actions are separate. |
| A47 | Open-item absolute source-decision lookup | The 0.1.453 normal-chat producer fails with exactly one current reviewed source decision is required per source. Its adapter lookup accepts the exact absolute input paths supplied by the agent, while the assurance decision lookup accepts only input-relative keys. A local regression reproduces the missing decisions with otherwise unchanged sources and mappings. | Neither reviewed CSV is qualified and no accounting report is produced. The failed run and assumptions are retained. | Candidate 0.1.454 resolves the exact current absolute and full input-relative path to the same source receipt. It preserves relative identities in decision receipts and refuses foreign-run paths, ambiguous basenames and conflicting aliases. All 399 component tests pass with 81.72% coverage, including full Archive production with absolute mappings. Fresh acceptance remains pending. | Path spelling is not a missing professional review. Exact source identity must stay bound to current bytes without forcing an undocumented spelling. |
| A48 | Native Open-item nullable source conventions | The underlying producer admits null for a missing thousands separator, but the native draft validator requires text for that money field. The same native CSV regression fails with Invalid unfinished source convention when the valid explicit null is used. | A valid ordinary CSV convention cannot be retained through the native service. This was reproduced here, not in the normal-chat CLI route. | Candidate 0.1.454 mirrors only the producer-admitted nullable entity/party and decimal/thousands fields. All other values still reach the existing complete source validator. The native panel also encoded its Assente choice as an invalid empty string and offered an unsupported space separator; it now preserves null and only the supported choices. All 57 native intake, reporting, regeneration, panel and bridge regressions pass after the separate A49 repair. | An absent thousands separator is not an incomplete human decision. The transport must preserve the producer contract. |
| A49 | Native Open-item JSON transport | CI job 118919566070 installed PyMuPDF 1.28.2. Its legacy import writes a warning to stdout before JSON; 42 native tests fail with JSONDecodeError. Two local public-bridge regressions reproduce corruption from import and execution diagnostics. | The native service cannot read an otherwise valid contract or review response. This is a real protocol defect, separate from the CSV path failure. | Candidate 0.1.454 reserves stdout for the final JSON response in both Open-item bridges and retains Python diagnostics on stderr. Both regressions and all 57 real native-suite checks pass locally; CI verification remains pending. The test-only regeneration launcher separates its own import diagnostics in the same way. | Dependency diagnostics are not accounting data or evidence of an incompatible runtime. No version pin, policy-counter change or skipped JSON validation is introduced. |
| A50 | Public Open-item review runtime selection | The public MCP replay selects an override, project environments or PATH Python, but omits the shared environment used by the successful producer. Replaying that fallback with /usr/bin/python3 fails on missing defusedxml. A public save regression with a valid shared environment and unrelated unusable project interpreter fails before repair. | The installed normal chat generates the correct three-invoice drafts but save_open_item_reconciliation_decisions returns Complete assurance replay failed. The original tool conceals subprocess details, so its exact interpreter is not independently attested. | Working-tree follow-up prefers the existing shared interpreter before project/PATH fallbacks, preserving an explicit override. The same public save regression passes. No dependency upgrade or runtime version gate is added. | A tool that resumes the producer must use its available declared runtime rather than assume the unrelated chat project provides dependencies. |
| A51 | Cancellation confirmation after Archive closure | The cancel operation writes its request and the worker stops, but result delivery then rejects the already-closed Archive run. Retained job 6780d3e0-16b7-4661-8be4-aaa0d05a4476 has state cancelled and returncode -9. | The user-facing call reports failure and cannot confirm cleanup despite successful cancellation. | Working-tree follow-up returns only service-owned cancellation status after closure, including status polling of a cancelled worker. Undelivered stdout/stderr are withheld and the sealed report bytes remain unchanged. Focused regressions pass. | Stopping or confirming an owned worker is distinct from sending new professional output into a closed report. |
| A52 | Open-item outgoing-data provenance | The failed 0.1.454 run records four unmapped emissions: the producer summary, validation index, render index and review error. Both imported CSVs have exact read coordinates, but the component does not register the emitted producer summaries and review projections. | The automatic report correctly remains incomplete despite recording all 36 known source cells; no source minimization claim is supported. | The working-tree repair binds exact producer status and private-review digests, records actual CSV/XLSX field origins, and keeps full mutation objects in app metadata. The CLI omits free-form engagement text. Eight focused cases pass, including exact selected-cell counts, pending-review counts, full regeneration, and rejection of false partial-payment claims. Unknown errors and edited or unsupported data remain unmeasured. Installed normal-chat acceptance remains pending. | A server signature proves the report identity, not complete outgoing-data measurement. |
| A53 | MCP review transaction context recovery | The real three-invoice public-MCP integration passes save, but apply fails assurance replay. Temporary diagnostic instrumentation identifies `current Open-item Reconciliation customer-run context is unavailable`: the Python resolver recognizes `.audit-review-transaction-` browser copies but not `.generated-review-transaction-` MCP copies. | A valid managed run cannot apply its review through the public MCP route, even with the correct interpreter. | Admit both producer-owned working-copy forms only at their existing locations inside the same run. Portable client/run identity and source receipts still revalidate. | Different internal transaction names do not establish a different client or invalid source. |
| A54 | Retaining an empty predecessor directory | After A53, the same integration fails with `Review transaction changed an unauthorized directory` for the predecessor's empty `.open_item_reconciliation_cache`. The Python producer retains the full snapshot but returns only its file paths to the MCP transaction validator. | Correct snapshot preservation is rejected because its empty directory has no file from which the validator can infer the directory. | Return the freshly replayed history's directory list as well as its files, and validate their actual directory types before promotion. The three-invoice public save/apply integration then passes. | Preserve exact predecessor contents, including empty directories; do not treat their absence from a files-only list as evidence of an unauthorized change. |
| A55 | Partial-payment report readiness | The integrated public save/apply and native regeneration succeeds with all mechanical checks and semantic review passed, but `report_ready=false`. The gate independently rejects every allocation with `balanced=false`, including the verified EUR 300 payment on an EUR 800 invoice retaining EUR 500 outstanding. | A correct partial settlement cannot become a ready report, despite being a central result of this workflow. | Carry the exact partial-ledger IDs already rederived from source evidence into gate evaluation. Their retained residual is allowed; unbound imbalances and claimed full closures remain checked. The real public save/apply and native regeneration integration reaches final_ready/report_ready with source files and retained predecessor files unchanged. False full closure and erased residual regressions also pass. | An unpaid residual is an accounting result, not by itself an arithmetic or evidence failure. |
| A56 | Ordinary decimal tolerance rejected during preparation | Fresh 0.1.455 chat supplies the exact string `amount_tolerance="0.00"`; the producer rejects it with `amount_tolerance must be canonical Decimal text`. The existing calculation helper accepts that same value as exact zero, while the preparation layer requires the already-canonical serialization `"0"`. A public preparation regression reproduces the rejection. | The run stops before producing Excel/Word and never exercises the repaired public review. | Reuse the calculation's exact finite non-negative parser at intake and serialize its result canonically. Receipt replay still requires the stored canonical form. Seventeen focused tolerance checks pass, including negative, non-finite, ambiguous and binary-float rejection. Full candidate checks and installed acceptance remain pending. | Canonical storage does not require rejecting equivalent exact input notation; normalization changes no tolerance or accounting decision. |
| A57 | Calculation parameter treated as an unowned accounting figure | After A56 normalization, the temporary public integration rejects the Word tolerance paragraph as a material figure outside a workflow-owned table. A nonzero tolerance also reproduces the corresponding Excel failure for its Assumptions value. The validators demand source-record ownership for a declared calculation parameter. | Valid explicit tolerances prevent delivery of the generated documents. This was found in candidate integration, not in a resumed normal chat. | Carry the canonical prepared tolerance into rendering. Match the renderer-owned parameter line and Assumptions cell against that exact sealed value, separately from source-record figures. Twenty-six focused tolerance/report tests pass, including all five languages and changed or erased values in both Word and Excel. The existing arbitrary-figure and source-formula checks remain. | Parameter identity is established by its sealed input value; treating it as an invoice amount is a false classification. |
| A58 | Failed-run report linked but not displayed | The completed 0.1.455 chat's final answer contains a report link and an incomplete-measurement notice, but no readable report body. No saved-report show command appears in that turn. Archive already returns `vera_reporting.display_markdown`, and the existing generic contract requires displaying it. | Saving and signing succeeded, but the transcript does not establish the required inline delivery. | Clarify the Vera-specific reporting reference: show the actual returned Markdown even for an incomplete failed-run report, with links in addition, and use the saved-report reader when the returned text is unavailable. Report generation and the shared Archive implementation are unchanged. Fresh normal-chat delivery remains unproved. | This is an observed handoff failure, not evidence of a missing report or invalid server signature. Clearer instructions alone are not acceptance evidence. |

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
| B14 | CI Windows foundation / cancellation at job limit | Job `118860947624` ran all 125 foundation tests successfully in 551.56 seconds, then reported cancellation; the code-quality step was skipped. Its total job time was about ten minutes, matching the configured ten-minute budget in `fusione-guidata.yml`. | The exact repair commit still lacks a green required job; passing pytest output alone does not establish the skipped checks. | Source job budget increased from 10 to 15 minutes, retaining every test and quality command. Required CI on the next commit remains pending. The cancellation is consistent with the configured limit; no failing test is shown. | Do not weaken test assertions or treat a cancelled job as green. This CI resource limit is separate from ordinary Vera execution. |
| B15 | CI macOS runner allocation | `Local helper environment (macos-latest)` job `118860946811` is cancelled, has runner ID 0, an empty runner name and no steps. Its log endpoint returns BlobNotFound. The other 96 checks succeeded; B14 is the other cancelled job. | This job provides no test result and cannot count as green. | Re-run through the next source commit; no product or test change is justified by this evidence. | No runner execution is evidenced. The reason GitHub cancelled the unassigned job is unknown. |
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
| H22 | First workflow 0.1.450 / final reporting | Fresh GPT-6.1 Sol chat `01a15ad6-71f0-7d13-a0ce-09edc3d67df6` verified the installed version, resumed the authorized task, sealed copied mapping metadata, reconciled two pairs with one EUR 5 bank residual, and ran the validated worker. Both returned archived receipts were readable and accounted. Finalization reported three derived-output lineage gaps (A36). | The chat stopped, failed run `run_8cc0a81736810e631d5ff33b`, and automatically delivered the failed-run privacy report and server receipt. No pipeline is accepted. | Read-only server verification confirms report SHA-256 `8df9feb2614027db9915ae4ffa684c7f47725c5c7c26bdbaa52cf9801b331bfc`, receipt `a8e5f6bb-c2d4-5df7-9668-6432d905089d`, and userID `0ed4a818-1877-4652-8515-787c64de17a5`. Worker response/events/stderr/launch file hashes, validated-result content hashes and graph binding verify. A36 repairs future runs; this failed report stays unchanged. | A stamp verifies report identity and owner, not completeness. Separate worker execution is observed; actual model/effort attestation remains unavailable and is not claimed. |
| H23 | First workflow 0.1.451 / agent-authored command | Fresh GPT-6.1 Sol chat `01a15af3-50be-7423-885b-1090d870b2e8` passed version/input checks, mapping, reconciliation and the validated worker. Its additional Python command to check balances and write prose contained one extra closing parenthesis and exited with SyntaxError before executing. | The chat stopped, failed `run_d5339195724a34040da8b1cb` and delivered its automatic failed-run privacy report. This is an agent-command error, not an observed Vera engine defect. | The coordinator corrected the exact expression and tested the full command against isolated synthetic inputs: bank 1295, journal 1300, difference -5, both progressive balance checks valid. No real run was changed and no product edit was required. This failed run's reporting is complete with no measurement errors; receipt `8d2460f2-20b3-5ccd-b838-cd1e6a6a6e1e`, report SHA-256 `4ea2138991c30ef00094eb886661cc97672440bd599329c9cb3f098d78863ba5` and expected userID verify independently. Worker artifacts and graph binding also verify. | A complete failed-run privacy report proves reporting for these actual sends, not successful end-to-end delivery. Preserve the failed run and restart only test 1 on the same verified 0.1.451 installation. |
| H24 | First workflow 0.1.451 clean retry / host Python cache | Chat `01a15af9-79ae-7a61-8d9a-0758adb1fddf` completed reconciliation and a validated worker for `run_239e95647a784ddf43122d25`. Its additional `python3 -m py_compile work/controllo_saldi.py` attempted to create bytecode under the host Apple Python cache and failed with PermissionError before the balance calculation ran. | The chat stopped and failed the run; complete professional delivery was not reached. | The coordinator compiled the exact source in memory successfully, without writing a cache or executing the real-case script. Syntax checking needs no new Python version, external-directory write permission or Vera product patch. Keep dependent commands sequential rather than queueing execution before compilation succeeds. | This is a host/tool-use failure in an additional agent command; do not describe it as a missing Vera runtime capability. |
| H25 | Coordinator prompt / overbroad ban on manual measurements | Automatic approval review rejected the already queued balance-check script: it interpreted the coordinator's instruction not to produce manual measurements or receipts as forbidding accounting balance calculations. That wording was intended to prohibit fabricated privacy exposure counts and receipts. | The optional accounting check was denied before execution, contributing to H24's stopped delivery. | Narrow the test handoff explicitly to privacy measurements and receipts. Ordinary local accounting calculations and draft preparation are already part of the user's original reconciliation request. No denied command is retried in the stopped run and no approval is invented. The automatic failed-run report is complete; independent proof verifies SHA-256 `245d7e22a25a16cc5dac6cda0b24dcc20d39105e97d6ee00575be93676c7b267` against the expected userID and run. | This block came from the coordinator's ambiguous instruction and automatic approval review, not an observed Vera engine defect. The scope correction preserves the ban on manual privacy evidence and records both failures. |
| H26 | Accepted first workflow / independent verifier network | The third 0.1.451 chat completed reconciliation, the separate validated worker, balance checks, professional delivery and Archive finalization for `run_f833545796f658d8aaaba563`. The independent shell verifier then returned URLError, so the chat stopped and marked its usage task failed while preserving the completed Archive run. | Acceptance was held pending independent server proof. | The coordinator ran the unchanged installed verifier with authorized host network access and explicit expected userID; it returned verified for `4cdc26f113b17e8b6551c8c4bb7a742132409f1a5ca39481a7119c349ae33d37`. A restricted-shell diagnostic separately reproduced DNS gaierror 8. The chat then reopened the saved report, recorded resumed/completed on the same task, and retained the original block and recovery. Report and run hashes remained unchanged. | This is recorded recovery of the independent acceptance check, not recalculation, fabricated privacy evidence or a bypass of a denied transmission. The server hash, owner and Archive run were actually verified. |
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
| T23 | Derived-output regression and proof assumptions | The new application test and first proof command guessed `resolution_application.json`; the actual file is `semantic_resolution_application.json`. The CSV negative test replaced `5.00`, but canonical output held `5`, so it changed no value. A later proof compared logical content digests with raw file digests. | These coordinator checks initially failed or failed to exercise their intended mutation. They are not additional product defects. | Used the actual returned application filename, changed the selected CSV cell through its CSV structure, and verified logical JSON digests separately from file-byte hashes using the constructor contracts. All 34 Journal-Bank checks pass; all seven worker bindings verify. | Correct test and proof assumptions rather than changing production behavior to accommodate them. |
| T24 | Candidate packaging / source changed during build | Final source review identified repeated XLSX coordinate scans. That correction landed while the first 0.1.451 build was still finishing, so the build rejected stale service privacy fingerprints. | The intermediate package was not accepted or installed. | The table regression now verifies one workbook scan for multiple output cells and correct selected-row coordinates. Source edits are frozen, the inspected source fingerprints are refreshed, and every affected host package is rebuilt together before parity checks. | This is a development build-order error; no runtime policy counter or ordinary-user approval is added. |
| T25 | Coordinator commit / stale Git lock | Committing the verified 0.1.451 candidate failed because `.git/index.lock` already existed. It was empty and dated 22:03:55; `lsof` found no owner and the process inventory showed no active Git writer. | Commit and installation were held. | Recheck the exact lock and Git processes, remove only that stale empty lock, then retry the existing branch commit. No repository contents are reset or discarded. | A local repository lock, not a Vera execution block or failed product test. |
| T26 | Status-regression fixture | The first new Clara/Lucia scope tests inherited Vera's `journal-sampling` default, which is absent from those products' catalogues. | Two tests failed validation before exercising status. | Corrected only the test inputs to existing Clara `business-planning` and Lucia `quesito-legale-fiscale` processes. The intended five pre-fix assertions then failed; the repaired combined suite passes. | This is a test-fixture mistake, not a new product restriction. |
| T27 | Coordinator staging inventory | The commit precheck omitted generated `.claude-plugin/marketplace.json` from this task's allowed paths, so it stopped before staging anything. | No commit or product operation ran. | Inspected the diff: only Vera, Clara and Lucia version numbers changed to the three built candidates. Include this generated local Cowork catalogue in the same commit. | This is package-source bookkeeping, not an external Marketplace upload or a product execution block. |

| T28 | Coordinator validation sequencing | One first-pass integrity regression failed because implementation bytes changed while the full suite was running. | That run could not establish a stable candidate result. | Froze product source and reran the complete suite: 389 passed. No integrity check was removed. | The rejection correctly detected in-run source change; source edits and acceptance validation must be sequential. |
| T29 | Word layout regression fixture | Adding exact record references changed the source-map table headers; the existing test assumed the old column set. | The first wide-table regression failed. | Kept document and record references as repeated anchors, updated the fixture to include its actual reference, and verified the existing width, amount and completeness assertions. The full suite passes. | The source-map lineage repair changes the intended output schema; no production behavior was weakened to accommodate a test. |
| T30 | Coverage harness for retained implementations | Standard coverage found virtual Python filenames that the bootstrap compiles from unchanged .source bytes, then omitted those helpers because physical .py files do not exist. | Its initial 76 percent summary omitted executed implementation files. | Added a test-only coverage filename tracer; complete measurement now includes all five retained modules and reports 81.70 percent with 389 passing tests. CI runs the full suite and the same measurement. | Correct source attribution preserves executed line numbers and does not omit uncovered production code or alter the bootstrap. |
| T31 | Coordinator development diagnostics | Several guessed helper paths/globs and a shell quote failed; an optional diff-cover module was absent. A first preservation check incorrectly assumed a .vera directory, so it reported missing paths before hashing. A new broad format check found an untouched legacy test file. | These checks produced no product mutation or client-work result. | Read actual paths, verified the existing Vera ledger, and matched all 16 old-run and 10 imported-file hashes. Required full coverage and scoped formatting/type/security checks pass; no optional package was installed and unrelated legacy formatting was not changed. | Failed diagnostics are not evidence that archived files changed or that Vera needs a new runtime restriction. |
| T32 | Coordinator premature test stop | The first fresh 0.1.453 chat used nonexistent paths in three read-only source searches. The coordinator stopped on the failed command marker before inspecting the cause. | The started run was marked failed before accounting execution; no producer failure had occurred. | The stop is recorded as coordinator error. Exact existing reference/source paths were inspected here; a new task and run reused the two immutable CSVs. That later attempt stopped independently on A47. Both failed histories are preserved. | A command status alone does not establish a product defect. Inspect the error before attributing or interrupting; record recovered diagnostic errors in the test output. |
| T33 | Coordinator diagnostic and test-fixture errors | Additional searches named nonexistent files or an unmatched shell glob. The first bridge regression used pytest's reserved request parameter name and failed collection. | These commands did not establish a product result. | Used the actual file inventory and renamed only the fixture parameter; both intended pre-fix JSON corruption regressions then failed and passed after A49. | Record development mistakes separately from product defects; do not change production behavior to satisfy an invalid test fixture. |
| T34 | Unreleased provenance implementation errors | The first new regression exposed a copied helper name absent from Open-item; the next exposed provenance markers added before an exact internal transaction-response comparison. Some diagnostic searches again named nonexistent files, and one replay inspection printed an unnecessarily large synthetic result. | The first two were mistakes in the unshipped repair, not defects of the installed 0.1.454 release. | Use the component's existing canonical serializer and add transport provenance only after the internal transaction closes. The selected-cell and public save/apply regressions pass; subsequent A53-A55 failures are separately traced to existing product behavior. | Keep failed repair attempts and diagnostic mistakes distinct from observed normal-workflow defects. |

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
  Installed 0.1.450 was verified against all 2,183 cache files and exercised in a
  fresh GPT-6.1 Sol chat. It passed the repaired mapping and receipt handoffs,
  then stopped at H22. Its failed report and worker proofs verify; no pipeline
  is accepted.

### Candidate 0.1.451 source verification

- A36 is repaired in the Journal-Bank producer and shared Archive collector.
  Source JSON results retain exact producer hashes; selected residual CSV cells
  retain per-cell source origins. Preparation alone records no send.
- All 34 Journal-Bank provenance checks and 68 semantic checks pass. The complete
  reporting CI suite passes 198 tests with 82.74% coverage (the new projection
  runtime itself has 82%). Changed-file Black, Isort, Mypy and Bandit checks pass.
- The initial focused regression reproduced both JSON gaps and six nonempty
  residual selections. T23 records the separate new-test/proof mistakes and
  their corrections. Changed-artifact and missing-origin negatives retain
  incomplete reports; equal table bytes cannot swap producer paths.
- Unique package versions are Vera 0.1.451, Journal-Bank 0.1.75, Clara 0.1.325
  and Lucia 0.1.149. Clara and Lucia receive the synchronized reporting runtime;
  this does not claim acceptance of their workflows. Runtime policy remains 15.
- All 55 Geneva wrapper entrypoints and jurisdiction dispositions are unchanged.
  Reviewed privacy controls describe the new source links; no additional model
  payload, recipient or external delivery route is introduced.
- Final review also removed repeated XLSX scans: the table registrar builds one
  coordinate index per exact workbook during a declaration, and verifies source
  hashes at the end. A regression verifies one scan and exact selected-row
  coverage. T24 records the discarded intermediate build.
- All-host builds and exact package parity pass. Package/privacy/update checks
  pass 481 cases with two absent-curated-installation skips. The Vera ZIP hash
  is `e74c290a4494fd7d01512d90c22d3a24cf932059279d72bf43c569b78bf6392b`.
  Installation and fresh-chat acceptance remain pending.

### Accepted first workflow: Vera 0.1.451

- Chat: `01a15aff-55ce-7892-b0ad-7631cb0cc496`, GPT-6.1 Sol. Enabled source
  and all 2,183 installed cache files match the verified candidate ZIP.
- Run `run_f833545796f658d8aaaba563` is `completed`. The actual worker completed
  and validated; response, events, stderr, launch receipt, logical result
  hashes and graph binding independently match. The runtime does not attest
  actual worker model/effort, and this audit does not claim that it does.
- Two matches and one EUR 5 bank-fee residual are preserved. Independent read-only
  inspection opens the workbook and verifies the declared counts, balances of
  1295/1300, all progressive-balance checks, and byte identity of every delivered
  file and the complete ZIP with the archived outputs. No accounting entry or
  professional adoption was invented to close the residual.
- The original final response automatically delivered the readable privacy report.
  Collection is complete, with no errors: 27 sends, 127,139 characters, all 33 bank
  cells and 22 journal cells recorded as sent. No reduction of source exposure is
  claimed for this small case.
- Server receipt `b388a42e-ac01-5005-b0bf-f03ab02b3af3`, revision 1, independently
  verifies report SHA-256 `4cdc26f113b17e8b6551c8c4bb7a742132409f1a5ca39481a7119c349ae33d37` against userID
  `0ed4a818-1877-4652-8515-787c64de17a5` and this exact Archive run.
- Reopening displayed the same saved report without recalculation or mutation of
  either the report or completed run. Usage task
  `49ae526a-d458-4822-aa14-845c52af4984` is server-side `completed`, with verified
  Computer ID `fefc8400-dae2-4384-b4f5-ae24b9f49d11`, all 22 events acknowledged
  and zero queued events for this task. All 14 historical incident entries retain
  their original exact hashes; the one extra current-task report remains separate.
- H23-H26 preserve every failed attempt and recovered block. A37 is repaired in
  source and awaits deployment/live readback; B14/B15 await green final CI.
  Neither is replaced by a fabricated receipt or a claim of completed CI.
  Only this pipeline is accepted. The remaining 12 tests, release completion and
  the overall goal remain outstanding.


### Task-status follow-up after first acceptance

- The public status API now distinguishes Archive-owned reporting from separate
  usage-task receipts. It makes no claim that an Archive report exists without
  inspecting that report. Historical links and all source/report bytes stay intact.
- Related incident, task-usage and receipt suites: **394 passed**, **94.44%**
  coverage; changed store coverage is 95%. Black, Isort, Mypy and Bandit pass.
- Product versions reserved after checking the sole open PR: Vera **0.1.452**,
  Clara **0.1.326**, Lucia **0.1.150**. Their reviewed server fingerprints require
  regenerated packages. No reconciliation engine, Archive collector or worker
  implementation changed after the accepted 0.1.451 run. All-host builds and exact
  source/package parity pass, together with **481 package/privacy/update checks**
  (two absent-curated-installation skips). ZIP comparison finds 2,186 files with
  no additions, removals or executable changes; 121 metadata/provenance files
  changed. Final CI, installation and deployment are pending; this is not a new
  end-to-end acceptance claim.

### Deployed 0.1.452 and second-workflow restart

- PR #884 passed all 98 checks on `1e58198d3d7465b6cf0c913b9673e537e9b79e24`.
  Merge `3f6f8796ec49b2b4cd5f71f31ae18e6d75b98a56` has the identical tested tree.
  Server Git pull and normal restart succeeded; live task status returns
  `archive_managed` / `archive_run`, verified Computer ID and zero queued events.
  The accepted first report's exact hash/user/run receipt was reverified after
  deployment, with report and completed-run bytes unchanged.
- The enabled 0.1.452 installation was verified against its generated ZIP.
  Branch cleanup verified one local branch, one remote branch, one worktree and
  zero stashes before starting this new repair branch. No Marketplace action.
- Fresh test two stopped at A38, with H27-H29 retained. Its full local report is
  `/Users/fabio/Documents/Codex/2026-10-20/vera-privacy-02-452-restart/outputs/resoconto-test-02.txt`.
- Candidate Vera **0.1.453**, Open-item **0.1.61**, is reserved after observing
  no open release PR. Initial positive/negative regression set: **123 passed**,
  including the original multi-party case in five output languages and full
  source/final replay. The complete stable-source suite, including the XML
  regression, now passes: **389 tests, 81.70% coverage**. Black, Isort, Mypy
  and Bandit pass on the changed implementation and tests. Old archive bytes
  match all 26 baseline hashes. Packaging is in progress; no installed
  acceptance, server deployment or test-two pass is claimed.
- The mechanical changes preserve source facts and enforce exact identities,
  dates, cents and record ownership. Source-role and mapping meaning remain
  agent-reviewed. No human approval, external-runtime allowlist or changed
  runtime-policy counter was introduced. The source-data flow still reads the
  selected files locally and renders existing reviewed records; party values
  already belonged to that disclosed source/output path. Reports now preserve
  them per row and add local record references to source-map tables.

The first wider native check exposed A44 and stopped installation. Some older
negative tests also incorrectly expected an empty output directory after Archive
start; they now verify the retained report pair and absence of accounting
outputs. This is a test expectation repair, separate from A44's product repair.
Four additional native regressions pass: the original multi-party CSV with
recorded agent review, unknown output, pending intent and foreign-run reporting.
The optional human panel still uses its existing explicit submission; this test
establishes the service route, not a human-panel CSV mapping experience.
The package checks repeated after the native repair pass **481 tests**
(**2 skipped**), and all host package parity checks pass.
The complete native intake, reporting, regeneration, browser-panel and component
integration group now passes **125 tests**. Both human and agent source-review
attribution are covered, including rejection of contradictory attribution.
The rebuilt 0.1.453 Codex, Cowork and Antigravity packages pass parity.
Installation, deployment and fresh normal-chat acceptance remain pending.

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

## Fresh 0.1.453 test-two outcomes and 0.1.454 repair

PR #885 currently contains source commit fb64c735b5cddb4a9097308468fac1ce2ef03a14.
Vera 0.1.453 was installed through the supported command; the single enabled
installation and all 2,183 installed package files matched the checked ZIP.
Fresh GPT-6.1 Sol chat 01a15b67-2e5c-7c23-b692-0831e201af65 independently
verified its exposed skill/version. It remains stopped after the second outcome.

- First task eed24369-1219-4cd9-82d1-b177703ee0d6, run
  run_52b44ac34c26f2549bc0ab7e: interrupted by T32 before calculation.
  The automatic failed-run privacy report was delivered and independently
  verified against the correct userID by the published server-proof verifier;
  this is failed-run reporting evidence, not workflow acceptance.
- Second task a7989ceb-d7d5-4643-a9fd-67fbcf05d8a5, run
  run_4f75bf6417b4b6ae645fc98f: the public producer reached A47 and stopped.
  Sources, assumptions and technical diagnostics remain unchanged. The report
  openly marks unmapped sent-data coordinates as incomplete. The technical
  incident remains queued locally; historical queues were not flushed.

The candidate repair is Vera 0.1.454 / Open-item 0.1.62. The same three-invoice
case now passes with exact absolute decision keys, alongside nested receipt
identity and conflicting/foreign-key regressions. The complete component suite now passes **399 tests with 81.72% coverage**,
including full Archive producer execution with absolute mappings. Ten panel
checks pass within the complete 57-test native suite, including reporting,
regeneration and bridge protocols. All rebuilt host packages match source; 481 package/privacy/update checks pass
with two skips. CI for the final commit and fresh normal-chat acceptance remain pending. The accepted count remains **1 of 13**.

The A49 dependency behavior is documented by the upstream [PyMuPDF change log](https://pymupdf.readthedocs.io/en/latest/changes.html): 1.28.2 added the legacy import warning, and 2.0 changes it to a Python warning. The repair handles diagnostic output at the JSON boundary rather than requiring either release.

Final local 0.1.454 package SHA-256: `325993152c80cfd5b00bfb50bfa51978dc0fbf0da510c1f06d21066f04b355ad`. Compared with the installed 0.1.453 package, 135 files change, none are added or removed, and the executable delta is limited to the two Open-item source readers, two native bridges, native intake and its panel. The preinstallation inventory shows one enabled `vera@mp-vera` at 0.1.453. Its first sandboxed inventory could not reach the remote catalog; the authorized read-only retry returned the complete inventory without warnings. All 31 files retained from both failed 0.1.453 runs and their exact imports still match their preserved hashes.

## Fresh 0.1.454 test-two outcome

The fresh GPT-6.1 Sol chat `01a15b8d-ec87-7ed0-8b47-48cc5c291c60` verified its actual exposed 0.1.454 installation and the unchanged two imported CSVs. Task `e796550f-e753-4c7e-b5b0-eef305dc8235`, run `run_524f2896f03f02f4de149890`, produced the expected EUR 2,500 opening, EUR 1,500 receipts and EUR 1,000 outstanding. It stopped at the public review-save failure and marked its run and task failed. The Word document was not visually accepted, and no subsequent pipeline began.

All blocks, including the recovered dependency warning, unfinished review, privacy gaps, cancellation-confirmation failure and unrelated orphan-profile inventory warning, are retained in the chat's `outputs/resoconto-test-02.txt`. The 41 files in the new failed run have a separate preservation baseline at `/private/tmp/studio-archive-test2-454-failed-preservation.json`; the preceding failed histories remain unchanged.

The original final response automatically displayed the incomplete privacy report. Independent server verification confirms report SHA-256 `a0e67fae2d107ca6e2f25f20bedd207ca91e764e50082c6f63a8dac93ab47d06`, receipt `8ff0f7d4-d50f-5bef-9894-94ca5680c93c`, revision 1, bound to userID `0ed4a818-1877-4652-8515-787c64de17a5` and this exact run. That proof does not make the failed workflow accepted. Overall acceptance remains **1 of 13**; test 2 is stopped under the next repair and test 3 must not start.

## Vera 0.1.455 candidate verification

The source repair addresses A50-A55. A real temporary Archive integration now
runs the public producer, review validation/rendering, selected-case reads,
decision save/apply and native regeneration. It reaches `final_ready` with the
EUR 500 partial residual intact, and preserves source bytes and predecessor
history. Exact selected-cell counts are checked, while edited reviews and
unsupported origins remain incomplete. The final projection/reporting group
passes 17 cases; the broader public review/native group passed 105 before the
final CLI-summary and count-metadata refinements covered by those 17 cases.

All host packages match the source, and package/privacy/update validation passes
481 tests with two skips. Black, Isort, Mypy, Node syntax and Bandit medium/high
checks pass. The full component suite passes **400 tests with 81.69% coverage**.
Two stale test fixtures were corrected: the optional PDF import mock and a
mocked extraction result without `source_origins`. Neither correction changes
production behavior. An expanded integration also passes after reading all four
indexed cases before public save/apply and native regeneration.

Candidate ZIP SHA-256 is
`3b8751c425d1394ca0fc2e64193794266c94abaa8d0ba800f8a8530b29d00fb5`.
It changes 132 of 2,186 files relative to the verified installed 0.1.454 source,
with no added or removed files. All 72 preserved historical source/run files
still match their recorded hashes. Installation, exact-commit CI, deployment
and fresh normal-chat acceptance remain pending. No Marketplace action occurred.

## Fresh 0.1.455 test-two outcome and tolerance repair

Commit `37f25304c176d32382cade01ab0e3ae956fbc64f` was pushed to PR #885.
The supported installation command installed 0.1.455; all 2,183 cached plugin
files matched its ZIP and the independent fresh GPT-6.1 Sol chat
`01a15bc3-2e67-7993-82a4-9f58c31490ff` verified its actually exposed skill.
Task `64eb16a2-a498-43f4-8f25-c15c2703042e`, run
`run_a9be36c3363f4dbeb0768f5c`, stopped at A56. Both run and task are failed;
no Excel/Word was produced and no other test started. The run's 14 files have
an independent preservation baseline. The complete interruption log remains in
the test chat's `outputs/resoconto-test-02.txt`.

The automatic failed-run report remains explicitly incomplete because its error
emission has no source coordinates. Independent server verification confirms
report SHA-256 `0ff71889f4576265c9cf53b2fca41fb6f52807ca5670f278267539cc248ce281`,
receipt `af0f9e80-24b8-5311-ad74-53be195fc640`, revision 1, bound to this exact
run and userID `0ed4a818-1877-4652-8515-787c64de17a5`. The test read CSVs through
the shell before the producer; the report explicitly covers Vera-sent data and
does not claim to measure those shell reads. Task metadata was acknowledged;
the separate diagnostic remains queued locally, and no historical queue was
flushed. Recovery of a shell UUID command, a guessed nonexistent reference,
truncated diagnostic reads, nonblocking Archive inventory warnings and a granted
sandbox write are recorded in the test's log.

The 0.1.456 candidate normalizes tolerance input, carries that exact prepared
value into rendering, and verifies its Word/Excel presentation against the sealed
parameter rather than an accounting-record formula. Canonical receipt parsing
is unchanged. The repair adds no recipient or model-facing data field; the
parameter was already part of the generated documents. Other source changes
are version/generated release metadata.
The existing full public review integration now uses `"0.00"` as its input, so
its next run must complete review and regeneration using the observed notation.
Acceptance remains **1 of 13**; test 2 stays stopped until the candidate is ready.

The final accounting repair passes **420 component tests with 81.76% coverage**,
26 focused tolerance cases and all eight public Archive/review/projection cases.
The latter now uses `"0.00"` through complete save/apply and regeneration. Static
checks pass. The first rebuilt 0.1.456 package also passed all-host parity and
481 package/privacy/update tests (two skips); it must be rebuilt once more after
the A58 handoff clarification. The final clarification updates the Vera-specific
reporting reference. The measured report body, terminal response shape, recipients,
source-coordinate mapping and accounting calculation are unchanged, and no
execution gate is added. All 86 preserved files remain unchanged.

The A58 implementation briefly changed shared Archive descriptions, then an
incorrectly selected generated runtime copy. The build synchronization removed
that generated-copy edit and exposed its stale review fingerprint. Those two
unreleased approaches were discarded; the final delta is the Vera-owned delivery
reference. This is a coordinator implementation mistake, not an installed workflow
failure. Inline delivery remains an open normal-chat acceptance check.

Final 0.1.456 build and parity now pass for every host. The final source also
passes 59 automatic-reporting checks; the final package/privacy/update suite
passes 481 tests with two skips. Candidate ZIP SHA-256 is
`36e322d01eb42a74180fda1a54ad3d7377deedce3192ec67797a9bb4a4d9e4ba`.
Its 130-file delta against the verified installed 0.1.455 package contains no
added or removed files; only the four Open-item tolerance implementation files
are executable changes. Installation and fresh normal-chat acceptance remain
pending. The report-delivery clarification is guidance whose effect must be
observed in that next chat, not an accepted delivery fix.

### Fresh 0.1.456 normal chat: accounting passed, privacy coverage failed

The supported local installation was verified as the single enabled `vera@mp-vera`
0.1.456, with all 2,183 cache files matching the candidate ZIP. Fresh GPT-6.1 Sol
chat `01a15be6-0a1a-73e0-93a4-d5cdd9f4dc3c` created task
`a072942f-18fc-477b-b318-9c604fe5647e` and run
`run_825b61ba38d2aec1f667854a`. Its ordinary review and regeneration reached
`report_ready=true`, 17 passing checks and three agent-reviewed rows. F001 was
closed, F002 retained its EUR 500 partial-payment residual and F003 retained its
EUR 500 open balance. The chat inspected all eight rendered Word pages and the
Excel values. It reported awkward long technical references, some decimal-dot
formatting, an English date label and no dedicated counterparty column in the
operational sheet. These usability issues remain recorded, not silently accepted
as polished professional delivery.

Finalization exposed two unmapped emissions. The test stopped and marked its run
and task failed; it delivered the retained drafts. This is a failed privacy
acceptance result, not evidence that the arithmetic or reviewed drafts failed.
The final answer **automatically displayed a readable privacy report**, resolving
the observed A58 handoff failure for this attempt. It honestly reported incomplete
coverage, 11 emissions and 69,315 characters. Both input sources' 36 cells were
measured, but the unknown remainder remained explicit.

- **A59, exact-identifier diagnostic provenance:** requesting all four cases with
  `include_exact_identifiers=true` also emitted the pending-review check's note.
  That note is constructed from internal row locators; the projection supported
  the count-only version but not this producer-authored note. The earlier
  integration requested all cases without exact identifiers and missed this path.
- **A60, public replay output boundary:** the normal `audit_assurance.py
  validate-run-json` command returned the same detailed reconciliation rows used
  by the private review transaction, without registering their provenance. Its
  23,040-character response was the second unmapped emission. The replay succeeded;
  the outgoing-data contract was incomplete.

Independent read-only server verification succeeded for receipt
`95a7b974-4938-53e8-812e-b47de5269bff`, revision 1, report SHA-256
`bf6f088c401dfcaac50b285ec2bd5c3bd041ab7d983588c4d46b4f21b6e3865e`, this exact
run and userID `0ed4a818-1877-4652-8515-787c64de17a5`. The test chat's own
verification invocation had used Python isolated mode and failed to import the
receipt module; the coordinator used the documented non-isolated reader, without
altering the sealed report. Its initial sandboxed network read failed, followed
by an authorized read-only verification. Proof is retained in
`/private/tmp/studio-archive-456-failed-report-proof.json` and 77 run-file hashes
in `/private/tmp/studio-archive-test2-456-failed-preservation.json`.

The test log also retains recovered guessed paths, truncated reference reads,
pre-calculation delimiter correction, native workspace UI unavailability with a
published specialist fallback, and a corrected worker-cancel argument. It records
shell/browser/rendering reads outside the Vera-sent-data measurement scope.
Acceptance remains **1 of 13**; test 2 is stopped, and test 3 has not started.

The 0.1.457 candidate separates the normal assurance replay response from its
private review bridge. Normal validation emits a registered technical summary;
the internal transaction explicitly requests its detailed rows and keeps them
inside the component. The existing owned CLI recorder now also covers direct
assurance invocation. Requesting the detailed bridge directly still records the
actual output and leaves unknown coordinates incomplete. Exact-mode pending-review
notes are recognized only as lists of known pending row locators within the same
producer-bound private review. This is mechanical provenance checking, not a
semantic relevance rule, an execution veto or a new consent requirement.

The expanded public integration first reproduced both missing paths. After the
repair, ten projection/review/replay cases and two additional negative cases
passed. The negative cases retain incomplete measurement for an unknown
producer-bound diagnostic and for externally emitted private bridge rows. The
normal accounting checks remain unchanged. The function's five-language public
explanation also corrects its previous blanket statement that technical locators
always stay out: an explicit exact-reference request can expose them in selected
diagnostic notes. No recipient was added.

The coordinator's initial full-suite command omitted the repository's retained
source coverage plugin. It ran the tests without failures but reported only the
ordinary Python files (75.62%); that is not valid component coverage evidence.
The suite is being repeated with the exact checked-in CI coverage configuration.
Read-only diagnostic path guesses and an unavailable sandbox process listing
did not affect the product run or its evidence. These are coordinator mistakes,
separate from A59/A60. Final build, installed acceptance and saved-report reopening
remain pending for 0.1.457.

The correct CI command subsequently passed all 420 accounting tests with 81.69%
coverage. All 89 current public review/native tests passed, as did the first
0.1.457 all-host parity and 481 package/privacy checks (two skips). Before
installation, manual review found that the new locator mapping also needed to
compare the evidence-note copy with the main note. An additional producer-bound
unknown-evidence-note regression failed against that intermediate implementation;
the final condition now checks every emitted note against the same verified
locator list. No installed user run used the intermediate candidate. Final
projection and package validation are being repeated for those changed bytes;
the accounting implementation and its coverage result are unchanged.

Final 0.1.457 validation passed all 13 public projection/review/replay cases,
481 package/privacy/update checks (two skips), and all-host source/package
parity. The earlier 420 accounting cases (81.69% coverage) and 89 review/native
cases remain valid; the final change affects only diagnostic-note provenance.
Final ZIP SHA-256 is
`c8e096a4db33e5db0078030cb3c57c64d539a9d16212a3ec964f8504764c18f0`.
The 128-file delta against verified 0.1.456 has no additions/removals and only
two executable changes: the Open-item MCP server and assurance CLI. Installation
and normal-chat acceptance remain outstanding; these source/package checks do
not accept test 2.

### 0.1.457 normal-chat result: finalization failure and missing error emission

The supported local installation was verified at 0.1.457, with all 2,183 cache
files matching the final ZIP. Fresh GPT-6.1-sol chat
`01a15c06-31d3-78c2-99ba-fe9ff57318af` ran only test 2. Run
`run_757f06f00ca937238010bdeb` and task
`bf524ab3-938e-4f29-914a-931387b63bc0` are failed and stopped. Preserve them;
never resume this run to turn its result into a pass.

Observed: the reconciliation, review, apply and regeneration completed. The
three rows passed checks and were report-ready; EUR 2,500 less EUR 1,500 collected
left EUR 1,000. The agent visually reviewed all eight Word pages. No human
approval was invented. The new failure occurred during Archive finalization:
the agent declared 65 paths as `outputs/<file>` relative to the run, while the
finalizer expected paths relative to `output_dir`. Its MCP path field did not
state that base, whereas the artifact reader explicitly supports run-relative
paths. This inconsistent handoff is **A61**. It is unrelated to the accounting
calculation or an unmet professional decision.

The chat automatically displayed the privacy report. Independent read-only
verification confirmed receipt `bc7fe21f-c45f-52be-bbac-4f9d768973ea`, revision 1,
SHA-256 `5fbdc48d7181c8808f3d68e243e865b01280f3e1570fb182b147dfa06f098615`,
the exact run and userID `0ed4a818-1877-4652-8515-787c64de17a5`. The child had
encountered a sandbox network error; the coordinator's authorized reader verified
the receipt without rewriting the report. Proof is retained in
`/private/tmp/studio-archive-457-failed-report-proof.json`. Seventy-seven run-file
hashes are retained in
`/private/tmp/studio-archive-test2-457-failed-preservation.json`.

The saved report labels its collection complete: 15 emissions, 18,805 characters,
and all 36 source cells. Subsequent source inspection and a failing MCP regression
showed that Archive's failed finalization response was omitted. This is **A62**:
successful Archive responses record themselves, but neither worker errors nor
MCP validation errors were recorded. Therefore the report's complete label is
not accepted as complete response coverage. The signature verifies the retained
bytes and ownership; it does not cure that omission. The coordinator corrected
its earlier completeness claim after finding this defect.

Recovered interruptions are retained in the chat's `outputs/resoconto-test-02.txt`:
an unrefreshed index did not block existing imports; pending row decisions were
resolved through agent review; apply required the documented predecessor/replay
regeneration; guessed helper paths and truncated reference reads were corrected;
the incident-registration tool was unavailable while the two task-usage events
were acknowledged. A stale generic final-artifact caveat still referred to
pending UI decisions after final readiness. Technical paths in the Word report
remain awkward. Shell reads before Archive start and host/browser/rendering
activity remain outside Vera-owned emission measurement and were disclosed.

The local repair accepts unambiguous references to the same owned output file,
retains output-relative paths in manifests, and records exact run-bound MCP and
CLI errors. Unknown error content remains unmapped, making coverage incomplete;
it is not declared harmless metadata. No recipient or professional approval step
was added. The first regression run reproduced four failures; the repaired five
cases passed, followed by 248 Archive, lifecycle, reporting and Lucia tests.
Further boundary checks and release validation remain in progress. Acceptance
remains **1 of 13**. Test 3 has not started.

Final 0.1.458 source validation passed 260 Archive/lifecycle/reporting/Lucia tests
with 97.37% coverage of the error recorder, plus the full automatic-reporting CI
command: 230 tests and 83.15% coverage. Additional negative cases preserve
prepared/closed/unselected runs, record failures despite missing inputs, reject
foreign reporting state, and withhold an unrecorded detailed error when the
recorder fails or supplies no acknowledgement. Path cases cover nested `outputs`
directories, duplicate aliases, absolute paths and escapes. All 481 package,
privacy and update checks passed (two skips); Black, Isort, Mypy, Bandit and Node
syntax checks passed. All-host parity passed for Vera 0.1.458 and Lucia 0.1.151,
embedding Archive 0.1.61. The unchanged Open-item engine remains 0.1.65.

The final Vera ZIP hash is
`779b55855143d3b19d5767a48da75aa1be3e836e86f086c46d481c36ac32a0c0`.
The delta against the verified 0.1.457 baseline contains 132 changed files, one
new Archive error-recorder module and no removals. Executable changes are limited
to Archive's MCP server, CLI, ledger and new recorder, plus the same ledger copied
into Fusione's vendor directory. All 240 retained-file hash checks passed.
The accepted test-1 transcript and resoconto were reviewed for A62: they record
no failed Archive operation; their verification error occurred after report
closure and was independently diagnosed as restricted-shell DNS failure. Its
previous acceptance evidence remains unchanged. Fresh installed 0.1.458 test-2
acceptance and saved-report reopening are still required.

### 0.1.458 normal-chat result: public regeneration command failed

The supported local installation was verified at 0.1.458: all 2,184 enabled
cache files matched the generated ZIP. Fresh GPT-6.1-sol chat
`01a15c2a-52d1-7a30-90a6-60b9097d0072` stopped at the first workflow error.
Task `4f9d12f2-a50c-45b5-874d-6618398955e0` and Archive run
`run_fa98101b02e43d8f8aa0bcae` are failed; neither may be resumed or rewritten.
All 317 retained-file hash checks across the earlier attempts still passed.

The initial three-row reconciliation was correct: EUR 2,500 less EUR 1,500
received left EUR 1,000. Eight review decisions were recorded as agent review,
without human confirmation or professional approval. The agent inspected all
eight Word pages through the installed LibreOffice route. Public save/apply
completed, but the subsequent published `raw_input_runner.py` command failed:
`rendered review rows do not match persisted professional review authority`.
The command accepted `--expected-predecessor-checkpoint` yet reran initial
production instead of consuming the applied authority through the existing
regeneration transaction. This is **A64**. Earlier 0.1.457 used a wrapper calling
the regeneration function and therefore did not exercise this public CLI gap.
No Archive finalization occurred in 0.1.458; A61 still needs normal-chat proof.

The readable privacy report appeared automatically in the final response.
It honestly reports incomplete collection: 13 emissions, 18,486 characters,
21 of 24 population cells and 4 of 12 bank cells, with an unknown remainder.
The only unmapped emission is the failed native-execution response, including
stderr and its local technical-evidence pointer. It is not declared safe
metadata or silently omitted. Independent read-only server verification passed
for receipt `845fbc55-f666-51be-93c8-3015abcbac65`, revision 1, exact userID
`0ed4a818-1877-4652-8515-787c64de17a5`, exact run and report SHA-256
`05cfffc07ef903ea4855aba1dc4b986ee45c6c43dd49f59b6a4e4fd5ab0027bf`.
Proof is retained in `/private/tmp/studio-archive-458-failed-report-proof.json`.
This verifies the failed report; it does not accept the workflow.

The chat's `outputs/resoconto-test-02.txt` retains every interruption. An
unrefreshed search index did not prevent exact imported-source work. The normal
review/replay transition was required, without a new human approval. The native
technical incident remained queued locally because the dedicated incident tools
were not exposed. A task event linking that incident and one scoped retry
returned HTTPError; its exact HTTP status was not retained. Started/failed task
events were acknowledged and ComputerID was verified. No historical queue was
flushed. The server source requires an incident report to exist for that
installation before accepting its link; this is consistent with the queued
incident, but the exact rejected response has not been independently observed.

The coordinator could create the separate chat but Computer Use refused access
to the Codex app, so a separate window was not verified. The refusal was
reported and not bypassed. This is a host limitation, not a Vera calculation
failure. Two untranslated Italian-report labels and long technical provenance
paths were also recorded.

### 0.1.459 repair in progress: regeneration dispatch and completed handoff

**A63** was independently reproduced against the retained 0.1.457 output:
`final_artifacts.status=final_ready` coexisted with a required browser review,
pending-decision caveat and initial setup instructions. The actual successor
finalizer in `audit_assurance.py` wrote the terminal state while retaining
initial handoff metadata. An initial repair of the browser/MCP writers alone
did not fix this path; six expanded regressions exposed the remaining defect.

The source repair now routes the public predecessor-checkpoint CLI through the
existing regeneration transaction, retaining original settings and applied
decisions. It accepts the documented regeneration command without repeating
initial assumptions. Shared Python handoff rendering and the MCP writer reflect
completed review only at final readiness; pending review remains pending.
The completed handoff names delivery and outstanding evidence explicitly rather
than repeating review setup. Two missing display-label translations are added;
source fields and exact accounting values are unchanged.

The public CLI failure was reproduced in two cases before the fix and those
cases passed afterward. The terminal handoff failure was also reproduced and
its focused regression now passes. Full accounting, native/public review and
projection suites are in progress. No 0.1.459 installation or acceptance chat
has started. Acceptance remains **1 of 13**; test 3 has not started.

The source suites subsequently passed: 420 accounting cases with 81.63%
coverage, 129 public-review/native cases, and all 17 projection/regeneration
cases. Final review also corrected the CLI's completion label from
`ready_for_review` to `final_ready` when the retained assurance reports ready;
all four CLI integration variants passed again for that final response change.
The same public review/projection suite is now explicitly included in CI.
Black, Isort, Mypy, Bandit medium/high and Node syntax checks passed. All 317
historical file hashes remained unchanged. Canonical candidate versions are
Vera 0.1.459 and Open-item 0.1.66; package and installed acceptance checks remain
pending at this point.

Final 0.1.459 package/privacy/update checks passed: 513 tests, two skips, plus
three icon-consistency checks. All-host source/package parity passed. Final
Vera ZIP SHA-256 is
`a5fbe32ba8ee18cf1c7c8973c013afcfbdce4a997f91cf0b0d3768965789810f`.
The delta against verified 0.1.458 has 129 changed files, no additions and no
removals. Its six executable changes are confined to Open-item's MCP server,
assurance finalizer, public CLI, review server and two retained rendering/locale
sources. Installation and fresh normal-chat acceptance remain outstanding.
