# Automazione web

Strumento Vera per insegnare un processo web a cui lo sviluppatore non può
accedere direttamente. L'operatore usa la propria sessione Chrome autenticata,
descrive la funzione e sceglie `guided`, `autonomous` oppure `hybrid`: può
mostrare il percorso, lasciare che il modello esplori i passaggi sicuri, o fare
entrambe le cose.

Il modello interpreta pagine, milestone, rami ed errori. Il runtime JSON usa
Playwright nella connessione Chrome per eseguire azioni, estrarre output
strutturati, verificare postcondizioni e generare ricevute hash-linked. Una
pipeline locale controlla struttura, origini, approvazioni separate, esclusione
dei segreti, ricevute di prova e hash dei pacchetti. Il primo risultato è un
developer pack sanitizzato e revisionato con timeline, postcondizioni, rami,
incertezze e draft non eseguibile. Dopo approvazione e replay, il secondo
risultato è la capability portabile specifica del processo.

Il modulo include:

- un osservatore guidato read-only che conserva solo percorsi senza query,
  metadati semantici dei controlli e fingerprint di stato;
- una skill generica di discovery, developer handoff, generazione, replay e
  capability handoff;
- un recupero model-led limitato a un nuovo locator semantico per la stessa
  azione sicura oppure a un locator CSS circoscritto per un campo dentro una
  riga strutturata già risolta, con proposta owner-only e ricevuta non valida
  come clean run;
- una capability Gmail in stato `validated_local`, verificata con due replay
  puliti sul ramo con risultati, che esporta metadati visibili in un artefatto
  privato senza aprire i messaggi;
- uno scaffold Agenzia per richiesta fatture e recupero ZIP;
- uno scaffold TeamSystem da specializzare sul prodotto e processo reali.

Le capability non contengono credenziali, cookie, storage del browser, sessioni,
contenuti osservati o file scaricati. Ogni operatore autentica la propria
sessione Chrome.

```bash
python scripts/check_dependencies.py
python scripts/capability_pipeline.py validate --kind capability capabilities/gmail-search-export/capability.json
python scripts/discovery_pack.py --help
node --test ../../tests/test_browser_automation_runtime.mjs ../../tests/test_browser_automation_discovery_runtime.mjs
```

Le capability `scaffold` e `draft` non sono eseguibili. Una capability passa a
`discovered` solo dopo l'approvazione dell'esatto record di discovery; passa a
`validated_local` solo dopo due ricevute generate dal runtime nella stessa
interfaccia Chrome e senza recovery. `outputs.json`, raw capture e proposte di
recovery non entrano nel pacchetto portatile. La validazione Gmail corrente è
specifica all'ambiente osservato; il ramo senza risultati resta dichiarato ma
non è stato verificato dal vivo.
