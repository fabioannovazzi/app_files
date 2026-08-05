---
name: bilancio-xbrl-it
description: Use when an Italian professional accounting studio asks Vera or Codex to understand accounting evidence and intelligently prepare, update, reconcile, review, validate, or export an individual OIC civil-law annual financial statement from CSV/XLSX evidence, a prior XBRL, or structured schedules. XBRL is a final deterministic output format, not the workflow identity. The workflow never invents missing facts, signs, approves corporate accounts, or files them.
---

# Bilancio intelligente

After substantive use, read and follow the `Plugin Improvement Feedback`
section at the end of this skill.

Before operating or describing this workflow, read
`references/product-thesis.md`, `references/implementation-status.md`, and
`references/acceptance-matrix.md` completely. The product thesis is fixed: the
existing bilancio process remains the process, and Vera makes its execution
intelligent. Do not reduce the workflow to XBRL generation, exception
detection, or a separate AI feature.

## Product boundary

The canonical, reviewable bilancio is the product object. XBRL is one final
export adapter for an approved snapshot. Intelligence must participate inside
source understanding, mapping, ambiguity recognition, evidence requests,
prior-year reuse, schedules, disclosures, narrative preparation, validation
explanations, and review direction. It is not a chatbot placed above passive
forms.

Technical sequencing may establish deterministic plumbing before every
intelligent behavior is available. That delivery order must never be presented
as the product thesis or make intelligence an optional later mode.

## Safety boundary

Prepare a reviewable draft for a commercialista. Never present Vera as the
corporate approver or filer. Never sign digitally, submit to Registro Imprese,
automate an undocumented TEBENI browser flow, or turn a missing fact into zero.

Use deterministic code only for exact parsing, Decimal arithmetic, explicit
effective-dated rule conditions, reference closure, revision hashes, XML
construction, and XBRL validation. Use model-led reasoning or professional
review for ambiguous account meaning, accounting treatment, legal relevance,
materiality, narrative drafting, and evidence sufficiency. A model suggestion
is never an accepted fact.

Real case data may enter the selected Codex or Cowork model context. Do not
promise local-only processing or automatic anonymization. The user's selected
runtime account controls apply. TEBENI upload is optional, external, and
user-controlled; obtain explicit route choice before transmitting a file.

The service-facing intake must use the host-configured malware scanner and may
not treat safe parsing as a clean malware verdict. Return exported bytes only
through the checksum-bound short-lived artifact grant when that delivery
boundary is configured; never expose the local storage path or signing secret.
Do not invent a retention duration. Archive and deletion are available only
when the deployment supplies the owner-approved tenant policy; deletion must
remain blocked until its exact recorded cutoff.

## Output location

Never write run outputs inside this Git workspace or a published folder. For a
customer case, use one prepared and started Studio Archive engagement
run. Keep source receipts and all generated case/export artifacts below that
run. Never write customer outputs into this Git repository, the plugin source,
or a public folder.

## Required intake

Confirm or obtain:

- entity, tax identifier, legal form, OIC framework, listed and regulated flags;
- reporting period, comparative period, first-year flag, and prior form;
- trial balance with opening, debit/credit movements, closing, and comparative;
- annual threshold metrics and any micro-enterprise exclusion flags;
- official taxonomy package, entry point, and verified SHA-256 before XBRL export;
- named preparer and reviewer identities.

Reject listed, IFRS, regulated, insurance/banking, consolidated-note,
sector-taxonomy, ETS, public-sector, and final-liquidation cases in the MVP.
Missing scope flags are not evidence of eligibility.

## Run workflow

Resolve the module root as the directory two levels above this skill. Run the
dependency check before helper scripts:

```bash
python scripts/check_dependencies.py
```

Do not install missing packages at runtime. `requirements.txt` is the declared
runtime contract. Report the missing dependency and let the user or deployment
process update the environment.

The optional HTTP deployment additionally uses `api-requirements.txt`. Check it
only when operating `scripts/http_api.py`; do not make FastAPI a completion gate
for the normal Vera/MCP workflow.

Explicit approval is reserved for external, destructive, approval-sensitive,
or material steps. Ordinary local inspection, deterministic calculation, and
validation do not require a separate approval ceremony. Manual TEBENI upload
and final professional approval always require the user's explicit choice.

1. Create the scope-checked case with `scripts/xbrl_case.py create`. Lock the
   statutory, OIC, filing, and taxonomy identifiers supplied in the payload.
   Require legal name, reporting identifier, registered office, explicit
   first-year status, and the prior statutory form when it is not the first
   financial year.
   Output defaults to Italian. Set `output_language` to `en` only for a wholly
   English approved output; never mix languages inside one case output.
2. When available, attach the previous filed instance with
   `ingest-prior-xbrl`; the parser must match the entity and comparative period
   and records facts as source evidence without treating them as current-year
   accounting decisions. Ingest one generic CSV or XLSX trial balance with
   `ingest`. Review the
   source-anchor inventory and calibration samples.
3. Explicitly confirm the progressive convention with `confirm-parser`. Stop
   while it is `UNKNOWN`.
   If an open case must move to replacement regulatory packs, use only the
   explicit `migrate_regulatory_versions` operation as a studio administrator.
   Review its change report and rerun every invalidated computation plus full
   validation. Never migrate an approved, exported, or archived snapshot and
   never pass a different pack directly to an existing locked computation.
4. Run `determine-forms` with effective-dated threshold metrics. Show eligible
   and ineligible forms and reasons; do not select a form for the user.
5. Record the explicit form choice with `select-form`.
6. Prepare exact approved candidates with `mapping-candidates` when a
   tenant-owned mapping-memory file exists. Client matches take precedence over
   explicitly approved tenant-wide mappings. Then consider deterministic
   dictionaries, prior history, model suggestions, and manual mapping in that
   order. Apply only reviewed decisions with `apply-mappings`. Every split must
   balance current and comparative amounts exactly. Never reuse mappings across
   tenants.
7. Run `compute-statements`. Treat its output as exact aggregation over
   reviewed mappings, not evidence that accounting classifications are right.
8. Run `record-statutory-presentation` with the checksum-bound catalogue and
   bundled versioned presentation pack. Review every leaf required by the
   selected official primary-statement networks. Existing facts remain
   source-backed; every absent current or comparative leaf must receive an
   explicit professional `ZERO_CONFIRMED` or `NOT_APPLICABLE_CONFIRMED`
   decision and reason. Official calculation relationships derive or verify
   totals. Never infer zero from absence. Continue only when coverage is
   `COMPLETE` and all total mismatches are resolved.
9. Collect reviewer-triggered schedules and structured disclosure answers. Use
   `ingest-schedule` for the documented CSV/XLSX fixed-asset, receivable,
   payable, equity, provision, TFR, tax, and guarantee templates, or use
   `record-schedule` for normalized fixed-asset, receivable, payable, equity,
   provision, TFR, tax, guarantees/commitments, and cash-flow evidence. Ordinary
   cases require an indirect cash-flow schedule whose evidence-backed items
   reconcile opening to closing cash; never derive investing or financing
   classifications from a trial balance alone. Use `record-answers` for accepted
   answers and annual negative confirmations. Preserve `OPEN` when unknown.
10. For every non-cash schedule, run `record-schedule-taxonomy-adapter` with the
    deployment-controlled effective pack. Map cells only through a reviewed
    decision to concepts under the selected official note-table roots. Every
    schedule cell must be mapped or receive a specific professional omission
    reason; table policies require at least one mapped fact. Do not infer a
    concept from a free-form row label. Reused primary facts must reconcile.
11. Run `validate`. Resolve every blocker and unoverridden high issue.
12. Run `prepare-xbrl-review` with the checksum-bound catalogue and official
    taxonomy package. This renders the current unapproved case and records the
    local XBRL processor report; approval is blocked unless it passes and still
    matches the current substantive content.
13. Have a reviewer inspect statements, mappings, evidence, issues, preview,
    rendered XBRL, and local processor report. Run `approve` only after all
    reviewer declarations are true.
14. Run `export` only from the immutable approved snapshot and a checksum-bound
    catalogue generated from the official taxonomy package.
15. The user may upload the exported instance to TEBENI manually and return the
    official report for comparison. Do not substitute that external result for
    the mandatory pre-approval local processor report.
16. After approval, use `remember-mappings` only when the studio chose an
    explicit tenant-owned memory path and source-system template. The command
    verifies the immutable snapshot and stores classification fields, never old
    amounts or source anchors.

## Intelligent participation loop

At each material stage, use `intelligence-packet` or the corresponding Vera MCP
tool to provide only the context required for one semantic task. The packet may
support workflow guidance, account mapping, question prioritization, narrative
drafting, prior-year comparison, or issue explanation. Do not send the whole
case merely because it is available.

Run the semantic task in the selected Vera runtime, then pass the strict JSON
result through `record-intelligence`. The validator rejects references outside
the packet and stores the output as `MODEL_SUGGESTED`. A model mapping must be
converted through a separate reviewed `apply-mappings` decision. A model
narrative remains a draft until a reviewer records it through
`record-narratives`. Workflow guidance explains what should be considered next;
it does not change case state by itself.

Use intelligence continuously:

- after intake, explain the source interpretation and next missing input;
- during mapping, propose meaning, alternatives, ambiguity, and evidence needs;
- after statements, identify relevant schedules and questions without treating
  account absence as a negative fact;
- during notes, draft only from accepted facts and confirmations;
- during validation, explain issues and possible resolution evidence;
- before approval, direct attention to consequential professional decisions.

Never present these as a separate optional AI mode. They are the intelligent
participation layer inside the existing bilancio process.

Every mutating command requires the current `revision_id`. A stale revision
fails. Any post-approval mutation archives and invalidates the approval before
creating a new revision.

For workbook ingestion, mapping-candidate preparation, intelligence-result
recording, narrative recording, preview, validation, pre-approval XBRL review,
export, deployment-controlled taxonomy-catalogue construction, or host-side
minimum-context model invocation, the host may use `xbrl_case_enqueue_job`.
Treat `job_id` as the
idempotency key and show its compact status with `xbrl_case_job_get`. Jobs are
bound to the submitted revision and must become `STALE`, never apply, after an
intervening case edit. Do not expose the internal `SERVICE_WORKER` execution
role to the conversational user; the deployment invokes
`scripts/run_background_job.py` from its trusted worker boundary.
Never put package paths, registry choices, entry points, or a proposed model
output into a taxonomy/model-invocation queue request. Those values come from
the trusted worker configuration and runner response.

## Taxonomy catalogue

Do not create a hand-copied production concept list. Obtain the official
taxonomy package and its verified checksum, then run:

```bash
python scripts/build_taxonomy_catalogue.py \
  --package <official-taxonomy.zip> \
  --entry-point ORDINARY=2018-11-04/itcc-ci-ese-2018-11-04.xsd \
  --entry-point ABBREVIATED=2018-11-04/itcc-ci-abb-2018-11-04.xsd \
  --entry-point MICRO=2018-11-04/itcc-ci-micr-2018-11-04.xsd \
  --taxonomy-id PCI_2018-11-04 \
  --expected-sha256 <verified-sha256> \
  --official-source <official-source-url> \
  --output <case-run>/taxonomy/catalogue.json
```

The builder uses pinned Arelle, records the official package checksum, and
extracts concepts and relationship sets. The exporter rejects `UNVERIFIED` or
mismatched catalogue checksums.

## Review output

Always show:

- case state and exact revision;
- parser convention and unmatched rows;
- eligible forms and missing decision fields;
- mapping coverage, balancing splits, and exclusions;
- statement and schedule reconciliations;
- selected-form statutory presentation coverage, explicit absence decisions,
  and official calculation-total mismatches;
- open questions by domain and severity, never a vague completion percentage;
- validation layers and unresolved issues;
- approved snapshot, artifact checksums, and the manual filing boundary.

Use `xbrl_case_get_review_view` for the structured case dashboard, source,
mapping, statements, schedules, questionnaire, notes, issues, preview, and
approval/export surfaces. Page large grids with `offset` and `limit`; never
replace explicit blockers and open questions with a completion percentage.
Treat preview, workpaper, and artifact resource identifiers as references, not
authorization to return local paths or bytes.

## Codex-Native Run UX

Use a short checklist covering scope intake, source import, parser confirmation,
form choice, mapping, statements, disclosures, validation, approval, and export.

Show a compact Run Intake table with entity, period, source files, parser state,
taxonomy lock, case run, preparer, reviewer, and expected artifacts. Use a
Decision Table only for unresolved material choices such as the statutory form,
ambiguous account mappings, missing evidence, double-format treatment, or the
optional TEBENI route.
Ask only those unresolved choices in chat; do not turn routine workflow steps
into preference questions. Derive resolved fields from the actual inputs and
inspected case evidence. Do not surface dormant alternatives unless the facts cue them.

Default output policy: preserve source evidence and produce one revisioned case,
approved XBRL, preview, mapping report, issue report, validation report,
workpaper, and checksum manifest. These are not choices to propose when the
user requested the normal Bilancio XBRL run.

Before long or write-heavy work, show an execution checkpoint naming the case,
revision, source manifest, output location, and expected validation. End with an
Artifact Card listing the approved snapshot, XBRL, workpaper, validation state,
checksums, and residual professional-review items. Create `codex_run_review.md`
when blocked or when a repeatable workflow gap should survive the chat. Never
edit generated ZIPs during a run.

## Current implementation boundary

Do not claim that an intelligent behavior, statutory table, complete narrative,
golden case, review surface, or external compatibility exists unless the
implementation-status reference and current tests prove it. The existence of a
deterministic export does not prove that the intelligent bilancio workflow is
complete.

## Plugin Improvement Feedback

At the end of a completed or blocked run, identify concrete workflow gaps
without client or source details. Keep the improvement note local to chat or run artifacts. When this workflow runs
through Vera, follow Vera's consent-based feedback process before transmitting
anything.
