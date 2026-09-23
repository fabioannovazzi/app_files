---
name: controllo-documento
description: Audit a legal document for inconsistent names, definitions, numbering, references, dates, amounts, language and hidden document defects. Use for systematic proofreading before circulation or signature, with evidence and proposed corrections; use contract review for negotiation and substantive legal risk.
---

# Controlla errori e incoerenze

Read `../revisione-contratti/references/document-workflow.md` and
`../revisione-contratti/references/prassi-italiana.md`. For a DOCX or a request for
corrections in Word, also read `../revisione-contratti/references/word-handoff.md`.
Use the host's Documents/Word skill for rendering, native edits and comments.
Lucia's helper inspects evidence and verifies outputs; it is not a Word editor.

Establish the document version and purpose. Proofread the selected artifact in
Italian unless another language is requested; foreign governing law remains
foreign law. Preserve originals. Report defects first; apply requested corrections
on a copy with tracked changes. A proofreading request alone does not authorize
silently changing legal positions, accepting existing revisions or sending files.

## Inspect and map

Prepare a `controllo-documento` evidence pack using the shared local helper.
Then run `python scripts/legal_proofreading.py scaffold --run-dir <run>` from the
plugin root. Read the complete selected sources in manageable chunks, retaining
source/anchor coverage. The scaffold is unfinished work, not an audit result.

For DOCX, ordinary paragraph anchors contain the proposed/final text; `/original`
anchors contain the previous text where it differs. `/structure` and `package/`
anchors expose links, fields, direct run/paragraph properties, styles, numbering,
comments and revisions. Do not mix removed words into operative clauses. Read
style inheritance and numbering definitions before alleging formatting or sequence
errors; a changed font alone does not establish a defect. Use the document skill
to render and inspect layout, including tables, notes, headers and footers.

For PDFs, use the available PDF skill to inspect rendered pages and links as well
as text. Record evidence from that inspection with page references; do not claim
that a DOCX metadata check ran on a PDF or plain text. Image-only content remains
unreadable unless the user has supplied readable text or requested a separate OCR
operation. Never hide the affected page or turn its gaps into absent clauses.

Build three source-linked maps in `proofreading.json`: entities and their name
variants; sections/numbering (including the contents list); defined terms and their
uses. The model identifies relationships and meanings. The code does not decide
that every capitalized word is a definition or every number is a section.

## Review in separate passes

Use one pass for each category, recording its conclusion or limitation:

1. Definitions: inconsistent use, conflicting scope, unused or circular terms.
2. References: clause, annex, document and field targets, with their intended meaning.
3. Internal consistency: contradictory obligations, exceptions, scope or timelines.
4. Entities: names, legal forms, roles, signatories and identifiers against evidence.
5. Numbers: dates, currency, Italian separators, words versus figures, percentages
   and stated calculations. Do not invent a legal deadline from a date alone.
6. Language: typos and grammar that are wrong or change meaning; separate preference.
7. Numbering: duplicates, gaps, hierarchy and correspondence with the contents list.
8. Formatting: styles/runs, tables, whitespace, hidden hyperlink/field targets,
   comments and revisions. Never open a document-controlled link just to inspect it.

Several anomalies in one passage justify looking more closely; they do not prove
copy/paste origin. An intentional style or defined exception is not an error.
Assign severity from the consequence in this document, never a category lookup.
An uncertain name, amount or intention prompts a question rather than fabrication.

## Record and deliver

Populate the scaffold according to `scripts/legal_proofreading.schema.json`.
Every finding has `id`, `severity`, `category`, `kind` (error, preference or
uncertain), exact `citations`, `issue`, `reason` and proposed `fix`. Keep every
selected document and pass visible. Maps need quoted evidence or an explanation
of missing/absent entries. Record visual evidence and unresolved limitations.
Use the user's language for findings, maps and explanations.

Run `python scripts/legal_proofreading.py render --run-dir <run>`; inspect and
deliver `proofreading.html`, the few corrections that matter most, and any
requested Word output via the document skill. Rendering checks quote occurrence
and declared pass coverage; it does not prove that every defect was found.
If there are no findings, say which passes were actually completed and which
remain open. Do not equate an empty list with a clean bill of health.

Adapted from Mike's MIT `proofread` workflow. Unchanged source, licence and pinned
provenance are in `references/upstream/`; they are historical evidence, not runtime
instructions. Lucia maintains this Italian method independently.
