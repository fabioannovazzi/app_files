# Previdenza INPS workflow reference

## Contents

1. Scope and professional boundary
2. Intake decisions
3. Evidence contracts
4. Model-led research and source review
5. Approved arithmetic
6. Statuses and acceptance gates
7. Privacy and external access

## 1. Scope and professional boundary

Prepare a documented case file for professional review. Vera may register an official portal export. A read-only capture of one already-authenticated INPS browser tab is conditional on separate verification of permission under the particular service terms or another applicable basis; user or studio approval alone is insufficient. This is not an INPS API, autonomous login, or authority to operate the portal. Do not submit filings, activate delegations, sign an opinion, or automatically assign a subject to a contribution regime. Preserve contrary evidence and residual uncertainty.

Python owns only mechanically verifiable work: file hashes, extraction, stable locators, exact quote presence, identifier references, ISO date shape, explicit timeline sorting, Decimal arithmetic from approved recipes, schema checks, and packaging. Codex drafts source-backed interpretations, research paths, alternatives, and provisional conclusions. The professional reviewer owns the legal or contribution classification and final conclusion.

Never encode contribution rates, thresholds, ceilings, limitation periods, regime mappings, legal topic keywords, or source domains in deterministic code. A file named `gestione_commercianti.pdf` is still only a file until Codex and the reviewer assess its contents.

## 2. Intake decisions

Real case material may enter the Codex model context when it is useful for the professional analysis. The workflow does not ask for a per-case model-processing or data-minimisation declaration because it cannot verify those assertions. Account, workspace, retention, and training controls are chosen by the firm or user outside the case workflow.

Resolve these questions before the remaining semantic work:

1. What exact professional question will the output support?
2. Which document contains any label such as “3°/4° gruppo,” and what does that document say the label means?
3. Which subjects, relationships, and periods are in scope?
4. What is the legal/research cut-off date?
5. Are there deadlines, disputes, notices, or already-started proceedings?

Record the four material gates in `case_records_draft.json`:

```json
{
  "material_decisions": {
    "professional_question_confirmed": true,
    "framework_confirmed": true,
    "period_scope_confirmed": true,
    "ambiguous_terms_resolved": true
  }
}
```

These booleans record reviewer decisions. The validator must never infer them. Also record one `decision_log` entry for every gate, with the gate name, decision, stable actor reference, approving role, recording timestamp, and specific documentary or user-instruction basis. The model is not an approving authority.

An apparent urgent deadline must be surfaced as soon as it is observed. It is not deferred until every other intake question is resolved. Limited exploratory research may identify candidate meanings or missing authorities while a gate is open, but it remains non-conclusive and cannot assign a regime, approve a claim, or provide an arithmetic basis.

## 3. Evidence contracts

### Portal-derived evidence

The normal high-fidelity path is an official PDF or other document downloaded by the subject or an appropriately profiled intermediary/delegate using their own SPID, CIE, or CNS. The repository has no general-purpose INPS API credential flow. Public INPS APIs and PDND e-services must not be treated as interchangeable with access to an individual contribution position: use an API only after the exact e-service, eligible legal actor, agreement, authorization, and technical contract have been verified.

For an export already supplied as a local file, `register_portal_export.py` records the declared official origin, copies the evidence into an owner-only directory, and binds its name, size, type, and content by hash. It performs no portal, browser, authentication, or network action, so it does not ask for per-file access, profile, delegation, or model-processing declarations. The exact-host check validates the declared origin's shape; it cannot prove the file's download history.

When browser assistance is technically available, `capture_portal_snapshot.py` remains blocked until the professional records a specific terms, contract, or mandate basis permitting software-assisted capture for that service. Only then may it attach through a loopback-only CDP endpoint to exactly one tab that the authorized human has already opened and authenticated. The human owns login, profile selection, delegation, and any entry of personal identifiers. The capture code may read only rendered body text and a page image. It must not navigate, click, fill, submit, download, inspect cookies or storage, save HTML, export browser state, or close the user's browser. Require a stable approving-actor reference, timezone-aware approval time, exact approved INPS origin, bounded scope and purpose, verified access/profile/delegation authority, own-credential use, read-only scope, and absence of visible credentials or one-time codes. Do not add a separate per-capture declaration that ordinary client-data processing is authorized; the capture script cannot establish that legal conclusion.

The capture manifest stores the exact origin, a SHA-256 of the full page URL instead of its raw query or fragment, hashes and sizes for every private local artifact, and negative attestations for navigation, cookies, browser-state export, upload, and submission. Re-verify the manifest before inventory. Browser-visible text is `partial_evidence` until an authorized human compares the cited quote with the captured page image. A current-tab image is supplementary evidence and does not establish that every page, period, or account section was reviewed. Prefer official downloadable documents whenever they are available. The professional remains responsible for confirming that browser assistance is permitted for the particular portal service and mandate.

Treat connector artifacts as atomic receipts, not ordinary documents. An undeclared, nested, altered, or incomplete capture/export receipt causes inventory to stop before writing outputs. Validation binds the exact `file_inventory.json` bytes and a canonical projection of the acquisition posture, approvals, OCR network state, and portal-receipt hashes to the validated case records. Packaging requires that same `run_intake.json` and binding; it cannot recreate a missing intake as “local only.” The final artifacts also bind the exact private professional `review_payload.json` hash.

`inventory_case.py` creates document IDs and evidence fragments. It uses sufficiently populated embedded PDF text first, then Vera's shared local PaddleOCR adapter for pages whose embedded text is absent or mechanically too sparse and for supported images. The sufficiency gate measures only character coverage and never document meaning. OCR is local; model-weight downloads are disabled by default and require a separate explicit approval ID. A missing runtime or local model cache is recorded as an extraction limitation rather than triggering a hidden download. Facts authored by Codex must cite a document locator and a verbatim excerpt:

```json
{
  "fact_id": "F-001",
  "statement": "Il rapporto indicato nel documento decorre dal 2021-01-01.",
  "value": "2021-01-01",
  "value_type": "date",
  "subject_ids": ["SUB-001"],
  "evidence": [
    {
      "document_id": "DOC-001",
      "locator": {"kind": "page", "value": 3},
      "quote": "decorrenza dal 1 gennaio 2021"
    }
  ],
  "review_status": "confirmed",
  "conflict_group": null
}
```

Use `pending` or `disputed` when review is incomplete. Do not collapse conflicting facts. Timeline events must cite facts; the script only validates and sorts explicitly authored events.

Distinguish separate events and facts for an F24 being prepared, a debit occurring, INPS allocating the payment, and an INPS extract crediting a period. For absence claims, record which complete record set and period were checked; silence in one fragment is not affirmative proof. Preserve original email hashes and, when material, the original headers, thread relationship, and attachment inventory. OCR-derived material labels, dates, codes, and amounts require visual human confirmation before they can be `confirmed`. The same rule applies when OCR fails and the retained fragment is marked `embedded_text_below_ocr_quality_threshold`.

OCR never changes the locator: page 3 remains `DOC-…#page-3`, and every frame of a multi-page TIFF receives its own `page-N` locator. Successful OCR fragments carry `extraction_method: paddle_ocr` and `ocr_text_requires_visual_confirmation`. A `confirmed` fact citing one, or a weak retained text layer, must add a `visual_confirmation` object to that evidence anchor with `confirmed: true`, a stable human actor ID, an `authorized_user` or `professional_reviewer` role, a timezone-aware timestamp, and the basis for the page-image comparison. Pending or disputed facts may retain these anchors without that confirmation, but they cannot feed calculations.

## 4. Model-led research and source review

After facts are validated, determine the research framework in Codex. Prefer primary legislation, official administrative guidance, court or institutional sources, and reliable professional doctrine where interpretation is needed. Choose concrete sources from the confirmed issue and period; do not use a deterministic domain list.

For every material claim record:

- the precise claim;
- a claim type: `rule`, `case_application`, or `calculation_basis`;
- a `confirmed`, `open_ended`, or `unresolved` temporal scope and the research cut-off date;
- validated fact IDs for every case-application or calculation-basis claim; a pure rule claim may omit them but cannot classify the subject;
- each cited source as a separate record with reference, temporal role, retrieval timestamp, version basis, support note, and optional immutable snapshot hash;
- a support verdict: `supported`, `partially_supported`, `not_supported`, `contradicted`, or `uncertain`;
- a separate reasoning review;
- residual uncertainty or proposed correction.

Separate the rule applicable during the contribution period, the law known at the research cut-off, and later interpretive authorities. Never manufacture a temporal boundary to satisfy the schema; record it as `unresolved` or `open_ended`. Such a claim cannot be `supported` until the reviewer confirms exact applicability.

Use Vera’s `prompt-optimizer` component to prepare broad or disputed research. Use `deep-research-validator` on the completed research output before packaging. If either component is unavailable, perform the same model-led steps with current official sources, record the limitation, and label the result a model self-check rather than independent validation.

## 5. Approved arithmetic

An arithmetic recipe is executable only when:

- its formula basis claim is fully supported;
- a professional reviewer explicitly confirms the recipe and records actor ID, role, timestamp, and approval basis;
- every operand cites a confirmed fact or supported claim;
- the operation and rounding rule are explicit.

Allowed operations are add, subtract, multiply, and divide with `Decimal`. The script never supplies a missing rate, threshold, period, ceiling, formula, or rounding rule.

`calculation_audit.json` must bind the results to the exact approved recipe, validated case-record file, and claims file by path and SHA-256. The packager rejects results without that audit or when any bound input or result changed.

## 6. Statuses and acceptance gates

- `blocked_input`: no readable material evidence.
- `blocked_decision`: a material scope or framework choice remains unresolved.
- `partial_evidence`: scans, protected files, missing pages, or incomplete sources.
- `schema_error`: a record or reference is malformed.
- `calculation_not_run`: an approved arithmetic gate is missing.
- `validation_fail`: material claims fail package validation.
- `ready_for_professional_review`: the draft package is structurally complete.

Never emit a stronger final status. The professional must record substantive approval separately.

When blocked, still deliver the intake, inventory, extraction report, extracted evidence, document requests, and a visible handoff naming the blocker and next required professional decision. Do not create a conclusive memo or calculation for a blocked case.

Acceptance gates:

- each material fact has a valid locator and quote;
- each arithmetic input is reviewed and traceable;
- each material legal claim has a temporal scope and source verdict;
- unsupported or contradictory claims remain visible;
- final memo says `BOZZA PER REVISIONE PROFESSIONALE`.

## 7. Privacy and external access

Keep evidence in a dedicated access-restricted output directory. Local OCR and loopback browser capture do not upload page images to a provider. If an approved run downloads missing OCR model weights, record the approving ID and actual network use separately; only public model files are retrieved. Local scripts making no content network calls do not imply that later model processing is local. The private MCP review may include real case facts, labels, values, quotes, reasoning, calculations, and document requests. Keep raw portal or session URLs, credentials, cookies, tokens, and raw local paths out of it. Persisted review actions must match the exact stored review payload. A persisted ready review also requires a regular, identity-matching final manifest that is itself ready and binds that review. Before every persisted render, save, or apply action, the MCP server rechecks the package's acquisition binding against the current acquisition posture, exact file-inventory bytes, and canonical portal receipts; a mismatch stops before any review artifact is written. Package-owned execution-trace additions are deliberately outside that immutable projection. Minimize duplicate evidence copies and exclude personal identifiers from external research queries. Retention, encryption, secure sharing, and deletion remain the studio's responsibility unless a separately approved storage policy controls them.

The built-in bridge is intentionally limited to read-only capture of a user-controlled tab; it is not a login connector and never receives SPID/CIE/CNS material. Record its approval, scope, retrieval time, external execution location, and immutable local artifact hashes. Never invent an API, connector tool name, eligibility, authentication flow, or delegation state.
