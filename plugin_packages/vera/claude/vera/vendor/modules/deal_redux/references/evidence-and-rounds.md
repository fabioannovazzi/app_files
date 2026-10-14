> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Prove, contabilità delle revisioni e ripresa

L'adattatore risolve `<helper-dir>`, il root del prodotto e l'output autorizzato.
Controlla le dipendenze dichiarate e usa l'ambiente Python condiviso del prodotto.
Il helper riusa `legal_documents.py`, `legal_docx.py`, jsonschema, lxml e openpyxl;
non installa pacchetti né crea un ambiente dentro la pratica.

Per un solo Word crea un evidence pack `revisione-documentale`, oppure riusa
quello già preparato per revisione o confronto. `prepare` richiede una nuova
directory: scegli una nuova sottocartella se il contenitore esiste. In Archive
usa una sottocartella dell'output della run autorizzata, non il contenitore
già creato. Per nuove prove dopo una run completata/sigillata crea una run
successiva, con originali e review precedente selezionati come input/upstream;
non modificare la run sigillata.

```bash
python <helper-dir>/legal_documents.py prepare --run-dir <run> --workflow revisione-documentale --file <revisionato.docx> --topic "Posizioni negoziali"
python <helper-dir>/legal_negotiation.py scaffold --run-dir <run> --source <source-id>
```

Gli ID provengono da `evidence.json`: non scegliere l'ultima fonte dal filename.
`negotiation-inventory.json` conserva gli ID di ogni unità tracciata, tipo,
posizione XML, contesto precedente/proposto, proprietà, autori/date e commenti.
`negotiation-inventory.sha256` e gli originali vengono ricontrollati contro
l'estrazione attuale. La scansione riguarda i componenti XML Word del DOCX;
oggetti incorporati e layout richiedono l'originale e verifica visiva. Elementi
di revisione non riconosciuti e contenuti non estratti restano limiti espliciti.
Il registro conta unità di markup, non scelte negoziali o correttezza delle fonti.

Leggi `legal_negotiation.schema.json` accanto al helper e compila
`negotiation.json` con il modello:
- `context`: parte, rapporto, legge/foro, istruzioni, fonti e lingua, come nel
  contratto di review documentale. Scrivi incognite motivate quando necessario.
- `positions`: ID, titolo, `effect`, `grouping_reason`, `change_ids`,
  citazioni `source_id/anchor/quote` e `response`. Le citazioni devono appartenere
  al testo della fonte selezionata; il loro riscontro non decide supporto giuridico.
  L'ordine dei record è l'ordine professionale deciso dal modello.
- `other_changes`: ciascun ID non assegnato a una posizione con un motivo
  specifico. Nessuna categoria Word viene esclusa automaticamente.
- `comment_reviews`: ogni ID di commento una sola volta, analisi e posizioni
  eventualmente collegate. Mantieni anche commenti privi di ancora.
- `response_mode: blank` e risposte vuote ordinariamente; soltanto per una
  richiesta dell'utente usa `user_requested` e registra `response_request`.
- `original_inspected`, `visual_review` con file/pagine realmente verificati,
  e `limitations`: dichiarazioni della review, non osservazione del modello.

Per un round successivo seleziona lo snapshot consegnato precedente:
```bash
python <helper-dir>/legal_negotiation.py scaffold --run-dir <nuova-run> --source <source-id> --previous-review <precedente-run>/negotiation-reviewed.json
```
Il helper conserva `negotiation-prior.json` e il suo hash. Non certifica le fonti
o l'approvazione del record importato: verifica la provenienza nel caso. Compila
`round_comparison` con ID precedenti e attuali, stato motivato e analisi. Ogni
posizione precedente e attuale deve comparire una volta; gruppi molti-a-uno o
uno-a-molti sono ammessi. La corrispondenza è semantica, non scelta dal codice.

```bash
python <helper-dir>/legal_negotiation.py render --run-dir <run> --review <run>/negotiation.json --product <Vera-or-Lucia>
python <helper-dir>/legal_negotiation.py verify --run-dir <run>
```

La validazione controlla forma, ID, fonti/citazioni, assegnazioni esatte e
coerenza dichiarata. Originale o inventario alterati, ID omessi/ripetuti/estranei,
commenti omessi e citazioni non riscontrate impediscono il render. Una verifica
visiva pendente resta visibile: zero unità non assegnate non completa la review.

Ogni render conserva gli output precedenti in `previous-*`, crea HTML/XLSX/CSV,
`negotiation-reviewed.json` con l'esatta review consegnata e la ricevuta dei
loro hash. Un rerender fallito ritira gli output precedenti dai nomi correnti;
non consegnarli come attuali. Prima di dichiarare consegnato il pacchetto, usa
`verify`, leggi gli output e controlla i conteggi. Mantieni versioni e prove.
