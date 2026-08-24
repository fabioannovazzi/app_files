# Vera — Intelligent Passive-Invoice Audit

This Vera/Codex workflow screens a passive FatturaPA population against the
ledger entries actually recorded for those invoices. It is an independent
review workflow: it never posts to an ERP and never books an invoice.

## Inputs

- one directory, XML file, or ZIP containing readable passive FatturaPA XML;
- one CSV, XLSX, or XLSM ledger export containing the actual journal lines;
- a reviewed JSON column map; use `references/ledger-mapping.example.json` as
  the contract, substituting the exact source headers;
- optionally, a reviewed JSONL history with prior invoice description, account
  code, account description, treatment state, and an explicit
  `relevant_to_invoice_ids` array linking each treatment to the current invoices
  for which the professional considers it relevant; and a JSON object mapping
  account codes to client-specific chart descriptions.

The ledger map must provide `movement_id`, `entry_date`, `account_code`, and
`account_description`, plus either `amount_signed` or both `debit` and
`credit`. Supplier tax ID, invoice number/reference, document date, gross,
taxable, VAT and currency fields materially strengthen matching and checks.
When supplied directly, `amount_signed` must use debit minus credit. Map
`account_type` when credit-note polarity should be checked mechanically.

## Run or resume

```bash
python scripts/run_audit.py \
  --invoices /path/to/passive_xml_or.zip \
  --ledger /path/to/prima_nota.xlsx \
  --ledger-mapping /path/to/ledger-mapping.json \
  --client-engagement /absolute/path/to/context.json \
  --output /path/to/audit-job
```

The client-engagement context is created by Vera's Studio Archive for the
`passive-invoice-audit` workflow. It binds the exact input receipts and confines
all writes to that run's output directory.

The default Luna workload is 25 independently judged invoice packets per task,
two concurrent native Codex workers, low reasoning effort, and two retries.
Verbose packets are split earlier when the encoded prompt would exceed the
240 KiB workflow limit.
Reuse the same output directory to resume. The content-bound SQLite job rejects
different inputs or controls, skips completed chunks, and resets interrupted
`running` chunks to `pending`. A content-bound chunk checkpoint and the native
Luna receipt allow a result published immediately before an interruption to be
recovered without invoking Luna again; incomplete attempt files are preserved
under the chunk's `recovery_attempts` directory before a retry.

Outputs are `full_population.jsonl`, `exception_workpaper.xlsx`,
`ledger_entries_without_invoice.jsonl`, `run_summary.json`, `run_summary.md`,
`audit.sqlite3`, and content-addressed Luna chunk evidence. The workpaper shows
exceptions; the JSONL preserves the full population.

## Evaluation

Labels are JSONL objects with `invoice_id`, `label` (`problematic`,
`acceptable`, or `ambiguous`), and optionally `known_issue`.

```bash
python scripts/evaluate_audit.py evaluate \
  --results /path/to/audit-job/full_population.jsonl \
  --labels /path/to/labels.jsonl \
  --output /path/to/audit-job/evaluation.json
```

The report prioritizes exception recall, false-positive rate, human review
rate, and the complete list of missed material issues.

Synthetic test copies are created only from explicit mutation plans and are
written separately; real packets and ledger data are never changed. Every
mutation must include `source_review_label: "acceptable"`, and the source
invoice must already be matched, free of deterministic exceptions, and have a
`no_issue_detected` baseline. Only the account code and descriptions are
replaced; the original line description is retained so the packet does not tell
Luna that it is synthetic.

```json
[
  {
    "invoice_id": "reviewed-source-invoice-id",
    "source_review_label": "acceptable",
    "replacement_account_code": "CANC",
    "replacement_account_description": "Cancelleria",
    "label": "telecom_to_stationery"
  }
]
```

```bash
python scripts/evaluate_audit.py synthetic \
  --results /path/to/audit-job/full_population.jsonl \
  --mutation-plan /path/to/mutations.json \
  --output /path/to/audit-job/synthetic/packets.jsonl
```

To run those controlled corruptions through native Luna and measure whether
they are surfaced:

```bash
python scripts/evaluate_audit.py synthetic-evaluate \
  --results /path/to/audit-job/full_population.jsonl \
  --mutation-plan /path/to/mutations.json \
  --output /path/to/audit-job/synthetic/evaluation-run
```

This writes the immutable packets, one structured result per synthetic copy,
chunk evidence, recall, human-review rate, and every missed synthetic issue.

## Model boundary

Semantic review calls the pinned native Codex executable with exactly
`gpt-5.6-luna`. It reuses Vera's qualified, read-only macOS Seatbelt capsule,
passes the compact prompt by stdin, enforces a strict JSON schema, and retains
the response, JSONL events, stderr and launch receipt per chunk. It uses the
existing Codex login. There is no API client, `OPENAI_API_KEY`, external AI
service, model substitution, or global Codex configuration change.

`no_issue_detected` means only that the screen found no concrete review reason.
It does not mean correct, verified correct, approved, or audit passed.

## Optional native Luna acceptance test

Use a fresh empty output directory. This opt-in test sends one compact batch
containing ordinary telecom and software controls, an unrelated telecom account,
an equipment/expense case, and an instruction embedded in invoice text. It
verifies that the intended native Luna worker runs and that the ordinary packets
are not contaminated by the embedded instruction.

```bash
VERA_RUN_REAL_LUNA_INTEGRATION=1 \
VERA_REAL_LUNA_OUTPUT_DIR=/path/to/fresh-luna-test \
python -m pytest -q tests/test_passive_invoice_audit.py::test_real_luna_integration_is_opt_in
```
