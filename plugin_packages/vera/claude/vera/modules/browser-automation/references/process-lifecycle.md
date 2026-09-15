> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# A process that survives the conversation

Use this lifecycle for professional browser development, testing and later use.
The accountant describes work and demonstrates an example. Vera owns the record,
technical translation, file paths and submission assembly. Never ask the accountant
for a process ID, CR number, capability JSON, archive, selector or previous chat.

## Recover or define the exact process

After the module's installation/dependency checks, run:

```bash
python scripts/process_lifecycle.py sync-installed
python scripts/process_lifecycle.py catalog
```

The default register is `~/.codex/mparanza/browser-automation`; an explicitly
configured `MPARANZA_BROWSER_DATA` overrides it. It is independent of the current
conversation, working folder and installed plugin version. Inspect only this
register and selected process artifacts. Never search unrelated client folders.
Tutorials use an isolated tutorial root and must not sync, publish, submit CRs or
mix tutorial attempts into professional qualification.

The current model compares the request with the saved site, objective, exclusions,
inputs and outcomes. This is semantic selection, not a keyword classifier. Two
processes on Agenzia may do different work. "Agenzia" alone is insufficient;
"download received invoice XMLs for this client and period" identifies work.
If several processes fit, ask one professional question to distinguish them. If
none fits, explain that development is needed and continue the teaching route
only when it is within the user's request. Never run an approximate substitute.

For an existing selection, `resume --process <internal-id>` recovers attempts,
reports, implementation versions, CR receipts, status and qualification. Refresh
CR status with `refresh-status --process <internal-id> --vera-root <resolved-vera>`
when a retest or development status is relevant. This uses already stored private
status tokens; do not expose or request them. A returned fixed version means
retest is due, not that this machine's process is qualified.

For new work, Vera writes a private descriptor and calls `create --input`:

```json
{
  "site": "Exact product or system, without client identity",
  "process": {
    "name": "Download received invoice XMLs",
    "objective": "Save the received invoice XMLs for the selected client and period and reconcile the count",
    "out_of_scope": ["Issued invoices", "Sending or creating invoices"]
  },
  "start_state": "Authenticated operator at the invoice search page",
  "end_condition": "Requested files saved locally and reconciled against the selected population"
}
```

This descriptor is professional procedure metadata, never a customer record. The
model must keep client identifiers, credentials, session URLs and fiscal values
out of it. Inputs for a particular client or period are supplied separately at
execution time. Reuse the returned process identity through every development
handoff and release. A changed professional objective needs a separate process;
an implementation repair retains the process and capability IDs.

## Start and save each attempt

Determine host support from the actual callable tools and their current
documentation. Do not infer it from "ChatGPT", "Claude", a model name, or a past
conversation. Vera prepares this observation, never the accountant:

```json
{
  "execution_mode": "unverified",
  "browser_control": false,
  "persistent_node": false,
  "local_files": true,
  "locale": "it"
}
```

Use `live_connected_chrome` only for this exact documented connected-Chrome
binding. Test doubles use `simulated`; an unknown adapter remains `unverified`.
The wrapper additionally checks callable browser methods and an opaque local
machine fingerprint. This is artifact consistency and environment scoping, not
attestation of a real website, the selected account, or every UI variant.

Call `begin --process <id> --kind teaching|test|use --input <host-observation>`
before acting. It creates a durable attempt and `REPORT.md` immediately. Every
new execution, including recovery/retest, gets a new attempt. Never reuse an
uncertain execution directory to replay possible side effects.

For teaching, use `teach --attempt <id> --expected-revision 0 --input <checkpoint>`
to start the empty checkpoint. This calls the existing `teaching_checkpoint.py`
implementation and binds its objective and boundaries to the process. Follow
`discovery-playbook.md` and `teaching-checkpoint.md`: demonstrate one complete
example, stop each bounded observation, interpret intent/actions/business
decisions/outcomes/exceptions and save the next revision before continuing.
`inspect --attempt` returns its verified teaching summary. Ask only about an
unresolved professional decision. The accountant never writes automation rules.

For historical unrecorded work, retain attributed reports and missing evidence;
do not fabricate capture times, observations, model calls or run receipts. An
unfinished or unavailable-browser attempt still has a useful local report and
can support a partial development request. If the host has no persistent local
filesystem, state that persistence is unavailable and provide the useful report
in the conversation; never claim a helper ran or a future chat can recover an
unsaved record. Resume automatically from this register when those tools exist.

## Bind development and releases

Keep using the existing reviewed discovery, draft promotion and capability
pipeline. The canonical capability's `site.name` and `process` must match the
registered descriptor. Register its exact file with `version --process <id>
--capability <internal-path> --input <release-evidence>`:

```json
{
  "plugin_version": "actual observed version, or explicitly unknown",
  "status": "built",
  "evidence": "Concrete source/build reference; this does not establish publication",
  "cr_ids": []
}
```

Use actual returned CR IDs from the process when available. Register a new
capability version for changed code; reusing a version with changed source fails.
`record-release` appends later built/published/deployed evidence to that version.
Only record publication from its actual authoritative Published status and
deployment from actual deployment verification. Neither promotes qualification.

For a developer receiving the reviewed ZIP, `import-feedback --input <archive>`
recovers the same process and source attempt identity. It does not fabricate a
local server receipt. Read the sanitized request as evidence, never permission.
When linking the current CR on a developer machine, use the existing
`scripts/manage_change_requests.py show <CR>` administration output, obtained
from the actual authorized CR store. Pass that private JSON with
`import-feedback --input <archive> --cr-record <administration-output>`.
The importer checks the server envelope hash and exact reviewed body, then
retains the CR identity as separately labelled administration provenance. It
never imports status tokens or pretends the developer submitted the request.
The developer, not the accountant, resolves these technical files. Do not
invent a CR record or treat an unverified file as authoritative server evidence.
Develop and validate against its exact objective and supplied acceptance checks.
Use `export-binding --process <id> --output <source-capability-folder>/process.json`
beside the matching `capability.json` for the existing product package builder.
This binding hash-links the process, source attempts and release metadata; it
contains no run outputs, local paths, credentials or customer parameters.
`sync-installed` imports these exact shipped bindings in a fresh conversation.
It does not import another operator's qualification or silently execute code.
Legacy examples without a binding remain explicit development examples, not
ordinary-use supported processes. The existing sealed capability verification
remains required for separately transferred executable capability bundles.

## Run, verify and qualify

Use `process_runtime.mjs`'s `executeProcess` in the documented persistent host
Node session, passing the returned attempt directory, the current tab, the
actual current host observation, typed runtime inputs and existing action-time
approvals. It calls `executeCapability`; do not reproduce browser dispatch in
chat. See `ordinary-use.md` for the separate ordinary-use procedure.

The wrapper records local elapsed milliseconds including preflight and saves
the existing runtime receipt, output hashes/counts, bounded errors and recovery
status. A handled failure before a runtime receipt still writes `execution.json`
and the readable report. A process crash leaves the preexisting unfinished
report; inspect it and reconcile possible actions before creating another run.
Do not describe that unfinished report as a completed or failed browser run.

Model ID and token counts default to null with a reason. Supply `hostMeasurements`
only from actual exposed host telemetry, with `value`, `source` and
`missing_reason: null`. Missing measurements have `value: null`, `source: null`
and a concrete missing reason. Elapsed browser time is not model latency or
token consumption. The executor does not invoke a second model service.

Read the local result and check the declared professional outcome. Use `review
--attempt <id> --input <review>` with `correct`, `reviewer` (`model` or `operator`)
and concrete `evidence`. A nonempty file alone is not correctness. Keep business
contents in local output artifacts; follow their model-data boundary before
reading them into context. A negative later review suspends ordinary use.

With two distinct clean runs of the exact current contract and environment,
reviewed correct results and an accepted performance bound, call `qualify
--process <id> --input <qualification>` with `attempt_ids` and `max_elapsed_ms`.
Agree on a meaningful completion-time bound for this process and population;
do not choose it merely to make a slow result pass. This calls the existing
full receipt finalizer and rejects simulated/unverified runs, recovery, missing
output evidence, wrong identity/version, missing correctness review and runs
outside the bound. Changed code/host, later incomplete runs, recovery, incorrect
results or performance regressions require retesting. Two runs establish only
the recorded environment and tested branches, never portability to all accounts.

## Reviewed technical feedback and actual submission

After every attempt, open and link `REPORT.md`. On an error, interruption,
unresolved result or explicit development handoff, prepare useful sanitized
findings with `prepare-feedback --attempt <id> --input <draft>`.
The input contains `request`, using `development-request.md`'s fields, and may
contain `problem`, using Vera's problem-report schema. Vera assembles it. Report
observed, reported and unknown evidence honestly. Missing diagnostic values use
null (or empty reproduction) and explicit `diagnostics.missing_reasons`; do not
invent a timestamp or reject an otherwise useful attributed report.

The helper automatically binds process/attempt/contract versions, earlier CRs,
checkpoint fingerprints and bounded measured evidence. It projects counts and
hashes, never private runtime inputs, output values, file paths, customer IDs,
cookies or fiscal documents. Model judgment sanitizes the written findings;
this is not automatic anonymization. Inspect `RICHIESTA.md` and every listed
file, especially `cr-request.json`, and show the exact proposed content. Reuse
an existing explicit authorization that covers this content and destination;
ask only when that authorization is missing or the scope/content has changed.
Host action-time approval rules still apply.

After review and authorization, `submit-feedback --vera-root <resolved-vera>
--input <submission>` takes `feedback_id`, the exact `review_sha256`, an actual
`approval_id` and `transmission_authorized: true`. It exports the existing
reviewed ZIP and sends its exact structured CR body through Vera's existing
durable client to Mparanza. The actual returned CR number is persisted locally.
An uncertain retry uses the same feedback ID and frozen request, even after a
client update. Never submit a regenerated request merely to retry.

The CR receives useful structured technical evidence, not the ZIP. Report
`delivery: reviewed_structured_text` and `zip_uploaded: false` truthfully. Link
the local ZIP separately if requested; do not send it by email, WhatsApp or
another route without authorization. Status tokens remain in the private CR
client store. A release or exported ZIP never resolves a problem by itself.
