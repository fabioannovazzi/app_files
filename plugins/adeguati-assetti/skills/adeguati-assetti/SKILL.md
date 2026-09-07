---
name: adeguati-assetti
description: Review an Italian enterprise's organizational, administrative and accounting arrangements from documents and operating evidence; prepare a proportionate assessment, findings, improvement actions and follow-up for professional review. Use for adeguati assetti and organizational readiness, not merely financial reporting or a concordato plan.
---

# Valutazione degli assetti organizzativi, amministrativi e contabili

Help the professional assess whether this enterprise's responsibilities, processes
and information support its actual activities and timely decisions. Deliver a
sourced assessment memo, findings and an improvement plan. This is an assessment
of arrangements, not a compliance certificate, statutory audit, attestation or
automatic crisis declaration. Directors retain their responsibilities; the
commercialista reviews the proposed analysis. Neither a score nor a successful
script establishes adequacy.

Read `references/intelligent-assessment.md`, `references/professional-method.md`
and `references/record-contract.md`
from the module root before analysis. The model selects scope, sources,
proportionality, materiality, interpretation and recommendations. Python verifies
exact bindings, hashes and record shape only. No questionnaire total, ratio,
company-size threshold or keyword classifier decides adequacy or legal scope.

## Codex-Native Run UX

Inspect the actual inputs before asking questions. Establish the entity,
activities, scale and complexity, governance, review date, purpose, scope and
available material. Summarize the proposed work briefly in professional language.
Resolve material choices from the evidence. Ask only unresolved questions that
could change the next defensible step; do not
require a universal questionnaire or ask the user to select internal skills.
Do not raise hypothetical branches unless the facts cue them.
A small owner-managed company need not imitate a large company's bureaucracy.
A complex group needs a scope that considers delegations, subsidiaries and
information flows rather than an automatic entity-count rule.

Use existing organization charts, delegations, procedures, minutes, interview
notes supplied by the user, management reports, closing calendars, reconciliations,
forecasts and examples of decisions where relevant. Do not demand every category
in every case. Register user statements as statements, never independent proof.
Do not contact employees, management or the client without explicit authorization.

## Assess evidence and operation

For each relevant arrangement distinguish what is documented, what is reported,
what operating evidence demonstrates, and what is unknown. Several observations
may concern the same arrangement with different evidence states. Cite originals
and exact page, row, date or event for material observations and counterevidence.
A policy does not prove implementation. Missing documentation does not prove that
a process never operates. A missing report may limit the review without proving
that the company never produced one. Explain the difference.

Adapt the areas of review to the company's facts, considering responsibilities
and substitutes, authority and oversight, key operational processes, information
flows, timeliness and reliability of accounting, reporting used by management,
and the ability to identify and respond to emerging financial difficulties.
Investigate actual use: when a report was produced, who received it, what decision
followed, and whether exceptions were addressed. A profitable year does not prove
adequate arrangements; financial stress does not alone prove their inadequacy.
Do not infer prospective cash sufficiency from historical bank movements.

For each material finding explain the observation, professional interpretation,
consequence for this company, alternative explanations and targeted follow-up.
Keep unverified areas explicit and continue independent useful work. An area not
assessed must never silently become satisfactory. An exclusion requires a
company-specific reason. Lead the memo with a proportionate overall assessment
and its evidence limits, not a checklist completion percentage.

## Reuse supporting work selectively

Reuse exact reviewed artifacts from the same client engagement when relevant:
`management-control-pack` for recurring reporting evidence; `financial-analysis`
for its supported historical calculations; `business-planning` for an already
requested or justified forward-looking plan; `open-item-reconciliation` for
specific balance evidence. Read the selected skill before its helpers. Do not
require a full financial stack or generate a second business plan by default.
Record each artifact's scope, date and limitations. Historical reporting alone
cannot demonstrate a functioning forward-looking process.

An isolated management report stays in its reporting workflow; a business
investment decision stays in Business Planning; a review of a concordato proposal
stays in Concordato Plan Review. A general legal question about article 2086
without a company assessment belongs to `quesito-legale-fiscale`. Material legal
claims in this assessment follow Vera's validated-answer journey; its mechanical
validation never certifies the company assessment.

## Actions and subsequent review

Propose actions linked to findings with a reasoned priority, a proposed responsible
role, proposed timing and the evidence needed to assess implementation. Mark an
unknown owner or date as unresolved in words; do not invent an accepted commitment.
Do not create calendar monitoring, send reminders, assign people externally or
implement organizational changes as part of this review.

For a subsequent assessment, bind the exact previous finalized record in the same
engagement. Compare new evidence with the historical scope and address every
previous action, including those not yet assessable, deferred or superseded.
An action marked complete needs cited implementation evidence and a reasoned
assessment; a new policy alone does not establish operating effectiveness.
Preserve historical judgments rather than rewriting them. Request professional
review of conclusions and action dispositions; record approval only when explicit,
with the exact proposal digest. A reviewer label is not an authenticated signature.

## Durable delivery

Never edit plugin source or generated ZIPs during client work. When useful,
write `codex_run_review.md` in the run output to summarize delivery and limits.
Never write run outputs inside this Git workspace or a published directory.
In Codex, select the Studio Archive client and engagement, import exact source
files and any prior review, prepare and start workflow `adeguati-assetti`. Use only
hydrated bound inputs and the run's exact output folder. Follow Vera's managed
launcher; run `scripts/check_dependencies.py` before helpers. Prepare the model's
review JSON in the output folder and run from the module root:

```bash
python scripts/assetti_review.py --client-engagement <context-path> --review <run-output>/review_input.json
```

For every new run, author the `intelligent_review` extension described in the
record contract. Use its coverage, process evidence, targeted questions, chronology
and decision brief to make the reasoning reviewable. Reassess hypotheses after
answers; do not merely fill fields or run the helper and call that analysis.

Default output policy: the Markdown assessment memo and versioned JSON record
are normal outputs, not choices to propose;
the memo contains the evidence observations, findings and action plan. Narrative
uses the user's language. State unresolved areas, professional review status and
which actions remain proposals. Include Vera's per-phase model-data reports and
receipt when available, declare the outputs in Studio Archive, then finalize and
complete the run. Completion means delivery, not adequacy or professional approval.
If archive capability is unavailable, complete the evidence-based review in chat
or connected files and disclose that no portable run or immutable decision was
saved. Do not claim a helper ran without execution evidence.

## Model and external data

The selected model may read complete relevant company documents, staff roles,
interview notes, financial reports, prior findings and decisions; there is no
automatic anonymization. Initial assessment, legal-source review, action planning
and follow-up can each read relevant evidence. Local hashing does not make the
analysis local-only. Public legal research uses generic topics without private
company or employee identifiers. No external business-data connector is included.

## Plugin Improvement Feedback

Keep the improvement note local to chat or run artifacts.
Use Vera's shared feedback policy only if the user chooses transmission.

## Execution boundaries

The local deterministic helpers use only the Python standard library declared in
`requirements.txt`; they verify bindings and record integrity, not adequacy.
Run `scripts/check_dependencies.py` before helper execution. Do not install
undeclared dependencies. Explicit approval is reserved for external, destructive,
approval-sensitive or materially unresolved steps. Ordinary authorized local
inspection and record creation proceed without an additional approval ceremony.
