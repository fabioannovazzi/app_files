> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# LIPE — frontespizio e approvazione della versione

Questa fase prepara una richiesta di revisione e verifica una decisione firmata
esternamente. Non abilita da sola l'export XML reale, non firma una dichiarazione
e non trasmette dati. Le qualificazioni professionali, del gestionale e dell'host
restano quelle effettivamente documentate in `acceptance.md`.

## Frontespizio

Compilare `schemas/frontpage.schema.json` da fonti importate nello stesso run
Studio Archive del caso. Confermare anno, contribuente, partita IVA, eventuale
dichiarante e codice carica, società dichiarante e impegno dell'intermediario.
Ogni valore compilato, salvo i due flag di firma proposti, richiede una citazione
di fonte. I flag non rappresentano firme digitali sull'XML. Le interpretazioni
delle cariche e dell'impegno sono decisioni professionali, non classificazioni
dedotte da una parola o dal codice fiscale.

I controlli meccanici applicano formato e carattere di controllo degli
identificativi, abbinamento dichiarante/carica, completezza dell'intermediario,
anno di imposta e finestra della data di impegno. Le date di presentazione usano
Europe/Rome, anche su Windows. La fonte è la specifica tecnica IVP18 2024;
i caratteri di controllo seguono gli articoli 7 e 9 del DM 23 dicembre 1976.
I riferimenti sono in `sources.json`. La finestra di anno non abilita correzioni
storiche, regimi o periodi fuori dal perimetro supportato.

Formato e carattere di controllo non verificano esistenza, titolarità o
corrispondenza in Anagrafe. Registrare per ogni identificativo la fonte della
verifica effettivamente svolta e la conferma professionale; non inventare una
risposta del servizio Agenzia Entrate. I controlli CF e partita IVA sono distinti.
LIPE verifica la presenza della citazione e l'integrità della fonte, non decide
se una schermata o un documento attestino correttamente quella corrispondenza.
Il revisore conferma questo significato. Una data di revisione non può precedere
la verifica che dichiara di avere esaminato.

## Preparare la richiesta

Generare e aprire la bozza, verificare Excel/PDF, quadrature, anomalie e decisioni.
Completare il report effettivo sui dati arrivati al modello nella cartella output
del run. La fase controlla report JSON, relativa evidenza, identità del run e
corrispondenza del Markdown tramite il validatore esistente di Studio Archive.
Non inventare una dichiarazione di mancata esposizione per superare il controllo.

```bash
python scripts/lipe_approval.py prepare --case /absolute/run/inputs/case.json --frontpage /absolute/run/inputs/frontpage.json --client-engagement /absolute/client_engagement.json --draft /absolute/run/output/lipe-HASH --output /absolute/run/output/approval-request-01
```

Usare i percorsi reali delle copie importate; aggiungere `--catalog` per un caso
collegato al catalogo. `--source-root` è disponibile solo per esempi dichiarati
sintetici. Il packet contiene `request.json`, `review-snapshot.json`,
`frontpage.json` e una richiesta leggibile. Non contiene un'approvazione.
La cartella deve essere nuova e separata dalla bozza: i file già presenti non
vengono sovrascritti.

La richiesta vincola cliente, incarico, anno, trimestre, origine dei dati, caso,
frontespizio, fonti, risultato ricalcolato, revisione del catalogo, motore, regole,
schema XML, componente crittografico e ogni file della bozza. Una modifica richiede
una nuova revisione. La scadenza di 24 ore è una politica operativa interna di
LIPE, non un termine fiscale. Il professionista firma esternamente gli esatti byte
di `request.json` con firma CMS DER separata; conversioni di newline o altre
modifiche non sono ammesse. Non consegnare a LIPE chiavi private o password.

## Autorità dello studio

L'amministratore dello studio deve predisporre indipendentemente una policy
conforme a `authority-policy.schema.json`, il percorso assoluto di OpenSSL 3,
radici fidate e CRL correnti complete. La configurazione è indicata dalla variabile
host `VERA_LIPE_AUTHORITY_CONFIG`; non è un argomento scelto dal caso.
Il JSON contiene esattamente `policy`, `openssl`, `trusted_roots`, `crls`;
gli ultimi tre sono percorsi assoluti a file installati. Configurazione, provider
e materiale fiduciario devono risiedere fuori dal run cliente e dai componenti.
La protezione di queste risorse dipende dai permessi amministrativi dell'host:
essere fuori dalla cartella cliente non rende inviolabile una policy modificabile
dallo stesso utente del sistema operativo.

Il mandato segue `professional-mandate.schema.json`: policy, perimetro esatto,
professionista, certificato, azione, validità e riferimenti alle prove dei poteri.
Un amministratore il cui certificato è già nella policy firma gli esatti byte del
mandato. Il certificato del professionista firma la richiesta. I due ruoli non
vengono dedotti dal nome nel certificato. La dichiarazione firmata dello studio
stabilisce i poteri; LIPE non consulta autonomamente albi o registri professionali.
Il mandato e i certificati non possono essere revocati nella policy corrente.

Non creare una policy reale, inserire un proprio certificato come amministratore,
creare mandati o firmare decisioni per aggirare un'autorità mancante. I certificati
creati dai test sono sintetici e non vengono distribuiti come autorità dello studio.

## Verificare e conservare

```bash
python scripts/lipe_approval.py accept --case /absolute/run/inputs/case.json --frontpage /absolute/run/inputs/frontpage.json --client-engagement /absolute/client_engagement.json --draft /absolute/run/output/lipe-HASH --request /absolute/run/output/approval-request-01/request.json --signature /absolute/returned/decision.p7s --mandate /absolute/returned/mandate.json --mandate-signature /absolute/returned/mandate.p7s --output /absolute/run/output/approval-01
```

La verifica riusa il componente CMS già presente in Vera (`patent-box-review`):
contenuto esatto, algoritmi ammessi, uso della chiave, catena e revoche con CRL.
Non scarica certificati o revoche dalla rete e non installa OpenSSL. Le prove
mancanti o non attuali impediscono l'approvazione. I documenti restituiti dal
firmatario sono letti come originali limitati in dimensione, verificati e copiati
nella nuova cartella di approvazione con hash, insieme al mandato, materiale
fiduciario, policy, snapshot e `approval.json`. Non sono retroattivamente aggiunti
all'inventario immutabile degli input originari del run.

Il caso viene ricalcolato e confrontato con la bozza prima e dopo la verifica.
La ricevuta distingue verifica crittografica, poteri dichiarati dallo studio,
qualifica della firma non testata e mancata firma/invio della dichiarazione.
Un export successivo dovrà riverificare gli originali, lo stato corrente della
policy/revoche e tutti i vincoli; un `approval.json` modificabile non è un token
fidato. Il serializer reale e la gestione delle ricevute di invio restano fasi
distinte ancora da implementare e qualificare.

## Quali dati arrivano al modello

Se aperti dall'host, frontespizio e fonti, verifiche anagrafiche, nomi e identificativi
dei dichiaranti/intermediari, richiesta firmata, certificati pubblici, mandato e
riferimenti ai poteri possono entrare nel contesto del modello scelto. La verifica
crittografica locale non invoca modelli o rete e non richiede chiavi private.
Il report del run deve descrivere ciò che l'host ha realmente letto; la ricevuta
CMS non misura l'esposizione al modello, né certifica conformità GDPR.
