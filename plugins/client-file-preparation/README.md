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
- `applied_decisions.json`, creato solo quando la review viene applicata;
- `final_artifacts.json` con stato e artefatti finali.

Il server MCP espone i tool interni:

```text
validate_client_file_preparation_review
render_client_file_preparation_review
save_client_file_preparation_decisions
apply_client_file_preparation_decisions
```

Il widget usa `ui://widget/client-file-preparation-review.html`. Se i tool MCP
del client non sono disponibili, il pacchetto Vera include un workbench locale
con write-back persistente, avviabile dal root del modulo con:

```bash
python scripts/review_server.py "/percorso/output/client-file-preparation"
```

La sola review in Markdown/chat non applica decisioni: in quel caso
`ui_decisions.json` resta in attesa.

Per arrivare allo stato finale la review deve essere completa e attribuita a un
riferimento stabile del professionista o del suo account. Può essere il nome
reale del professionista; non deve contenere credenziali, token di sessione o
percorsi locali grezzi. Una review saltata o incompleta non rende il fascicolo
pronto.

## Copertura documentale

- PDF testuali e immagini, con OCR locale opzionale;
- DOCX, XLSX ed EML con estrazione locale; gli allegati EML restano esplicitamente
  non letti;
- MSG e altri formati non supportati restano nell'inventario con stato non
  leggibile e non ricevono mai una raccomandazione automatica di accettazione;
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
review_handoff.md
final_artifacts.json
applied_decisions.json        # dopo l'applicazione della review
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
  --jurisdiction italy \
  --language it \
  --out "/percorso/output/client-file-preparation"
```

`--jurisdiction` accetta `italy`, `geneva`, `zurich`, `uk` o `mixed`;
`--language` accetta `it`, `en`, `fr` o `de`. Il payload di review include per
impostazione predefinita estratti limitati di ogni documento leggibile,
evidenze dei campi fiscali e anteprime della scheda per lo studio, del memo e
dell'e-mail al cliente. Possono contenere dati reali del cliente necessari alla
review. I limiti servono a mantenere gestibile l'interfaccia, non sono una forma
di anonimizzazione e non descrivono tutto ciò che Codex può aver letto. Restano
esclusi credenziali, materiale di sessione e percorsi locali assoluti.

Il motore non segue link simbolici presenti nella cartella cliente. Estrazione
PDF/testo, OCR e lettura dei formati Office/archivio supportati applicano limiti
espliciti; un file oltre soglia resta evidenza non letta o parziale, senza
essere considerato verificato.

Ogni file elencato in `final_artifacts.json` è sigillato con dimensione e
SHA-256. Il `package_hash` copre l'inventario canonico degli output e viene
verificato e ricalcolato quando le decisioni vengono salvate o applicate.

Le dipendenze base sono in `requirements.txt`; l'OCR opzionale è in
`requirements-ocr.txt`.

## Regola di sviluppo

La sorgente modificabile è `plugins/client-file-preparation`. Nel pacchetto Vera
viene incorporata come `plugins/vera/modules/client-file-preparation`. Cartelle
scaricate, cache Codex e ZIP sono artefatti generati e non vanno modificati
direttamente.

Dopo una modifica, il rilascio ricostruisce il pacchetto Vera e ne verifica
contenuto e test di integrità.
