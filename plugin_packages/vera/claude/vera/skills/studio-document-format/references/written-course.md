> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Written Cowork course

Cowork does not have the native teacher/worker pair or its tutorial-case adapter.
Use the installed written course route, not a fabricated voice session or token:

```text
python <vera-root>/scripts/local_courses.py list
python <vera-root>/scripts/local_courses.py prepare studio-document-format --language <it|en|fr|de|es> --output-dir <fresh-private-course-folder>
```

Read the returned `course-provenance.json`, `teacher.md` and actual source files.
Verify `product` is `vera`, `workflow` is `studio-document-format`, `mode` is
`cowork-written-single-conversation`, and that selected files match their exact
hashes in `prepared_artifacts`. Preparing a kit records no execution, learner
understanding or adoption. Retain its `.vera-onboarding-local-only` marker.

For each demo/practice attempt, create a fresh ordinary private directory beside
the prepared course folder, with `inputs` and `outputs` children. Keep generated
outputs outside the prepared kit; add `.vera-onboarding-local-only` to this
attempt directory too. Copy only the phase's
explicit `source_files` or `practice_files` into `inputs`, checking bytes against
the prepared hashes. Vera writes `tutorial_case.json` in this attempt directory:

```json
{
  "tutorial": true,
  "local_only": true,
  "phase": "demo",
  "workflow_id": "studio-document-format",
  "directory": "<absolute-attempt-directory>",
  "output_dir": "<absolute-attempt-directory>/outputs",
  "inputs": [{"path": "<exact-copied-specification>", "sha256": "<actual-file-sha256>"}],
  "status": "prepared",
  "mode": "cowork-written-single-conversation"
}
```

Use `practice` only after the real demonstration was executed and explained.
This is an operator-attested written project descriptor, not a native paired
worker receipt. Never apply it to a Claude lesson to bypass its bound adapter.

Run `practice-materials` on the copied specification, with a fresh child of
`outputs` as its destination. Initialize the fictional studio workspace in
another child of `outputs`, then execute the skill's normal inspection,
proposal, preview and user-adoption steps. Ask for genuine learner decisions.
After actual adoption, `report-case` consumes this descriptor, the generated
CSV and approved studio workspace and creates its separate real synthetic
client run. Follow the financial report procedure with its returned input and
output bindings; keep model-data evidence and receipts local for this tutorial.

Open and explain actual Word outputs in the conversation. Update
`lesson-progress.md` from actual demonstration/practice outputs, review choices,
and learner participation. Keep incompleteness visible; neither prepared source
files nor an approval flag set by Vera are learner acceptance. The learner can
stop the lesson and request ordinary work at any time.
