---
name: business-planning
description: One shared, adaptive Business Planning workflow for startups, new ventures and established companies. Vera owns the accounting-financial result; Clara owns the strategic-commercial result. Counterpart work is internal and all financial claims bind Vera's calculation register.
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

Never write run outputs inside this Git workspace or a published folder. Vera
uses the exact Studio Archive run output for workflow ID `business-planning`.
Clara uses the selected advisory case workspace and its `business-plan` folder.
Synthetic developer evaluations may write to a temporary test directory.

# Business Planning

Use one shared case and compiler. The invoked product remains the visible owner
from intake through delivery. Do not ask the user to invoke the other product,
transfer contribution files or choose a lens or company-stage mode.

- Vera owns the accounting-financial result. Obtain Clara's model-led strategic
  contribution internally when the mandate requires strategy, market or options.
- Clara owns the strategic-commercial result. Obtain Vera's financial contribution
  internally whenever financial figures, feasibility or funding enter the result.
  The shared runner invokes Vera's arithmetic directly; no separate plugin call
  or manually supplied financial summary is necessary.
- Both use exactly the same source register, assumptions and authoritative
  calculated figures. Internal contributors edit proposed sections of the shared
  case; the owner resolves differences with the professional before acceptance.
- Record company stage in reviewed plain language. Adapt source collection and
  questions to the actual business, including new ventures inside existing firms.
  Missing history never becomes zero. Do not infer stage using keyword rules.

## Intake and review

Read [the case contract](../../references/case-contract.md). Both entry points
require `mparanza.business_planning_case.v2`. Legacy v1 case and counterpart files
are inspection inputs only; they cannot finalize reports. Migrate by inspecting
actual files and obtaining real assumption/audience decisions, never by inventing
review metadata. Do not assume an earlier report used this registered pipeline.

Establish entity, mandate, audience, currency, monthly horizon, source selection,
opening position, scenarios and material unknowns from the actual evidence. Ask
only material unresolved questions. Keep the user informed about intake, evidence
review, financial calculation, strategic interpretation, validation and delivery.

For every selected file record its relative path, actual SHA-256, version, role,
review status, intended audience and explicit confidentiality restrictions. Roles
distinguish client documents, professional reviews, existing financial models,
external evidence and model-created hypotheses. Hashes establish file identity,
not truth. Existing spreadsheets must be reconciled as evidence.

The model and professional must extract and align material source figures into
`observations` with period, scenario, metric, units and source IDs. Include
contradictory values, not only values supporting the preferred conclusion.
Deterministic grouping exposes differences in these reviewed alignments; it
cannot discover omitted claims or interpret raw documents. Review source coverage
and completeness explicitly before marking the case reviewed.

Keep facts, assumptions, hypotheses, calculated results, conflicts and professional
decisions distinct. Confirm every material assumption, including financing timing,
debt service, working capital and the variable/fixed cost split, with a named
professional and timestamp. Explicit confirmed zero differs from missing `null`.
Each input needs evidence/assumption references effective for its period.

An accepted conflict resolution names an observation and a reviewed professional
decision. Never silently select a conflicting number. Unresolved material conflicts
produce partial results; disagreement with accepted figures blocks readiness.

## Financial and strategic work

Vera's shared engine calculates monthly scenarios and linked statements, margins,
EBITDA/EBIT/net income, cash flow, working capital, minimum cash, pre-financing
funding need and residual gap, runway, revenue break-even, margin of safety,
debt service/DSCR and sources-and-uses reconciliation. Read their formula and
limitation fields. Do not treat mechanical reconciliation as viability.

Clara interprets reviewed market evidence, positioning, options, initiatives,
commercial implications and risks. All financial amounts in narrative use typed
`{{claim}}` placeholders with exact calculation IDs and expected values. Clara
must never independently calculate or rewrite a Vera amount. Correct the accepted
inputs and rerun the shared engine if figures need changing.

Do not invent scores, benchmarks or KPI thresholds. They require a reviewed rubric,
source, or explicitly labelled and confirmed professional hypothesis. A reference
to a number does not support the meaning of a score: professional review must check
both numerical and semantic claims, including numbers written as words and implied
recommendations. The compiler checks exact bindings, not prose meaning.

A precise capital recommendation requires the complete accepted cash-flow model,
all material reviews/conflicts resolved, and the full-horizon `funding_requirement`
calculation ID. It is not permission to recommend a financing instrument, valuation,
buffer or round size unsupported by that model. Report missing inputs and questions
instead. Financing timing and unpaid/missing debt cannot be hidden in prose.

## Registered execution

Run `python scripts/check_dependencies.py` first. `requirements.txt` is the core
published dependency declaration; do not install arbitrary packages at runtime.

Vera imports the shared case and **every selected source** as exact same-engagement
Studio Archive receipts, then prepares and starts workflow `business-planning`.
Use source paths relative to the run's `input_dir` (`imports` / receipt ID / stored filename),
and pass the returned context unchanged. Inputs are checked against exact receipts.

```bash
python scripts/run_business_plan.py --case <receipted-case.json> \
  --client-engagement <context.json> --source-root <run-input-dir> \
  --output-dir <run-output>/plan
```

Clara keeps its case JSON at the advisory case workspace root and all selected
sources below that workspace:

```bash
python scripts/run_strategic_plan.py --case <case-workspace>/business_plan_case.json \
  --case-workspace <case-workspace> --source-root <case-workspace> \
  --output-dir <case-workspace>/business-plan
```

Use a fresh output folder. Exit code 2 means partial/blocked or rejected input;
inspect the report/validation file if written. Do not overwrite a previous report.

## Controlled delivery

Only the shared compiler produces the deliverable. Do not draft an independent
final HTML, Markdown, spreadsheet or PDF with copied figures. Edit the reviewed
structured case and rerun. Normal outputs are `business_plan.json`,
`report_structure.json`, `business_plan_review.html`, `calculations.json`,
`calculations.csv`, `input_manifest.json`, `reconciliation.json`,
`validation.json` and `execution_receipt.json`.

The compiler replays arithmetic, source hashes, reference closure, narrative
bindings and chart data before rendering. It includes complete provenance,
comparisons, professional decisions, unresolved matters, limitations and audience
restrictions. Audience release requires an explicit reviewed decision bound to the
source's hash; internal-only material cannot be exported to a different audience
merely because a new audience name was entered.

HTML comes first. Visually inspect it, including chart axes, negative results,
zero lines, legends, source comparisons and provenance tables. PDF is optional via
`--pdf`, solely from that validated structure. Check `requirements-pdf.txt` before
using the optional renderer; no PDF is permitted for a partial or blocked result.

Charts use canonical calculation IDs only: reported versus adjusted EBITDA when
available, EBITDA scenarios, monthly cash before/after financing and cumulative
funding gaps. Reported values are labelled source projections, not accepted EBITDA.
Do not add decorative progress bars, unsupported scorecards or channel unit
economics when channel-specific inputs are absent.

For model interpretation provide only the reviewed, audience-permitted excerpts,
assumptions and calculation records needed for the assignment. Full local source
files and paths are not automatically model context. The full report structure is
an audience-controlled local audit artifact; do not send it wholesale to a model
or external service without the relevant data-use authorization.

Deliver one owner report with its status, supported conclusions, open matters and
next professional action. Finalize Vera's physical output artifacts with stable
IDs, purpose, audience and media type and complete the Studio Archive run. Record
failure/cancellation honestly. Clara records results in the selected case workspace.

## Cowork-native Run UX

Show a compact checklist for intake, evidence/assumption review, calculation,
interpretation, validation, visual inspection and delivery. Use a Run Intake table
for the actual entity, mandate, audience, horizon, sources and output folder, and
a Decision Table only for unresolved material choices. Confirmed facts and
accepted assumptions are not choices to propose.

Default output policy: use only the selected run/case folder. End with an Artifact
Card giving the report path, status, unresolved matters and next professional
action. Include `run_review.md` when the host needs a review note. Build
generated ZIPs from canonical source; never edit their extracted copies.

Ask only those unresolved choices in chat, grounded in the actual inputs. Do not
introduce hypothetical alternatives unless the facts cue them. Before execution,
show an execution checkpoint with the selected inputs, command intent, output
folder and expected artifacts.
