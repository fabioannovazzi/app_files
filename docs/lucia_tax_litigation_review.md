# Lucia Italian tax-litigation workflow: development evidence

Review date: 13 October 2026. Source guidance:
`plugins/_shared/vendor/modules/italian_tax_litigation/`. This is a source/package review,
not acceptance on a real client file or a fresh installed conversation.

## What was authored

Lucia identifies the next procedural step from case events using its own Italian
guide. The lawyer supplies facts and documents and makes professional choices;
the lawyer is not asked to encode the procedure. The guide covers first-instance
preparation, service and subsequent filing, hearing submissions, interim-order
challenges, settlement consequences and appeal. Later remedies are identified
with explicit limits rather than claimed as fully implemented procedures.

`references/fonti.md` records the official sources and editorial access limits.
The reviewed consolidated texts establish the 2027 commencement of the tax code,
ordinary 60/30-day steps, hearing intervals and the specific 15-day interim-order
challenge. Official Cassation summaries supplied the distinction between postal
dispatch and receipt for the filing clock; the full decisions were not acquired.
Legal applicability and subsequent developments still require case-specific
research and review. No legal classifier or fixed deadline engine was added.

## Synthetic forward checks

The current assistant applied the source-reviewed guide to the following fictional
inputs and wrote the analyses. The existing local helpers then prepared evidence,
saved/reopened stages and questions, retained history and rendered progress.
Arithmetic was checked against the stated premises; the script did not choose
law or classify facts. These checks did not test autonomous behavior in a new host.

| Case | Model-authored result and observed local behavior |
| --- | --- |
| Tax act received 1 June 2026; postal dispatch 20 July; recipient receipt 23 July; no filing proof | Distinguished the ordinary challenge deadline from filing. With stated ordinary-regime and summer-suspension premises, filing calculation was 22 September. Packet preparation stayed available; acquiring filing proof stayed blocked. No filing was claimed. |
| First-instance collegial interim order dated 2 October; registry communication initially missing | Identified the specific art. 47 remedy and left the 15-day clock undetermined. Independent strategy work remained available. A simulated lawyer answer of 5 October yielded a visibly conditional 20 October calculation; the receipt remained an open evidentiary question and prior state was preserved. |
| Public hearing on 30 November 2026 | Calculated 20 clear days for documents and 10 for a memorandum from explicit premises: 9 and 19 November. Did not introduce the 5-day chamber-only written reply into a public hearing. Kept a changed hearing date as a reason to reopen the calendar. |

Local evidence: `/private/tmp/lucia-tax-forward-evidence/verification.json` and
the three case folders, containing fictional inputs, working evidence, written
analysis, `matter.json`, history and `matter.html`. These task-local paths are
development evidence and are not runtime dependencies.

## Acceptance boundaries

The matter helper enforces declared question dependencies, schema and file
integrity. It cannot detect every legally omitted step, establish source support
or prove unchanged law from unchanged hashes. The model must review those issues.
Preparation is distinct from actual lawyer-performed service, filing and payment.
No real court filing, background alert or client-case acceptance was performed.

The new explanation uses the existing function-page renderer, shared blue system
and five translations, including the function-specific final model-data section.
Source changes and all Lucia host packages share one candidate version. Package
building does not update an enabled plugin or authorize Marketplace publication.
