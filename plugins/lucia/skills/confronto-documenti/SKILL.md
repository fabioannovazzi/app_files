---
name: confronto-documenti
description: Compare two or more supplied legal documents or versions, showing terms, source locations and the practical significance of changes. Use for version comparison or parallel agreements, not standalone contract risk review.
---

# Confronto documenti

Read `../revisione-contratti/references/document-workflow.md` and
`references/upstream/compare-documents.md`. The local contract takes precedence
over upstream assumptions about uploads or tools. No Mike server or separate API.

Identify whether these are versions of one instrument or separate agreements.
Use filenames, dates and the user's instruction to establish order; ask if the
baseline is ambiguous. Never infer that the last file supplied is the latest.
For versions, run the local `compare` helper for each relevant pair. Its literal
diff is a reading aid; it does not detect legal significance, prove equivalence,
resolve renumbering or account for layout/images. Read the source texts too.

Use a topic-by-document comparison with one column per document and a separate
explanation of the difference. Cover the material similarities as well as changes
to rights, obligations, economics, deadlines, definitions and incorporated texts.
Trace each term to its own document and anchor. Distinguish new, deleted, moved
and reworded provisions through model judgment. Explain why a change matters for
the represented party. A changed word can matter more than a moved page.

Keep every document visible, including unreadable versions. “Not stated” requires
complete reading coverage; an extraction gap is not deletion. If the documents
are only partly comparable, explain the limit and compare the meaningful overlap.

Write the shared review JSON with one cell per source/topic and document-specific
quotes. Populate `differences` with exactly one topic key per selected topic and
the model's explanation of the cross-document difference as its value; an
unresolved comparison must explain the missing evidence. Put the main decisions
in `takeaways`. Rendering creates a topic-by-document table with a separate
Difference column in both HTML and Excel. Summarize its material conclusions in
the final answer.
Return no more than five main decisions/follow-up points unless the case needs
more. Preserve all originals; this workflow does not accept or reject changes.

MIT source and pin: `references/upstream/PROVENANCE.json` and `LICENSE`.
