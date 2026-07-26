# Vera audit and reconciliation assurance implementation checklist

Status: active

The authoritative scope and acceptance criteria are in
`vera-audit-assurance-redesign.md`.

## V0 - Inventory and baseline

- [x] Inspect Vera workflow routing and professional boundary.
- [x] Inspect the six module workflow contracts.
- [x] Inspect Clara M1-M7 scope and reusable controls.
- [x] Identify unsafe journal amount/side reconstruction paths.
- [x] Identify binary-float monetary paths.
- [x] Identify case-origin Audit Reconciliation terminology.
- [x] Run the focused pre-change accounting-workflow regression suite.
- [x] Complete module-by-module duplication and test-coverage inventory.
- [x] Record the final migration matrix.

## V1 - Shared assurance primitives

- [x] Add the package-neutral shared module.
- [x] Add canonical Decimal parsing and serialization.
- [x] Add stable canonical JSON and local artifact receipts.
- [x] Add source-qualification contract and validator.
- [x] Add independent gate-status contract and validator.
- [x] Add numeric evidence-ledger contract and validator.
- [x] Add reviewed-decision receipts and stale-decision rejection.
- [x] Add relationship, evidence-reuse, and allocation-conservation controls.
- [x] Add replayable assurance-envelope validation.
- [x] Add initial positive and adversarial unit tests.
- [x] Add Vera package vendor configuration.
- [x] Add bounded trusted-memory review-output transactions to every changed
  save/apply surface and prove exact rollback under hostile mutation.

An independent read-only audit on 2026-07-25 executed 42 hostile and control
cases plus a separate seven-case black-box replay. The five original forged or
stale-authority exploits and forged child path/effect cases were rejected;
canonical tree bytes and modes, an external sentinel, and zero transaction
residue all closed exactly. This is bounded rollback and authorization, not an
operating-system sandbox: same-user helper code can still copy or mutate
unrelated external paths, and a background descendant can act after return.

## V2 - Journal Sampling

- [x] Replace binary-float monetary parsing.
- [x] Require source qualification before normalization.
- [x] Remove automatic generic text-PDF amount/side assignment.
- [x] Make print-friendly layouts bounded source-family adapters.
- [x] Add unsupported-layout diagnostics and review payload coverage.
- [x] Add independent holdout and negative fixtures.
- [x] Prove sampling only uses a qualified complete population.

Representative evidence is recorded in
`representative-evaluation-log.md`. One native 4,406-row monetary population
qualified after reviewed mapping; four structurally different exports
abstained without emitting rows. Two unrelated official 200-row flat payment
populations also qualified only after complete reviewed mappings, reproduced
byte-identical normalized and systematic-sample CSVs, and blocked undisposed
numeric fields, invalid units, and changed source bytes. These public cases
validate bounded transport and sampling mechanics, not double-entry completeness
or professional sample-design judgment.

## V3 - Audit Reconciliation

- [x] Remove or explicitly scope `All.A` case vocabulary.
- [x] Make filename/source-role classification advisory.
- [x] Require reviewed source-role mapping where ambiguous.
- [x] Remove positional midpoint debit/credit ownership.
- [x] Qualify journal/ledger rows before reconciliation.
- [x] Enforce entity, party, and currency compatibility.
- [x] Enforce evidence-use uniqueness, fan-out, and allocation conservation.
- [x] Make failed checks or pending required review block final readiness.
- [x] Preserve unsupported evidence as partial without row-level promotion.
- [x] Bind workpapers and review artifacts to source receipts.
- [x] Add independent holdout and negative fixtures.
- [x] Add the exact 25-file successor boundary, external predecessor
  checkpoint, deterministic predecessor replay, and browser/Python/MCP
  enforcement; pass 308 scoped tests and a separate 32-attack root re-audit.

## V4 - Remaining workflows

- [x] Close Journal Sampling review successors with exact predecessor archives,
  stage-chain replay, physical file/directory/mode equality, and freshly
  rederived non-final review gates; pass the 160-test root re-audit.
- [x] Migrate Check Entries to exact money and qualified journal evidence.
- [x] Close Check Entries initial/transition/successor physical output equality,
  retain foreign-file/link/special-file and rollback attacks, and pass the
  fresh 189-test root re-audit.
- [x] Migrate Journal-Bank Reconciliation to exact money and qualified inputs.
- [x] Bind non-canonical Journal-Bank direction vocabularies to reviewed
  source-specific polarity mappings.
- [x] Make Journal-Bank one-to-one matching waves order-independent, keep the
  later-singleton stage reachable, invalidate old relationship receipts, and
  stabilize native workbook bytes.
- [x] Freeze a machine-readable Journal-Bank evaluation contract before
  commissioning the successor blind oracle.
- [x] Add the Journal-Bank tabular v5 CSV transport contract: bounded
  comma/semicolon/tab/pipe profiling, separate field and numeric separators,
  mechanical LF/CRLF/CR normalization, strict full-file parsing, and zero-row
  abstention for ambiguity, unsupported delimiters, or parser failure.
- [x] Bind every reviewed Journal-Bank mapping to the exact current
  `potential_monetary_columns` and an explicit complete mapped-or-excluded
  disposition, including empty exclusion lists.
- [x] Freeze the row-free Journal-Bank v3 repository contract for adapter v5
  while retaining v2 as immutable historical evidence.
- [x] Replace parser-order date guessing with the Journal-Bank v6
  source-bound `day_first` / `month_first` authority contract; reject stale v5
  receipts, invalid populated dates, and partial mixed-validity emission.
- [x] Freeze the row-free Journal-Bank v4 repository contract with exact
  direction outcomes, monetary-token and stable-reference rules, condition
  outcomes, gate vocabulary, and independent semantic-oracle projections.
- [x] Freeze the prospective Journal-Bank v5 repository contract with explicit
  signed match presentation, non-negative matching/allocation magnitudes, and
  exact ambiguous/unsupported/parser-failure delimiter outcomes. Record r3 as
  mechanical regression `GO`, not M7 promotion.
- [x] Add native Journal-Bank relationship residuals plus all-row
  prepared-to-CSV/XLSX material-value addresses and fresh deterministic replay.
- [x] Execute and retain the sealed Journal-Bank v7 holdout as `NO-GO`;
  remediate its genuine blocked-output-set and direct source-outcome gaps
  without adopting non-contract hidden expectations. The exposed diagnostic is
  regression evidence only.
- [x] Execute a separately authored, sealed v5-contract successor with
  candidate/oracle isolation. Preserve its 23/24 `NO-GO`, remediate the genuine
  mid-run source-membership outcome inconsistency, and pass the focused replay
  plus the complete 300-test Journal-Bank file. The exposed replay remains
  regression evidence, not M7 promotion.
- [x] Run a private real-source Journal-Bank qualification diagnostic without
  retaining source or row data in the repository. The reviewed journal source
  qualifies all 8,141 candidates; the bank source correctly emits zero rows
  because localized textual-month dates are outside the frozen v5 contract.
  The 23-file blocked package and exact assurance receipts replay. Treat the
  source family as exposed diagnostic evidence, not an independent holdout.
- [x] Freeze and implement the additive `journal_bank.tabular.v7` contract
  without changing adapter v6. Bind full Italian textual-month parsing and
  exact blank-date/no-reference summary labels to a current mapping receipt;
  cover positive, invalid, mixed-language, stale-receipt, and structural
  non-override cases. On the private diagnostic, qualify 202 bank and 8,141
  journal movements, replay all 83,826 material-value addresses and 42
  assurance receipts, and keep reconciliation/reporting withheld for 166 bank
  plus 8,105 journal unmatched rows. Preserve the case as non-promotional
  evidence.
- [x] Migrate Concordato candidate arithmetic to exact money.
- [x] Close Concordato reviewed formula authority, exact 27-file
  implementation perimeter, all-row numeric-address ledger, physical output
  equality, review-successor chain, standalone replay, and rollback attacks;
  pass the fresh 104-test root re-audit.
- [x] Add Report Builder numeric evidence ledger with complete reviewed
  candidate-cell, sign, and formula dispositions.
- [x] Add Report Builder fresh-output and no-mutation-on-failure closure.
- [x] Close the Report Builder alternative-honest-predecessor substitution with
  an externally retained checkpoint, predecessor replay, Python/MCP
  enforcement, and a fresh 142-test full-file rerun.
- [x] Preserve workflow-specific review contracts and judgment boundaries.

Check Entries now replays the qualified Journal Sampling population and its
source, decision, normalized, implementation, and gate receipts; material
amounts, signed support, differences, and tolerances remain canonical Decimal
text through CSV, XLSX, the numeric ledger, and the assurance envelope.
The six isolated full workflow suites completed 1,239 cases without failures,
errors, or skips on 2026-07-26. Node-backed Journal–Bank cases were enabled.
The intended production topology is one CLI/MCP process per plugin;
same-interpreter source co-loading is not a supported execution contract. A
separate 248-case cross-workflow gate passed across shared assurance,
packaging, non-plotting workbench, interaction, payload-coverage,
review-contract, transaction-generator, demo, and visual-audit checks.

## V5 - Evaluation, privacy, and release

- [x] Write the representative evaluation and rights/privacy protocol.
- [x] Run shared-core unit and adversarial tests (50 passed on 2026-07-24).
- [ ] Complete the explicit M1-M7 advanced-control transfer audit:
  - [x] exact units, increments, precision, and abstention;
  - [x] reviewed effective recipes, mappings, and relationship perimeters;
  - [x] source, decision, implementation, prepared-output, and rendered-output
    receipts with fresh replay;
  - [x] complete output-set closure and exact material-value output addresses;
  - [x] independent gates and genuine blocked or failed runs;
  - [x] reviewed formula execution, exact residual preservation, and forbidden-
    inference tests;
  - [x] pre-parser source eligibility and zero plausible rows after
    qualification failure;
  - [ ] mutation failures pass, but Journal-Bank M7 remains `NO-GO` after the
    independently authored sealed successor scored 23/24 and exposed a now
    remediated source-membership outcome defect. The later additive-v7
    private-source diagnostic qualifies the complete reviewed date population
    and replays current outputs, but is still not blind promotion evidence for
    either v5 or v7. Concordato Preventivo now has a source-bound semantic
    case-model contract and representative synthetic plan-form tests, but no
    qualified independent reviewer has adjudicated that model on a previously
    unseen complete real case.
- [x] Run focused workflow regressions: six isolated full workflow suites
  passed 1,239/1,239 cases without failures, errors, or skips.
- [ ] Commission and execute a new independent unseen Journal-Bank v6 holdout
  from the frozen v5 contract and exact production schemas; do not retrofit the
  prior v2/Aurora, v3/v5, v4, adjudicated r3, exposed v7, or sealed 23/24
  successor evidence. The already exposed private localized-date source family
  is also ineligible for that role. The external handoff and acceptance
  protocol are ready in `journal-bank-v6-holdout-commission.md`; author,
  operator, evaluator, adjudicator, and private custody fields remain
  unassigned. M7 remains `NO-GO` until that successor passes.
- [ ] Commission and execute a separate independent unseen adapter-v7 holdout
  against the exact additive extension contract. Do not reuse the private
  localized-date source family or its sibling statements. Until it passes, v7
  has bounded implementation and diagnostic evidence but no representative
  promotion.
- [ ] Commission a qualified independent semantic Concordato Preventivo
  review on a previously unseen complete case. The reviewer must adjudicate
  procedure, document authority, creditor perimeter and treatment,
  plan-versus-liquidation basis, sources and uses, liquidity, feasibility
  evidence, and open issues—not only the historical numerical candidate
  population. Reviewer and custody fields remain unassigned.
- [ ] Re-establish the full repository runtime and coverage gate for the
  current source state. Clean importlib collection passes at 7,398 tests. A
  current runtime attempt was stopped at 22% after 31 unrelated baseline
  failures involving missing local fixtures, stale legacy-UI expectations,
  private permission-path leakage, and blocked local Postgres access. The
  historical 7,373-test/80.32% result remains evidence for its earlier source
  state only.
- [x] Refresh every changed Vera privacy-surface fingerprint.
- [x] Validate the complete Vera privacy register and 21 focused privacy tests.
- [x] Run plugin interaction and review-contract validators: 248 passed.
- [x] Run plugin release checks: 270 passed in a clean disposable release
  surface after version and published-manifest corrections.
- [x] Build and verify source-derived install and ChatGPT-upload archives with
  exact source-drift checks.
- [ ] Reconcile the pre-existing worktree archive state: the tracked install
  archive is deleted and an undeclared wrapped upload archive is present.
- [x] Complete the requirement-by-requirement completion audit in
  `completion-audit.md`; the strict program remains open on the independent M7
  evidence listed above.
