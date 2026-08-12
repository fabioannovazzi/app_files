---
name: apertura-pratica
description: Use when Lucia must open a new legal client or a new matter for an existing client from supplied facts and documents; inventory evidence, map parties and roles, prepare conflict-check candidates, engagement scope, possible deadlines, confidentiality, conditional AML, privacy/retention posture, missing-information requests, and a reviewable matter-file plan. Do not use it to clear conflicts automatically, accept an engagement, calculate a binding deadline without lawyer confirmation, move original files, or manage an already-open matter.
---

# Apertura pratica

Read `references/workflow-method.md` and
`references/italian-professional-boundaries.md` completely before starting.
Treat `../../../references/source-registry.json` as a currentness-controlled
research starting point, never as a deterministic legal rule table.

## Surface contract

In Claude, prefer the durable Studio Archive client/engagement lifecycle exposed
by Lucia. Prepare and start an `apertura-pratica` run, then use only its exact
input view and output directory. In Cowork or another connected-folder surface
without that ledger, create one fresh private standalone run and keep all
receipts and outputs inside it.

In ChatGPT, use supplied materials to produce a useful lightweight intake in
chat. Do not claim that files were snapshotted, a conflict register was
searched, durable decisions were saved or a practice was opened when those
operations did not occur.

Never write run outputs inside this Git workspace. Run the dependency check
from the resolved component root before helper scripts:

```bash
python scripts/check_dependencies.py
```

Use the package's declared `requirements.txt`; never install dependencies at
runtime. If a declared helper requirement is unavailable, continue with the
file-based contract when possible and report the limitation.

Reserve explicit approval for external, destructive, approval-sensitive, or
materially unresolved steps. Ordinary read-only intake, local analysis,
evidence validation and review-package generation continue without ceremonial
confirmation prompts.

## Intake

Infer safe defaults and ask only material choices that change the matter:

- new client and new matter, or new matter for an existing client;
- client and assisted-party identity;
- requested work and objective;
- known urgency, jurisdiction and procedural posture;
- exact client/matter register available for the conflict check.

Generate the choices from the actual inputs. Ask only those unresolved choices in chat.
Do not offer named remedies, authorities or document types unless the facts cue them.

Do not require the user to know internal schemas or workflow names. Missing
facts produce explicit `partial` or `blocked` states.

## Workflow

1. Create a fresh run:

   ```bash
    python scripts/initialize_workspace.py <private-run-dir> \
     --opening-mode <new_client_new_matter|existing_client_new_matter> \
     --client-reference <stable-reference> \
     --matter-reference <stable-reference> \
     --language <it|en|fr|de|es>
   ```

2. Add every selected document as immutable evidence. The script copies exact
   bytes, rejects links and drift, records SHA-256 and never alters the source:

   ```bash
   python scripts/add_evidence.py <run-dir> <selected-file> \
     --role <client_supplied|firm_record|authority|correspondence|other>
   ```

3. Inspect only the selected evidence. Use model-led reasoning to complete
   `matter_intake.json` against `schemas/matter_intake.schema.json`. Keep every
   ambiguity and missing premise visible. Never fabricate a register search,
   professional decision, engagement acceptance, source, date or document.

4. Prepare the specialised review package:

   ```bash
   python scripts/prepare_review.py <run-dir>
   ```

   This produces the intake memo, missing-information request, folder plan,
   validation report, review payload and artifact manifest. It does not invoke
   Deep Research Validator. When the package includes a separate substantive
   legal analysis, validate that analysis independently before attaching it.

5. For a multi-item review, use the local workbench:

   ```bash
   python scripts/review_server.py <run-dir>
   ```

   The workbench persists `pending_review_decisions.json`. If it cannot run,
   collect the same item decisions in chat and write a schema-equivalent JSON
   file only after explicit user confirmation.

6. Apply only decisions bound to the current intake:

   ```bash
   python scripts/apply_review.py <run-dir> <pending_review_decisions.json> \
     --confirmed-by-user
   python scripts/validate_run.py <run-dir>
   ```

   Any intake change makes prior review receipts stale. Never edit a receipt or
   digest to make it current.

## Review boundary

The four required scopes are `conflict`, `engagement`, `deadlines` and
`opening`. The lawyer reviews the exact parties and register scope, engagement
and exclusions, deadline candidates, and overall readiness. The validator may
enforce evidence closure, hash integrity, reference closure, required decisions
and receipt freshness. It must not overrule the lawyer on meaning,
applicability, conflict, deadline or strategy.

Saved review state, applied scope receipts and the final artifact list remain
separate and bound to the current intake digest.

No original file is renamed, moved, deleted or overwritten. `folder_plan.json`
is a proposal for a later approved organization action.

## Handoff

Finish with `review_handoff.md` and an Artifact Card containing the run directory, current status,
intake memo, missing-information request, review payload, review receipts,
validation report and exact next action. State separately whether the dossier
is `blocked`, `partial`, `ready_for_review` or `ready_to_open` and why.

## Cowork-native Run UX

1. Show a checklist for dependency readiness, intake, selected evidence, party
   map, conflict-search posture, engagement, deadlines, confidentiality,
   conditional AML, privacy/retention, professional review and validation.
2. Show a Run Intake table with opening mode, opaque client and matter
   references, jurisdiction, urgency, selected input count, private output path
   and current status.
   Before a long or write-heavy stage, show an execution checkpoint with the
   selected inputs, private output directory and expected review artifacts.
3. Present unresolved professional items in a Decision Table with scope,
   evidence basis, proposed next action, blocker status and lawyer decision.
   Values already proved by the inputs are facts to preserve, not choices to propose.
4. Default output policy: keep every artifact in the exact private run output
   directory and never write client or matter content into the repository.
5. Maintain `run_review.md` as the compact human-readable progress and
   blocker summary. Finish with the Artifact Card defined above.
6. Any generated ZIPs are optional handoff copies only. Create one only when the
   user requests it, exclude credentials and session material, and keep the
   unpacked digest-bound run as the source of truth.
