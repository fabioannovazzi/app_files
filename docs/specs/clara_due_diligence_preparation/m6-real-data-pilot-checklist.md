# M6 real-data pilot checklist

Status: intake-declaration, semantic-review, and source-independent
output/error-retention gates implemented; eligible data and execution pending

This milestone tests whether Clara's preparation boundary survives genuine
commercial accounting messiness. It does not authorize an orchestrator,
automatic account mapping, interpretation, report readiness, publication, or
reuse of a file merely because it is present in the workspace.

## Observed eligibility position

- The repository contains no commercial trial balance with a matching
  anonymization or reuse-authorization record.
- Several ignored, commercial-looking ledger workbooks exist in the local
  workspace. Their filenames and prior presence are not consent evidence, and
  their contents have not been inspected for M6.
- The only tracked Clara monthly trial balance is explicitly synthetic and
  cannot satisfy this milestone.
- A bounded public-source search found no dataset that simultaneously proves
  real commercial origin, trial-balance or general-ledger granularity, stable
  reproducible access, and owner-backed commercial reuse permission.
- BookSQL is based on anonymized business accounting databases, but its
  CC-BY-NC-SA terms prohibit commercial use. It is not an eligible Clara
  Marketplace fixture.
- BPI Challenge 2019 is a licensed, real, anonymized commercial process log,
  but it is purchase-to-pay event data rather than a complete general ledger or
  trial balance.
- The frozen intake contract accepts `commercial_trial_balance` only. A general-
  ledger pilot would require a separately reviewed contract-version and scope
  change; it must not be relabeled as a trial balance.

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

- [ ] Obtain explicit authorization for one exact commercial trial-balance
  source or receive a separately anonymized source with documented reuse
  authority.
- [ ] Inspect only the authorized source and record its actual export shape.
- [ ] Confirm whether the source is a monthly movement trial balance. Do not
  reinterpret a closing or year-to-date export deterministically.
- [ ] Freeze case-owned reviewed contracts for scope, entity, calendar,
  currency, unit, sign, account mapping, controls, and tolerances.
- [ ] Freeze a semantic issue register with reviewer, version, evidence,
  status, and blocking flag.
- [ ] Run a separate real-data producer; do not relax or relabel M2's synthetic
  producer.
- [ ] Reuse the M3 mechanical kernel and audit-envelope boundary. Revise the
  kernel explicitly if the private case has no genuine remote-source receipt;
  do not fabricate one.
- [ ] Emit separate mechanical and semantic error artifacts.
- [ ] Keep all raw and row-level inputs and outputs in an ignored local run
  root.
- [ ] Retain only a separately reviewed, sanitized error-class summary and
  necessary cryptographic receipts in a case-approved confidential evidence
  store. Keep them outside the plugin and source repository by default; any
  exception requires an explicit review of the exact metadata, access, and
  retention boundary.
- [ ] Add one-error-at-a-time mutations for both mechanical failures and
  reviewer-owned semantic blocking.
- [ ] Obtain an independent evidence/code review.
- [ ] Run retained M1–M5 regressions, privacy validation, release checks, and
  Marketplace package verification.

## Definition of done

M6 is complete only when an eligible exact source has passed intake, its
semantics have been reviewed rather than inferred, the deterministic
preparation has run, mechanical and semantic errors are separately recorded,
the raw data has remained outside the repository and package, and independent
review confirms the resulting evidence does not overstate what was proved.
