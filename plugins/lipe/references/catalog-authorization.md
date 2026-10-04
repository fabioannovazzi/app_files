# LIPE — autorizzazioni del catalogo

Un catalogo nuovo dichiara l'origine delle interpretazioni. Con `REAL`, ogni
registrazione, revisione, revoca, contestazione e decisione del curatore richiede
firme CMS esterne. La stringa con il nome del revisore non attribuisce un ruolo.
Le prove sintetiche possono usare `SYNTHETIC`; aggiungere `--require-signatures`
per provarne anche le autorizzazioni. Non etichettare dati reali come sintetici.

```bash
python scripts/lipe_catalog.py init --catalog /absolute/studio/catalog/lipe.sqlite3 --studio-id STUDIO_ID --data-origin REAL --minimum-confidence SOGLIA_SCELTA --output /absolute/studio/catalog/init.json
```

Lo studio sceglie la soglia. Il comando crea un catalogo vuoto e restituisce il
`catalog_id` da configurare; non attribuisce poteri professionali. I cataloghi
precedenti restano leggibili, ma la loro origine non è stabilita e non possono
alimentare nuovi calcoli: conservare lo storico e far rivedere le interpretazioni
in un nuovo catalogo. Non modificare i metadati per simularne la migrazione.

## Autorità indipendente dello studio

L'amministratore configura `VERA_LIPE_CATALOG_AUTHORITY_CONFIG` con il percorso
assoluto di un JSON conforme a `schemas/catalog-authority.schema.json`, fuori
dalla cartella del catalogo, dai packet e dai componenti installati. L'agente
non crea questa autorità durante una pratica, non inventa certificati e non
modifica ruoli per sbloccare un'operazione.

Il JSON contiene `policy_id`, `catalog_id`, `studio_id`, `data_origin`, percorsi
assoluti di OpenSSL 3, radici e CRL, impronte revocate e incaricati. Ogni incaricato
ha nome, impronta SHA-256 del certificato, ruoli, livelli ammessi (`CLIENT`,
`STUDIO`, `CENTRAL`), `all_clients` e `client_ids`. I provider devono essere file
regolari indipendenti; per un eseguibile installato tramite collegamento usare
il percorso reale del file.

| Operazione | Firme richieste |
|---|---|
| Registrare/rivedere una classe cliente o studio | `PROFESSIONAL` del livello; per il cliente anche l'esatto cliente autorizzato |
| Registrare/rivedere una classe centrale | `PROFESSIONAL`, `CURATOR` e `DISCLOSURE_REVIEWER`, tutti per `CENTRAL` |
| Revocare una classe cliente o studio | `PROFESSIONAL` del livello e cliente applicabile |
| Revocare una classe centrale | `CURATOR` per `CENTRAL` |
| Aprire una contestazione che blocca tutti i livelli | `PROFESSIONAL` per `STUDIO` |
| Risolvere una contestazione | `CURATOR` per `CENTRAL` |

Una persona può coprire più ruoli solo se lo studio glieli assegna. Il nome nella
decisione deve coincidere con quello associato al certificato nella policy.
Il soggetto del certificato non prova iscrizione all'albo, incarico, correttezza
della classe o assenza di dati privati. Proteggere policy, database e prove con
i permessi dell'host, incluse le ACL Windows. L'applicazione non difende da un
amministratore che può sostituire codice, policy e database.

## Preparare, firmare e applicare

Preparare `operation.json` con l'operazione esatta e i contenuti già esaminati
in `code-catalog.md`. I campi sono:

- `RECORD`: `kind`, `entry_id`, `entry` completo, `supersedes` (null se nuova).
- `REVOKE`: `kind`, `entry_id`, `revoked_revision`, `allow_fallback`, `review`.
- `DISPUTE`: `kind`, `key` con software/lato/codice, `sources`, `evidence`, `review`.
- `RESOLVE_DISPUTE`: `kind`, `dispute_hash`, `selected_revision`, `curator_review`.

Non includere timestamp generati, oggetti conservati o una presunta autorizzazione.

```bash
python scripts/lipe_catalog_authorization.py --catalog /absolute/studio/catalog/lipe.sqlite3 --operation /absolute/studio/catalog/operation.json --output /absolute/studio/catalog/review-01
```

Leggere l'intero `request.md` e le fonti originali. Il packet include gli esatti
byte `request.json` e `required-roles.json`. Prepararlo non valida la classe e
non modifica il catalogo. I firmatari firmano esternamente `request.json` con
CMS detached DER, conservate nel packet come `decision-*.p7s`: da uno a otto
firmatari distinti. Nessuna chiave privata entra in LIPE. Non cambiare il file.

Aggiungere `--approval /absolute/studio/catalog/review-01` al comando `record`,
`revoke`, `dispute` o `resolve-dispute`, mantenendo gli stessi valori e la testa
esatta del catalogo. La richiesta vincola metadati, autorità e versione di codice
e schemi; scade dopo 24 ore, come politica interna e non come termine di legge.

Nella transazione, LIPE verifica contenuto, firme, catena, CRL correnti, revoche,
nomi, ruoli, livelli e clienti. Ricontrolla policy e scadenza dopo la verifica.
Ogni modifica richiede una nuova decisione; non aggiornare automaticamente le
impronte di una richiesta firmata. Anche il ripiego su un livello inferiore
dopo una revoca deve essere autorizzato nella decisione firmata.

## Prova storica e limiti

Gli eventi conservano `ROLES_VERIFIED_AT_COMMIT`, firmatari, ruoli e verifiche.
`<catalogo>.authorizations` conserva richiesta, firme, policy e materiale di
fiducia originali. Mantenere questa cartella, `.sources` e database insieme.
La lettura controlla l'integrità delle prove; non riverifica le firme storiche
né attesta che incarichi e certificati siano ancora validi. Togliere un ruolo
impedisce nuove scritture; non riscrive il passato. Revocare esplicitamente la
classe quando la sua applicabilità è contestata.

Le misure di primo passaggio e le risposte attribuite nelle misurazioni non
modificano classi e non ereditano queste garanzie. Conservano la propria origine
`REAL`/`SYNTHETIC` e lo stato di attribuzione. Il calcolo richiede che l'origine
del catalogo delle classi coincida con quella del caso.

Le firme non giudicano fiscalità o riservatezza. Le revisioni del curatore e di
divulgabilità devono essere effettive. Nessuna promozione automatica, pubblicazione
o sincronizzazione fra studi. Il percorso non è ancora qualificato da uno studio
reale e non attesta una firma qualificata.

## Quali dati arrivano al modello

Se aperti, classi, citazioni, fonti, identificativi cliente/studio, nomi, certificati,
richieste, firme e policy possono entrare nel modello dell'host. La policy può
contenere altri incaricati: leggerla solo se serve al lavoro autorizzato. Le
firme non anonimizzano. I programmi locali non chiamano modelli o reti. Registrare
le letture effettive nel report del run quando il catalogo è usato in una pratica.
