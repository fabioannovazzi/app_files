---
name: mparanza-avviso-intake
description: Use when creating a first intake memo for notices, agency communications, avvisi, cartelle, HMRC letters, or Swiss cantonal tax letters found in a customer folder, extracting practical references.
---

## Cowork execution contract

Select the exact files needed for this request. Folder access does not select
all its contents: if the task needs two files in a folder containing four, use
only those two. Resolve genuinely ambiguous choices with the user; reuse clear
choices without another confirmation.

Before parsing documents or creating a client, engagement or run, call
`check_studio_import_sources` with all selected paths on the actual importer
host. It needs no configured Archive and creates no records. If the MCP tool is
unavailable, use the packaged `check-import-sources --source-path <path>` CLI
through the maintained managed launcher on that same host (repeat the flag per
file). A cloud-shell `ls` is not proof of access by a computer-side importer.
Readable attachments, including `/mnt/user-data/uploads/` paths when the importer
can read them, continue directly without requiring a connected computer folder.

If files are unavailable, explain the cause immediately before creating anything:
"The file is in the chat, but the import tool looks for it on your computer."
Do not keep trying that same inaccessible path. Use this recovery sequence:

1. Inspect the host's actual callable file-transfer capabilities and the already
   connected folders. Reuse an authorized ordinary working folder outside the
   managed `Vera/engagements/.../inputs` tree. Offer **Add folder** from the **+**
   menu only when the current host offers it; otherwise explain the available
   connection method. Ask for a folder only if an accessible destination is needed.
2. With a supported bridge, copy only the selected original attachments to that
   folder as files. Compute each original SHA-256 through the host file tools.
   Do not recreate CSV text, convert encodings or line endings, relay document
   contents through model-authored tool arguments, guess a mount translation,
   overwrite a different file with the same name, or scan unrelated folders.
   A verified byte-for-byte copy may reuse its destination on retry.
3. Check the actual destination paths with `check_studio_import_sources`, passing
   `expected_sha256` as the original hashes in the same order as `source_paths`.
   The CLI takes one `--expected-sha256` per source. Archive hashes the destination
   locally and returns `ready=true` only when all supplied original hashes match.
   If no byte-preserving host transfer is available, say so and ask the user to
   save the original selected files to the accessible working folder; then verify
   them. Do not promise a bridge operation that is not callable.
4. Only after all selected sources are ready, select/create the client and
   engagement and import each through `import_studio_client_document` (CLI
   `import-document`). Pass that file's `expected_sha256` / `--expected-sha256`
   when a transfer was required. The importer checks it again during copying and
   creates the input ID and SHA receipt itself. Never manually populate `inputs`.

The path importer does not itself fetch chat attachments. Direct attachment use
requires actual importer access or a demonstrated host transfer. If neither an
importer-side check nor transfer is callable, explain the missing capability
before creating records; do not create a cloud-only replacement for a local Archive.

On any later import failure, disclose the existing `client_id` and `engagement_id`
and resume those same records. A folder-name collision calls for inspecting the
returned existing scope and reusing it when its identity matches; never clear old
folders or change the client's name just to get past the error. A deliberately
separate synthetic test may have a distinct name; retries retain their identities.
Documentless client work needs no file check. Standalone workflows check access
on their own execution host and do not require Archive or a computer folder when
that engine can read the inputs.

Public workflow names select skills; component IDs select module paths.
`financial-report-builder` uses component `report-builder`, `vouching` (historically
called Check Entries) uses `check-entries`, and `purchase-invoice-review` uses
`passive-invoice-audit`. These component IDs are not additional workflows.

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, financial-report-builder and vouching only, optional cache
cleanup uses the corresponding component ID from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
This supported maintenance command is the only cache-cleanup exception to the
prohibition on editing the installed tree by hand. It is optional: ordinary
validation and execution tolerate incidental bytecode without removing it.
On a read-only installation, skip cleanup. If the command reports a permission
error, retain that error and continue the ordinary validated workflow when its
checks pass; do not chmod, delete files manually, copy or patch the installation,
or bypass the host's permissions to make cleanup succeed.
If `validate_implementation_tree` ever fails with a file/directory-contract
mismatch, do not delete or modify files inside the installed plugin tree by hand
and do not bypass a sandbox/permission rejection to do so. Stop and report the
exact error instead.

Work from the connected folder and supplied files first. Before a module's Python
helpers, locate the installed plugin root. When it contains `components.json` and
`scripts/managed_python_runtime.py` (as Vera does), run from that root:

```bash
python3 scripts/check_dependencies.py --module <module>
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

If the enclosing plugin does not ship this managed launcher, use the module's
dependency checker and only already-installed dependencies; do not assume that a
standalone module script provisions them.

The managed launcher provisions and reuses one user-scoped CPython 3.12
environment per OS host with the published, hash-checked dependency locks, outside client
folders. Modules and products share this dependency environment; it does not
isolate client matters. This declared dependency setup is authorized as
part of running the workflow; never install arbitrary packages or use ambient
Python for subsequent module helpers. Repeat any declared `--requirements` options
on both commands. Missing ambient imports are a reason to run this setup, not to
abandon the calculation. If setup fails, report its exact error and do not replace
the required calculation with an invented result. Optional OCR setup still needs
separate approval. If setup reports `Host not in allowlist` for PyPI, explain that
Claude Settings > Capabilities > Allow network egress is disabled or restricted.
Ask the user or organization administrator to authorize package-registry access;
never change network permissions silently or work around the restriction. Retry
the same managed setup after access is approved, in a new session if needed.

MCP tools, browser or computer control, and local review servers are optional
enhancements, never completion gates. Cloud Cowork sessions may not expose local
plugin MCP servers even when the plugin is installed; use the packaged Python
workflow through the managed launcher in that case. Do not equate missing MCP
registration with a failed calculation engine. When an optional capability is
unavailable, continue with Markdown and file-based review and state the limitation.

The normal Cowork deliverable is a reviewable draft, artifact card, and
source/review files. A callable persistence interface may optionally record or
apply reviewer actions, but its absence never blocks delivery. Never claim
`applied` or `final_ready` unless corresponding persisted artifacts prove it;
otherwise report that professional review remains pending.

Use host-neutral user-facing artifact names. Name assistant-authored review
folders and files for Vera or their professional purpose (for example,
`vera-review/`, `vera_phase1_synthesis_reviewed.md`, and `run_review.md`).
Never put host, platform, or model-provider names in assistant-authored
user-facing artifact paths, document headings, field labels, narrative text,
or status summaries. Describe execution routes generically, such as
`external review route`, `connected tool`, or `local review interface`.

Derive any run ID, status, artifact count, or package hash quoted in an
assistant-authored supplement from the final delivered manifests.
After any rebuild, regenerate or resynchronize those supplements before
delivery. When a workflow ships a complete-delivery validator or sealer, run it
against the exact connected-folder copy after the last write.
In this contract, the base package validator alone does not validate extra
narrative files.

When a workflow declares owner-only or private output and uses a private scratch
directory before copying the final package into the connected folder, reapply
the privacy modes after that transfer: `0700` for the package root and every
directory, and `0600` for every file. Verify the connected-folder tree with
`stat` or `lstat` before claiming completion. If the host filesystem cannot
preserve those modes, do not claim owner-only delivery; keep the package in the
private scratch location or report the limitation and ask for a safer
destination.

Do not use WhatsApp, live INPS browser capture, hosted suggestion or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract. When invoked through Vera, Clara or Lucia, task
usage, signed receipts, technical recovery and 1–5-star feedback through the
invoking product's incident service and rating form remain available. Follow the
primary task's workflow-usage contract and product identity. Tutorials retain
their no-reporting boundary.

## Client workflow gate

Resolve the exact Studio Archive client and engagement before reading or writing
case material. Resume or prepare a `client-file-preparation` run, use only its
managed input folder and `output_dir`, and pass its absolute context path as
`--client-engagement`. Do not invent a sibling output folder.

# Avviso Intake

Use this workflow when a customer folder contains an avviso, comunicazione, cartella, Agenzia file, HMRC letter, Swiss cantonal tax letter, or similar document.

## Cowork-native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Reuse choices already established in the conversation or bound case records. Ask only for unresolved material choices and wait before their dependent work; continue independent authorized preparation. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not infer missing required evidence, approval, or a material business decision. State routine provisional assumptions when the workflow permits them.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Vera-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy follows the document and jurisdiction: Italy uses
`EUR`, Swiss cantonal matters normally use `CHF`, and UK matters normally use
`GBP`. Preserve an explicit source currency. Ask only when an unresolved
currency would materially change the intake; otherwise record the applicable
jurisdiction default as an assumption.

Keep progress and handoff concise. Use a checklist, Run Intake table, Decision
Table, or Artifact Card when it helps the user review complex work; their chat
format is optional. Preserve all required saved mappings, review decisions,
validation records, and artifacts. Resolve material choices before dependent
execution and continue independent authorized work while awaiting an answer.
Obtain authorization for external, destructive, or approval-sensitive actions
when not already given, and preserve workflow-specific approval gates.
At delivery, link outputs and state their purpose, review status, unresolved
items, and next action. Create `run_review.md` when a durable review index
is useful; never edit plugin source or generated ZIPs during a user-data run.

## Scope

- Extract practical elements only: file name, possible dates, possible amounts, protocol references, and documents to recover.
- State clearly when an element is "da verificare".
- Read each file's classification and extraction disposition from the shared
  handoff. A filename hint does not establish the document's meaning, and an
  unreadable or unsupported notice cannot be treated as reviewed. Inspect the
  relevant source before interpreting practical references or missing evidence.

## Run

The avviso intake is included in the full workflow:

```bash
python ../../scripts/build_file_preparation_outputs.py <managed-input-folder> --client-engagement <client_engagement_path> --year <anno>
```

If the command is interrupted, rerun it with the same arguments and output
folder. The workflow resumes integrity-checked extraction checkpoints for
unchanged source files and rejects stale or incompatible partial runs.

Review:

- `avviso/avviso_intake_memo.md`
- `avviso/deadlines_and_amounts.csv`

For persisted Model review, validate once and reuse the returned opaque review
reference for render, save, and apply. Do not resend `review_payload.json`
merely to carry state. Routine high-confidence inventory rows omit extracted
text previews after deterministic mapping; exception rows retain a bounded
preview, and every row keeps its exact local source reference.

## Deliver the reviewed notice, not only the extraction list

A mention of a tax form in a notice does not establish that the form was supplied.
Read the notice and any client covering message before accepting document kinds.
Use the existing text-hash-bound `--document-kind-decisions` contract when a
lexical candidate is wrong. For a readable letter with no supported fiscal-form
adapter, `kind: "unsupported"` means no fiscal-form fields are extracted; it does
not mean that the letter is unreadable. Preserve the exact extracted-text hash
and `basis: "model_review"`. Changed decisions require a new successor run.
Keep generated decision JSON under that run's owning `outputs/` and use
`--out <owning-outputs>/intake` for its fresh native output directory, so the
configuration is outside the initially empty intake folder.

The deterministic `avviso/avviso_intake_memo.md` and date/reference CSV are
extraction aids. The main delivered note is the current source-backed synthesis
in `07_scheda_per_studio.md`. Follow the full client-file-preparation skill's
normal explicit review edit and Apply path to replace its initial template.
Explain who wrote to whom, the stated request and period, protocol, dates with
their source meaning, documents actually received, missing evidence and next
checks. Distinguish a client statement from an acquired document or proof of
receipt. Do not turn an extracted date into a verified legal deadline or infer
a quantified debt from a document request.

Review the missing-document candidates against this assignment. Remove unrelated
general tax-intake questions; a notice does not by itself justify a CU request.
Show the reviewed note first, then the extracted references. Keep all original
sources and extraction records. Apply changes through the normal review contract,
never by overwriting sealed outputs. Practice with new evidence uses a fresh run
and retains the earlier notice assessment.
