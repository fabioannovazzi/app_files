# LIPE

Evidence-linked review pilot for Italian periodic VAT communications. The
pipeline reads reviewed register extractions, reconciles totals, calculates VP
drafts, and retains source hashes, row composition and payment differences.
Case contract 1.3 requires each period's liquidation sections, their reviewed
comparison bases and source quotations. Reconciliation compares each VAT code;
absence is not a printed zero and offsetting errors remain visible.

Each valid-contract revision includes `workpaper.xlsx` with exactly three tabs:
register/liquidation reconciliation, visible VP formulas and F24 comparisons.
Formulas have cached draft values and an explicit comparison against the Decimal
engine. Source contributions, carry-forward steps and adjustments remain visible.
Editing Excel does not amend or approve the saved case: update the evidence and
rerun LIPE. Blocked cases show blockers instead of plausible tax figures.

Structured anomaly proposals preserve invoice/protocol references, quoted facts,
unknown or estimated VP6 effects, actions and content-bound local decisions.
Open/stale decisions block VP output. Proposals are not tax classifiers and their
effects are never applied automatically. `anomalies.md`/JSON, an unsent per-client
`review-request.md` and a paginated `summary.pdf` accompany each valid-contract
revision. The PDF uses embedded fonts and Italian money formatting. Unsupported
glyphs are identified by Unicode code point; original text remains in JSON.

The local SQLite catalog retains vendor/version classes, client and studio
overrides, central-reference records, original source bytes, confidence and
review history. Revisions/revocations are append-only; conflicts and explicit
curator disputes block reuse. Calculation rechecks bound entries over the whole
quarter against the current catalog. No classification or promotion is inferred
from code strings or agreement counts. Real catalog writes require external CMS
signatures with independently assigned professional/curator/disclosure roles and
client/level permissions. Original evidence records verification at commit;
historical reads do not attest that those powers remain current.
See `references/code-catalog.md` for commands and outstanding limits.

The private measurement ledger preserves first-pass populations and subsequent
professional class changes. Reports expose review coverage and denominators,
deduplicate repeat runs and separate real from synthetic cohorts. Literal class
changes are not a tax-error rate. Follow `references/code-measurements.md` before
confirming case mappings; no real performance rate has been established.

Front-page checks now bind identifiers, representative/intermediary fields and
registry-evidence declarations to preserved sources. Approval packets bind the
exact reviewed version and verify external CMS signatures under an independently
configured firm mandate, including chain and revocation checks. These are local
cryptographic checks, not qualified-signature, professional-register or filing
acceptance. See `references/approval.md`.

The approved export path re-verifies original signatures and the current case,
reserves the intermediary's chosen five-digit filename in the configured studio
registry, and writes an unsigned IVP18 with its approved PDF and fresh evidence.
Every XML field and VP amount is read back before delivery. Supplied transmitted
XML can be compared by taxpayer, year and period; metadata and representation
changes remain visible. See `references/xml-export.md`. No real studio or
importer has qualified this path.

The supplied-receipt reader preserves original bytes, validates the official
receipt schema offline, records the declared file ID/status and every reported
error, and compares the name of an optionally supplied transmitted file. It does
not verify the receipt's XAdES signature or establish filing acceptance. Matching
names do not prove content identity. See `references/receipts.md`.

Run `scripts/check_dependencies.py`, then follow `skills/lipe/SKILL.md`.
The exact JSON contract is `schemas/case.schema.json`. The example is entirely
synthetic. Its three monthly modules each have VP2 1,000.00, VP3 500.00, VP4
220.00, VP5 110.00 and VP14 debit 110.00.

Official instructions and technical specifications were downloaded and inspected
on 2026-10-02. URLs, byte hashes and the requirements provenance are recorded in
`references/sources.json`. The channel's original package passed 68 supplied
tests but its real aggregate fixtures and provisional rules are not distributed
in this implementation. LIPE uses a separately implemented, stricter contract.

The delivered state is a **pilot**, not professional acceptance. See
`references/acceptance.md`. Unsigned export requires current external approval
and the host-configured firm authority. The separate synthetic XML command uses
fictional identifiers. Neither path establishes Agenzia Entrate or accounting-
software acceptance, and neither signs or transmits a declaration.

## Quali dati arrivano al modello

The host model can read register pages, identifiers, amounts, tax codes, periods,
payment excerpts, decisions and review outputs. The Python helpers make no model
or network requests; this does not describe what the host already received.
Authorized catalog/measurement reads can also expose preserved proposals,
complete source documents, client/engagement identities, reviewer records and
software-specific counts. Aggregate reports are not guaranteed anonymous.
Front-page evidence, public certificates, signed review requests, mandates and
professional-authority references may also enter the selected model context.
Private signing keys are never requested. Actual model exposure is recorded separately in the run's model-data report.
Supplied receipts, IDs, filenames, dates, error descriptions and notes, and any
file supplied as transmitted may also enter context when the host reads them.
