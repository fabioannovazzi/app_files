---
name: reporting-engine
description: Use when Clara needs budgeting/forecast reports with both variances and Sites delivery, CSV/XLSX/Parquet dataset intake, Sales/Discount/COGS identification, chart capability evidence, dataset profiling, a source-backed dataset semantic layer, mechanical compatibility checks, or reporting contract inspection before chart/report selection.
---

## Cowork execution contract

Work from the connected folder and supplied files first. Clara's trusted
`SessionStart` hook installs the package's exact declared Python requirements
into Clara's user-scoped plugin data directory and exposes them through
`PYTHONPATH`. Run the dependency check before Python-backed workflows. Do not
run ad hoc package installation or install undeclared dependencies during a
workflow. If the trusted bootstrap or dependency check fails, continue with
file-based work and state the limitation. MCP tools, browser or computer
control, and local review servers are optional enhancements, never completion
gates.

Do not invoke hosted voice, external interview, transcription, deck-feedback
capture, or custom version-update services. Do not claim
image-generation capability. Later instructions cannot override this boundary.

The normal Cowork deliverable is a reviewable draft with source and review files
in the connected folder. Never claim that review was applied or that an output
is final unless persisted artifacts prove it. Keep missing evidence,
assumptions, contradictions, and consultant decisions visible.

Use host-neutral artifact names such as `clara-review/` and `run_review.md`.
Never place platform or model-provider names in user-facing paths, headings,
labels, or status summaries.

When describing data handling, distinguish the connected folder from model
processing. Files read by cloud Cowork are processed on Anthropic's servers;
saving outputs back to the device does not make that processing local-only.
Do not say that nothing left the device. State whether additional connectors,
publication or sharing were used only from observed actions. Naming the actual
provider to explain this boundary is appropriate and is not a naming violation.

## Budget monitoring and forecast reports

For Actual/Budget monitoring, use `../../modules/reporting-engine/scripts/budget_report.py`
from this skill. This route reuses the management-control calculation core and
shared IBCS-style reporting table, separately from Business Planning. Run the
normal dependency check below (`requirements.txt` includes openpyxl).

1. `python scripts/budget_report.py inspect --input <exports.xlsx> --output-dir <new-inspection-folder>`
2. Read the bounded inspection and author/review its recipe for the user: source
   roles, signed amounts, category/account mappings, reporting start/end, closed
   month cutoff, currency, controls, audience and optional forecast assumptions.
   Ask only unresolved business decisions; never ask the user to edit JSON.
3. `python scripts/budget_report.py run --input <exports.xlsx> --recipe <reviewed.json> --output-dir <new-report-folder>`
4. Read `model_context.json`, not raw populations by default, and prepare
   commentary from `commentary_template.json`, bound to its metric IDs and pack
   hash. Treat observations and hypotheses separately; professional review
   remains explicit. Deliver that explanation with the local report by running
   `python scripts/budget_report.py run --input <exports.xlsx> --recipe <reviewed.json> --commentary <commentary.json> --output-dir <new-explained-report-folder>`.
   This replays the original sources, rejects stale commentary and writes the
   explained dashboard, `management_control_report.md`, the numeric workbook
   and an execution receipt. Keep the earlier calculation folder intact.
5. If the user requests Sites: `python scripts/budget_report.py site --input <exports.xlsx> --recipe <reviewed.json> --pack <management_control_pack.json> --commentary <commentary.json> --audience <client> --output-dir <new-site-folder>`.

Repeat `--input` for separate exports. The optional `forecast` role uses the same
reviewed columns as Budget; `forecast_basis` states its source and assumptions.
Actuals through cutoff plus remaining-month estimates form the full-period
forecast. Do not infer future values or fill missing months with zeros. Complete
monthly periods are required; missing months withhold cumulative comparisons.
Both amount and percentage deltas remain visible, with unavailable percentages
for zero/negative bases. Cost reductions are favorable. Controls only switch
precomputed views with common scales; no IBCS certification is claimed.

Set recipe `audience` to internal, client or public_demo; only synthetic examples
may use public_demo. Review all content for those readers. This Clara entry point
uses Clara's selected project/output scope and does not require Vera Studio
Archive. It does not direct Clara through Vera's client-bound entry points.

The Sites helper replays sources and the pack, checks audience equality, rejects
blocked reports and preserves earlier outputs. Publish its exact static `dist`
through Sites using the available hosting capability and existing authorization.
All financial views, optional customer/supplier/service labels, commentary and
limitations in the HTML reach Sites, including hidden views. Original exports,
raw populations and full pack JSON are not copied into the public output. No
automatic redaction occurs. Verify deployment and visitor access; sending
invitations needs authorized recipients. Reuse the Site ID for an explicitly
requested, reviewed refresh; there is no automatic recurring update.

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or any GitHub Pages/static-site folder unless the task is
explicitly plugin packaging/release. For user-data runs, choose an output
directory outside the repo, preferably a sibling `output/reporting-engine-<run>`
folder next to the user-provided input folder.

# Reporting Engine

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../clara/SKILL.md`.

## Required handoff for a reviewed report

When a reviewed run will leave its execution workspace, include
`--delivery-dir <new-final-bundle-directory>` in the `run_capability.py`
execution command. This exports and verifies the input and render evidence
alongside the completed run. Without this option, the command reports
`delivery_required: true`: use the explicit export command below before
delivery. Transfer the entire bundle, including hidden files, and verify it
at its final location. Manual selection or renaming of evidence breaks this
contract. Write report links against the final directory layout.

For any separately authored chart, calculate values and percentages directly
from the full-precision reviewed inputs; round only the displayed labels.
Retain the generating script and exact inputs. Resolve input paths relative to
the delivered script, or accept explicit input/output arguments. Generate from
the exported bundle's final paths; do not depend on a temporary working render
directory that will be removed. Test the retained script against the delivered
layout before calling it reproducible. After the last visual edit,
compute and check the hashes of the final image, script and inputs. An earlier
image receipt does not cover an edited image. Invoke
`advisory-deliverable-validator` on the final report and charts: read its complete
workflow and retain `advisory_validation_review.json` and `validation_audit.json`
for the exact final report. Reading the skill or verifying render bytes does
not complete that review. If a prerequisite is missing, follow the validator's
missing-prerequisite path and disclose the unfinished review.

In the report's reasoning review, separate observed changes from their causes.
Aggregate Sales/Units is average selling price: its change can reflect product
mix as well as within-product price changes. Do not attribute sales growth to
price alone without the corresponding decomposition, or to margin merely
because the margin rate increased. State descriptive movements and unresolved
drivers when the evidence does not establish causation.

The monthly period-comparison renderer includes a period-to-date monthly
average column: a label such as `_FebÆ` is its intentional IBCS notation,
not an extra month or corrupted source category. Inspect its recipe and values
before judging the column. Explain it in the report when retaining it; a
separate chart omitting it needs its own calculation and artifact evidence.

## Short descriptive summaries

For a short request limited to descriptive statistics over readable local data,
such as counts, median, range or missing values, inspect the source, units and
missing-value treatment and calculate with already available local tools. The
Python standard library is sufficient for a simple CSV summary. Return the
requested summary with its source and interpretation limits; do not initialize
a semantic project, run dependency setup or create a reporting run merely to
answer that request. This is a descriptive summary, not a reviewed Reporting
Engine execution or a calculation receipt for downstream professional handoff.

Use the full intake and reviewed execution below for chart selection, governed
reports, reusable dataset semantics or case contributions. A short summary must
not be used to manufacture those acceptance receipts or bypass their checks.

If the user forbids Internet access, do not run dependency checkers or launchers
that may install packages. Use an already prepared runtime for a full workflow;
if none is available, explain the limitation and complete only the supported
local work. Do not attempt an unmanaged import as a workaround.

## Reporting contracts and execution

Reporting Engine is Clara's reporting contract component. It packages the
reviewed chart-selection manifest, gallery artifact metadata, role registry,
family selector playbooks, Clara adapter registry, stable dataset semantic
contract, and a unified rendering entrypoint. Reviewed semantic layers for user
data are persistent project objects outside the repository. Dataset profiles,
snapshot attachments, compatibility audits, and render proofs are per-run
artifacts outside the repository.

The canonical component root is `../../modules/reporting-engine` relative to
this skill directory in both the editable Clara source and installed Clara
package. Run component helpers with that directory as the working directory.
There is no standalone Reporting Engine plugin or fallback source tree.

Use this component to answer mechanical questions:

- what chart capabilities exist;
- what roles a chart needs;
- which `reporting-engine.*` adapter owns the chart contract;
- which legacy plugin source is only provenance for that adapter;
- how to render a chosen capability through the adapter boundary;
- how to prove the exact input, effective request/recipe, and output bytes for
  that render;
- what dataset columns are candidate periods, metrics, dimensions, or
  identifiers;
- which reviewed metric, if any, represents Sales, Discount, or COGS, and
  whether any role is absent or ambiguous;
- whether a dataset is mechanically compatible with a chart;
- how to create, review, and validate a dataset-specific semantic layer that
  defines metric meaning, aggregation, dimensions, periods, and valid analyses.

Material choices for this component are limited to the dataset path, output
folder, chart family or capability filter, and whether optional render-library
requirements should be checked. They are not choices to propose as a substitute
for evidence. Inspect the actual inputs first; ask only those unresolved choices in chat. Do not introduce chart, metric, or dimension choices unless the facts cue them.

Do not treat the generated scaffold or deterministic validator as semantic
judgment. The scaffold marks every concept `unknown`. Claude or a human must
inspect source evidence and author or review business meaning and analysis
validity, including whether Sales, Discount, and COGS are mapped, absent,
ambiguous, or still unknown. A matching header is not enough to promote a
candidate automatically. Create semantics once for a stable caller-,
connector-, or project-assigned dataset contract id. On later uploads, reuse
that semantic version through snapshot compatibility; never regenerate
semantics merely because values, rows, members, or date bounds changed. A
`contract_valid` result proves coherent wiring only; it does not prove the
semantic claims are true or choose the final chart.

Local data and deterministic-script ownership are part of this workflow.
Deterministic scripts own manifest loading, dataset profiling, role-candidate
extraction, semantic document scaffolding, reference and role-binding checks,
package contract inspection, and mechanical compatibility evidence. Claude owns
source-backed semantic authoring and interpretation and must keep those
judgments separate from deterministic validation.

Explicit approval is reserved for external, destructive, approval-sensitive, or
material steps such as network access, deployment, package release, deleting
files, overwriting user data, or changing the canonical manifest. Local
read-only inspection, profiling into a user-chosen output folder, and contract
summaries can proceed without an approval checkpoint.

Before running component helper scripts, run this from the Clara plugin root:

```bash
python scripts/check_dependencies.py --module reporting-engine
```

This prepares and checks the component's declared managed runtime. For chart
rendering, add `--include-optional` so setup includes `requirements-render.txt`
and selects the same runtime as the render command. Host Python imports do not
describe what is installed in that managed runtime. Run the remaining commands
below from `modules/reporting-engine`.

If setup fails, retain the exact command, exit status and complete error output
in the run's diagnostic evidence before attempting anything else. Report the
failure if the declared setup cannot complete. Do not install directly into a
generation, call private runtime helpers, or write readiness receipts or active
pointers yourself. Those actions bypass the setup evidence and cannot establish
a successful Reporting Engine execution. `bootstrap_python_dependencies.py` is
the core SessionStart hook, not a replacement for module-specific setup.

For semantic-layer creation or review, read
`../../modules/reporting-engine/references/semantic_layer.md` relative to this
skill directory before authoring the dataset-specific JSON. The reference is
inside the component, not this wrapper skill's directory.

Whenever the user supplies a CSV, XLSX, or Parquet dataset, run
`scripts/dataset_intake.py` before chart compatibility or selection. On a first
upload, inspect the generated authoring context, the actual data, and available
source evidence; then author the semantic layer for the user. Explicitly review
Sales, Discount, and COGS. Map a role only to a source-backed reviewed metric;
record `absent` only when the evidence establishes no separate measure; record
`ambiguous` when plausible candidates remain unresolved; otherwise keep
`unknown`. Never ask the user to edit JSON. Ask one focused business question
only after the available files and sources cannot resolve a material ambiguity.
Save the reviewed layer as persistent project data outside the repository.

On later uploads, pass the same stable contract id and persistent reviewed layer
back to `dataset_intake.py`. Reuse an accepted mapping; do not infer identity
from a similar schema, overwrite the persistent layer, or silently create a new
contract after rejection. This workflow is local to Clara/Claude and does not
depend on a FastAPI upload route.

Useful commands:

```bash
python scripts/reporting_contract.py
python scripts/reporting_adapters.py
python scripts/reporting_adapters.py --capability period_comparison.trend --plan
python scripts/reporting_contract.py --capability period_comparison.trend
python scripts/dataset_intake.py <dataset.csv> --dataset-contract-id <stable-id> --output-dir <run>
python scripts/dataset_intake.py <new-snapshot.parquet> --dataset-contract-id <stable-id> --semantic-layer <project-data>/semantic_layer.json --output-dir <run>
python scripts/profile_dataset.py <dataset.csv> --output <run>/dataset_profile.json
python scripts/semantic_layer.py init --profile <run>/dataset_profile.json --output <run>/semantic_layer.json
python scripts/semantic_layer.py context --profile <run>/dataset_profile.json --layer <run>/semantic_layer.json --output <run>/semantic_authoring_context.json
python scripts/semantic_layer.py validate --profile <run>/dataset_profile.json --layer <run>/semantic_layer.json --output <run>/semantic_validation.json
python scripts/semantic_layer.py attach --profile <run>/new_snapshot_profile.json --layer <run>/semantic_layer.json --output <run>/snapshot_attachment.json
python scripts/check_compatibility.py <run>/dataset_profile.json --output <run>/compatibility.json
python scripts/render_capability.py period_comparison.trend <dataset.csv> --output-dir <run>/render --role-bindings-json '{"period_axis":"Date","comparison_metric":"Sales"}' --options-json '{"current_period_label":"<current-period>","previous_period_label":"<baseline-period>"}' --artifact-mode data_only
python scripts/mechanical_acceptance.py --suite --output-dir <empty-run-dir> --execute --artifact-mode data_and_render
```

Current boundary:

- the manifest and gallery artifact metadata are packaged as product contract
  evidence;
- every manifest capability resolves to a Clara-owned reporting-engine adapter;
- `scripts/render_capability.py` is the low-level diagnostic render entrypoint for a chosen
  capability;
- each `render_manifest.json` uses schema `0.2` and records SHA-256 plus byte
  counts for the input and every current-run output, a canonical request
  digest, effective-recipe evidence, and an output-set digest; every invocation
  renders inside a fresh isolated directory so a pre-existing artifact never
  counts as current-run by mere presence;
- old chart-family plugin names are provenance, not the caller-facing boundary;
- the chart-family components are embedded in Clara and called through the
  unified render entrypoint;
- the profiler creates runtime dataset-side role candidates;
- `scripts/dataset_intake.py` is the first local entrypoint for CSV, XLSX, and
  Parquet files; it writes the profile, draft/context or compatibility
  attachment, and an intake receipt without making hidden semantic decisions;
- `catalog/semantic_layer.schema.json` defines a persisted stable dataset
  semantic contract with explicit identity and semantic version;
- `scripts/semantic_layer.py` creates an unreviewed scaffold, packages all 48
  manifest analysis types for model-led review, validates evidence and
  canonical-role bindings, attaches mechanically compatible snapshots, and
  resolves reusable period rules into snapshot-specific bounds;
- equal schemas never establish logical dataset identity; the caller, source
  connector, or project configuration must supply the stable contract id;
- changed values, rows, members, and date bounds do not invalidate semantics;
  missing or role-incompatible bound fields disable affected analyses;
- reviewed analysis policies use manifest task and selection-emphasis ids as
  join keys but do not contain or choose a final chart id;
- `contract_valid` and `semantic_readiness` are separate: a mechanically valid
  draft remains `draft_unreviewed`;
- canonical Sales, Discount, and COGS mappings remain `unknown` until
  source-backed model or human review records them as mapped, absent, or
  ambiguous;
- unlisted manifest analysis emphases remain `unknown`; a reviewed semantic
  layer is ready only within its declared scope and does not need one policy per
  chart;
- compatibility evidence distinguishes required roles from optional roles,
  reports candidate and ambiguous columns for both, and only rejects missing
  required roles;
- period-filter charts require a bounded scope or an explicit all-data request,
  while period-axis charts may intentionally use the available range;
- comparison charts require distinct current and baseline periods;
- the root-cause exploded bridge binds a generated alternative driver sequence
  and then one or more one-based drilldown rows; neither choice is hidden in the
  renderer;
- the packaged mechanical acceptance suite currently executes and render-proves
  all 48 capabilities against synthetic fixtures;
- the packaged semantic fixture proves nine valid analysis policies bind
  complete manifest role sets and one unsupported statement analysis remains
  explicitly invalid;
- Clara may use the evidence to narrow chart choices;
- automatic chart selection and full report orchestration are intentionally not
  implemented here.

When a rendered data artifact feeds an HTML deck, seal that CSV or JSON into
the HTML Deck `clara.evidence_bundle.v1` contract and bind the prepared series
or cell. Never copy values from the render manifest into prose or a plot spec.
The current renderer still accepts one input file (except the attribute-package
boundary). Multi-source analytical work must first use reviewed semantic and
relationship decisions to materialize deterministic evidence tables; the
renderer must not infer cross-source joins.

When a Reporting Engine result introduces or updates a claim in a Clara case,
record the model-authored claim and calculation meaning through the shared
handoff helper:

```bash
python scripts/record_reporting_contribution.py \
  --case-dir <case-dir> \
  --render-manifest <run>/render_manifest.json \
  --contribution <model-authored-reporting-contribution.json> \
  --verification-artifact <run>/semantic_validation.json \
  --verification-artifact <run>/compatibility.json
```

The contribution JSON supplies the semantic observation, scope, limitations,
method, full claim record, and optional judgement projection. The helper does
not infer them. It verifies the authoritative Reporting Engine 0.2 result,
input, recipe, current-run outputs, output-set digest, and added verification
files, then creates the `calculation_run` receipt and commits the receipt,
claim, and judgement projection atomically. The claim must reference that
receipt in both `evidence_links` and `calculation_evidence_id` and names any
upstream claim dependencies. This cross-workflow receipt lets the advisory
validator find and selectively rerun the exact calculation; it does not replace
Reporting Engine's semantic review, compatibility checks, calculation logic,
or render proof.

### Execute from reviewed semantics

After semantic acceptance, prefer `scripts/run_capability.py` for a supported
reviewed analysis. It derives role columns, currency and period scope from the
accepted policy instead of taking fresh caller overrides:

```bash
python scripts/run_capability.py <dataset> --layer <semantic_layer.json> --profile <dataset_profile.json> --acceptance <acceptance.json> --source <reviewed-source-notes> --analysis-id <reviewed-policy-id> --capability-id <selected-capability> --output-dir <run>/render
python scripts/run_capability.py --verify-output <run>/render
```

Repeat `--source` for every source bound in acceptance. Verify again before
registering an analysis contribution and bind `reviewed_execution.json` as an
exact-basis evidence artifact together with the selected output. A changed
source, semantic layer, profile or rendered artifact invalidates that handoff.
The receipt proves execution against declared reviewed inputs, not the truth
of a business conclusion or professional approval of the deliverable.

The current compiler rejects unmaterialized derived metrics, grouped weighted
aggregations, compound bindings and unsupported period-window adapters. Keep
those requirements visible and use the owning preparation workflow; never
change a metric's aggregation rule or use a diagnostic run to bypass the gap.
`render_capability.py` remains available for mechanical diagnostics. Its output
alone is not proof of execution under reviewed semantics.

### Keep intake parser settings through rendering

For Excel or a non-default CSV dialect, carry the selected table settings from
`dataset_profile.json` into `render_capability.py --parser-settings-json`.
For example, use `'{"sheet_name":"Reviewed"}'` for that exact Excel sheet or
`'{"csv_options":{"separator":";","decimal_comma":true}}'` for a reviewed
regional CSV. The renderer parses once, supplies a normalized UTF-8 CSV to the
component, and records the parser settings and normalized-byte hash. Temporary
normalized input is removed after the run; the source stays unchanged.
Do not change settings to obtain a passing chart. Return to intake if the
selected sheet, parsing contract, or source bytes differ from the reviewed input.
These checks establish parsing identity, not semantic approval of the analysis.


## Cowork-native Run UX

For full reporting execution, inspect the manifest contract, run dataset intake when a tabular file is
provided, create or load the dataset semantic layer, review Sales/Discount/COGS,
validate its evidence and role bindings, and compare required chart roles with
role candidates. Report the result concisely; a checklist or intake table is
optional, while the semantic and mechanical checks remain required. For a short
descriptive summary, follow the bounded path above instead.

Default output policy: write user artifacts outside this repository. Catalog
changes, generated ZIPs, and package checks are allowed inside the repo only
when the task is explicitly plugin packaging or release.

When a table helps explain compatibility, show facts and evidence: chart
capability, required roles, matched dataset columns, missing
roles, ambiguous roles, invocation contract status, and render-proof status.

Use an execution checkpoint before claiming a chart family is ready: the
manifest must load, the dataset profile must exist when relevant, the semantic
layer must be reviewed for any semantic claim, mechanical compatibility must be
shown, and any missing role must be visible. If a run creates persistent
artifacts, include a `run_review.md` file that links the manifest, dataset
profile, semantic layer, semantic validation, compatibility table, and any final
JSON outputs.

Before delivery, reconcile each diagnostic with its own scope. Unresolved
bindings in an analysis policy and missing roles in a dataset compatibility
check are different populations. Do not merge their counts or describe
available columns as absent. Explain the
source-backed reason an analysis is unsupported; mechanical compatibility alone
does not establish professional feasibility or the truth of that judgment.

Resolve every review-index and report link from the file that contains it,
after copying the final bundle to its delivery location. Retain the referenced
evidence there. A separately authored chart is a new artifact: identify it as
such, retain its generation source and input identity, and check its displayed
values. Do not attribute the packaged renderer's byte proof to that replacement.

Reporting publication uses `current_reporting.json` as the current-generation
pointer. Completed generations live under `.reporting-generations/` and contain
the exact render manifest, outputs and generated recipe. Working copies in the
output directory may be replaced during another attempt. Before handoff, use
`run_capability.py --verify-output <output-dir>`; its `publication` result gives
the verified generation directory and checks that its manifest is exactly the
reviewed one. Deliver artifacts from that generation. A running or failed
pointer is not a successful current render, even if older files still exist.
These byte checks do not validate chart interpretation or business conclusions.

For delivery outside the execution workspace, export the complete verified run:

```bash
python scripts/run_capability.py --export-output <output-dir> --delivery-dir <new-delivery-dir>
python scripts/run_capability.py --verify-output <new-delivery-dir>
```

The export copies the reviewed source inputs, preserves original receipt and
artifact names, and includes the current hidden generation directory. Keep the
entire exported directory together when transferring it, including hidden
members and `reporting_delivery.json`. Do not manually select or rename its
evidence files. Use the exported descriptor's actual relative input paths when
referencing the semantic layer or source notes. Verify the transferred bundle
again at its final location. A successful verification prints `status: verified`;
it proves byte identity and reviewed input wiring, not the report's conclusions.
Author the management report and its links against this final file layout.

Before delivering, review the actual report and charts with
`advisory-deliverable-validator`. Check the report's unsupported-analysis
explanation against the sources; a missing mechanical role is evidence about
an adapter contract, not proof that a professional conclusion is "not a
judgment call". Inspect each chart at its delivery size for clipped titles,
legends and source notes. For a separately authored chart, keep its generating
script and exact input references alongside it. If the user requests an
independent run excluding earlier outputs, do not read them for formatting or
other context either.
