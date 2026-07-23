# Fastenal Q1 2025 public-truth case

This fixture is a reviewed, offline extraction of four official published
documents:

- Fastenal's January 2025 monthly information release;
- Fastenal's February 2025 monthly information release;
- Fastenal's March 2025 monthly information release;
- Fastenal's Q1 2025 Form 10-Q, accession `0000815556-25-000083`.

The three issuer releases disclose monthly net sales in USD thousands. The
fixture normalizes those values to USD millions, so one reported USD thousand
becomes an increment of `0.001` USD million. The Form 10-Q discloses the
complete quarterly income statement in USD millions with one decimal place.
The quarterly observations use the filing's Inline XBRL fact identifiers and
context `c-1`, covering 2025-01-01 through 2025-03-31.

## Reviewed boundary

This case proves:

- the extracted monthly net-sales values;
- the extracted quarterly statement values;
- exact arithmetic over normalized Decimal values;
- reconciliation within the combined disclosed rounding intervals;
- absence of evidence for monthly cost of sales, gross profit, SG&A, operating
  income, interest, tax, and net income.

It does not prove:

- a monthly full P&L;
- account-level balances or mappings;
- transaction-level revenue;
- customer, product, or channel profitability;
- the issuer's internal trial balance, consolidation, or eliminations;
- independent extraction from the remote documents during test execution.

The source documents are not redistributed with the plugin. `benchmark.json`
records the exact remote byte count and SHA-256 observed on 2026-07-23. Tests
run only from the frozen fact files and do not contact the issuer or SEC.
