# LIPE

Evidence-linked review pilot for Italian periodic VAT communications. The
pipeline reads reviewed register extractions, reconciles totals, calculates VP
drafts, and retains source hashes, row composition and payment differences.

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
