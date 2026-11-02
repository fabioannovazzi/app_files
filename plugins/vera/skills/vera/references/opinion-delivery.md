# Vera opinion delivery

This policy applies to Vera's legal, tax and compliance answer journey,
research, answer review and opposing opinion on every host. It replaces the
shared module's **Native research review**, **MCP Review UI** and **Cowork
review handoff** instructions, including their browser and chat queue fallbacks.
The shared substantive research and validation method still applies.

## Before researching a new question

Send one ordinary assistant message in the current chat **before the first
substantive source lookup**, including subscription searches. Use the working
language. Give the **question I’ll answer** as you understand it, with the
jurisdiction, relevant date or scope when they matter. Then give the **sources
I’ll consult**. Name the case-specific authorities or documents you plan to
check and, where useful, the issue each can settle. Describe a prospective
plan. An uninspected source has not been verified or approved. Keep generation
instructions and the optimized prompt internal.

Once the message is visible, continue research in the same turn. Wait only for
an unresolved fact or choice that materially changes the answer. If the same
plan is already visible in this chat, continue from it. If the assignment or
source plan changes materially, briefly tell the user what changed before the
new lookup. For review of a supplied answer, do this when fresh research is
needed. In a chat-only host, use the same sequence.

## Deliver the answer

Lead with the conclusion, its decisive reasons and supporting sources. Link
the reviewed opinion and, when required, the opposing opinion and comparison.
In the opinion and in substantive conclusions repeated in chat, cite the source
immediately after **each material conclusion**, including the opposing position
and any material conclusion restated in the comparison. Name the authority,
date and the article, paragraph, page or short passage that supports that point.
Use an inline named Markdown link to the actual checked source when available,
or a parenthesized title and locator for a private document. Keep qualifications
and competing authorities beside the point they affect. Where support is
missing, say exactly what could not be verified and what follows from that
limitation. A source list alone does not complete the opinion.

State material missing evidence, uncertainty and any professional choice that
remains. Ask a focused question only when that choice or missing fact changes
the answer or prevents completing the requested work.

Do not create, open or recreate an answer-review panel. Do not run
`research_record.py review-ui`, launch a local review workbench, or call the
`validate_deep_research_review`, `render_deep_research_review`,
`save_deep_research_decisions` or `apply_deep_research_decisions` tools. Do not
replace the panel with a list of per-source, per-file or per-claim approvals
in chat. Internal counts, JSON records and routine technical checks are not
the user's deliverable.

## Check the actual opinion

For an opinion, set `vera_opinion: true`, `evidence_display: inline_citations`
and `validation_scope: all_material_claims` in the answer contract (including
when the user waives an opposing examination). Review coverage semantically
against the entire final text. In each retained material claim, copy the exact
conclusion into `claim_text` or `disposition.revised_claim` for a corrected
conclusion. On each source check you rely on, record the human citation label
in `opinion_citation` and put that citation immediately after the statement,
in the same paragraph. This is a synthetic example.

    The contractual period is thirty days. [Supply agreement, clause 4](https://example.invalid/agreement)

For a retained private source use `(Supply agreement, clause 4)` instead of a
public link. When evidence only partly supports the finding, conflicts, is
unavailable, or requires professional judgment, record the exact visible
qualification as `opinion_limit` and put it immediately after the citation
group (or after the statement if no authority was verified). Never invent an
authority or classify a supported conclusion as evidence-limited to pass a
check. Repair the actual opinion and rerun the review when the audit identifies
a material conclusion with missing evidence. Preserve the reviewed text in all
exports. A separately requested citation-free client letter may keep its own
source record; deliver its supporting professional opinion with inline sources.

For every Vera opinion, use the invoking product’s `scripts/opinion_validation.py`
with the same arguments as the shared `package_validation.py` command for
each reviewed position. It runs the shared review and checks the reader’s
citations before marking an opinion ready. Use the shared writer for a separate
citation-free client letter. Keep each opinion’s source and document inventories,
claims review, answer contract and delivered Markdown together with its captures.
In Codex, use `vera_execute` with component `deep-research-validator` and
script `scripts/opinion_validation.py` for both packaging and verification.
For the managed command line, run from the Vera product root.

```sh
python scripts/managed_python_runtime.py --requirements modules/deep-research-validator/requirements.txt run scripts/opinion_validation.py verify <review-directory>
```

For packaging, replace `verify <review-directory>` with the shared writer’s arguments. After the
existing research and opposing-opinion checks, run
`scripts/opinion_validation.py verify <review-directory>` **before delivering
or closing the run**. For a combined opinion pass the parent of `position/` and
`adversarial/` to check both actual documents. In the comparison, restate each position’s
reviewed conclusion with its citation in the corresponding conclusion field.
Return any new material finding to the relevant position for review. This check is read-only and also
applies when issuing a new opinion from an older review. Keep previously issued
records intact. If local tooling is unavailable, compare the actual chat or
document text against every material claim and source before sending it.

## Keep substantive checks and records

Review retained source passages, answer-contract conformance, claim coverage,
semantic support, reasoning and professional-judgment limits. Repair failed
validation checks. Retain `claims_review.json`, `validation_audit.json`, source
captures and the research issue register; technical checks remain the agent's
work. Bind and verify `research_review.json` and, when required,
`opinion_delivery.json` using the existing helpers before completing the same
Archive run. Declare the actual physical artifacts and preserve the existing
professional-review rules. Do not require a UI snapshot or UI decisions to
deliver the requested draft.

Shared packaging helpers may still emit compatibility files such as
`review_payload.json` and `ui_decisions.json`. Keep those files internal; their
existence does not require a panel or a decision queue. Never invent reviewer
decisions, claim save/apply occurred, or mark professional adoption complete
without an actual instruction. Record substantive user feedback in the issue
register, resolve consequential findings and revalidate the affected opinion.
When resuming an older run, preserve and consume any already recorded
substantive feedback without reopening its panel or rewriting its evidence
merely for display.
