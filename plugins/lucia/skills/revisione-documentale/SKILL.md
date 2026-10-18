---
name: revisione-documentale
description: Review a selected collection of legal documents against common questions, with one row per document and evidence-backed cells, coverage gaps and an Excel review table. Use for structured document review or due diligence across files.
---
<!-- MPARANZA_REPORTING_BEGIN -->
## Task reporting and recovery

For every substantive user mandate, follow
`skills/lucia/references/workflow-usage.md` from this installation's root.
Start one primary task before preparation, using `usage/pipelines.json`; nested
specialists, retries and Studio Archive infrastructure reuse that task. Record
only the observed whole-task outcome. Build and show the readable local model-data
report under `skills/lucia/references/model-data-report-contract.md`, link its
actual signed receipt, and ask once for the user's 1–5 stars after delivery.
Only user-authored feedback is submitted; tests remain explicitly marked.
Follow `skills/lucia/references/incident-recovery.md` for automatic technical
reporting, evidence requests and targeted remedies. Use `luciaIncidents` if
local execution is unavailable. Never ask the user to relay logs or repeat consent
for technical reporting. Recovery requires an observed successful retry of the
original task and inputs, bound to the original report and current remedy.
Tutorials remain local-only and are excluded from task usage and ratings.
<!-- MPARANZA_REPORTING_END -->


# Revisione documentale

Read `../revisione-contratti/references/document-workflow.md` and
`../revisione-contratti/references/prassi-italiana.md` before execution.
All helpers run on selected files; no upload to Mike, Dario, Mparanza or a separate
model service. The host model performs the legal reading in the conversation.

Agree the decision and select useful columns from the brief and the documents.
Use `references/colonne-italiane.md` to select questions for Italian practice.
Choose them semantically; remove irrelevant questions and add case-specific ones.
Record a different relationship, law or formation history in each affected document
cell when reviewing a mixed portfolio. Upstream YAML snapshots are attribution and
history, not the column definitions to execute. Never fill a missing contract value
with a speculative estimate; a requested calculation needs inputs and assumptions.

Create one source per document and keep amendments and annexes separately
identifiable. Explain relationships in the review rather than merging contradictory
texts. Process bounded batches, persist review progress and inspect every selected
document. Read long documents in chunks; never silently clip to a character limit.
Track actual anchors read in `coverage`. An unreadable or unfinished row remains
visible and cannot become “not stated”.

For each cell separate extracted term, exact quotation, interpretation and action.
Do not infer agreement-wide silence from a search miss. Read definitions, exceptions
and applicable schedules before deciding what a term means. Reconcile apparent
inconsistencies across documents; retain unresolved conflicts explicitly.

Render the common evidence report and Excel table. Summarize exceptional terms,
missing information and decisions for the lawyer, without hiding unreviewed rows.
The output is a review workpaper, not completed due diligence or legal clearance.
No files are sent, filed or changed by this workflow.

Upstream pin and licence: `references/upstream/PROVENANCE.json` and `LICENSE`.
