# Automazione web

Componente Vera per registrare, entro confini dichiarati, un percorso web
mostrato da un operatore autorizzato. Il primo percorso supportato è la
registrazione post-login del flusso di richiesta e recupero ZIP delle fatture
nel portale Agenzia delle Entrate.

Il componente produce una mappa tecnica da rivedere; non acquisisce fatture e
non esegue ancora autonomamente il flusso registrato.

## Dipendenze opzionali

```bash
python scripts/check_dependencies.py --requirements requirements-portal-recorder.txt
python scripts/record_agenzia_invoice_flow.py --output-dir <fresh-private-directory>
```

L'output deve restare fuori dal repository e deve essere letto dal modello
soltanto dopo la revisione e l'approvazione esplicita dell'operatore.
