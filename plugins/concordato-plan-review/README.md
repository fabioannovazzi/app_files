# Revisione del Concordato Preventivo

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/concordato-plan-review) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Plugin Codex per organizzare e riesaminare un caso italiano di **concordato
preventivo**. Il significato del prodotto è quello giuridico e professionale
del termine: procedura, proposta, piano, attestazione, creditori, trattamento,
alternativa liquidatoria e fattibilità. Non è il nome arbitrario di un
riconciliatore costruito per un singolo fascicolo.

Il plugin aiuta Codex e un professionista qualificato a costruire un modello
riesaminabile del caso e a produrre workpaper riproducibili. Non emette un
parere legale, non attesta il piano, non autentica il revisore e non decide se
i requisiti di legge sono soddisfatti.

## Cosa riesamina

- quadro normativo applicabile e data di aggiornamento;
- identità, fase, tribunale, riferimento e tipologia della procedura;
- perimetro e versioni autorevoli di proposta, piano, attestazione e allegati;
- popolazione dei creditori, prelazione, classi, voto, trattamento e tempi;
- recupero proposto rispetto all'alternativa liquidatoria;
- fonti e impieghi, apporti esterni, dismissioni e fabbisogno;
- liquidità per periodo, distribuzioni, milestone e assunzioni;
- coerenza fra proposta, piano, attestazione, contabilità e prospetti;
- questioni aperte, contraddizioni, lacune documentali e follow-up.

La classificazione semantica viene proposta da Codex e confermata o corretta
da un professionista. Il codice valida il contratto e calcola soltanto ciò che
è meccanicamente verificabile.

## Confine fra calcolo e giudizio

Il codice deterministico gestisce:

- cattura delle fonti, hash, ricevute e chiusura degli output;
- schema, identità delle fonti e riferimenti di evidenza;
- aritmetica decimale esatta;
- aggregazioni per creditore e classe;
- percentuali di recupero e confronto piano/liquidazione;
- fonti e impieghi, funding gap e bridge di cassa;
- produzione riproducibile di JSON, CSV, XLSX, DOCX e payload di review;
- tie-out numerico per importo come controllo opzionale di appendice.

Codex e il professionista mantengono il giudizio su:

- diritto applicabile e significato dei documenti;
- perimetro, prelazione, classi, voto e trattamento dei creditori;
- sufficienza e pertinenza dell'evidenza;
- fattibilità, sostenibilità, materialità e continuità;
- profili legali, fiscali e previdenziali;
- gravità delle questioni e conclusione professionale.

Una formula esatta può provare un totale o una differenza. Non può provare che
un trattamento sia legittimo, che una fonte sia sufficiente o che il piano sia
fattibile.

## Flusso in due decisioni indipendenti

### 1. Ispezione

Il primo passaggio cattura le fonti senza assegnare significato dai nomi file:

```bash
python scripts/run_concordato_review.py /path/to/input \
  --output-dir /path/to/inspection \
  --reference-date 2026-03-31 \
  --language it \
  --document-language it \
  --tolerance 1
```

Fra gli output dell'ispezione:

- `inventory.json` e ricevute delle fonti;
- `suggested_concordato_case_model.json`, template semantico non riesaminato;
- `raw_amount_candidates.csv`, solo per l'eventuale appendice numerica;
- `suggested_source_role_recipe.json`, non operativo.

`suggested` significa realmente non autorevole. Il nome di un file non
classifica proposta, piano, attestazione o supporto contabile.

### 2. Modello semantico riesaminato

Codex legge le fonti e completa una copia del template con riferimenti di
evidenza e basi di giudizio. Un professionista conferma o corregge il modello.
Lo script seguente lo normalizza e lo lega ai byte correnti delle fonti:

```bash
python scripts/review_case_model.py /path/to/inspection \
  /path/to/reviewer-confirmed-case-model.json \
  --output /path/to/reviewed-semantic-recipe.json \
  --reviewer-ref qualified-reviewer \
  --reviewed-on 2026-07-26 \
  --reference-date 2026-03-31
```

Il modello deve classificare ogni fonte catturata e deve includere tutte le
aree professionali obbligatorie. Può registrare `missing`, `partial`,
`unclear`, `gap` e questioni aperte: la validazione non trasforma una lacuna in
una conclusione positiva.

### 3. Esecuzione semantica

```bash
python scripts/run_concordato_review.py /path/to/input \
  --output-dir /path/to/reviewed-output \
  --reference-date 2026-03-31 \
  --language it \
  --document-language it \
  --tolerance 1 \
  --semantic-recipe /path/to/reviewed-semantic-recipe.json
```

Il run rilegge le stesse fonti. Una modifica dei byte o del perimetro rende la
decisione obsoleta e blocca la review semantica.

### 4. Appendice numerica opzionale

Quando il caso richiede un tie-out riga-per-riga, Codex può preparare anche la
recipe numerica con `review_source_roles.py` e passarla con `--recipe`. Questa
decisione autorizza solo classificazione dei token e formula
`piano - supporto`; non sostituisce il modello del caso e non è necessaria per
un run semantico.

## Output principali

- `concordato_case_model.json`;
- `concordato_semantic_checks.json`;
- `creditor_treatment.csv`;
- `creditor_class_summary.csv`;
- `sources_and_uses.csv`;
- `liquidity_schedule.csv`;
- `concordato_review_workpaper.xlsx`;
- `concordato_semantic_review.md`;
- `concordato_preventivo_review_summary.docx`.

Gli output numerici precedenti restano disponibili come appendice:

- `amount_candidates.csv`;
- `exact_amount_matches.csv`;
- `concordato_tie_out_workpaper.xlsx`;
- `concordato_review_summary.docx`.

Il workbook principale separa Overview, Documents, Creditors, Classes,
Sources Uses, Liquidity, Review Questions, Issues, Mechanical Checks e Numeric
Tie-Out. La coda di review porta in testa procedura, domande professionali,
questioni, trattamento delle classi e controlli meccanici.

## Assurance e replay

Il modello riesaminato è una decisione semantica source-bound. Le
qualificazioni, i gate, le ricevute degli artifact e la chiusura completa degli
output sono riproducibili. Un run semantico senza appendice numerica registra
la riconciliazione come `not_applicable`; non finge che il tie-out sia stato
eseguito.

Per una replay indipendente:

```bash
python scripts/replay_assurance.py --output-dir /path/to/reviewed-output
```

Le ricevute provano coerenza e replay, non identità professionale, firma
digitale, completezza del fascicolo o correttezza del giudizio. La
pubblicazione rimane separata e trattenuta.

Il contratto meccanico completo è in
[`references/workflow-reference.md`](references/workflow-reference.md); il
metodo professionale è in
[`references/review-methodology.md`](references/review-methodology.md).

## UI di review

Il server MCP locale espone:

- `validate_concordato_plan_review`;
- `render_concordato_plan_review`;
- `save_concordato_plan_decisions`;
- `apply_concordato_plan_decisions`.

La UI legge il payload chiuso prodotto dal run. Le modifiche del revisore
restano decisioni esplicite; non alterano silenziosamente fonti, calcoli o
modello riesaminato.

## Primo prompt

```text
Usa Revisione del Concordato Preventivo sul fascicolo che indico.
Ricostruisci procedura, documenti autorevoli, creditori e trattamento,
alternativa liquidatoria, fonti e impieghi, liquidità e questioni aperte.
Tieni il tie-out numerico come appendice quando i documenti lo rendono utile.
```

## Sorgente e test

La sorgente modificabile è:

```text
plugins/concordato-plan-review
```

Dopo modifiche:

```bash
.venv/bin/python scripts/build_codex_plugin_zip.py concordato-plan-review
.venv/bin/python scripts/build_codex_plugin_zip.py concordato-plan-review --check
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/plugins/test_concordato_preventivo_semantics.py \
  tests/plugins/test_concordato_plan_review_plugin.py \
  tests/plugins/test_codex_plugin_packages.py
```
