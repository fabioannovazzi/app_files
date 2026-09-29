# Vera — Geneva localization assessment and implementation

Updated 2026-09-29 (catalogue integration only; prior professional assessment retained). Target: CH-GE; example user: a generalist fiduciary serving SMEs. French output and CHF are explicit case settings, not selectors of governing law.

This applies the common-core localization method to the complete existing catalogue: 35 professional functions, four internal helpers and two new case foundations. The disposition records the assessment; implementation status is separate. No services absent from Vera have been added.

The release adds bounded adapters and instructions, not a blanket claim that every fiduciary mandate is supported. Original evidence and professional decisions remain necessary. No real Geneva client workflow has been accepted.

| Existing function | Assessment | Implemented path or qualification |
|---|---|---|
| adeguati-assetti | Adapt | CH-GE evidence-based organisation review with Swiss framework basis and same-jurisdiction history. |
| adversarial-opinion | Use | Existing function retained with the recorded qualification limits. |
| aml-review | Adapt | CH-GE source/mandate-applicability contract, same-jurisdiction history and explicit block on Italian scoring. |
| archive-organization | Use | Existing function retained with the recorded qualification limits. |
| avviso-intake | Use | Existing function retained with the recorded qualification limits. |
| bandi-agevolazioni | Adapt | Query-scoped Geneva source-content instructions in the existing discovery/dossier workflow; no imported Italian eligibility assumptions. |
| bilancio-oic | Adapt | Swiss CO/CHF annual-account draft adapter using reviewed account mappings, two-period reconciliation, source-bound disclosure review and professional decisions. No automatic statutory-completeness or filing claim. |
| browser-automation | Use | Existing function retained with the recorded qualification limits. |
| business-planning | Adapt | French report presentation and number formatting; existing CHF calculations retained. |
| centrale-rischi-review | Unresolved | Existing function retained with the recorded qualification limits. |
| comunicazione-professionale | Use | Existing function retained with the recorded qualification limits. |
| concordato-plan-review | Unresolved | Existing function retained with the recorded qualification limits. |
| datev-invoice-start | Unresolved | Existing function retained with the recorded qualification limits. |
| dati-fiscali-strutturati | Use | Existing function retained with the recorded qualification limits. |
| email-cliente | Use | Existing function retained with the recorded qualification limits. |
| esg-reporting-assurance | Unresolved | New evidence foundation; Swiss/Geneva applicability and professional use have not been assessed. |
| fatture-xml-check | Ignore for this target | Existing function retained with the recorded qualification limits. |
| financial-analysis | Use | Existing function retained with the recorded qualification limits. |
| financial-report-builder | Use | Existing function retained with the recorded qualification limits. |
| fusione-guidata | Unresolved | P0 preserves multi-company evidence and review history. All legal merger branches are unsupported; Swiss/Geneva professional fit and adaptations have not been assessed. |
| invoice-xml | Unresolved | Existing function retained with the recorded qualification limits. |
| journal-bank-reconciliation | Adapt | Reviewed French textual dates use additive adapter v8; currencies remain explicitly source-mapped. |
| journal-sampling | Adapt | Source-evidenced currency and Swiss export qualification instructions; no new sampling algorithm. |
| learn-with-vera | Use | Existing function retained with the recorded qualification limits. |
| legal-tax-answer-planner | Use | Existing function retained with the recorded qualification limits. |
| legal-tax-answer-review | Use | Existing function retained with the recorded qualification limits. |
| management-control-pack | Use | Existing function retained with the recorded qualification limits. |
| new-client | Adapt | Geneva source-bound setup adapter with identity, mandate, ownership, AML applicability, privacy-role and document-state review; Italian scoring excluded. |
| open-item-reconciliation | Adapt | Explicit currency guidance; raw Geneva runs reject omitted currency. Existing reconciliation method retained. |
| presenza-digitale-studio | Use | Existing function retained with the recorded qualification limits. |
| previdenza-inps | Adapt | Explicit Swiss institutional context for local contribution-evidence review; shared chronology/arithmetic pipeline and Geneva memo framing. INPS portal adapters remain Italy-specific. |
| privacy-surface-review | Use | Existing function retained with the recorded qualification limits. |
| purchase-invoice-review | Adapt | Reviewed Swiss document population adapter feeding the existing matching, arithmetic and semantic audit; exact source and extraction-review hashes checked. |
| quesito-legale-fiscale | Use | Existing function retained with the recorded qualification limits. |
| registro-imprese-sari | Adapt | Explicit CH-GE intake/plan, official Swiss source hosts, local authority/position handling and French labels; no portal filing. |
| sales-plan | Use | Existing function retained with the recorded qualification limits. |
| studio-archive | Adapt | Swiss IDE normalization and explicit OCR language through CLI/MCP; language changes trigger reindexing. |
| treasury-forecast | Adapt | CHF forecast/update arithmetic with currency-safe records and currency-correct HTML, Markdown, XLSX and live review. Fixed interface prose remains Italian. |
| variance-analysis | Use | Existing function retained with the recorded qualification limits. |
| vera | Use | Existing function retained with the recorded qualification limits. |
| vouching | Adapt | Supporting-PDF intake for Geneva without FatturaPA-first assumptions; source currency and lineage preserved. |

## Scope that remains unresolved

Centrale Rischi source equivalence, the restructuring mandate/procedure, the actual DATEV application and a Swiss structured-invoice output requirement remain unresolved. The Italian FatturaPA-only checker stays outside the domestic example, while remaining available for actual Italian files. No replacement services were invented.

The 0.1.279 catalogue refresh adds `fusione-guidata` and updates its router entry. It preserves the existing professional assessments. The new foundation is unresolved for Geneva; its synthetic structural checks do not establish Swiss merger capability.

## Acceptance record

The repository tests exercise CHF Treasury figures and generated currency labels, French Business Planning reports, reviewed French date parsing, Swiss IDE/OCR handling, source-bound annual accounts and onboarding, and rejection of altered sources or inappropriate jurisdiction/currency combinations. The release validation records exact commands and results. Synthetic examples are not legal validation or field acceptance.

## Official starting sources

These sources support the target investigation, not an automatic rules engine. Recheck effective dates, entity scope and mandate applicability in the actual case.

- [Swiss accounting obligations (SECO)](https://www.kmu.admin.ch/fr/comptabilite-obligatoire-lobligation-de-tenir-une-comptabilite)
- [Swiss Code of Obligations (Fedlex)](https://www.fedlex.admin.ch/eli/cc/27/317_321_377/fr)
- [Geneva registry documentation and forms](https://www.ge.ch/document/registre-du-commerce-documentation-formulaires)
- [FINMA AML legal framework](https://www.finma.ch/fr/documentation/bases-legales/lois-et-ordonnances/loi-sur-le-blanchiment-d-argent/)
- [OCAS contribution records](https://www.ocas.ch/en/node/143)
- [Geneva FAE support](https://www.ge.ch/dossier/developpement-economique-recherche-innovation/dispositif-cantonal-soutien-aux-entreprises/fondation-aide-aux-entreprises-fae)
- [Swiss enterprise identifier (AFC)](https://www.estv.admin.ch/fr/numero-identification-des-entreprises-ide)
- [PFPDT outsourcing and processing roles](https://www.edoeb.admin.ch/fr/externalisation-sous-traitance)

See [the complete machine-readable assessment](assessment.json) for each function’s purpose, common method, original adaptation requirement, acceptance example and source references.

## ESG catalogue update — 29 September 2026

Vera 0.1.282 adds the ESG evidence foundation to the catalogue. The earlier
35-function assessment is preserved; the new function is recorded as unresolved.
Its synthetic evidence/version tests do not establish Swiss reporting support.
The combined catalogue now contains 37 function entries and four internal helpers, including the separate unresolved merger foundation from main.

The subsequent combined catalogue also includes the synthetic-only transformation
prototype, separately unresolved for Geneva. There are 42 skill entries in total.
