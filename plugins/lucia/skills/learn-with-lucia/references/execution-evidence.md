# Local execution evidence

This is a host-attested record of an observed run, not a provider-authenticated
receipt or professional approval. Only the teacher saves progress, after opening
the actual result and checking the working thread's native run records. The
worker creates the following local JSON from the actual files and tool results;
never prefill it from the teaching kit or invent a successful execution.

```json
{
  "schema": "mparanza.teaching_execution.v1",
  "evidence_kind": "host_attested_local_execution",
  "product": "lucia",
  "workflow_id": "the-exact-own-workflow",
  "phase": "demo",
  "worker_thread_id": "actual-paired-working-chat-id",
  "outcome": "review_required",
  "skill_sha256": "SHA-256 of the exact installed owning SKILL.md used",
  "inputs": [{"path":"case/inputs/source.xlsx","sha256":"actual file SHA-256"}],
  "native_records": [{"path":"case/run/validation.json","sha256":"actual file SHA-256"}],
  "outputs": [{"path":"case/outputs/report.xlsx","sha256":"actual file SHA-256"}]
}
```

Use `demo`, `practice` or `application` for the actual phase. Outcome is
`completed` for executed work or `review_required` when the normal pipeline
produced its reviewable draft with disclosed unresolved professional decisions.
A blocked or failed execution remains a checkpoint, not a completed demo.
The native records must be the pipeline's actual validation, calculation,
execution or package records. If the workflow exposes its execution only as a
host tool result, preserve that exact observed result locally. An intake context
or prepared-case receipt alone does not establish execution. Never turn an
authored assertion into a native run record.

All paths must be ordinary files inside this lesson's directory; for
`application`, use the explicitly selected real-work destination. Use the
source snapshots actually consumed by the run. Inputs, native records and
learner-facing outputs have distinct paths. The `outputs` list must match the
progress command's `artifacts` list in order. Each list contains 1–30 files.
Keep the execution JSON itself separate from all three lists. Save it as, for
example, `demo-execution.json`, and pass that path as `execution_record` when
recording progress. Preserve the demo's files and record a new execution for
practice. Do not overwrite a retained execution record.

The tracker checks product/workflow/phase, paired worker, the current owning
skill hash, all file hashes, and exclusion of prepared material or input copies.
It rechecks the retained execution before completion and when opening a saved
result for explanation. These mechanical checks do not establish the model's
professional judgment, actual user understanding or human approval. Those still
require the normal live explanation, participation and workflow review.
