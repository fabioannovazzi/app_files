# M6 real-data pilot checklist

Status: source-qualification pilot completed with a fail-closed negative
result; successful real-data preparation remains unmet

This milestone tests whether Clara's preparation boundary survives genuine
commercial accounting messiness. It does not authorize an orchestrator,
automatic account mapping, interpretation, report readiness, publication, or
reuse of a file merely because it is present in the workspace.

## Observed pilot result

- One exact commercial general-journal source was inspected only after explicit
  authorization and binding to the private M6 intake.
- The source was a paginated presentation export rather than an eligible
  row-wise movement export. Some monetary components were embedded in text or
  detached from their posting rows, and source geometry did not uniquely bind
  every amount and debit/credit role to one posting.
- Exact controls could detect disagreement but could not select a posting owner
  or debit/credit role. Balancing is therefore retained as validation, never as
  a classifier.
- A private reviewed qualification classified the source as
  `unsupported_source_layout`. The official producer recorded
  `semantic_review_blocked` and stopped before invoking the parser or reading
  source rows. It emitted no prepared movement table, account-month artifact,
  reconciliation success artifact, plot, or report.
- The unresolved source-specific reconstruction evidence and exception or
  equation machinery remain outside the repository and Marketplace package.
  The bundled fail-closed parser seam does not qualify this source or turn that
  research into a reusable adapter.
- A future attempt requires a native structured journal-detail export or a
  separately justified adapter backed by representative cases and independent
  line-level truth.

This is a valid boundary result, not a successful real-data preparation. It
shows that Clara abstains instead of manufacturing a plausible ledger when
ownership is not source-provable.

## Required source shape for the next pilot

The next real-data preparation attempt must start from a source-owned movement
export with:

- one posting per source row and an explicit stable row or posting identifier;
- an explicit posting date and source account on every posting row;
- explicit debit and credit fields, or one amount plus an explicit
  source-owned posting-side convention;
- one exact source locator for every canonical fact;
- every monetary field consumed exactly once as a posting, a declared control,
  or a structurally typed nonmovement;
- no posting component embedded in narrative text, split across logical lines,
  detached into a parallel batch, or assigned by a balancing equation; and
- exact reconciliation to reviewed source controls when those controls are
  claimed.

Controls validate a complete candidate population. They may not fill missing
amounts, choose between multiple owners, infer a debit/credit side, or turn a
residual into a posting.

This is the reviewed eligibility policy for the next pilot, not a claim that
the current workbook parser proves arbitrary source eligibility. The bundled
v5 parser remains a bounded experimental pilot scaffold. Its synthetic tests
include explicitly reviewed multiline, embedded, and cross-row locator paths;
therefore it is not itself the row-wise eligibility gate and was not invoked
for this negative pilot. A reusable automated qualification contract remains
deferred until representative export families establish stable, mechanically
testable predicates.

## Deterministic-versus-judgement boundary

Deterministic intake may:

- bind one declared source to its exact byte count and SHA-256 digest;
- require a reviewed declaration with an explicit M6 purpose and validity
  dates;
- require the fixed local-storage, no-package, no-publication boundary;
- require acknowledgement that model-read material may enter Codex context;
- require a reviewed de-identification record when the source is described as
  anonymized;
- require every named semantic review before preparation and prohibit automatic
  mapping;
- emit a sanitized, byte-stable intake receipt.

The receipt is hash-bound mechanical evidence, not a signed attestation. It
does not prove who produced or signed the declaration.

Deterministic intake must not:

- infer consent from file presence or prior processing;
- verify the identity or authority of the person making the declaration;
- certify legal permission or anonymization sufficiency;
- inspect accounting meaning, approve a mapping, or resolve a semantic issue;
- copy raw or row-level data into the repository or plugin package;
- promote the pilot to report-ready or authorize publication.

Human judgement owns:

- whether the authorizer has the right to permit the exact use;
- whether anonymization and re-identification risk are acceptable;
- dataset identity and grain, including movement versus closing or
  year-to-date values;
- scope, entity, consolidation, eliminations, currency, unit, FX, calendar,
  signs, and control equivalence;
- every account mapping, tolerance, exception disposition, and semantic error;
- whether any sanitized summary or receipt metadata may be retained, where it
  may be stored, who may access it, and for how long.

The receipts and sanitized summary are confidential, pseudonymous, linkable
audit metadata—not anonymous or automatically safe to publish. Exact source
digests support file-membership checks; stable IDs, byte counts, dates, counts,
and cross-receipt hashes support correlation. Digest-shaped IDs are only
syntactically constrained and may encode identifying text. Deterministic code
does not prove random generation, non-identifiability, unlinkability, reviewer
identity, reviewer authority, or review authenticity.

## Error-separation contract

Mechanical errors are limited to exact, reproducible failures such as:

- malformed schemas, duplicate fields or keys, stale digests, unsupported
  decimals, or path/receipt drift;
- invalid periods, duplicate or missing account-period rows, imbalance,
  unmatched reviewed mappings, fan-out, or conservation failure;
- formula, reconciliation, deterministic replay, or output-byte failure.

Semantic errors are reviewer-recorded findings about:

- dataset identity, grain, period basis, scope, entity, eliminations, currency,
  unit, FX, or sign;
- account meaning or mapping;
- control equivalence, reported increment, or tolerance;
- any unresolved ambiguity that could produce a plausible but wrong output.

The preparation runner must keep the two registers separate. Deterministic code
may enforce a reviewer-owned `blocking` status but may not create or resolve a
semantic classification.

## Intake acceptance

- [x] Freeze `clara.real_data_pilot_intake.v1`.
- [x] Bind authorization to the exact source digest, M6 purpose, effective
  dates, allowed local processing, and prohibited commit/package/publication
  actions.
- [x] Record that ordinary processing uses the selected Codex account, Clara
  adds no separate recipient, and Clara does not automatically anonymize.
- [x] Require reviewed de-identification and re-identification-risk records for
  a source declared `anonymized_real`.
- [x] Require seven named semantic reviews, prohibit automatic mapping, and
  block preparation while a reviewer-owned blocking issue is unresolved.
- [x] Emit `clara.real_data_pilot_intake_receipt.v1` without file paths,
  authorization narrative, account rows, entity names, or amounts.
- [x] Keep publication `withheld` and `report_ready: false`.
- [x] Add clean, schema, determinism, digest, date, purpose, privacy,
  de-identification, semantic-boundary, duplicate-field, float, and CLI tests.

These checked items validate declared boundaries and review mechanics using
synthetic test bytes. They do not establish current authorization, an eligible
source, accounting-semantic correctness, or completed M6 execution.

## Source-independent execution scaffolding

- [x] Require a fresh, current-user-owned `0700` local output leaf below the
  declared ignored run root and a nonempty, sorted, unique set of existing
  input files.
- [x] Seal an exact registered output tree, reject symlinks and hard links, and
  replay-check each role, generic path, byte count, and SHA-256 digest at the
  validation instant.
- [x] Restrict retainable role identifiers and paths to `mechanical_errors` or
  digest-shaped `artifact-<16 hex>` names at fixed generic locations.
- [x] Bind a mechanical register to the exact pilot and execution IDs, exact
  sealed non-self output receipts, and the current self-register receipt.
- [x] Avoid the impossible self-hash cycle with a declared closure projection:
  only the `mechanical_errors` receipt's byte count and digest are omitted from
  the closure digest; authoritative replay still requires that full receipt to
  match the exact current register path and bytes.
- [x] Restrict check, error, and code identifiers to digest-shaped IDs;
  require closed artifact references, producer-declared fixed mechanical
  classes, and mechanically derived status and counts.
- [x] Derive a canonical path-free, prose-free error-class summary candidate
  from the replay-validated register.
- [x] Require a local retention approval to bind that exact candidate digest,
  then emit a retained receipt that embeds the candidate and binds the approval
  by digest.
- [x] Re-derive the candidate during authoritative validation so coordinated
  count/digest edits to a detached retained receipt cannot establish a valid
  replay.
- [x] Add synthetic mutation coverage for identity, receipt, path, byte,
  permission, alias, identifier, count, approval, dependency, and
  terminal-newline drift.

These checks prove only the generic storage, receipt, separation, and retention
machinery on synthetic bytes. They do not define or validate the actual export
shape, parser, mapping, controls, tolerance, producer, check catalog, local
row-level evidence artifact, or M3 integration for the eventual case. A
case-owned local evidence artifact may be needed for diagnostic row locators;
its shape must be reviewed and digest-bound only after the authorized export is
inspected. The caller must stop the producer and every writer before sealing;
the file-system receipts cannot mechanically establish future quiescence.
None of these artifacts is report-ready or publication-authorized.

The word `sanitized` means only the fixed path/prose/row-value exclusions; it
does not mean anonymous, non-identifying, unlinkable, or safe for a public
repository. The approval artifact is an unauthenticated declaration whose
presence does not prove that a human review occurred.

## Pilot execution acceptance

- [x] Obtain explicit authorization for one exact commercial source and bind
  that source to the private intake.
- [x] Inspect only the authorized source and record its actual export shape.
- [x] Preserve its declared general-journal identity rather than relabeling it
  as a trial balance.
- [x] Apply a private reviewed source-layout qualification before treating the
  source as mechanically preparable.
- [x] Reject the source when amount ownership and posting-side ownership are
  not unique and source-bound.
- [x] Freeze case-owned reviewed contracts for scope, entity, calendar,
  currency, unit, sign, account identity, controls, and tolerances without
  inferring account meaning.
- [x] Freeze a semantic issue register with reviewer, version, evidence,
  status, and blocking flag.
- [x] Run a separate real-data producer; do not relax or relabel M2's synthetic
  producer.
- [x] Reuse the M3 mechanical receipt and output-boundary kernel. Do not promote
  a failure-only run to a preparation audit envelope or fabricate a success
  artifact.
- [x] Preserve the semantic qualification evidence separately from the fixed
  producer-owned mechanical error register.
- [x] Keep all raw and row-level inputs and outputs in an ignored local run
  root.
- [x] Retain only a separately reviewed, sanitized error-class summary and
  necessary cryptographic receipts in a case-approved confidential evidence
  store. Keep them outside the plugin and source repository by default; any
  exception requires an explicit review of the exact metadata, access, and
  retention boundary.
- [x] Add one-error-at-a-time mutations for both mechanical failures and
  reviewer-owned semantic blocking.
- [x] Obtain an independent evidence/code review.
- [x] Run retained M1–M5 regressions, privacy validation, release checks, and
  Marketplace package verification.

## Definition of done

The M6 boundary test may close through either non-overlapping branch:

1. an eligible exact source passes intake and source-layout qualification, its
   semantics are reviewed rather than inferred, deterministic preparation and
   reconciliation pass, and independent review confirms the evidence; or
2. an authorized source fails a reviewed qualification, the semantic gate
   stops preparation before the parser or source-row processing, no prepared
   facts or downstream output are emitted, the fixed failure evidence is
   deterministic and privately retained under review, and independent review
   confirms that the result does not overstate what was proved.

The second branch completes the boundary test but does not establish successful
real-data preparation. M7 remains blocked until an eligible source completes
the first branch, retained regressions pass, and the open product decisions are
resolved or explicitly excluded.
