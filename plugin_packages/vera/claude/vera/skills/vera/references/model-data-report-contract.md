> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Run-level model-data report contract

Use this contract after every substantive Vera run, across client-bound,
studio-wide, local, connected-source, Claude, and Cowork workflows. The invariant
studio-wide, local, connected-source, ChatGPT, Claude, and Cowork workflows. The
invariant is evidence about the actual model-context boundary. A smaller context
is not required when the professional purpose needs a complete document or
population.

## Required outputs

When the runtime can write durable artifacts, create both files in the run's
exact output folder:

- `model_data_report.json`: the machine-readable, hash-bound receipt;
- `model_data_report.md`: the small localized report shown in the final
  Artifact Card.

The same build command automatically creates for every durable report:

- `model_data_receipt_request.json`: the retry-stable four-field request;
- `model_data_receipt.json`: the returned server timestamp and Ed25519 proof;
- `model_data_receipt.html`: a customer-readable receipt that can be printed or
  saved as PDF and links to public verification.

There is no activation setting or per-run confirmation. If stamping fails,
retain the completed work, local report, and retry-stable request; return the
run successfully with `server_receipt.status` set to `pending`; and state that
no server-stamped receipt was created. Never discard, roll back, or mark the
professional work as failed because the receipt service is unavailable. Retry
later with `scripts/notarized_run_receipt.py stamp` and call the run stamped only
after that command succeeds.

For a Studio Archive run, declare both files as run artifacts before completion.
For a studio-wide workflow, keep them in that workflow's exact authorized output
folder. Never write a client report in plugin source. When the host cannot write
files, show the same compact report in chat, state that no durable receipt was
created, and use `host_attested` rather than claiming exact payload evidence.

The report is not a consent banner, privacy score, network monitor, provider
attestation, DPIA, legal opinion, or GDPR certification.

## Automatic server-stamped proof

The server receives exactly schema version `1`, a random receipt UUID created
for this run, the installed Vera version, and the SHA-256 digest of the
canonical local report. It does not receive the report, workflow or local run
IDs, client or case data, purposes, phase labels, counts, filenames, file
contents, source-document hashes, prompts, or model outputs. Mparanza retains
only the opaque receipt ID, its own timestamp, Vera version, report digest,
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

## Build and validation

From the Vera root, after assembling `model_data_report_input.json` from the
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
