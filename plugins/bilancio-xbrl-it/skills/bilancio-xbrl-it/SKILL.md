---
name: bilancio-xbrl-it
description: Use when an Italian professional accounting studio asks Vera or Codex to understand accounting evidence and intelligently prepare, update, reconcile, review, validate, or export an individual OIC civil-law annual financial statement from CSV/XLSX or readable/scanned PDF evidence, a prior XBRL, or structured schedules. XBRL is a final deterministic output format, not the workflow identity. The workflow never invents missing facts, signs, approves corporate accounts, or files them.
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

Codex and Cowork must use the same `intelligence_contract.py` packet builders
and bounds. Never replace an unavailable packet helper with a raw read of
`case.json`, a source workbook/PDF, or the full connected folder. Use the
callable packet service/CLI, or stop and explain that the bounded-context
capability is unavailable in that runtime.

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
- trial balance with opening, debit/credit movements, and closing; require a
  comparative only when this is not the first financial year;
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
python scripts/check_dependencies.py [--input <trial-balance.pdf>]
```

Do not install missing core packages at runtime. `requirements.txt` is the
declared core contract. For an image-only PDF, the input-aware check may report
`OCR_SETUP_REQUIRED`. Ask only: “PaddleOCR is required to read this document.
Shall Codex install it now? The download is about 500 MB.” If the user agrees,
run `python scripts/managed_ocr_runtime.py install`; it installs the separate
`requirements-ocr.txt` contract into the persistent shared OCR runtime. Then
retry the same PDF automatically. Do not attempt OCR installation without that
approval.

The optional HTTP deployment additionally uses `api-requirements.txt`. Check it
only when operating `scripts/http_api.py`; do not make FastAPI a completion gate
for the normal Vera/MCP workflow.

Explicit approval is reserved for external, destructive, approval-sensitive,
or material steps. Ordinary local inspection, deterministic calculation, and
validation do not require a separate approval ceremony. Manual TEBENI upload
and final professional approval always require the user's explicit choice.

1. Create the scope-checked case with `scripts/xbrl_case.py create`. Resolve the
   OIC and filing identifiers only from the controlled registry, select the
   effective statutory pack, and lock every regulatory identifier and checksum
   together with the filing campaign and taxonomy checksum.
   Require legal name, reporting identifier, registered office, explicit
   first-year status, and the prior statutory form plus exact comparative start
   and end dates when it is not the first financial year.
   Output defaults to Italian. Set `output_language` to `en` only for a wholly
   English approved output; never mix languages inside one case output.
2. When available, attach the previous filed instance with
   `ingest-prior-xbrl`; the parser must match the entity and comparative period
   and records facts as source evidence without treating them as current-year
   accounting decisions. Ingest one generic CSV or XLSX trial balance with
   `ingest`. For a readable or scanned PDF trial balance, use `ingest-pdf` (or
   `PDF_TRIAL_BALANCE` through the service). This creates only a
   `PENDING_REVIEW` extraction candidate: embedded PDF geometry or OCR output
   is never a canonical accounting fact. Inspect the paginated source review,
   inspect every page method and table-coverage disposition, confirm or replace
   the proposed column mapping, record every cell correction, and dispose every
   page without a detected table as reviewed non-accounting content. An
   excluded non-account row must have only zero/blank monetary fields; a
   non-zero summary row must name accepted account rows and reconcile every
   selected monetary field within tolerance. Submit all four review
   declarations through `review-pdf-extraction`. Only an accepted review may
   install the trial balance. OCR confidence and model
   explanation may direct attention, but may never accept, correct, exclude,
   or promote a row. Then review the canonical source-anchor inventory,
   including page, table, row, column, bounding box, extraction method,
   original value, confirmed correction, and confidence. For every source,
   review the original headers,
   normalized fields, exact coordinates and raw/normalized values, plus the
   calibration samples. Header aliases that collide, non-finite/exponent
   monetary values, ambiguous double signs and operationally unbounded amounts
   must fail before accounting data is accepted.
3. Explicitly confirm the progressive convention with `confirm-parser`. Stop
   while it is `UNKNOWN`. Review the separate closing-entry assessment:
   supported numeric columns do not prove that closing entries are included,
   so only the professional's explicit convention confirmation may set that
   status.
   If an open case must move to replacement regulatory packs, use only the
   explicit `migrate_regulatory_versions` operation as a studio administrator.
   Review its change report and rerun every invalidated computation plus full
   validation. Never migrate an approved, exported, or archived snapshot and
   pass only controlled pack identifiers—never caller-supplied pack objects.
4. Run `determine-forms` with effective-dated threshold metrics. Show eligible
   and ineligible forms, entry/continuation basis, and the consequences of each
   form change; do not select a form for the user.
5. Record the explicit form choice with `select-form`.
6. Prepare exact approved candidates with `mapping-candidates` when a
   tenant-owned mapping-memory file exists. Client matches take precedence over
   explicitly approved tenant-wide mappings. Then consider deterministic
   dictionaries, prior history, model suggestions, and manual mapping in that
   order. Apply only reviewed decisions with `apply-mappings`. Every split must
   balance current and, when applicable, comparative amounts exactly. A
   first-financial-year mapping must not contain a comparative value. Never
   reuse mappings across tenants.
7. Run `compute-statements`. Treat its output as exact aggregation over
   reviewed mappings, not evidence that accounting classifications are right.
8. Run `record-statutory-presentation` with the checksum-bound catalogue and
   bundled versioned presentation pack. Review every leaf required by the
   selected official primary-statement networks. Existing facts remain
   source-backed; every absent leaf for each applicable annuality must receive
   an explicit professional `ZERO_CONFIRMED` or
   `NOT_APPLICABLE_CONFIRMED` decision and reason. Do not create prior-period
   decisions for a first financial year. Official calculation relationships
   derive or verify totals. Never infer zero from absence. Continue only when
   coverage is `COMPLETE` and all total mismatches are resolved.
9. Collect reviewer-triggered schedules and structured disclosure answers. Use
   `ingest-schedule` for the documented CSV/XLSX fixed-asset, inventory,
   receivable, payable, equity, provision, TFR, tax, and guarantee templates,
   or use `record-schedule` for normalized fixed-asset, inventory, receivable,
   payable, equity, provision, TFR, tax, guarantees/commitments, and cash-flow
   evidence. Inventory classification, costing method, net-realisable-value,
   obsolescence, count, and pledged-stock conclusions must remain explicit
   professional evidence; Vera validates terminal review states and the reviewed
   movement and statement arithmetic, but never infers the conclusions. Bind the
   inventory schedule only to a statement line backed exclusively by reviewed
   mappings to the selected form's inventory concepts; do not relabel an
   unrelated line or add a trigger to satisfy the gate. Ordinary
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
    matches the current substantive content. The processor may not modify the
    rendered candidate.
13. Have a reviewer inspect statements, mappings, evidence, issues, preview,
    rendered XBRL, and local processor report. Run `approve` only after all
    reviewer declarations are true.
14. Run `export` only from the immutable approved snapshot and the exact
    checksum-bound catalogue reviewed before approval. Export must reproduce
    the approved XBRL candidate and reviewed preview byte-for-byte; any
    catalogue, candidate, preview or snapshot mismatch stops the export.
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
case or an out-of-band case routing identifier merely because it is available;
include either only when the semantic task actually needs it.

Enforce the packet contract rather than manually assembling model input:

- account mapping accepts one to fifty exact account IDs;
- disclosure activation includes at most the first twenty accounts by stable
  case order, a value-free account/fact/schedule catalogue, and up to fifty
  exact `account:`, `fact:`, or `schedule:` selectors when more evidence is
  professionally relevant;
- question prioritization includes no more than fifty active questions and
  only their matching prior-answer suggestions;
- narrative drafting includes one section, the accepted answers and complete
  schedules linked to that section by the versioned disclosure rule pack, and
  only explicitly selected additional `fact:`, `answer:`, `schedule:`, or
  `prior:` context (up to fifty selectors);
- prior-year comparison includes at most twenty prior and twenty current items
  by default, with exact `prior:` and `block:` selectors for targeted batches;
- workflow guidance includes at most twenty detailed rows from each issue,
  question, schedule, presentation, or PDF collection and reports the complete
  counts; use exact issue/question packets or paginated review views for more;
- issue explanation accepts one to twenty exact issue IDs.

Every packet contains `context_receipt` with the exact content hash, task,
selectors, bounds, and disclosed/available counts. `record-intelligence`
persists that receipt with the model run. Catalogue entries are discovery aids,
not citeable evidence; request the exact expansion before relying on one.

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

For workbook or PDF ingestion, mapping-candidate preparation, intelligence-result
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
extracts schema-2 item/tuple/dimension metadata, labels, references, and
relationship sets. Only non-abstract reportable items may become facts; tuple
containers remain structural paths for repeated rows. The exporter rejects
`UNVERIFIED` or mismatched catalogue checksums.

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
`xbrl_mapping_get_review_packet` and `xbrl_questionnaire_get` likewise return
at most 500 records with explicit pagination. `xbrl_case_get_workpaper` returns
only approval/snapshot hashes plus resource and exported-artifact metadata; it
must never place the immutable snapshot body in model context. Use the targeted
review views for analysis and a separately authorized artifact grant for the
complete exported workpaper.

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

## Mandatory implementation-review invariants

When reviewing or changing this implementation in the source repository, run
the dependency check and then:

```bash
python scripts/check_review_invariants.py
```

Do not declare the review complete unless every probe passes. The gate must
prove that non-zero accounts cannot be excluded, mapping requests preserve
unsubmitted decisions, selected OIC packs change the professional checklist,
failed review/export jobs leave no partial destination and can be retried,
symbolic links in destination ancestors fail closed, mixed PDF pages cannot be
partially accepted, headerless continuation tables remain visible, empty pages
require dispositions, candidate hashes bind page/table coverage, non-zero PDF
summary exclusions reconcile to named account rows, OCR package/model receipts
detect drift or tampering, workflow guidance cannot skip form prerequisites or
recommend a different action, and the Vera privacy fingerprint matches the
governed source. A general green test suite does not replace these named
adversarial probes.

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
