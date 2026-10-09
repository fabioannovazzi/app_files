> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Standalone work without client registration

Use this route when the user selects standalone work or clearly requests one
invoice, contract analysis, legal/tax question or answer review without ongoing
client-practice or archive continuity. State the inferred scope and proceed; the
user need not name the route. Respect an established choice to archive the work. It does not support ledger-dependent accounting
engines, filing, signatures or submissions. A standalone task is not a registered
client, a completed Archive run, or professional approval.

Explain once: sources and outputs remain in the chosen task folder until the user
removes them; no client/engagement is registered, no archive is configured, and
later Archive adoption is a separate explicit action. This is durable task storage,
not a promise that the host, model provider or backups delete data. Model processing
and Vera's actual model-data report/receipt contract still apply.

Reuse the user's selected writable work folder outside plugin source, Git and
published directories. If no destination is available, ask only for the destination
or use the host's already-authorized task workspace; do not open the studio archive
chooser. Select a new labelled task subfolder. Claude performs all commands, including
Cowork's existing managed Python route; users do not run Terminal or edit JSON.

Run from Vera's root after the maintained dependency setup for the selected module:

```bash
python scripts/standalone_work.py --destination <new-absolute-task-folder> \
  --workflow <invoice-xml|prompt-optimizer|deep-research-validator> \
  --source <explicitly-selected-absolute-source> [--source <another-source>] \
  --label <task-label> --purpose <actual-purpose>
```

The helper preserves originals, captures at most 32 selected files (64 MiB each,
256 MiB total), and returns a distinct `vera.standalone_workflow_context.v1` with a
`task_...` ID, receipted inputs and exact output paths. Keep every selected page;
source selection and meaning remain model/professional judgments. Retain a failed
partial task for inspection; never silently overwrite it or infer a successful retry.

Pass this task's `context_path` to the maintained engine's existing
`--client-engagement` argument; that argument accepts this separate task schema only
for the three supported engines. Use its `input_dir` and `output_dir`. No client ID
is created or invented. Source mutations, extra input files, foreign workflow
contexts and output escape are rejected. The ordinary invoice proposal, source
qualification, preview, XSD/arithmetic checks and exact export approval still apply.

For a legal-answer journey, create a prompt-optimizer task with the question and
selected source files. Generate and review using the unchanged answer contract and
shared journey. Create a separate deep-research-validator task with the generated
answer and selected support sources, then inspect/validate and, when required,
perform the opposing examination. Copy selected prior artifacts as explicit sources;
never claim same-engagement upstream reuse. Keep both task links in the final result.

Store and show the real model-data report in each task's output folder. Link the
answer or XML and its checks directly, after all required professional review gates.
Do not call Archive finalize/complete for a standalone task, and do not report
archived client continuity or SdI acceptance. A later request reopens the retained
artifacts and rechecks source receipts; it does not recreate a client or rerun the
analysis merely to show the result.

Without local scripts, continue the shared in-chat preparation/review fallback and
state that no validated XML or durable local task was created.
