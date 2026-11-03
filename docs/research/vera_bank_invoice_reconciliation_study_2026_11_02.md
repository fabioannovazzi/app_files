# Vera bank and invoice reconciliation for Italian commercialisti

Research and product assessment · 2 November 2026 · Independent Italian accounting practices

## Decision in brief

**Emphasize operational allocation, but position Vera as assistance with unresolved settlements and evidence, alongside the accounting system. Preserve bank–journal control and open-item substantiation as distinct results. Share the mechanical infrastructure and offer purpose-specific workflows; do not merge the meanings of their matches or create three independent engines.** This is a recommendation from the evidence below, not a claim that this architecture is fully implemented or that Vera has demonstrated an economic advantage.

Vera already does more than produce a list of possible matches. Its open-item component can establish unique invoice payments, retain partial-payment balances, construct conserved allocation ledgers and incorporate source-cited semantic assessments. It also distinguishes internal bookkeeping, payment instructions and external settlement evidence. These are useful foundations to retain. Its bank–journal component independently checks correspondence between bank and accounting movements. Neither result, by itself, proves that accepted proposals have reached the live bookkeeping system. [S1–S8]

For routine transactions already handled inside an enabled accounting product, **use that product's matching and posting first**. TeamSystem products, Zucchetti Ago, PROFIS, DATEV Koinos and GB document overlapping automation; product and module differences matter. Vera's strongest plausible contribution is the work left outside that automation: ambiguous names, several invoices behind a transfer, instalments, missing remittances, contradictory records, and evidence gathered across files. The reviewed evidence does not establish market-wide time savings, comparative model accuracy, adoption or installed-host readiness. [E1–E8]

The most necessary improvements are concrete: expose competing allocations and their evidence in the review, distinguish acceptance from bookkeeping updates, and provide a usable handoff to the studio's actual system. Start with an explicit allocation schedule and destination identifiers; an import-ready file or write connector requires the exact destination contract. Building generic accounting writeback or replacing native bank feeds would be premature. Improving the report's prose alone would leave the operational problem unresolved.

## Scope and strength of evidence

**Observed** means inspected source, an executed regression, an official manual, or explicitly identified historical evidence. **Inferred** means a reasoned product or professional-work conclusion. **Unknown** means the available evidence does not establish it. Recommendations are assessment only. No production code, deployment, publication, client records, vendor accounts or external communications are part of this work.

The source baseline is commit `1b86d7735ca28f272edf763b67cfe95f1ecda4b3`, inspected in the primary checkout. References S1–S20 below identify exact owning files and line spans, with immutable GitHub links. Local changes to those files would require reassessment. Vendor sources were checked on 2 November 2026; claims about automation are vendor documentation, not independently measured benefits.

The three purposes have different completion criteria:

| Purpose in priority order | Question answered | Useful completion | What completion does not establish |
| --- | --- | --- | --- |
| Operational allocation | Which invoices or instalments should consume this payment, and by how much? | An evidenced allocation, remaining cash and invoice balances, unresolved alternatives, and a usable bookkeeping handoff | That a proposal has been posted, or that the entire balance is recoverable |
| Accounting control | Do existing allocations and balances agree with bank evidence, subledgers and journals? | Explained differences and specific correction proposals; all supplied populations accounted for | That bank–journal agreement proves correct invoice attribution |
| Audit and substantiation | Are settlements and balances supported, including evidence against the recorded conclusion? | Traceable procedures, evidence, alternatives, exceptions and a professional conclusion appropriate to the engagement | A signed opinion, authentic third-party confirmation, or sufficiency established by software alone |

These are uses, not evidence of three implemented pipelines. Audit can discover a previously unidentified settlement or reject an apparent match. It is not limited to endorsing existing allocations.

## Professional work and where the effort remains

### Operational allocation

**Observed professional practice.** Passepartout's saldaconto manual works on customer/supplier instalments, supports full and partial payments and abbuoni, and generates accounting entries. Its banking manual distinguishes bank movement reconciliation from the subledger settlement operation. Aruba's procedure separates proposed associations, manual selection, cancellation and completion; completion changes payment status and payment date. These are documented operating procedures rather than abstract AI capability lists. [E9–E11]

**Inferred working method.** Establish the company, account, currency, period and current unpaid population; distinguish invoice face amount from current outstanding amount. Inspect bank execution and remittance information. Propose the invoice/instalment allocation, preserve excess cash and unpaid balances, and separate settlement from deductions. Investigate alternatives before consuming cash. Then record the operation in the accounting system and inspect the resulting balances. The professional task is finished only to the degree that this last step and the exceptions have actually been dealt with.

The time-consuming part is plausibly finding and resolving exceptions rather than adding amounts. This prioritization follows Fabio's stated objective and the structure of the documented work; it is not a measured Italian time-allocation statistic. The study does not require a new time study before making a recommendation.

What remains manual or judgmental includes identifying a payer acting for someone else, obtaining a remittance, determining whether a deduction is agreed, deciding how an unexplained short payment should remain open, selecting a valid bookkeeping treatment, and resolving two equally plausible invoices. Some of this work belongs to the client or the commercialista because the source evidence does not contain the answer. A model can draft the specific question; it cannot create the missing fact.

**What an affordable plugin can contribute.** Normalize the selected exports, search source references, calculate several proposed distributions, surface competing interpretations, explain why one is better supported, retain the decision, and prepare an allocation schedule for recording. Use a model where meaning matters, such as a shortened payer name combined with a document reference. Do not spend model calls recomputing totals or re-reading an unchanged case. If the native accounting product already proposes the same allocation and records it directly, using Vera may add export, review and re-entry work with no compensating benefit.

### Accounting control

**Observed professional practice.** The Passepartout banking manual checks that movements exist in both the bank statement and the bank ledger and that amounts and dates correspond, then addresses errors. GB documents a route from open items to the underlying journal entry and a view of recorded versus unrecorded movements. [E8, E10]

**Inferred working method.** Use both directions of reconciliation. An entry without bank support and a bank movement absent from the ledger are different exceptions. Reconcile opening balances plus movements to closing balances for each bank account and the relevant subledger/control account; investigate timing items and subsequent clearance. Check the actual allocation links where available. A receivables total can be right while one customer's invoice is closed incorrectly and another remains open.

Low-cost assistance can cross-check exports independently of the software that produced them, trace duplicate usage, show residuals and prepare a correction list. It should distinguish a missing entry from a missing document, an allocation error from a timing difference, and a source gap from a confirmed accounting error. It cannot independently confirm live balances or detect concurrent edits from stale exports.

**No-change conclusion.** Keep a straightforward bank–journal check available. A studio needing a period-end control need not provide invoices or undergo an operational allocation workflow merely to compare two movement populations. Where the accounting system already supplies an adequate control and no independent check is needed, a second Vera run is unnecessary.

### Audit and substantiation

**Observed professional reference.** ISA Italia 500 requires sufficient appropriate evidence and addresses reliability, entity-produced information, item selection and inconsistencies. ISA Italia 505 discusses external confirmation and alternative procedures; source, direct acquisition and documentary form affect reliability. These are audit references, not mandatory workflow steps for every bookkeeping allocation. [E12, E13]

**Inferred working method.** Define the assertion and population, reconcile to the accounts, inspect settlement support and contrary evidence, and consider cutoff and later receipts. A subsequent receipt can support settlement of an identified receivable while leaving its position at the earlier cutoff unchanged. Investigation may find an unrecorded settlement, an unsupported closure, an offset, or a disputed debt. A bank transfer does not establish all assertions about an invoice, and technical file integrity does not establish source authenticity.

Affordable plugin work is useful for evidence indexing, full-population mechanical checks, risk-focused selection, explicit alternatives and document requests. It should help the auditor obtain and assess evidence, including evidence inconsistent with the books. It cannot issue a confirmation on behalf of a counterparty, substitute a copied file for direct confirmation, or conclude recoverability and materiality from matching alone.

**No-change conclusion.** Retain the evidence distinctions and provenance in the open-item component. Do not replace this with an accept/reject screen over existing matches, and do not impose a statutory-audit dossier on ordinary cash allocation.

## What Vera implements now

### Open items and bank evidence

**Observed source flow.** `build_reconciliation_artifacts` calls `reconcile_open_items`, builds closed-bank allocation ledgers, generates bank allocation candidates and produces the workbook analyses. `reconcile_open_items` classifies source items, promotes configured probable payments and supported partial payments, withholds settlement for opposing entries, checks mechanical allocations, then applies semantic resolution and declared-payment drafts. These are separate operations inside one component. [S1, S2]

| Implemented behavior | Evidence and practical implication | Limit |
| --- | --- | --- |
| Evidence-aware classification | Strong external support can close an item; an instruction/bridge or internal closure can require further evidence; internal booking can support an open position [S2] | Labels depend on reviewed source roles and evidence policies. A mislabeled source is not made authentic by replay |
| Advisory bank candidates | Invoice references in bank descriptions, shared batch identifiers and unallocated pools produce candidate rows with amounts, differences and follow-up instructions [S3] | This is not a general search that automatically resolves every combination of unpaid invoices |
| Optional promotion | `promote_probable_bank_payments` defaults to false; separate exact-closure policy can promote an eligible high-confidence candidate, followed by allocation controls [S3, S4] | Candidate confidence is rule output, not a calibrated probability or professional approval |
| Partial settlement | A unique compatible, unused supporting payment smaller than the item records allocated and residual amounts [S5] | The mechanical path deliberately abstains on competing documents; cumulative payments can instead use the semantic path |
| Conserved allocation ledgers | Source/target identity, amounts, perimeter, ownership and residuals are checked [S6] | Conservation proves arithmetic and ownership constraints, not the economic meaning of a transfer |
| Source-bound semantic resolution | The worker proposes allocations with quotations and reasons, including party-name equivalence; explicit conflicting IDs remain incompatible [S7] | A valid response shape and real quotation do not prove semantic correctness |
| Direct delivery and resumption | The maintained Archive operation can deliver exact verified work, return a reviewable draft, and reopen the same request without recalculation [S8] | Its `verified` status describes the package's checks. It does not mean posted into bookkeeping |

The current reviewed tabular adapter supports CSV/XLSX roles including `open_items`, `bank_statement`, `journal`, `invoice_list` and `payment_list`. Source-wide entity/currency/unit and per-row party mapping are explicit; ambiguous dates, invalid critical rows and unsupported mappings do not silently become a partial population. This exposes outdated guidance: the component README describes CSV and different Excel layouts as unsupported until a qualified adapter or reviewed preparation exists, without naming the maintained tabular adapter and simple route now available. The wrapper is more current than that README passage. Do not characterize ordinary reviewed CSV/XLSX as universally unsupported. [S8, S9, S19]

Declared invoice/payment lists are useful for preparing an arithmetic draft but do not acquire bank-evidence strength by being imported. A draft can be delivered with that limitation; professional adoption is separate. [S8, S9]

### Bank and journal movements

**Observed implementation.** The core first accepts noncompeting reference matches, then eligible shared-reference groups, then noncompeting amount/date matches in stages. It tracks consumed bank and journal IDs and checks the configured perimeter, date window and amount tolerance. The group path handles a single movement against several on the other side, in either direction, including explicit reference lists. Overlapping alternatives remain unmatched. [S10]

The policy vocabulary includes many-to-many, but the inspected automatic group routine accepts one-to-many or many-to-one shapes. It is not evidence of a general automatic N:N invoice allocator. Its tolerance can permit a difference in a movement match; exact remaining amounts are preserved in the relationship ledger and residual outputs. A matched pair is not necessarily a zero-residual pair. [S10, S11]

The relationship ledger's target population is **journal transactions**. It does not change into an invoice/instalment ledger because a transaction reference happens to resemble an invoice number. Suppose a €1,000 bank receipt matches a €1,000 journal receipt, but the bookkeeper closed invoice B rather than invoice A. Bank–journal correspondence can be correct while invoice allocation is wrong. To answer the latter question Vera needs invoice-level outstanding balances and the settlement relationships, not merely those two €1,000 movements. [S11]

### Actual overlap and dependency

Both components use shared `vera_assurance` primitives for exact amounts, receipts, perimeters, allocation conservation and artifact replay. Open-item semantic resolution explicitly loads the bank component's semantic execution capsule. Thus they already share infrastructure and have a concrete cross-component dependency; they are not fully independent implementations. Their business populations, classification logic, matching sequence and outputs remain different. [S6, S7, S10, S11]

The useful shared object is a source-identified movement or settlement allocation with a defined target type. The dangerous shortcut is an untyped universal “match” whose acceptance means bank control in one screen, invoice settlement in another and audit sufficiency in a third.

## What is demonstrated and what is not

**Observed in this assessment.** The first focused run passed all 72 selected regressions covering partial payments, party mismatches, grouped relationships, competing singletons, allocation constraints, declared lists and the Archive operation. Six additional native-adapter tests passed for selected-case context, assured open-item review and bank review edits. Another 33 passed for exact automatic review, duplicate identities, shortened payer names, uncertain semantic outcomes and oversized packets. Two real-resource Chromium tests then passed after recovering a sandbox launch denial: 113 passed test executions in total, with the original two environmental failures retained separately. Commands and the exact limits of these tests are in the companion note. [V1]

One illustrative fixture is a €524.60 invoice issued on 1 July 2026 to `Eta Impianti Elettrici Di Rossi Mario & C. Sas`, with a 22 July receipt from `ETA IMPIANTI ELETTR.` bearing the invoice reference. The regression verifies that a supplied source-cited semantic response can close and deliver the item without rewriting original names or dates. It also has contrary and ambiguity tests. **The worker is controlled in these regressions**: this establishes acceptance and replay of the intended assessment, not a measured success rate for a live model choosing that assessment. [S16]

**Historical evidence, not a fresh host test.** The retained Test 1 account describes two exact bank–journal matches and an unmatched €5 commission. Decisions persisted, but Apply was blocked with zero target updates and zero regenerated files. UI counting, status, language and feedback defects were then repaired in source; post-install acceptance was not verified at that point. Current source contains corresponding queue and feedback changes. The historical result cannot establish that the current installed package still fails or now passes. The original per-test artifact directory named in history was not present in this checkout during this study. [H1, S13]

**Unknown.** Current installation bytes versus this commit, successful opening and use of the native review in this chat, representative accountant acceptance, live semantic accuracy, large-population completion, comparative end-to-end cost, and bookkeeping writeback. No live client work or acceptance campaign was resumed to answer a research request.

## Review experience and the operator's next action

### What exists and should stay

The current workbench gives a selected accounting case, evidence details, discussion through a bounded selected-case projection, persistent decisions, reviewer notes, requests for documents and saved-work reopening. Bank review separates journal entry, bank movement and match result; native queue code excludes artifact-existence rows from bank accounting-case counts. Apply feedback reports actual decision, blocker, updated-file and regenerated-file counts. These controls should stay. [S12–S14]

**Observed browser UI.** Two existing tests rendered the real MCP resource in an isolated Chromium host with synthetic accounting fixtures. The several-case path saved a note, reopened the same editor through Archive and showed `Decisione salvata · Da chiarire`; the single-case path showed the matched movement and the decision selector. I inspected both screenshots. Evidence is initially collapsed behind the source/details control, so investigation requires expanding it. These tests verify a working browser path and persistence in the fixture; they do not test the native installed Codex host or an allocation-editing workflow. [Screenshots and provenance](../../outputs/vera-reconciliation-study-20261102/provenance.json) are retained with the verification record. [V1]

Open-item review offers accept, reject, edit, unclear, request documents and skip. The generated row's edit target is `review_notes` in the review packet. Bank matched-row editing similarly targets a review note, even where the native workbook is updated to include it. Therefore “Edit” is not evidence of a UI for changing cash amounts, selecting another invoice or redistributing a batch. Open-item candidate counts and workbook sheets exist, but the inspected payload builds accounting items from review rows, rather than exposing every allocation candidate as a first-class editable relationship. [S3, S12, S15]

The review rows are capped at 500 in the producer projection; the native queue paginates the supplied items in pages of 30. Pagination does not recover rows omitted upstream. The full workbook/canonical records remain relevant for larger cases. An operator should not be told that finishing the visible queue establishes review of every source item. [S12, S13]

### Necessary changes if operational allocation is the product priority

These are proposed behaviors, not implemented features. They can build on the current case view and persisted engine decisions.

| Difficult case | What the reviewer needs to see | Next action and required effect |
| --- | --- | --- |
| Several plausible invoices | Original transfer description, payer, eligible open instalments, balances, candidate reasons and competing explanations | Choose an evidenced allocation or leave cash unallocated. Selecting a candidate must update the allocation proposal, not just its note |
| One transfer for several invoices | Allocation lines, each invoice's prior balance, total allocated and remaining bank amount | Add/remove invoice lines and enter exact amounts; reject double consumption across the whole proposal |
| Several transfers or instalments | Each actual payment/date, cumulative allocated amount and invoice residual | Preserve separate payment events. Do not manufacture one aggregate payment date |
| Shortened or third-party payer | Both original identities, references, relevant remittance text and contradictions | Record the supported identity relationship or ask for confirmation of the payment purpose; no forced alias rewrite |
| Credit note, agreed deduction or fee | Invoice gross amount, credit/deduction evidence, cash received and unexplained difference | Distinguish a documented noncash settlement from a remaining debt or fee proposal; accounting treatment belongs to the destination workflow |
| Excess payment or advance | Applied amount, remaining cash, current invoice balances and any remittance instruction | Retain unapplied cash/advance explicitly; do not over-close an invoice to make the bank total disappear |
| Missing evidence | What is already available, the exact missing link and why it matters | Draft a precise request such as “Which invoices are covered by transfer X?” rather than “Send more documents”; sending remains separate |
| Apparent matched item with contrary evidence | Existing allocation, bank evidence, later reversal/credit and alternative targets | Reopen the assessment and produce a correction proposal. An audit view must permit investigation beyond accepted items |

Show three separate states: **proposal saved**, **workpapers regenerated**, **recorded in accounting**. The last needs destination acknowledgement/readback, not a successful local Apply. Count unresolved relationships and remaining balances in addition to decisions clicked. After a decision, return to the next unresolved accounting case while retaining an explicit route back to the saved choice.

The native open-item screen currently asks the operator to type a separately retained predecessor hash for Apply and regeneration. The integrity check prevents applying decisions to a substituted predecessor, a concrete harm worth preventing. Manual transcription is technical burden, however: the simple Archive operation already retains the checkpoint outside the candidate package. The recommended change is to carry the trusted checkpoint through the normal handoff and reserve manual entry for genuine legacy recovery. Keep the independent checkpoint verification; do not turn it into professional approval ceremony. [S8, S14]

For audit, add visibility of evidence against a closure and procedure coverage; for accounting control, lead with differences and proposed corrections. For routine allocation, lead with the bank transaction and distribution. These are different views over evidence, not a justification for three separate UI applications.

## Accounting systems and realistic integration boundaries

### Documented native functionality

| Product and exact scope | What official evidence supports | Consequence for Vera |
| --- | --- | --- |
| TeamSystem Studio and TS Pay | TeamSystem documents integrated bank acquisition and reconciliation; its Studio article describes this context [E1] | Native acquisition/posting is a serious existing alternative. Do not generalize features or APIs across all TeamSystem products |
| TeamSystem Fatture in Cloud | Bank feeds through TS Pay, AI document suggestions, confirmation into prima nota, and manual CSV/XLS/XLSX intake are documented [E2] | Repeating routine native matches outside the product needs a concrete reason |
| TeamSystem Contabilità in Cloud / Reviso | Developer access and REST APIs; a specific semicolon-delimited accounting-entry import with existing master data are documented [E3–E5] | A possible integration surface, not proof of an endpoint that allocates Italian open instalments |
| Zucchetti Ago Infinity | Official page documents AI bank reconciliation and suggested accounting entries [E6] | Overlap is documented. An accessible Ago invoice-allocation write API or exact external allocation-import contract was not established |
| Sistemi PROFIS | Sportello Interrogazione conti bancari integrates statement acquisition and accounting; Sistemi AI documentation includes posting bank movements from Excel or Sportello [E7] | Let native acquisition and accounting do their job. No verified external writeback contract for allocations in this study |
| DATEV Koinos DK Konto | Official indexed product text describes authorized Open Banking movement acquisition and accounting automation [E14] | Relevant Italian offering. German DATEV interfaces are not evidence of Italian DK Set capabilities |
| GB Riconcilia | Official page documents bank-file intake, account rules and invoice settlement associations, with access to open items and journal previews [E8] | Provides a concrete native alternative for operational allocation, not just bank balance checking |
| Passepartout | Official manuals separately document bank intake/reconciliation and instalment saldaconto with generated entries [E9, E10] | Confirms why settlement must be attached to actual instalments and their accounting effects |

This is not a vendor ranking. Licences, client configuration, installed version, data quality, available modules and suitability for a particular studio were not tested. None of the pages establishes comparative savings or a zero-error rate.

### APIs and connectors

**Observed available documentation.** Fatture in Cloud publishes REST API and SDK documentation. Issued documents have a modify operation, and the payment-item model includes ID, amount, status, payment account and paid date. This is a concrete candidate for an eventual product-specific payment-status integration. It does not establish that its API exposes the same bank-reconciliation relationship as the web UI or updates the independent studio's main accounting ledger. Permissions, plan entitlement and semantics of updating existing instalments require verification before implementing writes. [E15, E16]

Contabilità in Cloud documents application and agreement tokens and a GET-only demo. Its API reference contains entries, invoices and payment resources, but the voucher section is explicitly restricted to agreements with international ledgers. In particular, the existence of `POST /vouchers/drafts/customer-payments` cannot be treated as proof of support for the Italian ledger. The reviewed reference did not establish the required invoice-allocation write operation for the target Italian setup. [E4, E5]

DATEV Koinos has an official developer portal, accreditation through DKid and public API documentation categories including SuperBill, configuration and IntegraSDI. That is stronger evidence than “DATEV has no APIs,” but does not establish a DK Konto/DK Set open-item settlement endpoint. Its product page repeatedly timed out on direct open; the capability statement above is limited to the official indexed text, and the developer portal was directly readable. [E14, E17]

For Ago, PROFIS, GB and TeamSystem Studio, the reviewed official sources did not establish an external allocation-write API available to this user. This is an evidence limit, not a conclusion that private/partner interfaces do not exist. No Vera connector to these destinations appears in the inspected reconciliation entrypoints and output/review paths. Their concrete outputs are local workpapers, JSON/CSV records and review artifacts. [S1, S8, S11, S15]

### File handoff

The current exportable allocation and evidence records can support a useful **reviewable settlement schedule** today: source bank ID/date, destination invoice/instalment reference, amount, currency, entity, original party, evidence, residual and decision. Where destination IDs are not present in the supplied exports, mark them unresolved. This is a proposed handoff format, not a vendor-import specification already implemented in Vera.

Contabilità in Cloud provides a real import contract for accounting entries: semicolon CSV, grouped registration number, dates, existing customer/supplier/account codes and other documented columns. This proves entry import is possible, not that an entry import closes a pre-existing open instalment. Obtain the actual example file and verify the linkage behavior in the exact edition before calling any output “import-ready.” Do not invent a generic TeamSystem CSV. [E3]

Xero's official processor-receipts example illustrates a further boundary: individual invoices can be settled through a clearing account, while an aggregate bank receipt clears that account. Fees and refunds require their own supported treatment. Vera should preserve such intermediate evidence where supplied rather than insist that every net bank receipt directly equals an invoice total. This is a useful accounting-workflow example, not a proposal to move an Italian studio to Xero or evidence of a Vera integration. [E18]

Similarly, a bank CSV, CBI RH or CAMT feed is movement transport, not a general allocation-update contract. Passepartout documents CBI RH and CSV/TXT bank intake; it does not mean Vera currently parses CBI or can write settlement links by producing one. Re-importing already acquired bank movements can duplicate entries if mistaken for an allocation update. [E10]

### Computer use

Computer use can bridge a visible export or a missing one-off entry screen when the exact installed software and controls are available. It is usually a weaker default for repeated bulk writes: it adds navigation, calls, UI drift and uncertain save outcomes, while making duplicate prevention harder. This is an architectural inference, not a measured comparison on these systems.

No tested computer-use route from Vera's accepted reconciliation to TeamSystem, Ago, PROFIS or DK Set was established here. The existence of general browser automation or DATEV-related skills is not proof of such a route. A future implementation should first prepare and review the proposal, then use the visible native operation with explicit scope, retain its result and read back the changed balances. If a save times out, inspect destination state before retrying. This assessment authorizes none of those writes.

### Boundary for accepted allocations

Vera should own evidence organization, proposals, explanations, exact distribution checks and review history. The accounting product should remain the authority for current open instalments, chart of accounts, posting periods, tax-sensitive accounting effects and durable posting identifiers. A supported connector may create or update a native draft rather than making the accountant transcribe it; that is a valid future outcome if the product supports it.

For a future write route, the minimum useful sequence is:

1. Read current destination items, existing payments and stable identifiers. Preserve whether the bank event is already booked, since allocating an existing receipt and creating a new receipt are different operations.
2. Freeze a reviewable plan containing only the accepted allocations and explicit residuals. Preparation needs no professional signature.
3. Recheck balances and existing allocation links before the write. A stale export must not authorize a second application of the same cash.
4. Use the exact documented draft/import/update operation with the required authorization. Use destination idempotency where supported; otherwise retain an operation reference and inspect the destination before a retry. A local hash alone cannot prevent a duplicate created outside Vera.
5. Retain destination receipts and read back actual allocations and balances. Report partial success per operation and keep unsuccessful items open.

These controls prevent identifiable errors: duplicate receipts, allocation to the wrong company or instalment, over-allocation, and retry after an uncertain save. They do not justify blocking production of an allocation draft because an import contract is unavailable. If writeback cannot be supported economically, a clear manual posting schedule is an acceptable endpoint, with its re-entry burden stated.

## Architecture choice

| Option | Advantage | Cost or failure mode | Assessment |
| --- | --- | --- | --- |
| One multiuse pipeline with one result meaning | Few entrypoints, common preparation | Conflates movement matching, invoice settlement and evidence sufficiency; may demand irrelevant inputs | Reject as the product model. A common launcher alone is harmless |
| Shared core with purpose-specific workflows | Reuses parsing, evidence identity, conservation, review storage and worker isolation while preserving different questions | Requires typed populations, explicit statuses and carefully scoped shared policies | **Recommended**, extending the sharing already observed |
| Fully separate pipelines/engines for operational, control and audit | Independent evolution and clear initial purpose | Duplicates money/source logic, divergent decisions and repeated imports; three report stacks to maintain | Unnecessary on current evidence |

Keep two domain engines for now: bank–journal correspondence and open-item/evidence settlement. Provide operational allocation, control and audit workflows that select the needed engine/results; control may use both. Share mechanical primitives and evidence storage rather than rewriting either matching algorithm merely to consolidate code. A graph joining bank movement, journal entry, payment event and invoice instalment is a useful conceptual model, but implementing a new graph platform is not necessary to make the next improvement.

Do not require a bank–journal run before every invoice allocation. A studio may have bank receipts and open invoices before entries are posted. Conversely, a bank-account control should run without invoices. An audit engagement may need ledger roll-forwards and contrary evidence in addition to both. An engine result should state its actual coverage so workflows can compose it without overstating its conclusion.

## Affordable intelligence and reviewer burden

**Observed boundaries.** Open-item semantic resolution projects selected fields and considers all unresolved targets and eligible unused external-bank evidence within a currency/entity perimeter. It does not partition by a fuzzy customer name that could hide a relevant alternative. A perimeter exceeding 120 combined rows or a 48,000-byte prompt is left explicitly blocked; it is not silently truncated. Bank semantic review similarly requires complete admitted residual coverage within its packet/component bounds. [S7, S17]

This is a sound protection against false certainty from missing alternatives, but it is also a practical capacity limit. A same-company EUR perimeter can exceed the open-item cap in ordinary work; the study does not establish how often. A future scaling design must preserve retrieval coverage, candidate alternatives and cross-batch cash ownership rather than simply chopping the spreadsheet into arbitrary sets of 120.

The relevant economic model is:

`total effort/cost = intake + model context/calls + investigation + review + regeneration/retries + destination entry + correction risk`

A smaller model packet can lose overall if it causes repeated source opening, another explanation, a second review and manual posting. A larger, well-grounded case packet can be cheaper overall. The inspected code does not establish actual token charges, median review minutes or comparative errors; no numerical ROI is claimed.

Applying the repository's deterministic-judgment standard leads to these boundaries:

| Work | Reason for the boundary | Recommendation |
| --- | --- | --- |
| Parse an explicitly mapped table; sum amounts; conserve allocation capacity | Exact contracts and arithmetic are mechanically verifiable | Retain deterministic code and meaningful regressions |
| Identify an exact unique source reference within a compatible perimeter | Uniqueness and source agreement can be checked directly | Retain automatic handling; do not demand a click for every such item |
| Infer payer identity, remittance meaning or explanation for a difference | Meaning depends on surrounding evidence and alternatives | Use model/professional judgment with citations and abstention |
| Choose whether a deduction extinguishes debt or changes accounting treatment | Arithmetic cannot establish entitlement or the economic fact | Show a proposal and evidence; retain the unresolved material decision |
| Reopen an unchanged saved result | Recomputing repeats effort without new information | Retain stable request resumption |
| Retrieve candidate evidence at scale | Fixed pruning can silently exclude the right relationship | Treat as an unresolved design problem; retain visibility of excluded scope and test representative alternatives before adopting a rule |

Do not replace the semantic name-resolution path with prefix matching to save tokens. The shortened-payer fixture demonstrates why exact string identity can be too restrictive; it does not prove that every similar name is the same party. Conversely, do not ask a model to override explicit conflicting party IDs merely because it finds the narrative plausible. [S7, S9, S16]

## Recommendations by value and necessity

| Priority | Retain or change | Concrete reason and tradeoff |
| --- | --- | --- |
| First | Make allocation relationships and alternatives actionable in the existing review | This closes the observed gap between candidate production and an operator's allocation decision. Adds focused review complexity; avoids building a whole new application |
| First | Deliver a settlement schedule usable for the actual accounting task, with explicit posting state | Reduces interpretation and potential re-entry errors; it remains manual until a verified destination contract exists |
| First | Keep exact arithmetic, source identity, residuals and evidence strength | These prevent demonstrated over-allocation, wrong-party and unsupported-closure harms; do not remove them for a cleaner screenshot |
| First | Preserve direct delivery of exact results and useful drafts | No accounting adoption is implied; mandatory review ceremony would impose effort with no demonstrated gain |
| Next | Carry trusted review checkpoints automatically through supported handoffs | Keeps predecessor-substitution protection while removing manual technical transcription |
| Next | Make coverage and blocked semantic scope visible, including the review-row cap | Prevents finishing a visible subset from looking like complete work; does not require withholding useful completed results |
| Next | Qualify one destination-specific handoff where a studio actually uses it | Potentially turns accepted decisions into operational work. Prefer an existing supported draft/import route; integration maintenance may outweigh value for small volumes |
| Next | Align README guidance with the maintained CSV/XLSX route | Removes an observed documentation contradiction at low cost |
| Retain | Bank–journal control as a separate result and existing shared infrastructure | Both serve a distinct question; a rewrite has no demonstrated benefit |
| Retain | Evidence-oriented open-item audit outputs, including contrary evidence and post-cutoff distinctions | They support investigation rather than merely ratifying current allocations |
| Do not pursue by default | Generic writeback to all Italian systems, replacement bank feeds, three independent engines, automatic semantic writeoff or forced completion | Interfaces and economic advantage are not established; these expand scope without solving the evidenced review gap first |

The present recommendation is actionable without interviews or new benchmarks: prioritize exception allocation and bookkeeping handoff; retain the current mechanical foundation and separate result meanings. Later measurements can revise the investment order. They are not prerequisites for making this bounded choice.

## Data reaching the model and privacy reporting

Local parsing does not mean a local-only professional workflow. Mapping previews, selected-case evidence and semantic worker packets can contain real dates, amounts, invoice references, descriptions and party names. Current open-item privacy documentation explicitly recognizes those paths. The worker projects a bounded set of fields; that is minimization, not anonymization. Selected-case explanations reduce routine context, but their usefulness depends on access to relevant alternatives when the operator investigates an ambiguous allocation. [S7, S18, S20]

Keep pipeline and privacy-report results separate. The simple operation returns accounting readiness and reporting warnings separately. A missing/incomplete measurement must remain visible and be repaired without negating useful reconciled output. Historical Test 1 evidence described a running report that showed zero exposure while collector events already existed; that is a warning against interpreting an unfinished report as zero transmission, not a fresh finding about this source version. [S8, H1]

This study read source and synthetic test evidence; it did not start a real reconciliation or issue a terminal data-use acceptance report. Model-context/runtime boundaries and provider behavior were not independently audited here.

## Source register

All S references use commit `1b86d7735ca28f272edf763b67cfe95f1ecda4b3`. Line spans below describe the inspected scope; the link opens its start. They establish implementation, not deployment or installed acceptance.

- **S1** — [Open-item artifact orchestration, lines 410–501](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/open-item-reconciliation/scripts/reconciliation_workflow.py#L410).
- **S2** — [Classification, lines 3589–3754, and orchestration, 3917–3993](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/open-item-reconciliation/scripts/retained_sources/reconciliation_helpers.source#L3589).
- **S3** — [Candidate construction, lines 2150–2432](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/open-item-reconciliation/scripts/retained_sources/reconciliation_helpers.source#L2150).
- **S4** — [Exact candidate closure and promotion, lines 2478–2593](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/open-item-reconciliation/scripts/retained_sources/reconciliation_helpers.source#L2478); [default assumptions, lines 88–100](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/open-item-reconciliation/scripts/retained_sources/reconciliation_helpers.source#L88).
- **S5** — [Partial payments, lines 3103–3190](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/open-item-reconciliation/scripts/retained_sources/reconciliation_helpers.source#L3103).
- **S6** — [Allocation controls, lines 2696–3068](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/open-item-reconciliation/scripts/retained_sources/reconciliation_helpers.source#L2696).
- **S7** — [Semantic resolution, lines 1–114, 198–370 and 514–685](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/open-item-reconciliation/scripts/semantic_resolution.py#L1).
- **S8** — [Maintained import-to-delivery guide, lines 1–54](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/open-item-reconciliation/references/simple-reconciliation.md#L1); [owning operation, delivery and finish, lines 83–203](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/studio-archive/scripts/reconcile_open_items.py#L83).
- **S9** — [Reviewed tabular source contract](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/open-item-reconciliation/references/tabular-source-layout.md#L1).
- **S10** — [Bank core imports, lines 53–73, candidate filtering, 5444–5505, groups and stage matching, 5592–5901](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/journal-bank-reconciliation/scripts/journal_bank_core.py#L5444).
- **S11** — [Bank–journal relationship ledger, lines 5902–5971, and output/readiness logic, 7411–7598](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/journal-bank-reconciliation/scripts/journal_bank_core.py#L5902).
- **S12** — [Open-item review rows, lines 668–801, payload assembly, 1603–1705, candidate count, 1762–1764; cap at line 25](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/open-item-reconciliation/scripts/retained_sources/review_session.source#L668).
- **S13** — [Native queue filtering, pagination and recovery, lines 941–1034](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/vera/scripts/native_workspace.py#L941); [UI case evidence and feedback, lines 3222–3242 and 3380–3405](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/vera/ui/workspace.js#L3222).
- **S14** — [Review actions and checkpoint/regeneration controls, lines 3454–3518](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/vera/ui/workspace.js#L3454); [assured Apply, lines 1206–1265](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/open-item-reconciliation/scripts/review_server.py#L1206).
- **S15** — [Bank matched-item edit target, lines 596–603](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/journal-bank-reconciliation/scripts/review_session.py#L596); [open-item workbook candidate sheet, lines 2429–2457](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/open-item-reconciliation/scripts/retained_sources/workpaper_outputs.source#L2429).
- **S16** — [Shortened-payer synthetic fixture](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/tests/fixtures/open_item_reconciliation/case013_truncated_payer.json); [semantic regression, lines 591–655 and related tests](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/tests/open_item_reconciliation/test_semantic_resolution.py#L591).
- **S17** — [Bank semantic bounds, lines 230–246, and complete selection, 1820–1868](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/journal-bank-reconciliation/scripts/semantic_review.py#L1820).
- **S18** — [Native selected-context route](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/vera/mcp/selected-context.cjs#L1); [context and review regressions, lines 1511–1574 and 2007–2066](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/tests/plugins/test_vera_native_workspace.py#L1511).
- **S19** — [Open-item README, input scope](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/open-item-reconciliation/README.md#L1); [Vera open-item wrapper](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/vera/skills/open-item-reconciliation/SKILL.md#L1); [bank wrapper](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/vera/skills/journal-bank-reconciliation/SKILL.md#L1).
- **S20** — [Function-specific model-context inventory](https://github.com/fabioannovazzi/app_files/blob/1b86d7735ca28f272edf763b67cfe95f1ecda4b3/plugins/vera/privacy/workstreams/open-item-reconciliation.json#L1). This is source documentation, not an independent privacy audit.

External references, each with the scope actually used:

- **E1** — [TeamSystem Studio reconciliation article, updated 15 January 2024](https://www.teamsystem.com/magazine/gestione-dello-studio/riconciliazione-bancaria-estratti-conto-la-soluzione-per-i-commercialisti/): integrated acquisition and reconciliation context. The supplied Contabilità in Cloud commercialista landing page returned only an iframe; its functionality was not inferred from that response.
- **E2** — [Fatture in Cloud reconciliation](https://www.fattureincloud.it/software-fatturazione/riconciliazione/): native feed, suggestions, confirmation/prima nota and file intake. Claims such as error elimination or bank coverage are not adopted as verified results.
- **E3** — [Contabilità in Cloud accounting-entry import](https://help.reviso.com/it/articles/61175-importare-registrazioni-contabili): specific CSV fields, existing master data and Italian-version limits.
- **E4** — [Contabilità in Cloud integration tools](https://help.reviso.com/it/articles/61016-strumenti-per-integrare-ed-estendere-contabilita-in-cloud) and [REST API guide](https://help.reviso.com/it/articles/61597-rest-api): developer route, tokens and GET-only demo.
- **E5** — [Reviso API reference](https://api-docs.reviso.com/): payment-management and voucher resources; international-ledger restriction on vouchers. No verified Italian open-item allocation-write operation established.
- **E6** — [Zucchetti Ago Infinity](https://zucchetti.it/it/cms/professionisti/contabilita-fisco-finanza/gestione-contabile-fiscale/ago-infinity/software-gestionale-per-commercialisti.html): FAQ on reconciliation and suggested entries. No accessible external write contract inferred.
- **E7** — [Sistemi bank-account service sheet](https://www.sistemi.com/downloads/Sportello-Interrogazione-conti-bancari_scheda.pdf) and [Sistemi AI for the commercialista](https://www.sistemi.com/eventi-notizie/sistemi-ai-per-il-commercialista-digitale/): native PROFIS acquisition/posting and Excel route.
- **E8** — [GB Riconcilia](https://www.softwaregb.it/software-contabilita-commercialisti/software-import-estratto-conto-studi/): file models/rules, invoice associations, open-item and posting inspection.
- **E9** — [Passepartout saldaconto manual](https://www.edupass.it/manuali/manualistica-passcom-express/manuale-prodotto?a=manuale-bspexpress/contabilita/saldaconto-clienti--fornitori-scadenzario-a-partite): instalments, partial/full settlement, abbuoni and generated entries.
- **E10** — [Passepartout banking manual](https://www.edupass.it/manuali/manualistica-mexal/manuale-prodotto?a=manuale-prodotto/contabilita/appendice--riconciliazione-bancaria): two-way movement controls, PSD2 and CBI RH/CSV/TXT intake.
- **E11** — [Aruba guided reconciliation](https://guide.aruba.it/soluzioni-fatturazione-elettronica/modulo-incassi-pagamenti/gestione-menu/riconciliazione-bancaria/procedura-guidata-riconciliazione): association review/cancellation and actual payment-status/date changes. Its tolerance is not adopted as a Vera policy.
- **E12** — [ISA Italia 500, 2022 text](https://revisionelegale.rgs.mef.gov.it/area-pubblica/export/mef/resources/PDF/ISA-Italia-500-15.06.2022.pdf), paragraphs 6–11 and relevant application material; [MEF current standards index](https://revisionelegale.rgs.mef.gov.it/area-pubblica/normativa/principiRevisione/elencoPrincipiInternazionali/). Direct PDF opening returned HTTP 503; the indexed official text was readable. Not a clause-by-clause legal-currentness opinion.
- **E13** — [ISA Italia 505, 2022 text](https://revisionelegale.rgs.mef.gov.it/area-pubblica/export/mef/resources/PDF/ISA-Italia-505-15.06.2022.pdf), paragraphs 1–3 and alternative-procedure context. Same direct-fetch limitation; official indexed passages used for evidence principles.
- **E14** — [DATEV Koinos DK Konto](https://www.datevkoinos.it/prodotti/dk-konto): official indexed product text on acquisition and automation; direct page fetch timed out, so feature detail remains limited.
- **E15** — [Fatture in Cloud developer introduction](https://developers.fattureincloud.it/docs/getting-started/) and [official issued-document API SDK](https://github.com/fattureincloud/fattureincloud-ts-sdk): API availability and modify operation, not proof of a bank-reconciliation write operation.
- **E16** — [Official payment item model](https://github.com/fattureincloud/fattureincloud-ts-sdk/blob/master/docs/IssuedDocumentPaymentsListItem.md): ID, amount, status, payment account and paid date.
- **E17** — [DATEV Koinos developer portal](https://developer.datev.it/) and [API introduction/categories](https://developer.datev.it/Docs): accreditation and published integration scope; not proof of DK Set settlement writes.
- **E18** — [Xero payment-processor receipts guide](https://developer.xero.com/documentation/guides/how-to-guides/handling-payment-processor-receipts-in-xero): an additional architectural example. It separates payments against invoices via a clearing account from aggregate bank reconciliation and handles fees/refunds separately. This supports the distinction between settlement and bank matching; it is not evidence of Italian bookkeeping compliance or a Vera connector. The supplied Xero Central reconciliation page had no readable body and the replacement Find & Match page was inaccessible, so their full UI behavior is not treated as verified here.

**H1** — Historical acceptance account read from local memory: `/Users/fabio/.codex/memories_v2/rollout_summaries/2026-10-28T10-07-54-TqWb-vera_test1_sol_ui_acceptance_and_0532_repair.md`, lines 13–31, originating chat `01a181fb-068e-7c53-ad9f-c92ad972f727`. Secondary retained summary, explicitly not a present-host observation. It is included to bound acceptance claims, not to substitute for current source inspection.

**V1** — [Study verification record](vera_bank_invoice_reconciliation_verification_2026_11_02.md). Local regressions and research limitations are separate from native-host and professional acceptance.
