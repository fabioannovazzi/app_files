# New Client — motore di preparazione del fascicolo

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/client-file-preparation) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Questa cartella contiene il motore interno che Vera usa nella prima fase di
**New Client**. Non è un prodotto o un percorso da presentare separatamente:
l'utente avvia New Client e Vera coordina sia la preparazione dei documenti sia
le fasi successive del nuovo rapporto professionale.

Il motore trasforma una cartella cliente in evidenze strutturate e rivedibili:
inventario, estrazioni locali, controlli formali, dati fiscali, memo operativo e
bozza di richiesta al cliente. Copre fascicoli Italia, Ginevra, Zurigo e Regno
Unito; eventuali regole normative dipendono dai rule pack del percorso New
Client, non da questo layer documentale.

## Posizione nel percorso New Client

```text
New Client
  preparazione del fascicolo (questo motore)
  anagrafica e soggetti rilevanti
  incarico, privacy e informativa AI
  valutazione AML e documenti applicabili
  review, export professionale e monitoraggio
```

La richiesta utente resta unica:

```text
Usa New Client per preparare il fascicolo nella cartella
/percorso/cartella-cliente. Anno target 2025. Porta il caso fino alla review
dello studio.
```

Vera deduce giurisdizione, presenza di scansioni e cartella di output quando le
evidenze lo permettono; chiede soltanto le decisioni materiali non ricavabili.

## Come lavora il motore

1. controlla dipendenze, accessibilità dei file e disponibilità OCR;
2. crea inventario e classificazione prudente dei documenti;
3. estrae testo, campi fiscali leggibili e dati FatturaPA XML;
4. segnala duplicati, file incerti, anomalie formali e possibili mancanze;
5. produce il payload di review e le prime bozze operative;
6. Vera legge le evidenze, raccoglie le decisioni e prosegue nello stesso
   percorso New Client.

Le estrazioni deterministiche conservano fonte e limite di lettura. La review
Codex distingue sempre classificazioni basate sul nome file, contenuto
effettivamente estratto e materiale non leggibile.

## Contratto di review

Gli script producono:

- `run_intake.json` con input, assunzioni e postura dati;
- `review_payload.json` con inventario, eccezioni e bozze;
- `ui_decisions.json` con le decisioni raccolte;
- `applied_decisions.json` con le decisioni applicate;
- `final_artifacts.json` con stato e artefatti finali.

Il server MCP espone i tool interni:

```text
validate_client_file_preparation_review
render_client_file_preparation_review
save_client_file_preparation_decisions
apply_client_file_preparation_decisions
```

Il widget usa `ui://widget/client-file-preparation-review.html`. Se il server
MCP non è disponibile, Vera può svolgere la stessa review in Markdown/chat, ma
mantiene le decisioni pendenti finché non vengono registrate e applicate.

## Copertura documentale

- PDF testuali e immagini, con OCR locale opzionale;
- CU, F24, 730 e Redditi PF leggibili;
- FatturaPA XML, riepiloghi IVA, potenziali duplicati e anomalie formali;
- avvisi e comunicazioni presenti nel fascicolo;
- documenti fiscali di Ginevra e Zurigo;
- Self Assessment, HMRC notices, P60, P45, P11D e altri documenti fiscali UK;
- campi strutturati con fonte, valore, snippet, confidenza e warning.

## Output principali

```text
00_environment_check.md
00_fascicolo_index.md
01_document_inventory.csv
02_documenti_mancanti_o_incerti.md
03_domande_interne_studio.md
04_bozza_email_cliente.md
05_anomalie_formali.md
06_memo_istruttoria.md
07_scheda_codex_per_studio.md
08_dati_fiscali_strutturati.md
run_intake.json
review_payload.json
ui_decisions.json
applied_decisions.json
final_artifacts.json
duplicate_candidates.csv
extracted/
fatture/
avviso/
```

Gli output di casi reali vanno in una cartella privata fuori dal repository,
preferibilmente in una directory `output/client-file-preparation` accanto alla
cartella cliente.

## Dipendenze e debug per sviluppatori

Il pacchetto Vera include già questo motore. I comandi seguenti servono a test e
debug dalla sorgente, non costituiscono un'installazione o un percorso utente
separato.

```bash
python scripts/check_dependencies.py --folder "/percorso/cartella-cliente"
python scripts/build_file_preparation_outputs.py \
  "/percorso/cartella-cliente" \
  --year 2025 \
  --out "/percorso/output/client-file-preparation"
```

Le dipendenze base sono in `requirements.txt`; l'OCR opzionale è in
`requirements-ocr.txt`.

## Regola di sviluppo

La sorgente modificabile è `plugins/client-file-preparation`. Nel pacchetto Vera
viene incorporata come `plugins/vera/modules/client-file-preparation`. Cartelle
scaricate, cache Codex e ZIP sono artefatti generati e non vanno modificati
direttamente.

Dopo una modifica, il rilascio ricostruisce il pacchetto Vera e ne verifica
contenuto e test di integrità.
