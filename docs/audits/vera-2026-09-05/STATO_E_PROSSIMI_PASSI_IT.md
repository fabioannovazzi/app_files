# Vera — stato e prossimi passi verificabili

Aggiornamento: 6 settembre 2026. **Il progetto T01–T20 non è concluso.**
Questo documento orienta la continuazione; non sostituisce né riduce i requisiti
di `VERA_REMEDIATION_HANDOFF.md`. Le autorizzazioni già date alle correzioni e
alle proposte professionali restano valide. Non occorre richiederle di nuovo.
Non sono autorizzati merge, deploy o pubblicazione.

Il goal è nuovamente attivo. L'utente ha autorizzato esplicitamente i subagenti
Astra Medium e ha chiesto di riprendere. Sono iniziate una nuova interpretazione
delle fonti Bandi e una verifica indipendente delle attività residue. I due PDF
storici mancanti limitano soltanto i test Centrale Rischi che li richiedono;
non bloccano le altre correzioni. «Revisione professionale» indica il controllo
dei risultati prodotti rispetto alle fonti e alle aspettative già approvate,
non una qualifica o certificazione richiesta all'utente.

Ultimo avanzamento: i sei casi di campionamento previsti hanno esecuzioni
gestite documentate. Sono stati verificati dieci casi Management Control, con
una nuova consegna completa di 20 artefatti, e sei varianti XML. I casi INPS
L01/L02, Registro Imprese L05, Concordato L06/L07 e avviso incompleto L08 hanno
prodotto pacchetti tecnici con limiti e punti irrisolti espliciti.

Passive Invoice Audit 0.1.4 corregge tre errori riprodotti: convenzione numerica
non applicata a tutte le colonne monetarie, rifiuto dei negativi fra parentesi
e sostituzione di uno zero reale con un importo alternativo. Passano 16 casi
gestiti e 103 test del componente, con un test saltato. Sono stati corretti anche
la copertura incompleta dei PDF misti, il dominio ufficiale SARI e il rifiuto
delle dichiarazioni DTD/entity nei documenti OOXML UTF-16. Le prove precedenti
rimangono conservate in `RESUMED_IMPLEMENTATION.md`.

Le tre varianti locali del pacchetto Vera corrispondono alla sorgente aggiornata;
i 18 server MCP si avviano ed elencano gli strumenti. Gli hash sono in
`passive-014-identities.json`. Il test completo del repository con copertura è
ancora in esecuzione su una copia congelata; le successive modifiche Passive
hanno verifiche separate. Nessun risultato globale è ancora dichiarato.

I quattro contributi Bandi validi sono raccolti in
`BANDI_CONTRIBUTI_RIPRESA_IT.md`. È emersa una lacuna concreta: i contributi
alle fonti non costituiscono ancora i report dei casi L03/L04. Questa fase è
in lavorazione usando le aspettative già approvate; non occorre ripetere
l'autorizzazione alle sessioni nuove. Nulla è stato pubblicato.

Le sezioni successive conservano risultati precedenti e i relativi limiti;
per l'identità corrente dei pacchetti usare il riferimento appena indicato.

## Cosa dimostrano gli ultimi risultati

- Sales Plan 0.1.7 conserva come indisponibili sconti mancanti, ricavi netti e
  margini dipendenti; non presenta somme parziali come totali completi. Gli
  zeri espliciti restano valori conosciuti. Il caso gestito prima/dopo conserva
  gli stessi input e il risultato errato originale.
- I 29 test Sales Plan passano; la copertura del motore è 86,06%. Due copie
  temporanee con difetti reintrodotti fanno fallire rispettivamente due e
  quattro test. La sorgente di produzione non è stata alterata dalle prove.
- Il controllo Mypy esplicito passa su 21 file; Bandit non rileva problemi
  di severità media o alta su quel perimetro. Non è una certificazione
  dell'intero repository.
- Le tre varianti ZIP Vera sono state rigenerate dalla sorgente e verificate;
  18 server MCP hanno completato avvio ed elenco strumenti. Gli hash esatti
  sono in `sales-017-final-identities.json` nella cartella di evidenze esterna.
- Nei tre casi contabili negativi A05/A06/A07, quattro partite restano senza
  allocazione e con richiesta di evidenza. Il controllo valutario fallito di
  A06 è conservato: non va trasformato in un pagamento accettato.
- Bandi dispone di un nuovo run con quattro fonti importate e hash verificati,
  incluso l'avviso sul finanziamento. Le fonti sono ancora candidate; non è
  una conclusione sull'ammissibilità.

## Domande e risposte

**Abbiamo finito le correzioni?**

Sono state implementate e verificate molte correzioni concrete. Non è ancora
dimostrata la chiusura di ogni requisito T01–T20. I risultati tecnici non
sostituiscono la qualificazione dei sistemi ospitanti o la revisione dei
risultati professionali.

**Devo approvare di nuovo le proposte italiane?**

No. Le aspettative A01–A08 e L01–L08 già approvate rimangono tali. Il registro
distingue quell'approvazione dalla revisione dei risultati effettivamente
generati e dalle eventuali nuove decisioni sostanziali.

**I test sono tutti verdi?**

No. L'ultima suite package/update ha 385 successi e cinque fallimenti. Il
fallimento relativo alla versione Sales Plan è stato poi corretto e verificato.
Restano due prove Clara fermate dal DNS PyPI, il ritardo del manifesto pubblico
Clara rispetto alla cache installata e drift in quattro sorgenti Clara esterne
alla correzione. Il precedente risultato globale del repository ha copertura
79,50%; le prove mirate successive non lo trasformano in un pass globale.

**Il cambio ad Astra Medium è stato applicato?**

Sì, è stato confermato dall'utente. Non servono altre domande sul cambio modello.
Questo non qualifica automaticamente Astra come sostituto del worker isolato:
quel percorso ha un proprio contratto, prove e selezione vincolata.

## Continuazione ordinata

| Perimetro | Prossima azione concreta | Cosa non basta per chiudere |
| --- | --- | --- |
| T08 — worker isolato | Completare la prova del percorso nascosto di lettura immagini e una normale esecuzione sul profilo candidato; conservare isolamento e prove negative. | Aggiornare hash/versioni, oppure riutilizzare la sola prova dell'allegato CLI. |
| T10/T19 — browser | Riprendere dal collegamento Settings → Computer Use → Google Chrome, quando disponibile; verificare runner, byte scaricati e casi di login/origine/selettori cambiati. | Evento download, presenza di metodi o interazione manuale con il solo form. |
| T13 — dipendenze | Usare la mappa delle responsabilità e le prove di import; rimuovere dipendenze solo con prova di non raggiungibilità e beneficio. | Dimensione elevata o assenza di un import testuale. I moduli `.source` Open Item sono attivi. |
| T14–T16 — risultati | Completare la corrispondenza fra aspettative approvate, output normali, affermazioni e fonti; mantenere denominatori ed etichette non disponibili espliciti. | Receipt, fixture o `report_ready` come prova di correttezza professionale. |
| T17 — Bandi | I metadati delle quattro fonti sono stati corretti nel run `run_3634d7fef969b5df85a3f4e8`; i quattro contributi validi sono registrati. Completare gli output dei casi L03/L04 con i fatti sintetici effettivi e rendere esplicite le valutazioni ancora da rivedere. | Inventare un identificativo di sessione fresca o accettare automaticamente il contributo. L'autorizzazione ai subagenti è stata ricevuta. |
| T17/T18 — revisione professionale | Presentare i risultati effettivi e registrare le decisioni sostanziali, inclusi disaccordi e punti irrisolti. | Riutilizzare l'approvazione delle aspettative come approvazione di un nuovo risultato. |
| T18 — Centrale Rischi | Recuperare gli originali esatti `camera_webinar` e `historical_examples` richiesti dal gold manifest e rieseguire i casi associati. | Sostituire un PDF simile o modificare gli hash del benchmark. |
| T20 — integrazione | Riconciliare solo modifiche pertinenti, conservando quelle altrui; verificare sorgenti, privacy, ZIP e controlli applicabili sullo stesso stato finale. | Una suite parziale o un successo di packaging come prova di pubblicazione. |

Il difetto di import del generatore Clara con `--case-dir` è riprodotto anche
fuori da pytest: il caricamento del runtime di lineage non risolve `case_store`.
Non è stato nascosto con un monkeypatch. Le istruzioni del repository impongono
stop e segnalazione per modifiche di produzione volte a risolvere errori di
import dei test; la correzione di produzione rimane aperta. I nove fallimenti
della UI legacy non autorizzano lavoro su una superficie esplicitamente esclusa.

## Dove riprendere

- Requisiti completi: `VERA_REMEDIATION_HANDOFF.md`.
- Stato dettagliato e cronologia, con fallimenti conservati:
  `IMPLEMENTATION_STATUS.md` e `INTEGRATED_DIAGNOSTIC.md`.
- Output contabili: `ACCOUNTING_REVIEW_CASES.md` e `SOURCE_INTAKE_FINDING.md`.
- Fonti e casi professionali: `PROFESSIONAL_REVIEW_CASES.md`.
- Sistemi ospitanti e visualizzazione: `HOST_QUALIFICATION.md` e
  `VISUAL_ACCEPTANCE.md`.
- Dipendenze: `RESPONSIBILITY_MAP.md`.

Questi file sono in
`/Users/fabio/Documents/GitHub/app_files/docs/audits/vera-2026-09-05/`.
Log, output sintetici e ricevute voluminosi sono in
`/private/tmp/vera-remediation-01a07083/`: controllarne la presenza prima di
usarli, perché la cartella temporanea può essere rimossa dal sistema.
Non ricreare prove mancanti come se fossero originali e non dichiarare completo
il goal finché i requisiti non sono sostenuti da evidenza del perimetro corretto.
