> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Foreign invoice preparation

Use the [Agenzia delle Entrate compilation guide 1.10, 2025-04-01](https://www.agenziaentrate.gov.it/portale/documents/d/guest/guida_compilazione-fe-esterometro-v1-10_aprile_2025),
directly retrieved and inspected on 2026-09-14, alongside the current official
format documentation linked in `../README.md`. Check current guidance and the
operation's applicable period before making a case-specific tax proposal.
Public research uses generic topics, never client identifiers or invoice text.

The guide distinguishes TD17 for services purchased from abroad, TD18 for
intra-community goods purchases and TD19 for the specified goods purchases
under article 17(2). These are different operations, not interchangeable XML
encodings. The professional selects the applicable treatment from actual facts.

Preserve the foreign supplier in CedentePrestatore and the Italian party in
CessionarioCommittente. For each document retain the original invoice number
and date in DatiFattureCollegate. Separately review the new document date and
numbering. The original date alone does not determine the correct preparation
date; receipt and operation timing may matter. Preserve foreign original
currency/amounts in evidence and review the basis of any EUR conversion.

Stop tax inference when establishment, location or kind of supply is unclear.
Do not assume that foreign VAT, a foreign address, or a keyword proves reverse
charge. Credit corrections and unusual regimes need the applicable guidance,
reference linkage and explicit treatment review. The exporter checks the
recorded fields; it does not determine legal applicability or validate an
identifier against tax-authority registers.
