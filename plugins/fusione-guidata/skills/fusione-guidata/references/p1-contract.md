# P1 request and output contract

Use existing `init`, `apply`, `show`, `export` and P0 `demo`. `demo-p1 --output`
adds two synthetic end-to-end examples. All normal writes require the declared
actor, the exact case and expected revision. The helper makes no network calls.

## Archive actions

`apply` request fields besides `action`:

| Action | Fields |
|---|---|
| `bind_archive` | `object_id`, `entity_id`, absolute `client_root`, exact `client_id`, `engagement_id`, `expected_version` |
| `import_archive` | `object_id`, exact `binding` reference, selected `input_id`, `locator`, `description`, `expected_version` |
| `workpaper` | `object_id`, `kind`, `request`, `expected_version` |

A binding requires case administrator access and an allowed company source root.
The actual Studio Archive ledger verifies the client, open engagement and sealed
receipt. Imports copy only the selected immutable input. Their evidence record
retains client/engagement/input IDs, receipt digest, source digest, paths and bytes.
No other archive is discovered and no source engagement is modified.

## References and facts

`ref` below always means the full `operation_id`, `id`, `version`, `sha256` object
returned by `show`. `decimal`, `date`, `text`, `boolean` and `fraction` below mean
references to known Facts of those kinds, **not inline values**. Facts require
actual Evidence. Record unknown/disputed values as null through ordinary `put`.

A workpaper collects all exact references selected in its request and always
references the current Operation. This mechanically captures selected inputs;
it cannot discover a semantically omitted document. Reads, calculation and write
occur in one SQLite transaction. Unavailable facts/dependencies produce a persisted
blocked result with `result: null`; incompatible shapes fail without a partial
record. Derived P1 records cannot be forged with generic `put`.

All P1 data has `engine_version: fusione.p1.v1`, the immutable `request`, computed
`result`, and explicit `issues`. Result existence is not approval. ChangeImpact
and current status determine whether an earlier confirmation remains effective.
Rules and selected P1 branches require their own exact professional confirmation.
LegalDocument approval also requires reviewed upstream workpapers. The live planned
date must fall inside each selected rule's explicitly declared applicable period;
this tests that declaration, not whether the legal interpretation was correct.

## Workpaper kinds

### BranchDecision

- `branch`: `ordinary_domestic_oic` or `wholly_owned_domestic_oic`.
- `acquirer`, `target`: two distinct Entity refs, explicitly coded IT/OIC.
- `assumptions`: boolean Fact refs named `domestic_oic`, `incorporation`,
  `homogeneous_rights`, `no_cash_adjustment`, `no_own_or_reciprocal_holdings`,
  `no_mlbo`, `no_special_regulated_or_crisis_case`.
- `ownership`: fraction Fact, respectively `0/1` or `1/1`.
- `ownership_edge`: null for independent companies; otherwise the exact
  OwnershipEdge with acquirer as holder, target as company and ratio `1/1`.
- `rationale`: text Fact; `rules`: nonempty list of exact RuleVersion refs.

Legacy P0 BranchDecision proposals remain unsupported and are not promoted.
The declaration does not replace the model/professional's legal classification.

### Valuation

`plan` (P1 BranchDecision ref), `company` (Entity ref), `basis` (`equity` or
`enterprise`), `value` (positive decimal), `debt`, `cash`, `adjustments`, `method`
(text), `valuation_date` (date). Equity basis requires the three bridge fields to
be null. Enterprise basis requires each explicitly, with nonnegative debt/cash
and signed adjustments. Result: base − debt + cash + adjustments. Nonpositive
result blocks the simple exchange model. This does not perform a valuation.

### ExchangeModel

`plan`, `valuation_a`, `valuation_b`, `units_a`, `units_b`, `nominal`, `unit_type`
(`shares` or explicitly defined `capital_units`), `shareholders_a`, `shareholders_b`,
`allocation_policy` (text). Each shareholder is `{id, name: text, units: decimal}`;
every company's rows reconcile to its total. Valuations must match plan, companies
and dates. Independent exchange retains exact ratios and owner allocations.

For wholly owned incorporation, both valuations and `units_b` are null, and
`shareholders_b` is empty: there is no exchange for the cancelled holding.
Acquirer owner rows remain. `shares` counts must be whole; fractional results are
retained but block approval until a dedicated allocation is implemented. Capital
units preserve exact fractions and are not described as Srl shares. No cash
adjustment, hidden rounding or congruity approval is generated.

### BookBridge

`plan`, `exchange`, `balances_a`, `balances_b`, `date_a`, `date_b` (same reviewed
date), `investment_account` (acquirer account ID for wholly owned, otherwise null),
`eliminations`, `difference_allocations`, `accounting_policy` (text), `tax_register`.

Balance and allocation rows are `{id, label, category, balance: decimal}` with
category `asset|liability|equity`, signed debit-positive/credit-negative amounts.
Both source trial balances must sum to zero. Closed profit/loss and prior
adjustments must already be reflected in the professionally mapped balance sheet.

An elimination is `{a: account_id, b: account_id, eligible: boolean}`. It uses
each account once, matches an asset and liability, and requires opposite equal
amounts plus the declared eligible treatment. Any discrepancy remains uneliminated
and blocks approval. The code does not infer intercompany identity or legal rights.

The bridge drops target equity, cancels the selected participation or adds the
exchange capital, then exposes the resulting signed difference. Explicit reviewed
allocation rows must sum to it. Without them, an unallocated workpaper line remains
and approval is blocked; no automatic goodwill. Opening balances must reconcile.

`tax_register` rows are `{id, owner: text, category, book: decimal, tax: decimal,
assessment: text}`. Category is `asset|liability|shareholder_cost|reserve|loss`.
These preserve professionally supplied values; no tax treatment, tax neutrality,
loss availability or deferred-tax rate is calculated or approved by the helper.

### Deadline

`plan`, nonempty `events`, `computation_policy` (text). Each event is:

`{id, label, anchors: [date refs], count: integer, unit: days|months, rule: RuleVersion ref,
owner: text, actual: date ref|null, constraint: not_before|not_after,
adjusted_boundary: date ref|null, adjustment_reason: text ref|null}`.

The model selects every relevant anchor; code takes the latest of that selected
population. Positive day offsets exclude the anchor day. Calendar months clamp
to the destination month's final valid day, rather than using 30-day multiples.
Offsets are limited to ±1200 units. An optional explicit professional adjustment
preserves both raw and adjusted dates. No holiday, waiver or reduction is inferred.
Missing actual evidence is `not_evidenced`. An outside-boundary actual date blocks
approval. Passing the computation never permits signing, filing or execution.

### LegalDocument

`plan`, `exchange`, `bridge`, `calendar`, `title` (plain text), `sections` (text
Fact refs named below). All workpapers must use the same exact plan and exchange.

Sections: `mandate`, `objectives`, `due_diligence`, `feasibility`, `articles`,
`profit_participation`, `accounting_effective_date`, `special_rights`,
`management_advantages`, `tax_review`, `execution_checklist`, `cutover`,
`post_merger_checks`. The model writes case-specific prose from acquired evidence;
code does not judge its legal sufficiency. The result combines these sections with
calculated workpapers. Signature/filing are not performed; legal effect is unverified.

## Inspecting the examples

Each `demo-p1` branch directory contains `plan-request.json`, valuation requests
where relevant, `exchange-request.json`, `bridge-request.json`, `calendar-request.json`
and `dossier-request.json`, alongside the synthetic case and source archives.
They show complete request shapes with actual valid references for that demo case.
They are examples, not reusable identities for another client or an instruction
to invent professional confirmations. `show --id <id>` returns record and status.
`export --output <fresh-directory>` produces scoped JSON history, Markdown/HTML
P1 workpapers and the canonical readable model-data report.

The accounting result includes `opening_journal`: target asset/liability assumption, reciprocal eliminations, consideration and reviewed difference allocations. These draft entries transform the acquirer ledger into `opening_balances`; `journal_residual` and `opening_residual` must both be zero. No entry is posted to an accounting system.
