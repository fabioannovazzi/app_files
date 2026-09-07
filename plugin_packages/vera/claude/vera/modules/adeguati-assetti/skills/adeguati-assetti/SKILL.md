---
name: adeguati-assetti
description: Review an Italian enterprise's organizational, administrative and accounting arrangements from documents and operating evidence; prepare a proportionate assessment, findings, improvement actions and follow-up for professional review. Use for adeguati assetti and organizational readiness, not merely financial reporting or a concordato plan.
---

## Cowork execution contract

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, report-builder and check-entries only, optional cache
cleanup is available from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
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

The managed launchers provision and reuse an isolated environment containing only the
module's published requirements. This declared dependency setup is authorized as
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

# Valutazione degli assetti organizzativi, amministrativi e contabili

Help the professional assess whether this enterprise's responsibilities, processes
and information support its actual activities and timely decisions. Deliver a
sourced assessment memo, findings and an improvement plan. This is an assessment
of arrangements, not a compliance certificate, statutory audit, attestation or
automatic crisis declaration. Directors retain their responsibilities; the
commercialista reviews the proposed analysis. Neither a score nor a successful
script establishes adequacy.

Read `references/professional-method.md` and `references/record-contract.md`
from the module root before analysis. The model selects scope, sources,
proportionality, materiality, interpretation and recommendations. Python verifies
exact bindings, hashes and record shape only. No questionnaire total, ratio,
company-size threshold or keyword classifier decides adequacy or legal scope.

## Cowork-native Run UX

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
write `run_review.md` in the run output to summarize delivery and limits.
Never write run outputs inside this Git workspace or a published directory.
In Claude, select the Studio Archive client and engagement, import exact source
files and any prior review, prepare and start workflow `adeguati-assetti`. Use only
hydrated bound inputs and the run's exact output folder. Follow Vera's managed
launcher; run `scripts/check_dependencies.py` before helpers. Prepare the model's
review JSON in the output folder and run from the module root:

```bash
python scripts/assetti_review.py --client-engagement <context-path> --review <run-output>/review_input.json
```

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

## Execution boundaries

The local deterministic helpers use only the Python standard library declared in
`requirements.txt`; they verify bindings and record integrity, not adequacy.
Run `scripts/check_dependencies.py` before helper execution. Do not install
undeclared dependencies. Explicit approval is reserved for external, destructive,
approval-sensitive or materially unresolved steps. Ordinary authorized local
inspection and record creation proceed without an additional approval ceremony.
