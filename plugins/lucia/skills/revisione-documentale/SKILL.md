---
name: revisione-documentale
description: Review a selected collection of legal documents against common questions, with one row per document and evidence-backed cells, coverage gaps and an Excel review table. Use for structured document review or due diligence across files.
---

# Revisione documentale

Read `../revisione-contratti/references/document-workflow.md` before execution.
All helpers run on selected files; no upload to Mike, Dario, Mparanza or a separate
model service. The host model performs the legal reading in the conversation.

Agree the decision and select useful columns from the brief and the documents.
For commercial agreements read `references/upstream/commercial-columns.yaml`;
for NDAs read `references/upstream/nda-columns.yaml`. These are MIT-licensed
starting questions, not a fixed taxonomy or an automatic classifier. Remove
irrelevant columns and add case-specific questions. Do not calculate an estimated
contract value unless the required inputs exist; show formula and assumptions.

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
