---
name: rating-legalita
description: Prepare an Italian AGCM legality-rating initial application from available documents or no documents, with evidence, eligibility, subjects, obstacles, premiums, gaps and a review dossier.
---

## Cowork execution contract

Public workflow names select skills; component IDs select module paths.
`financial-report-builder` uses component `report-builder`, `vouching` (historically
called Check Entries) uses `check-entries`, and `purchase-invoice-review` uses
`passive-invoice-audit`. These component IDs are not additional workflows.

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, financial-report-builder and vouching only, optional cache
cleanup uses the corresponding component ID from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
This supported maintenance command is the only cache-cleanup exception to the
prohibition on editing the installed tree by hand. It is optional: ordinary
validation and execution tolerate incidental bytecode without removing it.
On a read-only installation, skip cleanup. If the command reports a permission
error, retain that error and continue the ordinary validated workflow when its
checks pass; do not chmod, delete files manually, copy or patch the installation,
or bypass the host's permissions to make cleanup succeed.
If `validate_implementation_tree` ever fails with a file/directory-contract
mismatch, do not delete or modify files inside the installed plugin tree by hand
and do not bypass a sandbox/permission rejection to do so. Stop and report the
exact error instead.

Work from the connected folder and supplied files first. Before a module's Python
helpers, locate the installed plugin root. When it contains `components.json` and
`scripts/managed_python_runtime.py` (as Vera does), run from that root:

```bash
python3 scripts/check_dependencies.py --module <module>
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

If the enclosing plugin does not ship this managed launcher, use the module's
dependency checker and only already-installed dependencies; do not assume that a
standalone module script provisions them.

The managed launcher provisions and reuses one user-scoped CPython 3.12
environment per OS host with the published shared requirements, outside client
folders. Modules and products share this dependency environment; it does not
isolate client matters. This declared dependency setup is authorized as
part of running the workflow; never install arbitrary packages or use ambient
Python for subsequent module helpers. Repeat any declared `--requirements` options
on both commands. Missing ambient imports are a reason to run this setup, not to
abandon the calculation. If setup fails, report its exact error and do not replace
the required calculation with an invented result. Optional OCR setup still needs
separate approval. If setup reports `Host not in allowlist` for PyPI, explain that
Claude Settings > Capabilities > Allow network egress is disabled or restricted.
Ask the user or organization administrator to authorize package-registry access;
never change network permissions silently or work around the restriction. Retry
the same managed setup after access is approved, in a new session if needed.

MCP tools, browser or computer control, and local review servers are optional
enhancements, never completion gates. Cloud Cowork sessions may not expose local
plugin MCP servers even when the plugin is installed; use the packaged Python
workflow through the managed launcher in that case. Do not equate missing MCP
registration with a failed calculation engine. When an optional capability is
unavailable, continue with Markdown and file-based review and state the limitation.

The normal Cowork deliverable is a reviewable draft, artifact card, and
source/review files. A callable persistence interface may optionally record or
apply reviewer actions, but its absence never blocks delivery. Never claim
`applied` or `final_ready` unless corresponding persisted artifacts prove it;
otherwise report that professional review remains pending.

Use host-neutral user-facing artifact names. Name assistant-authored review
folders and files for Vera or their professional purpose (for example,
`vera-review/`, `vera_phase1_synthesis_reviewed.md`, and `run_review.md`).
Never put host, platform, or model-provider names in assistant-authored
user-facing artifact paths, document headings, field labels, narrative text,
or status summaries. Describe execution routes generically, such as
`external review route`, `connected tool`, or `local review interface`.

Derive any run ID, status, artifact count, or package hash quoted in an
assistant-authored supplement from the final delivered manifests.
After any rebuild, regenerate or resynchronize those supplements before
delivery. When a workflow ships a complete-delivery validator or sealer, run it
against the exact connected-folder copy after the last write.
In this contract, the base package validator alone does not validate extra
narrative files.

When a workflow declares owner-only or private output and uses a private scratch
directory before copying the final package into the connected folder, reapply
the privacy modes after that transfer: `0700` for the package root and every
directory, and `0600` for every file. Verify the connected-folder tree with
`stat` or `lstat` before claiming completion. If the host filesystem cannot
preserve those modes, do not claim owner-only delivery; keep the package in the
private scratch location or report the limitation and ask for a safer
destination.

Do not use WhatsApp, live INPS browser capture, hosted feedback or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract.

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
implemented workflows. A minimal event register and reviewed 30-day calendar
are included from intake, including events arising while an application is pending.
They do not provide automatic surveillance, reminders or transmission. The catalog
retains the other maintenance controls as reference.
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

## Before a real pilot

Before requesting individual judicial-information sheets or reading real judicial
documents into the model, have the studio review the engagement and data plan.
Record them in `practice.mandate` and `practice.data_governance`, with the actual
reviewer, date and imported evidence IDs. Unreviewed records remain null.
The engagement distinguishes the representative's declarations, completeness
and signature from the studio's evidence gathering, legal assessment and drafts.
Name the company contact responsible for reporting events, the agreed channel
and excluded services. Do not transfer the representative's attestations to Vera.

The data plan identifies the controller, information notice and its provision,
general processing basis and specific authority for judicial data, authorized
roles, purpose-based retention/deletion criteria, responsible person and next
review date. Review the actual selected model/account data path as well.
An information notice or consent alone does not establish authority under GDPR
Article 10 and Italian law. Do not invent a standard retention period.
Use M15 in `references/templates.md`; legal adequacy is a professional decision.
Without these records, use synthetic material or non-sensitive pre-intake only.
The CLI refuses real-case evidence processing without recorded prerequisites;
it cannot prevent the host from receiving material pasted or uploaded beforehand.
It does not enforce access permissions or delete files automatically.

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

Register events immediately with separate occurrence and knowledge dates.
Append a `practice.event_reviews` entry only after professional qualification:
`art21_1_mandatory`, `art21_4_premium`, or reasoned `not_reportable`.
The reviewed legal scope must distinguish an applicant from a rating holder.
Link evidence and owner; leave unknown dates unresolved and flag urgency.
The helper adds 30 calendar days to the occurrence date, never the knowledge
date, with no automatic holiday extension. Qualification and date computation
must be reviewed on the actual case. Reopen affected substantive controls when
an event changes their evidence; the register alone does not requalify them.
Record an actual communication only with its external date and imported receipt.
Never generate an AGCM action or receipt. Mandatory-requirement breaches under
Article 21(1–3) differ from premium changes under Article 21(4–5). The 18-month
restriction starts when the obstacle ceases to be relevant, not at occurrence,
discovery or automatically at revocation. No automatic sanction decision or
reapplication date is produced. Preserve earlier events and review entries;
record corrections as new events and append reviews instead of overwriting them.

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

Record actual professional review sessions in `practice.review_sessions`:
reviewer, stage, timezone-aware start/end and breaks. Include rework separately;
never infer time from a test run, file timestamp, model latency or the number of
controls. The dossier totals active minutes by stage, rejects overlapping sessions
for the same reviewer and reports absent measurements as unknown, not zero.
Agree case-level coverage and business criteria before comparing the positive,
incomplete and ineligible pilots. Synthetic timings must remain labelled synthetic.
See `references/pilot-scenarios.md` for the three document-led acceptance exercises;
passing helper tests does not complete those professional exercises.

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

The current Claude or Cowork model can read selected corporate, personal,
judicial, fiscal and payment evidence, relevant original documents or reviewed
extractions, questions, answers, quotations, decisions and drafts. There is no
automatic anonymization or local-only guarantee. Python validates schemas,
quotes, hashes and arithmetic locally and makes no model or network calls.
Research current public AGCM sources with non-identifying legal queries; do not
put client identifiers or identifiable judicial details into search queries.
Use the chosen account's data terms. Keep case files and judicial details out
of technical logs and developer feedback; use synthetic reproductions.

## Cowork-native Run UX

Default output policy: the dossier and gap plan are normal outputs, not choices
to propose. Prepare `run_review.md` beside the dossier with observed
checks, unresolved questions and actual output paths. Package changes belong
in source; generated ZIPs are rebuilt, never edited. Ordinary authorized work
continues without ceremony; stop for unresolved material choices or external,
destructive or approval-sensitive actions outside the authorized scope.
Never write run outputs inside this Git workspace or a published directory.
The local deterministic scripts verify data integrity and arithmetic only;
the selected model and professional retain responsibility for interpretation.
