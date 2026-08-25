# Vera audit assurance representative evaluation plan

Status: active; source candidates are not promotion evidence until executed and
recorded in `representative-evaluation-log.md`.

This plan operationalizes M7 without introducing an orchestrator. A case proves
only the mechanical capability named in its claim. Public accounting data,
official examples, and generated layouts do not by themselves prove source
authenticity, audit-evidence sufficiency, or a professional conclusion.

## Promotion protocol

For every claimed source family:

1. use at least two independent positive sources;
2. keep at least one positive source blind until implementation is frozen;
3. give the oracle author a frozen machine-readable copy of the existing
   product contract: eligible inputs, adapter and relationship versions,
   canonical schemas, stage predicates, native output structure, gate and
   readiness rules, and the exact artifacts that must repeat byte for byte;
4. require the oracle to conform to that product contract and audit
   concordance before treating any mismatch as an implementation defect;
5. seal the expected result independently of the workflow output;
6. record source URL or private source reference, retrieval time, SHA-256,
   rights/privacy treatment, oracle author, and holdout status;
7. run in two independent output directories and compare the contract's
   deterministic artifacts byte for byte while keeping intentionally
   run-scoped IDs and timestamps outside that equality claim;
8. run applicable negatives for missing identity, ambiguous amount ownership,
   duplicate keys, mixed units, sign ambiguity, shifted columns, source
   mutation, and truncation;
9. require zero plausible prepared rows from an unsupported source;
10. validate exact Decimal values, locators, source and implementation receipts,
   gates, residuals, and rendered values;
11. keep semantic and professional conclusions pending after mechanical success;
12. retain no private or rights-restricted raw source in the repository or
    Marketplace package.

An abstention is a passing result when the source does not meet the declared
adapter contract.

## Minimum case matrix

| Workflow | Positive case A | Positive case B / holdout | Mechanical claim | Required negatives |
| --- | --- | --- | --- | --- |
| Journal Sampling | Reviewed 200-row slice of the [Connecticut Open Expenditures Ledger](https://data.ct.gov/resource/jz5u-r6jf.csv?$limit=200) | Reviewed 200-row slice of [San Francisco Vendor Payments](https://catalog.data.gov/dataset/vendor-payments-purchase-order-summary), selected after the first implementation pass; plus the existing private native-journal holdout | Bounded flat-table qualification, full monetary-field disposition, exact normalization, stable row identity, reproducible sampling | Ambiguous amount ownership, missing posting identity, mixed units, shifted columns, truncation, multi-sheet ambiguity, generic PDF |
| Open-item Reconciliation | Rights-cleared public expenditure slice split into independently sealed open-item and payment views | A second public transaction population selected after implementation freeze | Reviewed source roles, one-to-one evidence use, exact residuals, party/currency controls, final-readiness blocking | Ambiguous roles, duplicate or reused evidence, fan-out, party mismatch, cross-currency allocation, truncation |
| Check Entries | Official illustrative FatturaPA XML from [Docs Italia](https://docs.italia.it/italia/18app/18app-esercenti-docs/it/bozza/linee-guida-fatturazione.html), paired with a separately sealed Journal Sampling entry | Fresh fictitious multi-line FatturaPA example authored independently from the implementation | Upstream-envelope replay, strong invoice identity, exact money, one-support-per-entry control | Deleted or stale upstream envelope, amount/date-only coincidence, wrong parties, currency mismatch, support reuse, unrelated sole PDF |
| Journal–Bank | Fictitious bank CSV following one published bank export layout, paired with a public transaction slice | A different published bank CSV layout selected blind | Bounded v6 source adapters, receipt-bound day/month convention, LF/CRLF/CR transport equivalence, stable identities, source-bound direction vocabularies, explicit-reference or reviewed relationship matching, exact residuals, one-to-one use, and all-row native material-value closure | Ambiguous or unsupported CSV field delimiter, field-delimiter/numeric-separator confusion, stale v5 mapping receipt, mutated date convention, ambiguous or invalid populated date, incomplete or changed potential-monetary-column disposition, malformed or truncated record beyond the delimiter profile, missing date and reference, duplicate amount/date candidates, generic description token, evidence reuse, cross-currency, unmapped or sign-conflicting direction values, second-row/cell output mutation, source mutation |
| Report Builder | Compact facts derived from one official [SEC Financial Statement Data Set](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets), checked against the related filing | A second issuer from another filing/quarter, selected blind | Stable source capture, exact source-to-prepared-to-XLSX/Markdown/DOCX closure, fresh output, duplicate-name isolation | Source mutation, changed unit/scale/period, duplicate table identity, missing fact, tampered rendered value, scanned PDF |
| Concordato Preventivo Review | Fictitious direct-continuity case with multiple creditor classes, reviewed document roles, treatment, liquidation comparator, sources and uses, and liquidity bridge | Independently authored liquidation, indirect-continuity, and mixed cases; then one previously unseen real case reviewed by a qualified professional. The historical bounded EVIVA pages remain diagnostic evidence only | Source-bound procedure and document model; creditor and class treatment; exact plan-versus-liquidation, sources-and-uses, and liquidity calculations; replayable evidence and explicit withholding of legal or feasibility conclusions | Missing attestation or creditor evidence, equal amounts in unrelated contexts, one-cent difference, imbalance, broken cash bridge, stale source receipt, unsupported priority/class/treatment, prospective assumption presented as historical |

## Rights and privacy boundaries

- The Oklahoma catalog describes the dataset as public and links a CC-BY
  license. Confirm the exact attribution text before retaining or
  redistributing a slice.
- SEC financial-statement datasets reproduce registrant-filed structured data
  and carry an accuracy disclaimer. Retain only compact accession-specific
  facts with source attribution; do not imply SEC endorsement.
- The Docs Italia page contains an explicitly illustrative FatturaPA XML.
  Prefer fictitious identifiers in retained derivatives.
- Published bank-layout documentation is reference material only. Do not
  package the documentation or a real customer statement; generate wholly
  fictitious CSVs that exercise the documented fields.
- Private holdouts remain outside the repository. The log may retain only
  anonymous labels, hashes, counts, outcomes, and non-identifying failure
  classes.

## Current blockers

- The exact external handoffs are ready in
  `journal-bank-v6-holdout-commission.md` and
  `concordato-full-population-review-commission.md`. Completing those packets
  requires people and custody channels independent of this implementation
  process; the templates themselves are not evaluation evidence.
- Check Entries and Report Builder have completed their recorded remediation
  and independent current-tree reruns. Their bounded transaction and successor
  claims do not authenticate an external reviewer or independently retained
  historical checkpoint.
- Journal–Bank r3 is mechanical regression `GO`, not representative promotion
  evidence. The sealed v7 holdout remains immutable `NO-GO`. A later
  independently authored v5-contract successor completed the full sealed
  protocol and scored 23/24: it exposed a genuine stale source-outcome defect
  under mid-run source-membership change. The defect is remediated and its
  post-exposure replay passes, but that replay is diagnostic evidence only. M7
  remains `NO-GO` until a new unseen v6 holdout is authored independently from
  the exact bytes of
  `journal-bank-evaluation-contract.v5.json` (SHA-256
  `4824652ecdb990a844fd9b72d799a2537f46a21ddb9fefb8a664f828c0ec6657`).
  The prior v2/Aurora, v3/v5, v4, adjudicated r3, exposed v7, and sealed
  23/24 successor evidence remain immutable history and must not be
  retrofitted or relabelled as a passing holdout.
- A private monthly bank export and corresponding ledger provide
  non-promotional real-source evidence. The initial adapter-v6 diagnostic
  correctly withheld the bank population because localized textual-month dates
  were outside the frozen v5 contract. A separate additive adapter-v7 contract
  is now frozen and implemented without changing v6. With a current
  reviewer-bound Italian locale and exact non-movement summary authority, the
  private rerun qualified 202 bank and all 8,141 journal movements, produced 36
  deterministic candidate matches, retained 8,343 relationship residual rows,
  replayed 83,826 material-value addresses, and kept reconciliation, semantic,
  reporting, and publication authority withheld. The complete 318-case
  Journal–Bank file passes with Node-backed cases enabled and no skips. This remains exposed
  diagnostic evidence, not v5 or v7 promotion; the sibling statements cannot
  serve as an independent holdout for either contract.
- Concordato Preventivo Review now has a reusable semantic contract and
  synthetic coverage across direct continuity, indirect continuity,
  liquidation, and mixed plans. Historical bounded real-PDF evidence from an
  EVIVA plan, attester's report, and judicial commissioners' report remains
  useful only as a numerical diagnostic. It does not validate the semantic
  capability. Promotion still requires one previously unseen complete case
  modeled and adjudicated by a qualified independent reviewer.
- The repository collection and runtime import boundaries are repaired in test
  code. At the earlier source state, the eight previously classified
  production or source-contract defects were remediated and an uncapped
  7,373-test traversal reached 80.32% `src` coverage; the subsequent regression
  recorded 7,364 passes and 9 dependency-gated skips. Those results are
  historical, not current proof. On the 2026-07-26 remediation state, clean
  collection succeeds for 7,398 tests, while a repository-wide runtime attempt
  was stopped at 22% after 31 unrelated baseline failures. Current closure
  therefore rests on the complete Vera workflow, cross-workflow, privacy, and
  clean release gates, not on a claimed green repository-wide traversal.
- Privacy, full-regression, interaction, release, and Marketplace-package
  checks remain V5 requirements after case execution.
