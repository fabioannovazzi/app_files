# Vera advanced-control transfer audit

Date: 2026-07-25

Status: open remediation record. This document records inspected production
evidence; it is not a capability claim and it is not an orchestrator design.

## Acceptance criteria

The selective Clara M1-M7 transfer is assessed through eight mechanically
reviewable criteria:

1. exact units, increments, precision, and visible abstention;
2. reviewed effective recipes, mappings, and relationship perimeters;
3. separate source, decision, transitive implementation, prepared-output, and
   rendered-output receipts with fresh replay and re-derivation where those
   layers exist; a consistently rehashed current manifest is not by itself an
   authority;
4. exact declared output-set closure and material-value output addresses where
   the workflow renders material values, with changed values accepted only
   when they rederive from trusted inputs or an explicit reviewed successor;
5. independent source, preparation, reconciliation, semantic, reporting, and
   publication states where applicable, including genuine blocked and failed
   runs;
6. reviewed formula/sign execution, exact residual preservation, and
   forbidden-inference controls where calculations exist;
7. source eligibility before prepared facts can become authoritative, with
   zero plausible rows after qualification failure; and
8. mutations that fail at the intended gate plus independent representative
   cases.

`Not applicable` is permitted only when the workflow has no corresponding
assurance risk. It is not a substitute for missing evidence.

## Inspected baseline

| Workflow | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Audit Reconciliation | gap | gap | gap | gap | gap | pass | pass | gap |
| Journal Sampling | pass | pass | gap | gap | pass | selective N/A | pass | bounded pass |
| Check Entries | pass | pass | pass | gap | pass | pass | pass | gap |
| Journal-Bank | pass | pass | pass | gap | pass | pass | pass | gap |
| Report Builder | pass | pass | gap | gap | gap | pass | pass | pass |
| Concordato | pass | pass | gap | gap | pass | gap | gap | gap |

This baseline was established by inspecting production code, focused tests,
workflow instructions, and retained evaluation evidence. Documentation alone
did not count as implementation evidence.

### Audit Reconciliation

Pre-parser role/adapter qualification, exact source and decision receipts,
strict Decimal parsing and abstention, one-to-one evidence-use controls,
allocation conservation, independent gates, material-value addresses, and
readiness blocking for failed checks or pending required review are retained.

The current successor boundary is an exact 25-file implementation contract.
Every public Python and MCP surface checks that boundary before loading
workflow logic. A successor requires a caller-supplied predecessor checkpoint
retained outside the candidate tree, archives the predecessor, rederives its
prepared rows, allocations, closed-bank-allocation controls, and core checks,
and binds the successor run identity to that replayed transition. Missing or
wrong checkpoints leave the exact tree unchanged.

The scoped remediation suite passed 308 tests with no failures, errors, or
skips. A separate root re-audit passed 32 targeted attacks across expanded
implementation trees, timestamp-valid bytecode, browser/Python/MCP checkpoint
enforcement, alternative self-resealed predecessors, and seven material
predecessor mutation families. Black, isort, mypy, Bandit, Python compilation,
Node syntax, widget parity, and scoped diff checks passed.

The checkpoint proves continuity only if the operator retained it through an
independent channel. Reviewer identity remains unauthenticated, and the public
bank-like cases are projections rather than authentic raw bank statements.

### Journal Sampling

Normalization has reviewed mappings, source/decision/implementation/prepared
receipts, qualification, gates, replay, exact units and increments, and strong
population closure.

The sampling stage now has a sample-stage receipt/envelope, exact
declared-vs-physical output closure, all-row prepared-to-CSV/XLSX value
addresses, fresh replay, implementation receipts, and independent
source/preparation/semantic/reporting gates. The focused Journal Sampling and
shared-assurance block passed after this remediation.

The review successor boundary now archives each trusted predecessor under its
canonical stage identity, binds the successor to the predecessor manifest,
freshly rederives decisions, effects, counts, statuses, gates, run intake, and
final artifacts, and seals the exact file, directory, and mode contract.
Save-then-apply chains preserve and replay every predecessor. Review acceptance
cannot set `final_ready`: semantic review remains `not_assessed`, reporting
`blocked`, publication `withheld`, and `report_ready=false`.

The fresh root re-audit passed all 160 Journal Sampling tests with no failures,
errors, or skips. Retained attacks cover missing and rogue paths, empty
directories, symlinks, hardlinks, FIFOs, file/root modes, archived bytes and
manifests, predecessor binding, stale effect/count/status fields, and a rogue
predecessor file before archive. Black, isort, mypy, Bandit, Node syntax, and
diff checks passed.

This closes the supplied-successor gap for the current chain. The archive and
manifest prove internal chain consistency; they are not an external signature
or independently retained checkpoint against wholesale substitution before a
review call.

Ratios, de-cumulation, and residual allocation remain deliberately not
applicable to sampling.

### Check Entries

Upstream normalization replay, exact support capture, relationship/direction
decisions, numeric addresses, independent gates, and reproducible assurance
envelopes are implemented.

Exact workflow-owned output-set validators now cover the initial run, the
bounded review transition, and the accepted successor. They enumerate the
canonical base package and the only permitted review decision, revision, and
backup paths; they reject unexpected regular files, directories, symlinks,
hardlinks, and special files. Run, validate, render, save, and apply paths all
enforce the same physical perimeter, and late failures restore the exact prior
tree.

The fresh root re-audit passed all 189 Check Entries tests with no failures,
errors, or skips. Black, isort, mypy on the material boundary, Bandit, Node
syntax, and diff checks also passed. This closes the previously recorded
physical output-set and rollback gaps. It establishes current-tree
self-consistency and bounded successor replay; it does not authenticate an
external reviewer or prove the historical identity of an entirely substituted
honest run tree.

### Journal-Bank

The prior adapter-v5 snapshot had bounded delimiter profiling, explicit
separator and complete monetary-column authority, strict full parsing,
reviewed relationship policy, source capture, exact matching/residuals,
independent gates, final physical output-set closure, and stale-receipt
rejection.

An independent audit of that frozen snapshot passed all 212 plugin tests and a
separate adversarial harness. It closed intermediate fail-open paths for
explicit numeric separators, stale automatic-path monetary declarations,
stale v4 receipts, malformed authority fields, and malformed recipe
containers. The audited production core SHA-256 was
`5b5742f3a10a841f85cd7a4308825312b52aebfef4006bed4b15bc54fbe7febe`;
contract v3 remained
`13b7f430805767962f7c531872cd8d91b6bb68adc74ff895acb0e6b3a2e99046`.

The sealed blind v3/v5 holdout did not reach the oracle: its public intent used
a direction-policy phrase outside production's enumerated vocabulary, while
contract v3 required a policy without defining the allowed vocabulary. The
oracle remained unopened, so this established a public-fixture/contract defect
rather than an implementation result.

A subsequent independent contract audit found a separate production defect:
adapter v5 could silently resolve dates such as `01/02/2026` according to
format-list order. The v5 snapshot is therefore historical evidence, not the
promotable current contract. Adapter v6 now binds `day_first` / `month_first`
authority to the source receipt, rejects parser-order guessing and invalid
populated dates, preserves exact tolerance types, and freezes
direction/reference vocabularies and semantic-oracle projections in contract
v4. Native `relationship_residuals.csv` and `material_value_ledger.json` close
every declared match/residual value from fresh preparation through its CSV row
and XLSX cell, including second-row/cell mutation checks. At that repository
freeze, all 252 Journal-Bank plugin tests passed; immutable contract v4
SHA-256 is
`18c3e11da7bf263dbe392c13ad56af64b94c2093a1f2428ede52a66e85bdc97b`
and the production core SHA-256 is
`b6dabd917396ef36eb62de37b4066549409a5d113e32014d498da08a8debefe5`.

The adjudicated r3 successor is recorded as mechanical regression `GO`. It
confirmed the existing production boundary: normalized and matched source
amounts preserve sign, matching and allocation use non-negative magnitudes,
ambiguous delimiters require review, unsupported delimiters remain unsupported
layouts, and `parser_failure` is reserved for an actual failed full parse.
Because r3 corrected already-inspected v4 oracle evidence, it is not a fresh
unseen promotion case and does not close C8.

Prospective contract v5 freezes those semantics explicitly without changing
production behavior. Its SHA-256 is
`4824652ecdb990a844fd9b72d799a2537f46a21ddb9fefb8a664f828c0ec6657`.
The sealed v7 holdout reached its hidden evaluator and remained `NO-GO`. It
identified a genuine blocked-output-set defect: blocked runs did not persist
the complete initial native package. Current blocked runs now persist the exact
reviewable package except the contract-forbidden material ledger, and expose
per-side source outcomes.

The exposed v7 diagnostic still disagrees with production over direction
authority containing an extra unobserved label, exact stable-reference tokens,
fields absent from the frozen `vera.allocation_ledger.v1` allocation schema,
unspecified material-ledger internal key names, and the artifact in which a run
block code is read. Those expectations are not adopted as product semantics.

A separately authored sealed v5-contract successor then passed 23 of 24 cases
and exposed a genuine stale per-side source outcome after mid-run source-root
membership change. That defect is remediated. The post-exposure replay is
regression evidence only; the sealed result remains immutable `NO-GO`.

A later private real-source diagnostic first qualified all 8,141 reviewed
journal candidates and correctly withheld all bank candidates because
localized textual-month dates were outside the frozen adapter-v6 date
contract. Its blocked package and assurance receipts replayed. This was
positive abstention and reviewability evidence for the declared adapter, not a
v5 defect or promotion evidence.

The separately frozen additive
`journal-bank-tabular-v7-extension-contract.v1.json` has SHA-256
`74f779325acf234cbbf126b2060d43ea63a2788f6f645d36a750cd3ec4910347`.
It requires current source-bound reviewer authority for the exact Italian
locale or exact non-movement summary labels; it does not silently upgrade v6
or infer accounting meaning. Its public positives, invalid/mixed-language
dates, stale-receipt mutations, structural summary non-overrides, and
sequential all-row workbook replay pass. The complete Journal–Bank file now
collects 317 tests: 228 pass and 89 dependency-gated cases skip, with no
failures or errors.

The authorized private v7 rerun qualified 202 bank and all 8,141 journal
movements, produced 36 deterministic candidate matches, retained 8,343 exact
relationship residual rows, replayed 83,826 material-value addresses and all
42 assurance receipts, and correctly kept reconciliation, semantic, reporting,
and publication gates from promotion. The known source family and its sibling
statements remain diagnostic rather than blind holdout evidence.

V5 is not promoted: Journal-Bank M7 remains `NO-GO` until a new independent
unseen holdout bound to the exact v5 bytes and production schemas passes. The
additive v7 contract separately requires a fresh independently authored unseen
holdout before any representative v7 claim.

### Report Builder

Reviewed measure meaning and source-to-prepared-to-XLSX/Markdown/DOCX numeric
addresses are the strongest output-closure implementation in this set. Formula
cells fail closed, source and output bytes are replayed, and a genuine
post-remediation blind SEC holdout exists.

The current implementation adds an exact transitive implementation and
prepared-output receipt set, exact physical file/directory equality, link and
special-file rejection, bounded rollback, independent readiness/publication
withholding, and a replayed successor history. A later review requires the
prior `integrity_checkpoint` through an external argument; it is never inferred
from the candidate report tree. The retained alternative-honest-predecessor
substitution now fails in both public Python and MCP validation.

The full current Report Builder file passed 142 tests with no failures, errors,
or skips. Retained tests cover exact implementation receipts, unowned physical
paths, formula and prepared-output rehashing, source mutation, current and
predecessor successor forgeries, missing or wrong external checkpoints,
transaction rollback, and publication withholding. Black, isort, mypy,
Bandit, Node syntax, generator parity, and scoped diff checks passed.

This is local continuity anchored by an operator-retained digest, not a
signature, reviewer authentication, or protection against replacement of the
entire package and its external checkpoint channel. A full Clara-style
assurance envelope is not required.

### Concordato

Exact Decimal candidate parsing, reviewed source roles and candidate
dispositions, source/decision/implementation/prepared receipts, gates,
candidate-value addresses, and semantic withholding exist.

The current boundary closes the previously observed implementation gaps:

- the exact 25-file plugin and shared-assurance implementation tree is checked
  before assured commands import workflow logic;
- reviewed `source_role_mapping` and paired
  `calculation_formula_authority` decisions bind source roles, candidate
  dispositions, formula, sign meaning, period, sources, and candidate
  perimeter before authoritative numeric extraction;
- the numeric evidence ledger freshly replays every selected candidate,
  difference, tolerance, result, residual, summary count, source count, and
  material CSV/XLSX/DOCX address;
- the final closure covers the exact physical file and directory set, rejects
  links and special files, and binds every declared path to current bytes;
- save and apply seal explicit successors through
  `previous_closure_content_sha256`, while fresh standalone replay rederives
  immutable authority and review effects; and
- review acceptance cannot set professional readiness: semantic review remains
  unassessed, reporting blocked, publication withheld, and
  `final_ready=false`.

The fresh root re-audit passed all 104 Concordato tests with no failures,
errors, or skips. Retained attacks cover stale or forged formula authority,
source-role and candidate perimeters, implementation mutation, unowned
implementation entries, numeric-ledger rehashing, last-row CSV/XLSX/DOCX
mutation, unexpected outputs, links, hardlinks, special files, forged
successor chains, stale parent receipts, child self-authorization, and exact
rollback. Black, isort, mypy, Bandit, Node syntax, and diff checks passed.

This establishes the bounded deterministic contract on the two retained
synthetic workbook families. A later bounded real-source case compared selected
pages from a published plan, a separately authored attester's report, and a
judicial commissioners' report. It showed exact aggregate agreements,
material adjustments, and creditor-class reallocations while keeping semantic
support conclusions withheld. Only three selected pages were qualified, so
full-population real-plan generality remains unproven and M7 is not closed for
a real corporate source family.

Legal, tax, and support-sufficiency conclusions remain professional judgment
and must not be converted into deterministic classifications.

## Shared transaction boundary

The bounded parent/child review transaction was independently exercised
against Check Entries and Report Builder:

- 42 retained exploit, malformed-result, source-replay, readiness, and
  mode-preservation cases passed;
- a separate seven-case black-box harness passed;
- rejected operations preserved the exact canonical tree bytes and modes and
  left no transaction residue.

This is not an operating-system sandbox. Same-identity child code retains the
ambient filesystem and network authority of its parent process; the contract
protects the bounded canonical output tree and validates declared effects.

The current cross-workflow verification ran 213 shared-assurance, packaging,
non-plotting review workbench, review-contract, interaction-pattern,
payload-coverage, transaction-generator, demo, and visual-audit tests in one
process with no failures, errors, or skips. The six workflow implementations
are separate plugin process boundaries and their complete isolated suites
passed 1,201 tests in aggregate.

They are not safe to co-load as source modules in one Python interpreter:
multiple plugins deliberately use local names such as
`implementation_bootstrap`, and Python module caching can bind a later test to
the earlier plugin's boundary. Marketplace execution starts each plugin
CLI/MCP surface in its own process; same-interpreter co-loading is outside the
declared execution contract.

## Selective exclusions

- Do not add de-cumulation, ratio, or allocation machinery to Journal Sampling
  without a reviewed case that needs it.
- Do not move customer-concentration interpretation from Clara Commercial DD
  into Vera.
- Do not force Clara's full assurance envelope into Audit Reconciliation or
  Report Builder. Package-neutral receipts, ledgers, replay, exact output
  closure, and independent readiness remain required.
- Do not mechanize Concordato legal or tax relevance, evidence sufficiency, or
  professional conclusions.
- Preserve source-reported increments specifically where the source contract
  provides them; do not manufacture increments for every workflow.
- Do not add an orchestrator as part of this remediation.

## Promotion rule

The transfer remains open until every applicable gap above is either:

1. closed in production code and retained tests;
2. shown by inspected evidence to be non-applicable for a stated workflow
   risk; or
3. explicitly removed from the product claim.

After remediation stabilizes, the evidence must include a coherent focused
run, full coverage gate, refreshed per-surface privacy reviews, interaction and
review-contract validation, release checks, a fresh unseen Journal-Bank
adapter-v6 holdout result under the exact v5 contract, and one final
requirement-by-requirement audit.
