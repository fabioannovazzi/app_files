# Review And Outputs

Load this reference when producing delivery workpapers, reviewing deterministic classifications, or preparing operational follow-up requests.

## Codex Review Layer

After every deterministic run intended for delivery, build and review a reproducible sample containing at minimum:

- 10 highest-value in-scope rows;
- all rows with bank, factoring/operator, compensation, or other mandatory closure evidence;
- a stable random sample of at least 20 remaining in-scope rows;
- any user-challenged rows.

For each sampled row, record `PASS`, `FAIL`, or `UNRESOLVED`.

If any `FAIL` exists, stop, patch deterministic logic or extraction, rerun reconciliation, rebuild the review packet, and repeat review before delivery. Do not deliver final Excel/Word as audit-ready while required review rows are still `PENDING`.

## Operational Review Sample

When the user wants a few rows to inspect with a client or reviewer, run `scripts/build_review_sample.py` after the reconciliation workbook exists. This is a post-run review aid, not a replacement for deterministic classification.

Example:

```bash
python scripts/build_review_sample.py <output-dir>/riconciliazione_audit.xlsx --count 2
```

The script creates `campione_movimenti_da_controllare.xlsx` and `testo_richiesta_controllo.md`.

Keep technical rule codes in the audit workbook, but avoid exposing them in emails or reviewer requests. Use operational wording such as "risulta ancora aperta, ma trova riscontro nei mastrini", "il riscontro e stato trovato sommando piu righe dello stesso documento", and "serve verificare se esistono pagamenti, incassi, compensazioni, storni o giroconti".

## Outputs

For audit workpapers, create Excel and Word outputs when useful:

```text
<output-dir>/
  riconciliazione_audit.xlsx
  relazione_riconciliazione_audit.docx
  source_pages.json
```

The workbook should preserve assumptions, source inventory, extracted source pages, normalized records, reconciliation detail, summary, checks, Codex review rows, bank allocation candidates, external evidence details, and ledger/journal controls where relevant.

Every row-level conclusion must show source reference, document number/date/amount, evidence type, deterministic rule, matched evidence reference, and missing evidence or next step when unresolved.

## Missing Evidence Wording

When evidence is missing, state the operational next step, such as:

- official bank statement, bank receipt, or bank accounting detail for the cited movement;
- allocation schedule tying a batch payment to specific rows;
- factoring/operator statement tying document number and amount to settlement;
- compensation agreement or accounting support tied to the specific rows;
- readable export/OCR for files that could not be extracted.

Avoid saying that no evidence is missing for rows that are not proven closed.
