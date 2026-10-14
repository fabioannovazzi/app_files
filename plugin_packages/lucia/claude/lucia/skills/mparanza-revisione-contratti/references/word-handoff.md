# Word files through the host document skill

Use the Documents/Word skill exposed in the current host catalogue to create,
edit, redline, comment on and render Word files. Read that skill and the references
it requires for the actual operation. Resolve its tools and bundled dependencies
through the host; never assume a cache path, a skill version or a locally installed
desktop application. This is the same conversation model, not an extra model API.
Use the corresponding available native document capability on other supported
hosts; do not assume Codex filesystem paths work in Cowork.

Lucia owns the legal purpose, proposed wording, factual support and review choices.
The document skill owns Word authoring and visual verification. Lucia keeps source
snapshots, the anchored request and verification results alongside the output.
No Mike add-in, backend, account, server or remote document service is required.

## Before the edit

Prepare the selected original with `legal_documents.py`. Inspect final/original
revision views and existing comments. Do not accept another reviewer's revisions
as a side effect. Explain any ambiguous base version and proceed on independent
review work. For signed/protected/encrypted material obtain an appropriate editing
source; never silently remove protection or invalidate a signature.

Record a `word-request.json` identifying the exact source SHA-256 and intended
changes. For inline edits the format is:

```json
{
  "source_sha256": "SHA-256 from the evidence pack",
  "mode": "tracked",
  "edits": [
    {"id": "E1", "kind": "replace", "anchor": "word/document.xml#p4",
     "old": "30 giorni", "new": "60 giorni", "basis": "Termine concordato dal cliente"},
    {"id": "C1", "kind": "comment", "anchor": "word/document.xml#p4",
     "old": "30 giorni", "comment": "Confermare la decorrenza del termine.",
     "basis": "Evento iniziale non documentato"}
  ]
}
```

`start`, when supplied, is a zero-based character offset in the original paragraph's
final text view. It disambiguates repeated phrases and is required for a pure
insertion (`old` is empty). The declared changes must not overlap. This is a
mechanical addressing contract, not a legal approval or a reason to ask the lawyer
to operate JSON files. Lucia prepares it from the agreed task.

## Author and verify

Use the document skill on a new output file, preserving the template's layout,
styles, numbering, fields, notes, hyperlinks and unrelated package parts. Request
native Word revisions when reviewing or redlining; do not substitute colored text,
strikethrough formatting or only a separate change list. Comments explain the
specific point at the relevant passage. Use an honest author label such as Lucia.

Do not assume every document helper can handle every range. Some helpers only
match within one text run, choose the first matching paragraph or report success
despite unmatched edits. When that applies, use the document skill's supported
precise OOXML/editing path; do not flatten the document or silently skip changes.
Do not copy a second general-purpose Word editor into Lucia.

Check boundary spaces and run properties after any split-run edit. A helper may
write the right XML text yet omit `xml:space="preserve"`, causing Word to join
words around insertions/deletions, or fail to carry the original run formatting
into revision nodes. Correct those defects through the document skill's precise
OOXML path and render again; raw-text equality alone is insufficient.

For inline edits, run the bundled read-only verification after authoring:

```bash
python scripts/legal_word_bridge.py --original <snapshot.docx> --result <reviewed.docx> --request <word-request.json> --report <word-verification.json>
```

Resolve every reported mismatch using the original evidence and the document
skill. The verifier checks expected final text, original text under rejected
revisions, retained existing revisions/comments, comment anchors and changes to
unrelated package parts. It does not verify all OOXML semantics or layout.
It also rejects newly introduced edge whitespace without preservation markup.

Structural edits (adding/reordering paragraphs, tables or sections) require the
document skill's explicit whole-document comparison, a complete change register
and visual inspection. The inline verifier intentionally does not certify them;
record that different verification scope, including unaffected material checked.
Do not describe an inline-verifier failure as a pass.

Render with the document skill and inspect every page. Check the insertion and
deletion views, original/final wording, comments wiring and actual changed regions.
Where Word itself is available verify accept/reject behavior there; otherwise
state the boundary between file-format/render checks and a Word application test.
Never replace current evidence with an earlier successful rendering.

Deliver the reviewed DOCX, readable review/change register and unresolved choices.
If the host document capability is unavailable, preserve the findings and proposed
changes and identify the Word step as unfinished. Do not claim a redline exists,
silently install another service or mislabel a clean replacement as tracked editing.
