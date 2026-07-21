# Installare Vera per usare New Client

La preparazione del fascicolo è inclusa nel percorso **New Client** di Vera. Non
richiede un'installazione separata e non compare come prodotto distinto.

## Installazione

1. Decomprimi lo ZIP di Vera.
2. Apri in Codex la cartella estratta che contiene
   `.agents/plugins/marketplace.json`.
3. Nella sezione `Plugins`, installa o abilita **Vera** dal marketplace locale
   Mparanza.
4. Apri una chat Codex nella stessa area di lavoro.

## Avvio di New Client

Scrivi, per esempio:

```text
Usa New Client per preparare il fascicolo nella cartella
/percorso/cartella-cliente. Anno target 2025. Porta il caso fino alla review
dello studio.
```

Vera avvia la fase interna di preparazione, controlla le dipendenze, legge gli
output e continua con anagrafica, incarico, privacy, AML e review nello stesso
percorso.

## Nota per sviluppatori

Nella sorgente il motore vive in `plugins/client-file-preparation`; nel bundle
Vera viene incorporato in `plugins/vera/modules/client-file-preparation`. Gli
script Python possono essere eseguiti direttamente solo per test e debug.
