# Release one developed operation as its own skill

The browser-automation skill owns teaching, development, tests and repairs.
An ordinary user invokes a separately named operation, such as a skill for
downloading received invoice XMLs from a specified system. Its name and description
must distinguish that job from other jobs on the same website.

The developer authors this skill after reviewing the supported behavior, result
checks and limits. Local qualification is test evidence; it does not generate,
publish or advertise a new skill. The developer releases the skill through the
normal source review, package tests and existing Marketplace release procedure.

## Produce the source handoff

Keep the exact process ID from the development loop. Register the developed
executable version and its actual release evidence using `process-lifecycle.md`.
Write one reviewed skill specification with these text fields:

```json
{
  "name": "system-received-invoice-download",
  "description": "Download received invoice XMLs for the selected client and period in the named system. Excludes issued invoices and accounting registration.",
  "display_name": "Download received invoice XMLs",
  "short_description": "Save and reconcile received invoice XMLs for a client and period",
  "default_prompt": "Use $system-received-invoice-download to download this client's received invoice XMLs for the selected period.",
  "instructions": "Vera downloads the selected received invoice XMLs and reconciles saved files with the observed invoice population. Specify the client and period; review any missing or duplicate files before relying on the result.",
  "result_checks": "Compare each saved XML's invoice identity with the requested population. Report missing, duplicate and unexpected invoices; a matching file count alone is insufficient.",
  "model_data": "Describe this exact procedure's observed browser data, output fields read by the model, locally retained artifacts and external feedback projection after inspecting its implementation."
}
```

This illustrates the authoring fields, not a ready-made production operation.
Replace every field with the actual system, scope, checks and reviewed data path.
Semantic scope and the decision to support an operation belong to the author;
the exporter checks file identity and structure, not professional correctness.

```bash
python scripts/process_skills.py export --process <persistent-process-id> \
  --input <reviewed-specification.json> --output <vera-source>/skills
```

The result is `skills/<name>/SKILL.md`, its UI/Marketplace card, `process.json`
and the exact `capability.json`. The shared executor stays in the browser module.
The folder is reviewable source. Export refuses to overwrite an existing skill;
revise an existing operation through a reviewed source change, preserving its name
and process ID and increasing its procedure version when execution changes.

Review the generated skill, its supported examples and exclusions, and its
function-specific result/data instructions. Add its public explanation page and
privacy evidence as required by the product release rules. A supported operation
needs representative acceptance evidence; two repeated cases alone do not show
all accounts, branches or populations work. Do not ship scaffold or demo skills
as professional operations.

The existing Codex, ChatGPT-upload and Cowork builders include the source skill.
ChatGPT's public card and root route are assembled from its adjacent authored
`marketplace-card.json`. A broken procedure binding or collision with another
public skill fails packaging. Run the normal release checks before publication.

## Ordinary use and later repairs

The user may invoke the named skill explicitly or ask for its described work.
Vera's ordinary skill router selects among installed named skills, not unpublished
development records. The selected skill calls `process_skills.py begin`, which
loads only its adjacent binding and pins that version. Same-site procedures and
newer local development drafts cannot silently replace it.

Read `ordinary-use.md` for execution, local qualification, result delivery and
failure handling. The ordinary user never supplies an internal path or process
ID. A failure retains the selected process identity for the existing CR loop.
Fixes update the same named skill; publication and local retesting remain distinct.
