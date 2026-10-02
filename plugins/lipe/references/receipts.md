# LIPE — ricevute fornite dal professionista

Il lettore conserva una ricevuta già ottenuta dal canale di trasmissione. Non
accede al portale fiscale, non invia dichiarazioni e non autentica la ricevuta.

## Fonte e significato dei controlli

L'allegato sulle modalità di trasmissione al provvedimento del 27 marzo 2017,
sezione 3.5, indica `DatiFatturaMessaggi_v2.0.xsd` per la notifica e una firma
XAdES-BES enveloped. Il file originale dello schema è stato scaricato il
3 ottobre 2026 dalla [documentazione ufficiale FatturaPA](https://www.fatturapa.gov.it/it/norme-e-regole/DocumentazioneSDI/).
URL e hash dei byte sono in `sources.json` e `xsd/manifest.json`. Il provvedimento
2017 è usato qui soltanto per il formato della notifica, non per le regole di
calcolo o le scadenze attuali.

Il parser applica lo schema originale, compresa la struttura della firma, e
risolve l'esatto import W3C usando la copia completa verificata localmente.
Non scarica dipendenze XML. Rifiuta DTD, entità, strutture ambigue e file XML
oltre 8 MiB, 10.000 nodi o 64 livelli: sono limiti del lettore, non limiti legali.

Gli esiti dichiarati dallo schema sono:

| Codice | Testo dichiarato |
|---|---|
| ES01 | File validato |
| ES02 | File validato con segnalazione |
| ES03 | File scartato |

Una firma presente e conforme allo schema può essere falsa. Il rapporto mantiene
`cryptographic_integrity`, `xades_profile` e `signer_trust_and_revocation` a
`NOT_TESTED`, e `filing_acceptance` a `NOT_ESTABLISHED`, anche per ES01. Il
verificatore CMS dell'approvazione non è un verificatore XAdES delle ricevute.
Il professionista verifica origine, collegamento, esito e segnalazioni nel canale
ufficiale e conserva l'evidenza. LIPE non modifica automaticamente la posizione
del cliente o il risultato VP sulla base del testo di una ricevuta.

## Conservazione nel fascicolo

Per un caso reale usare il suo contesto Studio Archive v2 e una nuova cartella
negli output del run:

```bash
python scripts/lipe_receipt.py --case /absolute/run/inputs/case.json --client-engagement /absolute/client_engagement.json --receipt /absolute/returned/ricevuta.xml --submitted-file /absolute/returned/IT12345678903_LI_00001.xml --output /absolute/run/output/receipt-01
```

I nomi nell'esempio sono fittizi. `--submitted-file` è facoltativo. Le ricevute
arrivano dopo l'avvio del run: i loro byte sono conservati come nuova evidenza
negli output, senza riscrivere l'inventario immutabile degli input iniziali.
Dichiarare la nuova cartella tra gli artefatti del run e aggiornare il suo report
dei dati letti dal modello secondo il contratto Studio Archive. Il caso e le sue
fonti devono comunque corrispondere alle ricevute d'importazione del run scelto.

La nuova cartella contiene:

- `receipt.original`: byte originali della ricevuta, anche se XML non valido;
- `submitted-file.original`: byte del file fornito come trasmesso, se presente;
- `receipt-inspection.json`: hash, ambito selezionato, stato dei controlli,
  valori dichiarati, eventuale archivio, tutte le segnalazioni e limiti;
- `receipt-inspection.md`: lettura professionale con le stesse distinzioni.

Le cartelle esistenti non vengono sovrascritte. Evidenze vuote, non regolari o
oltre 16 MiB sono rifiutate prima della conservazione; documentare separatamente
quel limite e richiedere un formato supportato senza scartare l'originale.
Un file leggibile come byte ma non conforme allo schema produce un rapporto
bloccato e conserva l'originale. La data della ricevuta resta quella dichiarata:
il lettore non inventa un fuso orario se manca.

## Collegamento al file e al periodo

`NomeFile` viene confrontato esattamente con il nome del file fornito. Non
rinominare i file per ottenere una corrispondenza. Un nome uguale può identificare
byte diversi: `FILENAME_MATCH_ONLY` non è una prova crittografica. Il file fornito
è trattato come evidenza opaca; questo passaggio non apre contenitori CAdES,
non verifica la firma sul trasmesso e non confronta frontespizio o VP. Queste
verifiche restano separate. Una differenza di nome è visibile e non viene
corretta automaticamente, anche quando esiste `RifArchivio`.

La ricevuta non contiene il codice fiscale del contribuente o il periodo VP.
Cliente, incarico, anno e trimestre nel rapporto sono l'associazione scelta
dall'operatore, esplicitamente non provata dal solo XML della ricevuta.

Il codice di uscita 0 significa che la lettura strutturale è riuscita, anche
quando l'esito dichiarato è ES03. Non significa invio accettato. Il codice 2
segnala lettura bloccata o nome non coincidente. Errori di contesto, conservazione
o integrità degli schemi interrompono il comando prima di un rapporto valido.

## Quali dati arrivano al modello

Se letti dall'host, ricevuta, nomi dei file, identificativi di trasmissione,
date, PECMessageID, note ed errori entrano nel contesto del modello scelto. Il
file fornito come trasmesso può includere nomi, codici fiscali, intermediari e
importi VP. Il programma locale legge e conserva soltanto i file selezionati,
senza chiamate di rete o al modello; non misura le letture già fatte dall'host.
Il report della sessione deve registrare l'esposizione effettiva, senza promesse
di anonimizzazione automatica o trattamento soltanto locale.
