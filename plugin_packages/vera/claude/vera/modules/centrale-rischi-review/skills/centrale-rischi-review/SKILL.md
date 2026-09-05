---
name: centrale-rischi-review
description: Use when Vera must normalize an official digital Italian Centrale Rischi PDF or analyse a reviewed export, separate duration lenses, list supported guarantees and exceptions, and prepare source-supported debt and resource KPIs.
---

## Cowork execution contract

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

The managed launchers provision and reuse an isolated environment containing only the
module's published requirements. This declared dependency setup is authorized as
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

## Output location

Never write run outputs inside this Git workspace or a published folder. In
Claude, use only the exact Studio Archive run output for workflow ID
`centrale-rischi-review`.

# Centrale Rischi Review

Use this workflow for one reviewable analysis of a Banca d'Italia Centrale
Rischi report or an already normalized export. The expected PDF input is the
official digital report downloaded from the Banca d'Italia service. Treat that
report as native text: OCR is not part of this workflow and must not be
presented as an intake requirement, capability gap, fallback, or open issue.
If the supplied file is a printout or an image-only scan, request the original
digital report instead of starting an OCR path. The executable layer accepts
`.pdf`, `.csv`, `.xlsx`, or `.xlsm` inputs. PDF inspection first writes separate
normalized review sheets and provenance receipts; those sheets must still be
checked against the source and bound to a reviewed recipe before calculation.
Browser automation is an optional acquisition adapter; it is not part of the
calculation or professional-review contract.

Official guides, facsimiles and educational PDFs remain useful parser test
corpora. Do not reject them merely because they are not one client's report.
Evaluate their examples as explicit page or page-range cases and report parser
coverage for each case separately. Never combine several examples into one
fictitious client analysis, and never infer case meaning from a filename or
keyword. Corpus evaluation produces coverage evidence only; client analysis
still requires one bound report and a reviewed mapping recipe.

Do not mix the report supplied to the interested client with technical
XML/SDMX survey flows used by reporting intermediaries. This initial workflow
targets the client report and its reviewed tabular normalization. Technical
intermediary flows require a separate input adapter and validation population.

Normal outputs include:

- exposures split into reviewed `short`, `medium`, `long`, `not_relevant`, or
  explicit `unclassified` original-duration classes, with the official
  residual-duration lens reported separately as `within_one_year`,
  `over_one_year`, `not_relevant`, or `unclassified`;
- exposure-linked positive guaranteed amounts, separate `Garanti
  intestatario`, `Garanzie ricevute`, and `Debitori ceduti` review rows,
  non-suffering overruns, and supplied prejudicial events;
- separate `Altre informazioni` and `Prospetto sintetico` control or
  information rows when the exact supported table shape is present; these
  populations never enter exposure totals;
- accordato, accordato operativo, utilized, available resources,
  category-specific utilization, overrun, guarantee-coverage, maturity-mix,
  concentration, and multi-month movement metrics;
- explicit unavailable results for PFN/EBITDA, Debt/Equity, DSCR, or
  prejudicial evidence when the required additional sources are absent.

Never reproduce, estimate, or imply a bank's proprietary rating. Never treat a
single reported month as continuous monitoring.

## Judgment boundary

Deterministic code owns file inventory, exact field extraction after reviewed
mapping, date and Decimal parsing, exact aggregation, the non-suffering overrun
formula `max(utilizzato - accordato operativo, 0)`, control totals, evidence-
reference closure, rendering, and hashes.
Evidence references may resolve to an existing metric ID, control ID, or source-
row locator. These rules are fixed because their
correctness is mechanically verifiable and the work must replay exactly.

Claude and the professional own report scope, source meaning, duration and risk
category mappings, whether a category is a sofferenza, entity identity,
materiality, causal interpretation, missing-evidence requests, conclusions,
and approval. Do not assign maturity or exposure-family classes from keywords,
filenames, or presumed Banca d'Italia labels. A suggested mapping is not a
reviewed mapping.

## Client-bound run

1. Select one Studio Archive client and engagement.
2. Import the exact report/export as immutable `source` receipts.
3. Prepare and start workflow ID `centrale-rischi-review` from those inputs.
4. Pass the returned absolute `client_engagement_path` unchanged to every
   helper and write only below its `output_dir`.
5. Finalize every physical output with a stable artifact ID, path, purpose,
   audience, and media type; review the declaration and complete the run.
   Record a failed or cancelled run rather than treating partial files as final.

In Cowork, use only explicitly connected files and folders and state that no
portable Studio Archive run was created.

## Cowork-native Run UX

Start with a visible checklist and a compact Run Intake table covering client,
engagement, source receipts, entity, currency, reference months, output folder,
confirmed mappings, and unresolved choices. Before helper scripts, identify the
material choices that can change the result. Ask only those unresolved choices in chat.
Use chat for the small mapping decision; use the
self-contained HTML and Excel outputs for population review.
Generate options from the actual inputs. Do not propose named methods,
categories, or output variants unless the facts cue them.

Default output policy: produce every normal supported structured,
spreadsheet, narrative, dashboard, context, open-issue, and receipt artifact.
Natural outputs are not choices to propose.

Before helper scripts, establish:

- the explicit objective: explain the report, prepare for financing, identify
  anomalies, reconstruct trends, compare with the bank, reconcile to external
  evidence, or prepare a factual discrepancy dossier;

- the exact exposure table and columns for reference month, intermediary, risk
  category, original duration, residual duration, accordato, accordato
  operativo, and utilizzato;
- optional guarantee type, guaranteed amount, and prejudicial-event columns;
- an exhaustive reviewed mapping from every observed original-duration value
  to `short`, `medium`, `long`, `not_relevant`, or `unclassified`;
- an exhaustive reviewed mapping from every observed residual-duration value
  to `within_one_year`, `over_one_year`, `not_relevant`, or `unclassified`;
- an exhaustive reviewed mapping from every observed risk-category value to
  `performing`, `suffering`, or `other`;
- source control totals when available and a tolerance.

Use one workflow with three internal modes. `descriptive` uses the CR evidence
alone. `trend` requires multiple reference months. `reconciled` requires a
separate reviewed external-evidence adapter and is intentionally blocked by the
initial engine until that adapter exists.

For a PDF-derived normalization, preserve the source document hash, page,
row/region locator, whether the record is current or previous, `Da` and `A`
validity dates, and extraction confidence. Native PDF styling and coordinates
can be substantive because previous or corrected records may be visually
distinguished. `Garanti intestatario`, `Garanzie ricevute`, `Debitori ceduti`,
`Altre informazioni`, `Prospetto sintetico`, inframonthly events and
information requests stay on separate review sheets and are not merged into
client credit exposures. Empty generated sheets are not evidence that the
corresponding population was present and empty. A linear text dump is not a
validated parser.

Show a Decision Table only for unresolved material mappings generated from the
actual evidence. Do not make normal output formats into user choices. Ordinary
local inspection and writes inside the authorized run output require no extra
approval ceremony.

Before a long or write-heavy step, show an execution checkpoint with the
command intent, exact inputs, authorized output folder, and expected artifacts.

End with an Artifact Card listing delivered paths, purposes, coverage,
calculation status, review status, unresolved issues, and next action. When
useful, write `run_review.md` beside the run artifacts. Never edit plugin
source or generated ZIPs during a client-data run.

Explicit approval is reserved for external, destructive, approval-sensitive,
or material steps.

## Inspection and reviewed recipe

From the module root:

```bash
python scripts/check_dependencies.py
python scripts/inspect_inputs.py \
  --input <bound-report-or-export> [--input <bound-export> ...] \
  --client-engagement <context.json> \
  --output-dir <run-output>/inspection
```

`requirements.txt` is the complete core dependency declaration. Do not install
arbitrary packages at runtime. If the check reports a missing requirement,
install only that published declaration when the environment and user authority
permit it; otherwise report the unavailable capability.

For a PDF, the inspector reads native text and table geometry locally and
writes `centrale_rischi_normalized.xlsx`, `pdf_normalization.json`, and
`pdf_normalization_receipt.json` before the ordinary inspection artifacts. The
normalizer recognizes only mechanically reviewable table shapes, parses Italian
amount formatting, and preserves unresolved tables and row-level issues. It
does not assign duration meaning, exposure family, materiality, or conclusions.

The inspector reads each complete normalized or supplied table locally,
records row counts and hashes, and exposes at most ten preview rows with cell
text bounded to 200 characters. It does not assign semantic roles. Complete
`suggested_recipe.json` as
`reviewed_recipe.json`, bind it to the unchanged `inventory_sha256`, and set a
named, timestamped `mapping_review.status` to `reviewed` only after review.

Do not calculate one indiscriminate utilization ratio across unlike risk
categories. The engine reports utilization and available resources within each
reviewed source category. It calculates overrun row by row before aggregation,
so an available margin in another operation or intermediary never offsets it.

## Calculation and interpretation

```bash
python scripts/run_analysis.py \
  --input <bound-report-or-export> [--input <bound-export> ...] \
  --recipe <run-output>/inspection/reviewed_recipe.json \
  --client-engagement <context.json> \
  --output-dir <run-output>/analysis
```

For a native-text PDF, pass the same bound PDF to both commands. The analysis
runner verifies the PDF hash, the inspection receipt and the exact run-local
`centrale_rischi_normalized.xlsx` before calculating from that reviewed
workbook. Do not manually substitute another normalization file.

Read `execution_receipt.json`, `centrale_rischi_analysis.json`, and
`model_context.json` before opening the rendered files. Stop on a blocked
analysis or failed declared control. The bounded model context contains exact
metrics, maturity summaries, at most 50 category-movement rows, at most 36
monthly rows, at most 20 previous-record review rows, and at most 20 top
overruns, exposure-linked guarantees and prejudicial events, plus at most 20
rows from each separate population of guarantees received, guarantors of the
holder, ceded debtors, other risk information, summary totals, inframonthly
events and information requests. It excludes raw populations, absolute paths,
original filenames and source-document hashes from those bounded auxiliary-row
projections by default.

For parser development or regression evaluation, run examples separately:

```bash
python scripts/evaluate_pdf_corpus.py \
  --input <guide-or-facsimile.pdf> \
  --output <outside-repo-output>/corpus_coverage.json \
  --case <case-name>=<page-or-range>
```

Omit `--case` to evaluate every page independently. A case that contains no
recognized layout is recorded as `not_recognized`; it does not reject the
other examples and does not create a client analysis.

For a release-quality regression check, run the reviewed gold manifest with
`scripts/run_gold_benchmark.py`. Bind every source ID to the exact local PDF;
the runner verifies both SHA-256 and page count before using it. The benchmark
must keep these gates separate:

- exact page-level extraction facts and population counts;
- reviewed mappings, control totals, Decimal metrics, and expected rejection
  of pages that contain no current exposure population;
- self-contained HTML, formula-free numeric XLSX, and bounded model context;
- row-order invariance, exclusion of previous records from current totals, and
  separation of auxiliary populations from exposure metrics;
- model or professional semantic review of the commentary against the supplied
  rubric.

Do not call the workflow professionally validated merely because the
deterministic gates pass. A model review remains
`model_reviewed_not_professional`; client-facing output remains pending until a
commercialista reviews it. This is the intended supervised workflow, not by
itself a failure of the model-led semantic layer. Preserve the evidence scope
accurately in the benchmark receipt and do not present an available source as
missing. Passing cases support a quality conclusion for the represented
layouts; unseen layouts remain a separate robustness question.

Prepare `centrale_rischi_commentary.json` from the template. Separate facts,
hypotheses, questions, and limitations. Every observation and hypothesis must
reference existing evidence with `metric:<metric_id>`,
`control:<control_id>`, or `row:<source_row_locator>`; the finalizer rejects
unknown references. A metric movement is not proof of business causation.

```bash
python scripts/finalize_analysis.py \
  --analysis <run-output>/analysis/centrale_rischi_analysis.json \
  --commentary <run-output>/analysis/centrale_rischi_commentary.json \
  --client-engagement <context.json> \
  --output-dir <run-output>/analysis/final
```

The final Markdown and HTML remain
`draft_pending_professional_review`. Inspect the HTML visually and open the
XLSX when the runtime permits it. Check sheets, headers, formats, totals,
coverage, and review status.

## Natural outputs

- `inspection.json`, private `inspection_control.json`, and recipe skeleton;
- for PDF intake, the normalized workbook, full local normalization review and
  normalization receipt;
- `centrale_rischi_analysis.json` and `execution_receipt.json`;
- `centrale_rischi_analysis.xlsx`;
- `centrale_rischi_facts.md` and `centrale_rischi_dashboard.html`;
- `model_context.json` and `commentary_template.json`;
- `open_issues_template.json`, separated into documentary, arithmetic,
  semantic, and professional issues;
- after interpretation, `centrale_rischi_report.md`,
  `centrale_rischi_dashboard_reviewed.html`, and
  `commentary_receipt.json`.
