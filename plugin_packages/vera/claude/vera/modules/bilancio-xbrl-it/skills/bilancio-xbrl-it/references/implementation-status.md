> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Implementation status

## Implemented foundation

- MVP scope blocking for legal form, OIC, listed, regulated, consolidated, and
  final-liquidation flags.
- Revisioned JSON case record with source manifest, audit events, optimistic
  concurrency, approval invalidation, and immutable approval snapshot hashes.
- Generic CSV/XLSX trial-balance layouts, Decimal normalization, source anchors,
  duplicate-account rejection, debit/credit progressive calibration, exact
  closing-total confirmation gate, bounded XLSX preflight, macro/external-link
  rejection, formula-cache checks, and ZIP-path/compression controls.
- Effective-dated form thresholds loaded from a versioned JSON rule pack,
  first-year/two-year windows, user form selection, and micro exclusions.
- Minimum entity identity intake now requires legal name, reporting identifier,
  registered office, explicit first-year status, and a prior statutory form for
  non-first-year cases.
- Open cases have a studio-admin-only regulatory migration operation. Silent
  statutory/disclosure pack substitution is rejected; approved, exported and
  archived cases are immutable. An accepted migration retains source evidence,
  emits version/checksum and invalidation details, clears regulated outputs,
  and records each required full revalidation result.
- Explicit reviewed account mappings and balancing splits; no automatic model
  suggestion acceptance.
- Tenant-isolated approved mapping memory with exact client-over-tenant
  precedence, explicit tenant-wide reuse approval, and no cross-tenant reads.
- Secure prior-XBRL intake with exact entity/period checks, schema reference,
  fact source anchors, no remote XML resolution, validated context periods and
  unit definitions, strict XML-decimal monetary values, and an EUR-only
  comparative-reconciliation gate. Its versioned context model preserves
  explicit dimensions, canonical typed dimensions, tuple ancestry,
  segment/scenario placement, semantic context signatures, and context-to-fact
  groups for later table reconstruction.
- Exact statement-line aggregation, balanced reviewer-approved presentation
  adjustments, full-precision computation, explicit presentation-rounding
  formulas, current and comparative balance/result tie-outs, annual negative
  confirmations, layered blockers, approval, workpaper, and artifact manifest.
- Versioned ordinary, abbreviated, and micro primary-statement presentation
  policies bound to the official catalogue. The engine derives every required
  monetary leaf and total from the selected official presentation/calculation
  roles, requires explicit period-by-period zero or not-applicable decisions
  for absent leaves, verifies or derives calculation totals, and blocks
  validation and rendering until coverage is complete. The controlled official
  catalogue audit closed 87 abbreviated, 84 micro, and 224 ordinary unique
  leaves and all three complete-form instances passed pinned offline Arelle.
- Explicit fixed-asset, receivable, payable, equity, provision, TFR, tax, and
  guarantees/commitments schedule contracts with exact movement, maturity,
  opening/closing, reclassification, and statement reconciliation checks.
- A checksum-locked schedule-to-taxonomy adapter derives the selected form's
  permitted note-table concepts from the official presentation graph. A
  professional records an exact disposition for every stable schedule cell;
  mapped monetary facts are mechanically derived, text facts use one exact
  source, omissions require reviewed reasons, out-of-table concepts and
  duplicate or contradictory facts are rejected, and matching primary facts
  are reconciled instead of duplicated. The ordinary and abbreviated forms
  expose controlled table inventories; micro cases follow a reviewed
  text-only route because the entry point has no note tables.
- Tuple-based note tables preserve role-specific presentation paths and bind
  each reportable descendant to its exact root and tuple ancestry. Repeated
  schedule rows create distinct tuple occurrences while retaining
  occurrence-scoped duplicate controls; official single- and two-row PCI tuple
  instances pass pinned offline Arelle.
- Payable schedules separately capture and validate the amount secured by
  guarantees, including a source anchor, and reject negative amounts or an
  amount above the closing payable balance.
- An indirect cash-flow evidence contract for ordinary accounts that reconciles
  opening cash, closing cash, and net movement and rejects unsupported
  trial-balance-only classifications. Final validation also reconciles that
  reviewed net movement to the versioned statutory XBRL cash-flow root.
- Documented CSV/XLSX supporting-schedule template ingestion with exact Decimal
  normalization and per-cell evidence anchors for the normalized schedule
  contracts.
- Effective-dated disclosure coverage, a blocker-first dynamic questionnaire,
  all annual negative confirmations, fourteen structured note sections,
  terminal-answer gates requiring substantive values or specific
  not-applicable reasons under the authenticated reviewer identity,
  sentence-level narrative provenance, prior-text stale suggestions and
  word-level redlines.
- Pre-validation lifecycle state now follows the reviewed coverage itself:
  incomplete structured schedules or answers enter `DATA_GAPS`; once those
  source-backed requirements are complete, the case enters `NOTE_DRAFT` for
  narrative work. Narrative absence is not mislabeled as missing accounting
  evidence.
- Escaped HTML review preview with substantive-content hashing, preview
  invalidation, structured workpaper inclusion, and a user-controlled external
  TEBENI report record that does not alter the approved accounting snapshot.
  A later export carries the report and its source-document receipt as a
  non-authoritative workpaper addendum.
- Tenant-scoped file service with authenticated request context, role
  capabilities, time-limited platform-support grants, optimistic concurrency,
  file locking, idempotency records, and compact writable Vera MCP tools.
- Intelligent-participation contracts for workflow guidance, account mapping,
  question prioritization, narrative drafting, prior-year comparison, and issue
  explanation. Context packets exclude direct entity identity where not needed,
  treat document text as untrusted, and validate strict model output schemas and
  evidence closure. Suggestions remain `MODEL_SUGGESTED` until a professional
  applies a separate reviewed decision.
- State-aware orchestration selects the next bounded intelligence contribution
  from unresolved mappings, active questions, stale prior text, incomplete note
  sections, validation issues, or general workflow guidance. The selector does
  not apply its own suggestions.
- Arelle-backed schema-2 taxonomy catalogue builder that distinguishes items,
  tuples, dimensions and non-item schema concepts and preserves labels,
  references and extended relationship metadata; checksum-bound XML renderer,
  accepted narrative text facts, reviewed dimensional facts, explicit
  taxonomy-permitted nil facts, and a replaceable local Arelle validation
  interface.
- The local validator fails on Arelle calculation inconsistencies and all
  severe processor log levels even when the processor exits with code zero, so
  approval cannot treat a calculation-warning channel as a passing report.
- Reviewer-owned issue acknowledgements and professional HIGH overrides bound
  to exact issue fingerprints. Structural blockers remain non-overridable;
  approval requires warning review and explicit override confirmation.
- Substantive taxonomy mismatches create a reviewer-owned differences record,
  remain visible as a reviewed warning, and block readiness until a treatment
  is chosen. Vera records but does not select or legally require the
  double-format filing route; exports include the differences artifact.
- Micro-company cases require an explicit notes-versus-footer choice. A
  footer-only case can satisfy narrative requirements through three reviewed
  statutory footer items and no note blocks; the deterministic renderer emits
  the versioned official footer text concept. Positive disclosures that
  conflict with the simplified route remain blocking.
- Audit events include tenant, actor, case, revision, originating interface,
  and before/after hashes for material changes. The exported workpaper includes
  the entity and period, adjustments, narrative change log, warnings,
  overrides, approval, and artifact-manifest reference.
- Major derived outputs carry one standardized reproducibility context with the
  originating case/revision, source-manifest hash, mapping hash, locked rule
  versions, taxonomy checksum, model/template version, and computation time.
- Approved export produces standalone mapping, issue, and validation reports in
  addition to XBRL, accessible preview, and the complete workpaper. Each report
  binds the immutable snapshot identifier and hash. The workpaper contains
  peer-artifact checksums, while the final manifest records the workpaper and
  all other artifact hashes without recursive self-hashing.
- An offline model-quality regression harness scores recorded outputs for
  monetary-weighted mapping precision, material-ambiguity recall,
  missing-information recall, stale-text recall, prompt-injection leakage,
  strict contract validity, and normalized-output stability.
- Official PCI 2018-11-04 package source and SHA-256 recorded in the taxonomy
  registry. A generated 2,399-concept catalogue and minimal ordinary,
  abbreviated, and micro instances were exercised locally against the official
  package; all three passed the pinned Arelle validator. See
  `taxonomy-spike.md` for the reproducible evidence and remaining gates.
- A checked official schedule-taxonomy audit binds the adapter policy to the
  locked package and catalogue. It found 623 permitted ordinary and 453
  permitted abbreviated monetary table concepts across the eight non-cash
  schedule families, while all eight micro families are explicitly
  `TEXT_ONLY`. See `docs/bilancio_schedule_taxonomy_audit.json` at the
  repository root.
- A checked-in 24-case synthetic regression register covers every scenario in
  specification section 23.3. On 2026-08-05, twenty controlled XBRL instances
  passed the checksum-pinned offline Arelle validator and four unsupported,
  adversarial, or professional-treatment cases passed their production boundary
  contracts. All twenty XBRL cases traverse the public lifecycle, complete
  selected-form presentation and disclosure coverage, and bind approval to a
  passing local processor result. Every ordinary case reconciles its reviewed
  cash-flow schedule to the statutory XBRL root. All eight non-cash schedule
  families exercise a complete adapter disposition in the relevant golden
  cases and emit representative official schedule facts. The run records exact
  suite, catalogue, package, rule-pack, instance, and report checksums and
  explicitly leaves TEBENI as a user-controlled open gate.
- Approval now requires a pre-approval render of the current substantive case
  and a passing local XBRL processor report. The candidate, catalogue, package,
  and report hashes are carried into the immutable snapshot; any substantive
  mutation invalidates the review before approval can recur.
- The file-backed service accepts source and returned external-report reads only
  below a deployment-configured case input root. Taxonomy catalogue/package
  paths are deployment configuration rather than model-controlled request
  fields, and symlinked case, lock, idempotency, preview, export, catalogue, and
  case-write paths fail closed.
- Long-running case mutations can be queued as checksum-verified tenant-scoped
  jobs, executed only by an internal worker role, and replayed through the same
  mutation idempotency ledger. Jobs carry retry limits and the exact source
  revision; intervening edits produce a terminal `STALE` result rather than
  applying old work. Vera exposes enqueue and compact status tools, not worker
  execution authority.
- The same revision-bound worker queues deployment-controlled taxonomy
  catalogue construction without accepting request-selected packages, paths or
  entry points. It verifies registry, package and case checksums and attaches a
  checksum-bound case catalogue receipt usable by pre-approval review/export.
  Host-side semantic invocation accepts only task and subject IDs, constructs
  the existing minimum-context packet, invokes a no-shell JSON command outside
  the mutation lock, persists the exact response for retry recovery, and
  records it only as `MODEL_SUGGESTED` if the original revision still matches.
- A reproducible maximum-size performance runner exercises the production CSV
  parser, mapping application, statement engine, deterministic repeat, and
  validation engine. The recorded 20,000-row arm64 run passed the 60-second
  parse, 10-second statement, and 60-second validation targets. Batch mapping
  audit events reuse one exact post-mutation hash instead of reserializing the
  unchanged case once per account.
- Ten paginated professional-review contracts expose the case dashboard,
  sources and parser evidence, mapping decisions, statements and drill-down
  references, schedules, contextual questions, facts and narrative blocks,
  validation issues, preview/local-XBRL status, and approval/export metadata.
  Large collections are capped per request; approval snapshots, local paths,
  source files, and artifact bytes are not returned by the view tool.
- An optional FastAPI adapter exposes the specification's case, document,
  ingestion, parser, form, mapping, statement, schedule, question, note,
  validation, approval, export, artifact, audit, review-view, and job resources.
  Authenticated context is injected by the host rather than accepted from
  headers or payloads; every mutation uses an idempotency header and every
  post-creation mutation uses an `If-Match` revision precondition.
- MCP and HTTP creation reject request-selected statutory rule packs; the
  trusted bridge loads statutory and disclosure packs from deployment
  configuration, while explicit studio-admin migration remains the only route
  for changing a locked regulatory version.
- The official checksum-locked XBRL 2.1 conformance suite dated 2025-07-16
  passes 606/606 variations with `arelle-release==2.42.1` offline. The first
  structural-only run exposed that calculation inconsistencies were not being
  evaluated; the production validator now always enables Arelle's `xbrl21`
  calculation mode. See `references/conformance-evidence.md`.
- The canonical case record is atomically paired with a SHA-256 sidecar and is
  verified before every load. Missing, malformed, mismatched, or symlinked
  record/checksum files fail closed, adding corruption and partial-write
  detection beneath the existing revision and audit hashes.
- Case output defaults to Italian and may explicitly select English. Accepted
  narrative blocks and taxonomy text facts must match the single case output
  language, rendered XBRL carries the corresponding `xml:lang`, and prior text
  with a known different language cannot be reused. The comparative preview
  adds semantic headings and regions, labelled tables, a skip link, visible
  keyboard focus, and keyboard-scrollable tables.
- The conversational service and trusted worker require a host-configured
  no-shell malware scanner before file ingestion. A clean verdict is tied to
  the exact pre/post-scan checksum and size, stored with engine/signature
  metadata, linked to the imported document, and recorded in the audit trail.
  Non-clean verdicts, missing required configuration, and files changed during
  scanning fail before parsing.
- Reviewer and read-only-auditor roles can issue idempotent, HMAC-signed
  artifact grants lasting 30–900 seconds. Grants disclose no storage path and
  bind tenant, case, artifact and approved checksum. Non-canonical Base64URL
  encodings are rejected before HMAC verification; redemption rechecks the
  manifest, bytes, size and safe path and records both issue and download
  events. The optional HTTP adapter streams the verified bytes with no-store
  and nosniff response controls.
- A host-configured retention period of 1–3,650 days enables studio-admin case
  archiving without invalidating the immutable approved snapshot. Approved
  artifacts remain downloadable while archived. Studio-admin purge is bound to
  the exact revision and archive cutoff, rejects early deletion, removes only
  the validated tenant/case directory, and writes a checksum-protected
  idempotent tombstone containing final case/artifact hashes and accountability
  metadata rather than source content.

## Not yet implemented or proved

- Redistribution/licensing approval for bundling the official PCI 2018-11-04
  ZIP or generated catalogue, and complete statutory golden filings containing
  every triggered statement subtotal and note table. The current 24-case suite
  validates balanced statement totals, scenario-specific official concepts and
  narrative facts, plus four domain boundaries; it is not evidence of complete
  filing-content coverage.
- Automatic reconstruction of complete prior narrative tables from preserved
  dimensional contexts plus the taxonomy presentation graph, and automatically
  prepared section-specific redline packets beyond text facts.
- Complete automated semantic mapping from arbitrary client charts of accounts
  to every PCI leaf, plus a professionally reviewed binding corpus that maps
  every applicable real-client schedule and note-table cell to its exact PCI
  concept and dimensions. Primary-statement inventories, official calculation
  totals, schedule table boundaries, per-cell disposition controls, and
  representative schedule-fact emission are complete and guarded; the
  remaining gap is real-case semantic classification and complete
  non-primary-table population, not adapter plumbing or primary-network
  enumeration.
- Production broker/worker deployment. The durable file-backed reference queue
  covers the specified workbook, taxonomy, semantic, note, render, validation,
  preview and export task classes, but object storage, production
  scanner/signature operations and secrets,
  encrypted backup controls, production retention/deletion jobs, and
  owner-approved tenant policy values remain absent.
  The local scanner and signed-delivery adapters, file service, and optional
  HTTP adapter are tested reference boundaries, not a production persistence
  or gateway deployment.
- Dedicated production interaction components and end-to-end accessibility
  validation for the structured dashboard, review grids, notes editor, issues,
  and approval surfaces. The service/MCP data contracts and accessible local
  comparative preview are implemented, but they are not a production UI.
- Representative recorded-model benchmarks. Strict packets, state-aware
  orchestration, recording tools, and an offline scoring harness exist, but the
  representative benchmark corpus has not yet been run against the selected
  production model versions.
- Provider-backed narrative latency, production review-grid responsiveness,
  multi-environment load results, and production SLO ownership. The checked-in
  deterministic benchmark is local evidence, not an availability or capacity
  guarantee.
- Manual TEBENI compatibility results and external-renderer regression fixtures.
- Complete applied-intelligence evaluation for mapping, ambiguity recall,
  missing-information recall, question relevance, narrative fidelity,
  prior-year reuse, prompt-injection resistance, and Italian terminology.

Never describe the MVP acceptance criteria as complete while any item above
remains open.
