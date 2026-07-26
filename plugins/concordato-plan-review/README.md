# Revisione Piano Concordato

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/concordato-plan-review) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Plugin Codex per il tie-out numerico e la review contabile di un piano di
concordato rispetto a bilancio provvisorio, mastrini, database rettificato e
dettagli di supporto.

Il plugin non sostituisce il giudizio del revisore. Gli script catturano e
inventariano le fonti, estraggono candidati numerici e, solo dopo una decisione
revisionata e legata alle fonti, trovano match meccanici per importo e preparano
workpaper rivedibili. Codex usa quei risultati per classificare differenze,
chiedere evidenze mancanti e scrivere un report sintetico sulle criticita.

## Cosa fa

- inventaria PDF e workbook forniti nel fascicolo;
- estrae testo pagina-per-pagina dai PDF testuali;
- ispeziona fogli Excel e celle numeriche rilevanti;
- propone ruoli delle fonti dai nomi file, senza renderli operativi;
- richiede la review del piano autorevole, del ruolo, della valuta e dell'unita
  di ogni fonte supportata;
- richiede una disposizione per ogni token numerico estratto, distinguendo un
  importo candidato da un numero non monetario;
- produce match deterministici per importo, con tolleranza configurabile, solo
  dopo questa review;
- prepara CSV, JSON, XLSX, Markdown e un Word riassuntivo per la review;
- distingue nel Word i numeri che battono per importo da quelli non trovati,
  senza chiamarli supporto semantico;
- prepara un payload MCP/HTML rivedibile con fonti, importi del piano,
  match candidati, importi non trovati, errori di estrazione e artifact finali;
- guida Codex nella distinzione tra dato storico, rettifica, riclassifica, assunzione prospettica e dato non supportato.

## Due passaggi obbligatori

Il primo passaggio e una ispezione in astensione: cattura i byte delle fonti e
produce `inventory.json`, `raw_amount_candidates.csv` e
`suggested_source_role_recipe.json`. I suggerimenti basati sul nome file non
classificano alcuna fonte e non producono importi o match operativi.

Codex o il revisore prepara poi un file decisioni che:

- assegna esattamente una fonte al ruolo `concordato_plan`;
- assegna a ogni fonte supportata ruolo, valuta e unita;
- assegna a ogni `candidate_id` la disposizione `candidate_amount` oppure
  `excluded_non_amount`;
- registra `reviewer_ref` e `reviewed_on`.

Lo script seguente lega queste decisioni alle ricevute delle fonti e crea la
recipe revisionata:

```bash
python scripts/review_source_roles.py /path/to/inspection \
  /path/to/source-role-decisions.json \
  --output /path/to/reviewed-source-role-recipe.json
```

Il secondo passaggio rilegge le stesse fonti con la recipe:

```bash
python scripts/run_concordato_review.py /path/to/input \
  --output-dir /path/to/reviewed-output \
  --reference-date 2026-03-31 \
  --language it \
  --document-language it \
  --tolerance 1 \
  --recipe /path/to/reviewed-source-role-recipe.json
```

Se i byte delle fonti, i candidati estratti, la recipe o gli artifact numerici
non corrispondono alle ricevute, la replay fallisce. Anche dopo l'applicazione
delle decisioni la consegna resta `final_ready=false`: il giudizio sulla
sufficienza del supporto e la pubblicazione sono separati. `reviewer_ref`
registra una dichiarazione locale; non autentica crittograficamente l'identita
del revisore.

La ricevuta di calcolo autorizza esclusivamente la formula fissa
`piano - supporto`, il valore assoluto della differenza e il confronto con la
tolleranza. Lega formula, convenzione del segno, periodo, fonti, ruoli, valuta,
unita, candidati e byte dell'implementazione. Una variazione richiede una nuova
review prima del parsing qualificato.

Prima di importare codice locale, ogni comando Python verifica il set fisico
esatto di 25 file di implementazione, configurazione, UI e assurance condivisa
e disabilita la bytecode locale. Anche il server MCP chiude lo stesso set prima
di leggere il manifest e avvia Python con import isolati e bytecode disabilitata.
File, directory, cache, link o file speciali non dichiarati bloccano
l'esecuzione. Queste ricevute provano coerenza e replay, non autenticano il
publisher del pacchetto o il professionista.

`numeric_evidence_ledger.json` riapre e verifica ogni indirizzo numerico
materiale reso in CSV, XLSX e DOCX. `workflow_output_closure.json` chiude invece
l'intero set di output con una allowlist esplicita e ricevute byte-per-byte:
file mancanti, inattesi, modificati, link simbolici o file speciali bloccano la
replay. Salvataggi e applicazioni di review producono una chiusura successiva
legata crittograficamente alla precedente prima di sostituire l'output
canonico.

Il dominio decimale canonico ammette al massimo 38 cifre significative e 18
decimali. I valori eccedenti sono rifiutati prima dell'emissione di righe
autorevoli; i calcoli usano un contesto locale e non dipendono dalla precisione
globale Python. La replay rigenera inoltre gli output immutabili dalle fonti e
dalle decisioni revisionate, quindi una narrativa alterata e semplicemente
ri-firmata non viene accettata. Le azioni del revisore restano input di
autorita, ma identita, azioni consentite e legame con `review_payload.json`
sono verificati; effetti, blocker, conteggi, stati, azioni successive e
`final_artifacts.json` vengono invece ricalcolati da tali input. Anche
`review_handoff.md` viene rigenerato e confrontato dopo save e apply.

Il contratto completo e descritto in
[`references/workflow-reference.md`](references/workflow-reference.md).

## UI review MCP

La review UI segue il pattern locale OpenAI-style usato dagli altri plugin
migrati:

- lo script Python produce i file deterministici consentiti dallo stato di
  review e
  aggiunge `run_intake.json`, `review_payload.json`, `ui_decisions.json` e
  `final_artifacts.json`;
- il server MCP locale dichiarato in `.mcp.json` espone
  `validate_concordato_plan_review` e `render_concordato_plan_review`;
- il widget HTML riusabile `assets/concordato-plan-review-widget.html` rende
  il payload con ricerca, filtri per tipo e dettaglio evidenza;
- prima di ogni scrittura di review, il server ripete localmente la verifica di
  payload, ricevute, ledger numerico, assurance envelope e chiusura completa
  degli output;
- se MCP non e disponibile, Codex legge `review_payload.json` e continua con
  Markdown/chat senza promuovere lo stato di assurance.

Per una replay indipendente:

```bash
python scripts/replay_assurance.py --output-dir /path/to/reviewed-output
```

I test sintetici e avversariali verificano il contratto meccanico, ma non
sostituiscono un holdout su un piano aziendale reale e mai visto, confrontato da
un revisore con un workpaper preparato indipendentemente.

## Primo prompt

```text
Usa Revisione Piano Concordato sulla cartella /percorso/fascicolo.
Data di riferimento: 31/03/2026.
Lingua: it.
Confronta piano CP, bilancio provvisorio, mastrini, DB rettificato e dettaglio debiti; genera tabulato differenze e criticita per revisore.
```

## Sorgente

La sorgente modificabile e solo:

```text
plugins/concordato-plan-review
```

Dopo modifiche alla sorgente, ricostruire e verificare il pacchetto:

```bash
.venv/bin/python scripts/build_codex_plugin_zip.py concordato-plan-review
.venv/bin/python scripts/build_codex_plugin_zip.py concordato-plan-review --check
.venv/bin/python -m pytest tests/plugins/test_concordato_plan_review_plugin.py tests/plugins/test_codex_plugin_packages.py
```
