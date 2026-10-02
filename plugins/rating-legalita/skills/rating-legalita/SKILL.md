---
name: rating-legalita
description: Prepare an Italian AGCM legality-rating initial application from available documents or no documents, with evidence, eligibility, subjects, obstacles, premiums, gaps and a review dossier.
---

# Rating di legalità — prima attribuzione

Inspect the actual inputs before asking questions. Resolve material choices
from available evidence; ask only what changes the work. Do not raise
hypothetical branches unless the facts cue them. The declared requirements
are in `requirements.txt`.

Work from this module root. Read `references/checklist.md`,
`references/catalog.json`, `references/sources.md`, `references/templates.md`
and `references/case-contract.md`. Use the current AGCM regulation and FAQ;
the shipped catalog records research on 2026-10-02, not perpetual validity.

This implementation covers pre-intake through a reviewable initial-application
dossier. Renewal, maintenance, transitional cases and portal automation are not
implemented workflows. The catalog retains their source controls as reference.
Identify such requests explicitly and explain this boundary before proceeding;
do not relabel a renewal or notification as an initial application.

## Start with what exists

Say that you are using Vera's rating-legalita workflow. No compulsory tutorial.
Use answers already provided; do not require the user to know the law or bring
a complete file. If identity is unknown, create a pre-intake with `client: null`.
Ask the next material question (usually company identity and whether this is a
first application); draft a short document request with purpose and recipient.
Never invent a client, archive engagement, rating or professional approval.

From the Vera root first run `python scripts/check_dependencies.py --module
rating-legalita`; from this module run `python scripts/check_dependencies.py`.
Dependencies belong in the shared managed Python 3.12 environment, never an
ad-hoc pip install. Then:

```bash
python scripts/rating_case.py init --case-id intake-001 --as-of YYYY-MM-DD --output /absolute/work/case.json
python scripts/rating_case.py render --case /absolute/work/case.json --source-root /absolute/work --output /absolute/work/output
```

## Bind the real client and read evidence

Once identity is confirmed, follow Vera's Studio Archive skill. Resolve the
existing client and engagement; import the original intake and selected
documents; prepare and start `rating-legalita`. Preserve the pre-intake dossier
and pass it as `--previous` when continuing. Use the portable v2 run context.
Import the model-authored case JSON as a run input before rendering. Register
both originals and readable, reviewed extractions from PDFs/scans, using the
existing extraction/OCR workflow; preserve extraction-to-original provenance.
Never use a filename, a search snippet or an unread scan as substantive evidence.

Read the selected evidence with the current host model. Inventory declarations
with author and date separately from independently supported facts. Identify
contradictions, missing pages and limits. Evidence quotations must be exact
text passages in an imported readable file; record the original page/section
locator and hash. The helper verifies text and bytes, not legal meaning.

```bash
python scripts/rating_case.py render --case /absolute/run/inputs/case.json --client-engagement /absolute/client_engagement.json --previous /absolute/prior/dossier.json
```

The CLI validates case/client/engagement identity and exact Studio Archive
input receipts. It writes into that run's output directory. If Archive is
unavailable, preserve pre-intake and explain the blocked real-case path;
do not claim a registered run or bypass the binding with `--synthetic`.

## Review in professional order

1. Establish current sources, submission date and entity. Review access
   conditions, including qualified turnover, registration and Italian seat.
   A declared amount is not verified turnover. If access fails, explain why
   and prepare a reviewable gap plan without promising a remedy.
2. Reconstruct all relevant roles, powers and former office holders. Review
   every subject/event; the professional confirms the complete perimeter.
   Expand controls into distinct instances where evidence or persons differ.
3. Assess obstacles and exceptions from actual acts, their procedural stage,
   effective dates and complete facts. Do not use keywords to classify criminal
   proceedings, finality, dissociation or eligibility. Escalate a precise legal
   question with its evidence through Vera's validated-answer workflow.
4. Only after base eligibility is supported assess optional premiums a–h.
   Count one premium per letter. A policy title, future certification or planned
   compliance function does not establish implementation. P09 records whether
   the ANAC deduction condition exists, not whether the check was performed.
   Unknown deduction or unresolved cap order stays visible in the estimate.
5. Use the model to propose facts, relevance, applicability, conclusions and
   follow-up. Only record `verified`, `failed` or `not_applicable_reviewed`
   after the professional's actual decision. Capture actor, date, reason,
   sources and exact evidence. A missing proof stays `unknown` or
   `evidence_pending`; a conflict stays `disputed`. Never promote a model
   proposal into a professional confirmation.

`core_rating.py` performs arithmetic on already qualified facts. It does not
select legal topics, sources, research phases or relevant acts. Any use of the
traceability ratio or safety thresholds requires the methodology and legal
perimeter to be reviewed, as explained in its docstrings and source register.

## Preserve facts, goals and decisions

Save T0 first. Append observed snapshots with dates when new evidence is
reviewed; never overwrite T0. A `conditional_scenario` is titled **Scenario
obiettivo — non realizzato**. Only the last observed snapshot drives current
status. Actions in a gap plan never change the score by themselves.

For every gap record: kind (information, evidence, access, obstacle, optional
premium, update or interpretation), linked instances, T0, target, action,
owner, reviewer, agreed deadline or unknown date, dependencies, expected proof,
impact, current status, normative basis and closure criterion. Do not invent
costs, implementation times or likelihood of acceptance. Reuse one document
across controls with distinct locators rather than repeatedly requesting it.

## Deliver and close the run

Read and check the generated `dossier.md` and `dossier.json`; do not infer
completion from file existence. Explain what is supported, what prevents a
conclusion, what can be done now and by whom. Deliver the eligibility review,
subject matrix, evidence/decision chain, documentary score or unknown result,
T0 comparison and gap plan even when the application is incomplete/ineligible.
Use `references/templates.md` to draft the client report, document requests,
declarations and application index from those same reviewed facts.

This dossier is not an AGCM form. Preparing an application requires checking
the actual current WebRating fields, declarations and attachments. Do not
invent a field map, signature verification, approval, submission receipt or
official rating. The helper always returns `submission_authorized: false`.
No portal, email, PEC, public posting or background monitoring is performed.

Follow Vera's `references/model-data-report-contract.md`: generate and display
`model_data_report.json` and `model_data_report.md` in the exact run output.
Record actual model-visible inputs rather than saying all work was local.
Finalize the dossier, requests and report as durable Studio Archive artifacts;
complete the run only after those artifacts and its model-data report exist.

## Data boundary

The current Codex or Cowork model can read selected corporate, personal,
judicial, fiscal and payment evidence, relevant original documents or reviewed
extractions, questions, answers, quotations, decisions and drafts. There is no
automatic anonymization or local-only guarantee. Python validates schemas,
quotes, hashes and arithmetic locally and makes no model or network calls.
Research current public AGCM sources with non-identifying legal queries; do not
put client identifiers or identifiable judicial details into search queries.
Use the chosen account's data terms. Keep case files and judicial details out
of technical logs and developer feedback; use synthetic reproductions.

## Codex-Native Run UX

Default output policy: the dossier and gap plan are normal outputs, not choices
to propose. Prepare `codex_run_review.md` beside the dossier with observed
checks, unresolved questions and actual output paths. Package changes belong
in source; generated ZIPs are rebuilt, never edited. Ordinary authorized work
continues without ceremony; stop for unresolved material choices or external,
destructive or approval-sensitive actions outside the authorized scope.
Never write run outputs inside this Git workspace or a published directory.
The local deterministic scripts verify data integrity and arithmetic only;
the selected model and professional retain responsibility for interpretation.

## Plugin Improvement Feedback

Keep the improvement note local to chat or run artifacts.
Use Vera's shared feedback policy only if the user chooses transmission.
