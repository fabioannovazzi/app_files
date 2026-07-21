# Usare New Client dallo ZIP di Vera

Lo ZIP di Vera contiene già il motore di preparazione del fascicolo. L'utente
abilita **Vera** una sola volta e avvia un solo percorso: **New Client**.

## Avvio

Dopo avere aperto lo ZIP come workspace Codex e abilitato Vera, chiedi:

```text
Usa New Client sulla cartella [percorso cartella cliente]. Anno target 2025.
Prepara il fascicolo e accompagnami fino alla review dello studio.
```

Vera:

- controlla ambiente, file e OCR disponibile;
- prepara inventario, estrazioni, controlli e dati strutturati;
- presenta le evidenze per la review;
- prosegue con i dati del rapporto, incarico, privacy, AML e monitoraggio.

Gli output restano in una cartella privata scelta per il caso e includono la
scheda per lo studio, la bozza di richiesta al cliente, i dati fiscali
strutturati e gli artefatti di review.

## Debug del motore interno

Questi comandi sono destinati agli sviluppatori. Non sono necessari per usare
New Client da Vera.

```bash
cd plugins/client-file-preparation
python scripts/check_dependencies.py --folder "/percorso/cartella-cliente"
python scripts/build_file_preparation_outputs.py \
  "/percorso/cartella-cliente" \
  --year 2025 \
  --out "/percorso/output/client-file-preparation"
```

Le dipendenze base sono in `requirements.txt`; per scansioni e immagini è
disponibile `requirements-ocr.txt`.
