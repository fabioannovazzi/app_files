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
| T01 | Test harness | The component fixture restored `sys.path` between tests while its reporting adapter remained cached. | Broad regression run failed importing `archive_report_receipt` in the tax-litigation case. | Fixture now supplies product sibling imports per test; exact failing case passes. No product import behavior changed for this failure. | A fixture import defect does not justify changing production code. |
| T02 | Previous behavior assertions | Two older tests required an exact recovery response without new issue fields and a global listing failure for an unreceipted file. | Broader regression verification failed after the intended inventory repair. | Assertions now verify the complete recovery response and the useful behavior: verified inputs remain visible, the unreceipted entry is unavailable and its bytes stay unchanged. Subsequent broader suite passes. | Tests must validate the requested behavior rather than preserving the defect as authority. |
| B01 | Release evidence | `build_product_release.py vera clara lucia` stopped at privacy contract generation: reviewed fingerprints still described the previous source. | No candidate package was produced at that step. | Completed the source-delta review below, corrected three disclosure manifests and refreshed 40 affected review fingerprints. All three product privacy registers now validate; contract generation passes. No installed acceptance follows from this result. | Release disclosures must describe the governed source; this build check is separate from ordinary client execution. |
| B02 | Release evidence | The next build stopped at the generated course-catalogue freshness check, first at Vera's `bilancio-oic/course.json`. Regeneration then invalidated the dependent Vera onboarding, Clara teaching/course-files and Lucia course-files fingerprints. | Packaging did not reach ZIP generation during those attempts. | Regenerated the existing authoring corpus; all 20 changed course JSON files changed only SHA-256 provenance fields. Reviewed that delta, refreshed the four dependent records and rebuilt successfully. | Generated course source references must match their declared source; this is a release check, not an ordinary client execution prerequisite. |
| H01 | Acceptance host | `cua.getApp("Codex")` returned `Computer Use is not allowed to use the app 'com.openai.codex' for safety reasons.` | Cannot open the requested separate Codex app window through Computer Use. No workflow test was launched. | The supported chat API can create a separate GPT-6.1 Sol chat but exposes no new-window operation. Asked whether that separate chat is acceptable or whether to wait for a user-opened window; response pending. | This is a host tool restriction, not a Vera execution or Python check. No alternative UI-control mechanism was used to bypass it. |

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

## Remaining audit targets

- Complete the changed-source privacy review, refresh only reviewed records,
  rebuild the product packages and run package/contract/receipt checks.
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
Shared-service fingerprints also cover the incident reader or product version.
The review is limited to these inspected source deltas. It is not evidence that
each workflow, packaged host, external service or normal chat has run successfully.
