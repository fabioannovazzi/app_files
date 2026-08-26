---
name: centrale-rischi-review
description: Use when Vera must normalize a native-text Italian Centrale Rischi PDF or analyse a reviewed export, separate duration lenses, list supported guarantees and exceptions, and prepare source-supported debt and resource KPIs.
---

## Output location

Never write run outputs inside this Git workspace or a published folder. In
Codex, use only the exact Studio Archive run output for workflow ID
`centrale-rischi-review`.

# Centrale Rischi Review

Use this workflow for one reviewable analysis of a Banca d'Italia Centrale
Rischi report or an already normalized export. The executable layer accepts
native-text `.pdf`, `.csv`, `.xlsx`, or `.xlsm` inputs. PDF inspection first
writes separate normalized review sheets and provenance receipts; those sheets
must still be checked against the source and bound to a reviewed recipe before
calculation. Scanned PDFs stop visibly because OCR is a separate adapter that
is not enabled.
Browser automation is an optional acquisition adapter; it is not part of the
calculation or professional-review contract.

Do not mix the report supplied to the interested client with technical
XML/SDMX survey flows used by reporting intermediaries. This initial workflow
targets the client report and its reviewed tabular normalization. Technical
intermediary flows require a separate input adapter and validation population.

Normal outputs include:

- exposures split into reviewed `short`, `medium`, `long`, `not_relevant`, or
  explicit `unclassified` original-duration classes, with the official
  residual-duration lens reported separately as `within_one_year`,
  `over_one_year`, `not_relevant`, or `unclassified`;
- exposure-linked positive guaranteed amounts, separate `Garanzie ricevute`
  review rows, non-suffering overruns, and supplied prejudicial events;
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
formula `max(utilizzato - accordato operativo, 0)`, control totals, metric
reference closure, rendering, and hashes. These rules are fixed because their
correctness is mechanically verifiable and the work must replay exactly.

Codex and the professional own report scope, source meaning, duration and risk
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

## Codex-Native Run UX

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
distinguished. `Garanzie ricevute`, inframonthly events and information
requests stay on separate review sheets and are not merged into client credit
exposures. A linear text dump is not a validated parser.

Show a Decision Table only for unresolved material mappings generated from the
actual evidence. Do not make normal output formats into user choices. Ordinary
local inspection and writes inside the authorized run output require no extra
approval ceremony.

Before a long or write-heavy step, show an execution checkpoint with the
command intent, exact inputs, authorized output folder, and expected artifacts.

End with an Artifact Card listing delivered paths, purposes, coverage,
calculation status, review status, unresolved issues, and next action. When
useful, write `codex_run_review.md` beside the run artifacts. Never edit plugin
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
metrics, maturity summaries, at most 36 monthly rows, and at most 20 top
overruns, guarantees, and prejudicial events. It excludes raw populations,
absolute paths, and original filenames by default.

Prepare `centrale_rischi_commentary.json` from the template. Separate facts,
hypotheses, questions, and limitations. Every observation and hypothesis must
reference existing metric IDs; a metric movement is not proof of business
causation.

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

## Plugin Improvement Feedback

After substantive use, read and follow the `Plugin Improvement Feedback`
section in the Vera router. Keep client data and source details out of any
technical improvement note. Keep the improvement note local to chat or run artifacts.
