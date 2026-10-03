# LIPE - review of anomalies and correspondence

These prompts implement the channel's A1-A13 investigation scope. They are not
tax classification rules or evidence that every control has passed. Read the
original pages, determine whether each question is relevant, and record only
supported proposals. Missing source material means not examined, not no error.
Do not infer a tax status from a name, a country, a code prefix or round amounts.

| ID | Question to investigate | Evidence and boundary |
| --- | --- | --- |
| A1 | Does a closing entry explain a register/liquidation difference? | Inspect the actual entry, account, date and software treatment. An opposite amount or a code absent from a register is only a lead; it does not establish the cause or justify a reversal. |
| A2 | Are the supplied prints final and complete? | Quote the actual header or warning, identify the affected sections and obtain the missing definitive print. A date or filename alone does not establish finality. |
| A3 | Do registration, chargeability and deduction belong to different periods? | Inspect invoice receipt, registration and the claimed deduction basis with the current official rules. VP3 follows registration. A software “data IVA” label does not establish entitlement or move both base and tax. Cross-year cases remain outside the supported scope. |
| A4 | Does documented F24 principal differ from the calculated amount due? | Check the actual receipt, tax code, period, compensation and separate interest/penalties. Missing evidence is not zero paid. Do not diagnose omission, late payment or choose a remedy from the difference alone. |
| A5 | Does a credit note explain a timing difference? | Identify the actual note, signs, related transaction and reviewed periods. Equal amounts alone do not prove the explanation; recalculation does not automatically cure an incorrect allocation. |
| A6 | Is the meaning of the code appropriate for this register? | Verify the vendor/version, any client override and the underlying transaction. Prefix A/V is not a portable tax rule and never authorizes automatic recoding. |
| A7 | Why does one supplier have different codes? | Compare the actual transactions and source invoices. The same supplier may legitimately supply different goods or services; require evidence before proposing a correction. |
| A8 | Is an excluded purchase correctly classified? | Obtain the invoice and its actual legal basis. A personal name or recurring invoice does not establish a forfettario regime. Unknown meaning blocks the affected computation; it is not automatically excluded. |
| A9 | Are import and reverse-charge records duplicates? | Link the invoice, customs evidence, integration and original register rows. Similar amounts or counterparties alone do not prove a duplicate. Determine the separate effects on each VP row; do not assume VP6 neutrality. |
| A10 | Is the recorded deduction justified? | Review the transaction, restriction and actual amount for which deduction is exercised. Repetition or a vendor code alone proves neither full deduction nor full non-deductibility. |
| A11 | Does the transaction require an OSS or territoriality review? | Establish the transaction type, purchaser capacity, place, relevant periods and aggregate facts using current official sources. Do not infer applicability or a threshold breach from a foreign personal name. Unsupported determination methods remain blocked. |
| A12 | Does a non-taxable or round-value invoice require more evidence? | Read the contract/invoice, delivery and relevant export or transport evidence. Round values and zero invoices do not establish an advance, export or error. |
| A13 | Is the country/tax treatment consistent with the actual transaction? | Establish the parties' capacities, places and transaction facts. Country alone does not determine territoriality or the correct code. |

The channel's original proposed defaults are not adopted where they presume an
exclusion, deduction period, closing-entry diagnosis, automatic remedy or filing
with open anomalies. The reviewed official instructions and technical sources in
`sources.json` govern the implemented arithmetic scope; unresolved legal
interpretations require current source research and professional judgment.

## Recording proposals

Case contract 1.3 requires `observations`, `anomaly_review` and `correspondence`.
Use an empty observations list only when there are no recorded proposals; it
does not itself confirm that the sources were reviewed. `anomaly_review` records
the professional's actual scope/completeness review and remains null or PROPOSED
until that review occurs. Never create a confirmation on the professional's behalf.

For each observation record the periods, source quotations, linked register
rows and available protocol, invoice number, date, counterparty and amount.
Keep absent fields null, including an unknown proposed VP6 effect. Specify the
amount basis (taxable base, VAT or invoice total); never present one as another.
Transcribed identifiers and counterparties must occur in the quoted source;
dates must occur as ISO, DD/MM/YYYY or DD.MM.YYYY. Preserve other printed date
forms in the quotation and obtain a supported transcription before claiming a
parsed date. Amount checks respect the declared source number format.

Use `related_comparisons` and `related_findings` from the calculation result to
link the proposal to a concrete discrepancy in the same period. The Excel cause
column and the correspondence then preserve that link. A difference without a
recorded explanation stays a question; the helper never manufactures a cause.

## Decisions and recalculation

A proposal without a confirmed decision blocks VP output. A calculation still
preserves its dossier and current `review_bindings`. After the professional has
actually decided, record `NO_CHANGE` or `INPUTS_REVISED`, reviewer, date and the
reason, plus those exact bindings. `INPUTS_REVISED` is a reviewer declaration,
not proof that an earlier file changed. First correct and recalculate the case,
then bind the decision to the current facts and proposal.

Changing financial facts, source hashes, the proposal, engine or rules makes the
decision stale. Reopen it for review; do not just copy new hashes onto an old
decision. Estimated effects are never automatically added to VP6. A confirmed
explanation does not erase a numerical difference from the workpaper. These
local records attribute decisions; they do not authenticate identity or permit
real XML export.

## Deliverables

Inspect `anomalies.md`, `anomalies.json`, `workpaper.xlsx`, `summary.pdf` and
`review-request.md`. The latter is an unsent client-specific draft: print issues,
available VP figures and method, numbered source-backed questions, corrected
print request and filing deadline. Recorded resolutions are not asked again.
Review all language before delivery. Never send the draft without authorization.

Populate `correspondence.filing_deadline` only with a supported date and its
review status from a current official source saved in the case. The helper
checks that the date occurs in the citation; it does not determine legal
applicability. If it is unknown, the draft expressly leaves it to be verified.
Do not create an automatic filing calendar or infer a deadline from a quarter.
