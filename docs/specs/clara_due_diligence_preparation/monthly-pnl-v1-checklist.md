# Monthly P&L v1 implementation checklist

Status: M1 complete
Parent plan: [Clara due-diligence preparation plan](./clara-due-diligence-preparation.md)

## M1 — Pinned public truth

- [x] Select a company with independently published monthly and quarterly facts.
- [x] Record the semantic limitation: Fastenal publishes monthly net sales, not
  a monthly full P&L.
- [x] Pin source URLs, dates, identifiers, byte counts, and SHA-256 receipts.
- [x] Store the three monthly sales facts as exact Decimal values with declared
  units and reported increments.
- [x] Store the Q1 statement facts, XBRL concepts, context, and disclosed
  precision.
- [x] Reconcile monthly sales to quarterly sales with a rounding-interval
  contract.
- [x] Verify quarterly gross profit, operating income, pretax income, and net
  income identities.
- [x] Verify that undisclosed monthly P&L lines contain no facts.
- [x] Emit a deterministic validation report.
- [x] Add clean, malformed-contract, and one-error-at-a-time adversarial tests.
- [x] Keep all automated tests offline.
- [x] Rebuild and verify the Clara plugin package.

## M1 definition of done

- The fixture is immutable unless its pinned digest is deliberately updated.
- Three monthly net-sales facts sum to USD 1,959,429,000.
- The published quarterly net-sales midpoint is USD 1,959,400,000.
- Reconciliation passes only because the disclosed rounding intervals overlap.
- Every quarterly statement identity has zero difference.
- Monthly cost of sales, gross profit, SG&A, operating income, interest, tax,
  and net income are explicitly `not_disclosed`.
- Adding an invented monthly expense fact fails the abstention gate.
- Missing a month, exceeding the rounding interval, breaking a statement
  identity, or corrupting provenance fails before anything is report-ready.
- Passing M1 records a benchmark result, not downstream report readiness;
  render compatibility and evidence sealing remain later gates.

## M2 preview — Synthetic monthly trial balance

M2 will add the actual preparation slice:

- frozen monthly trial balance with exact integer or Decimal amounts;
- reviewed chart-of-accounts mapping with scope, sign, effective dates,
  evidence, version, digest, and status;
- exact account-to-line aggregation and statement formulas;
- `monthly_pnl.csv`;
- `unmapped_accounts.csv`;
- `reconciliation.json`;
- `prepared_evidence_manifest.json`;
- clean and adversarial fixture variants;
- `statement.pnl_table` render proof;
- `clara.evidence_bundle.v1` sealing proof.

The statement renderer will consume prepared values. It will not own account
mapping, authoritative arithmetic, period interpretation, or reconciliation.
