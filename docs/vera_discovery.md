# Vera discovery: candidate and evaluation

This change improves the descriptions used to recognize professional requests.
It preserves Vera's identity, subtitle, keywords and professional approval
boundaries. It does not change accounting engines, native UI or MCP transport.

## Changes

- Listing description and three starter prompts use bank/first-note matching,
  OIC preparation and journal sampling as concrete entry points.
- Ten skill descriptions state the requested outcome, inputs, output and the
  nearest competing workflow. The router also accepts unnamed requests and
  clarifies ambiguous outcomes before execution.
- Marketplace starter/card copy follows the same distinctions. An obsolete
  mandatory-onboarding sentence is removed from the card; onboarding remains
  optional under the existing source contract.
- Three local MCP server descriptions identify **review of prepared results**,
  preserving the distinction from intake, extraction and calculation. Their
  individual tool schemas, annotations, resources and implementation are unchanged.
  The current public skills-only projection omits this native MCP registration;
  these local descriptions cannot change public tool selection in that package.

## Evidence and limits

Evaluation baseline: `484f85201f22f95055e45c577d4352ed96b5e293`.
Implementation rebased onto `a34681fb7023d6db8e82e720642f29e800d3518a` to
preserve the subsequently merged Patent Box course.
Observed on 1 October 2026 using Codex CLI 0.159.2, the host's default model,
read-only ephemeral runs, a supplied complete 46-entry skill-description
catalogue and the same 32 fictional requests. Expected labels and descriptive case IDs were withheld
from the evaluator; it received only opaque IDs C01-C32. An initial pilot
with descriptive IDs was repeated and is not used for the final counts. Full source files, engines and client documents were not
supplied. This is a **model metadata-matching experiment**, not an observed
installed-plugin invocation, task completion or public recommendation test.
The evaluator was explicitly asked to route requests; there were no competing
external catalogues, and the requests were evaluated together in one batch per
catalogue. This is a limited controlled check, not a statistically established
selection-rate estimate.

| Observed result | Before | Candidate |
| --- | --- | --- |
| Exact specialist on supported requests | 19/19 | 19/19 |
| Clarification on ambiguous requests | 5/5 | 5/5 |
| Unrelated code/pizza requests captured by Vera | 0/2 | 0/2 |
| Requested unsupported VAT filing or US GAAP certification promised | 0 | 0 |

Both catalogues respected the request to use Clara and declined autonomous OIC
approval/filing. For OCR-only bank statements, the baseline selected the
reconciliation route because its metadata did not exclude OCR, reserving input
quality checks; the candidate declined that input explicitly. Source requires a labelled text-PDF
table or reviewed CSV/XLSX, so the candidate explanation is more precise.
These boundary cases are reviewed semantically: do not treat their action labels
as an exact automated pass/fail score. The original corpus's suggested related
workflow for approval/filing is not permission to execute those operations.

**No recall improvement was observed in this set.** The baseline was already
correct on all supported cases. The source revision provides more explicit
inputs, outputs and exclusions; its real discovery impact remains unmeasured.

The public listing was visible at version 0.1.295 in a logged-out browser. The
plugin-search connector returned no matches for both `commercialista
riconciliazione bilancio` and the exact name `Vera`. Because the exact-name
lookup also returned nothing, this connector observation cannot establish a
ranking loss or absence from the public directory. No before-installation
conversational recommendation was observed.

A separate fresh installed-host intake test used enabled Vera 0.1.295 and an
unbranded bank/first-note request. The trace shows reads of the installed
`vera:journal-bank-reconciliation` skill and its component, followed by a request
for bank/journal files and an explicit statement that no data had been processed.
This establishes one actual implicit selection on the existing installation.
It does not test the uninstalled candidate, MCP execution, a reconciliation
artifact or public recommendations. Existing MCP startup warnings were present.

The [retained evaluation evidence](vera_discovery_evaluation.json) includes
exact responses, input/trace hashes, original expectations and the installed
intake trace summary. Raw local JSONL and prompts are also retained in the
implementation output folder.

## Repeatable acceptance

`plugins/vera/evals/discovery_cases.json` contains the requests, intended
workflow, inputs, useful output and boundary. It is a test specification, not
recorded model behavior. The existing explicit-invocation fixtures remain.

For a controlled replay, snapshot every Vera skill name/description before
editing; give the same requests without expected labels to separate fresh
model sessions before and after. Retain exact prompts, catalogue hashes, model
identity when available, host/version, raw response traces and semantic review.
Report missing model identity rather than infer it. Compare route and boundary
behavior; do not score keyword presence as observed selection.

For **installed-host acceptance**, use a fresh supported conversation with the
exact candidate installed, retain the host-exposed skill path/version, submit
unbranded requests with fictional files, and record the actual skill reads/tool
calls, arguments, clarification and resulting artifact or blocked state. Run
named controls and unsupported/ambiguous cases separately. Do not substitute a
source catalogue experiment or generated ZIP inspection for this gate.

For **public recommendations**, use genuine conversations before installation,
record account/client/locale, request, installed-plugin state and actual
suggestion. Evaluate Marketplace search separately on recorded queries. Neither
unpublished testing nor installed invocation proves ranking preservation or
improvement. No inherent conflict between accurate conversational metadata and
Marketplace matching was established.

Official references: [Optimize Metadata](https://developers.openai.com/plugins/guides/optimize-metadata)
and [review/distribution](https://developers.openai.com/plugins/deploy/app-review).
OpenAI describes relevant metadata as a tool-selection signal and enhanced
public distribution as selective; neither reference promises a Vera ranking.

## Release review

The data-boundary review covers the source diff: nine specialist wrappers only
change discovery descriptions; the root adds semantic intake guidance; three
native server labels change description only. No engine, payload builder, file
scope, recipient, permission or approval mechanism changes. Existing model
context classes, runtime profiles and external-boundary records are preserved.
Nine course records change source fingerprints only, with unchanged lessons.
The privacy review dates/fingerprints are refreshed to the inspected source.

## Catalogue-wide intent inventory

These source-owned starter intents and output labels map all source skill
cards, including internal review/teaching functions. They are inspected metadata,
not evidence that every workflow has completed a professional acceptance run.
Each workflow's full skill remains authoritative for supported inputs, host
requirements and output limitations. Only the 32-case corpus above was evaluated.

| Workflow | Ordinary request / materials | Intended output or bounded function |
| --- | --- | --- |
| [`adeguati-assetti`](../plugins/vera/skills/adeguati-assetti/SKILL.md) | Valutare gli assetti di questa impresa e preparare rilievi e un piano di miglioramento. | Esamina responsabilità, processi, reporting e funzionamento effettivo |
| [`adversarial-opinion`](../plugins/vera/skills/adversarial-opinion/SKILL.md) | Sviluppare la più solida posizione contraria a questo parere e confrontare le due conclusioni. | Sviluppa e verifica la posizione contraria |
| [`aml-review`](../plugins/vera/skills/aml-review/SKILL.md) | Esaminare queste evidenze e preparare la revisione antiriciclaggio del cliente. | Esamina titolarità, operazioni e variazioni del cliente |
| [`archive-organization`](../plugins/vera/skills/archive-organization/SKILL.md) | Analizzare questa cartella cliente, propormi il riordino e farmelo approvare prima di qualsiasi modifica. | Propone un nuovo ordine e sposta file solo dopo approvazione |
| [`avviso-intake`](../plugins/vera/skills/avviso-intake/SKILL.md) | Esaminare questo avviso fiscale e preparare una prima nota istruttoria con scadenze e documenti da recuperare. | Rileva scadenze, importi e documenti mancanti |
| [`bandi-agevolazioni`](../plugins/vera/skills/bandi-agevolazioni/SKILL.md) | Cercare opportunità compatibili con questo profilo e preparare il dossier della misura selezionata. | Scopre opportunità e prepara dossier per bandi agevolati |
| [`bilancio-oic`](../plugins/vera/skills/bilancio-oic/SKILL.md) | Preparare da questo bilancio di verifica i prospetti OIC, le informazioni mancanti per la nota integrativa e i controlli prima dell’export XBRL. | Prepara bilanci OIC revisionabili con esportazione XBRL |
| [`browser-automation`](../plugins/vera/skills/browser-automation/SKILL.md) | Usa $browser-automation nel mio Chrome autorizzato in modalità hybrid: ti mostro il percorso principale, esplora soltanto rami sicuri e prepara un developer pack sanitizzato e una capability verificabile. | Insegna, prova e corregge una procedura browser |
| [`business-planning`](../plugins/vera/skills/business-planning/SKILL.md) | Use $business-planning to assess this business, test its assumptions and develop a plan we can revise as evidence changes. Assess the proposed financing if relevant. | Develop and revise a business plan and assess financing |
| [`business-valuation`](../plugins/vera/skills/business-valuation/SKILL.md) | Preparare le carte di lavoro della valutazione di questa impresa, con fonti e ipotesi da rivedere. | Prepara metodi, calcoli e carte di lavoro da rivedere |
| [`centrale-rischi-review`](../plugins/vera/skills/centrale-rischi-review/SKILL.md) | Analizzare questo PDF ufficiale o export Centrale Rischi e preparare un pacchetto rivedibile. | Espone scadenze, garanzie, sconfinamenti e KPI |
| [`composizione-negoziata`](../plugins/vera/skills/composizione-negoziata/SKILL.md) | Esaminare questa pratica nel mio ruolo e preparare la prossima attività. | Guida la pratica e le revisioni |
| [`comunicazione-professionale`](../plugins/vera/skills/comunicazione-professionale/SKILL.md) | Valutare questa novità e preparare email, articolo web e grafica nel formato del mio studio, oppure concludere che non vale la pena pubblicare. | Scrive nel formato dello studio |
| [`concordato-plan-review`](../plugins/vera/skills/concordato-plan-review/SKILL.md) | Esaminare questo piano di concordato e preparare rilievi, prospetti e questioni aperte. | Controlla piano, trattamento e sostenibilità finanziaria |
| [`datev-invoice-start`](../plugins/vera/skills/datev-invoice-start/SKILL.md) | Provare DATEV Windows con la procedura fatture passive già predisposta, salvando risultati e punti da adattare. | Prova fatture passive su DATEV Windows |
| [`dati-fiscali-strutturati`](../plugins/vera/skills/dati-fiscali-strutturati/SKILL.md) | Estrarre e controllare i dati di questi documenti fiscali in una tabella revisionabile. | Estrae dati fiscali con fonte e livello di confidenza |
| [`email-cliente`](../plugins/vera/skills/email-cliente/SKILL.md) | Trasformare questa nota istruttoria e i documenti mancanti in una email chiara da rivedere prima dell'invio. | Trasforma i rilievi in richieste chiare al cliente |
| [`esg-reporting-assurance`](../plugins/vera/skills/esg-reporting-assurance/SKILL.md) | Organizzare le evidenze di questa pratica ESG e mostrarmi le decisioni da rivedere. | Organizza evidenze e decisioni ESG con versioni tracciabili |
| [`fatture-xml-check`](../plugins/vera/skills/fatture-xml-check/SKILL.md) | Controllare queste FatturePA XML e preparare il prospetto delle fatture e delle anomalie. | Controlla FatturePA, IVA, periodi e duplicati |
| [`financial-analysis`](../plugins/vera/skills/financial-analysis/SKILL.md) | Analizzare questi prospetti finanziari, controllare i calcoli e preparare risultati legati alle fonti. | Controlla prospetti, riconciliazioni e indicatori finanziari |
| [`financial-report-builder`](../plugins/vera/skills/financial-report-builder/SKILL.md) | Analizzare questo Excel e preparare un report finanziario controllato per il destinatario indicato. | Trasforma dati finanziari in un report controllato |
| [`fusione-guidata`](../plugins/vera/skills/fusione-guidata/SKILL.md) | Preparare una incorporazione OIC con evidenze, concambio, ponte contabile e calendario revisionabili. | Concambio, ponte contabile, calendario e dossier da revisionare |
| [`invoice-xml`](../plugins/vera/skills/invoice-xml/SKILL.md) | $invoice-xml Prepara una fattura XML da questi documenti e mostrami i dati da verificare prima di esportare. | Prepara XML da PDF e foto con revisione prima di esportare. |
| [`journal-bank-reconciliation`](../plugins/vera/skills/journal-bank-reconciliation/SKILL.md) | Riconciliare questi estratti conto con il giornale contabile e separare abbinamenti, residui ed eccezioni. | Abbina estratti conto e giornale contabile |
| [`journal-sampling`](../plugins/vera/skills/journal-sampling/SKILL.md) | Qualificare questo giornale contabile e produrre un campione riproducibile con tracciabilità. | Prepara un campione contabile riproducibile e tracciabile |
| [`learn-with-vera`](../plugins/vera/skills/learn-with-vera/SKILL.md) | Usa $learn-with-vera: mostrami a voce come funziona un controllo utile al mio lavoro, esegui un esempio nella seconda chat e poi proviamolo insieme. | Impara a voce con esempi eseguiti in due chat |
| [`legal-tax-answer-planner`](../plugins/vera/skills/legal-tax-answer-planner/SKILL.md) | Ottimizzare questa richiesta professionale in un piano di risposta con fonti e controlli espliciti. | Trasforma una richiesta professionale in un piano verificabile |
| [`legal-tax-answer-review`](../plugins/vera/skills/legal-tax-answer-review/SKILL.md) | Verificare questa risposta professionale contro le fonti e indicare ciò che va corretto o confermato. | Verifica affermazioni, fonti e ragionamento professionale |
| [`management-control-pack`](../plugins/vera/skills/management-control-pack/SKILL.md) | Trasformare questi export contabili in un pacchetto di controllo di gestione rivedibile. | Unisce P&L, Budget, aging, cassa e concentrazione |
| [`new-client`](../plugins/vera/skills/new-client/SKILL.md) | Organizzare i documenti iniziali di questo cliente e preparare il fascicolo di avvio con le evidenze mancanti. | Prepara il dossier iniziale e le decisioni da rivedere |
| [`open-item-reconciliation`](../plugins/vera/skills/open-item-reconciliation/SKILL.md) | Verificare quali partite dichiarate aperte al cut-off risultano chiuse, parziali o ancora aperte. | Verifica quali partite al cut-off sono ancora aperte |
| [`patent-box-review`](../plugins/vera/skills/patent-box-review/SKILL.md) | Esaminare i documenti selezionati e preparare controlli, costi e fascicolo Patent Box in bozza. | Prepara controlli e fascicolo Patent Box in bozza |
| [`presenza-digitale-studio`](../plugins/vera/skills/presenza-digitale-studio/SKILL.md) | Rinnovare il sito dello studio o crearne uno iniziale dai materiali verificati, con preview responsive da approvare. | Rinnova o crea il sito informativo dello studio |
| [`previdenza-inps`](../plugins/vera/skills/previdenza-inps/SKILL.md) | Esaminare questi documenti INPS e preparare una bozza istruttoria con calcoli e punti aperti. | Organizza provvedimenti, calcoli e punti aperti INPS |
| [`privacy-surface-review`](../plugins/vera/skills/privacy-surface-review/SKILL.md) | Verificare come questa modifica a Vera tratta dati, account, servizi esterni e conservazione. | Controlla dati, confini, account e conservazione |
| [`purchase-invoice-review`](../plugins/vera/skills/purchase-invoice-review/SKILL.md) | Confrontare queste fatture passive con la prima nota e preparare la carta di lavoro delle sole eccezioni. | Controlla fatture registrate e mostra solo le eccezioni |
| [`quesito-legale-fiscale`](../plugins/vera/skills/quesito-legale-fiscale/SKILL.md) | Rispondere a questo quesito legale o fiscale con fonti, ragionamento e limiti professionali verificati. | Prepara e verifica una risposta professionale completa |
| [`registro-imprese-sari`](../plugins/vera/skills/registro-imprese-sari/SKILL.md) | Impostare questa pratica societaria e indicare dati mancanti, verifiche e decisioni ancora aperte. | Prepara dati, verifiche e passaggi di una pratica societaria |
| [`sales-plan`](../plugins/vera/skills/sales-plan/SKILL.md) | Costruire un piano vendite da questi Actual mensili e da queste assunzioni commerciali. | Trasforma Actual e assunzioni in un piano vendite |
| [`scissione-guidata`](../plugins/vera/skills/scissione-guidata/SKILL.md) | Preparare il fascicolo di questa scissione e indicare evidenze e decisioni da rivedere. | Fascicolo, decisioni e prospetti di scissione. |
| [`studio-archive`](../plugins/vera/skills/studio-archive/SKILL.md) | Archiviare questo lavoro nel fascicolo cliente e cercare le evidenze nei file, in Gmail o in una chat WhatsApp verificata. | Salva il lavoro nel fascicolo e ritrova le evidenze senza modificare i documenti |
| [`trasformazione`](../plugins/vera/skills/trasformazione/SKILL.md) | Dimostrare un dossier societario sintetico con evidenze, revisione e riapertura delle decisioni. | Rivedi un dossier su dati sintetici |
| [`treasury-forecast`](../plugins/vera/skills/treasury-forecast/SKILL.md) | Preparare il budget di tesoreria da queste tabelle e rivedere date, ipotesi e variazioni. | Aggiorna incassi, pagamenti e saldi previsti |
| [`variance-analysis`](../plugins/vera/skills/variance-analysis/SKILL.md) | Riconciliare questi dati contabili e preparare un’analisi degli scostamenti con tabelle e grafici di varianza. | Confronta Actual, Budget, Forecast o periodi con grafici |
| [`vera`](../plugins/vera/skills/vera/SKILL.md) | Esaminare questi documenti, scegliere il controllo appropriato e preparare una carta di lavoro revisionabile. | Organizza controlli e pratiche contabili |
| [`vouching`](../plugins/vera/skills/vouching/SKILL.md) | Confrontare queste scritture campionate con le fatture e segnalare anomalie o documenti mancanti. | Confronta scritture campionate e documenti di supporto |
