# WD-40 FY2025 synthetic monthly P&L preparation fixture

## Evidence boundary

The quarter and fiscal-year statement values are published WD-40 Company
figures in USD thousands. The monthly phasing, trial-balance rows, account
codes, account names, account splits, chart-of-accounts mapping, and clearing
account are synthetic. They are test data, not reconstructed or estimated
WD-40 monthly actuals.

The fixture uses a debit-positive trial balance. Revenue and interest-income
credits are negative in the source rows. The reviewed mapping turns statement
expenses into positive presentation magnitudes, keeps other income/(expense)
and tax provision/(benefit) signed, and turns source interest expense from a
negative published presentation into a positive expense magnitude.

The Q2 income-tax amount is a benefit. Its placement across December, January,
and February is synthetic.

## Official controls

- Q1 FY2025 Form 10-Q, filed 2025-01-10, accession
  `0000105132-25-000009`:
  https://www.sec.gov/Archives/edgar/data/105132/000010513225000009/wdfc-20241130.htm
- Q2 FY2025 Form 10-Q, filed 2025-04-09, accession
  `0000105132-25-000015`:
  https://www.sec.gov/Archives/edgar/data/105132/000010513225000015/wdfc-20250228.htm
- Q3 FY2025 Form 10-Q, filed 2025-07-10, accession
  `0000105132-25-000025`:
  https://www.sec.gov/Archives/edgar/data/105132/000010513225000025/wdfc-20250531.htm
- Q4/FY2025 earnings Exhibit 99.1, furnished 2025-10-22, accession
  `0000105132-25-000061`:
  https://www.sec.gov/Archives/edgar/data/105132/000010513225000061/wdfc-20251022xexx991.htm
- Audited FY2025 Form 10-K, filed 2025-10-27, accession
  `0000105132-25-000067`:
  https://www.sec.gov/Archives/edgar/data/105132/000010513225000067/wdfc-20250831.htm

Q1–Q3 use the direct three-month statement columns. Q4 uses the direct
three-month column in Exhibit 99.1. The fiscal-year facts use the audited 10-K.
Q4 also equals the audited fiscal year less the first nine months, but that
derivation is not used as its primary source receipt.

## Frozen download receipts

The raw SEC HTML bytes were retrieved on 2026-07-23. Automated tests are
offline; they verify these frozen receipts and do not refetch SEC documents.

| Source | Bytes | SHA-256 |
| --- | ---: | --- |
| Q1 10-Q | 1,030,161 | `b7a1534f188f6e30b4d24cae3e173d3cda7d68b6c40f5aa24af19c3654daa70f` |
| Q2 10-Q | 1,405,347 | `e013e12e87e4a0ad38f12194823eff81d17f9cb880a0b3a09146e0359fda3707` |
| Q3 10-Q | 1,435,323 | `cafdc1640c715179b956f05e502333229b129d5a4e0a0c4c0beed18844cb253d` |
| Q4 Exhibit 99.1 | 238,878 | `df9040b54e65e635d114c0414468f6779fb440b32de7ead30b35f6c49b600710` |
| FY2025 10-K | 1,793,208 | `d03a7ef37c6796c1a01d6b9bdb438afb6b276abfa5baa112b9b0465b4fe83209` |

EPS and weighted-average shares are deliberately excluded because they are not
additive statement lines for this preparation exercise.

## Reviewed reporting semantics

The stable logical dataset for reporting is `expected/monthly_pnl.csv`, at one
statement `row_key` by fiscal `period` by `scenario`. `value` is a signed
prepared amount in USD thousands; `scenario=SYN` means synthetic monthly
phasing, not an issuer-reported monthly actual. The reviewed recipe defines the
row and period order and transports `source_key` values without renderer-side
arithmetic.

The only reviewed Reporting Engine use is
`structured_statement_values` for the prepared monthly P&L table. Values may be
shown at their native grain or summed across periods for the same statement
line and scenario; they must not be summed across statement rows. All other
analysis emphases remain unassessed. This fixture review is model-reviewed, not
human accounting review, and it does not select a chart, interpret the
statement, or approve publication.
