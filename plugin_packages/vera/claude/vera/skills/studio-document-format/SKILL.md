---
name: studio-document-format
description: Teach Vera a professional studio's reusable Word report format from selected examples and preferences, show short and long previews, adopt an explicitly approved standard, or revise and reuse it. Use for requests such as “learn our house style”, “use our letterhead” or “teach Vera our studio format”.
---

## Cowork execution contract

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, report-builder and check-entries only, optional cache
cleanup is available from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
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
environment per OS host with the published shared requirements, outside client
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

Do not use WhatsApp, live INPS browser capture, hosted feedback or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract.

# Teach Vera our studio format



Apply `../vera/references/model-data-report-contract.md` to actual model reads,
including metadata and rendered pages. Keep a truthful local report; parser
execution alone does not establish what reached the selected model.

The studio supplies examples and ordinary-language preferences. Vera interprets
them, proposes supported presentation settings, generates actual previews and
saves only the version explicitly approved by the user. This does not train or
fine-tune a model. The standard is a private, versioned configuration that later
supported document generators load explicitly.

Onboarding is optional and never blocks normal work. For a requested lesson,
read `../learn-with-vera/SKILL.md` in desktop Claude and use this installation's
prepared `studio-document-format` course. Cowork can execute the written skill
and local course files; do not claim native voice or paired teaching there.
Tutorial files and decisions remain local; do not submit improvement requests,
contact contributors, or count an explanation as a completed exercise.

Read `references/procedure.md` completely. Resolve
`../../modules/comunicazione-professionale`, `../../modules/studio-archive`
and `../../modules/report-builder`
from this skill directory in a package, or `../../../comunicazione-professionale`
and `../../../report-builder` in repository source. Read their
`skills/comunicazione-professionale/SKILL.md` privacy/history procedure and
`skills/financial-report-builder/SKILL.md` document construction contract when
those routes are used. The native helper is `scripts/studio_document_format.py`
under the Vera root; its first-run defaults are
`assets/studio-document-format/baseline-profile-<language>.json` in the communications component.

Use the ready managed Python environment documented in `../vera/SKILL.md`;
do not install packages into a client folder or pick an arbitrary interpreter.
Invoke the native helper with that exact environment's interpreter and its
absolute path. Vera writes technical JSON and runs commands; the studio never
needs to edit JSON, know skill names or use a terminal.

## Complete ordinary first use

1. Establish the studio identity, authorized owner/retention owner and one exact
   private workspace outside repository/public roots. Reuse its communications
   workspace when it exists. This is studio-wide setup, not a client engagement.
   Use the component's `scripts/initialize_workspace.py` only with actual user
   authorization; an instruction to set up the specified workspace is sufficient.
   Do not ask twice. A tutorial uses its bound private project and fictional owner.
2. Ask only for missing selected examples, optional PNG/JPEG logo and preferences.
   Never browse a mailbox or archive to find examples. Inspect DOCX structure with
   `inspect`; do not open originals for text interpretation by default. Formatting
   metadata and style names can still identify the studio. If actual example text
   is needed, use the communications isolated stripping, pseudonymization and
   independent review route before downstream use. PDF or images require an
   explicitly selected visual inspection route; the structural helper supports
   DOCX only. Do not present unobserved PDF styling as extracted metadata.
3. Interpret the evidence with the native model. Present observed settings,
   proposed defaults, conflicts, unsupported requests and uncertain/inherited
   styling separately. Ask about ambiguous choices that affect the result.
   Do not silently select the most frequent font or claim exact template cloning.
4. Write settings, then run `prepare` with `--language` set to the user’s
   chosen `it`, `en`, `fr`, `de` or `es`. This produces the exact proposal and two
   synthetic DOCX previews. Open both as documents; render them with the host's
   document tooling and inspect the actual pages when available. Show font
   substitutions and review the long table, page breaks, logo and footer. If
   rendering is unavailable, leave visual acceptance open; do not assert it passed.
5. Apply requested corrections through a fresh review ID, regenerate both previews
   and show the changed result. Wait for the user's explicit adoption of the exact
   proposal and previews. Then run `approve` with that digest and actual reviewer.
   Never invent approval from silence, a tutorial answer or your own assessment.
6. Show the saved standard, studio identity and version, plus what remains
   unsupported. Reuse through the financial report builder's exact
   `--studio-workspace`, `--studio-id` and `--studio-name` arguments. Its client
   engagement, reviewed financial inputs and report-content assurance remain
   required. Formatting cannot change figures, accounting meaning or conclusions.
   A new chat selects the same private workspace explicitly; there is no global
   “last studio” fallback. For revision, load the existing standard, merge the
   requested changes into its DOCX settings, prepare new previews and approve a
   new version. The prior standard stays available in its version archive.

## Course execution

Use the current kit's source and distinct practice specification. Desktop Claude
uses its normal bound tutorial case adapter for each attempt. Cowork follows
`references/written-course.md` with its actual written-course provenance and
private project descriptor; never fabricate native session authority. Then run `practice-materials` to
create the actual fictional DOCX example and accounting CSV in its output
folder. These are inputs, not precomputed successful deliverables. Inspect the
example, interpret its styling, propose settings and run the normal setup,
preview and adoption steps, pausing for the learner's real choices.

Demonstration: set up fictional Studio Riva, review both previews and save the
standard only after actual confirmation. Request a small financial DOCX from
the generated CSV through the current financial report procedure, retaining
its normal reviewed mapping and content controls, and verify the saved format
and a source amount in the result. This delegated report is the reuse check,
not an alias for another course. Run `report-case --tutorial-case <actual-tutorial_case.json> --source
<generated-financial-source.csv> --studio-workspace <approved-private-workspace>`
to create its actual client run; retain the returned `client_engagement_path`,
input bindings and output directory. Execute and close the report through its
current procedure without hosted stamping. It uses a real synthetic client run under the
same lesson with a `financial-report-builder` binding; never relabel the studio
workspace as a client run or bypass the report's archive adapter.

Practice: independently set up the different fictional studio and its new
source file, ask the learner to change one preference, review the result, adopt
it and produce the corresponding financial report. Then revise that studio's
format once and check that version 1 remains archived. Never copy a successful
answer, adopt on the learner's behalf, or report practice complete without
actual execution and participation. Ordinary work is available immediately.
