# Starter Prompts

Load this reference when the user wants beta-facing examples or when adapting a known reconciliation workflow prompt.

## Full Open-Item Reconciliation

```text
Usa il plugin Riconciliazione partite sulla cartella /percorso/lavoro/input.
Periodo 2025, cut-off 31/12/2025. Lingua: it.
Chiedimi prima del run il file popolazione, le assunzioni sulle evidenze e ogni dato mancante.
Prepara Excel/Word con dettaglio righe, evidenze citate, review Codex e punti da verificare.
```

## Ledger Vs Bank/Evidence Check

```text
Usa Riconciliazione partite per confrontare mastrino, banca e supporti esterni nella cartella /percorso/lavoro/input.
Periodo 2025, cut-off 31/12/2025.
Separa evidenze forti, distinte ponte, sola evidenza interna e righe da verificare.
```

## Missing-Evidence Request Pack

```text
Partendo dal workbook di riconciliazione gia prodotto, genera il pacchetto richieste evidenze mancanti.
Usa wording operativo e distingui cosa e gia disponibile dal tassello che serve per chiudere o confermare aperta ogni riga.
```

## Reviewer Sample / Exception Review

```text
Partendo dal workbook di riconciliazione, crea un campione operativo di righe da controllare con revisore o cliente.
Includi righe collegate, domande di verifica e criteri di scelta senza esporre codici tecnici del motore.
```

## Post-Cut-Off Evidence Review

```text
Usa Riconciliazione partite per analizzare le evidenze successive al cut-off.
Segnala i candidati che spiegano chiusure successive, ma non usarli per chiudere righe alla data di cut-off se gli eventi post cut-off sono esclusi.
```
