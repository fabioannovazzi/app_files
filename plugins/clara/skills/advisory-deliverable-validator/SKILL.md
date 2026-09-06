---
name: advisory-deliverable-validator
description: Use when Clara must validate a completed advisory memo, report, analysis, presentation, or other supported professional document against advisory_contract.json and available evidence. Review contract fit, support, calculations and provenance, reasoning, contradictions, recommendation fit, judgement boundaries, correction needs, uncertainty, and delivery readiness without turning the workflow into legal, tax, compliance, or jurisdictional research.
---

# Validate an advisory deliverable

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../clara/SKILL.md`.

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or another published folder. Use a project output folder
beside the user's source material or another user-selected working directory.
Preserve the supplied deliverable. A correction always has a different path and
is a separate reviewed artifact.

## Generation-time binding prerequisite

Before handing a non-deck memo or report to validation, bind its final bytes
and each claim's location from the plugin root:

```bash
python scripts/advisory_evidence_lineage.py bind-output <case_dir> <deliverable_path> <locations_json>
```

`locations_json` is a JSON file, for example
`[{"claim_id":"cl-a","locator":"Recommendation, paragraph 2"}]`; include an
entry for every claim appearing in the deliverable, using existing claim IDs
and precise locations. A case-bound HTML build uses `build_html_deck.py
--case-dir <case_dir>` to bind automatically. Keep each bound artifact immutable;
write revisions to a new path and bind their new appearances before validation.
If validation reports "no hash-bound appearance", return to this binding step
for the exact prepared deliverable, then prepare the validation inventory again.

## Retain bound build artifacts

Content-addressed build directories under `<output_root>/<sha256>/` must remain
in place once their appearances are bound to the claim register. Never delete a
previous bound build after rebuilding; retain superseded builds alongside new
ones. Claim appearances are append-only and refer to the exact original bytes.
Before any proposed cleanup, run from the plugin root:

```bash
python scripts/advisory_evidence_lineage.py check-safe-to-delete <case_dir> <path>
```

A nonzero exit blocks cleanup when this case references the path or a file below
it, or its lineage cannot be checked. A zero exit means only that this case has
no bound appearance there; check every other case using that output root too.
The command is read-only and does not prevent manual filesystem deletion.


## Purpose and boundary

Use this workflow for a completed advisory deliverable: a memo, report,
analysis, presentation, or another supported professional document. Validate it
against `advisory_contract.json` and the evidence actually available. This is a
domain-neutral advisory review. It does not perform legal, tax, compliance, or
jurisdictional source selection and must not be represented as one.

Clara performs the semantic work through the user's selected model: selecting
material claims and decisions, assessing source support, reviewing reasoning and
assumptions, identifying contradictions and missing evidence, judging whether
recommendations fit the evidence and decision, identifying professional-
judgement boundaries, and drafting evidence-bounded corrections.

For Clara-created work, validation begins upstream rather than reconstructing a
claim list after the document is finished. When a source, interview, calculation,
or Clara analysis introduces a claim, record the evidence receipt and claim at
that step. When another claim depends on it, carry the claim ID, evidence IDs,
dependency mode (`all_of` or `any_of`), and the stated derivation forward. When
the claim appears in a memo, report, deck, or recommendation, record that exact
appearance. The final validator selects the decision-relevant claims through
model judgement and walks each selected claim back through every declared
dependency and evidence receipt.

For a durable generation-time case, read
[the case-direction return contract](../advisory-case-director/references/case-direction-return.md)
before returning the review. The validator is a bounded contributor to the
spine, not a second case controller.

For an external completed document with no generation-time registers, use
`matched_support`. Clara may identify material claims and match them to supplied
or newly inspected evidence, but must not describe that reconstruction as
original provenance.

Deterministic code is limited to mechanically verifiable work: supported-format
text extraction, file hashing, citation/link/numeric-token inventory, declared
JSON-shape validation, cross-field consistency, original-preservation checks,
approval-state consistency, referenced-artifact existence and hashing, and
packaging. These fixed checks are justified by mechanically verifiable
correctness and audit closure. They never decide which content is material,
whether evidence supports a claim, whether reasoning is sound, whether a
format-specific check passed semantically, or whether a recommendation is good.
The scripts make no model API calls. Do not replace them with a keyword classifier,
semantic scorecard, or hidden model route.

## Evidence and claim lineage

The canonical case records are:

- `advisory_evidence_register.json` (`schema_version: "1.0"`): append-only
  receipts for local documents, public web captures, interview transcripts,
  datasets, calculation runs, management assertions, advisor judgement, prior
  Clara outputs, and other explicitly identified evidence;
- `advisory_claim_register.json` (`schema_version: "1.0"`): model-authored
  claims with evidence relationships, what each receipt proves and does not
  prove, downstream dependencies, uncertainty, judgement boundaries, and
  deliverable appearances;
- `advisory_evidence_map.md`: deterministic readable rendering of those two
  registers, not a separate source of truth.

Use `scripts/advisory_evidence_lineage.py` to initialize, append, validate, and
render these records. The helper enforces schema, immutable IDs, literal
references, timestamps, file hashes, and an acyclic dependency graph. It does
not decide whether an observation is true, whether evidence supports a claim,
or whether a conclusion follows.

Evidence must travel with the claim:

- A public page capture records the requested/final URL, captured bytes,
  normalized text, hashes, capture scope, and explicit limitations. The model
  inspects that capture and authors the observation. For example, thirteen
  visible listings support only that captured observation; they do not support
  a claim that the company holds thirteen or three hundred vehicles in total.
- A management or interview statement may remain an `assertion_only` receipt.
  “Giovanni believes X” can be properly supported by the transcript even when X
  itself is not independently established. A separate truth claim about X needs
  its own basis.
- A calculation claim references a `calculation_run` receipt containing the
  Reporting Engine inputs, method, output, reconciliation or render manifest,
  and hashes. The final validator may require a targeted rerun, but does not
  replace the Reporting Engine.
- A derived claim records all required upstream claim IDs and the reasoning,
  aggregation, quotation, or calculation that connects them. If claim X needs
  both A and B, use `all_of`; the final review cannot assess X while omitting A
  or B.

Capture a public page only when the workflow actually uses it:

```bash
python scripts/capture_advisory_web_evidence.py <case-dir> <public-url> \
  --evidence-id ev-web-001 \
  --observation "The model-authored observation from the inspected capture" \
  --scope "The exact page and capture time" \
  --limitation "What this capture does not establish"
```

This direct local fetch is opt-in. It checks public-network destinations and
redirects, preserves the response and normalized text under
`source_materials/web/`, and verifies source identity. It does not infer the
observation or certify its completeness or truth.

## Advisory contract

Read [references/advisory-contract.md](references/advisory-contract.md) before
creating or consuming a contract. The canonical filename is exactly:

```text
advisory_contract.json
```

The schema version is exactly `"1.0"`. Its required stable semantic fields are
`decision`, `purpose`, `audience`, `deliverable_type`, `output_language`,
`scope_included`, `scope_excluded`, `available_inputs`,
`evidence_requirements`, `analysis_plan`, `assumptions`,
`unresolved_questions`, `success_criteria`, `selected_clara_workflow`,
`validation_profile`, `validation_scope`, `correction_policy`, and
`professional_judgement_policy`.

When an external document has no contract, Clara may create one from explicit
context already supplied by the user. If consequential scope, evidence,
correction, or judgement ownership is not explicit, show the proposed contract
and obtain confirmation for that point before validation. Do not silently
invent scope. Record unresolved but non-blocking questions explicitly.

## Supported inputs

Supported primary deliverables in the initial release:

- Markdown (`.md`, `.markdown`) and plain text (`.txt`);
- standalone HTML (`.html`, `.htm`);
- readable text-layer PDF (`.pdf`);
- Word (`.docx`);
- PowerPoint (`.pptx`).

CSV, XLSX, and Parquet files may be supporting analytical evidence. They are not
treated as a finished client-facing advisory deliverable by this validator.
When claims depend on them, compose with `clara:reporting-engine` for semantic
mapping, calculation, provenance, and reporting checks.

Image-only or unreadable PDFs require Clara's normal input-aware dependency
preflight and approved OCR setup. Encrypted files, Keynote, Pages, live Google
Docs, live BI dashboards, archives, audio, video, and image-only deliverables
are unsupported as primary inputs in this release. Ask for a supported export;
do not claim validation from an incomplete extraction.

Whether an HTML file is a stage deck or a scrolling document is a model-led
interpretation from the artifact and context, not a filename or keyword rule.

## Required review dimensions

Assess all ten dimensions separately:

1. contract conformance;
2. factual and source support;
3. calculations and data provenance where relevant;
4. reasoning and assumptions;
5. contradictions and missing evidence;
6. recommendation-to-evidence and decision fit;
7. professional-judgement boundaries;
8. correction needs;
9. residual uncertainty;
10. delivery readiness.

Do not collapse these into one score. `not_applicable` is allowed only with a
specific explanation. A structurally complete review record is not proof that
the deliverable is correct.

## Format-specific composition

The validator coordinates existing Clara checks and consumes their artifacts;
it does not duplicate or weaken them:

| Artifact condition | Required composition |
| --- | --- |
| Material claims in a PPTX | Use `clara:claim-basis-map`. For an external deck without a generation record, label the result matched support rather than original provenance. |
| Clara fixed-stage HTML deck | Use `clara:html-deck` static validation and multi-viewport browser QA. Preserve its content/evidence ledgers and reports. |
| Claims based on CSV/XLSX/Parquet calculations | Use `clara:reporting-engine` with a reviewed semantic layer and its calculation/render evidence. |
| Correction of an existing PPTX or Clara HTML deck | Use `clara:deck-correction`; preserve the original and complete its approval, render, and verification gates. |

During generation, reuse the same upstream claim ID in the Claim Basis Map
`claim_key`/`advisory_claim_id` and in the HTML content ledger claim `id` when
its safe-ID contract permits. Add the corresponding deliverable appearance to
the shared claim register. The format ledgers remain authoritative for their
own text drift, visual binding, calculation binding, rendering, and browser QA;
the shared registers remain authoritative for the cross-workflow evidence and
dependency chain. A shared receipt never substitutes for a missing
format-specific artifact.

Record these needs under `validation_profile.format_checks` in the advisory
contract. Required check artifacts remain authoritative. If a required check is
blocked, delivery readiness is blocked; the validator must not reimplement a
weaker substitute. A check marked `passed` must reference the workflow-owned
result artifact: Claim Basis Map audit, both HTML static and browser-QA reports,
Reporting Engine 0.2 render manifest, or Deck Correction completion record.
Packaging resolves the paths relative to the advisory contract, verifies their
bytes, verifies that HTML static and browser-QA results name the exact prepared
deliverable SHA-256, and consumes only the owning workflow's explicit pass/fail
fields. A generic file containing `{"status":"passed"}` is not an authoritative
result.

## Workflow

1. Inspect the supplied deliverable, selected evidence, and any existing Clara
   format-check artifacts. Infer only low-risk setup facts. Ask one focused
   question when a consequential contract field cannot be established from
   explicit context.
2. Run the dependency check from the Clara plugin root:

```bash
python scripts/check_dependencies.py
```

Run helpers through Clara's managed core runtime:

```bash
python scripts/managed_python_runtime.py run \
  skills/advisory-deliverable-validator/scripts/advisory_validation.py \
  prepare <deliverable> \
  --advisory-contract <work-folder>/advisory_contract.json \
  --output-dir <work-folder>/validation \
  --source-file <selected-evidence> \
  --evidence-register <case-dir>/advisory_evidence_register.json \
  --claim-register <case-dir>/advisory_claim_register.json
```

Supply both lineage registers or neither. Omit them only for an external
document or a legacy run that genuinely has no generation-time lineage. The
preparation then records `matched_support` and does not create fake empty
provenance.

3. Read the complete `extracted_deliverable.md`, the bounded
   `coverage_inventory.json`, the lineage registers when supplied, the selected
   source material, and the required existing format-check artifacts. Citation
   markers, links, numeric tokens, and coverage-unit boundaries are navigation
   aids only; they must not select or assess material claims.
4. Use model judgement to select the claims that affect the deliverable's
   decision, recommendation, material conclusion, or material limitation. In
   generation-time mode, walk each selected claim through every declared
   dependency. Compare its final wording with what its receipts prove and do
   not prove. Record any material final claim missing from the upstream
   register as `untracked_material_claims`; do not silently retrofit it into
   original provenance. In matched-support mode, review material claims against
   the evidence now available and preserve the reconstruction limitation.
5. Perform the model-led review across all ten dimensions. Preserve the
   contract's scope and explicitly record reviewed sections, omitted sections,
   every considered or deliberately omitted coverage unit, missing evidence,
   and judgement-dependent points. Write one `unit_assessments` entry for every
   coverage unit. Each entry must say whether it contains selected tracked
   claims, selected reconstructed claims, no material claim after model review,
   or was omitted. The union of those claim IDs must exactly match the lineage
   review. The coverage inventory makes a long report auditable in bounded
   units; it does not reduce a two-hundred-page review to a single prompt or a
   deterministic claim extractor. A delivery-ready review must contain at least
   one model-reviewed material claim.
6. For each reviewed claim chain, decide whether a final targeted recheck is
   required. Recheck public evidence when the original capture is missing,
   inaccessible, stale for the decision, contradicted, or insufficiently
   scoped. Rerun a calculation through its authoritative calculation workflow
   when inputs, method, version, or reconciliation are missing or changed. A
   completed recheck creates a new evidence receipt linked to the earlier one.
   Rerun preparation after adding the receipt so the final review binds the
   updated registers and hashes.
   The deterministic packager only records these model-selected tasks in
   `recheck_tasks.json`; it never chooses or performs them secretly.
7. Write `advisory_validation_review_draft.json` against
   [references/advisory_validation_review.schema.json](references/advisory_validation_review.schema.json).
   Use schema version `"1.3"`, `model_led_materiality_review` for document
   coverage, and `model_led_claim_chain_review` for lineage selection. Bind the
   review to the contract, deliverable, coverage inventory, and lineage
   inventory hashes. Record evidence references, analysis, rechecks, correction
   state, professional-review needs, and explicit approval records separately.
   Approval is a user or professional fact: never infer it from polished output,
   an empty issue list, or a model recommendation. Do not turn the fields into a
   numeric score.
8. If correction is needed and permitted, create a separate corrected artifact.
   Preserve the original bytes. For decks, use `clara:deck-correction`; for
   calculation-backed content, rerun the authoritative Reporting Engine checks;
   for an HTML stage deck, rebuild and rerun HTML deck validation/browser QA.
   In a generation-time case, do not make a semantic correction directly from
   the validator: package the review, return the material findings to the case
   director through the common case-direction contract, update the spine, and
   then rebuild. Pure format or wording corrections that do not change claim
   meaning may remain inside the format-specific correction workflow.
   An unchanged claim keeps its claim ID and gains a new appearance. A changed
   claim gets a new claim record whose `supersedes_claim_id` points to the prior
   claim; withdrawn wording remains in the history rather than being erased.
   Re-run `prepare` on the corrected artifact and complete a second model-led
   review whose correction status is `not_required` and whose delivery status
   is ready or ready with explicit residual uncertainty. Record the corrected
   artifact, corrected inventory, and corrected review SHA-256 values in the
   original correction record. When the contract
   requires correction or professional-judgement approval before delivery,
   record the explicit approver and a reference to the approval; pending
   approval is not delivery-ready.
9. Package and mechanically audit the review:

```bash
python scripts/managed_python_runtime.py run \
  skills/advisory-deliverable-validator/scripts/advisory_validation.py \
  package <work-folder>/validation/deliverable_inventory.json \
  <work-folder>/validation/advisory_validation_review_draft.json \
  --advisory-contract <work-folder>/advisory_contract.json \
  --output-dir <work-folder>/validation \
  [--corrected-deliverable <separate-corrected-file> \
   --corrected-deliverable-inventory <corrected-validation>/deliverable_inventory.json \
   --corrected-review <corrected-validation>/advisory_validation_review_draft.json]
```

10. Read `validation_audit.json` and `recheck_tasks.json`. Its `record_complete`
   status proves only declared shape, original and corrected-artifact hash
   binding, explicit approval-state consistency, cross-field consistency,
   existence and hashes of referenced format-check artifacts, and original
   preservation. Use `delivery_readiness.status` and the semantic review to
   state whether delivery is ready, ready with residual uncertainty, not ready,
   or blocked.
11. For every generation-time case, return the packaged semantic review to the
   case director, whether it confirms the current claims or requires a change.
   Author a `validation_feedback` envelope against the common case-direction
   return schema. Bind the exact `advisory_validation_review.json` and
   `validation_audit.json`, select the material finding IDs through model
   judgement, and return the active claim IDs that now carry the answer. Then
   run:

```bash
python scripts/record_case_direction_return.py \
  <case-dir> <model-authored-validation-feedback-return.json>
```

   The helper checks exact bytes, reviewed IDs, current pre-feedback register
   hashes, declared graph closure, and replay safety. It does not infer the
   findings' meaning. If feedback changes a claim or opens a recheck, return to
   `clara:advisory-case-director`, update and checkpoint the workpaper, rebuild
   the deliverable, and rerun this validator. Do not describe the earlier audit
   as current after the spine changes.
12. For a generation-time Clara case HTML deck, run the final mechanical case
   gate after packaging:

```bash
python scripts/managed_python_runtime.py run \
  scripts/verify_advisory_html_delivery.py \
  <case-dir> <final-index.html> <work-folder>/validation/validation_audit.json \
  --output <work-folder>/advisory_html_delivery_receipt.json
```

   A `ready` receipt is required before the exact HTML is described as ready to
   deliver or publish. It binds the current workpaper checkpoint, registers,
   hash-bound direct claim appearances, HTML checks, and this model-led review;
   it does not add a second semantic assessment.

## Codex and Cowork

In Codex, use the packaged helpers and exact local files, hashes, and
format-specific checks. Cowork follows the same semantic dimensions and
contract. When Cowork can execute the packaged scripts, use the same
mechanical artifacts and limits. When it cannot, the model may review only the
files explicitly connected by the user; schema/hash/package closure and
original-preservation proof remain unavailable, so report the mechanical state
as partial rather than claiming an equivalent verified package.

The workflow does not automatically fetch links, search legal or other source
domains, call connectors, upload material, publish, or send the deliverable.
The explicit public-page capture helper is used only when Clara is already
collecting or model-selects a targeted recheck of that exact public source.
Those external actions remain visible, bounded workflow steps.

## Codex-Native Run UX

Use a short checklist for contract, extraction, format checks, semantic review,
correction, packaging, and delivery. Before helper scripts, show a compact Run
Intake table with the primary deliverable, contract path, selected evidence,
language, output folder, declared format checks, and unsupported inputs.

Default output policy: write user artifacts outside this repository. Catalog
changes, generated ZIPs, and package checks are allowed inside the repo only
when the task is explicitly plugin packaging or release.

Write a Decision Table for consequential review decisions: the contract fact,
available evidence, format-specific check, finding, professional owner, and
delivery effect. These are evidence-backed decisions, not choices to propose as
a substitute for the required review.

Use chat for a small number of consequential choices. Do not build a new HTML
review UI in this initial workflow. If findings are numerous, create a readable
Markdown review package and discuss material decisions in chat. Treat `partial`
and `blocked` as first-class states.

Before write-heavy work, show one execution checkpoint naming the input,
contract, output folder, expected inventories, format checks, and whether a
separate correction is expected. Approval is required only for an external,
destructive, approval-sensitive, or materially unresolved step.

End with an Artifact Card listing the original, contract, inventories, required
format-check artifacts, review, audit, package, corrected artifact if any,
delivery readiness, professional-review items, and residual uncertainty.
When a run creates persistent artifacts, also write `codex_run_review.md` with
links to those artifacts and the unresolved or professionally owned decisions.

## Expected outputs

- `advisory_contract.json`;
- `deliverable_inventory.json`;
- `extracted_deliverable.md`;
- `citation_inventory.json`;
- `calculation_inventory.json`;
- `source_inventory.json`;
- `coverage_inventory.json`;
- `lineage_inventory.json`;
- copied `advisory_evidence_register.json` and
  `advisory_claim_register.json` when generation-time lineage exists;
- `advisory_validation_review.json`;
- `validation_audit.json`;
- `recheck_tasks.json`;
- `advisory_validation_package.md`;
- a separate corrected artifact, corrected preparation inventory, and corrected
  model review only when correction was completed.

## Failure modes

- Missing contract: create it from explicit/user-confirmed context before
  preparation; do not let deterministic code invent it.
- Unsupported or unreadable primary input: report the exact limitation and ask
  for a supported export.
- Missing required format check: mark the review blocked or not ready; do not
  duplicate the missing check.
- Missing source or calculation evidence: assess what is available, identify
  the gap, and do not invent support.
- Missing generation-time lineage: use `matched_support`; never label a
  reconstructed source match as original provenance.
- Omitted dependency claim: complete the declared chain review before claiming
  readiness.
- Pending or blocked targeted recheck for a material claim: keep delivery
  blocked until the recheck is completed or the claim is removed, corrected, or
  explicitly qualified within the contract and professional boundary.
- Review-record audit failure: repair the model-authored record and rerun
  packaging; do not ignore failed checks.
- Proposed correction without a separate artifact: keep delivery not ready.
- Required approval still pending: keep delivery not ready; do not infer
  approval.
- Output path aliases an input or corrected artifact: choose a different output
  folder or filename; never overwrite the protected file.
