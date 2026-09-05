---
name: aml-review
description: Review an Italian client's AML evidence at onboarding, periodic review, a material change or an unusual transaction; reconstruct ownership, investigate inconsistencies and prepare a sourced assessment for the commercialista.
---

# AML review

Prepare an evidence-based antiriciclaggio review for one Italian client and
engagement. Use this for substantive AML work on new or existing relationships.
New Client remains the owner of whole-client onboarding; do not repeat its
identity, engagement and privacy intake when already available. A general legal
question without a client review belongs to Vera's legal/tax answer workflow.

Read `references/professional-method.md` (relative to the module root) before
analysis and `references/record-contract.md` before using the helper. Resolve
the module root two levels above this file. The model performs the analysis;
Python checks evidence bindings, saves versioned records and optionally calls
New Client's existing arithmetic. No script detects suspicion or assigns scores.

## Evidence and investigation

Resolve material choices from actual inputs. Ask only those unresolved choices in chat;
do not introduce extra document categories unless the facts cue them.

Establish the engagement, review date, question and documents available. Reuse
the selected prior assessment rather than asking the studio to re-enter facts.
For updates, distinguish the historical assessment from new evidence; explain
what changed and which earlier conclusions remain supported, require revision,
or cannot be reassessed. Missing old evidence does not prove a change.

Read the selected originals. Cite file ID and page, clause, row or transaction
reference for material facts, including counterevidence. Reconstruct ownership
and control from supported links; do not infer the beneficial owner from a name
match, a percentage alone or the absence of another known individual.

For each material issue explain the discrepancy, competing explanations,
evidence supporting or weakening each explanation, the targeted question or
document that would resolve it, and the effect on the proposed assessment.
Keep client assertions distinct from corroborated facts. Do not equate an
unusual amount, foreign connection, missing document or indicator with suspicion.
Do not manufacture concerns when the documents provide a coherent explanation.

Use currently verified primary/professional sources for applicable obligations.
Record title, URL, locator, retrieval date and case applicability. Public legal
research uses generic topics, not client identifiers or private case text.
Screening is limited to reports supplied or explicitly selected by the studio:
record source, date, scope and match resolution. No screening connector is
included. An unperformed check is unknown, never a negative result.

Present the proposed rationale and unresolved issues to the commercialista.
Ask focused factual questions as needed, without making every missing field a
reason to stop useful analysis. Do not send requests to the client. Treat an SOS
assessment as confidential internal work: no automatic filing, no client-facing
disclosure of suspicion or contemplated reporting. Acceptance, abstention,
enhanced measures and reporting decisions remain with the professional.

## Durable work

Never write run outputs inside this Git workspace or a published directory.

In Codex, use Studio Archive with workflow ID `aml-review`: select the exact
client and engagement, import sources (including any chosen prior review),
prepare and start the run. Use only its hydrated inputs and exact output folder.
Run `python scripts/check_dependencies.py` before helpers. Write the model's
review JSON in that output folder, then run:

```bash
python scripts/aml_review.py --client-engagement <context-path> --review <output-dir>/review_input.json
```

The helper creates an immutable content-addressed JSON record and a readable Markdown
companion. Use the contract's `previous` binding for subsequent versions. Import
an earlier run's finalized record as a source in the same engagement before
reusing it. Supply a complete New Client input as optional `calculation_source_id`
only when it is available and relevant; do not fabricate the rest of an onboarding
record to obtain a score. Otherwise leave arithmetic unavailable and explain why.
Use New Client's established assessment/review process when revised scored inputs
are needed. A previous calculation is historical until its inputs are reviewed.

Professional decisions are recorded only after explicit review, with the exact
proposal digest, reviewer reference, date, conclusion, disposition of each issue
and any chosen review date plus reason. A reviewer label is not an authenticated
signature. The record is not a compliance certificate; unresolved issues remain
visible even after a decision. No automatic calendar monitoring is included.

Deliver the review memo, linked evidence and questions, calculation when available,
and recorded decisions when supplied. Use the user's language for narrative.
Follow Vera's model-data report contract, declare every output in Studio Archive,
then finalize and complete the run. Completion means delivered work, not a clean
AML opinion. If a host cannot operate the portable archive, prepare the sourced
review in chat and disclose that no durable version or decision was saved.

The local deterministic helpers use only the standard library declared in
`requirements.txt`; they do not replace model-led professional analysis.
Request explicit approval for external, destructive or approval-sensitive
steps and resolve material unknown choices. Ordinary authorized review proceeds.

## Plugin Improvement Feedback

Keep the improvement note local to chat or run artifacts.
Use Vera's shared feedback policy only if the user chooses transmission.

## Codex-Native Run UX

Use Vera's checklist, Run Intake table and Decision Table to show scope, bound
sources and unresolved choices. Give an execution checkpoint before saving.
Default output policy: the memo and version record are normal outputs, not choices
to propose. End with an Artifact Card; `codex_run_review.md` may summarize the
handoff. Never edit plugin source or generated ZIPs during client work.
