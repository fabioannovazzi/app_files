# Valutazione d’impresa

Vera component for source-backed PMI valuation workpapers. DCF, constant or
finite-duration equity income, clean-surplus residual income with changing equity,
NAV, mixed income, holding/SOTP composition, multiples and APV, with explicit
professional assumptions, receipt-bound sources, exact
calculation lineage, independent method review and existing v3 business-plan
reuse. Outputs: HTML, Markdown, DOCX/PDF, formula XLSX, JSON and CSV.
Optional multiple workpapers retain every peer decision, reported-to-comparable
reconciliations and explicit period/accounting/lease bases without selecting or
averaging the applied multiple.

Read the [skill](skills/business-valuation/SKILL.md) and
[case contract](references/case-contract.md), including its bundled
[JSON Schema](references/valuation-case.schema.json). Run within a portable Studio
Archive engagement. The module calculates selected methods; model and professional
judgment select relevant evidence, methods and economic conclusions. It does not
certify PIV compliance, qualify every legal purpose, sign or file an opinion.

Based on Francesco Giraldo's Valutazioni PMI Developer Pack v0.1.0, recovered
from the Vera Discord discussion on 29 September 2026. Original pack SHA-256:
`cf7ee90de4a3ae4d04682399c1b00cb217252db2ccd8daa33c038e044ef42d2d`.
The implementation adapts its methods to Vera's existing boundaries; the attached
prototype was inspected as source material, not installed or executed.
