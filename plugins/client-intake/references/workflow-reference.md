# Workflow Reference

Load this reference when the user needs starter prompts, artifact expectations, or a sub-workflow-specific output list.

## Starter Prompt Bank

Full customer-folder intake:

```text
Usa il plugin Client Intake sulla cartella /percorso/cartella-cliente.
Anno target 2025.
Prima del run chiedimi cartella output, OCR/scansioni e ogni limite di lettura.
Prepara inventario, controlli formali, dati fiscali strutturati, memo per lo studio, bozza email cliente e punti interni.
```

730/Redditi PF first intake:

```text
Usa Client Intake per un primo passaggio su fascicolo 730/Redditi PF nella cartella /percorso/cartella-cliente.
Anno target 2025.
Evidenzia CU, F24, spese, mutuo, 730/Redditi PF leggibili, documenti mancanti o incerti e limiti della lettura.
```

Geneva / Zurich intake:

```text
Usa Client Intake sulla cartella /percorso/cartella-cliente.
Giurisdizione Geneva o Zurich, anno target 2025.
Classifica dichiarazioni, certificati di salario/Lohnausweis, tassazioni,
attestati bancari fiscali, imposta preventiva e lettere cantonali leggibili.
```

UK Self Assessment intake:

```text
Usa Client Intake sulla cartella /percorso/cartella-cliente.
Giurisdizione UK, anno target 2025.
Classifica Self Assessment, HMRC notices, P60, P45, P11D, payslips, bank
interest certificates, dividend vouchers and consolidated tax vouchers.
```

FatturaPA XML formal check:

```text
Usa il plugin Client Intake per controllare formalmente le FatturaPA XML nella cartella /percorso/cartella-cliente.
Anno target 2025.
Prepara riepilogo CSV, duplicati potenziali, file malformati, date fuori periodo, campi IVA/Natura e anomalie formali.
```

Structured fiscal fields:

```text
Estrai e rivedi i dati fiscali strutturati da CU, F24, 730, Redditi PF,
Geneva/Zurich tax documents e UK tax documents leggibili.
Riporta fonte, campo, valore, snippet di evidenza, confidenza e warning.
```

Missing-document email pack:

```text
Partendo dall'istruttoria gia prodotta, migliora la bozza email cliente.
Usa solo richieste supportate da 02_documenti_mancanti_o_incerti.md, togli domande generiche non supportate e mantieni tono operativo per lo studio.
```

Avviso intake:

```text
Usa Client Intake per preparare un primo memo su avvisi, comunicazioni o cartelle presenti nel fascicolo.
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
- `final_artifacts.json`;
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

The plugin follows the OpenAI-style MCP UI pattern for review surfaces:

1. the Python workflow writes `run_intake.json`, `review_payload.json`,
   `ui_decisions.json`, and `final_artifacts.json`;
2. Codex calls `validate_client_intake_review` with the complete
   `review_payload.json` object;
3. after validation succeeds, Codex calls `render_client_intake_review`;
4. the local MCP server serves `ui://widget/client-intake-review.html` and
   returns `openai/outputTemplate` metadata so the host can render the HTML
   widget;
5. if the MCP tools are unavailable, Codex falls back to Markdown/chat review
   using the same JSON files.

Do not hand-build a separate HTML page for this review handoff. The reusable MCP
widget is the primary UI surface.
