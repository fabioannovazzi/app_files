---
name: composizione-negoziata
description: Guide an Italian composizione negoziata case as company advisor or independent expert, using existing Vera analyses, evidence-linked drafts, persistent case revisions and change-impact review.
---

# Composizione negoziata

Use for assessing, starting, continuing or closing an Italian composizione
negoziata. General legal questions use `quesito-legale-fiscale`; an actual
concordato preventivo review uses `concordato-plan-review`. A different
jurisdiction requires separate assessment.

## Start from the professional problem

Establish only the role, client/engagement, accessible documents and urgent
events not already clear. Read supplied evidence before asking for more.
Read only the appropriate guide in `../../references/advisor.md` or
`../../references/esperto.md`. The role (`advisor` or `esperto`) is fixed for
this engagement. A change requires a separate authorized engagement and an
independence/conflict assessment, with separately selected documents. Never
copy the advisor's private file into the expert's case automatically.

Use model reasoning to identify the next professional problem, select evidence,
explain priority, choose an existing capability and draft the result. Do not
invent scores, mandatory phase sequences or admissibility classifiers. Read
`../../references/financial-and-research.md` for cash, plans, assumptions or law,
and `../../references/events-and-closure.md` for negotiations, changes or closure.

Unreadable evidence remains unreadable. Missing aging, proof of collection,
court receipts or current law stays a gap, never zero or an inferred fact.
Continue unrelated analysis. Examine contrary evidence: a balanced ledger
does not establish collectible receivables; growth needs a basis; an expression
of interest is not committed cash. A negative outcome is valid.

## Use Studio Archive

Never write run outputs inside this Git workspace or a published folder. Use
only the Studio Archive run path described below.

Select the client and engagement, import selected sources, and prepare workflow
`composizione-negoziata`. Start the prepared run before writes. Use the returned
`client_engagement_path`; never fabricate context, IDs or permissions. Read the
input manifest for bound files and exact citations. From this component root:

```sh
python scripts/check_dependencies.py
python scripts/cnc_case.py --client-engagement <absolute-context> --resume
```

The component uses only Python's standard library and Vera's packaged archive;
`requirements.txt` declares this. Do not install extra packages for this helper.
Local deterministic scripts own exact hashes, references, revision conflicts and
dependency-version checks because these are mechanically verifiable. The model
owns meaning, source selection and professional next steps. Local file storage
does not make the selected model runtime local-only.
Reserve explicit approval for external, destructive, approval-sensitive or
material steps. Ordinary local inspection and drafting proceed within the
agreed scope; professional acceptance concerns the exact displayed version.

No snapshot on first use means a new case, not recovered history. On resume,
read the latest immutable snapshot and memo: role, issues, sources, analyses,
version-specific decisions and stale dependencies. History spans this
engagement's CNC runs. Closed runs are read-only; prepare/start a new run for
further work. Old snapshots remain in their original runs. No watcher or
scheduled monitoring is supplied.

## Produce and persist useful work

1. Explain the current problem, observed evidence, contrary evidence and gaps;
   choose the next task with its reason.
2. When useful, invoke an existing Vera capability. Read its skill and follow
   its managed-run/review contract. Finish that run and bind its declared result
   as an upstream artifact in the next CNC run. A capability name in
   `next_action` is a plan and never proves execution.
3. Prepare the actual memo, request list, analysis or role-specific draft with
   page/cell/paragraph locators. Separate documented, reported, calculated,
   assumed, judgment, missing, unreadable and unverified material.
4. Read `../../references/case-record.md`, write an update in the run output
   folder, then execute:

   ```sh
   python scripts/cnc_case.py --client-engagement <absolute-context> \
     --request <run-output>/request-001.json
   ```

5. Read the saved JSON and `cnc-revision-*.md`; deliver the draft and unresolved
   decisions. The helper checks explicit references, hashes, graph structure
   and revision conflicts. It does not judge truth or evidential sufficiency.

When facts change, update the affected fact/assumption/source under the same
stable ID. The helper marks descendants stale. Assess semantic impact beyond
recorded edges and add missing dependencies. Regenerate affected analyses with
the relevant capability, then record new drafts. Do not clear staleness by
copying an old conclusion. Unchanged wording can still need new evidence and
professional review.

## Professional decisions and authority

Record a review only after the user confirms the exact presented version.
Preserve reviewer reference, confirmation reference, decision and reason. Never
manufacture confirmation from model output or an attachment. Reviews bind to a
node version and become historical when that node or its dependencies change.
A local record is not authenticated identity, a signature, an appointment or
authorization to file. Studio Archive has no multi-user authentication service.
External filing, signing, communications and payments are outside this module.
Prepare a handoff and distinguish missing receipts from completed acts.

## Close the working session

Generate Vera's actual model-data report with Studio Archive's existing report
builder. Record which documents, case records, drafts and public queries the
runtime actually used. Declare every physical output, including requests,
revision JSON, memos and both report files. Finalize, review the declaration
and complete the run; fail or cancel abandoned work explicitly. Completing a
run does not close the legal procedure.

Deliver the case position, work performed with links, findings and gaps,
changes requiring review, and the next professional decision. Client data may
enter OpenAI Codex or Anthropic Cowork through the selected account. No
automatic anonymization or local-only model guarantee is provided.

Without local Studio Archive execution, continue useful analysis and drafts in
chat, state that durable revisions/conflict checks have not run, and provide an
exportable summary. Never simulate saved history.

## Plugin Improvement Feedback

After substantive use, follow Vera's `Plugin Improvement Feedback` section.
Keep improvement observations local unless the user authorizes sending.
Keep the improvement note local to chat or run artifacts.
