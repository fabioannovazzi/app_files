# Worked examples for the first Vera conversation

Choose examples for the professional, not a universal tour. These starter files
are entirely fictional. They are small inputs for the **actual** specialist
commands; they are not precomputed answers. The native model must read the
selected skill, inspect input meaning, review mappings, run its commands and
explain the real outputs. Do not claim an assurance review succeeded merely
because a command returned zero.

Copy the relevant files from `<vera-root>/assets/onboarding/` below the active
lesson directory before use. Read the source files with the user. For practice,
let the user choose a change and write a separate source copy based on that
request. Other catalog workflows can use small synthetic inputs authored for
the professional's goal; inspect their current input and host contracts first.
Do not replace a complex capability with a fake local approximation to finish
onboarding. Resolve the requirement and resume the lesson.

| Starter | Possible lesson | Example natural request / professional check |
| --- | --- | --- |
| `invoice.xml` | `fatture-xml-check` | “Mi aiuti a controllare queste fatture XML?” Review date, totals, VAT and anomaly evidence; an arithmetic check does not certify deductibility. |
| `journal.csv` | `journal-sampling` | “Vorrei estrarre un campione ripetibile da questo giornale.” Confirm date/amount meanings and sample basis; a sample is not an audit opinion. |
| `actual-budget.csv` | `variance-analysis` | “Dove ci siamo scostati dal budget?” Confirm periods and signs; show amount and percentage, and distinguish arithmetic from a supported business cause. |

## Genuine managed case setup

The teaching chat must already have bound the pair and started the selected
lesson. In the **working** chat run:

```text
python3 <vera-root>/scripts/local_onboarding_case.py --thread-id <actual-worker-id> --workflow <selected-workflow> --token <current-lesson-token> --phase demo --source <absolute-selected-source-file>
```

Repeat `--source` for each selected input. Use `--phase practice` for the user's
own attempt, after the teacher recorded the demonstration. The helper creates
a separate synthetic customer folder and engagement **inside this lesson**,
imports immutable selected inputs, prepares and starts a genuine portable
Studio Archive run, and returns its real `context_path`, bound input paths and
`output_dir`. It never configures or modifies the professional's Studio Archive.
All case IDs are synthetic; do not replace them with a real client's identity.
The helper creates a new attempt per invocation; after interruption reuse the
saved `tutorial_case.json` and ledger state instead of starting another attempt.

Follow the specialist's documented commands using these returned values. For
an intake wrapper the actual ledger workflow is `client-file-preparation`.
For XML use the bound execution-input directory, not the original fixture
folder. For journal sampling, inspection and normalization use the run's
`normalization` output child and sampling uses its `sample` child. Inspect and
confirm the recipe before normalization. For variance, inspect columns,
review the proposed recipe against the small file, then run the analysis.

Retain specialist validation, model-data reports and the usual ledger finalization
and professional review stages. The portable `client_ledger` implementation
supports `finalize_run` and `complete_run` against this tutorial's `client_root`;
use it as the direct local adapter when native archive tools require the studio's
production configuration. Do not call archive setup merely to run this tutorial.
A model-data report under the marked onboarding root is local; the receipt client
returns `not_requested` / `local_onboarding`, including direct stamp retries.
Do not move tutorial reports out of that scope to obtain a stamp.

Record actual final artifact paths in `demo` or `practice`; state whether a result
is a reviewed draft or a completed reviewed run. A lesson can teach a professional
review stage, but cannot count a failed computation as a successful demonstration.
The teacher assesses user understanding; scripts enforce only evidence identity
and the requirement for distinct demonstration and practice outputs.
