# Worked examples for the first Vera conversation

Choose examples for the professional, not a universal tour. These starter files
are entirely fictional. They are small inputs for the **actual** specialist
commands; they are not precomputed answers. The native model must read the
selected skill, inspect input meaning, review mappings, run its commands and
explain the real outputs. Do not claim an assurance review succeeded merely
because a command returned zero.

Use the prepared kit from `scripts/local_courses.py` for the selected current
Vera workflow and language. Follow
`../../learn-with-vera/references/prepared-courses.md`; the kit provides valid
fictional source files and practice inputs. Existing files in
`assets/onboarding/` are compatibility fixtures, not an alternative lesson
library. A custom example may adapt a current own-product kit when useful.

## Genuine managed case setup

The teaching chat must already have bound the pair and started the selected
lesson. In the **working** chat run:

```text
python3 <vera-root>/scripts/local_onboarding_case.py --thread-id <actual-worker-id> --workflow <selected-workflow> --token <current-lesson-token> --phase demo --source <absolute-selected-source-file>
```

Repeat `--source` for each selected input. Use `--phase practice` for an
independent new attempt after the teacher recorded the demonstration. When the
lesson updates a previous assessment, follow its same-engagement route in
`../../learn-with-vera/references/prepared-courses.md`: retain the initial case,
import its actual record and the new evidence, and start a subsequent run there.
Do not create a different client to bypass a required predecessor. The helper creates
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

## Local archive search teaching route

`studio-archive` local search indexes client folders; it does not execute a
professional calculation against a ledger run input directory. Validate the
active worker token, then stage the selected kit files with the same adapter:

```text
python3 <vera-root>/scripts/local_onboarding_case.py --thread-id <actual-worker-id> --workflow studio-archive --token <current-lesson-token> --phase demo --source-root <kit>/files/input/archive --source <kit>/files/input/archive/<client>/<file>
```

Add `--session <id>` for a repeated lesson and repeat `--source` for every
returned demonstration source. Preserve the relative client-folder tree. The
adapter returns `archive_root`, `archive_state_dir`, `archive_session_id` and
`setup_required: true`; this stages files only and is not a completed search.
It creates no false ledger run or client-engagement context.

Use the current Studio Archive local commands with both
`VERA_STUDIO_ARCHIVE_STATE_DIR` and `VERA_STUDIO_ARCHIVE_SESSION_ID` set to the
returned values for every command. Diagnose access, configure that exact staged
root, refresh, select the intended scope from the returned scope list, search
and open the actual source IDs. This explicit tutorial setup uses the known
staged folder; do not repoint the user's normal MCP archive configuration or
invoke a real-folder chooser for the synthetic setup. Explain the normal guided
folder chooser when teaching how the professional will use their own archive.

Keep the private index outside `archive_root`, at the returned state directory.
Save the actual search/open results and source-backed answer in separate local
demo and practice output files for the teacher's evidence and focus steps; an
index file or staged source alone is not the search answer. The practice adds
only the selected update to this same teaching archive, refreshes the same
index and executes a new search. Revalidate the current worker handoff before
that bounded step. Preserve the demo's result files and all source agreements.
A later professional handoff uses the ordinary Studio Archive setup and its
current user-selected folder; it does not reuse this synthetic configuration.

## Local client-folder organisation route

For `archive-organization`, use the same adapter with `--source-root
<kit>/files/input/client` and each selected `--source`. It preserves the prepared
folder structure inside a new teaching client, takes a real client-folder
snapshot and starts the normal organisation workflow against that snapshot.
Resume from the returned `tutorial_case_path`, which lives under `Vera/` and
is excluded from the source snapshot. Do not import individual documents as a
substitute for the folder snapshot.

Use an isolated Studio Archive state directory outside this client folder and
an explicit tutorial session ID consistently for the current inventory/open
commands. Configure only the teaching client's parent directory in that private
state. The snapshot input ID is the `binding_id` in the run's input binding.
Read the projected inventory and open the actual items before interpreting
their categories. Follow the current organisation procedure to prepare its
review page, save all decisions, compile the plan and obtain the user's separate
apply choice. Prepared kit files carry no review or apply approval.

Apply only to this teaching copy when authorized. Inspect the resulting paths,
retained duplicate copy and operation journal. Explain rollback with the actual
journal; do not perform it merely to make the demonstration look complete.
Practice uses its own supplied client-folder copy and a newly reviewed plan.
