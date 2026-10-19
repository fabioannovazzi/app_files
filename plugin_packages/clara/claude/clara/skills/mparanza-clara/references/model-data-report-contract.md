# Run-level model-data report contract

## Vera scope overrides the generic delivery rules below

For Vera, use `skills/vera/references/selective-reporting.md` and the fixed
`usage/pipelines.json` list. Only selected Studio Archive runs qualify. Archive
finalization generates a report from recorded execution evidence; a chat-only
activity, another pipeline, or an execution without a measurable local remainder
does not produce this report. Missing evidence is explicitly unavailable, never
invented. The substantive-run and chat-draft rules below apply only to Clara
and Lucia.


For Clara and Lucia, use this contract after every substantive product run, across client-bound,
studio-wide, local, connected-source, Claude, Claude, Cowork and Antigravity workflows. The
invariant is evidence about the actual model-context boundary. A smaller context
is not required when the professional purpose needs a complete document or
population.

Studio Archive also reuses this input schema and local report validation in
`scripts/build_model_data_report.py`. That generic helper creates local JSON and
Markdown only and returns `server_receipt.status=not_requested`. The automatic
server-attestation behavior described below belongs to the product's own
`scripts/model_data_report.py` command; it is not implied by the generic helper.
The explicitly local onboarding path does not request stamping. Reading an
existing report does not request stamping either. The invoking product’s functions-and-limits reference remains applicable.

## Clara and Lucia chat inputs and drafts

A user mandate in chat and a template read by the model are observed inputs.
The agent assembles `model_data_report_input.json` from those phases; absence of
client files, a Studio Archive handoff, or an already prepared input JSON does
not waive the report. Use `host_attested` for conversational evidence and honest
unknown measurements where extent is unavailable. Synthetic content may support
`no_case_data`; it does not mean that no report input exists. Never reconstruct
a supposed exact provider payload or invent measurements.

A cloud task folder is a valid writable output folder. Do not require access to
native client folders simply to save a report. Use the installed product root
for its report scripts, independently of a delegated module's working directory.

## Required outputs

When the runtime can write durable artifacts, create both files in the run's
exact output folder:

- `model_data_report.json`: the machine-readable local processing report;
- `model_data_report.md`: the small localized report shown in the final
  Artifact Card.

For Vera, if the user prohibits receipt transmission, save
`model_data_report_options.json` with `{"local_only": true}` in the Archive run
output before finalization, failure or cancellation. For Clara and Lucia, add
`--local-only` to the build command. Both retain the local reports and return
`server_receipt={"status":"not_requested","reason":"local_only"}` without a
request file or network call. Do not retry stamping without a later explicit
request. This option does not change the selected host's model processing.

Otherwise the receipt-enabled product build command automatically creates:

- `model_data_receipt_request.json`: the retry-stable product-specific minimal request;
- `model_data_receipt.json`: the returned server timestamp and Ed25519 proof;
- `model_data_receipt.html`: a customer-readable receipt that can be printed or
  saved as PDF and links to public verification.

The default requires no per-run confirmation. If stamping fails,
retain the completed work, local report, and retry-stable request; return the
run successfully with `server_receipt.status` set to `pending`; and state that
no server-stamped receipt was created. Never discard, roll back, or mark the
professional work as failed because the receipt service is unavailable. Retry
later with `scripts/notarized_run_receipt.py stamp` and call the run stamped only
after that command succeeds.

For a Studio Archive run, declare both report files and, for schema 2, the saved
`privacy_contract.json` as run artifacts before completion. The build result
returns its exact `privacy_contract_path`; include that file in the output
declaration so Archive can close the complete output tree.
For a studio-wide workflow, keep them in that workflow's exact authorized output
folder. Never write a client report in plugin source. When the host cannot write
files, show the same compact report in chat, state that no durable receipt was
created, and use `host_attested` rather than claiming exact payload evidence.

The report is not a consent banner, privacy score, network monitor, provider
attestation, DPIA, legal opinion, or GDPR certification.

## Deliver the report by default

`build` returns `display_markdown` alongside the saved paths and receipt status.
Show this readable report directly in the final response, after the professional
result, and link `model_data_report.md`. Do not leave the report inside tool
output, show JSON to the user, or only say that it was saved. Preserve the actual
phase measurements, reasons, evidence basis and limitations. A long report may
use a compact per-phase table plus the full report link; do not collapse unlike
units into a single total or omit unknown exposure.

When stamping succeeds, also link the receipt HTML and its verification URL.
When stamping is pending, still show the report and say only that the server
receipt is pending. The generic local helper also returns `display_markdown`;
show it while preserving its local-only receipt status. If files cannot be
created, show the report directly in chat using the evidence available there.

## Show an existing report

Interpret the requested run from the conversation and the user's named client
or engagement. For a managed client run, use Studio Archive's saved engagement
and run listing to resolve its exact output folder. For a studio-wide run, use
its recorded workspace. When several runs fit, list their dates and work labels
and ask which one; never silently select a different client's report. If the
current conversation already identifies one run, retrieve it without asking
the user to locate files or name technical identifiers.

Run from the product root with its resolved Python runtime:

```bash
python scripts/model_data_report.py show \
  --report /absolute/run/output/model_data_report.json
```

This read-only command prints the readable report from the saved JSON. It checks
the report's recorded hashes, changes no files, reads no source documents, and
makes no network or stamping request. It can show a report even when source
files or its Markdown copy are no longer present. It does not revalidate current
source availability or prove transmission. Present the returned Markdown as
normal content in the answer, not a code block. Link existing saved artifacts
using the current host's supported file links. Open the report in a document or
browser panel when the user asks to open it and that host has such a tool.

If this was a chat-only run, show its existing report from the conversation. If
the report is missing, say so explicitly. Do not rerun the professional work,
invent measurements, or create a new report and present it as the original.
Retrieving or explaining this saved report is not a new substantive run and does
not require a report about that retrieval or a new server receipt.

## Automatic server-stamped proof

Vera preserves receipt request schema `1`: schema version, one random per-run
receipt UUID, the installed product version and the SHA-256 digest of the
canonical local report. Clara and Lucia use receipt request schema `2`, which
adds the explicit product as a fifth signed field. The model-data report's schema
version is separate from the receipt protocol version. Existing signed requests
and report bytes are never rewritten during a product upgrade.

It does not receive the report, workflow or local run
IDs, client or case data, purposes, phase labels, counts, filenames, file
contents, source-document hashes, prompts, or model outputs. Mparanza retains
only the opaque receipt ID, its own timestamp, the product version, report digest,
signature, key ID, and implicit schema version, without an automatic deletion
period. Existing proofs remain until removed locally or deleted administratively
from Mparanza, after which public verification is no longer possible. The proof
establishes existence, server time, and integrity of the matching report only.
It does not prove who submitted the digest, provider-side delivery, analytical
correctness, semantic necessity, a DPIA, legal compliance, or GDPR compliance.

## Phase evidence

Record every model-visible phase separately. Do not add unlike units or hide
repeat transmissions inside one reduction percentage. Use the natural units of
the workflow:

- tables: rows, columns and cells;
- documents: files, pages, sections, chunks and characters;
- correspondence: messages, threads and attachments;
- image and OCR work: images, pages and OCR blocks;
- derived analysis: metrics, exceptions, claims and evidence excerpts.

Each phase records:

- what source extent was available;
- what local code processed;
- what was model-visible;
- what remained local and was never model-visible;
- why that context was necessary;
- whether the evidence comes from an exact payload file, a workflow receipt,
  host attestation, or is not measurable.

Use exactly one phase outcome:

- `reduced_projection`: a bounded subset or derived projection reached the
  model and the report can identify what remained local;
- `full_context_required`: the complete relevant document or population was
  needed for semantic treatment; this is a valid minimization outcome, not a
  defect;
- `no_case_data`: the phase received no client or case material;
- `not_measurable`: the host cannot establish the extent from current evidence.

Do not claim `exact_payload_receipt` unless the named file is the exact packet
made model-visible. The report builder hashes those files. A hash binds the
receipt to bytes; it does not prove provider-side delivery or independently
establish that a semantic description is correct.

## Bounded model-led inspection

For tabular mapping, local code should inspect the complete population
mechanically and prepare a bounded evidence packet containing schema, types,
coverage, exceptional values and purpose-relevant examples. The model uses that
packet for semantic mapping and may request a bounded, reason-recorded follow-up.
Do not treat the literal first ten rows as representative without evidence, and
do not let a deterministic rule decide semantic relevance merely from names or
types.

## Improvement assessment

The JSON always records one internal assessment status:

- `candidate`: at least one narrower code path is supported by run evidence;
- `none_supported`: the inspected run supports no narrower path;
- `not_assessed`: the available evidence cannot support an assessment.

The Markdown report shows an improvement section only for `candidate`. Say
nothing to the user for `none_supported` or `not_assessed`.

Every candidate must identify the affected phases, the proposed code change,
the observed evidence, an estimated reduction in native units, and the quality
safeguard. A single run normally uses `candidate_needs_validation`. Use
`validated` only after representative cases show that professional usefulness,
calculation closure, evidence reachability, and required outputs do not regress.
The deterministic builder validates this record but never invents a candidate
or decides semantic necessity.

## Content boundary

The report contains counts, safe class labels, phase IDs, hashes, purposes, and
limitations. Do not copy source values, names, tax identifiers, document text,
email content, credentials, local absolute paths, or other client facts into the
report. Use stable artifact IDs and generic labels.

## Reviewed contract and actual run

Read the exact workflow's entry in `privacy/registry.json`, then its retained
`privacy/contracts/<workstream>.json`. This is the same source contract that
feeds the product-specific final section of the public function page. The
installed manifest additionally binds the projected host implementation.

Compare that description with the actual phases, host and services used. Add
`contract_review` to the report input:

```json
{
  "status": "consistent",
  "phase_ids": ["mapping"],
  "reason": "Le fasi osservate corrispondono al percorso descritto; il confronto usa le prove della lavorazione."
}
```

This is an example of shape, not a default verdict. `consistent` requires review
of every actual phase and the reviewed runtime. Use `divergence` with affected
phase IDs and a concrete reason when the run differs. Use `not_assessed`, an empty
phase list and the missing-evidence reason when comparison is unavailable. Do not
hide an uncertain extent or alter observations to fit the expected contract.
The comparison is an agent judgment; code only checks references and shape.

The product builder writes model-data report schema `2` with the exact product,
workflow, runtime, product version, source-contract digest and installed manifest
fingerprint. It retains `privacy_contract.json` alongside the report. Its source
contract digest is the public page's revision. The receipt signs the entire
report digest, including this binding; it does not turn the agent's comparison
into an independent attestation. Missing comparison is visibly unreviewed.

Legacy model-data reports with schema `1` remain valid. `show` reads either schema
offline without requiring the original installation or re-reading case files.
Preserve the saved original report and receipt; do not rebuild them to add newer
metadata. If no durable local workspace is available, disclose the actual
chat-only evidence and contract revision when available, without inventing files,
signatures or measured network exposure.

## Build and validation

From the product root, after assembling `model_data_report_input.json` from the
actual run evidence:

```bash
python scripts/model_data_report.py build \
  --input /absolute/run/output/model_data_report_input.json \
  --evidence-root /absolute/run/output \
  --output-dir /absolute/run/output

python scripts/model_data_report.py validate \
  --report /absolute/run/output/model_data_report.json

python scripts/notarized_run_receipt.py verify \
  --report /absolute/run/output/model_data_report.json \
  --receipt /absolute/run/output/model_data_receipt.json
```

The input uses schema version `1`. See the script's accepted fields and the
repository tests for reduced-projection, full-document, suppressed-improvement,
and tamper cases.

Use this compact shape, replacing the example measurements with evidence from
the run:

```json
{
  "schema_version": 1,
  "workflow_id": "variance-analysis",
  "run_id": "run_0123456789abcdef01234567",
  "runtime_profile": "openai-chatgpt",
  "language": "it",
  "created_at": "2026-08-27T12:00:00+02:00",
  "professional_purpose": "Confrontare Actual e Budget con mapping rivisto.",
  "phases": [
    {
      "phase_id": "mapping",
      "purpose": "Rivedere il significato delle colonne candidate.",
      "outcome": "reduced_projection",
      "evidence_basis": "workflow_receipt",
      "source_extent": [
        {"unit": "rows", "quantity": 10000, "label": "righe fonte", "basis": "measured"}
      ],
      "locally_processed": [
        {"unit": "rows", "quantity": 10000, "label": "righe profilate", "basis": "measured"}
      ],
      "model_visible": [
        {"unit": "rows", "quantity": 10, "label": "righe candidate", "basis": "measured"}
      ],
      "remained_local": [
        {"unit": "rows", "quantity": 9990, "label": "righe non mostrate", "basis": "derived"}
      ],
      "reason": "Il modello doveva stabilire il mapping semantico.",
      "evidence_files": []
    }
  ],
  "improvement_assessment": {
    "status": "none_supported",
    "candidates": []
  }
}
```

When the evidence supports an improvement, replace the assessment with:

```json
{
  "status": "candidate",
  "candidates": [
    {
      "candidate_id": "omit-unused-columns-after-mapping",
      "phase_ids": ["mapping"],
      "change": "Escludere due colonne dopo la conferma del mapping.",
      "evidence": ["Nessun calcolo successivo dipende dalle due colonne."],
      "estimated_reduction": [
        {"unit": "columns", "quantity": 2, "label": "colonne escluse", "basis": "derived"}
      ],
      "quality_safeguard": "Confrontare casi rappresentativi e mantenere il drill-down.",
      "status": "candidate_needs_validation",
      "validation_evidence": []
    }
  ]
}
```
