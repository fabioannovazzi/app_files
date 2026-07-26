# Vera audit and reconciliation assurance redesign

Status: active design and implementation

Date opened: 2026-07-24

## Objective

Reorganize and harden Vera's audit and reconciliation capabilities so that:

1. specialist workflows remain clear to the commercialista or revisore;
2. mechanically common controls are implemented once and reused;
3. source adapters are explicit about the export families they support;
4. unsupported or ambiguous layouts stop without manufacturing plausible rows;
5. monetary calculations and comparisons are exact;
6. every material output number can be traced to prepared evidence;
7. the strongest assurance capabilities proven in Clara M1-M7 are reused
   without importing Clara-specific cases, schemas, or orchestration;
8. representative independent cases, including negative cases, are required
   before a capability is described as general.

This is a Vera audit-assurance program. It is not a Clara Commercial Due
Diligence program and it does not authorize an orchestrator.

## User and professional boundary

The user-facing Vera workflows remain:

- Audit Reconciliation;
- Journal Sampling;
- Check Entries;
- Journal-Bank Reconciliation;
- Report Builder;
- Concordato Plan Review.

Vera may organize evidence, run mechanical checks, prepare workpapers, and
identify exceptions. The commercialista or revisore owns materiality,
professional judgment, approval, and conclusions.

## Evidence for the redesign

The current implementation has useful workflows and review artifacts, but it
does not yet prove generalization across independent accounting-system exports.

- Journal Sampling accepts a print-friendly source when the parser produces any
  records. Its generic text-PDF path assigns the final one or two numeric tokens
  on a line to debit and credit without proving source-owned amount roles.
- Audit Reconciliation contains case-origin terminology such as `All.A` in
  reusable evidence wording and can infer source roles from filename keywords.
- Audit Reconciliation may assign journal monetary cells to debit or credit by
  position relative to a calculated midpoint.
- Journal Sampling, Check Entries, Journal-Bank Reconciliation, and Concordato
  Plan Review contain binary-float monetary paths. Report Builder parses values
  as `Decimal` but serializes numeric profiles back to floats.
- Check Entries can select a sole support PDF without independent match
  evidence, can replace a missing movement number with a row index, and can
  emit `ok` when only the subset of available checks passes.
- Journal-Bank Reconciliation can treat generic description tokens as
  references, accept a unique amount candidate without a usable date, and
  silently disable an empty sample restriction.
- Audit Reconciliation does not currently enforce evidence-use uniqueness,
  fan-out, currency equality, party equality, or allocation conservation. One
  bank row can therefore close duplicated open rows, and equal amounts can
  match across currencies.
- Audit Reconciliation may write complete-looking workpapers when required
  review remains pending or checks fail; current final readiness is driven
  mainly by recorded review actions rather than independent mechanical and
  semantic gates.
- The focused pre-change regression suite for the six workflows passed on
  2026-07-24. Existing success is therefore the compatibility baseline, not
  evidence that the workflows generalize.

Relevant source locations:

- `plugins/journal-sampling/scripts/journal_sampling_core.py`;
- `plugins/audit-reconciliation/scripts/raw_input_runner.py`;
- `plugins/audit-reconciliation/scripts/locale_support.py`;
- `plugins/check-entries/scripts/check_entries_core.py`;
- `plugins/journal-bank-reconciliation/scripts/journal_bank_core.py`;
- `plugins/report-builder/scripts/report_builder_core.py`;
- `plugins/concordato-plan-review/scripts/concordato_plan_core.py`.

## Governing distinction: general procedures, bounded adapters

A source adapter may be narrow. It must not be vague.

A supported adapter declares:

- adapter and version;
- source family and accepted file types;
- required fields and field ownership;
- header or record-grain assumptions;
- date, account, posting identity, currency, and monetary-field rules;
- whether debit and credit are explicit or follow a source-owned convention;
- exact source locator for every emitted row;
- completeness and reconciliation checks;
- known limitations;
- representative positive and negative fixtures.

An adapter that cannot establish these properties returns
`unsupported_source_layout`. It does not infer missing ownership from residual
equations, numeric position, adjacent rows, or a model-generated guess.

Model-led inspection may propose an adapter recipe or mapping. The reviewed
recipe then becomes an explicit input to deterministic execution. A model
proposal is not itself proof that the source layout is eligible.

For Journal-Bank tabular sources, adapter v6 treats the CSV field delimiter as bounded
transport syntax separate from decimal and thousands separators. Only comma,
semicolon, tab, and pipe are eligible; ambiguous or unsupported selection emits
zero rows. LF, CRLF, and CR are normalized mechanically before a strict
full-file parse, so a malformed row outside the bounded profile cannot yield a
partial qualified population. Every reviewed mapping binds the exact current
potential monetary columns and a complete mapped-or-explicitly-excluded
disposition. It also binds `day_first` or `month_first` when day/month text has
two valid interpretations; invalid populated dates fail the complete source
rather than falling back to reference matching. These are reproducibility and
population-completeness controls, not substitutes for semantic review.

## Target architecture

### 1. Source-family adapters

Adapters inspect and normalize bounded source families such as:

- native row-wise journal exports;
- explicit debit/credit ledger exports;
- bank movement exports;
- open-item schedules;
- FatturaPA XML collections;
- readable report tables;
- reviewed plan and support schedules.

Each adapter produces a qualification result before prepared facts are
available.

### 2. Vera assurance core

The shared core owns only mechanically verifiable primitives:

- strict and canonical Decimal text;
- exact arithmetic and reviewed tolerances;
- canonical JSON and stable hashing;
- local input and output artifact receipts;
- reviewed-decision presence receipts;
- independent gate statuses;
- source-layout qualification records;
- evidence and output locators;
- deterministic replay validation;
- numeric evidence-ledger validation.

It does not select sources, interpret document meaning, choose accounting or
legal treatment, approve mappings, select materiality, or write professional
conclusions.

### 3. Reusable audit procedures

Procedures consume qualified canonical evidence:

- reproducible sampling;
- entry-to-support checking;
- journal-to-bank matching;
- open-item and evidence reconciliation;
- roll-forward and tie-out checks;
- reviewed financial calculations;
- report-table preparation.

Matching rules may deterministically close a row only when the evidence
contract proves the required keys or reviewed relationship. Candidate matching
and semantic similarity remain review inputs.

Every relationship-sensitive procedure must declare and validate:

- entity and party perimeter;
- currency and unit compatibility;
- one-to-one, one-to-many, many-to-one, or grouped allocation shape;
- evidence reuse policy;
- allocation conservation;
- unmatched and residual disposition;
- cut-off and date policy;
- sign and direction policy.

No evidence row may close more than the relationship contract permits.

### 4. Specialist workflow and review layer

The six Vera workflows remain the user entry points. They own:

- intake questions;
- workflow-specific recipes;
- assumptions and reviewed decisions;
- exception queues;
- Excel, Word, Markdown, CSV, JSON, and MCP review artifacts;
- professional limitations and follow-up requests.

The shared core must not become a generic user-facing workflow.

## Deterministic and judgment contract

Deterministic behavior is justified when correctness is mechanically
verifiable, reproducibility is required for auditability, or a fixed control
prevents unsafe promotion.

Use deterministic code for:

- stable-format parsing after an adapter is qualified;
- schema and contract validation;
- exact arithmetic;
- sampling from an explicit population and seed;
- explicit-key and reviewed-tolerance matching;
- duplicate, null, uniqueness, cardinality, fan-out, and reconciliation checks;
- hashing, receipts, file packaging, and output closure.

Use Codex and professional review for:

- source-role and document-meaning interpretation;
- ambiguous field mappings;
- evidence sufficiency;
- accounting, audit, legal, and tax relevance;
- materiality and tolerance selection;
- ambiguous matching;
- exception interpretation and narrative conclusions.

No deterministic classifier may promote a semantic judgment merely because it
finds a keyword, filename pattern, numeric coincidence, or positional
heuristic.

## M1-M7 capability migration

### M1: precision and abstention

Adopt:

- explicit units and reported increments;
- precision-aware reconciliation;
- unsupported facts remain absent and visibly unavailable;
- positive and mutation-based negative tests.

Retain the Fastenal fixture only as an evaluation example.

### M2: reviewed preparation and reconciliation

Adopt:

- reviewed mappings as explicit inputs;
- reviewed source-value vocabularies where categorical labels carry
  source-specific accounting meaning, such as debit/credit polarity;
- unmapped, duplicate, sign, period, unit, and scope controls;
- exact identities and tie-outs;
- prepared-evidence manifests.

Do not reuse the WD-40 chart of accounts or synthetic statement as a universal
model.

### M3: assurance kernel

Adopt and distill:

- exact Decimal and canonical JSON primitives;
- artifact, source, and reviewed-decision receipts;
- reference closure;
- explicit lineage levels;
- independent validation, preparation, reconciliation, semantic, downstream,
  and publication statuses;
- deterministic replay;
- representation of genuine failed or blocked runs.

Do not import `clara.preparation_audit_envelope.*` or the full Clara validator.
Vera receives a smaller package-neutral contract proven by its own workflows.

### M4: output evidence closure

Adopt:

- exact prepared-value to rendered-value addresses;
- source-bound numeric evidence ledgers;
- fresh-build verification before a report can be ready for review;
- separate reporting and publication status.

Do not import the WD-40 168-cell HTML-specific implementation.

### M5: reviewed formulas and unexplained residuals

Adopt:

- reviewed calculation perimeter and sign conventions;
- source-bound translation of non-canonical polarity labels rather than a
  universal debit/credit convention;
- exact aggregation, de-cumulation, ratios, and residuals;
- residuals remain explicit rather than being allocated or forced to zero;
- forbidden-inference tests.

Customer concentration remains a Clara Commercial DD slice. Working-capital
and financial tie-out patterns may be used by Vera when the workflow requires
them.

### M6: real-source eligibility

Adopt:

- pre-parser source qualification;
- explicit row grain and posting identity;
- source-owned monetary roles;
- one-to-one locators and complete monetary-field disposition;
- `unsupported_source_layout` distinct from parser failure;
- no prepared facts, reconciliation success, or report when qualification
  fails.

Do not import the bounded experimental parser or Clara's per-file consent
ceremony. Ordinary in-scope Vera work follows Vera's existing account and
privacy boundary.

### M7: promotion discipline only

Adopt the principle that capability claims require completed representative
cases, retained regressions, privacy validation, package checks, and resolved
scope decisions.

Do not design or implement an orchestrator as part of this program.

### Selective workflow application

The M1-M7 migration is not a requirement to force every mechanism into every
workflow. Each mechanism must close a real assurance risk in that workflow.
The target application is:

| Capability | Vera application |
| --- | --- |
| M1 precision and abstention | All six workflows use exact material values and visibly withhold unsupported or unresolved facts. Journal Sampling additionally preserves the source-reported increment. |
| M2 reviewed preparation | Journal and bank field mappings, source roles, parties, currencies, periods, signs, numeric measures, and plan/support roles become explicit reviewed inputs before deterministic execution. |
| M3 assurance kernel | Journal Sampling, Check Entries, Journal-Bank, and Concordato use replayable assurance envelopes. Audit Reconciliation and Report Builder retain their narrower workflow contracts while reusing package-neutral receipts, qualifications, ledgers, and independent readiness controls. |
| M4 output closure | Report Builder proves every reported material number through source, prepared, XLSX, Markdown, and DOCX addresses. Other workflows bind their material workpaper values and native review outputs where those values are rendered. |
| M5 reviewed calculations | Audit Reconciliation and Journal-Bank preserve allocations and residuals; Check Entries preserves direction and differences; Concordato preserves reviewed formula/sign boundaries and unsupported semantic conclusions; Report Builder binds unit, scale, sign, period, cell selection, and rendered totals. It is not useful to add de-cumulation or ratio machinery to Journal Sampling without a case that needs it. |
| M6 real-source eligibility | Source-derived rows require bounded qualification or an exact reviewed source contract. Stable byte capture alone does not make an ambiguous table semantically eligible. |
| M7 promotion discipline | Every workflow requires independent positive cases, adversarial mutations, retained regressions, privacy validation, and release checks before its claim is promoted. |

The advanced controls are part of that migration, not optional shorthand.
Where applicable, Vera must preserve:

- a reviewed effective recipe or relationship perimeter as an exact input;
- separate source, decision, implementation, prepared-output, and rendered-
  output receipts;
- fresh replay from current bytes rather than trust in a previously valid
  status;
- transitive implementation coverage for every parser, arithmetic,
  serialization, renderer, and closure module that can affect authority;
- re-derivation of material and deterministic presentation outputs so changing
  a value and recomputing its surrounding self-hashes cannot manufacture
  authority;
- complete declared output sets, with unexpected or missing artifacts failing
  closed;
- exact prepared-to-native-output addresses for material values;
- genuine blocked and failed states without success-shaped fallback artifacts;
- mutation tests that fail at the intended gate; and
- forbidden-inference and unexplained-residual records that prevent mechanical
  execution from silently becoming professional interpretation.

These controls are still selective. For example, de-cumulation belongs in a
Vera workflow only when a reviewed cumulative-to-period calculation is actually
required. Customer-concentration interpretation remains a Clara Commercial DD
capability, while exact aggregation, reviewed formulas, residual preservation,
and evidence closure are reusable assurance patterns.

This matrix is an acceptance map, not evidence of completion. V5 evaluation
and the final requirement audit determine whether each applicable migration
has actually passed.

## Core contracts

### Source qualification

Every prepared dataset records:

- `adapter_id`;
- `adapter_version`;
- `source_family`;
- `status`: `qualified`, `needs_review`, or
  `unsupported_source_layout`;
- exact source receipts;
- required-field and ownership checks;
- row and monetary-field counts;
- limitations and evidence references;
- reviewed mapping receipt when judgment was required.

Mapped categorical fields are not qualified merely because their column is
known. When source values have workflow-specific meaning, the reviewed mapping
must also bind the complete observed value vocabulary to canonical values.
Unknown labels, incomplete vocabularies, or a category that conflicts with a
mechanically verifiable signed amount withhold the source; code must not infer a
universal accounting convention from labels such as `debit` and `credit`.

Only `qualified` sources may emit prepared facts. `needs_review` is not a
partial success.

Any parser change that expands or reinterprets eligible source values must
increment the bounded adapter identifier or version. Existing reviewed mapping
receipts then become stale; a code change cannot silently broaden what an old
professional decision authorized.

### Independent assurance gates

The shared status model keeps these dimensions independent:

- source qualification;
- preparation;
- reconciliation;
- semantic review;
- reporting;
- publication.

A downstream status cannot promote an upstream failure. A blocked or failed
run remains representable and auditable.

### Numeric evidence ledger

Every material reported number records:

- source artifact and locator;
- prepared artifact and locator;
- canonical Decimal value, unit, and currency where applicable;
- reviewed calculation or mapping reference;
- output artifact and locator;
- comparison result;
- limitations.

The ledger proves numeric transport. It does not prove the professional
interpretation or conclusion.

### Review-output transaction

A save or apply operation that can change an existing review output must use a
bounded transaction:

- capture the canonical output tree from trusted parent code into memory before
  invoking any workflow helper;
- reject unsupported file types, links, duplicate paths, unexpected hard
  links, and configured file-count or byte limits before mutation;
- execute helper code only against a private staging tree;
- derive the operative review payload, run intake, current decisions, and final
  artifact state from the trusted persisted tree; any caller-supplied object
  must close exactly to that state and cannot expand actions or write targets;
- authorize an explicit output write set and, where the workflow emits a
  package, validate the whole staged tree before commit;
- independently reconstruct and verify the helper result, reviewed-decision
  receipt, declared effects, and current output receipts;
- replace the canonical tree only after every postcondition passes;
- restore the trusted in-memory bytes and file/directory modes exactly after
  any rejected commit, without trusting a sibling snapshot that helper code can
  modify;
- remove all still-resolvable bounded staging and recovery material on every
  success and failure path; and
- return fixed, path-free public failures while retaining local diagnostic
  detail outside the review payload.

This contract protects Vera's canonical review outputs from a failed,
misreported, or directly mutating workflow helper. It is not an operating
system sandbox: the helper and any other same-user process can access paths
outside the staging tree, copy data elsewhere, or relocate transaction
material beyond the paths known to the parent. The transaction must restore the
canonical output tree from trusted memory and clean every bounded location it
can still identify, but it cannot prove deletion of arbitrary external copies
or relocations. The release claim must state that limitation rather than
treating transaction validation as process isolation.

## Generalization evaluation standard

A parser, adapter, or procedure is not described as general merely because it
has configurable column names or multilingual labels.

Promotion requires:

1. at least two independent positive source examples for every claimed source
   family;
2. at least one positive example not used while implementing that adapter;
3. negative fixtures for missing identity, ambiguous amount ownership,
   duplicate keys, mixed units, sign ambiguity, shifted columns, and truncated
   populations where applicable;
4. a frozen machine-readable product contract supplied to the oracle author
   before case authoring, covering eligible inputs, adapter and relationship
   versions, canonical schemas, stage predicates, native outputs, gates,
   readiness, and the exact repeatability surface;
5. a concordance audit proving that the hidden oracle did not redefine that
   product contract;
6. exact expected normalized rows or an independent line-level oracle;
7. deterministic repeated output for the artifacts named by the contract,
   excluding intentionally run-scoped identities and timestamps;
8. no plausible prepared rows from an unsupported negative source;
9. workflow-level output and review-contract validation;
10. privacy and Marketplace package validation.

Synthetic tests remain useful but cannot alone establish source-family
generality.

## Privacy and external boundaries

The redesign introduces no new external recipient or service. Real case data
may enter Codex context under Vera's existing account boundary. Shared
assurance code processes local inputs and outputs.

Each changed workstream must register the shared assurance implementation in
`governed_shared_paths`, refresh its source fingerprint, and pass the complete
Vera privacy-surface validator before packaging.

## Milestones

### V0 - Inventory and frozen baseline

- inventory case-specific assumptions, duplicated utilities, monetary types,
  parser claims, and test coverage;
- record the focused pre-change regression baseline;
- freeze this architecture and migration contract.

### V1 - Shared assurance primitives

- implement package-neutral exact money and canonical serialization;
- implement artifact receipts and independent status validation;
- implement source-qualification records;
- implement reviewed-decision receipts and stale-decision rejection;
- implement procedure relationship and conservation controls;
- implement replayable assurance-envelope validation;
- implement numeric evidence-ledger validation;
- implement bounded trusted-memory review-output transactions;
- add adversarial unit tests;
- vendor the shared implementation into the Vera package.

### V2 - Journal Sampling hardening

- replace float monetary parsing;
- make source qualification precede normalization;
- disable unqualified positional PDF reconstruction;
- distinguish unsupported layout from parser failure;
- add positive and negative source-family fixtures;
- preserve deterministic sampling only over a qualified population.

### V3 - Audit Reconciliation hardening

- remove case-origin vocabulary from reusable rules;
- make source-role inference a proposal rather than authority;
- qualify journal and ledger layouts before row-level use;
- replace positional debit/credit ownership;
- add party, currency, evidence-reuse, fan-out, and allocation-conservation
  checks;
- make pending or failed required review block final readiness;
- preserve partial evidence without promoting unsupported sources;
- bind workpapers and review artifacts to source receipts.

### V4 - Remaining accounting workflows

- migrate Check Entries and Journal-Bank Reconciliation to exact money and
  qualified canonical evidence;
- remove sole-document auto-matching, row-index surrogate matching, generic
  description-token references, and unreviewed amount-only matches;
- require an explicit relationship policy for grouped, split, or reused
  evidence;
- migrate Concordato Plan Review candidate arithmetic to exact money;
- add Report Builder numeric evidence ledgers and fresh-output closure;
- preserve semantic review as Codex and professional judgment.

### V5 - Representative evaluation and release

- run independent cross-case and adversarial evaluations;
- run focused and full repository tests and coverage;
- validate all affected privacy surfaces;
- run plugin interaction, review-contract, and Marketplace package checks;
- rebuild only the Marketplace-ready Vera package;
- complete a requirement-by-requirement audit before declaring the goal done.

## Completion criteria

The program is complete only when:

1. all six workflows use exact money for material calculations and comparisons;
2. any source-derived prepared rows come from a qualified adapter;
3. unsupported layouts cannot produce plausible prepared facts;
4. case-origin assumptions have been removed or explicitly scoped to a named
   adapter;
5. shared assurance primitives replace duplicated implementations where they
   are genuinely common;
6. every material Report Builder number has source, prepared, and output
   closure;
7. independent gate statuses prevent downstream promotion;
8. representative holdout and adversarial cases pass;
9. review artifacts and professional judgment boundaries remain intact;
10. rejected review-output mutations restore exact canonical bytes and modes
    without trusting child-accessible rollback material;
11. privacy, regression, release, and Marketplace package checks pass.
