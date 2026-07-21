# New Client

New Client è l'unico percorso Vera per aprire un nuovo rapporto professionale:
parte dai documenti ricevuti, organizza le informazioni del cliente e prepara
un dossier rivedibile per lo studio.

## Percorso

New Client coordina cinque momenti dello stesso lavoro:

1. prepara il fascicolo e rende leggibili le evidenze in ingresso;
2. struttura anagrafica, soggetti rilevanti e dati verificati;
3. registra servizi, condizioni dell'incarico e scelte privacy;
4. raccoglie fattori, fonti ed esiti necessari alla valutazione AML;
5. porta memo, richieste e piano di monitoraggio in una review persistente.

La preparazione documentale è una fase interna del percorso. Può collegarsi a
un run `client-file-preparation` già `final_ready` oppure partire da evidenze
autonome, registrandone in modo esplicito origine e stato di revisione.

## Risultati

Il workflow:

- mantiene distinti codice fiscale e partita IVA;
- supporta persone fisiche, ditte, società ed enti, con esecutori,
  rappresentanti e titolari effettivi multipli;
- registra scopo, natura, servizi e condizioni dell'incarico indicati dallo
  studio;
- applica la formula AML versionata ai fattori confermati e conserva basi,
  eventuali blocchi e storico delle revisioni;
- associa a ogni soggetto gli esiti PEP, sanzioni e Paesi forniti dallo studio,
  insieme a fonte, data ed evidenza;
- struttura finalità, ruoli privacy, basi giuridiche e conservazione, con il
  consenso marketing in un record separato;
- costruisce la matrice di applicabilità per incarico, privacy, informativa AI,
  art. 28 e modulistica AML usando riferimenti a template approvati dallo
  studio;
- produce memo, richieste documentali, piano di monitoraggio e artefatti di
  review tracciabili.

Lo stato `ready_for_professional_export` identifica un dossier interno pronto
per il passaggio professionale. Le azioni successive restano nei processi e nei
sistemi approvati dello studio.

## Avvio locale

Dal root del componente:

```bash
python scripts/check_dependencies.py
python scripts/initialize_case.py --help
python scripts/package_new_client.py --help
```

Gli output di casi reali vanno scritti fuori dal repository, in una cartella
privata. Il workflow produce almeno `run_intake.json`, `review_payload.json`,
`ui_decisions.json`, `review_handoff.md` e `final_artifacts.json`, insieme agli
artefatti di dominio.

## Revisione

La review usa i tool MCP:

1. `validate_new_client_review`
2. `render_new_client_review`
3. `save_new_client_decisions`
4. `apply_new_client_decisions`

Le decisioni vengono registrate in `ui_decisions.json` e applicate in
`applied_decisions.json`; gli artefatti di origine restano immutati. Per
sbloccare l'export professionale, `apply` registra nel campo `reviewer` un
riferimento pseudonimo e stabile del professionista dello studio. Nome, email e
altri identificativi diretti restano fuori dal payload di review.

## Fonti e template

`references/source-registry.json` contiene le fonti normative e professionali
versionate usate dal workflow. È una base di ricerca verificabile: prima di una
pratica reale, Codex e il professionista verificano versione corrente e
applicabilità al caso.

`references/research-provenance.json` conserva separatamente la provenienza dei
materiali esterni valutati durante la progettazione. Sono record non-runtime e
non entrano nell'autorità, nella logica tariffaria o nelle fonti mostrate nel
fascicolo cliente.

I testi destinati al cliente restano nei sistemi approvati dello studio. New
Client registra il riferimento, l'hash, la versione e lo stato di approvazione
del template senza incorporarne il contenuto nel componente.
