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

## Material reasoning-chain invariant

Build `material_review_items` before assigning the ten dimension summaries.
Select every material factual claim, hypothesis, assumption, calculation,
inference, recommendation, and decision condition through model-led review of
the complete deliverable. This is not a sentence inventory: omit immaterial
copy, but never omit a premise whose failure could change a conclusion,
recommendation, condition, or delivery decision.

For each material item, record its exact location and statement, upstream
material-item dependencies, evidence references, support status, reasoning
status, counterevidence, decision effect, resolution, and professional-review
need. Recommendations and material inferences must identify the material items
they depend on. Explicitly distinguish a hypothesis from a fact. A hypothesis
may remain when it is labelled, bounded, decision-useful, and its uncertainty
does not control the decision; an untested critical hypothesis cannot be
accepted as residual uncertainty.

Use the weakest material dependency, not an average score, to determine
readiness. An unsupported or contradicted material claim, an unsound material
inference, or an unresolved critical weakness keeps delivery not ready until it
is corrected, removed, supported, or otherwise resolved in a separate reviewed
artifact. A bounded noncritical uncertainty may support
`ready_with_residual_uncertainty` only when the review records the qualification
and the overall assessment states the residual uncertainty. Do not let polished
prose, many sound sections, or an empty issue list compensate for one decisive
weak premise.

## Format-specific composition

The validator coordinates existing Clara checks and consumes their artifacts;
it does not duplicate or weaken them:

| Artifact condition | Required composition |
| --- | --- |
| Material claims in a PPTX | Use `clara:claim-basis-map`. For an external deck without a generation record, label the result matched support rather than original provenance. |
| Clara fixed-stage HTML deck | Use `clara:html-deck` static validation and multi-viewport browser QA. Preserve its content/evidence ledgers and reports. |
| Claims based on CSV/XLSX/Parquet calculations | Use `clara:reporting-engine` with a reviewed semantic layer and its calculation/render evidence. |
| Correction of an existing PPTX or Clara HTML deck | Use `clara:deck-correction`; preserve the original and complete its approval, render, and verification gates. |

Record these needs under `validation_profile.format_checks` in the advisory
contract. Required check artifacts remain authoritative. If a required check is
blocked, delivery readiness is blocked; the validator must not reimplement a
weaker substitute. A check marked `passed` must reference the actual local
artifact files. Packaging resolves those paths relative to the advisory
contract, verifies that they exist, and records their hashes without rejudging
their contents.

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
  --source-file <selected-evidence>
```

3. Read the complete `extracted_deliverable.md`, not only the mechanical
   inventories. Read the selected source material and the required existing
   format-check artifacts. Citation markers, links, and numeric tokens are
   navigation aids only; they must not select or assess material claims.
4. Perform the model-led review across all ten dimensions. Preserve the
   contract's scope and explicitly record reviewed sections, omitted sections,
   limitations, missing evidence, and judgement-dependent points.
5. Write `advisory_validation_review_draft.json` with review schema version
   `"1.1"` against
   [references/advisory_validation_review.schema.json](references/advisory_validation_review.schema.json).
   Use `model_led_materiality_review` as the coverage selection method. Record
   the complete material reasoning chain before the dimension summaries, then
   record evidence references, analysis, correction state, professional-review
   needs, and explicit approval records separately. Approval is a user or
   professional fact: never infer it from polished output, an empty issue list,
   or a model recommendation. Do not turn the fields into a numeric score.
6. If correction is needed and permitted, create a separate corrected artifact.
   Preserve the original bytes. For decks, use `clara:deck-correction`; for
   calculation-backed content, rerun the authoritative Reporting Engine checks;
   for an HTML stage deck, rebuild and rerun HTML deck validation/browser QA.
   Re-review the corrected artifact before marking correction completed. Record
   its resolved path and SHA-256 in the correction record. When the contract
   requires correction or professional-judgement approval before delivery,
   record the explicit approver and a reference to the approval; pending
   approval is not delivery-ready.
7. Package and mechanically audit the review:

```bash
python scripts/managed_python_runtime.py run \
  skills/advisory-deliverable-validator/scripts/advisory_validation.py \
  package <work-folder>/validation/deliverable_inventory.json \
  <work-folder>/validation/advisory_validation_review_draft.json \
  --advisory-contract <work-folder>/advisory_contract.json \
  --output-dir <work-folder>/validation \
  [--corrected-deliverable <separate-corrected-file>]
```

8. Read `validation_audit.json`. Its `record_complete` status proves only
   declared shape, original and corrected-artifact hash binding, explicit
   approval-state consistency, cross-field consistency, existence and hashes of
   referenced format-check artifacts, and original preservation. Use
   `delivery_readiness.status` and the semantic review to state whether delivery
   is ready, ready with residual uncertainty, not ready, or blocked.

## ChatGPT, Codex and Cowork

In ChatGPT or Codex, use the packaged workflow and, when local execution is
available, the helpers, exact files, hashes, and format-specific checks. Cowork
follows the same semantic dimensions, material reasoning chain, and contract.
When the host can execute the packaged scripts, use the same mechanical
artifacts and limits. When it cannot, the model may review only the files
explicitly connected by the user; schema/hash/package closure and
original-preservation proof remain unavailable, so report the mechanical state
as partial rather than claiming an equivalent verified package.

The workflow does not automatically fetch links, search legal or other source
domains, call connectors, upload material, publish, or send the deliverable.
Those are separate user-selected actions and workflows.

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
- `advisory_validation_review.json`;
- `validation_audit.json`;
- `advisory_validation_package.md`;
- a separate corrected artifact only when correction was completed.

## Failure modes

- Missing contract: create it from explicit/user-confirmed context before
  preparation; do not let deterministic code invent it.
- Unsupported or unreadable primary input: report the exact limitation and ask
  for a supported export.
- Missing required format check: mark the review blocked or not ready; do not
  duplicate the missing check.
- Missing source or calculation evidence: assess what is available, identify
  the gap, and do not invent support.
- Review-record audit failure: repair the model-authored record and rerun
  packaging; do not ignore failed checks.
- Proposed correction without a separate artifact: keep delivery not ready.
- Required approval still pending: keep delivery not ready; do not infer
  approval.
- Output path aliases an input or corrected artifact: choose a different output
  folder or filename; never overwrite the protected file.
