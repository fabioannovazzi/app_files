---
name: bandi-agevolazioni
description: Use when Vera must discover, monitor, match, prepare, or review Italian grants, subsidies, tax credits, or subsidized finance from official sources and client evidence; produces a reviewable opportunity radar or application dossier and never authenticates, contacts clients, signs, or files.
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

# Bandi e agevolazioni

Operate one of two connected stages:

1. a private opportunity radar that builds opaque company profiles, plans and
   records official-source checks, monitors opportunity lifecycle, matches one
   opportunity to one or more clients in both directions, and prioritizes
   professionally reviewable opportunities; or
2. one source-bound application dossier inside a running Studio Archive
   engagement after an opportunity has been selected.

Treat source relevance, compatibility, lifecycle meaning, economic assumptions,
eligibility, exclusion, eligible-cost, document, form, and narrative conclusions
as proposals until the responsible professional reviews them.

## Output location

Never write run outputs inside this Git workspace or a published folder. Stage A
uses one explicitly authorized, owner-only studio-radar workspace bound to its
exact local path; it is not a portable client run. Stage B uses only the exact
private Studio Archive client-run output described below.

## Hard boundaries

- Never invent eligibility, exclusion, eligible-cost, deadline, document, or
  form requirements.
- Never use deterministic keywords to select the governing framework or decide
  the meaning, applicability, or authority of a source.
- Never request, store, replay, or export credentials, SPID/CIE/CNS material,
  cookies, tokens, one-time codes, delegations, or signatures.
- Never log in, fill a live portal, accept a declaration, sign, pay, save a
  portal draft, or submit an application. Produce field-by-field guidance and
  stop before every portal action.
- Never use `ready` as a synonym for eligible or accepted. Keep documentary
  readiness separate from the assessment outcome. `ready_to_file` is always
  false.
- Treat an official FAQ as clarifying evidence whose effect requires review;
  never let it silently override a formal act.
- Keep OCR-derived facts at `verify` until the source image is visually checked.
- Never describe a source-plan coverage ratio as the probability that all
  opportunities were found. It measures only checked sources in the reviewed
  plan.
- Never begin semantic web discovery for a recent-opportunity scan before every
  reviewed priority source has been directly attempted for the requested
  window. Disclose every failed, unavailable, missing or unreviewed priority
  source instead of calling the scan complete.
- Never place client identity, financial data, project narrative, quotations,
  or declarations in public discovery queries. Portfolio radar profiles use
  opaque client references.
- Never contact a matched client automatically. The professional owns whether,
  when, and how to contact the client.

Reserve explicit approval for an external, destructive, approval-sensitive, or
material step. Ordinary local evidence inspection and deterministic validation
inside the already selected run do not require a separate confirmation.

## Cowork-native Run UX

1. Show a checklist covering dependencies, Run Intake, source selection,
   workbench drafting, professional review, validation, and packaging.
2. Show a Run Intake table with the opaque client reference, call identifier,
   reference date, bound input and output paths, source-set revision, and
   external-research posture.
3. Use a Decision Table for unresolved source authority, applicability,
   requirement meaning, eligibility, exclusions, costs, missing evidence,
   conflicting facts, form fields, narrative claims, and portal guidance.
   Generate it from the actual inputs; do not offer named classifications,
   authorities, or legal conclusions unless the facts cue them.
4. Ask only about material choices that change the case, governing source,
   professional conclusion, destination, or authorized write scope.
   Ask only those unresolved choices in chat and wait only when an answer would
   materially change the scope or authorized action.
5. Before a long or write-heavy stage, show an execution checkpoint with the
   bounded inputs, private output path, intended command, and expected files.
6. End with an Artifact Card listing source count, disposition, validation,
   stale or missing reviews, blockers, outputs, and the next authorized-person
   action.

Default output policy: produce the ordinary private JSON, audit, and Markdown
review package when the tooling can do so. These are not choices to propose.
When useful, save the visible run summary as `run_review.md` beside the
package. Never edit plugin source or generated ZIPs during a customer case run.

## Client boundary in Cowork

Cowork does not package Studio Archive, so it cannot select or register its
local clients, import controlled snapshots, prepare or start customer-folder
runs, or finalize their artifact manifests. Use a product CLI only when a
compatible local Vera installation supplied a digest-valid, running
`vera.client_workflow_context.v2` for this exact workflow and its complete
customer-folder ledger paths are available. Otherwise work from the exact
connected files, preserve a reviewable file-based handoff, and state that the
sealed customer-folder run remains pending. Never invent an ID, receipt,
lifecycle state, or completed artifact declaration.

## Workflow

Read `references/product-thesis.md`, `references/workflow-method.md`,
`references/opportunity-radar.md`, `references/source-first-discovery.md`, and
`references/implementation-status.md` completely before interpreting sources,
requesting a model contribution, or editing either workbench. Use
`references/acceptance-matrix.md` when reviewing or releasing the workflow.

### Stage A — opportunity radar

Initialize a private studio radar. `single_client` accepts at most one opaque
profile; `portfolio` supports reverse matching from a newly observed
opportunity to several opaque client references:

```bash
python scripts/opportunity_radar.py \
  --workspace <private-radar-workspace> \
  initialize \
  --radar-id <stable-id> \
  --workspace-id <stable-private-workspace-id> \
  --reference-date YYYY-MM-DD \
  --scope single_client|portfolio \
  --authorized-by <operator> \
  --retention-owner <firm-or-professional> \
  --confirmed-by-user
```

Initialization records an asserted-not-authenticated authorization receipt and
binds the radar to that exact non-Git, non-published directory. The professional
owns its local retention. Moving the radar or changing its path fails closed;
create a new explicitly authorized workspace rather than editing its receipt.

Use the model semantically to propose profile facets, a jurisdiction- and
client-specific official-source plan, source-backed opportunities and matches.
Register opaque profile evidence receipts first with `record-evidence`; every
document-observed facet must close to a same-client receipt. Record each
proposal with exact provider, model, prompt-template and operator provenance
using `record-profile`, `record-source`, `record-opportunity`, and `record-match`.
Record actual source checks separately with
`record-source-check`; a planned source is not checked merely because it is in
the plan. Use `record-scan` for resumable monitoring runs and preserve lifecycle
history rather than overwriting an earlier status.

For recent discovery, treat the reviewed source plan as a persistent priority
registry. Each source proposal must state `discovery_role`, `source_surface`,
`territories`, `categories`, and `act_families`; those fields remain model-led
and professionally reviewed. For each temporal scan, use model reasoning to
propose an exact query-scoped selection from confirmed registry entries. The
selection must declare one `covered` or `gap` claim for every territory and
category in the generic query context, cite the selected source IDs and explain
the semantic rationale. Code checks only exact claim presence, IDs and roles; it
does not match territory or category strings to publishers.

Start the scan with exact selection provenance, review the selection explicitly,
then render its direct-source worklist:

```bash
python scripts/opportunity_radar.py \
  --workspace <private-radar-workspace> \
  record-scan \
  --input <running-scan.json> \
  --idempotency-key <stable-scan-start-id> \
  --origin model_suggested \
  --provider <provider> \
  --model <exact-model> \
  --prompt-template-version bandi-source-selection-v1 \
  --recorded-by <operator>

python scripts/opportunity_radar.py \
  --workspace <private-radar-workspace> \
  review \
  --scope scan_source_selection \
  --target-id <scan-id> \
  --decision accepted \
  --reviewer-id <reviewer> \
  --reviewer-role commercialista \
  --confirmed-by-user \
  --idempotency-key <stable-selection-review-id>

python scripts/opportunity_radar.py \
  --workspace <private-radar-workspace> \
  worklist \
  --scan-id <scan-id>
```

Inspect every priority URL directly across the requested window, including
relevant DGR, DDR, BUR issues, annexes, FAQs and amendments. Record each check
against the running scan; optionally pass a cursor JSON containing the latest
stable publication ID, publication date or official URL:

```bash
python scripts/opportunity_radar.py \
  --workspace <private-radar-workspace> \
  record-source-check \
  --source-id <source-id> \
  --check-id <stable-check-id> \
  --scan-id <scan-id> \
  --check-status checked \
  --checked-at <ISO-date-time> \
  --window-start YYYY-MM-DD \
  --window-end YYYY-MM-DD \
  --result-count <count> \
  --cursor-input <optional-cursor.json> \
  --idempotency-key <stable-check-operation-id>
```

Review each check, then use semantic web research only as a complementary last
phase. Finish the same scan with a terminal payload. `complete` is rejected
unless the selection is confirmed, every query dimension is declared covered,
and the sealed coverage snapshot resolves every selected priority source.
Otherwise record `partial` or `failed` and report the exact scope gaps and
unverified source IDs. A rejected registry proposal outside the reviewed scan
selection never blocks that scan. A source cursor accelerates delta detection
but never replaces the stated historical window. Read
`references/source-first-discovery.md` for the complete contract.

Review each evidence receipt, source-plan entry, source-check result, profile,
opportunity and match explicitly. `source` confirms plan relevance;
`source_check` separately confirms the exact observed check result:

```bash
python scripts/opportunity_radar.py \
  --workspace <private-radar-workspace> \
  review \
  --scope evidence|profile|source|source_check|scan_source_selection|opportunity|match \
  --target-id <id> \
  --decision accepted|returned|rejected \
  --reviewer-id <reviewer> \
  --reviewer-role commercialista \
  --confirmed-by-user \
  --idempotency-key <stable-review-id>
```

When confirmed profile or opportunity facts change, supply an append-only
`revision_event` with a stable ID, observed time, rationale and referenced
evidence or official sources. The changed item and dependent matches return to
`proposed`; prior review events remain historical.

Render `opportunity_radar_review.md` with `report`. After the exact evidence,
profile, checked source-plan entries, check results, opportunity and match are
confirmed, use `handoff` to write one selected match inside the radar workspace.
The handoff embeds only that client's evidence and sources and carries
recomputable selection and source-entry hashes. Import that JSON as a source
into the chosen client's new Studio Archive `bandi-agevolazioni` engagement and
register it with source type `opportunity_handoff` and authority role
`mechanical`. Registration revalidates schema, hashes, client identity and
reference closure. The handoff selects work for instruction; it is not evidence
of eligibility and does not replace the exact official call materials.

### Stage B — application instruction

1. Run `python scripts/check_dependencies.py` from the component root. The
   declared `jsonschema` dependency is required for exhaustive runtime contract
   validation; do not install it at runtime.
2. Initialize the bounded drafts:

```bash
python scripts/initialize_case.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path> \
  --reference-date YYYY-MM-DD \
  --client-reference CLIENT-OPAQUE-001
```

3. Register each exact selected input without copying or fetching it:

```bash
python scripts/register_source.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path> \
  --source <bound-input-file> \
  --source-id SOURCE-001 \
  --source-type call \
  --title "Official call title" \
  --issuer "Issuing authority" \
  --authority-role primary \
  --selected-by <reviewer>
```

   After professional source selection, record amendments, supersession,
   clarification, implementation, and incorporation links mechanically:

```bash
python scripts/link_sources.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path> \
  --source-id AMENDMENT-001 \
  --kind amends \
  --target-source-id CALL-001
```

4. Read the selected sources and client evidence. Request one bounded semantic
   contribution at a time. Create a bounded task packet without mutating the
   case. The intake applicant object and local paths are not copied by default,
   but professionally relevant facts and excerpts may still identify the
   applicant; there is no automatic anonymization:

```bash
python scripts/intelligence_workflow.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path> \
  packet
```

   Record the exact response and exact provider/model/template identity as a
   non-authoritative `MODEL_SUGGESTED` run:

```bash
python scripts/intelligence_workflow.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path> \
  record \
  --model-output <strict-output.json> \
  --provider <provider> \
  --model <exact-model> \
  --prompt-template-version bandi-intelligence-v1 \
  --recorded-by <operator> \
  --idempotency-key <stable-request-id>
```

   Claude/model reasoning may propose atomic requirements, facts, assessments,
   document checklist items, expenses, form fields, narratives, consistency
   checks, issues, and an adversarial authority-review simulation. It cannot
   update the workbench until a professional explicitly accepts that exact run:

```bash
python scripts/intelligence_workflow.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path> \
  decide \
  --intelligence-run-id INTEL-000001 \
  --decision accepted \
  --reviewer-id <reviewer> \
  --reviewer-role commercialista \
  --confirmed-by-user
```

   `rejected` and `returned` are also explicit terminal decisions. Accepted
   contributions enter `application_workbench.json` only as `proposed`; they
   never overwrite confirmed or blocked work. Any change to intake, sources, or
   workbench makes an undecided run stale. Deterministic scripts validate shape,
   identity, references, exact arithmetic, review hashes, status consistency,
   and prohibited portal controls; they do not interpret the call.
5. Record explicit professional decisions mechanically:

```bash
python scripts/record_review.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path> \
  --scope source_baseline \
  --decision accepted \
  --reviewer-id <reviewer> \
  --reviewer-role commercialista \
  --confirmed-by-user
```

   Review scopes are `source_baseline`, `requirements`, `assessments`, and
   `dossier`. A changed bound artifact invalidates the prior review hash.
   Use `--confirmed-by-user` only after the user explicitly confirms that exact
   scope and decision. The local reviewer ID and role are asserted metadata,
   not authenticated identity; the dossier states this boundary and remains
   for authorized professional review.
6. Validate and package the private review dossier:

```bash
python scripts/validate_application.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path>

python scripts/package_dossier.py \
  --output-dir <run-output> \
  --client-engagement <client_engagement_path>
```

7. Show the professional the exact readiness/outcome matrix, missing evidence,
   unresolved interpretations, red flags, draft form fields, and narrative
   claims. Do not hide negative or uncertain findings in polished prose.
8. Provide portal assistance only as a manual field map. The authorized person
   owns authentication, declarations, signature, saving, and transmission.

## Status contract

Readiness is `ready`, `missing`, `verify`, or `not_applicable`. Assessment
outcome is separately `satisfied`, `not_satisfied`, `uncertain`,
`not_applicable`, or `not_assessed`. `not_applicable` requires a reviewed
rationale. A conclusive negative assessment may therefore be documentary
`ready` while making the dossier unsuitable for filing.

## Deterministic boundary

Use deterministic code only for mechanically verifiable work: exhaustive JSON
Schema and ID validation, exact hashes, path containment, source/reference
closure, workspace and handoff path binding, review freshness, source-plan
check ratios, source-registry revision binding, exact query-dimension claim
closure, query-scoped selection reference closure, temporal-window containment,
direct-before-semantic execution order, cursor preservation, scan completion
coverage, chronological lifecycle-history preservation, exact
economic range subtraction from supplied assumptions, the versioned
`exact_decimal_compare` and `exact_date_compare` rule families after their
inputs and outcome mapping are professionally confirmed, status invariants,
review hash binding, and packaging. Keep source-plan selection, source
relevance, opportunity meaning, compatibility, lifecycle meaning, economic
assumptions, recommended action, source authority, requirement meaning,
eligibility, exclusions, cost classification, narrative judgment, conflict
significance, and simulated-authority review model-led and professionally
reviewed.
