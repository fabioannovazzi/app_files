> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# LIPE — XML della proposta confermata

L'export produce un XML non firmato per l'importazione nel gestionale. Non
trasmette dati e non firma dichiarazioni. L'utente conferma la versione esatta
mostrata, non una responsabilità professionale generale.

## Prima dell'export

Completare la bozza e il frontespizio con fonti e scelte esplicite. Seguire
`approval.md` per mostrare il riepilogo e registrare la risposta effettiva.
La cartella scelta contiene `request.json`, `decision.json`, `approval.json`
e `review-snapshot.json`. Nessuna firma CMS, qualifica, policy di autorità o
mandato è richiesta per confermare la proposta o produrre l'XML.

Ogni export ricalcola i dati e ricontrolla i byte della bozza, le fonti, la
conferma e i riferimenti alla versione. Cambiamenti invalidano la conferma;
un generico ordine di continuare non sostituisce una scelta materiale irrisolta.

## Registro unico dei nomi

Impostare `VERA_LIPE_EXPORT_REGISTRY` al registro dello studio già selezionato,
fuori dai run cliente e dai componenti installati. Non usare un registro
sostitutivo per aggirare collisioni. Il progressivo deve essere quello effettivamente
confermato per l'intermediario; la storia esterna resta sconosciuta.
La prenotazione è transazionale e rimane consumata se una scrittura successiva
fallisce. Il registro è indipendente da qualsiasi configurazione di firme.

## Generare il file

```bash
python scripts/lipe_export.py export --case <case.json> --frontpage <frontpage.json> --draft <draft> --approval <confirmed-proposal> --client-engagement <context.json> --output <new-xml-folder> --progressive <confirmed-unused-number>
```

Il risultato conserva XML non firmato, la sintesi PDF esatta della proposta,
i record della decisione ed `export.json`/`export.md`. Schema, frontespizio,
periodi, righi VP e tutti gli importi sono riletti dall'XML e confrontati con i
risultati confermati. La risposta registrata non autentica identità o qualifiche,
non certifica correttezza fiscale e non prova invio o accettazione del gestionale.

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
