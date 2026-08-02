# Check Entries Codex Plugin

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/check-entries) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Check Entries is a Codex workflow plugin for comparing selected journal entries
with Italian FatturaPA XMLs and supporting PDF documents.

The plugin starts from a qualified prepared-evidence boundary:

- Studio Archive must identify the stable client and engagement. In a later
  chat, its engagement listing exposes persisted Journal Sampling contexts and
  exact available normalized-journal paths. Support must be copied, with user
  authorization and original preservation, into that same engagement. Both
  product CLIs require the returned Check Entries context and reject
  cross-client inputs or invented output paths.
- Journal Sampling must first write `normalized_journal.csv` and adjacent
  sealed `normalization_diagnostics.json`. Check Entries replays the complete
  upstream assurance envelope, gate register, reviewed mapping decisions,
  original-source receipts, retained reviewed-recipe receipt, normalized
  receipt, and exact 24-file Journal Sampling/shared implementation receipt
  set. It then invokes Journal Sampling's isolated `-I -B` replay CLI and
  requires the raw journal plus exact retained recipe to reproduce the
  canonical CSV and material preparation contract before Polars parses it.
  Raw journal tables and partial preparation packages are rejected.
- `scripts/inspect_entries.py` validates that qualified population and
  inventories a FatturaPA ZIP/XML, authorized connector export, or PDF support
  folder, then writes
  `inspection.json` and `suggested_recipe.json`.
- `scripts/run_checks.py` preserves prepared identities and source locators,
  seals the complete canonical support-directory membership, captures every
  support artifact once, qualifies the captured bytes, tries a unique labelled
  XML relationship first, and falls back only to a unique PDF carrying a
  labelled movement identifier in extracted text. The membership and every
  receipt are replayed before final assurance.
- `scripts/run_checks.py` also writes `run_intake.json`, `review_payload.json`,
  `ui_decisions.json`, and `final_artifacts.json` so Codex can render an MCP
  HTML review surface for supported entries, missing support, mismatches,
  manual-review rows, PDF extraction diagnostics, and generated artifacts.
- Exact monetary strings, local artifact receipts, source qualifications,
  source-to-prepared-to-CSV/XLSX numeric ledgers, lineage, and assurance gates
  are recorded in the audit. XLSX generation must reproduce identical
  canonical OOXML bytes twice before receipt. Codex handles ambiguity,
  evidence sufficiency, review explanation, and final language without direct
  OpenAI API calls from the plugin scripts.

Run `python -I -B scripts/check_dependencies.py` from the plugin directory
before using the helper scripts. The supported Python launchers establish the
implementation boundary before importing local modules.

Working locales: `it`, `en`, `fr`, `de`, `es`.

## Assurance preflight and trust boundary

Every run stores the exact recipe bytes used for execution in
`execution_recipe.json` and receipts that file as a source artifact. For an
assured run, Python preflight rebuilds the mechanical analysis in a private,
fresh directory from the still-available normalized journal, support source,
and original recipe. It then compares the captured recipe, normalized entries,
support inventory and facts, result CSV/XLSX, numeric evidence ledger,
material audit and review projections, gates, professional status, and final
status with the persisted run. A successor may differ from that fresh baseline
only through its specifically authorized `review_notes` cells and the exact
review-decision/effect lineage. Missing or changed original inputs fail closed.
MCP validate, render, save, and apply paths all invoke this fresh preflight.

Before any supported Python launcher imports local implementation modules, a
bootstrap closes the exact 26-file Check Entries/shared-assurance contract and
rejects every unowned path, bytecode cache, symlink, hardlink, FIFO, or other
special entry. The validated assurance package is loaded from its exact
directory without exposing the broader vendor parent as an import root. MCP
launches Python with isolated/no-bytecode flags. Upstream Journal Sampling
implementation membership is likewise closed before its receipts are replayed
or its normalization replay CLI is executed.

These controls establish reproducibility and internal consistency, not package
publisher identity or reviewer authority. The package is still mutable, local
hashes are not an external trust anchor, and no cryptographic reviewer identity
is established here. Fresh re-performance defeats a locally self-resealed but
stale normalization package; it cannot authenticate a consistently regenerated
package or prove that the person approving the recipe had authority.
Publication therefore remains withheld at this boundary.

## Support acquisition ladder

1. Prefer a ZIP containing the client's FatturaPA XML archive. ZIP members are
   parsed from one immutable archive capture and are not extracted into the
   workspace. Size, member-count, path, encryption, compression-ratio, and XML
   structure limits apply.
   Every member locator includes the canonical captured archive path
   (`archive.zip!/member.xml`), so equal member names in separate archives
   cannot collide or inherit the wrong artifact receipt.
2. If an authorized accounting-system connector materializes the same XML
   export locally, pass that folder or ZIP and record its name with
   `--connector-name`. The plugin never accepts credentials or logs into a
   provider itself.
3. Use PDFs for entries that have no unique XML match. Requests should be
   limited to those unresolved sampled entries rather than the full population.

An XML is accepted automatically only when exactly one invoice has a
distinctive invoice number in explicit labelled invoice syntax in the entry
description plus at least one corroborating amount or date signal. Generic
numeric, year, and single-letter tokens cannot establish identity. An exact
reviewed support-relationship receipt can instead establish the relationship
when it is bound to the prepared entry, captured support artifact, support
locator, and a non-empty recording exception. Amount/date/currency coincidence
can confirm an identity but can never establish one.

A PDF identity requires a distinctive identifier beside an accounting movement
label in text extracted from the captured bytes, or the same exact reviewed
support-relationship receipt. Filenames are inventory metadata only. Generic
numeric/year/single-letter tokens and page/row coincidences are never identity
evidence.

A row is mechanically `ok` only when amount, date, prepared currency, and
reviewed posting direction close against uniquely identified support and the
party perimeter is closed. Structured FatturaPA checks preserve
`TipoDocumento` and its bounded document polarity only as source facts: neither
an invoice nor a credit note determines which journal account side is under
test. PDF invoice/credit-note labels are likewise diagnostic and cannot sign a
support amount. Direction closes only through an exact reviewed
`check_entries_direction` receipt bound to the normalized journal, prepared
entry, captured support receipt, and locator; without one the signed support
amount and differences are withheld and the row remains manual review. PDF
currency requires the exact ISO code or an exact reviewed currency receipt:
`$` alone never distinguishes USD, CAD, or AUD, and an explicit conflicting
ISO 4217 code cannot be overridden. The
PDF party perimeter requires an exact reviewed tax ID beside the reviewed
supplier/customer role label; a generic tax label or opposite role fails
closed. Structured support may instead use an exact
structured XML name under the reviewed `casefold_alnum_v1` normalization
contract, or the exact reviewed relationship receipt and its recording
exception. Free-text name/beneficiary containment is diagnostic only and
cannot promote a row. Evidence facts stay separate from
`professional_conclusion=pending_review`; accepting a review item does not
silently pass withheld assurance gates.

Each PDF, XML, ZIP, or P7M support artifact has its own qualification record.
Readable PDF extraction is a layout qualification, not identity. P7M is
fail-closed until a bounded decoder and signature-validation policy exists.
Any failed support qualification, parse error, or missing support prevents the
global source gate from passing.

`support_manifest.json` records the canonical Unicode/casefold-unique relative
paths and captured receipts for the selected file or every file in the complete
nested support directory, including temporary-prefixed names. Unsupported
types fail source qualification, and symlinks, hardlink aliases, and special
filesystem entries are rejected. Added, deleted, replaced, aliased, or case-colliding support files invalidate final
replay. A successful rerun starts from an empty run directory
and cannot inherit prior `applied_decisions.json` or `revisions/`; any build
failure restores the exact prior output tree.

## UI review MCP

The review UI follows the local OpenAI-style MCP/widget pattern:

- the Python workflow writes bounded review-session JSON files in the run
  output folder;
- the local MCP server declared in `.mcp.json` exposes
  `validate_check_entries_review`, `render_check_entries_review`, and
  `save_check_entries_decisions`;
- `assets/check-entries-review-widget.html` renders summary counts, searchable
  rows, type filters, evidence details, and reviewer action controls;
- saved reviewer actions are validated against the review payload and persisted
  to `ui_decisions.json` when the render call includes `run_intake.output_dir`;
- before either save or apply writes anything, the MCP requires the caller's
  complete immutable run-intake projection to equal persisted
  `run_intake.json`; only the append-only local `execution_trace` is excluded;
- `review_payload.json` carries a canonical content digest, and saved decisions
  carry that same binding; stale or mismatched review state is rejected;
- before any apply write, the MCP replays the locally persisted assurance
  envelope and never trusts caller-supplied gates for final readiness;
- review-note edits are checked against the receipted original CSV, only the
  authorized `review_notes` cells may change, the workbook is regenerated, and
  only affected artifact receipts are refreshed;
- save/apply writes run against a private staged clone while the exact prior
  directory remains rollback material; internal symlinks, hardlinks, special
  entries, and post-preflight path swaps are rejected before review writes; a
  regeneration, reseal, manifest, or later write failure restores the exact
  original tree rather than leaving partial review artifacts;
- accept-only reviews also add a reviewed-decision receipt and reseal
  `assurance_envelope.json`;
- completing or accepting every review item cannot make the run final-ready
  while semantic-review, reporting, or publication gates remain withheld;
- if MCP is unavailable, Codex reads `review_payload.json` and continues with
  Markdown/chat review without blocking the workflow.
