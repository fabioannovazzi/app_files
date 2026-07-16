# Client Intake

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/client-intake) · [MIT License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Plugin Codex per trasformare una cartella cliente in una prima istruttoria operativa per lo studio: inventario, estrazioni locali, controlli formali, dati fiscali strutturati, memo operativo e bozza email cliente.

Il plugin classifica documenti, estrae testo e campi leggibili, segnala file
incerti o non leggibili e prepara output rivedibili dallo studio. La copertura
documentale include Italia, Geneva, Zurich e UK; le regole legislative restano
fuori da questo layer finché non viene aggiunto un rule pack dedicato.

## Che cosa fa davvero

Il plugin non è il comando Python. Il comando Python è solo un utensile locale.

Il workflow corretto è:

1. lo studio indica a Codex una cartella cliente;
2. Codex usa gli script locali per creare inventario, CSV e controlli formali;
3. Codex legge quei risultati;
4. Codex prepara una scheda sintetica per lo studio, con punti mancanti, anomalie, domande al cliente e punti interni.

Senza il passaggio 3-4, il pacchetto è solo uno scanner locale. Il valore del plugin è far seguire a Codex una procedura ripetibile di istruttoria.

## UI review MCP

Il plugin segue il pattern dei plugin OpenAI con UI:

- gli script Python producono evidenze e payload strutturati:
  `run_intake.json`, `review_payload.json`, `ui_decisions.json` e
  `final_artifacts.json`;
- il server MCP locale dichiarato in `.mcp.json` espone
  `validate_client_intake_review` e `render_client_intake_review`;
- il server MCP serve l'asset HTML riutilizzabile
  `ui://widget/client-intake-review.html`;
- Codex deve validare il payload e poi renderizzare il widget MCP quando gli
  strumenti sono disponibili;
- Markdown/chat restano il fallback quando MCP non è disponibile.

Il server MCP è il layer di validazione e rendering UI. Non fa istruttoria e non
sostituisce gli script deterministici o la revisione Codex.

## Primo run beta / First Run Onboarding

Per un primo lavoro completo, Codex deve raccogliere e confermare questi elementi prima di lanciare gli helper:

- cartella cliente da analizzare;
- giurisdizione/mercato quando non è ovvio: Italia, Geneva, Zurich, UK o misto;
- anno target o campagna dichiarativa, ad esempio `2025`;
- cartella output, se diversa da `<cartella-cliente>/out`;
- presenza di scansioni/immagini e disponibilità OCR locale;
- ambito atteso: fascicolo 730/Redditi PF, CU/F24, fatture XML, avvisi Agenzia,
  Geneva/Zurich tax documents, UK Self Assessment/HMRC/P60/P45/P11D o cartella
  mista;
- limiti di lettura: PDF non testuali, immagini non OCR, file protetti, documenti non classificati;
- controllo dipendenze con `python scripts/check_dependencies.py --folder <cartella-cliente>`;
- output attesi: inventario, memo mancanze/incertezze, domande interne, bozza email cliente, anomalie formali, scheda Codex per studio, dati fiscali strutturati e allegati CSV/JSONL;
- passaggio di review: Codex legge gli output, rimuove richieste generiche non supportate e distingue classificazione da nome file, testo estratto, XML letto e file non leggibili.

## Prompt di avvio per beta user / Starter Prompt Bank

### Istruttoria completa fascicolo cliente

```text
Usa il plugin Client Intake sulla cartella /percorso/cartella-cliente.
Anno target 2025.
Prima del run chiedimi cartella output, OCR/scansioni e ogni limite di lettura.
Prepara inventario, controlli formali, dati fiscali strutturati, memo per lo studio, bozza email cliente e punti interni.
```

### Fascicolo 730/Redditi PF

```text
Usa Client Intake per un primo passaggio su fascicolo 730/Redditi PF nella cartella /percorso/cartella-cliente.
Anno target 2025.
Evidenzia CU, F24, spese, mutuo, 730/Redditi PF leggibili, documenti mancanti o incerti e limiti della lettura.
```

### Geneva / Zurich

```text
Usa Client Intake sulla cartella /percorso/cartella-cliente.
Giurisdizione Geneva o Zurich, anno target 2025.
Classifica dichiarazioni, certificati di salario/Lohnausweis, tassazioni,
attestati bancari fiscali, imposta preventiva e lettere cantonali leggibili.
```

### UK Self Assessment

```text
Usa Client Intake sulla cartella /percorso/cartella-cliente.
Giurisdizione UK, anno target 2025.
Classifica Self Assessment, HMRC notices, P60, P45, P11D, payslips, bank
interest certificates, dividend vouchers and consolidated tax vouchers.
```

### Controllo formale fatture XML

```text
Usa il plugin Client Intake per controllare formalmente le FatturaPA XML nella cartella /percorso/cartella-cliente.
Anno target 2025.
Prepara riepilogo CSV, duplicati potenziali, file malformati, date fuori periodo, campi IVA/Natura e anomalie formali.
```

### Dati fiscali strutturati

```text
Estrai e rivedi i dati fiscali strutturati da CU, F24, 730, Redditi PF,
Geneva/Zurich tax documents e UK tax documents leggibili.
Riporta fonte, campo, valore, snippet di evidenza, confidenza e warning.
```

### Richieste mancanti / email cliente

```text
Partendo dall'istruttoria già prodotta, migliora la bozza email cliente.
Usa solo richieste supportate da 02_documenti_mancanti_o_incerti.md, togli domande generiche non supportate e mantieni tono operativo per lo studio.
```

### Avviso Agenzia / cartella

```text
Usa Client Intake per preparare un primo memo su avvisi, comunicazioni o cartelle presenti nel fascicolo.
Estrai riferimenti pratici, date, importi e documenti da recuperare.
```

## Stato plugin Codex

Questa cartella è un plugin Codex locale perché contiene:

- `.codex-plugin/plugin.json`;
- skill in `skills/`;
- script locali richiamabili dalle skill;
- template e asset;
- una voce repo-local in `.agents/plugins/marketplace.json`.

Lo ZIP scaricabile deve essere aperto come workspace Codex: contiene
`.agents/plugins/marketplace.json` e `.agents/plugins/client-intake`. In Codex
va installato o abilitato dalla sezione `Plugins`.

In una normale shell non esiste un comando magico `codex plugin run`: da CLI si
eseguono solo gli script per debug. Il workflow vero è Codex che vede il plugin,
carica le skill e l'utente chiede:

```text
Usa il plugin Client Intake sulla cartella /percorso/cliente/2025.
```

In quel caso Codex deve usare la skill `client-intake`, non limitarsi a lanciare uno script e fermarsi.

## Come si usa in Codex

Esempio di richiesta:

```text
Usa il plugin Client Intake sulla cartella /Clienti/[Cliente]/2025.
Anno target 2025.
Prepara la scheda per lo studio.
```

Codex deve:

- caricare la skill `client-intake`;
- eseguire il workflow `client-intake` o `fascicolo-intake`;
- generare i file tecnici nella cartella `out`;
- leggere i risultati generati;
- scrivere `07_scheda_codex_per_studio.md`;
- rispondere con una sintesi breve.

## CLI solo per debug

La CLI è il livello strumenti, non il livello plugin.

```bash
cd /percorso/client-intake
python -m pip install -r requirements.txt
python scripts/check_dependencies.py --folder "/percorso/cartella-cliente"
python scripts/build_intake_outputs.py "/percorso/cartella-cliente" --year 2025 --out "/percorso/out"
```

Poi si leggono gli output, in particolare:

```text
out/07_scheda_codex_per_studio.md
out/08_dati_fiscali_strutturati.md
out/extracted/structured_fiscal_fields.csv
```

## Cosa controlla oggi

- Scansione cartelle e sottocartelle.
- Classificazione prudente dai nomi file e dai percorsi.
- Estrazione testo da PDF testuali con `pdfplumber` / PyMuPDF.
- OCR locale opzionale con PaddleOCR quando il PDF o l'immagine non contiene testo leggibile.
- Estrazione di campi fiscali strutturati da testo leggibile per CU, F24, 730,
  Redditi PF, documenti Geneva/Zurich e documenti UK.
- Classificazione Geneva/Zurich: déclarations fiscales, Steuererklärungen,
  certificats de salaire/Lohnausweis, avis de taxation/Veranlagung,
  attestations fiscales, Steuerbescheinigungen e imposta preventiva.
- Classificazione UK: Self Assessment, SA100/SA302, HMRC notices, P60, P45,
  P11D, payslips, bank interest certificates, dividend vouchers e consolidated
  tax vouchers.
- Inventario CSV e indice markdown.
- Controllo formale e-fatture XML con dati documento, imponibile/IVA, natura, ritenute, bollo e pagamenti quando presenti.
- Duplicati esatti o fortemente sospetti.
- File fuori anno quando l'anno è nel nome file.
- Prime mancanze operative per fascicoli Italia: CU, F24, mutuo, ricevute sanitarie, documenti non classificati.
- Bozza email cliente e memo interno.

## Copertura attuale

Questa versione prepara l'istruttoria operativa del fascicolo.

- Estrae testo da PDF testuali e immagini quando le librerie locali sono disponibili.
- Segnala i documenti che richiedono verifica manuale quando la lettura non è affidabile.
- Produce una base ordinata per il lavoro dello studio.
- Produce campi fiscali strutturati con evidenza testuale, confidenza e avvisi di verifica.

## Dati strutturati estratti

Il parser lavora sui testi estratti localmente e produce righe verificabili.

- `F24`: codice tributo, anno riferimento, importi a debito/credito, righe tabellari quando leggibili.
- `CU`: codici fiscali, anni, redditi lavoro dipendente/pensione quando individuabili, ritenute, addizionali, punti CU numerici presenti nel testo.
- `730`: importi di liquidazione quando etichettati e righi/quadro leggibili come `RC1`, `E1`, `RN`, `RX`.
- `Redditi PF`: reddito complessivo, imposta lorda/netta, differenza e righi/quadro leggibili.
- `Geneva/Zurich/CH`: certificati di salario/Lohnausweis, dichiarazioni, tassazioni, attestati bancari fiscali e imposta preventiva quando leggibili.
- `UK`: P60, P45, P11D, payslips, Self Assessment, HMRC notices, certificati interessi bancari, dividend vouchers e consolidated tax vouchers quando leggibili.

Ogni campo contiene percorso documento, codice campo, valore originale, valore normalizzato, confidenza, snippet di evidenza e warning quando il valore dipende dal layout.

## Dipendenze locali

Controllo ambiente:

```bash
python scripts/check_dependencies.py --folder /percorso/cartella-cliente
```

Installazione base per PDF testuali:

```bash
python -m pip install -r requirements.txt
```

Installazione OCR locale:

```bash
python -m pip install -r requirements-ocr.txt
```

`requirements-core.txt` resta nel pacchetto come alias storico, ma il file di riferimento per il plugin Codex è `requirements.txt`.

## Output

```text
out/
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
  duplicate_candidates.csv
  extracted/
    documents.jsonl
    document_extraction.csv
    extraction_report.md
    structured_fiscal_fields.csv
    structured_fiscal_fields.jsonl
    fatture_xml.jsonl
    pdf_text/
  fatture/
    fatture_summary.csv
    duplicate_candidates.csv
    formal_anomalies.md
  avviso/
    avviso_intake_memo.md
    deadlines_and_amounts.csv
```

## Regola di sviluppo

La sorgente modificabile è solo:

```text
plugins/client-intake
```

Cartelle scaricate, cache Codex e ZIP sono artefatti generati. Dopo modifiche alla sorgente, ricostruire il pacchetto con:

```bash
.venv/bin/python scripts/build_codex_plugin_zip.py client-intake
.venv/bin/python scripts/build_codex_plugin_zip.py client-intake --check
.venv/bin/python -m pytest plugins/client-intake/tests tests/plugins/test_codex_plugin_packages.py
```
