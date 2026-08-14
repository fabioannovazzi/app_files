> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

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
- `07_scheda_per_studio.md`;
- `08_dati_fiscali_strutturati.md`;
- `run_intake.json`;
- `review_payload.json`;
- `ui_decisions.json`;
- `model_handoff.json` and every page under `model_handoff_pages/`;
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
- `07_scheda_per_studio.md`;
- `08_dati_fiscali_strutturati.md`;
- `run_intake.json`;
- `review_payload.json`;
- `ui_decisions.json`;
- `model_handoff.json` and every declared `model_handoff_pages/page-*.json`;
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

## Cowork review handoff

The normal Cowork handoff is the reviewable draft, artifact card, and
`run_intake.json`, `review_payload.json`, `ui_decisions.json`, and
`final_artifacts.json` in the connected folder. Review those files directly.

When a validated MCP or local workbench is callable, it may optionally persist
save/apply actions. Its absence never blocks delivery of the file-based package.
Never present conversational or Markdown review as persisted: keep decisions
pending unless corresponding saved and applied artifacts prove otherwise.

## Integrity And Review Contract

- validate that the customer folder exists and contains evidence before any
  default output directory is created;
- keep every inventoried file in `extracted/documents.jsonl`, including unread
  or unsupported files;
- keep absolute customer paths in the private local intake only; the review
  payload uses relative paths and includes bounded, professionally useful
  excerpts from readable inventoried documents, fiscal-field evidence, and
  generated drafts by default; these may contain real client data, and their
  size limits support interface performance rather than anonymization or an
  inventory of everything Claude may have read;
- use `model_handoff.json` and all of its hash-listed pages as the default
  Claude/Cowork context: one metadata row per inventoried file, exception-only
  document excerpts, every fiscal field with a citation of at most 600
  characters, reviewed email requests with `CLIENT-001`, and XML anomaly or
  opaque duplicate-group refs without invoice-party fields; do not sample
  pages or exceed 2,500 items / 1,500,000 bytes per page;
- exclude credentials, session material, and raw absolute local paths from the
  review payload;
- require `size_bytes` and `sha256` for every `final_artifacts.json` output;
- compute `integrity.package_hash` from the UTF-8-path-sorted canonical array of
  `{path, sha256, size_bytes}` records; `final_artifacts.json` itself is excluded;
- verify the sealed files before review application and reseal them after every
  save/apply mutation.
