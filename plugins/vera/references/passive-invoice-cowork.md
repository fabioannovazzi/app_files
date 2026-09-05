---
name: passive-invoice-audit
description: Screen passive FatturaPA XML against booked ledger entries using local checks and a native Cowork Haiku subagent, then deliver an exception workpaper with traceable evidence.
---

# Passive Invoice Audit in Cowork

Keep invoice XML and the booked ledger immutable. Bind the client, engagement
and run through Studio Archive; write outputs only inside that run. Resolve
material input/mapping ambiguities before execution. Do not create bookings,
post to an ERP, send communications or infer professional approval.

## Run and semantic handoff

1. Check the packaged Python dependencies using Vera's managed launcher for
   `passive-invoice-audit`. Install only declared requirements. This distribution
   uses Cowork's own worker, without Codex, API keys or a separate CLI. A
   dependency check is not model acceptance.
2. Inspect ledger headers and a bounded sample. Prepare the exact mapping.
   Required fields: movement_id, entry_date, account_code, account_description.
   Supply amount_signed or debit/credit and actual matching source fields.
   Never fabricate missing evidence. Show exact input paths, mapping, Studio
   Archive output, assumptions and chunk size before execution.
3. Run the module's `scripts/run_audit.py` through the managed launcher with
   `--invoices`, `--ledger`, `--ledger-mapping`, `--output` and
   `--client-engagement`. Use default low effort; Haiku does not take Luna
   effort settings. Optional account/history context must be supplied evidence.
4. Exit code 3 and `status=awaiting_semantic_review` mean preparation, not a
   successful audit. Enumerate `luna_chunks/*/cowork_request.json`. The directory
   name is historical; these requests explicitly identify the Cowork worker.
5. Delegate each pending request to packaged `vera:passive-invoice-reviewer`,
   configured with `model: haiku`, supplying only the exact request path.
   On the native `Agent` tool also pass `subagent_type: "vera:passive-invoice-reviewer"`
   and `model: "haiku"` explicitly so a host default cannot change the request. Use at
   most two concurrent workers. Do not silently substitute the parent or another
   model. If the agent cannot run, retain prepared artifacts and report the
   missing capability. Do not claim semantic completion.
6. Save each subagent's returned JSON unchanged as `cowork_response.json` beside
   the request. Save `cowork_worker_record.json` from actual host evidence:

```json
{
  "schema_version": "vera.cowork_worker_record.v1",
  "request_sha256": "copy from cowork_request.json",
  "agent": "vera:passive-invoice-reviewer",
  "requested_model": "haiku",
  "invocation_id": "actual Cowork tool invocation or task id",
  "response_sha256": "SHA256 of saved cowork_response.json bytes",
  "provenance": "cowork_host_reported"
}
```

Preserve original invocation output in the run evidence. Never invent an
invocation id. Hashes bind responses to requests; they do not prove model
identity. Distinguish configured Haiku from observed identity, and disclose if
the host does not expose it. Do not claim native Luna qualification or equal
accuracy. Do not rewrite model judgments to satisfy validation.

7. Resume the same command and output directory. The engine validates packet
   binding, schema, complete invoice coverage and review evidence. Do not edit
   databases/checkpoints to force completion. Retain rejected responses and exact
   errors before obtaining fresh worker responses.
8. Deliver the XLSX exception workpaper, full-population JSONL, SQLite job,
   summaries and chunk evidence. Pending or failed semantic work means incomplete
   review. Historical `luna_*` counters refer to the selected worker; use
   `semantic_runtime` and `semantic_worker_requested` to identify this run.

## Evidence and review

Code checks XML, arithmetic, VAT/currency, duplicates, matches and journal
balance. The worker screens economic substance versus booked accounts.
`no_issue_detected` is a screening result, never correctness or approval.
Present concrete exceptions and what the professional should inspect. With
reviewed labels, run the evaluation helper and report missed material issues.
Synthetic acceptance must inspect actual model answers for clear, wrong-account,
insufficient-evidence and injected-instruction cases. Dependencies alone do not
establish review quality.

## What data reaches the model

The parent sees intake/mapping samples and output evidence it opens. Workers
receive prepared requests containing bounded invoice lines/context, booked
expense/asset accounts, deterministic findings, source references and explicitly
supplied history (at most five treatments per invoice). Source XML archives and
full ledgers remain in local processing unless the parent separately opens them.
No direct model API, new credential or additional hosted service is introduced.
Cowork handles model processing in the user's existing Claude environment.
The professional remains responsible for review.
