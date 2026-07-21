# Client Onboarding

Componente Vera per preparare un dossier di onboarding cliente tracciabile e
rivedibile. Non replica una singola applicazione: trasforma l'idea di un flusso
complesso, spesso rimandato dagli studi, in un percorso locale con evidenze,
fonti, decisioni professionali e artefatti verificabili.

## Cosa fa

- verifica e lega un run `client-intake` effettivamente `final_ready`, oppure
  registra in modo esplicito che il caso parte da evidenze autonome senza
  descriverle come già revisionate da Client Intake;
- mantiene separati codice fiscale e partita IVA e supporta più esecutori e
  titolari effettivi;
- registra scopo, natura, servizi e condizioni dell'incarico inserite dallo
  studio;
- calcola in modo deterministico il rischio AML solo dopo che gli input
  semantici sono stati proposti, mostrando formula, versione e blocchi;
- controlla la copertura PEP, sanzioni e Paesi per ogni soggetto rilevante,
  senza eseguire screening o interpretarne automaticamente l'esito;
- struttura finalità, ruolo privacy, base giuridica e conservazione, mantenendo
  il marketing in un record separato dal rapporto professionale;
- prepara una matrice di applicabilità per mandato, privacy, informativa AI,
  art. 28 e modulistica AML senza copiare modelli di terzi;
- verifica l'integrità del riferimento e la coerenza dei metadati dichiarati
  per hash, approvazione, riuso, lingua e date; non prova diritti di riuso o
  validità legale e produce soltanto un piano documentale;
- genera memo, richieste documentali, piano di monitoraggio e una sessione di
  review persistente con un gate di esportazione non cancellabile dalla review.

## Cosa non fa

Non consiglia prezzi, non decide l'applicabilità normativa da parole chiave,
non effettua screening esterni, non genera documenti legali pronti per il
cliente, non firma, non invia e non attiva il rapporto. Può preparare una bozza
interna di richiesta informazioni da personalizzare. Lo stato massimo è
`ready_for_professional_export`: indica soltanto che il dossier interno corrente
può essere esportato per il lavoro del professionista; non equivale a cliente
accettato, fascicolo conforme o completo, né a documenti pronti o sottoscritti.

## Avvio locale

Dal root del componente:

```bash
python scripts/check_dependencies.py
python scripts/initialize_case.py --help
python scripts/package_onboarding.py --help
```

Gli output di casi reali devono essere scritti fuori dal repository in una
cartella privata. Il workflow produce almeno `run_intake.json`,
`review_payload.json`, `ui_decisions.json`, `review_handoff.md` e
`final_artifacts.json`, insieme agli artefatti di dominio.

## Revisione

La review usa i tool MCP:

1. `validate_client_onboarding_review`
2. `render_client_onboarding_review`
3. `save_client_onboarding_decisions`
4. `apply_client_onboarding_decisions`

Le decisioni vengono registrate in `ui_decisions.json` e applicate in
`applied_decisions.json`; gli artefatti di origine non vengono modificati in
silenzio. Per sbloccare l'export professionale, `apply` deve registrare nel
campo `reviewer` un riferimento pseudonimo e stabile del professionista dello
studio; nome, email e altri identificativi diretti restano fuori dal payload di
review.

## Fonti e testi

Il registro fonti distribuito contiene soltanto le fonti normative e
professionali usate dal workflow ed è un punto di partenza versionato, non un
servizio di aggiornamento normativo. Il materiale di Francesco, il sito
MandatoProfessionale e il listino ANC restano separati in
`references/research-provenance.json` come ispirazione non runtime: non sono
autorità, tariffari o librerie di clausole del componente.

Prima di una pratica reale, Codex e il professionista devono verificare le fonti
correnti e l'applicabilità al caso. I testi utilizzabili dal cliente restano nei
sistemi approvati dello studio. Client Onboarding registra e controlla soltanto
il riferimento al template; non ne copia, fonde o sostituisce i placeholder.
