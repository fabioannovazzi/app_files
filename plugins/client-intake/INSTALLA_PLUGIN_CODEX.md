# Installare come plugin Codex locale

Questo pacchetto deve essere usato come plugin locale, non come semplice script.

## Installazione

1. Decomprimi lo ZIP.
2. Apri in Codex la cartella estratta che contiene `.agents/plugins/marketplace.json`.
3. Vai nella sezione `Plugins`.
4. Installa o abilita `Client Intake` dal marketplace locale `Mparanza Local`.
5. Apri una chat Codex nella stessa area di lavoro.

## Uso

Scrivi:

```text
Usa il plugin Client Intake sulla cartella /percorso/cartella-cliente.
Anno target 2025.
Giurisdizione Italia, Geneva, Zurich, UK o mista se non è ovvia.
Prepara la scheda per lo studio.
```

Codex deve caricare la skill `client-intake`, controllare le dipendenze,
eseguire gli script locali, leggere gli output e preparare la sintesi operativa.

Il primo controllo tecnico che Codex deve eseguire dal folder del plugin è:

```bash
python scripts/check_dependencies.py --folder /percorso/cartella-cliente
```

## Output principali

```text
out/07_scheda_codex_per_studio.md
out/08_dati_fiscali_strutturati.md
out/extracted/structured_fiscal_fields.csv
out/04_bozza_email_cliente.md
```

## Nota per sviluppatori

Gli script Python possono essere lanciati da terminale solo per test o debug.
Il flusso prodotto per l'utente resta quello plugin: Codex carica la skill e
coordina i passaggi.
