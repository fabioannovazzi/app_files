# Automazione web

Strumento Vera per scoprire un processo autorizzato in un sito web attraverso
la sessione Chrome già in uso e trasformarlo in una capability portabile.

Il modello interpreta pagine, milestone, rami ed errori. Playwright nella
connessione Chrome esegue azioni e verifiche ripetibili. Un validatore locale
controlla soltanto struttura, origini, esclusione dei segreti, ricevute di prova
e hash del pacchetto.

Il modulo include:

- la skill generica di discovery, generazione, replay e handoff;
- una capability Gmail di prova;
- uno scaffold Agenzia per richiesta fatture e recupero ZIP;
- uno scaffold TeamSystem da specializzare sul prodotto e processo reali.

Le capability non contengono credenziali, cookie, storage del browser, sessioni,
contenuti osservati o file scaricati. Ogni operatore autentica la propria
sessione Chrome.

```bash
python scripts/check_dependencies.py
python scripts/capability_contract.py validate capabilities/gmail-search-proof/capability.json --kind capability
```
