---
name: client-file-preparation
description: "Use as New Client's first file-preparation phase for Italy, Geneva, Zurich, or the UK: run local checks, classify incoming documents, read generated evidence, and write a concise operational pack."
---

## Cowork execution contract

Work from the connected folder and supplied files first. Use a local script only
when it is callable and every declared dependency it needs is already available;
never install packages at runtime. MCP tools, browser or computer control, and
local review servers are optional enhancements, never completion gates. When an
optional capability is unavailable, continue with Markdown and file-based review
and state the limitation.

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

## Output Location Rule

Never write run outputs inside this Git workspace or a published folder. Use
only the Studio Archive run path described below.

## Client engagement gate

Every run is attached to one Studio Archive client and engagement. Identify or
create the client, create or select the engagement, import each source into its
managed input folder, then call `prepare_studio_client_workflow` with workflow
ID `client-file-preparation`. Pass the returned `client_engagement_path` as
`--client-engagement` to the workflow entry points.

Use the context's `output_dir` or a workflow-defined child of it. Never invent
a sibling output folder. The entry points reject a context for another
workflow, input outside the selected engagement, and output outside that run.

Start the prepared run before the first helper. After the last output write,
call `finalize_studio_client_workflow` and declare every physical file with a
stable artifact ID, relative path, concrete purpose, audience, and media type.
Review the closed declaration, then call `complete_studio_client_workflow`;
record `failed` or explicitly cancel an abandoned run instead of treating a
partial directory as a result.

# New Client · File Preparation

This is New Client's internal document-preparation engine. Use it as phase one
when the user supplies a customer folder for an Italian, Geneva, Zurich, UK, or
mixed case. Do not present it as a separate product or workflow.

The local scripts are only evidence-gathering tools. The plugin value is the Claude step after the scripts: Claude reads the outputs, checks the folder context, and writes a clear synthesis for the studio.

## Cowork-native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Reuse choices already established in the conversation or bound case records. Ask only for unresolved material choices and wait before their dependent work; continue independent authorized preparation. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not infer missing required evidence, approval, or a material business decision. State routine provisional assumptions when the workflow permits them.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Vera-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy follows the selected jurisdiction: Italy uses Euro
(`EUR`), Geneva and Zurich use Swiss francs (`CHF`), and the United Kingdom
uses pounds sterling (`GBP`). Source evidence or an explicit user instruction
overrides that default. For a mixed case, do not invent one currency: preserve
the currency stated by each source and ask only if an unresolved currency would
materially change the preparation or downstream professional pack.

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

## Workflow Positioning

Present this work as the first phase of New Client:

```text
Prepare the first file-preparation phase for a customer tax folder in Italy, Geneva, Zurich,
or the UK into inventory, formal checks, structured fields, a studio memo, and
a reviewable client email draft.
```

For Geneva, Zurich, and UK folders, present the same New Client phase as document
classification and evidence extraction for the local document set. The user
experience should feel like a guided Claude run: inspect the folder, confirm
jurisdiction/year assumptions, use OCR when available, run deterministic helpers, read
evidence, and deliver a concise operational pack.

## Source Rule

For development, the repo source is the only editable source:

```text
plugins/client-file-preparation
```

Do not edit downloaded plugin folders, ZIP contents, or Claude cache copies as source.

## Core Principle

Deterministic scripts own extraction, classification, parsing, duplicate detection, and formal checks.

Vera-assisted review is a quality-control and synthesis layer. It may remove
unsupported generic requests, explain weak evidence, point to unreadable files,
or propose improvements, but it must not silently invent missing document
content.

## Default Model Handoff

When `model_handoff.json` exists, both Claude and Cowork must use it and its
hash-listed pages as the default model context. Read only the item kinds listed
for the current phase in `phase_access`:

- file-preparation review uses the complete file-metadata population, flagged
  evidence excerpts, every mapped fiscal field with its bounded citation,
  review-only missing-request candidates, duplicate groups, and XML checks;
- client-email drafting uses only `email_request` items produced after a
  reviewer decision and the generic `CLIENT-001` reference;
- XML synthesis uses only `xml_anomaly` and `xml_duplicate_group` items, whose
  party fields and duplicate keys have been replaced by document/group refs.

Do not load `review_payload.json`, generated drafts, extracted text, or source
documents into ordinary model context merely because they are present. The
review payload remains the exact local UI/persistence contract. Load a bounded
excerpt or exact local file only when the handoff flags it, the professional
selects it, or the current judgment cannot be supported without it. Page order
is deterministic; process every page, never sample. Each page must remain at or
below 2,500 items and 1,500,000 bytes.

## Required Questions

Ask only what is needed. If not obvious, ask for:

- exact Studio Archive client and engagement;
- managed input folder containing the imported source snapshot;
- jurisdiction or market when not obvious: Italy, Geneva, Zurich, UK, or mixed;
- target year or tax campaign;
- whether unreadable/protected files should be skipped or paused for user help.

The default scope is full intake: inventory, formal checks, structured fiscal
fields, FatturaPA XML checks, missing/uncertain documents, avviso intake when
present, studio memo, and client email draft. Do not ask which of these normal
outputs to produce. Use OCR when dependencies are available and the folder
contains scans or images. If the shared OCR runtime is unavailable, use the
managed approval flow below instead of silently continuing with a partial pass.

Do not ask the user to edit JSON, YAML, or plugin files.

## First Run

For a beta user's first run, guide the work in this order:

1. Resolve the exact client and engagement, import the sources, prepare the
   `client-file-preparation` context, and confirm the target year/campaign.
2. Use the context's managed input and output paths. Use OCR automatically when
   available and relevant.
3. Run `python scripts/check_dependencies.py --folder <managed-input-folder>` from the plugin directory before helper scripts.
4. If OCR setup is required, ask for approval, perform the managed installation,
   and automatically retry as specified below.
5. Run the deterministic intake script.
6. Read the generated Markdown/CSV/JSONL evidence files before summarizing.
7. Read `run_intake.json` and, when present, `model_handoff.json` plus every
   page declared there. Treat `review_payload.json` as the shared local
   UI/review contract for the run: document inventory rows,
   uncertain files, missing-document requests, extracted fiscal fields, draft
   memo, and draft client email. If a local UI or fallback review is used,
   call `save_client_file_preparation_decisions` so `ui_decisions.json` is validated and
   persisted, then call `apply_client_file_preparation_decisions` so
   `applied_decisions.json` and `final_artifacts.json` reflect the reviewed
   actions before revising final outputs.
8. When the `newClientFilePreparation` MCP tools are available, use the OpenAI-style
   handoff: call `validate_client_file_preparation_review` with the full review payload,
   then call `render_client_file_preparation_review` once validation succeeds. When
   decisions are collected, call `save_client_file_preparation_decisions` and
   `apply_client_file_preparation_decisions` before treating the review as applied. When callable, the
   MCP server may provide validation, HTML widget rendering, and decision persistence;
   the Python scripts only produce the structured payload. If host MCP is unavailable and the local review server is callable, that server may be used as an optional persistent review enhancement. Otherwise continue through Markdown and files, keep unrecorded decisions pending, and deliver the useful file-based artifacts. A final-ready review must record a stable
   professional or account reference. A real professional name is allowed; do
   not put credentials, session material, or raw local paths in that field. A
   skipped or incomplete review does not make the package final-ready.
9. Record any complete replacement of `07_scheda_per_studio.md` or
   `04_bozza_email_cliente.md` as an explicit review edit before Apply. Apply
   performs the change transactionally, reruns the declared text QA, and
   reseals the package. Never edit sealed run files manually after Apply; start
   a new run if the evidence changes.
10. Summarize missing/uncertain documents, formal anomalies, structured-field limits, unreadable files, and concrete next steps for the studio workflow.

Expected delivery artifacts are listed in `references/workflow-reference.md`.

## Starter Prompt Bank

Load `references/workflow-reference.md` for beta-facing starter prompts and full artifact lists. Keep this `SKILL.md` focused on routing, guardrails, first-run flow, dependency checks, and final synthesis.

## What Vera Should Do

1. Resolve the exact client and engagement, import the source snapshot into its
   managed input folder, and confirm the target year.
2. From the plugin root, check local dependencies:

```bash
python scripts/check_dependencies.py --folder <managed-input-folder>
```

If core PDF dependencies are missing, stop and say that document reading is not
available in the current setup. Do not ask the user to run a technical
installation command. Handle other declared requirements the same way.

If the input-aware check reports `OCR_SETUP_REQUIRED`, ask only:

> PaddleOCR is required to read this document. Shall Claude install it now? The
> download is about 500 MB.

Do not ask the user to run pip, Python, Terminal, or any technical installation
step. Wait for explicit approval. When approved, Claude runs
`scripts/managed_ocr_runtime.py install` itself. On success, say `PaddleOCR is
ready. Retrying the document now.` and automatically rerun this dependency check
and the interrupted intake command. The managed runtime persists outside the
plugin and is shared by Clara and Vera, so later OCR jobs reuse it without
prompting. If setup fails, show only `I couldn't install PaddleOCR right now.
Shall I try the installation again?` unless the user asks for technical details.
Do not describe scanned evidence as read when setup is declined or unsuccessful.

3. Run the deterministic intake script from the plugin root:

```bash
python scripts/build_file_preparation_outputs.py <managed-input-folder> \
  --client-engagement <client_engagement_path> \
  --year <anno> \
  --jurisdiction <italy|geneva|zurich|uk|mixed> \
  --language <it|en|fr|de|es>
```

Use `--no-ocr` only when the user explicitly wants a text-only pass after
declining managed OCR setup.

If execution stops after producing partial files, resume the same Studio
Archive run and rerun the same command with the same context path. The script
validates the original source hashes and run settings, then reuses completed
document extractions whose text integrity still matches. It rejects changed
sources, incompatible settings, unrelated directories, and completed runs
instead of overwriting them.

`review_payload.json` keeps the exact local review state, including exception
excerpts, fiscal-field evidence snippets, and previews of generated drafts.
`model_handoff.json` is the narrower model-default artifact: it keeps one
metadata item for every inventoried file, omits routine high-confidence text
previews, retains every mapped fiscal field with a citation of at most 600
characters, and paginates without sampling. These records may still contain
real client data needed for professional work. Bounded excerpts are not
anonymization. Credentials, session material, and raw absolute local paths
remain excluded.
DOCX, XLSX, and EML bodies are extracted locally;
EML attachments, MSG, and other unsupported formats remain explicit unread
evidence and must not receive an automatic accept recommendation.

The intake never follows symbolic links from the customer folder. PDF and
plain-text extraction, OCR, and supported office/archive parsing are bounded;
files that exceed those limits remain explicit unread or partial evidence
rather than being silently trusted.

4. Read the generated evidence files listed in `references/workflow-reference.md`,
   including the review-session files:

```text
run_intake.json
review_payload.json
ui_decisions.json
model_handoff.json
model_handoff_pages/page-*.json
review_handoff.md
final_artifacts.json
applied_decisions.json (after application)
```

5. Prefer the MCP review widget when available:

```text
validate_client_file_preparation_review
render_client_file_preparation_review
```

Use `model_handoff.json` for model reasoning. Pass the complete
`review_payload.json` object only to the local review tool contract, plus `run_intake.json`,
`ui_decisions.json`, and `final_artifacts.json` when useful. Do not hand-build a
new HTML page for this review surface. When decisions are collected, use
`save_client_file_preparation_decisions` to persist `ui_decisions.json`, then
`apply_client_file_preparation_decisions` to write `applied_decisions.json` and update
`final_artifacts.json`.

If host MCP is unavailable and the local review server is callable, it may optionally persist the same save/apply decisions. Otherwise review through Markdown and files, keep unrecorded decisions pending, and state that they have not been applied.

6. Inspect nearby source files when useful and readable. Do not claim to have read the content of binary PDFs unless a text extraction step has actually succeeded.
7. Draft the short Vera synthesis file before review:

```text
07_scheda_per_studio.md
```

The synthesis must contain:

- `Sintesi del fascicolo`
- `Cosa è stato trovato`
- `Punti mancanti o incerti`
- `Anomalie formali`
- `Dati fiscali strutturati`
- `Domande da fare al cliente`
- `Punti per lo studio`
- `Limiti della lettura`

8. Review missing-document candidates and Apply the professional decisions.
   Draft or revise `04_bozza_email_cliente.md` from the resulting
   `email_request` items in `model_handoff.json`, not from unreviewed candidates.
   The script writes a conservative first draft; Claude should improve it when
   the evidence supports a clearer request. Keep only client-facing requests
   supported by the findings, remove irrelevant generic questions, and keep the
   tone suitable for a studio email. Record a complete replacement through the
   review decision and Apply path; do not modify the sealed file afterward and
   do not send the email automatically.

9. In the final response, tell the user where the output folder is and list the main issues found.

## Scope Boundaries

- Classify documents, extract readable fields, detect duplicates/anomalies, and
  draft operational questions from the evidence found.
- Do not invent missing document content.
- Do not say that a document set is complete unless the evidence supports only a
  formal completeness statement.
- Use language such as `da verificare`, `da confermare`, `elemento non
  individuato`, and `classificazione basata sul nome file/testo estratto`.

## Output Style

Be useful to a studio, not verbose. Prefer a direct internal memo style:

```text
Sono stati analizzati 32 file. Il fascicolo contiene CU, F24, fatture XML, spese sanitarie, documentazione mutuo e un avviso Agenzia. Mancano o non risultano evidenti: eventuali ulteriori CU, certificazione interessi passivi mutuo, conferma completezza F24.
```

When discussing fiscal fields, cite `08_dati_fiscali_strutturati.md` and `extracted/structured_fiscal_fields.csv`. Treat extracted fields as observed document data. If the evidence is weak because classification is based only on file names, layout parsing, or unreadable PDFs, say that clearly and point to `extracted/extraction_report.md`.
