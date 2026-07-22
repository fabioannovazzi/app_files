# New Client · File Preparation Reference

Load this internal reference when New Client needs starter prompts, artifact
expectations, or the file-preparation output list. Keep New Client as the user
entry point.

## Starter Prompt Bank

Full customer-folder intake:

```text
Usa New Client sulla cartella /percorso/cartella-cliente.
Anno target 2025.
Prepara inventario, controlli formali, dati fiscali strutturati, memo per lo
studio e bozza email cliente, poi continua con le altre fasi del nuovo rapporto.
```

730/Redditi PF first intake:

```text
Usa New Client sul fascicolo 730/Redditi PF nella cartella
/percorso/cartella-cliente.
Anno target 2025.
Evidenzia CU, F24, spese, mutuo, 730/Redditi PF leggibili, documenti mancanti o incerti e limiti della lettura.
```

Geneva / Zurich intake:

```text
Usa New Client sulla cartella /percorso/cartella-cliente.
Giurisdizione Geneva o Zurich, anno target 2025.
Classifica dichiarazioni, certificati di salario/Lohnausweis, tassazioni,
attestati bancari fiscali, imposta preventiva e lettere cantonali leggibili.
```

UK Self Assessment intake:

```text
Usa New Client sulla cartella /percorso/cartella-cliente.
Giurisdizione UK, anno target 2025.
Classifica Self Assessment, HMRC notices, P60, P45, P11D, payslips, bank
interest certificates, dividend vouchers and consolidated tax vouchers.
```

FatturaPA XML formal check:

```text
Usa New Client sulla cartella /percorso/cartella-cliente e includi il controllo
formale delle FatturaPA XML.
Anno target 2025.
Prepara riepilogo CSV, duplicati potenziali, file malformati, date fuori periodo, campi IVA/Natura e anomalie formali.
```

Structured fiscal fields:

```text
Nel percorso New Client, estrai e rivedi i dati fiscali strutturati da CU, F24,
730, Redditi PF,
Geneva/Zurich tax documents e UK tax documents leggibili.
Riporta fonte, campo, valore, snippet di evidenza, confidenza e warning.
```

Missing-document email pack:

```text
Partendo dall'istruttoria gia prodotta, migliora la bozza email cliente.
Usa solo richieste supportate da 02_documenti_mancanti_o_incerti.md, togli domande generiche non supportate e mantieni tono operativo per lo studio.
```

Avviso presente nel fascicolo:

```text
Usa New Client per preparare un primo memo su avvisi, comunicazioni o cartelle
presenti nel fascicolo.
Estrai riferimenti pratici, date, importi e documenti da recuperare.
```

## Expected Delivery Artifacts

- `00_environment_check.md`;
- `00_fascicolo_index.md`;
- `01_document_inventory.csv`;
- `02_documenti_mancanti_o_incerti.md`;
- `03_domande_interne_studio.md`;
- `04_bozza_email_cliente.md`;
- `05_anomalie_formali.md`;
- `06_memo_istruttoria.md`;
- `07_scheda_codex_per_studio.md`;
- `08_dati_fiscali_strutturati.md`;
- `run_intake.json`;
- `review_payload.json`;
- `ui_decisions.json`;
- `review_handoff.md`;
- `final_artifacts.json`;
- `applied_decisions.json` after decisions have been applied;
- `duplicate_candidates.csv`;
- `extracted/document_extraction.csv`;
- `extracted/structured_fiscal_fields.csv`;
- `fatture/fatture_summary.csv`;
- `avviso/avviso_intake_memo.md` when notices are present.

## Evidence Files To Read

- `00_environment_check.md`;
- `00_fascicolo_index.md`;
- `01_document_inventory.csv`;
- `02_documenti_mancanti_o_incerti.md`;
- `03_domande_interne_studio.md`;
- `04_bozza_email_cliente.md`;
- `05_anomalie_formali.md`;
- `06_memo_istruttoria.md`;
- `07_scheda_codex_per_studio.md`;
- `08_dati_fiscali_strutturati.md`;
- `run_intake.json`;
- `review_payload.json`;
- `ui_decisions.json`;
- `final_artifacts.json`;
- `duplicate_candidates.csv`;
- `extracted/documents.jsonl`;
- `extracted/document_extraction.csv`;
- `extracted/extraction_report.md`;
- `extracted/structured_fiscal_fields.csv`;
- `extracted/structured_fiscal_fields.jsonl`;
- `extracted/fatture_xml.jsonl`;
- `fatture/fatture_summary.csv`;
- `fatture/formal_anomalies.md`;
- `avviso/avviso_intake_memo.md`.

## MCP Review Handoff

The internal phase follows the OpenAI-style MCP UI pattern for review surfaces:

1. the Python workflow writes `run_intake.json`, `review_payload.json`,
   `ui_decisions.json`, and `final_artifacts.json`;
2. Codex calls `validate_client_file_preparation_review` with the complete
   `review_payload.json` object;
3. after validation succeeds, Codex calls `render_client_file_preparation_review`;
4. the local MCP server serves `ui://widget/client-file-preparation-review.html` and
   returns `openai/outputTemplate` metadata so the host can render the HTML
   widget;
5. if host MCP tools are unavailable, start the packaged local workbench from
   the resolved module root with
   `python scripts/review_server.py <output-directory>`; it uses the same tool
   contract and persists save/apply operations into the run directory;
6. only when neither review service can run, use Markdown/chat to inspect the
   same JSON files and keep `ui_decisions.json` pending rather than presenting
   an unpersisted conversation as an applied review.

Do not hand-build a separate HTML page for this review handoff. The reusable MCP
widget is the primary UI surface.

## Integrity And Privacy Contract

- validate that the customer folder exists and contains evidence before any
  default output directory is created;
- keep every inventoried file in `extracted/documents.jsonl`, including unread
  or unsupported files;
- keep absolute customer paths in the private local intake only; the review
  payload uses relative paths and omits text previews unless the run explicitly
  enables them; explicit preview mode includes bounded excerpts from every
  readable inventoried document, fiscal-field evidence snippets, and generated
  draft previews that can repeat the client name;
- require `size_bytes` and `sha256` for every `final_artifacts.json` output;
- compute `integrity.package_hash` from the UTF-8-path-sorted canonical array of
  `{path, sha256, size_bytes}` records; `final_artifacts.json` itself is excluded;
- verify the sealed files before review application and reseal them after every
  save/apply mutation.
