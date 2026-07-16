# Come usare lo ZIP

Questo ZIP contiene un plugin Codex locale-first per preparare l'istruttoria
operativa di una cartella cliente.

La parte importante non è lanciare uno script. La parte importante è aprire in
Codex la cartella estratta, installare il plugin locale e fare caricare a Codex
la skill `client-intake`.

## Installazione plugin

1. Decomprimi lo ZIP.
2. Apri in Codex la cartella estratta che contiene `.agents/plugins/marketplace.json`.
3. Vai in `Plugins`.
4. Installa o abilita `Client Intake` dal marketplace locale.
5. Apri una chat nella stessa area di lavoro.

Lo ZIP non è solo la cartella degli script: include anche la metadata di
marketplace locale necessaria perché Codex possa presentarlo come plugin.

## Uso corretto in Codex

Quando il plugin è abilitato, chiedi:

```text
Usa il plugin Client Intake sulla cartella [percorso cartella cliente].
Anno target 2025.
Giurisdizione Italia, Geneva, Zurich, UK o mista se non è ovvia.
Prepara la scheda per lo studio.
```

Codex dovrebbe:

- caricare la skill `client-intake`;
- eseguire `python scripts/check_dependencies.py --folder [percorso cartella cliente]`;
- segnalare eventuali librerie mancanti e proporre il comando di installazione;
- eseguire i controlli locali;
- leggere i file prodotti;
- preparare una scheda sintetica `07_scheda_codex_per_studio.md`;
- preparare `08_dati_fiscali_strutturati.md` e i CSV/JSONL dei campi fiscali quando i documenti sono leggibili;
- indicare cosa manca, cosa è incerto e cosa richiede controllo interno.

## CLI solo per debug

Il terminale serve per testare gli script, non per usare il prodotto come plugin.

```bash
cd .agents/plugins/client-intake
python scripts/check_dependencies.py --folder "/percorso/cartella-cliente"
python scripts/build_intake_outputs.py "/percorso/cartella-cliente" --year 2025 --out "/percorso/out"
```

## Dipendenze

Per PDF testuali:

```bash
python -m pip install -r requirements.txt
```

Per OCR locale su scansioni e immagini:

```bash
python -m pip install -r requirements-ocr.txt
```

## Copertura attuale

Il prototipo estrae testo da PDF testuali, può usare OCR locale se le librerie
sono installate e produce campi fiscali strutturati per F24, CU, 730, Redditi
PF, documenti Geneva/Zurich e documenti UK quando il testo è leggibile. I campi
hanno evidenza e confidenza.
