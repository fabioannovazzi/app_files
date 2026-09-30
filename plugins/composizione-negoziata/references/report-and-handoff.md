# Relazione, esito e attività successive

Usa quando occorre concludere, interrompere o trasferire il lavoro. La conclusione è una valutazione del professionista, non l'ultimo stato di una macchina. Verifica le fonti e l'indice applicabili alla data del caso.

## Advisor: relazione all'impresa e pacchetto di consegna

Produci contenuto effettivo: incarico/perimetro, cronologia essenziale, cause e base documentale, riconciliazioni aperte, ipotesi adottate e limiti, analisi e sensibilità, proposte/risposte/accordi effettivi, esito proposto e ragioni, condizioni ancora da soddisfare, atti e ricevute disponibili, attività residue con responsabili e basi dei termini. Se manca accordo, spiega alternative e handoff; non presentare bozze come impegni delle parti.

Distingui fine delle trattative, formalizzazione dell'esito e attuazione. Il monitoraggio successivo richiede un mandato: cosa osservare, dati necessari, cadenza concordata, responsabili e risposta agli scostamenti. Non promettere notifiche automatiche o obblighi adempiuti senza prova.

## Esperto: relazione finale e consegna del proprio incarico

Ricostruisci nomina e indipendenza con limiti, materiale acquisito, interlocuzioni, verifiche e test effettivamente svolti, prospettive iniziali e successive, trattative e posizioni attribuite, pareri, eventi rilevanti, esito e ragioni. Distingui attività dell'esperto da quelle dell'impresa e dei suoi advisor. Mappa l'indice richiesto alle evidenze; segnala ogni sezione non documentata prima della revisione e firma.

Documenta adempimenti proposti/eseguiti, ricevute, destinatari, consegne, attività e basi della richiesta di compenso quando pertinente. Una richiesta successiva di diventare advisor apre verifica di incompatibilità e nuovo incarico; nessun cambio di ruolo nello stesso fascicolo.

## Persistenza della consegna

Prepara un nodo `draft` con il testo della relazione e `responsibility` uguale al ruolo. Collega tutte le basi usate. Per una ricevuta effettiva importa il documento e registra un nodo `document` con citazione; una ricevuta assente resta `gap`, mai `documented`.

Aggiungi alla richiesta il campo opzionale `closure`:

```json
{
  "outcome": "no_agreement",
  "report_id": "final_report",
  "basis_ids": ["revised_forecast", "negotiation_outcome"],
  "receipt_ids": [],
  "residual_tasks": [
    {"node_id": "filing_receipt_gap", "owner": "Professionista incaricato", "due_basis": "Da verificare su atto e fonte applicabili"}
  ]
}
```

Esiti ammessi: `agreement`, `no_agreement`, `interrupted`, `alternative`. Sono descrizioni del risultato proposto, non certificazioni legali. La relazione deve dipendere dalle basi indicate. Il controllo meccanico rifiuta riferimenti mancanti o già superati; conserva le versioni della consegna. Una variazione delle basi, delle ricevute o delle attività residue riapre il riesame. I gap possono restare, ma devono essere visibili e attribuiti.

Consegna il memo salvato, i collegamenti agli elaborati, le decisioni richieste e il quadro residuo. Per passare a un'altra procedura prepara fonti, analisi, limiti e quesiti; non affermare che `concordato-plan-review` copra ogni procedura alternativa. Chiudere il run archivia la sessione: non firma né deposita e non dimostra chiusura della procedura.

Lo stato `draft_handoff` resta una consegna da rivedere. `reviewed_handoff` richiede una ricevuta Mparanza verificata di accettazione della versione corrente della relazione; un rifiuto successivo la riporta a bozza. `reopened_for_review` indica che una base o un elemento della consegna è cambiato. Nessuno di questi stati attesta la chiusura giuridica.
