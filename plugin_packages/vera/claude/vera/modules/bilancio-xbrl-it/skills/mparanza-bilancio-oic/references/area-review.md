> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Living area review

Use the same canonical Bilancio case, period locks, service authentication and
revision/idempotency preconditions. This extends the reviewed closing path; it
does not replace statutory presentation, schedules, notes or final approval.
No source or model conclusion is accepted automatically.

## Sources and interpretation

Attach a contract, resolution or policy with `attach_supporting_document`.
When replacing a registered source, provide `replaces_document_id` naming its
current immutable document record. The service retains both originals and an
append-only replacement event. Reimport is required: the panel does not watch
unregistered filesystem changes. New unclassified documents remain visible in
the existing closing review, rather than being assigned by keywords.

Read `REVIEW_SOURCES` through `xbrl_case_get_review_view` in small pages. Rows
contain exact document ID, source SHA-256, starting character offset and up to
4,000 characters of untrusted text. Pages exceeding 64 KiB are refused; reduce
`limit`. UTF-8 extracts have a 64 KiB source bound. Text PDFs require every page
to yield text, at most 200 pages and 64 KiB overall. Encrypted, image-only,
partially extractable or oversized PDFs require qualified extraction; this is
not OCR or original-PDF visual acceptance. Do not substitute a raw case/source
read for unavailable extracts.

Use model-led reading, including contrary passages, to propose each relevant
qualitative conclusion with `propose_qualitative_evidence`:

- `id`, `document_id`, exact `start`/`end` character offsets and `quote`;
- `period: {start, end}`, supported `flag` from the controlled catalogue,
  `outcome` and `reason`;
- optional `supersedes` identifies an earlier interpretation of the same flag.

The four proposed outcomes are `APPLICABLE`,
`NOT_APPLICABLE_WITH_EVIDENCE`, `UNDETERMINABLE` and `OUT_OF_ENGINE_SCOPE`.
Every proposal remains `MODEL_SUGGESTED`. Only a separately requested
professional decision uses `review_qualitative_evidence` with `proposal_id`,
`outcome: CONFIRMED|REJECTED` and `reason`. A source solely outside the current
period cannot confirm current applicability. Changed source bytes require a
fresh interpretation, with `supersedes` preserving the earlier conclusion.
Uncertainty and scope limits remain blocking. Absence of a keyword is never
negative evidence.

## Area plan

Use `propose_area_review` with `id`, `reason`, registered `evidence_refs`, and
`content` containing:

- `complexity: SIMPLE|COMPLEX` and `complexity_reason`;
- `account_areas`: exactly one `{account_id, area_id}` for every source account;
- `areas`: one disposition for every area in the controlled catalogue,
  `{area_id, status, reason, evidence_refs}`. Status is `ACTIVE`, `EXCLUDED`,
  `UNDETERMINABLE` or `OUT_OF_SCOPE`. Optional `closing_area_id` explicitly
  links an existing closing-review area; use its exact registered ID.

Read the controlled `rulepacks/it/review-catalogue-2026.1.json` as configuration,
not case evidence. Never classify account descriptions by tokens. Account
assignments and documentary relevance require model interpretation and
professional review. An assigned account cannot belong to an excluded area.
Confirmed positive documentary evidence prevents exclusion even with no account.

Only an authorized reviewer, after the professional has reviewed the proposal,
uses `confirm_area_review` with `proposal_id`, `reason`,
`source_versions_reviewed: true`, and the case's exact
`oic_rule_pack_checksum`. Changed source/form/account evidence makes a pending
proposal stale. Never synthesize the version-review confirmation.

The 29-principle index contains titles, source links and contributor metadata;
it is not bundled OIC publication text or complete codification. Ninety-six
professional prompts cover twelve principles. Other applicable principles show
an explicit coverage-gap conclusion; the 295 generic prototype section controls
are excluded. These are review prompts, not automatic accounting verdicts.
The effective-dated OIC pack already locked in the case remains authoritative.
In particular OIC 34 is not activated for the 2016–2023 pack. The catalogue's
current source editions must be checked against the actual exercise by the
reviewer; they are never silently backdated to historical financial years.

## Proportionality and workpapers

A `SIMPLE` micro/abbreviated case with internally maintained bookkeeping uses
`STREAMLINED`: each applicable principle groups all its review objectives into
one conclusion. No objective, statutory gate, required schedule or final
approval is dropped. Ordinary, external-bookkeeping and complex cases use
`FULL`. Ordinary accounts require the cash-flow area.

`AREA_DASHBOARD`, `AREA_WORKPAPERS`, `AREA_CONTROLS`, `OIC_CATALOGUE` and
`QUALITATIVE_EVIDENCE` expose paginated workpapers over accounts, reviewed
mappings, account-to-fact links, exact reconciliations, required/acquired
schedules, open questions, issues, note sections and source documents.
`record_area_controls` accepts one explicit professional conclusion with
`area_id`, `control_id`, current `basis_sha256`, `status: PASS|NOT_APPLICABLE|OPEN`,
`reason` and registered `evidence_refs`. These writes require reviewer authority.
A stale dependency hash is rejected. Never record a professional PASS from a
model suggestion alone.

Workpapers are projections of the current case. Source replacement, relevant
account/mapping/fact/schedule/note/question changes and linked closing
suspensions reopen the dependent controls. Unrelated controls remain reviewed.
Prior decisions and interpretation proposals remain in the verified event
chain. Unresolved areas, stale registry versions, account coverage gaps and
open controls block existing validation and approval.

## Existing native panel and Excel

The existing Bilancio and Vera studio panels offer **Aree del bilancio**,
**Carte di lavoro**, **Controlli**, **Catalogo OIC** and **Documenti e
applicabilità**. Area cards open their workpapers and controls; document buttons
open the exact registered text excerpt, with pagination and no arbitrary path.
**Aggiorna dal fascicolo** reads the latest service revision. This is controlled
reimport and refresh, not a background file watcher.

**Prepara Excel di revisione** builds a private fifteen-sheet `.xlsx` from that
same revision and offers its download inside the panel. It retains exact EUR
amounts as text, source checksums, states and decisions. All untrusted cells
are string cells, never formulas or external hyperlinks. Repeated export of
one unchanged revision is byte-identical. The file is a review document, not
an authoritative input; editing it cannot accept decisions or approve accounts.
Workbook files stay beneath the authorized case's private storage. A stale
revision, symlink destination, oversized cell or UI download is refused.

These synthetic tests do not establish real-client or installed-host acceptance.
