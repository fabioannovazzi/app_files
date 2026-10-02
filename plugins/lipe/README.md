# LIPE

Evidence-linked review pilot for Italian periodic VAT communications. The
pipeline reads reviewed register extractions, reconciles totals, calculates VP
drafts, and retains source hashes, row composition and payment differences.
Case contract 1.2 requires each period's liquidation sections, their reviewed
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
`references/acceptance.md`. Real XML export stays blocked. The synthetic XML
command requires local official XSD validation and uses fictional identifiers;
it does not establish Agenzia Entrate or accounting-software acceptance.

## Quali dati arrivano al modello

The host model can read register pages, identifiers, amounts, tax codes, periods,
payment excerpts, decisions and review outputs. The Python helpers make no model
or network requests; this does not describe what the host already received.
Actual model exposure is recorded separately in the run's model-data report.
