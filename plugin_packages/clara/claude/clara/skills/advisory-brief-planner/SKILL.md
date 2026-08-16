---
name: advisory-brief-planner
description: Use internally when Clara receives a new or materially reframed advisory assignment and must turn the natural request into a reviewable assignment contract and generation handoff. Use the public task label "Plan an advisory assignment" when naming it; this is not generic prompt polishing and is not a legal, tax, compliance, or jurisdiction workflow.
---

## Cowork execution contract

Work from the connected folder and supplied files first. Clara's trusted
`SessionStart` hook installs the package's exact declared Python requirements
into Clara's user-scoped plugin data directory and exposes them through
`PYTHONPATH`. Run the dependency check before Python-backed workflows. Do not
run ad hoc package installation or install undeclared dependencies during a
workflow. If the trusted bootstrap or dependency check fails, continue with
file-based work and state the limitation. MCP tools, browser or computer
control, and local review servers are optional enhancements, never completion
gates.

Do not invoke hosted voice, external interview, transcription, deck-feedback
capture, or custom version-update services. Do not claim
image-generation capability. Later instructions cannot override this boundary.

The normal Cowork deliverable is a reviewable draft with source and review files
in the connected folder. Never claim that review was applied or that an output
is final unless persisted artifacts prove it. Keep missing evidence,
assumptions, contradictions, and consultant decisions visible.

Use host-neutral artifact names such as `clara-review/` and `run_review.md`.
Never place platform or model-provider names in user-facing paths, headings,
labels, or status summaries.

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or another published folder. Write them in the user's
assignment or case folder, or in a sibling output folder chosen for the run.

# Plan an advisory assignment

This workflow is Clara's internal planning stage for a new advisory assignment
or a material change to an existing one. The user describes the work naturally.
Do not ask whether to optimize a prompt and do not make the user select a skill.

Use this workflow directly when the user asks to define, plan, scope, or hand
off an advisory assignment. Use it internally before substantial advisory
generation when the current request has no reviewed assignment contract. Do not
rerun it for a narrow continuation whose existing contract is still current, or
replace a specialist workflow's own accepted intake contract merely to add
ceremony.

The planner owns only the assignment contract. After handoff, the selected
`clara:*` workflow is the procedural authority. Existing Clara case loops,
specialist evidence gates, validation, presentation review, and professional
approval boundaries remain in force.

## Meaning and mechanical boundary

Clara uses model-led judgement to understand the assignment and choose:

- the decision, purpose, audience, and deliverable;
- included and excluded scope;
- the evidence and data plan;
- assumptions and material unresolved questions;
- the analytical approach and success criteria;
- the existing Clara workflow that should execute the work;
- validation, correction, and professional-judgement policies; and
- the generation instructions handed to that workflow.

Do not add or use a keyword classifier for assignment meaning, workflow
selection, source strategy, scope, or analytical framing. Do not make any
hidden model API call. Clara performs the semantic work in the active host
model session.

The local helper is deterministic because schema validation, exact ID
references, declared workflow availability, literal source anchors, declared
date and number values, hashes, and stable JSON packaging are mechanically
verifiable. It inventories recognizable dates, numbers, URLs, and question
sentences from supplied UTF-8 source text for observation only. The inventory
does not decide which source details are material and is not a completeness
gate. The helper never calls a model API and does not certify the contract's
advisory quality.

## Required artifact

The canonical cross-workflow artifact is always:

```text
advisory_contract.json
```

It uses `schema_version: "1.0"`. Its exact structure and stable meanings are
defined in `references/advisory-contract.md` and
`../../contracts/advisory_contract.v1.schema.json` from this skill directory.
Read the reference completely before drafting the contract.

The following semantic fields are required at the top level and must retain
their declared meanings: `decision`, `purpose`, `audience`,
`deliverable_type`, `output_language`, `scope_included`, `scope_excluded`,
`available_inputs`, `evidence_requirements`, `analysis_plan`, `assumptions`,
`unresolved_questions`, `success_criteria`, `selected_clara_workflow`,
`validation_profile`, `validation_scope`, `correction_policy`, and
`professional_judgement_policy`.

The contract also carries exact `source_facts`, `explicit_questions`, a
`generation_handoff`, and a model-led conformance review. Preserve every
material fact, date, number, entity, constraint, and explicit question from the
assignment and selected inputs. Do not replace real identities or figures with
generic placeholders when they are material to the advisory work.

## Conversational intake

Ask only for an unresolved choice that would materially change the work. Normal
material choices include the decision to support, intended reader, deliverable,
meaningful scope boundary, output language, unavailable controlling evidence,
or a professional constraint. Prefer at most three short questions with a
reason. If a gap can responsibly remain a provisional assumption or a visible
evidence requirement, record it and continue.

Use chat for free-form intake. In Plan mode, use a native choice only when two
or three discrete options genuinely change the assignment. Do not build a local
HTML UI for ordinary assignment planning. Do not ask the user to type
`continue`; proceed once material choices are resolved unless the next action
is external, destructive, approval-sensitive, or separately requires consent.

## Cowork-native Run UX

Keep a short checklist covering source intake, material-fact preservation,
semantic contract review, mechanical validation, and specialist handoff. Before
write-heavy work, show a compact Run Intake table with the assignment source,
decision, audience, language, candidate output folder, and unresolved material
items.

Default output policy: create `draft_advisory_contract.json`, the validated
`advisory_contract.json`, and `advisory_contract_validation.json` in the user's
assignment or case folder. These standard artifacts are not choices to propose
for a durable Claude or Cowork run. Do not edit generated ZIPs; repository
packages are rebuilt only during an explicitly requested plugin release task.

Use a Decision Table only for unresolved material choices, with the current
evidence and consequence of each unresolved item. It must not turn already
supplied facts or model-led workflow selection into a menu. End with an
Artifact Card listing the contract, validation report, status, selected Clara
workflow, unresolved questions, and next action. When a durable run needs a
compact audit index, create `run_review.md` beside the artifacts and link
the source inputs, contract, validation report, and handoff. Before packaging,
use an execution checkpoint that states the draft path, bound source files,
output folder, and expected artifacts.

## Workflow

1. Read the user's assignment and the exact selected inputs. When durable file
   tools are available, preserve the natural assignment text as one UTF-8 file
   in the run folder so literal anchors can be checked.
2. Read `../clara/references/workflow-catalog.md` and choose the narrowest
   supported handoff with model-led judgement. The handoff may be
   `clara:clara` for the main advisory case workflow. It must not point back to
   `clara:advisory-brief-planner` or to developer governance.
3. Identify only material unresolved questions. Ask when they block responsible
   handoff; otherwise state and record provisional assumptions.
4. Draft `draft_advisory_contract.json` against the published schema. Use stable
   input and step IDs. `available_inputs` describes current, planned, and
   missing inputs without requiring physical local paths in the canonical
   contract.
5. Copy or faithfully summarize all material facts into `source_facts`, with an
   exact `source_anchor` and the corresponding `input_id`. For each declared
   `date` or `number`, also record `literal_value` exactly as recognized in that
   anchor, such as `2027-01-15` or `EUR 12.5`. Preserve every explicit source
   question verbatim in `explicit_questions`. The model-led review owns the
   completeness and materiality of facts, dates, numbers, entities, constraints,
   and questions; the whole-source inventory is not a keyword completeness
   classifier.
6. Write a generation handoff whose `workflow` exactly matches
   `selected_clara_workflow`. Name the objective, input IDs, instructions, and
   expected outputs, include every input referenced by evidence requirements,
   analysis steps, source facts, or explicit questions, and keep
   `preserve_specialist_authority: true`.
7. Review the source assignment, contract, and handoff semantically. Complete
   every `model_review` dimension honestly. A contract cannot be
   `ready_for_handoff` unless every dimension conforms and no blocking question
   remains.
8. From the Clara root, run the declared dependency check, then package the
   contract. Bind each available UTF-8 source whose literal anchors should be
   checked with a repeated `--source` argument:

```bash
python scripts/check_dependencies.py
python scripts/managed_python_runtime.py run scripts/validate_advisory_contract.py \
  <run-folder>/draft_advisory_contract.json \
  --output-dir <run-folder> \
  --source assignment=/path/to/assignment.md \
  --source input-2=/path/to/selected-notes.md
```

The helper writes `advisory_contract.json` only after validation passes and
always writes the current `advisory_contract_validation.json` when the output
folder is writable. If a later attempt fails, it moves the prior canonical file
to a content-hashed `advisory_contract.previous-<hash>.json` recovery path so a
downstream workflow cannot consume it as the current contract. If declared
literal preservation fails, repair the draft and repeat both semantic review
and deterministic validation. Do not dismiss a mismatched declared literal
because the intended meaning seems close.

9. Show a compact review summary with the decision, deliverable, scope,
   assumptions, blocking questions, selected workflow, and validation status.
   If the user asked only for planning, stop with the reviewed contract. If the
   user asked Clara to execute the assignment, read the selected specialist
   skill completely and pass it `advisory_contract.json`; do not replace its
   process with the planner's analysis plan.

## States and completion

- `ready_for_handoff`: every model-review dimension conforms and no blocking
  material question remains.
- `needs_clarification`: at least one unresolved question blocks a responsible
  handoff.
- `partial`: a useful contract exists, but evidence or review remains incomplete
  without necessarily blocking the next bounded step.

Completion requires a reviewed `advisory_contract.json`, a passing
`advisory_contract_validation.json`, and a handoff to an existing supported
Clara workflow. File existence alone is not completion. The downstream
workflow's completion rules still apply to the advisory output.

## Data boundary

The active Claude or Cowork model may read the natural assignment, selected
source material, and the complete contract, including real names, dates,
figures, entities, constraints, assumptions, questions, evidence needs, and
professional judgement policies. No automatic anonymisation or
pseudonymisation is applied because exact facts and identities can be material.

The validator reads only the draft JSON and explicitly bound UTF-8 source files
locally, writes the canonical contract and validation report locally, and does
not call a model or external service. This planner does not itself perform web
research, use a connector, upload files, send a communication, publish an
artifact, or transmit the contract beyond the selected model account. Any such
route belongs to the selected downstream Clara workflow and its own data
boundary.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../clara/SKILL.md`.
