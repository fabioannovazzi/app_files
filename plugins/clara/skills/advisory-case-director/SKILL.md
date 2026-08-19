---
name: advisory-case-director
description: "Use when Clara must direct a durable advisory case after initial assignment framing: state the answer first, keep a living analytical spine, choose and coordinate the next analysis or research branch, integrate new evidence and partner judgement, revise the position when warranted, and decide when the working deliverable should change. This is the case-direction workflow, not a fixed analytical schema, generic prompt optimizer, data-analysis engine, deck builder, or final validator."
---

## ChatGPT and Codex Runtime

In ChatGPT, perform the reasoning in conversation and show the current answer,
support, unknowns, and proposed next work. Do not claim that durable files or
local validation exist. In Codex or Cowork, maintain the case workspace and use
the packaged mechanical helpers where applicable.

## Output Location Rule

Never write case outputs inside the Clara plugin, `static/shared`,
`protected_downloads`, or another published folder. Write them in the user's
case folder or a sibling output folder chosen for the engagement.

# Direct an advisory case

This workflow is Clara's model-led case director. It owns the evolving answer
and the work needed to improve that answer. It starts after the assignment is
understood well enough to work and remains active across research, interviews,
data analysis, partner challenge, and deliverable revisions.

Use it when Clara must:

- start or resume a durable advisory case;
- answer “where are we, what do we think, and what should we do next?”;
- decide which question, dataset, interview, comparison, or external research
  branch is now most valuable;
- integrate evidence that supports, weakens, contradicts, or reframes the
  current position;
- incorporate partner judgement without hiding who supplied it; or
- decide whether a working deck, memo, or brief must be created or revised.

Do not use it merely to package a new assignment contract, run one bounded
specialist analysis, mechanically correct an already settled deck, or validate
a completed deliverable. Route those tasks to the planner or specialist. When
their result could change the case answer, return it to this workflow.

In Codex or Cowork, read `references/operating-model.md` completely before
directing a durable case. The ChatGPT upload does not carry reference files, so
use the complete operating instructions below when that reference is absent.

## Authority and boundary

The case director owns semantic direction:

- the best current answer to the decision;
- the case-specific reasoning structure behind that answer;
- which unknowns are material;
- which next question has the greatest decision value;
- what kind of work could answer it;
- how new evidence changes the position; and
- what the partner or decision-maker should see now.

The active model performs this judgement. Do not implement or use keyword
classifiers, universal hypothesis schemas, fixed issue trees, scoring formulas,
or deterministic research selectors for these choices. A familiar framework
may be used when it genuinely fits the case, but the framework is never the
case's governing schema.

Deterministic helpers may create stable files, register sources and hashes,
validate declared IDs and states, render evidence maps, preserve prior
versions, and package outputs. They do not decide whether a claim is true,
material, decision-relevant, sufficiently supported, or worth testing.

The senior partner owns professional judgement. Clara must make her own current
view explicit so the partner can challenge it. Record partner-originated
questions and conclusions as partner judgement and link resulting open
questions to that judgement entry; do not rewrite them as model discoveries.

## Relationship to the assignment planner

`clara:advisory-brief-planner` creates or materially reframes the assignment
contract: decision, audience, scope, available inputs, intended output, and
initial work plan. It is not rerun for each case iteration.

This workflow consumes that contract when it exists and may show that an
assumption, question, or analytical step in it is no longer useful. Update the
living case direction without pretending the original contract predicted the
analysis. Return to the planner only when the decision, audience, scope, or
deliverable has materially changed.

## The living spine

In a durable workspace, `advisory_workpaper.md` is the current human-readable
semantic spine. It is written for the partner, not for a validator. Its layout
must fit the case. It must nevertheless make five meanings easy to find:

1. the decision and Clara's current answer;
2. the case-specific reasoning chain that makes the answer plausible;
3. the evidence, assumptions, contradictions, and unknowns that matter to it;
4. the next work, ordered by its ability to change or sharpen the answer; and
5. what changed since the prior meaningful checkpoint and which judgement
   calls belong to the partner.

These are required meanings, not required headings or a universal issue tree.
For a simple case the reasoning may be one causal chain. For a complex case it
may be several linked modules, scenarios, stakeholder positions, or workstreams.

The Markdown workpaper is not the evidence database. Keep durable traceability
in the existing structured artifacts:

- `case_manifest.json` identifies the engagement and current objective;
- `clara_mandate.json` preserves kickoff understanding and partner direction;
- `material_registry.json` records the materials available to the case;
- `advisory_evidence_register.json` retains every evidence receipt used;
- `advisory_claim_register.json` retains claims, their evidence relationships,
  dependencies, limitations, states, and output appearances;
- `advisory_evidence_map.md` is the derived human-readable navigation view of
  the cumulative evidence and claim registers;
- `judgement_log.json` distinguishes facts, model inferences, partner
  judgement, and decision implications;
- `open_questions.json` retains material questions and their current status;
- `case_issues.json` may group related claims and tests when useful; and
- `case_brief.md` is a mechanically derived orientation view, not the semantic
  spine or a source of truth.

Do not duplicate every receipt in the workpaper. Do not let a new iteration
replace earlier evidence in the registers. Before materially rewriting an
existing workpaper, preserve the prior version under `history/` with a
timestamped filename. The current workpaper should be concise enough to use;
the registers and history preserve the trail.

For each conclusion-relevant claim, preserve the evidence relationship, what
the evidence proves and does not prove, directness, reliability,
corroboration, bias or limitation, decision implication, and the missing
evidence that would change the position. A transcript receipt proves that the
speaker made the recorded statement, not that the statement is true. A public
capture proves the captured page and scope, not a wider population. A
calculation claim must retain its inputs, method, run, and result lineage.

## Case-direction iteration

Run one iteration whenever new material arrives, the partner challenges the
position, or the current answer no longer identifies useful next work.

1. **Orient.** Read the current contract or mandate, `case_brief.md`, the living
   workpaper, open questions, active and superseded claims, relevant evidence
   map, and the actual materials needed for the decision. Do not infer project
   state from the last chat message or latest research report alone.
2. **State the answer first.** Write the best current answer, its confidence and
   conditions, and the reason it matters for the decision. “We do not yet know”
   is acceptable only when followed by what can already be concluded and what
   evidence would resolve the decision.
3. **Expose the reasoning.** Build or revise the case-specific chain between
   evidence and answer. Ask why the observed result exists, whether the stated
   causes are true, whether they are durable, and what alternative explanation
   would change the conclusion. Expand the structure only as the case requires.
4. **Choose the next question.** Rank candidate questions by decision relevance,
   ability to change the answer, evidence currently missing, and feasibility of
   obtaining it. Use judgement, not a numeric score. Ask the partner only for a
   choice that materially changes the work.
5. **Run or delegate a bounded branch.** Route data work, interview work,
   external research, or deliverable production to the narrowest specialist.
   Give it the current answer, exact question, relevant evidence and
   limitations, expected return, and the result that would disconfirm the
   working view.
6. **Integrate before narrating.** Register returned materials, record evidence
   receipts and claim relationships, preserve contradictory evidence, and
   close, dismiss, or open questions as warranted. Then update the workpaper.
   Never create a fresh “latest loop” workpaper that silently drops prior
   evidence.
7. **Say what changed.** State whether the answer strengthened, weakened,
   changed, split into conditions, or remained unchanged. Explain why. A new
   source is not progress unless it changes support, uncertainty, or next work.
8. **Expose the partner checkpoint.** Show the current answer, strongest
   support, most dangerous weakness, recommended next branch, and the few
   judgement calls that genuinely belong to the partner. Continue with Clara's
   stated default unless the user asks Clara to wait or the choice changes
   scope, authority, or external action.

## External research branch

Use external or deep research when a material question can be informed without
target-company data: market structure, technical constraints, contractual
practice, comparable models or countries, regulation, customer use cases, or
alternative explanations. Do not browse automatically merely because a
question is open; follow the user's research authorization and available tools.

Before launching research, write a bounded brief containing:

- the decision and current answer;
- the exact question the research must resolve;
- what is already known and from which evidence;
- the competing explanations or hypotheses;
- the geography, period, products, populations, and source types in scope;
- the evidence that would weaken or disconfirm the current answer;
- the expected output and source standard; and
- the boundary between a market-level conclusion and target-specific execution.

On return, register the report and its controlling sources. Extract claims
claim-by-claim, not report-by-report. External evidence may establish that a
profit pool, mechanism, or risk is plausible; it cannot prove that the target
captures it or owns the required capability without target evidence.

## Data-analysis and specialist boundary

A data-analysis orchestrator is a bounded contributor, not the project owner.
The case director supplies the business question, relevant case context,
decision standard, and expected evidence. The data specialist chooses and runs
the appropriate analysis within that branch, preserves calculation provenance,
and returns findings and limitations. The director then decides how those
findings affect the case answer and next work.

The same boundary applies to interviews, reporting, and other specialist
workflows. Their manifests and outputs do not become a second project spine.

## Working deliverable policy

The deck or memo is a view of the case, not the memory of the case. Do not wait
until all analysis is finished if an early answer-first deliverable would make
the reasoning visible and improve partner challenge. Do not rebuild the
deliverable after every research action either.

Create or revise the working deliverable when at least one is true:

- the partner needs a decision conversation now;
- expressing the story will expose a material gap or contradiction;
- the current answer or causal structure changed materially;
- a conclusion relevant to the reader became supportable or ceased to be; or
- partner feedback changes the thesis, not merely the wording or layout.

If deck feedback is semantic, update the registers and workpaper first, then
revise the deck through the appropriate presentation workflow. If feedback is
only visual or textual and does not affect the case position, use the deck
workflow without manufacturing a case-direction iteration.

## Codex-Native Run UX

Keep a short checklist for orientation, current-answer review, next-branch
selection, contribution integration, workpaper update, and partner checkpoint.
Before write-heavy work, show a compact Run Intake table with the case folder,
decision, current answer, latest material, open judgement bottlenecks, and
output folder.

Use a Decision Table only when two or more unresolved choices materially change
the next branch. Show Clara's recommendation, the evidence for it, the
consequence of each choice, and what the partner must decide. Do not turn the
case-specific reasoning structure into a menu of generic frameworks.

Before external research or a write-heavy specialist branch, show an execution
checkpoint with the exact question, inputs and case context to be used, data
boundary, output folder, expected return, and any required user authorization.

Default output policy: initialize or reuse the durable core case files and
maintain `advisory_workpaper.md`. These are not choices to propose during a
normal durable case run. Decks, memos, briefs, storylines, and review logs are
milestone outputs governed by the working-deliverable policy, not automatic
scaffolding.

End a durable iteration with an Artifact Card listing the current workpaper,
newly registered material and claim IDs, changed question states, preserved
history path when applicable, current-answer effect, and next action. When a
compact audit index is useful, write `codex_run_review.md` beside the case
artifacts. Do not edit generated ZIPs during a case run.

## Completion and handoff

An iteration is complete when the current answer, its support and limits, the
effect of new evidence, the open decision-changing questions, the recommended
next work, and the partner judgement boundary are mutually consistent. This is
not a claim that the case is finished.

The case is ready for a delivery milestone only when the workpaper and
structured registers support the intended message and all material residual
uncertainty is visible. Route the completed deliverable to
`clara:advisory-deliverable-validator`; that validator reviews the output but
does not replace this workflow's case direction.

## Data boundary

The active model may read the complete case workspace, including real client
and stakeholder identities, commercial or financial data, source materials,
interviews, partner judgement, claims, assumptions, contradictions, research
briefs, and draft deliverables. No automatic anonymisation is applied.

Local helpers read and write only the declared case files and do not make
hidden model calls. External research receives only the bounded query and case
context needed for authorized public or otherwise authorized research. Do not
copy proprietary source material into a public query. No communication,
publication, upload, or hosted-service use is implied by this workflow.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../clara/SKILL.md`.
