---
name: passive-invoice-audit
description: Screen passive FatturaPA XML against booked ledger entries using local checks and a native Cowork Haiku subagent, then deliver an exception workpaper with traceable evidence.
---

## Cowork execution contract

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, report-builder and check-entries only, optional cache
cleanup is available from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
If `validate_implementation_tree` ever fails with a file/directory-contract
mismatch, do not delete or modify files inside the installed plugin tree by hand
and do not bypass a sandbox/permission rejection to do so. Stop and report the
exact error instead.

Work from the connected folder and supplied files first. Before a module's Python
helpers, locate the installed plugin root. When it contains `components.json` and
`scripts/managed_python_runtime.py` (as Vera does), run from that root:

```bash
python3 scripts/check_dependencies.py --module <module>
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

If the enclosing plugin does not ship this managed launcher, use the module's
dependency checker and only already-installed dependencies; do not assume that a
standalone module script provisions them.

The managed launchers provision and reuse an isolated environment containing only the
module's published requirements. This declared dependency setup is authorized as
part of running the workflow; never install arbitrary packages or use ambient
Python for subsequent module helpers. Repeat any declared `--requirements` options
on both commands. Missing ambient imports are a reason to run this setup, not to
abandon the calculation. If setup fails, report its exact error and do not replace
the required calculation with an invented result. Optional OCR setup still needs
separate approval. If setup reports `Host not in allowlist` for PyPI, explain that
Claude Settings > Capabilities > Allow network egress is disabled or restricted.
Ask the user or organization administrator to authorize package-registry access;
never change network permissions silently or work around the restriction. Retry
the same managed setup after access is approved, in a new session if needed.

MCP tools, browser or computer control, and local review servers are optional
enhancements, never completion gates. Cloud Cowork sessions may not expose local
plugin MCP servers even when the plugin is installed; use the packaged Python
workflow through the managed launcher in that case. Do not equate missing MCP
registration with a failed calculation engine. When an optional capability is
unavailable, continue with Markdown and file-based review and state the limitation.

The normal Cowork deliverable is a reviewable draft, artifact card, and
source/review files. A callable persistence interface may optionally record or
apply reviewer actions, but its absence never blocks delivery. Never claim
`applied` or `final_ready` unless corresponding persisted artifacts prove it;
otherwise report that professional review remains pending.

Use host-neutral user-facing artifact names. Name assistant-authored review
folders and files for Vera or their professional purpose (for example,
`vera-review/`, `vera_phase1_synthesis_reviewed.md`, and `run_review.md`).
Never put host, platform, or model-provider names in assistant-authored
user-facing artifact paths, document headings, field labels, narrative text,
or status summaries. Describe execution routes generically, such as
`external review route`, `connected tool`, or `local review interface`.

Derive any run ID, status, artifact count, or package hash quoted in an
assistant-authored supplement from the final delivered manifests.
After any rebuild, regenerate or resynchronize those supplements before
delivery. When a workflow ships a complete-delivery validator or sealer, run it
against the exact connected-folder copy after the last write.
In this contract, the base package validator alone does not validate extra
narrative files.

When a workflow declares owner-only or private output and uses a private scratch
directory before copying the final package into the connected folder, reapply
the privacy modes after that transfer: `0700` for the package root and every
directory, and `0600` for every file. Verify the connected-folder tree with
`stat` or `lstat` before claiming completion. If the host filesystem cannot
preserve those modes, do not claim owner-only delivery; keep the package in the
private scratch location or report the limitation and ask for a safer
destination.

Do not use WhatsApp, live INPS browser capture, hosted feedback or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract.

# Passive Invoice Audit in Cowork

Keep invoice XML and the booked ledger immutable. Bind the client, engagement
and run through Studio Archive; write outputs only inside that run. Resolve
material input/mapping ambiguities before execution. Do not create bookings,
post to an ERP, send communications or infer professional approval.

## Run and semantic handoff

1. Check the packaged Python dependencies using Vera's managed launcher for
   `passive-invoice-audit`. Install only declared requirements. This distribution
   uses Cowork's own worker, without Claude, API keys or a separate CLI. A
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
