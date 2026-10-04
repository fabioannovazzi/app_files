# LIPE — XML approvato e confronto del file fornito

Questa fase prepara un XML non firmato da verificare nel gestionale. Riverifica
l'approvazione professionale della versione e controlla che il file contenga
esattamente frontespizio e importi approvati. Non firma né trasmette una
dichiarazione e non attesta l'accettazione del gestionale o dell'Agenzia.
Le prove professionali e nei gestionali restano pendenti in `acceptance.md`.

## Prima dell'export

Completare la revisione del caso e il frontespizio, seguire `approval.md` e
conservare gli originali `request.json`, `decision.p7s`, `mandate.json` e
`mandate.p7s`. La richiesta autorizza la preparazione dell'XML da verificare nel
gestionale; dichiara espressamente che la qualificazione del software e
l'accettazione non sono attestate. Una vecchia richiesta con una dichiarazione
o vincoli diversi non viene riutilizzata: serve una nuova firma sugli esatti byte.

Una copia di `approval.json` con stato favorevole non autorizza nulla. L'export
legge gli originali e verifica nuovamente firme CMS, certificati, catena, CRL,
mandato, perimetro e scadenza contro l'autorità corrente configurata sull'host.
Ricalcola il caso e ricontrolla fonti, catalogo, file della bozza e report dei dati
effettivamente arrivati al modello. Dati, documenti o dichiarazioni modificate
richiedono una nuova revisione. La finestra di 24 ore della richiesta è una
politica interna, non una scadenza fiscale.

Per questo profilo di importazione serve `CFIntermediario`, con tutti i campi
di impegno e le relative prove del frontespizio. Non usare automaticamente il
codice del contribuente o la sua partita IVA al posto di quello dell'intermediario.
Non ricavare la titolarità o i poteri dal soggetto stampato nel certificato.

## Registro unico dei nomi

L'amministratore aggiunge alla configurazione host `VERA_LIPE_AUTHORITY_CONFIG`
il campo facoltativo `export_registry`, che diventa necessario per l'export.
È il percorso assoluto del file SQLite usato dallo studio per i nomi riservati,
fuori dai run cliente e dai componenti installati. La cartella padre deve già
esistere. Il programma può creare il database in quella posizione; non sceglie
un'altra posizione se manca la configurazione e non riutilizza un database di
un'altra applicazione, studio o origine dei dati.

Usare sempre quel registro per lo stesso insieme di intermediari. Proteggerlo
con i permessi dell'host, inclusi ACL Windows quando applicabili. Non eliminarlo,
azzerarlo o crearne un altro per superare un nome già riservato. Il registro non
è un servizio centrale, non resiste a manomissioni dell'amministratore e non
conosce file creati esternamente. Prima di assegnare un progressivo, lo studio
verifica anche quella storia. Non inventare un progressivo iniziale "sicuro".

Il profilo richiesto dal canale usa `IT` + codice fiscale dell'intermediario +
`_LI_` + cinque cifre da `00001` a `99999` + `.xml`. La scelta delle cinque cifre
è il profilo di importazione richiesto, non l'intera nomenclatura ammessa dal
protocollo di trasmissione: l'allegato ufficiale, sezione 2.2, ammette progressivi
alfanumerici fino a cinque caratteri. Fonti e hash sono in `sources.json`.

La prenotazione è una transazione SQLite esclusiva. Due esportazioni concorrenti
non possono riservare lo stesso nome nel medesimo registro. Se una scrittura
successiva fallisce, il nome resta riservato: un salto nella numerazione è
preferibile al riuso di un nome di cui può esistere una copia parziale. Il record
di prenotazione non afferma che la consegna sia riuscita.

## Generare il file

Il numero nell'esempio è fittizio: usare quello effettivamente confermato dallo
studio e i percorsi delle copie importate nel proprio run.

```bash
python scripts/lipe_export.py export --case /absolute/run/inputs/case.json --frontpage /absolute/run/inputs/frontpage.json --draft /absolute/run/output/lipe-HASH --approval /absolute/run/output/approval-01 --client-engagement /absolute/client_engagement.json --progressive 7 --output /absolute/run/output/xml-01
```

Passare `--catalog` quando il caso contiene riferimenti al catalogo. Per una
prova interamente sintetica, usare `--source-root` al posto del contesto reale,
una policy sintetica e un registro distinto. Non etichettare dati reali o
anonimizzati come sintetici e non configurare autorità reali con chiavi inventate.

La cartella deve essere nuova, separata dalla bozza e dall'approvazione, negli
output del run. Contiene:

- XML non firmato, validato contro l'XSD ufficiale offline;
- `approved-summary.pdf`, copia esatta della sintesi vincolata dalla firma;
- `approval/`, originali e nuova verifica della decisione e del mandato;
- `export.json`, impronte del file, vincoli della versione e controlli di rilettura;
- `export.md`, riepilogo leggibile con limiti e passi professionali residui.

Il serializer usa l'ordine dell'XSD e importi con due decimali e virgola. Omette
importi a zero e campi non applicabili. Ripete il dichiarante e la carica
nell'intestazione quando presenti. La singola comunicazione usa `00001` come
identificativo interno, distinto dal progressivo del nome file. Non inserisce
`FlagConferma` o `IdentificativoProdSoftware`. Situazioni non supportate che
richiederebbero un override restano bloccate; una conferma testuale non le abilita.

Prima di scrivere, il programma rilegge l'XML, confronta ogni campo del
frontespizio e dell'intestazione, ogni periodo e tutti i righi VP con il risultato
approvato, e ricontrolla che il PDF e la versione non siano cambiati. La firma
CMS nella sottocartella approva quella versione: non firma l'XML.

## Confrontare un XML fornito come trasmesso

Se il professionista fornisce l'XML effettivamente usato dal gestionale,
confrontarlo con il riferimento conservato:

```bash
python scripts/lipe_export.py compare --case /absolute/run/inputs/case.json --client-engagement /absolute/client_engagement.json --reference /absolute/run/output/xml-01/IT11111111115_LI_00007.xml --supplied /absolute/returned/transmitted.xml --output /absolute/run/output/comparison-01
```

Il confronto conserva entrambi i byte originali e produce `comparison.json` e
`comparison.md`. Legge solo XML; non apre contenitori CAdES `.p7m` o ZIP. Un file
non leggibile o non conforme allo schema è conservato con un rapporto bloccato.
Per un contenitore firmato, usare la copia XML ottenuta dal canale professionale
autorizzato e mantenere anche il contenitore come evidenza separata.

Contribuente, partita IVA, anno e periodi devono coincidere prima del confronto
numerico. Ogni rigo è confrontato al centesimo per periodo: errori mensili che
si compensano sul totale trimestrale rimangono visibili. Elementi assenti e zero
espliciti sono numericamente equivalenti nel confronto, ma la loro differenza
di rappresentazione viene elencata, senza certificarne l'accettabilità fiscale.

Date d'impegno, rappresentanti, intermediari, flag, metodi e identificativi del
software non vengono ignorati perché gli importi coincidono. Ogni differenza
resta da esaminare. L'XML può contenere una firma senza che questo lettore ne
verifichi autenticità o revoca. Il confronto non autentica neppure il riferimento
scelto dall'operatore: conservare il collegamento al packet di export e alla sua
approvazione. La ricevuta dell'Agenzia è una fase distinta (`receipts.md`).

Il codice di uscita 0 significa che i campi confrontati coincidono. Il codice 2
segnala differenze, identità o periodi incompatibili, oppure una lettura bloccata.
Nessuno dei due codici attesta invio o accettazione. Non inviare dichiarazioni
per qualificare questo software.

## Quali dati arrivano al modello

Se aperti dall'host, XML, frontespizio, identificativi del contribuente e
dell'intermediario, importi VP, PDF e prove dell'approvazione possono arrivare al
modello scelto. Il confronto può esporre gli stessi campi dei due documenti e
le loro differenze. Il registro dei nomi conserva nome, ambito cliente/incarico,
data e hash della richiesta e dell'XML; una lettura indiscriminata può esporre
altri casi dello studio e non è necessaria per l'export selezionato.
I programmi locali non chiamano modelli o servizi di rete. Registrare le
letture effettive nel report del run, senza promettere anonimizzazione o
trattamento solo locale da parte dell'host. Un aggiornamento successivo del
report cambia i vincoli per una futura esportazione e richiede nuova revisione;
non riscrive la prova storica già conservata nell'export.
