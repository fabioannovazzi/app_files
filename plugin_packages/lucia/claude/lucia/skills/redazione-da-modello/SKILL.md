---
name: redazione-da-modello
description: Draft from a supplied editable legal template, preserving the original and returning an edited copy with a change register, factual basis and unresolved placeholders for lawyer review. Use when a template exists, not to invent a template or sign a document.
---

# Redazione da modello

Read `../revisione-contratti/references/document-workflow.md` and
`../revisione-contratti/references/prassi-italiana.md`. The upstream snapshot is
attribution/history. Use the supplied editable template;
if none exists, request it. A PDF does not become an editable template merely
because its text can be extracted. Never rebuild a DOCX from extracted text.

Establish the represented party, transaction, jurisdiction, required changes and
supporting facts. Preserve missing information as visible placeholders with an
open-questions list. Never invent identities, amounts, dates, authority or law.
Treat example names and sample provisions in the template as examples, not facts.
Check Italian party identifiers, authority and communication details against the
supplied evidence. Separate business choices from legal changes. A firm template
is not evidence that every clause suits this relationship; keep consumer issues,
specific approvals and special regimes visible. Do not insert a generic double
signature block as a cure for all issues. Do not silently change foreign governing
law or translate common-law remedies into Italian remedies.
Record the shared Italian review context and the template/playbook version in
`review.json`, even when only an edited copy and change register are requested.
Deliver the context and open legal questions with the draft; exact replacements
do not verify their legal basis.

Prepare the template and supporting files in one evidence pack. Read the original
structure, schedules and instructions. Create `changes.json` as exact replacements:

```json
[{"anchor":"word/document.xml#p3","old":"[CLIENT]","new":"Example S.r.l.","basis":"Client name confirmed in the user's instruction"}]
```

For DOCX read `../revisione-contratti/references/word-handoff.md` and use the
host's Documents/Word skill for authoring, native revisions/comments and rendering.
Use tracked edits when showing adaptations for review; prepare a clean copy only
when requested, with the same change register. The local Word bridge verifies
inline edit results against the original and proposed changes. Do not rebuild a
second Word editor inside Lucia or mistake a helper's success message for proof
that every change was applied.

For TXT/Markdown use `draft --template D001 --changes /absolute/changes.json`.
The older local DOCX replacement mode remains a bounded clean-text helper, not
the normal Word authoring route or a substitute for native revisions. If the host
document capability is unavailable, return the proposed edits and identify the
unfinished Word step. Do not silently replace the template's layout or file format.

Inspect the resulting file, render it when local rendering is available, and
verify layout, numbering, definitions, cross-references, annexes and unresolved
placeholders. Compare the result with the original and match every intended edit
to the change register. Do not call the output final or ready to sign; explain
unverified formatting or facts. Deliver the edited copy, changes with factual
basis, open questions and the lawyer's review decisions. Never overwrite, sign,
send or file the original. The helper performs no model or network calls.

MIT source and pin: `references/upstream/PROVENANCE.json` and `LICENSE`.
