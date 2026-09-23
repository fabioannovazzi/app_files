# Questions and resumable work

Use the local matter record when missing facts affect a document task or when a
multi-step matter benefits from saved progress. Choose the stages from the actual
assignment; a practice-area name does not itself decide the needed evidence.

After preparing the selected evidence pack:

```bash
python scripts/legal_matter.py init --run-dir <run> --kind documenti --purpose "Obiettivo concreto dell'incarico"
```

Read `matter.json` and `scripts/legal_matter.schema.json`. Write proposed changes
to another JSON file. `stages` contain id, label, status (`pending`, `done` or
`not-required`), explanation and output paths relative to this run. `questions`
contain id, question, why it matters, the stage IDs it blocks, status (`open`,
`answered`, `not-needed`), answer and any exact citations to the selected evidence.
Record the actual source of a conversational answer; do not invent a file citation.

Lucia decides which fact matters and which steps depend on it. Code only enforces
the declared dependencies and verifies file/quote integrity. Do not label every
missing item as a blocker. Continue independent work while asking focused
questions; use native choices or chat, not JSON questions addressed to the lawyer.

Save updates with the revision read from the current state:

```bash
python scripts/legal_matter.py save --run-dir <run> --state <proposed-state.json> --expected-revision 0
python scripts/legal_matter.py status --run-dir <run>
python scripts/legal_matter.py render --run-dir <run>
```

Do not directly overwrite `matter.json`. History preserves prior questions and
answers; stale updates are rejected. If evidence has changed, prepare a new
evidence run rather than silently altering its snapshots. Retain the previous run
and explicitly carry forward still-supported answers with their origin.
Saves are serialized and replace the current record only after validation. After
an interrupted save, an identical history snapshot can be reused. If a hard
process crash leaves `matter-save.lock`, first verify that the writer has stopped
and inspect the current revision/history; remove only that stale lock, then retry
from the current revision. Never erase the state or history to force an update.

On resume read `status`, the state and its referenced outputs. Ask only unresolved
questions. A changed/missing result is not a previously verified current artifact.
Mark a stage done only after its actual output exists and its blocking questions
are resolved. A conditional step may be not required only with a stated reason.

Deliver `matter.html` with the actual work products when this record is used.
It shows questions, answers and outputs; it is not proof of legal completeness or
the lawyer's approval. Preserve conclusions and limitations in the work products
themselves, not only in the progress record.
