# Revisione Piano Concordato

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/concordato-plan-review) · [MIT License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Plugin Codex per il tie-out numerico e la review contabile di un piano di concordato rispetto a bilancio provvisorio, mastrini, database rettificato e dettagli di supporto.

Il plugin non sostituisce il giudizio del revisore. Gli script estraggono numeri, inventariano fonti, trovano match meccanici per importo e preparano workpaper rivedibili. Codex usa quei risultati per classificare differenze, chiedere evidenze mancanti e scrivere un report sintetico sulle criticita.

## Cosa fa

- inventaria PDF e workbook forniti nel fascicolo;
- estrae testo pagina-per-pagina dai PDF testuali;
- ispeziona fogli Excel e celle numeriche rilevanti;
- identifica candidati numerici del piano e delle fonti contabili;
- produce match deterministici per importo, con tolleranza configurabile;
- prepara CSV, JSON, XLSX, Markdown e un Word riassuntivo per la review;
- distingue nel Word i numeri che battono per importo da quelli non trovati;
- prepara un payload MCP/HTML rivedibile con fonti, importi del piano,
  match candidati, importi non trovati, errori di estrazione e artifact finali;
- guida Codex nella distinzione tra dato storico, rettifica, riclassifica, assunzione prospettica e dato non supportato.

## UI review MCP

La review UI segue il pattern locale OpenAI-style usato dagli altri plugin
migrati:

- lo script Python continua a produrre i file deterministici principali e
  aggiunge `run_intake.json`, `review_payload.json`, `ui_decisions.json` e
  `final_artifacts.json`;
- il server MCP locale dichiarato in `.mcp.json` espone
  `validate_concordato_plan_review` e `render_concordato_plan_review`;
- il widget HTML riusabile `assets/concordato-plan-review-widget.html` rende
  il payload con ricerca, filtri per tipo e dettaglio evidenza;
- se MCP non e disponibile, Codex legge `review_payload.json` e continua con
  Markdown/chat senza bloccare il workflow.

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
