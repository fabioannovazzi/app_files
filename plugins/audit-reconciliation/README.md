# Riconciliazione partite

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/audit-reconciliation) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Plugin Codex per riconciliare partite aperte, mastrini, evidenze bancarie, distinte, factoring/anticipi e compensazioni in workpaper Excel/Word rivedibili.

Questo non è un applicativo standalone: è un workflow Codex. Gli script del plugin fanno normalizzazione, matching e controlli deterministici; Codex guida il primo run, usa quei risultati per rivedere campioni, individuare anomalie, chiedere evidenze mancanti e spiegare i limiti dell'analisi.

## Cosa fa

- importa partite aperte o liste contestate;
- importa mastrini, libro giornale, estratti conto, distinte di pagamento, supporti factoring/anticipi e compensazioni;
- classifica ogni riga con regole deterministiche e riferimenti documentali;
- distingue evidenza forte, compensazione documentata, bridge documentale, sola evidenza interna e righe da verificare;
- confronta saldi iniziali/finali dei mastrini con il roll-forward da giornale quando i dati sono disponibili;
- segnala evidenze successive al cut-off che possono spiegare chiusure avvenute dopo la data di riferimento;
- costruisce aging, concentrazione per evidenza, mappa documento-fonti, possibili storni/compensazioni e movimenti vicino al cut-off;
- genera un pacchetto di review Codex con righe ad alto valore, righe con evidenza obbligatoria e campione stabile;
- prepara un piccolo campione operativo di righe da far verificare a un revisore;
- prepara richieste mirate di evidenza mancante, distinguendo cio che e gia nel fascicolo dal tassello che serve per chiudere o confermare aperta una riga;
- produce un workbook Excel auditabile, una scheda operativa per commercialista, una relazione Word e file JSON auditabili con le estrazioni usate.

## Input tipici

- liste partite aperte o allegati di controparte;
- mastrini clienti/fornitori e mastrini banca;
- libro giornale;
- estratti conto bancari ufficiali o esportazioni banca;
- distinte di pagamento o remittance batch;
- evidenze factoring, anticipo fatture o operatori di incasso;
- accordi o supporti di compensazione.

I file possono essere PDF, Excel, CSV o ZIP. I PDF testuali vengono letti direttamente; i PDF scansionati possono usare OCR se le dipendenze opzionali sono installate.

## Primo prompt

```text
Usa il plugin Riconciliazione partite sulla cartella /percorso/lavoro/input.
Periodo 2025, cut-off 31/12/2025.
Lingua: it.
Chiedimi le assunzioni mancanti e prepara Excel/Word con dettaglio righe, evidenze, review Codex e punti da verificare.
```

Assunzioni da chiarire quando non sono ovvie:

- quale file contiene la popolazione da riconciliare;
- se gli eventi dopo il cut-off sono esclusi;
- se una distinta di pagamento è solo documento ponte o prova sufficiente;
- se l'utente vuole un trattamento factoring/anticipo più restrittivo del default;
- se la compensazione richiede banca o basta supporto contabile/documentale.

Default factoring/anticipo: se un riferimento factor/operatore o pro-soluto è
collegato in modo deterministico a un pagamento presente negli estratti conto
bancari forniti, il plugin lo tratta come evidenza di chiusura. Non fare un
secondo run conservativo solo perché l'utente non ha confermato esplicitamente
questo default; chiedi solo se vuole rendere factoring/anticipo non chiudente o
se il collegamento alla banca è ambiguo.

## Primo run beta

Per un primo lavoro completo, Codex deve raccogliere e confermare questi elementi prima di lanciare gli helper:

- cartella input con partite aperte, mastrini, banche, distinte, factoring/anticipi e compensazioni disponibili;
- periodo e cut-off della riconciliazione;
- file che contiene la popolazione da riconciliare;
- lingua operativa e lingua dei documenti (`it`, `en`, `fr`, `de` o `auto` per documenti misti);
- assunzioni sulle evidenze: eventi post cut-off, valore probatorio delle distinte, eventuale trattamento factoring/anticipo più restrittivo del default e compensazione;
- controllo dipendenze con `python scripts/check_dependencies.py`;
- output attesi: Excel audit, scheda operativa per commercialista, Word, `source_pages.json`, `run_intake.json`, `review_payload.json`, `ui_decisions.json`, `final_artifacts.json`, `artifact_card.md`, `review_ui.html`, review Codex e, se utile, richieste mirate di evidenza;
- passaggio di review: controllare eccezioni, righe ad alto valore, evidenze obbligatorie e righe non chiuse.

Lingue supportate per etichette e testi di output: italiano (`it`), inglese (`en`), francese (`fr`) e tedesco (`de`).

## Review browser locale e UI MCP

Il plugin espone un server MCP locale dichiarato in `.mcp.json`.

- `validate_audit_reconciliation_review` valida `review_payload.json` prima della resa.
- `render_audit_reconciliation_review` apre il widget MCP `ui://widget/audit-reconciliation-review.html` tramite `openai/outputTemplate`, utile come superficie integrata Codex opzionale.
- `scripts/review_server.py` apre la review primaria nel browser locale su `127.0.0.1` e persiste le decisioni nella cartella output.
- Il widget mostra righe da rivedere, controlli falliti, righe `needs_evidence` / `unresolved`, pagamenti probabili, workbook e report generati.
- Le decisioni finali vanno conservate in `ui_decisions.json`; l'applicazione scrive anche `applied_decisions.json` e aggiorna `final_artifacts.json`.

Il passaggio di handoff primario è il browser locale: dopo ogni run normale Codex deve indicare `artifact_card.md`, avviare `python scripts/review_server.py <cartella-output>`, comunicare esplicitamente l'URL `localhost` aperto e spiegare che i pulsanti della pagina scrivono i JSON nella cartella output. Questo passaggio va eseguito prima della risposta finale; non è sufficiente lasciare un file o un widget nascosto.

La sequenza `validate_audit_reconciliation_review` -> `render_audit_reconciliation_review` resta disponibile quando serve una superficie integrata in Codex, ma non sostituisce il browser locale come handoff normale. Per run grandi, i tool MCP possono ricevere `run_intake_path`, `review_payload_path`, `ui_decisions_path` e `final_artifacts_path` invece dei JSON inline; il server legge solo file coerenti con la cartella output del run. Se il server browser non parte o il browser non può essere aperto, Codex deve dirlo esplicitamente e aprire `review_ui.html` dalla cartella output come fallback statico; quel fallback può copiare/scaricare JSON ma non persiste automaticamente. Se anche quel file non è disponibile, usare `review_payload.json`, `codex_review_packet.json` e il workbook come fallback markdown/statico. Le piccole scelte iniziali restano in chat o, quando disponibile, nei controlli nativi di Plan mode: non serve una pagina HTML dedicata per 2-3 opzioni.

## Diagnostica run

`run_intake.json` aggiorna automaticamente il campo `dependency_check` quando viene scritto: stato, timestamp, file requisiti controllati e pacchetti mancanti vengono conservati nel pacchetto audit. Quando le assunzioni indicano OCR o PDF scansionati, il controllo include anche `requirements-ocr.txt`.

Per PDF lunghi, usare `verbose_extraction` e, se serve, `pdf_progress_every_pages` nelle assunzioni del run. L'estrazione emette messaggi di start file, avanzamento pagina, OCR pagina, cache hit e fine file, così è visibile quale PDF sta richiedendo tempo.

## Prompt di avvio per beta user

### Riconciliazione completa

```text
Usa il plugin Riconciliazione partite sulla cartella /percorso/lavoro/input.
Periodo 2025, cut-off 31/12/2025.
Lingua: it.
Chiedimi prima del run il file popolazione, le assunzioni sulle evidenze e ogni dato mancante.
Prepara Excel/Word con dettaglio righe, evidenze citate, review Codex e punti da verificare.
```

### Mastrino contro banca/evidenze

```text
Usa Riconciliazione partite per confrontare mastrino, banca e supporti esterni nella cartella /percorso/lavoro/input.
Periodo 2025, cut-off 31/12/2025.
Evidenzia movimenti supportati da banca, distinte, factoring o compensazioni e separa le righe con sola evidenza interna.
```

### Richieste evidenze mancanti

```text
Partendo dal workbook di riconciliazione già prodotto, genera il pacchetto richieste evidenze mancanti.
Usa wording operativo in italiano e distingui cosa è già disponibile dal tassello che serve per chiudere o confermare aperta ogni riga.
```

### Campione per revisore o cliente

```text
Partendo dal workbook di riconciliazione, crea un campione operativo di righe da controllare con revisore o cliente.
Includi righe collegate, domande di verifica e criteri di scelta senza esporre codici tecnici del motore.
```

### Evidenze post cut-off

```text
Usa Riconciliazione partite per analizzare le evidenze successive al cut-off.
Segnala i candidati che spiegano chiusure successive, ma non usarli per chiudere righe alla data di cut-off se gli eventi post cut-off sono esclusi.
```

## Regola di sviluppo

La sorgente modificabile è solo:

```text
plugins/audit-reconciliation
```

Cartelle scaricate, cache Codex e ZIP sono artefatti generati. Dopo modifiche alla sorgente, ricostruire il pacchetto con:

```bash
.venv/bin/python scripts/build_codex_plugin_zip.py audit-reconciliation
.venv/bin/python scripts/build_codex_plugin_zip.py audit-reconciliation --check
.venv/bin/python -m pytest tests/plugins/test_codex_plugin_packages.py
```

## Controllo dipendenze

Il plugin include:

```text
requirements.txt
requirements-ocr.txt
scripts/check_dependencies.py
```

Prima di usare gli helper, Codex deve controllare le dipendenze dal folder del plugin:

```bash
python scripts/check_dependencies.py
```

Se servono PDF scansionati/OCR:

```bash
python scripts/check_dependencies.py --requirements requirements-ocr.txt
```

Se manca qualcosa, Codex deve installare le dipendenze dichiarate quando possibile; se non può installarle, deve spiegare chiaramente all'utente che manca un componente necessario e quale autorizzazione serve.

## Output di estrazione

Ogni run deve conservare nel folder di output il testo pagina-per-pagina usato per la normalizzazione:

```text
source_pages.json
```

Il file include nome sorgente, pagina, metodo di estrazione (`pdf_text` o `paddle_ocr`), lunghezza testo, numero righe e testo estratto. La cache resta utile per non rifare OCR, ma `source_pages.json` è il riferimento auditabile del singolo run.

## Controlli deterministici

Quando sono disponibili mastrini e giornale, il workbook include:

- `Account rollforward check`: confronto tra saldo iniziale da mastro,
  movimenti netti da giornale, saldo ricostruito e saldo finale da mastro;
- `Journal rollforward`: riepilogo dei movimenti da giornale usati per il
  controllo;
- `Journal detail`: dettaglio delle righe giornale filtrate;
- `Post-cutoff candidates`: evidenze successive al cut-off che possono spiegare
  una chiusura successiva, senza usarle per chiudere la riga al cut-off.
- `Open item aging`: aging deterministico delle partite per fasce temporali;
- `Evidence concentration`: concentrazione dell'importo per tipo di evidenza;
- `Review signals`: righe prioritarie per importo, anzianità ed evidenza debole;
- `Document source map`: presenza di ciascun documento in partite aperte,
  mastro, giornale, banca, distinte, factor e compensazioni;
- `Reversal candidates`: possibili storni, giroconti, rettifiche o compensazioni
  da verificare;
- `Cutoff window movements`: movimenti entro la finestra configurata intorno al
  cut-off.

La relazione Word include una sintesi di questi controlli quando sono presenti:
esito del confronto mastro/giornale, principali differenze, candidati post
cut-off e tabelle compatte delle analisi aggiuntive. Il dettaglio completo resta
nel workbook Excel e nei JSON.

## Campione di controllo

Dopo aver generato il workbook di riconciliazione, puoi creare un campione di
righe da controllare manualmente:

```bash
python scripts/build_review_sample.py <output-dir>/riconciliazione_audit.xlsx --count 2
```

Lo script produce:

- `campione_movimenti_da_controllare.xlsx`: righe selezionate, righe collegate,
  domande e criteri di scelta;
- `testo_richiesta_controllo.md`: bozza in italiano operativo per chiedere il
  controllo, senza codici tecnici del motore.

## Richieste mirate di evidenza

Dopo il run, il plugin puo produrre un workbook che non richiede di rimandare
tutto il fascicolo: per ogni riga indica cosa e gia disponibile e quale tassello
manca davvero.

```bash
python scripts/build_missing_evidence_requests.py <output-dir>/riconciliazione_audit.xlsx \
  --entity-name "Societa revisionata" \
  --counterparty-name "Controparte" \
  --cutoff-date 2023-12-31 \
  --language it
```

Lo script produce `richieste_mirate_evidenze.xlsx` con categorie operative
localizzate (`it`, `fr`, `de`, `en`): righe gia riconciliate con evidenza
forte, pagamenti probabili da allocare, scritture contabili da supportare,
evidenze da integrare, saldi aperti da confermare e righe non risolte. I codici
tecnici restano nel workpaper auditabile, non nella richiesta operativa.

## Installazione locale in Codex

Il pacchetto ZIP e gia organizzato per Codex. Dopo averlo decompresso, in
`Add marketplace` usa come `Source` la cartella estratta:

```text
.../riconciliazione-partite-codex-plugin
```

Quella cartella contiene:

```text
.agents/
  plugins/
    marketplace.json
plugins/
  audit-reconciliation/
    .codex-plugin/
      plugin.json
```

`marketplace.json` e dentro `.agents/plugins` e punta al plugin con:

```json
"path": "./plugins/audit-reconciliation"
```

Il percorso e relativo alla cartella principale del marketplace, quindi in
`Add marketplace` va selezionata la cartella estratta che contiene sia
`.agents` sia `plugins`.

## Dipendenze

Installa le dipendenze base se vuoi usare gli script locali del plugin:

```bash
pip install -r requirements.txt
```

Per PDF scansionati o immagini, l'OCR e opzionale:

```bash
pip install -r requirements-ocr.txt
```
