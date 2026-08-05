# Bilancio intelligente acceptance matrix

Evidence snapshot: 2026-08-05. This matrix separates code that is locally
proved from external, production-infrastructure, and owner-decision gates. A
passing row does not imply that a broader row is complete.

Status meanings:

- `PROVED_LOCAL`: implemented and exercised by current local tests or a
  checksum-recorded controlled run.
- `PARTIAL`: a useful implementation exists, but the complete specification
  boundary is not yet proved.
- `EXTERNAL_OPEN`: completion requires a user-controlled external system or
  third-party decision.
- `DEPLOYMENT_OPEN`: reference code exists, but production infrastructure or an
  operational control is absent.
- `OWNER_OPEN`: the specification explicitly reserves the decision for the
  product owner.

## Fixed product and scope decisions

| Requirement | Status | Inspected evidence | Remaining boundary |
| --- | --- | --- | --- |
| The existing bilancio process is made intelligent throughout; XBRL is an output adapter | `PROVED_LOCAL` | `references/product-thesis.md`, task-specific contracts in `scripts/intelligence_contract.py`, state-aware orchestration tests | Representative production-model usefulness remains an evaluation gate, not a product-thesis gate |
| Individual Italian OIC accounts only; supported legal forms S.r.l., S.p.A., S.a.p.a. | `PROVED_LOCAL` | Scope checks in `scripts/xbrl_case.py`; listed and IFRS rejection tests; golden case 21 | Cooperatives remain an owner decision |
| No signing, filing, or undocumented TEBENI automation | `PROVED_LOCAL` | Skill safety boundary, external-validation adapter, privacy manifest | Manual TEBENI execution remains optional and external |
| PCI 2018-11-04 locked by effective identifier and checksum | `PROVED_LOCAL` | `taxonomy/PCI_2018-11-04.registry.json`, catalogue builder tests, `references/taxonomy-spike.md` | Redistribution/licensing permission is open |

## Functional acceptance criteria (specification 24.1)

| Criterion | Status | Inspected evidence | Remaining boundary |
| --- | --- | --- | --- |
| Create an eligible S.r.l./S.p.A./S.a.p.a. case | `PROVED_LOCAL` | `create_case`, scope reasons, service create/idempotency tests | None for the declared MVP forms |
| Parse generic CSV/XLSX trial balance with source anchors | `PROVED_LOCAL` | `ingest_trial_balance`; CSV, workbook safety, formula-cache, traversal, and source-anchor tests | Native accounting-package adapters are later scope |
| Calibrate and confirm debit/credit convention | `PROVED_LOCAL` | `_calibrate`, `confirm_parser`; exact, unknown, and imbalanced tests; golden case 23 | None for supported layouts |
| Calculate eligible forms through effective-dated rules and record user choice | `PROVED_LOCAL` | versioned form pack, `determine_forms`, `select_form`; two-year, first-year, exclusion tests; silent pack replacement rejection; explicit open-case migration/change report/full-revalidation tracking | Regulatory rule ownership/sign-off remains operational |
| Require every account to be mapped, split, or excluded | `PROVED_LOCAL` | reviewed mapping decisions, exact split checks, validation coverage blocker, tenant/client mapping memory | Semantic mapping quality still needs representative model evaluation |
| Reconcile balance sheet and income statement to canonical accounting data | `PARTIAL` | exact Decimal aggregation, balance/result tie-outs, adjustment and rounding tests; complete selected-form leaf inventory and official calculation rollups | Semantic mapping from arbitrary client accounts to every PCI leaf still needs representative coverage evidence |
| Generate and reconcile ordinary cash flow with missing evidence blocked | `PROVED_LOCAL` | cash-flow schedule contract, missing-evidence tests, statutory-root reconciliation test, and every ordinary golden workflow | Complete PCI cash-flow table population is part of the taxonomy coverage gap |
| Provide fixed-asset, receivable, payable, equity, provision, TFR, and tax schedules when triggered | `PROVED_LOCAL` | `scripts/schedule_engine.py`; equation, maturity, secured-payable, sign, movement, statement, source-anchor, and template-ingestion tests | None for the normalized professional schedule contracts |
| Bind schedule evidence to form-specific PCI note tables | `PARTIAL` | `scripts/schedule_taxonomy_adapter.py`, checksum-locked adapter pack, exact per-cell dispositions, deterministic value derivation, primary-fact reconciliation, official inventory audit, and eight representative schedule golden workflows | Complete real-case professional bindings for every applicable table cell and dimension have not been exercised |
| Request missing non-accounting information dynamically | `PROVED_LOCAL` | effective-dated disclosure pack, blocker-first questionnaire, annual negative confirmations, prioritization contract | Representative question relevance/economy benchmark is open |
| Generate notes only from accepted structured facts | `PROVED_LOCAL` | fourteen note sections, claim-reference closure, substantive terminal-answer evidence gates, accepted narrative rendering, stale-text redline tests; prior contexts preserve explicit and typed dimensions, tuple ancestry, validated units and context-fact groups | Automatic reconstruction of complete prior tables and every real-case PCI note-table binding are partial |
| Generate deterministic XBRL | `PROVED_LOCAL` | checksum-bound renderer, explicit sign multipliers, context/unit/decimals, text, dimension, tuple and nil tests; all ordinary, abbreviated and micro primary-presentation facts rendered; controlled schedule facts, including repeated tuple rows, are derived, reconciled and rendered | Complete real-case schedule and note-table filing content remains partial |
| Pass local XBRL validation before approval | `PROVED_LOCAL` | `prepare_xbrl_review`, offline Arelle adapter, calculation inconsistency and severe-log failure tests, current-content hash, processor-report hashes, approval gate tests | None for locally configured taxonomy inputs |
| Approve an immutable reviewer snapshot | `PROVED_LOCAL` | revision check, declaration, issue review, snapshot hash and invalidation tests | Dual-review policy remains an owner decision |
| Export XBRL, preview, mapping, issue, validation, and workpaper artifacts | `PROVED_LOCAL` | approved-snapshot export; standalone snapshot-bound reports; peer checksums embedded in workpaper; final checksum manifest tests | Production object storage is not implemented |

## Safety and quality acceptance criteria (specification 24.2)

| Criterion | Status | Inspected evidence | Remaining boundary |
| --- | --- | --- | --- |
| No model-suggested, assumed, or missing fact is exportable | `PROVED_LOCAL` | exportable-status gates in mappings, taxonomy facts, narratives and renderer; intelligence contract tests | None in the current reference implementation |
| Every exported numeric and factual narrative item has provenance | `PROVED_LOCAL` | source/derivation checks, sentence-level claim closure, workpaper source references | A complete real-case professional audit has not been run |
| Structural invalidity and imbalance cannot be overridden | `PROVED_LOCAL` | blocker policy, issue fingerprint reviews, adjustment and statement tests | None in current policy |
| Unsupported entities are blocked before generation | `PROVED_LOCAL` | scope state and reason codes; listed/IFRS tests and golden case 21 | Special-sector coverage remains explicitly out of scope |
| Editing approved data invalidates approval and local XBRL review | `PROVED_LOCAL` | `_mutate`, archived snapshots, review invalidation tests | None in file-backed engine |
| Tenant and client data do not cross mapping, history, service, or path boundaries | `PROVED_LOCAL` | tenant authorization/memory/history tests; configured input-root and symlink tests | Production database/object-store row policies are not implemented |
| Vera privacy surface is reviewed and current for this workstream | `PROVED_LOCAL` | `plugins/vera/privacy/workstreams/bilancio-xbrl-it.json` with refreshed source fingerprint | Repository-wide validator still reports unrelated stale workstreams |

## Testing and taxonomy evidence

| Requirement | Status | Inspected evidence | Remaining boundary |
| --- | --- | --- | --- |
| Official package produces a form-aware concept catalogue | `PROVED_LOCAL` | schema-2 catalogue built offline with 2,399 concepts: 2,292 items, 29 tuples, 78 other schema/reference concepts and 6,708 references; catalogue-builder item/tuple tests | Catalogue/ZIP may not be bundled until licensing review closes |
| Synthetic XBRL validates with a conformant processor | `PROVED_LOCAL` | offline `arelle-release==2.42.1`; ordinary, abbreviated, micro spike plus 20 golden instances | No claim is made for another processor version |
| All 24 minimum golden scenarios exist | `PROVED_LOCAL` | `evals/golden_cases.json`, `scripts/run_golden_cases.py`, golden registry/runner tests; all eight non-cash schedule families use a complete adapter disposition and emit representative official facts where applicable | The current instances prove balanced totals and representative scenario concepts, not complete statutory filing content |
| Controlled official-taxonomy run | `PROVED_LOCAL` | 24/24 pass; 20/20 public-lifecycle XBRL workflows pass; four boundary passes; eight non-cash schedule cases complete the controlled taxonomy adapter; checksums in `references/taxonomy-spike.md` | External TEBENI/rendering comparison is open |
| Complete selected-form primary presentation coverage | `PROVED_LOCAL` | `scripts/statutory_presentation.py`, versioned presentation pack, `docs/bilancio_statutory_presentation_audit.json`; explicit-zero controlled closure for 87 abbreviated, 84 micro, and 224 ordinary unique leaves; 3/3 full primary instances pass pinned offline Arelle | Structural zero fixtures do not prove real-entity classification judgments or complete note/schedule tables |
| Official selected-form schedule table boundaries | `PROVED_LOCAL` | `scripts/audit_schedule_taxonomy.py`, versioned schedule-taxonomy pack, and `docs/bilancio_schedule_taxonomy_audit.json`; 623 ordinary and 453 abbreviated reportable item concepts across eight families; exact tuple paths support repeated rows; micro is explicitly text-only | The structural inventory does not supply the professional semantic binding for each real-company schedule cell |
| Representative model evaluation | `PARTIAL` | strict offline scoring harness and contract/stability tests | Recorded outputs from selected production model versions and Italian SME review are absent |
| XBRL 2.1 conformance and negative corpus | `PROVED_LOCAL` | `references/conformance-evidence.md`; official 2025-07-16 suite passed 606/606 with pinned Arelle in offline `xbrl21` calculation mode, plus renderer-specific duplicate/context/unit/nil/dimension/decimals/preflight tests | This proves the pinned processor boundary, not complete PCI statutory filing content or another processor version |

## External compatibility (specification 24.3)

| Criterion | Status | Inspected evidence | Remaining boundary |
| --- | --- | --- | --- |
| Golden outputs pass local validation | `PROVED_LOCAL` | 20 controlled instance reports, package SHA-256 `c24b86375529469ca0be9a06b231fbb05da18df99fa36a1db2e587ab51e2f0f1` | Complete statutory content remains partial |
| Golden outputs pass current official TEBENI | `EXTERNAL_OPEN` | Explicitly recorded as `NOT_RUN_USER_CONTROLLED` | Professional must manually upload controlled files and return reports |
| Official rendering matches approved amounts and notes | `EXTERNAL_OPEN` | Local renderer checks exact approved totals, marker facts and narratives | Official TEBENI rendering comparison fixtures are absent |
| Local/external differences are understood and regression-tested | `EXTERNAL_OPEN` | Returned-report comparison adapter exists | Requires real returned reports |

## Architecture and non-functional requirements

| Requirement | Status | Inspected evidence | Remaining boundary |
| --- | --- | --- | --- |
| Tenant-scoped service with RBAC, idempotency and concurrency | `PROVED_LOCAL` | `scripts/case_service.py`, `scripts/access_control.py`, service tests | This is a file-backed reference boundary, not the final production store |
| Source paths and taxonomy files cannot be selected as arbitrary host reads | `PROVED_LOCAL` | deployment-configured input root and taxonomy paths; service path tests | Host must configure one authorized input root per run/tenant |
| Revision-bound background case jobs | `PROVED_LOCAL` | Checksum-verified queue records, trusted worker, retry/replay/stale tests, deployment-controlled taxonomy builds, and minimum-context host model invocation outside the mutation lock with exact-response retry recovery | Production broker/worker deployment remains a deployment concern |
| Object storage, signed URLs and malware scanning | `DEPLOYMENT_OPEN` | Host-injected no-shell scanner boundary with checksum-bound clean receipts; 30–900 second HMAC artifact grants with role checks, manifest revalidation and audited redemption | Production object store, scanner deployment/signature operations, secret management and gateway delivery are absent |
| Encryption, backup, retention and deletion automation | `DEPLOYMENT_OPEN` | Host-configured 1–3,650 day archive policy, retained approved-artifact access, studio-admin/revision/cutoff-gated purge, and checksum-protected idempotent deletion tombstones | Owner-approved tenant periods, KMS/storage encryption evidence, backups and production deletion jobs/operations are absent |
| Ten required structured review data contracts | `PROVED_LOCAL` | `scripts/review_views.py`, bounded pagination and MCP/service tests cover dashboard, sources, mappings, statements, schedules, questionnaire, notes, issues, preview, and approval/export | None for the structured service contract |
| Dedicated workflow UI and accessibility | `DEPLOYMENT_OPEN` | Structured contracts and an escaped semantic comparative preview with a skip link, visible focus, labelled tables and keyboard-scrollable regions exist | Production interaction components, end-to-end keyboard/screen-reader verification and 10,000-row grid behavior are absent |
| REST resources described in section 18 | `PROVED_LOCAL` | Optional `scripts/http_api.py` and HTTP tests cover the suggested resources, host-injected authentication, deployment-controlled rule packs, `Idempotency-Key`, `If-Match`, replay, stale conflict and compact reads | Production HTTP deployment, gateway policy and availability remain deployment concerns |
| Performance targets | `PARTIAL` | `references/performance-evidence.md`; production engine passed the 20,000-row parse, statement-recompute and local-validation time targets on the recorded arm64 environment | Provider-backed narrative timing, 10,000-row production-grid responsiveness, repeat environments and production SLO ownership remain open |
| Local record integrity and partial-write detection | `PROVED_LOCAL` | Atomic canonical case writes include a SHA-256 sidecar; every load verifies it; tampered, missing and symlinked record tests fail closed | None for the file-backed reference record |
| Derived-output revision and version lineage | `PROVED_LOCAL` | Standard computation contexts on parser, eligibility, mapping-candidate, statement, schedule, disclosure, note, intelligence, preview, validation, and local-XBRL outputs; context contract tests | Production storage must preserve the same fields |
| Availability and recovery | `DEPLOYMENT_OPEN` | Atomic checksum-verified case writes, locks, job replay and reproducible approved exports exist | Production availability, backup restore and disaster-recovery evidence are absent |
| Italian/English localization and accessibility | `PARTIAL` | Cases default to Italian and may explicitly select English; accepted narrative/text facts reject mixed output languages; XBRL carries matching `xml:lang`; the local preview has semantic keyboard-accessible review structure | Complete production UI localization and WCAG verification are absent |

## Legal, operational, beta, and owner gates

| Gate | Status | Evidence or decision source | Required closure |
| --- | --- | --- | --- |
| Taxonomy redistribution/licensing | `EXTERNAL_OPEN` | Registry records `licensing_review: required_before_bundling` | Document legal permission or keep controlled fetch/cache deployment |
| OIC content rights and signed accounting-rule ownership | `EXTERNAL_OPEN` | Rule packs use concise metadata and avoid bundled publications | Accounting owner and licensing review must sign off |
| Manual TEBENI comparison | `EXTERNAL_OPEN` | No undocumented automation by design | Professional-controlled run and returned evidence |
| Anonymized real-case pilot and SME review | `EXTERNAL_OPEN` | Only synthetic cases inspected | Approved case corpus and professional reviewers required |
| Monitoring/support/regulatory-update runbooks | `DEPLOYMENT_OPEN` | Version locks and audit events exist | Operational documents, owners, alerts and rehearsal evidence required |
| Cooperatives, client links, retention periods, PDF/A timing, next native adapter, third-party licensing, single/dual approval | `OWNER_OPEN` | Specification section 28.2 | Product-owner decisions before beta where applicable |

## Evidence-first conclusion

Observed: the intelligent workflow kernel, guarded professional decisions,
deterministic accounting/XBRL path, controlled schedule-to-taxonomy adapter,
pre-approval local processor gate, service boundary, privacy manifest, and
24-case controlled suite are implemented and locally exercised.

Inferred: the repository now contains a coherent MVP reference implementation
of the product thesis, but not a production-ready or externally compatible
filing system.

Unknown or open: complete real-case non-primary PCI filing-content coverage and
classification quality, official TEBENI/rendering compatibility, third-party
rights, representative model/SME results, production storage and operations,
and the explicit owner decisions above.
