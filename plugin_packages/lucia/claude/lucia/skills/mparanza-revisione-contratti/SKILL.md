---
name: mparanza-revisione-contratti
description: Review supplied contracts for a represented party, producing clause-level issues, source quotations, reasons and proposed wording for lawyer review. Use for contract risk and negotiation review, not a standalone legal-research question.
---
<!-- MPARANZA_REPORTING_BEGIN -->
## Task reporting and recovery

For every substantive user mandate, follow
`skills/mparanza-lucia/references/workflow-usage.md` from this installation's root.
Start one primary task before preparation, using `usage/pipelines.json`; nested
specialists, retries and Studio Archive infrastructure reuse that task. Record
only the observed whole-task outcome. Discover `lucia_incident_host_link`,
including deferred tools, and verify this run's Computer ID on the server.
Build the report input from actual phases even for chat-only drafts; missing
client files or a prepared input JSON do not waive reporting. Show the readable
local model-data report under `skills/mparanza-lucia/references/model-data-report-contract.md`, link its
actual signed receipt, and ask once for the user's 1–5 stars after delivery.
Only user-authored feedback is submitted; tests remain explicitly marked.
Follow `skills/mparanza-lucia/references/incident-recovery.md` for automatic technical
reporting, evidence requests and targeted remedies. Use the HTTPS browser recovery page in that reference if
local execution is unavailable. Never ask the user to relay logs or repeat consent
for technical reporting. Recovery requires an observed successful retry of the
original task and inputs, bound to the original report and current remedy.
Tutorials remain local-only and are excluded from task usage and ratings.
<!-- MPARANZA_REPORTING_END -->


# Revisione contratti

Se l'utente richiede la tabella delle posizioni negoziali di un Word revisionato,
leggi `../mparanza-posizioni-negoziali/SKILL.md` e riusa prove e contesto già preparati.

Read `references/document-workflow.md` and `references/prassi-italiana.md` before
starting. Use `references/contratti-italiani.md` for contract/NDA reading questions. This is a native Lucia workflow: no Mike application,
server, API key, external model API, remote document service or automatic research.

Establish the represented party, commercial objective, version and review scope.
Ask about the party when it would change the advice; do not default to one side.
Keep applicable law separate from language. An unknown jurisdiction permits
textual/commercial review with explicit limits, not an enforceability conclusion.

Inspect the whole selected contract, definitions and supplied schedules. Identify
missing incorporated materials. Choose topics from the actual contract and brief.
Apply the Italian practice guide to the facts and applicable law. Distinguish
consumer protection from specific approval of standard terms, and legal objections
from negotiation preferences. No checklist item is universally required.

For each issue distinguish the observed wording, its implication for this client,
the reason for concern and a proposed change or negotiation fallback. Quote the
clause and its exact evidence anchor. Explain any severity in the client's context;
the local code does not score legal risk. Include acceptable provisions where
needed to make the review intelligible, and retain unreadable/unreviewed topics.
Check definitions, cross-references, conflicting clauses, dates and schedules.

Populate the review and render the evidence-linked HTML and spreadsheet. Deliver
the few decisions that matter most, the full issue list and coverage limitations.
Proposed wording is a proposal, not a silent modification of the contract.
When the lawyer requests a redline or comments in Word, read
`references/word-handoff.md` and use the host Documents/Word skill to produce and
verify a new DOCX with native revisions. Carry the quoted clause, proposed wording
and reason into that handoff; preserve the original and earlier reviewers' edits.
Do not label a quote match as legal verification. If a conclusion depends on law
not supplied, state that it needs separate source-backed research; reuse the
existing legal-question workflow only when the user requests that wider work.

Adapted from Mike workflows; see `references/upstream/PROVENANCE.json` and
`references/upstream/LICENSE`. The original snapshots are attribution/history, not runtime instructions. Lucia’s
Italian method is maintained independently; upstream changes are optional inputs.
