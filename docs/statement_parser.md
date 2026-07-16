# Generic Statement Parser

This module implements a hybrid extraction pipeline used by `check_statements`.

1. **Segmentation** – pages are scanned line by line and footer/boilerplate
   lines are removed.
2. **Multi‑strategy extraction** – each page is attempted in table mode first
   and falls back to a text state machine.  Incomplete rows may be repaired
   via the optional LLM helper.
3. **Normalisation** – dates and numbers are parsed in European and American
   formats and transaction direction is inferred from multilingual keywords.

Pass `deterministic_only=True` to `GenericStatementParser` to disable any LLM
repair.  Keywords can be extended by editing `parsers/keywords.py`.

### Reconciliation stages

Parsed transactions flow into a staged reconciliation pipeline with the
following sequence:

1. Amount and Date Window
2. Bank Fees and Charges
3. Cash Withdrawals/Deposits
4. Card Payments
5. Payroll and Taxes
6. Beneficiary Name
7. IBAN
8. References (Invoice/CRO/TRN)
