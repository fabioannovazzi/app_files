---
name: client-file-preparation
description: "Use as New Client's first file-preparation phase for Italy, Geneva, Zurich, or the UK: run local checks, classify incoming documents, read generated evidence, and write a concise operational pack."
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# New Client · File Preparation

This is New Client's internal document-preparation engine. Use it as phase one
when the user supplies a customer folder for an Italian, Geneva, Zurich, UK, or
mixed case. Do not present it as a separate product or workflow.

The local scripts are only evidence-gathering tools. The plugin value is the Codex step after the scripts: Codex reads the outputs, checks the folder context, and writes a clear synthesis for the studio.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Ask only those unresolved choices in chat and wait for the answer. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not run long or write-heavy execution under unconfirmed assumptions.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Codex-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy follows the selected jurisdiction: Italy uses Euro
(`EUR`), Geneva and Zurich use Swiss francs (`CHF`), and the United Kingdom
uses pounds sterling (`GBP`). Source evidence or an explicit user instruction
overrides that default. For a mixed case, do not invent one currency: preserve
the currency stated by each source and ask only if an unresolved currency would
materially change the preparation or downstream professional pack.

Use Codex-native UI artifacts as part of the workflow, not as optional
narration. At minimum:

1. Start with a visible markdown run checklist. Track intake, dependency check,
   inspection, user decisions, deterministic run, Codex review, and delivery.
2. Before helper scripts, show a Run Intake table with input paths, output
   folder, working language, document language, assumptions, and notification
   choice when the skill supports user run notifications.
3. After inspection, show a compact Decision Table for missing mappings,
   filters, review choices, unsupported files, or evidence assumptions. Ask
   only unresolved decisions and update the working recipe or assumptions
   yourself.
4. Before a long-running or write-heavy step, show an execution checkpoint or
   approval checkpoint with command intent, inputs, output folder, and expected
   artifacts. Ask for approval only when the step is external, destructive,
   approval-sensitive, or still depends on an unresolved material choice.
5. During execution, update checklist statuses as steps complete.
6. End with an Artifact Card listing output path, purpose, review status,
   unresolved items, and next action. When useful, create `codex_run_review.md`
   in the output folder from generated JSON/CSV/Markdown outputs; never edit
   plugin source or generated ZIPs during a run.

## Workflow Positioning

Present this work as the first phase of New Client:

```text
Prepare the first file-preparation phase for a customer tax folder in Italy, Geneva, Zurich,
or the UK into inventory, formal checks, structured fields, a studio memo, and
a reviewable client email draft.
```

For Geneva, Zurich, and UK folders, present the same New Client phase as document
classification and evidence extraction for the local document set. The user
experience should feel like a guided Codex run: inspect the folder, confirm
jurisdiction/year assumptions, use OCR when available, run deterministic helpers, read
evidence, and deliver a concise operational pack.

## Source Rule

For development, the repo source is the only editable source:

```text
plugins/client-file-preparation
```

Do not edit downloaded plugin folders, ZIP contents, or Codex cache copies as source.

## Core Principle

Deterministic scripts own extraction, classification, parsing, duplicate detection, and formal checks.

Codex/model review is a quality-control and synthesis layer. It may remove
unsupported generic requests, explain weak evidence, point to unreadable files,
or propose improvements, but it must not silently invent missing document
content.

## Required Questions

Ask only what is needed. If not obvious, ask for:

- customer folder;
- jurisdiction or market when not obvious: Italy, Geneva, Zurich, UK, or mixed;
- target year or tax campaign;
- output folder, if not a sibling `output/client-file-preparation` folder next to `<cartella-cliente>`;
- whether unreadable/protected files should be skipped or paused for user help.

The default scope is full intake: inventory, formal checks, structured fiscal
fields, FatturaPA XML checks, missing/uncertain documents, avviso intake when
present, studio memo, and client email draft. Do not ask which of these normal
outputs to produce. Use OCR when dependencies are available and the folder
contains scans or images; if OCR is unavailable, continue with the text-readable
pass and report the limitation unless the run would be misleading without OCR.

Do not ask the user to edit JSON, YAML, or plugin files.

## First Run

For a beta user's first run, guide the work in this order:

1. Confirm the input folder and target year/campaign.
2. Confirm output folder only when not inferable. Use OCR automatically when available and relevant.
3. Run `python scripts/check_dependencies.py --folder <cartella-cliente>` from the plugin directory before helper scripts.
4. If OCR is needed and optional dependencies are missing, continue with the text-readable pass, explain that scanned documents may remain unread, and record the limitation in the synthesis.
5. Run the deterministic intake script.
6. Read the generated Markdown/CSV/JSONL evidence files before summarizing.
7. Read `run_intake.json` and `review_payload.json`. Treat the review payload
   as the shared UI/review contract for the run: document inventory rows,
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
   `apply_client_file_preparation_decisions` before treating the review as applied. The
   MCP server owns validation, HTML widget rendering, and decision persistence;
   the Python scripts only produce the structured payload. If host MCP is
   unavailable, start `python scripts/review_server.py <cartella-output>` from
   the resolved installed module root so the same save/apply contract remains
   persistent. Fall back to Markdown/chat only if neither service can run, and
   then keep review decisions pending. A final-ready review must record a stable
   professional or account reference. A real professional name is allowed; do
   not put credentials, session material, or raw local paths in that field. A
   skipped or incomplete review does not make the package final-ready.
9. Record any complete replacement of `07_scheda_codex_per_studio.md` or
   `04_bozza_email_cliente.md` as an explicit review edit before Apply. Apply
   performs the change transactionally, reruns the declared text QA, and
   reseals the package. Never edit sealed run files manually after Apply; start
   a new run if the evidence changes.
10. Summarize missing/uncertain documents, formal anomalies, structured-field limits, unreadable files, and concrete next steps for the studio workflow.

Expected delivery artifacts are listed in `references/workflow-reference.md`.

## Starter Prompt Bank

Load `references/workflow-reference.md` for beta-facing starter prompts and full artifact lists. Keep this `SKILL.md` focused on routing, guardrails, first-run flow, dependency checks, and final synthesis.

## What Codex Should Do

1. Identify the customer folder and target year.
2. From the plugin root, check local dependencies:

```bash
python scripts/check_dependencies.py --folder <cartella-cliente>
```

If core PDF dependencies are missing, tell the user to run:

```bash
python -m pip install -r requirements.txt
```

If OCR dependencies are missing and the folder contains scans or images, record
that scanned documents may remain unread and, when useful, suggest installing:

```bash
python -m pip install -r requirements-ocr.txt
```

Continue without OCR for the text-readable pass unless the user explicitly wants
to pause and install OCR dependencies first.

3. Run the deterministic intake script from the plugin root:

```bash
python scripts/build_file_preparation_outputs.py <cartella-cliente> \
  --year <anno> \
  --jurisdiction <italy|geneva|zurich|uk|mixed> \
  --language <it|en|fr|de|es> \
  --out <cartella-output>
```

Use `--no-ocr` only when OCR is not installed or the user explicitly wants a
text-only pass.

`review_payload.json` includes bounded excerpts from every readable document in
the selected folder, fiscal-field evidence snippets, and previews of the
generated studio brief, memo, and client email by default. These may contain
real client data needed for professional review. The limits are for interface
and payload performance; they are not anonymization and do not enumerate
everything Codex may have read. Credentials, session material, and raw absolute
local paths remain excluded.
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
review_handoff.md
final_artifacts.json
applied_decisions.json (after application)
```

5. Prefer the MCP review widget when available:

```text
validate_client_file_preparation_review
render_client_file_preparation_review
```

Pass the complete `review_payload.json` object, plus `run_intake.json`,
`ui_decisions.json`, and `final_artifacts.json` when useful. Do not hand-build a
new HTML page for this review surface. When decisions are collected, use
`save_client_file_preparation_decisions` to persist `ui_decisions.json`, then
`apply_client_file_preparation_decisions` to write `applied_decisions.json` and update
`final_artifacts.json`.

If the host MCP tools are unavailable, do not replace write-back with an
ephemeral chat approval. From the resolved installed module root run:

```bash
python scripts/review_server.py <cartella-output>
```

This opens the same review widget on loopback and persists the same save/apply
tool calls. In repository source, the equivalent developer command from this
component root is
`python ../../scripts/serve_review_workbench.py <cartella-output> --plugin-dir .`.
If neither service can run, review in Markdown/chat but leave the decisions
pending and state that they have not been applied.

6. Inspect nearby source files when useful and readable. Do not claim to have read the content of binary PDFs unless a text extraction step has actually succeeded.
7. Draft the short Codex synthesis file before review:

```text
07_scheda_codex_per_studio.md
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

8. Review `04_bozza_email_cliente.md` after reading `02_documenti_mancanti_o_incerti.md`.
   The script writes a conservative first draft; Codex should improve it when
   the evidence supports a clearer request. Keep only client-facing requests
   supported by the findings, remove irrelevant generic questions, and keep the
   tone suitable for a studio email. Record a complete replacement through the
   review decision and Apply path; do not modify the sealed file afterward and
   do not send the email automatically.

9. In the final response, tell the user where the output folder is and list the main issues found.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting the deliverables, briefly identify concrete improvements that would have made this plugin run better. Base suggestions on the actual session, such as missing inputs, brittle extraction, unclear assumptions, output gaps, installation friction, unsupported document types, noisy client requests, or repeated manual steps.

Keep the improvement note local to chat or run artifacts. Do not submit it to
Mparanza automatically. When this workflow runs through Vera, use Vera's
consent-based Plugin Improvement Feedback process for any transmission.

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
