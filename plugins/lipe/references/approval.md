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

## Mostrare e confermare la proposta

Preparare la richiesta con `lipe_approval.py prepare --case <case> --frontpage
<frontpage> --draft <draft> --client-engagement <context> --output <request>`.
Mostrare `review-request.md`, frontespizio, righi VP, anomalie e scelte. Chiedere
se questa proposta va bene e se si può proseguire con l'XML non firmato.

Dopo la risposta effettiva, eseguire `lipe_approval.py accept` con gli stessi
parametri, `--request <request/request.json>`, `--reviewer <attore effettivo>`,
`--confirmation-ref <riferimento della risposta> --confirmed` e una nuova
cartella `--output`. Nessun ruolo professionale, firma, certificato o mandato è
richiesto. L'assistente registra la risposta: l'utente non compila JSON.

L'export ricalcola i dati e verifica richiesta, risposta e impronte di fonti e
bozza. Una proposta cambiata non eredita la conferma. Il record non autentica
identità, qualifiche o responsabilità professionali e non firma né trasmette XML.
La scadenza della richiesta è una politica operativa del prodotto, non un termine fiscale.

Il registro unico dei nomi dei file rimane separato dal run cliente ed è indicato
in `VERA_LIPE_EXPORT_REGISTRY`. Non creare un registro sostitutivo per aggirare
una collisione. Questo percorso non richiede una policy di autorità o materiale
crittografico. Conservare la distinzione tra controllo tecnico, scelta dell'utente
ed effettiva firma o trasmissione, che non sono eseguite da LIPE.
