# Lucia

[Pagina prodotto](https://mparanza.com/static/shared/lucia/index.html?lang=it) ·
[Supporto](https://mparanza.com/support) ·
[Licenza GNU AGPLv3](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Lucia è l’assistente AI di Mparanza per avvocati indipendenti e piccoli studi
legali che lavorano nel contesto italiano. Prepara ricerca e validazione
mantenendo visibili perimetro, fonti, affermazioni, incertezze e passaggi
riservati al giudizio professionale.

Lucia non sostituisce l’avvocato: strategia, conclusioni, approvazione e
responsabilità restano al professionista.

## Catalogo corrente

Il catalogo cresce attraverso workflow specialistici registrati. Le funzioni
attualmente pubbliche sono:

- **Ottimizza prompt** — Trasforma un quesito legale, fiscale o di conformità
  in una ricerca con perimetro, fonti e verifiche definite.
- **Valida Deep Research** — Controlla le affermazioni rispetto alle fonti
  citate e prepara il materiale consolidato.

Prompt Optimizer e Deep Research Validator sono le stesse implementazioni
canoniche incorporate in Vera. Lucia non ne mantiene copie divergenti: il
builder include gli stessi file sorgente e i test verificano l’uguaglianza dei
byte nei pacchetti generati.

## Come lavora

1. Lucia interpreta semanticamente la richiesta e la instrada al workflow
   specialistico registrato appropriato.
2. Prompt Optimizer definisce il contratto della risposta, il perimetro, le
   fonti necessarie e i controlli da superare.
3. Deep Research Validator verifica identità e accessibilità delle fonti,
   supporto delle affermazioni e tenuta del ragionamento.
4. Il risultato resta una bozza rivedibile. Lucia non firma pareri, deposita
   atti, invia comunicazioni o assume decisioni professionali.

Se nessun workflow registrato copre la richiesta, Lucia si ferma e indica che
la funzione non è ancora disponibile. Nuove funzioni possono essere aggiunte
al catalogo senza cambiare il contratto dei workflow esistenti.

## Superfici

- **ChatGPT Work** usa i materiali disponibili nella conversazione e non
  dichiara di avere eseguito strumenti locali o creato artefatti persistenti.
- **Codex** può lavorare nel workspace locale, eseguire i controlli dichiarati
  e conservare artefatti rivedibili quando le capacità sono disponibili.

Studio Archive è incluso nel pacchetto Codex soltanto come infrastruttura
privata per legare input, run e risultati a un incarico. Lucia non espone
ricerca d’archivio, Gmail, Google Drive o WhatsApp come funzioni pubbliche. Il
pacchetto per ChatGPT non include questo runtime privato.

## Sorgente e pacchetti

La sorgente modificabile vive in `plugins/lucia`. I pacchetti generati sono:

- `plugin_packages/lucia/lucia-plugin.zip` per Codex;
- `plugin_packages/lucia/lucia-chatgpt-upload.zip` per la submission ChatGPT.

I pacchetti sono artefatti generati e non devono essere modificati a mano.

Per ricostruirli e verificare che corrispondano alla sorgente:

```bash
.venv/bin/python scripts/build_codex_plugin_zip.py lucia
.venv/bin/python scripts/build_codex_plugin_zip.py lucia --check
```

## Dati e confini professionali

I dati forniti al modello vengono trattati attraverso il piano ChatGPT già
utilizzato dall’utente. I workflow ordinari non inviano a Mparanza file dei
clienti, prompt o contenuti del contesto del modello. Password, chiavi API,
cookie, token e dati di sessione non devono entrare nei prompt o nei file
leggibili da Codex.

La descrizione completa è disponibile nella pagina
[Gestione dei dati](https://mparanza.com/data-handling?lang=it).
