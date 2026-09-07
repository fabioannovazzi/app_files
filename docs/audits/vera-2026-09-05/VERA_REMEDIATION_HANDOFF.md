# Vera audit and remediation handoff — 5 September 2026

## Start here: instructions for the coordinating task

Audit repository: `/Users/fabio/Documents/GitHub/app_files`.

Use this document to coordinate scoped implementation tasks for the findings below. First inspect the current checkout and applicable AGENTS.md instructions. Revalidate each finding before changing code: this audit examined a dirty, actively changing working tree, based on commit `d4486cdec400b33a0a9b1c75b3ba7fb3e4705b91`, with Vera source manifest 0.1.191. Another task was rewriting shared business planning and updating packages during the audit. Do not overwrite its work or recreate changes already completed.

The original assignment authorized an audit and this handoff, not fixes, deployments, publication, or creation of remediation tasks. Once the user asks you to execute this plan, create tasks using the task cards below. Each task receives this document, its card, current source baseline, dependencies, and the common completion contract. Follow repository limits on temporary branches/worktrees; do not assume concurrent tasks may each create a worktree when the repository's lifecycle rule prevents that. Parallel analysis is possible; serialize shared-file integration and package generation.

Maintain a small coordinator checklist recording task ID, owner, baseline, status, evidence, and acceptance result. Use `confirmed`, `fixed`, `superseded`, `not reproduced`, or `needs evidence` for findings. Do not close a finding merely because a new version exists. Re-run its triggering case. Complete P1 correctness/recovery work before broad architectural simplification. Tasks marked qualification must establish a defect or measured benefit before implementation.

**What I would change:** strengthen input meaning and missing-data handling; make crash recovery and runtime setup reliable; replace duplicated orchestration with small shared contracts; measure professional outcomes and actual host behavior. Preserve exact arithmetic, source lineage, explicit uncertainty, bounded execution and professional review. A newer model is not evidence that those controls should be removed.

## Evidence and limits

- Inventoried 933 files across Vera, all 27 declared components, and the shared vendor superset. That superset also contains legacy code not necessarily reachable from Vera. Inventory contains source hashes and Python function ranges.
- Mechanically checked 677 Python, retained `.source`, JavaScript and JSON files: all passed syntax/parse checks at that snapshot. Manual review covered routing, component skills, principal pipeline kernels, shared execution/data boundaries, archive transactions, hosted receipts, tests and packaging. It was risk-directed, not a claim that every line of roughly 491,000 inventoried lines received semantic review.
- Synthetic local probes confirmed the input, aggregation, sampling, PDF and XML findings below. No client files, paid model runs, external messages or production mutations were used.
- Hosted receipt/change-request tests completed successfully: 51 tests, exit code 0. This does not establish all hosted behavior or deployed state.
- The broad plugin suite did **not** finish green. With Node correctly on PATH, it stopped at 12 failures in Check Entries/upstream Journal Sampling. Most traces rejected the exact implementation filesystem contract; inspection found bytecode cache files outside that contract and no missing contract files. Some caches can be introduced by ordinary test/audit imports. Treat this as a reproducible test-environment/qualification problem, not 12 independent accounting defects. The initial run also had missing-Node failures and a transient business-planning syntax error during concurrent editing; neither establishes a stable product defect.
- Read-only privacy validation found the business-planning fingerprint stale. Codex ZIP check found differences in business-planning report/skill/privacy files. These are integration observations on work in progress, not evidence of a production mismatch or a reason to overwrite the ongoing rewrite.
- No actual Windows, Cowork, connected-browser, real Luna capsule, live deployment, Marketplace or professional end-to-end acceptance was performed. No benchmark establishes that the present model produces better professional outcomes than 5.6.
- Large generated evidence was moved outside the checkout to `/private/tmp/vera-audit-evidence-01a07083/`: `source-inventory.json`, `syntax-scan.json`, baseline status, test logs, `reproduce_findings.py`, `reproductions.json`, `sampling-probe.json`, and size accounting. Temporary storage may be cleaned by the OS. **This document is self-contained for remediation; the external evidence is supplementary.** Do not add the generated inventory, copied skill text or full logs to the code change.

Source locators below are repository-relative and use audit-time line numbers. Resolve by symbol when lines have moved. P1 means correctness, integrity or recovery should precede broader work; P2 means maintainability/qualification/product improvements. No P0 production incident was established.

## Findings and task cards

Each card is a ready-to-use task brief. It includes the trigger, evidence, intended change and acceptance. Scope changes require evidence, not an assumption that a rewrite is intrinsically better.

### T01 — Management Control input and metric correctness (P1, confirmed)

**Evidence:** `plugins/management-control-pack/scripts/management_control_core.py`, `_parse_decimal` around 446, `_xlsx_tables` around 192, `_cash_section` around 1062, `_sales_sections` around 1242–1309.

A blank revenue cell becomes Decimal zero. A synthetic pack with an original revenue total of 2400 reports 1400 and `ready_for_review` when the 1000 cell is blank and optional source controls are absent. XLSX input uses only `data_only=True`, so uncached formulas can have the same missing-value path. With zero sales revenue and real direct costs, concentration and margin ratios are rendered as zero. Reversing two same-date bank rows changes the reported latest balance from 50 to 100. Services are truncated to 50 rows without a full-detail export in that section.

**Implement:** distinguish missing, invalid, uncached formula and actual zero; reject nonfinite numbers; propagate section-level uncertainty. Return undefined ratios with an explicit reason when the denominator is zero. Require a reviewed sequence/time/opening-closing convention for competing same-date balances or report ambiguity. Preserve complete local service results and disclose presentation truncation. Review the dual formula/value inspection already present in report-builder before adding another parser.

**Acceptance:** public pack-builder tests for blank required amounts, uncached formulas, NaN/infinity, zero denominator with nonzero costs, both same-day row orders, and 51 services. Correct totals remain unchanged for complete valid inputs; unaffected sections remain usable when another section lacks evidence. Do not equate `ready_for_review` with economic health.

### T02 — Passive Invoice numeric ingestion (P1, confirmed)

**Evidence:** `plugins/passive-invoice-audit/scripts/audit_core.py`, `_decimal` around 227 and `load_ledger` around 397. Public loader probes: signed amount `1,234` becomes `1.23`; a blank signed amount becomes `0.00` through absent debit/credit fields; `NaN` survives as `NaN`.

**Implement:** use an explicitly reviewed number convention, preserve the original lexeme, reject ambiguous values and nonfinite decimals, and distinguish an absent signed amount from a genuine debit/credit representation. Do not guess a locale from one cell. Keep exact Decimal arithmetic after interpretation.

**Acceptance:** both decimal/thousands conventions, blank signed amount with and without valid debit/credit, parentheses/minus conventions, nonfinite values, and mixed-convention files. Add a full audit-path fixture proving invalid input cannot silently become a review-ready zero. Preserve source-row evidence.

### T03 — Journal Sampling allocation and method claims (P1, confirmed allocation defect)

**Evidence:** `plugins/journal-sampling/scripts/journal_sampling_core.py`, `_stratified_sample` around 3756. Groups of sizes 1, 1 and 20 with a requested sample of 6 return only 4. Unused per-group allocations are not redistributed. The private selector was exercised; reproduce through the public archived-run interface before closing.

**Implement:** define an explicit allocation policy, redistribute available capacity, and report requested/eligible/selected counts. Separately review systematic start, fixed random seed and monetary-unit duplicate selections. Existing references describe deterministic methods: do not invent a claim that they already provide statistical inference. Make selection purpose and limitations explicit; retain reproducibility.

**Acceptance:** unbalanced strata, more strata than sample slots, population below request, zero/negative values, repeated monetary-unit hits and reproducible seeds. The public workflow meets the reviewed sample size whenever the population permits it, or gives an explicit shortfall. Any inferential claim needs an independently justified method and representative evaluation.

### T04 — Legal source acquisition and completeness (P1, confirmed)

**Evidence:** `plugins/deep-research-validator/scripts/inspect_sources.py`, `_source_file_record` around 149 and `_fetch_url_record` around 190. Local files are decoded as UTF-8 with ignored errors. A compressed PDF was marked `available` and `complete_local_text`, but the capture contained `%PDF-1.7` bytes and omitted its visible statutory sentence. URL fetching similarly decodes without a PDF adapter. `_looks_blocked` treats words such as `login` as barriers; ordinary readable guidance about portal login triggered it.

**Implement:** content-type-aware PDF/HTML/text extraction; distinguish bytes acquired, text extracted, pages covered, truncation and unreadable sources. Keep byte and extracted-text hashes distinct. Treat barrier keywords as hints requiring context, not authoritative semantic judgments. Check URL deduplication for case-sensitive path handling. Preserve public-address/redirect restrictions.

**Acceptance:** compressed and scanned PDFs, accessible HTML mentioning login/subscriptions, actual interstitials, partial responses, large truncated sources and extraction failure. Validation cannot treat undecoded bytes as complete source text. Legal conclusions still require current primary-source verification; this task does not certify substantive law.

### T05 — Consistent FatturaPA body identity (P1, confirmed)

**Evidence:** `plugins/client-file-preparation/scripts/parse_fatturapa_xml.py`, `parse_fatturapa_file` around 338 and `parse_fatturapa_audit_file` around 435. A two-body XML with A=122 and B=244 produces a summary named A with total 122 but both bodies' VAT and line counts. The audit parser correctly returns two bodies. `plugins/check-entries/scripts/invoice_support.py` explicitly rejects multiple bodies, which is an honest limitation.

**Implement:** a shared per-body identity/parse contract using source hash and body index; aggregate only with explicit aggregate semantics. Update folder intake and `fatture-xml-check`. Keep Check Entries' explicit unsupported boundary unless its matching contract is deliberately extended.

**Acceptance:** one/multiple bodies, different invoice dates/numbers, payments, withholding, VAT lines and namespaces. Each amount links to the same body as its metadata. Consumers either support the body contract or stop clearly; no mixed-body records.

### T06 — Archive interruption and concurrent mutation recovery (P1, static execution evidence)

**Evidence:** `plugins/archive-organization/scripts/archive_organization.py`, `_copy_exclusive_then_unlink` around 1418, `apply_approved_plan` around 1922, `rollback_applied_plan` around 2060. Apply uses a run-local exclusive lock; it copies/unlinks before writing the operation's applied state. A hard interruption can leave physical changes with `applying` journal state and a stale lock. Rollback has no equivalent lock and requires the journal already be `applied`; interrupted rollback is not naturally resumable.

**Implement:** explicit recoverable operation states, idempotent reconciliation against source/target hashes, durable journal boundaries, and a lock covering conflicting client-root mutations including rollback. Detect abandoned locks safely. Preserve approved-plan binding, no-overwrite creation, linked-path rejection and source identity checks.

**Acceptance:** synthetic fault injection before/after each copy, flush, unlink and journal write; restart after interruption; interrupted rollback; competing runs/rollback; changed files. Recovery must neither lose nor overwrite documents and must disclose unresolved states. No real client archive is needed for these tests.

### T07 — Managed Python runtime installation (P1, static race; P2 reproducibility)

**Evidence:** `plugins/vera/scripts/_managed_python_runtime.py`, `ensure_runtime` around 468–554. Readiness check, deletion of the existing target, venv creation, installation and ready receipt have no cross-process lock and operate directly on the shared target. Two launches can delete or build the same environment. Requirement text is fingerprinted, but allowed version ranges can resolve differently; readiness does not record the full installed dependency set.

**Implement:** per-target process lock, private staging environment, validation before atomic promotion, and preservation of a healthy environment. Record resolved dependency versions and interpreter/platform identity; decide where platform-specific locked resolutions provide value. Keep installs confined to published declarations and optional OCR separately authorized. Coordinate Vera/Clara shared runtime ownership.

**Acceptance:** simultaneous launches, installer crash, invalid dependency import, failed upgrade, stale lock and existing healthy runtime. No process runs from a half-built/deleted environment. Receipts distinguish two different resolved installations from the same declaration. Exercise supported operating systems; report untested hosts honestly.

### T08 — Actual supported Luna execution envelope (P2, confirmed hard constraints)

**Evidence:** `plugins/journal-bank-reconciliation/scripts/semantic_review.py` pins Darwin build `25F84`, Codex `0.148.0-alpha.21` and binary hashes; qualification around 2261/2326 rejects changed hosts. Passive Invoice `scripts/luna_worker.py` and dependency checks hardcode the Luna path/model and reuse this capsule.

**Implement:** versioned host-capability qualification and configurable, reviewed model/effort selection. Preserve native isolation, source read boundaries, canaries, output validation and the distinction between local receipts and provider proof. Do not remove hashes or broaden filesystem/network access merely to make an upgrade run.

**Acceptance:** a supported-host matrix with actual execution on each claimed platform, boundary-negative tests, clear unsupported states and one real sanitized run producing its normal answer, report and local/model boundary evidence. Compare model changes on representative cases before selecting a replacement for 5.6. No benchmark means no claimed superiority.

### T09 — Test environment, gates and exact implementation contracts (P1 prerequisite)

**Evidence:** corrected plugin-suite run failed against exact 24/26-file trees; inspection found extra `__pycache__` files and no missing contracted files. `.coveragerc`/Makefile target `src`; most Vera plugin code lies elsewhere. `pyproject.toml` includes `ignore_errors=true`. Router tests largely assert text/fixture presence. Packaged startup CI is useful but not full behavioral coverage.

**Implement:** reproducible tests from pristine implementation trees, bytecode policy established before imports, and separate intentional tampering fixtures. Diagnose the two MCP subprocess failures with captured stderr. Preserve rejection of actual unowned executable/configuration files. Add targeted plugin type/security/test gates and meaningful coverage for changed modules. Do not weaken production guards to fix test imports.

**Acceptance:** formerly failing Check Entries tests pass in a documented clean environment, deliberate tampering still fails, full applicable plugin tests complete, and results identify the exact baseline. CI catches a deliberately introduced plugin regression. If a production guard itself needs changing, follow AGENTS.md's explicit stop/report rule for production changes made to resolve test import failures.

### T10 — Workflow registry and host-aware orchestration (P2)

**Evidence:** `plugins/vera/components.json`, root router skill, workflow catalog and component/wrapper skills duplicate capability and ceremony instructions. Archive descriptions conflict: Desktop-only in router/catalog versus local-folder Codex/Cowork in the component skill. Browser automation assumes a specific `chrome:control-chrome`/`tab.playwright` surface; this audit host exposes unified CUA. Prompt preparation carries host/mode-specific coaching that may not match the current harness.

**Implement:** one small capability registry for generated factual metadata, supported hosts, entry points and required artifacts. Keep semantic routing model-led. Update browser capability discovery through tested adapters; preserve supported-origin/action and authorization constraints. Remove repetitive procedural coaching only after comparing outcomes; retain domain method, evidence and unresolved-issue requirements.

**Acceptance:** registry consistency checks plus actual routing cases spanning overlapping requests, unsupported hosts, available alternatives and follow-up questions. Measure unnecessary clarification/steps and routing errors. Each browser adapter is accepted with real host execution before being advertised. Do not implement or modernize the legacy UI.

### T11 — Run lifecycle, model-data reports and receipt retries (P2)

**Evidence:** router requires run-level model-data reports; `plugins/studio-archive/scripts/client_ledger.py`, `finalize_run` around 1917 and `validate_run_artifacts` around 2049, enforce generic exact output closure, without mandatory workflow-specific model-data artifact roles. Report generation and hosted stamping live separately in `plugins/vera/scripts/model_data_report.py` and shared helpers. Report attestations correctly distinguish their evidence basis.

**Implement:** workflow profiles with required artifact roles and one finalization integration point. Investigate the interaction between asynchronous/retried receipt generation and immutable finalized output trees before selecting a design; that conflict is a hypothesis, not a reproduced defect. Define append-only receipt metadata or deliberate successor finalization if necessary.

**Acceptance:** success, no-model run, unknown/attested transmission, offline stamp, later retry, duplicate retry and resume after finalization. Required reports cannot be omitted silently, and successful retries do not invalidate sealed outputs. UUID/hash server receipts must not be described as proof of exact provider transmission. Review actual public privacy pages against each final data path.

### T12 — Intake classification and structured field authority (P2)

**Evidence:** `plugins/client-file-preparation/scripts/scan_folder.py`, `classify_file` around 161; `parse_fiscal_forms.py`, `_detect_kind` around 484 and dispatch around 1134. Filename/category/early-text keywords select the only fiscal extraction adapter. Unknown types can yield no fields, and read failures can be skipped. This is semantic routing through a brittle lexical gate.

**Implement:** distinguish candidate hints from reviewed document-kind decisions; use model-led interpretation for ambiguous documents with explicit abstention, while retaining stable-format field extraction. Persist skipped/unreadable/unsupported counts and source identity. Avoid replacing proven mechanical form rules with unconstrained generation.

**Acceptance:** misleading filenames, cover letters naming another form, mixed bundles, supported languages/jurisdictions, unknown forms and unreadable files. Every source gets an explicit disposition; no silent omission appears as a complete intake. Connect results to new-client, avviso-intake, dati-fiscali-strutturati and email-cliente without turning draft correspondence into legal advice or sending it automatically.

### T13 — Shared assurance and pipeline decomposition (P2, qualification before refactor)

**Evidence:** large kernels include XBRL (~8,400 lines), Journal Sampling (~7,200), Open Items retained assurance (~6,900), bank reconciliation (~6,500), New Client (~5,600) and archive core (~5,500). Implementation bootstraps, receipt/review transport and contract validation repeat across components. Open Items retains executable Python under `.source`; variance vendors a broad legacy module set. Size alone is not a defect.

**Implement:** first map reachable code and duplicated responsibilities. Extract only stable shared boundaries with demonstrated maintenance benefit: physical-tree validation, numeric/source primitives, review transactions and artifact contracts. Keep workflow-specific professional judgment local. Prune unreachable vendored dependencies through the package builder, not hand edits of generated copies. Do not refactor legacy UI.

**Acceptance:** a short responsibility/dependency map, before/after duplication numbers, package-size changes, and differential/adversarial tests showing preserved behavior. Threat-model reasons for tamper controls remain explicit. Smaller code is not acceptance if safeguards or useful domain reasoning disappear.

### T14 — Shared Business Planning integration and economic interpretation (P2, active work)

**Evidence:** the current shared `planning_workflow.py`/`planning_report.py` rewrite already adds margin, DSCR, break-even/runway and typed narrative claims. An older complaint about absent EBITDA margin is therefore not a current confirmed defect. `_financial` around 320–382 returns no financial result when any input anywhere is missing. This is conservative but suppresses otherwise calculable sections/scenarios. Package/privacy checks observed unfinished integration.

**Implement:** coordinate with the existing owner first. Qualify partial-result behavior, materiality, cross-scenario comparisons and economic interpretation against representative plans. Consider dependency-aware null propagation instead of all-or-nothing suppression if it improves usable correctness. Reconcile canonical source, Vera/Clara wrappers, privacy fingerprints and generated artifacts after the rewrite stabilizes.

**Acceptance:** startup and established-company plans, 1.5% EBITDA margin, negative cash, missing opening balance, one missing scenario input, zero denominator, conflicting assumptions and unsupported benchmarks. Readiness means evidence/review completeness, not business viability. Financial health statements require margins, trends, benchmarks and downside evidence with visible limitations. Do not duplicate the existing rewrite.

### T15 — Accounting pipeline outcome evaluation (P2, qualification)

**Scope:** Open Item Reconciliation, Check Entries, Journal Bank Reconciliation, Passive Invoice Audit and Journal Sampling. Use their existing contract/tamper tests and fixtures as a starting point.

**Implement:** add end-to-end, source-to-normalization-to-review-to-final-artifact acceptance cases. Include partial payments, reversals, duplicate identifiers, one-to-many relationships, cutoff timing, currency, missing support and changed source evidence. Measure false matches, missed matches, abstentions and reviewer corrections. Keep exact arithmetic and replay independent of model judgments.

**Acceptance:** expected results are independently reviewed and source-backed; actual outputs and normal final reports are retained outside code where bulky. A fixture or receipt alone is not runtime proof. T02/T03/T05/T08/T09 feed this task. No new pipeline-specific defect is asserted solely from lack of an observed live run.

### T16 — Financial reporting outcome evaluation (P2, qualification)

**Scope:** Financial Analysis, Report Builder, Sales Plan, Variance Analysis, Management Control and Business Planning. Inspect current formula, mapping, period and report contracts before editing.

**Implement:** evaluate numeric locale, formula cache, sign convention, noncontiguous periods, fiscal-year boundaries, missing data, denominator effects, totals, reconciliations and scenario lineage. Verify that presentation truncation leaves complete local detail and narrative claims reconcile with calculations. Use model reasoning for interpretation; exact calculations and conservation checks stay deterministic.

**Acceptance:** independent expected totals and claim-to-source checks; explicit unavailable sections; readable actual HTML/PDF/XLSX outputs where the workflow produces them. Preserve baseline arithmetic and uncertainty. T01/T02/T14 inform this work; do not assert that every listed pipeline shares the reproduced management defect.

### T17 — Professional/legal pipeline outcome evaluation (P2, qualification)

**Scope:** Quesito Legale Fiscale, Prompt Optimizer, Deep Research Validator, INPS, SARI, Bandi, Concordato and professional communications.

**Implement:** current primary-source cases and deliberately incomplete/ambiguous cases, measuring jurisdiction/date relevance, claim support, source completeness, abstention and usefulness. Review long validators for mechanical-contract checks versus unsupported semantic vetoes. Keep dedicated operational workflows separate from general legal Q&A. Do not use a fresh model's agreement as the oracle.

**Acceptance:** visible claim/source/page linkage, unresolved conflicts, stale-source handling and appropriately bounded outputs. Have professional reviewers establish expected substantive outcomes. T04/T10 are prerequisites for relevant source/routing cases. No legal correctness certification was performed in this audit.

### T18 — Extraction, archive and AML outcome evaluation (P2, qualification)

**Scope:** Client File Preparation, New Client and its wrappers, Archive Organization, Studio Archive, AML Review, Centrale Rischi and Bilancio XBRL.

**Implement:** preserve existing Centrale Rischi gold/quality and XBRL benchmark assets; add real-format synthetic or authorized sanitized boundary cases. Cover missing/duplicate evidence, re-imported changed sources, engagement isolation, XML body identity, unreadable PDF, taxonomy/version mismatch and ambiguous document kinds. AML is new in this dirty tree: establish its acceptance independently rather than inheriting confidence from packaging.

**Acceptance:** every imported source has an explicit disposition and stable identity; resumable engagements preserve review history; unsupported formats stay explicit; no financial/legal health conclusion follows solely from structural readiness. T05/T06/T11/T12/T09 supply fixes and infrastructure.

### T19 — Public product and browser workflow coherence (P2, qualification)

**Scope:** Presenza Digitale Studio, Comunicazione Professionale, Browser Automation, public Vera/function pages and report/review entry points.

**Implement:** check each explanation against actual accepted inputs, outputs, host support, responsibilities and model-data path. Review browser teaching/discovery/build/validation lifecycle and changed-page recovery. Ensure existing shared review controls remain usable and authorization for publication or external writes is respected. This is product coherence work, not legacy UI modernization.

**Acceptance:** function-specific data sections and honest placeholders where unreviewed; no unverified privacy promises, unsupported browser claims or top-level slogans. Actual browser cases cover stale selectors, unexpected login, redirected origin and review before consequential action. T10/T11/T17 feed this task.

### T20 — Final packaging and integration qualification (P1 release gate; last)

**Evidence:** stale business-planning privacy fingerprint and differing ZIP entries at audit time. Packaging creates repeated component metadata/source copies by design; canonical-source duplication and generated distribution copies need different treatment.

**Implement:** after source integration, run declared tests and read-only package/privacy checks, then use the repository's release skill for any necessary local rebuild. One task owns regenerated bundles and shared manifests. Never hand-merge binary ZIPs or use package rebuilding to bless an unreviewed privacy path.

**Acceptance:** source/wrapper/component consistency, no stale fingerprints, clean generated-package checks and packaged MCP startup/tool listing for supported targets. Record exactly which source revision and dirty changes were included. Deployment, server verification, Marketplace submission and publication remain separate actions requiring explicit user requests.

## Coverage map: all declared components and Vera-only routes

“Qualification” means this review did not establish a component-specific runtime defect; it is not a claim that the component passed full professional acceptance. All components received inventory/contract review; principal code and tests were inspected by risk, with deeper work on the findings above.

| Component / route | Audit disposition and follow-through |
| --- | --- |
| open-item-reconciliation | Retained-source assurance/review architecture; T13, T15 qualification |
| archive-organization | Apply/rollback state and locking gap; T06; T18 |
| client-file-preparation | XML body defect and semantic kind gate; T05, T12, T18 |
| new-client | Large review/validation orchestration; T12, T13, T18 |
| aml-review | New, actively integrated component; T18, T20 qualification |
| journal-sampling | Reproduced stratified underfill; T03, T09, T15 |
| check-entries | Exact-tree test failures; explicit multi-body limitation; T05, T09, T15 |
| journal-bank-reconciliation | Native capsule hard pins and large core; T08, T13, T15 |
| passive-invoice-audit | Reproduced numeric ingestion defects; T02, T08, T15 |
| sales-plan | Reviewed contract/arithmetic workflow; T13, T16 qualification |
| business-planning | Rewrite already addresses older gaps; T14, T16, T20 |
| variance-analysis | Broad vendor footprint and duplicated contracts; T13, T16 |
| management-control-pack | Reproduced missing/zero/ordering errors; T01, T16 |
| centrale-rischi-review | Preserve normalization/gold evidence; T18 qualification |
| financial-analysis | Bounded FDD/mapping contracts; T13, T16 qualification |
| report-builder | Dual-view XLSX reading useful precedent; T01, T16 |
| concordato-plan-review | Long validator/domain review boundary; T13, T17 |
| comunicazione-professionale | Source relevance and publishing boundary; T17, T19 |
| presenza-digitale-studio | Actual content/data/host contract; T19 qualification |
| prompt-optimizer | Routing and procedural overhead; T10, T17 |
| deep-research-validator | Reproduced source capture/barrier defects; T04, T17 |
| previdenza-inps | Domain/source/output contract; T17 qualification |
| registro-imprese-sari | Domain/source/output contract; T17 qualification |
| bandi-agevolazioni | Source-first semantic selection and long validator; T13, T17 |
| bilancio-xbrl-it | Large taxonomy/kernel; preserve benchmark; T13, T18 |
| browser-automation | Tool/host adapter mismatch risk; T10, T19 |
| studio-archive | Good engagement/identity discipline; lifecycle integration T11, T18 |
| quesito-legale-fiscale | Prompt → answer → validation orchestration; T04, T10, T17 |
| avviso-intake | First-intake scope, readable notices and missing evidence; T12, T18 |
| dati-fiscali-strutturati | Extraction adapter/classification authority; T12, T18 |
| email-cliente | Operational draft boundary, no automatic sending; T12, T19 |
| fatture-xml-check | Shared intake XML summary inconsistency; T05, T18 |
| Vera router/privacy governance | Host/capability and actual data-path consistency; T10, T11, T19 |
| managed-python-runtime service | Concurrent setup/dependency receipts; T07 |
| plugin-update-check service | Preserve bounded metadata/version behavior; T11, T20 qualification |
| plugin-feedback service | Preserve consent and minimized payload; T11, T19 qualification |
| run-receipt-stamping service | Hosted tests passed; lifecycle/retry qualification T11, T20 |
| Shared assurance/FDD/OCR/vendor/build/hosted surfaces | T07, T09, T11, T13, T20; do not count broad legacy vendor inventory as all reachable Vera logic |

## Execution order and ownership

1. **Establish baseline:** T09 investigates clean test execution; coordinator records current dirty owners and revalidates T01–T08. T14 coordinates with existing business-planning work immediately.
2. **Correctness:** T01, T02, T03, T04, T05 have largely separate primary files. T06 and T07 can be developed independently but their integration needs common lifecycle awareness. Shared money/XML changes need explicit ownership to avoid conflicting abstractions.
3. **Shared contracts:** T08, T10, T11, T12. T13 starts with a proposal and differential evidence; delay broad extraction until correctness changes settle.
4. **Outcome qualification:** T15–T19 use the corrected baseline. They may discover new narrowly scoped work; record it with a reproduction and acceptance before creating additional tasks.
5. **Integrate once:** T20 owns package/privacy regeneration and final source-to-package acceptance after other tasks complete. A release is not authorized by this document.

The coordinator can combine small related cards when one owner can maintain clear acceptance. Do not launch twenty simultaneous edits. Avoid parallel changes to `components.json`, shared assurance, the managed runtime, root routing, privacy manifests or generated packages.

## Common completion contract for every implementation task

- State what was observed on the current baseline and whether the finding reproduced. Distinguish confirmed defect, justified design improvement and remaining unknown.
- Make the smallest coherent fix. Preserve unrelated dirty work and all applicable authorization, evidence, privacy and source-identity boundaries.
- Test the triggering case and meaningful neighboring failure modes through the public workflow where possible. A test that mirrors the implementation or asserts prompt phrases is not outcome validation.
- Record source changes, concise reproduction/validation commands, PASS/FAIL, and remaining host/professional gaps. Keep large logs, inventories, captures and generated copies out of canonical source changes unless required as small fixtures or official packages.
- For actual model runs, retain the normal answer, exact generated report, input/source boundary, selected model/runtime identity and independently assessed result. Mechanical receipts and manual examples alone do not establish actual provider behavior.
- Update this coordinator's checklist with concise evidence. Do not send user/client data externally, deploy, merge or publish without the authorization required for that action.
- Follow repository checks and branch/worktree cleanup rules. Report final local branch, remote branch, worktree and stash counts; preserve other tasks' work.

## What should remain intact

Exact financial arithmetic and reconciliation; source hashes and body/row/page lineage; client and engagement isolation; explicit unsupported states; review decisions bound to the evidence they concern; no-overwrite archive operations; model/local boundary disclosures; optional OCR authorization; tested tamper rejection; full professional review responsibilities. Simplification should remove repetition and accidental brittleness, not these controls.

## Change-size check and final audit state

The audit initially generated 20 evidence files containing 67,284 lines (1,982,989 bytes). They were moved to the external evidence directory above. Before this closing note, the retained handoff was 261 lines; the large inventory and copied skill extracts are not part of the proposed repository change.

At the relocation snapshot, other tracked additions plus untracked text contained 2,724 application/tooling lines, 1,307 test lines, 830 fixture lines, 865 documentation/declaration lines, 274 metadata/other lines and 8,389 generated package-copy lines. These are additions, not net growth; tracked deletions totaled 1,066 lines. Classification is path/extension-based and includes other tasks' ongoing work. Generated copies are the largest remaining addition; preserve required distributable contents and use T13/T20 to assess canonical duplication and package construction rather than deleting copies arbitrarily.

A final hash comparison found six inventoried files changed during the audit, all belonging to business-planning source, contract, skills or privacy review. Revalidate T14 and package checks against the owner's completed baseline. The additional broad test attempt excluding Check Entries was interrupted at about one-quarter completion; three reported failures concerned Clara routing/package integration, outside a confirmed Vera defect. Its log is supplementary evidence, not a green full-suite result.

Final Git inspection: one local branch, one remote branch (`origin/main`; `origin/HEAD` is a symbolic alias), one registered worktree, zero stashes. No application source, tests or distribution packages were edited by this audit; only this handoff remains in its audit directory.
