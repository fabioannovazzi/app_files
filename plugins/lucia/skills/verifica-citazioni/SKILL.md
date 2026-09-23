---
name: verifica-citazioni
description: Use when Lucia must check citations and legal propositions in a supplied or drafted document against Italian or otherwise applicable statutes, judgments and authorities, including identity, full text, temporal version, quoted support and inaccessible sources.
---

# Verifica citazioni, fonti e affermazioni

Controlla il documento e le fonti, non soltanto la plausibilità dei numeri.
Un articolo esistente o una sentenza trovata non prova che sostengano ciò che
il documento afferma. La lingua italiana non determina diritto applicabile o foro.
Il modello seleziona e interpreta le fonti; gli helper controllano soltanto copie,
citazioni, riferimenti e coerenza del registro. Non c'è una banca dati legale
incorporata, un collegamento a CourtListener o un server di Lucia/Mike.

## Incarico e fonti

Identifica il documento/versione da controllare, il perimetro, la giurisdizione,
il periodo dei fatti e le proposizioni sostenute dalle citazioni. Se la richiesta
è un nuovo parere o un quesito da risolvere, usa il percorso completo
`../quesito-legale-fiscale/SKILL.md`: il presente registro può documentarne i
controlli, senza sostituire o duplicare il metodo condiviso di ricerca e review.

Per il controllo di un documento già esistente leggi integralmente
`../legal-tax-answer-review/SKILL.md` e applica la review canonica una sola volta.
Integra il registro locale qui sotto nel lavoro richiesto. Non considerare un
JSON valido una review giuridica completata.

Usa la ricerca già disponibile nell'host oppure fonti fornite dall'avvocato.
Ricerca solo riferimenti giuridici e questioni generali: non inserire nomi,
documenti o fatti riservati del cliente nelle query pubbliche. Non creare account,
aggirare accessi o installare un backend per raggiungere una fonte.

Leggi `references/fonti-italiane.md`. Le destinazioni sono punti di accesso, non
una selezione esaustiva né un elenco di fonti automaticamente pertinenti. Per
ogni fonte registra ciò che hai davvero aperto, provenienza, data di consultazione,
versione e limiti. Uno snippet, una massima o un riassunto sono estratti; non
registrarli come testo integrale della decisione. Se non raggiungi il testo,
registra "non accessibile", non "inesistente" o "verificata".

Per una norma controlla atto, numero/data, articolo/comma, testo del periodo
rilevante e disciplina transitoria se incide sul caso. Per una decisione controlla
organo, sezione, natura del provvedimento, numero/anno e date effettivamente
riportate; distingui deposito/pubblicazione da udienza. Leggi motivazione,
fattispecie, limiti ed eventuali sviluppi pertinenti alla domanda. Non promuovere
una massima a regola universale né una decisione isolata a orientamento consolidato.

## Registro collegato alle prove

Conserva localmente il documento e i testi delle autorità realmente acquisiti,
con i metadati necessari a ritrovarli. Non spacciare una trascrizione parziale per
un originale integrale. Se nuove fonti arrivano dopo la preparazione, crea una
nuova run e conserva quella precedente; non alterare le copie o i checksum.

Usa l'ambiente condiviso e il contratto locale in
`../revisione-contratti/references/document-workflow.md`. Prepara i file con il
motore `revisione-documentale`, poi identifica separatamente i documenti le cui
citazioni devono essere controllate:

```bash
python scripts/legal_documents.py prepare --run-dir /absolute/pratica/fonti-001 --workflow revisione-documentale --file /absolute/pratica/memoria.docx --file /absolute/fonti/provvedimento.pdf --topic "Citazioni e proposizioni"
python scripts/legal_citations.py scaffold --run-dir /absolute/pratica/fonti-001 --document D001 --scope "Citazioni giuridiche della memoria, periodo del caso e limiti dichiarati"
```

Leggi `scripts/legal_citations.schema.json` e compila `citations.json`:

- `inventory`: documenti controllati, ancore effettivamente lette e limiti. Mantieni
  visibile una pagina ancora da esaminare anche se altre citazioni sono risolte.
- `authorities`: identità della fonte, tipo, URL realmente consultato o vuoto per
  una fonte fornita, `source_id` della copia, stato di accesso, data, versione,
  ancore lette e limiti. Per testo inaccessibile usa `source_id: null`, nessuna
  ancora letta e la ragione del mancato accesso.
- `claims`: proposizione da controllare, citazione esatta nel documento, periodo
  pertinente e correzione proposta o motivazione per conservarla.
- Ogni `check` collega una fonte e separa identità (`matched`, `mismatch`,
  `unresolved`), versione (`applicable`, `wrong-version`, `unresolved`) e supporto
  (`supports`, `partial`, `contradicts`, `does-not-address`, `unresolved`). Cita i
  passaggi della fonte, distinti dal documento sotto esame, e spiega ragionamento,
  applicabilità ed eccezioni. Un numero corretto non implica supporto corretto.

Non scrivere un esito verificato se il testo è inaccessibile o se hai solo un
estratto insufficiente. Una fonte sbagliata va identificata e corretta con prove;
una fonte non trovata resta irrisolta. Conserva tutte le fonti effettivamente
citate per la stessa proposizione, anche se una è contraria o non pertinente.

```bash
python scripts/legal_citations.py render --run-dir /absolute/pratica/fonti-001
```

Il rapporto `citations.html` mostra documento, fonte, passaggio e giudizio
motivato. Gli esiti sintetizzano soltanto i giudizi dichiarati dal modello e il
loro supporto nel registro; il codice non interpreta il diritto. "Supporto
riscontrato" richiede una fonte dichiarata integrale e letta, identità/versione
pertinenti e passaggi di supporto; non significa validazione professionale.

## Chiudere il controllo

Controlla ogni collegamento fonte/proposizione anche semanticamente. Evidenzia
citazioni errate, fonti insufficienti, versioni non pertinenti e ricerche residue.
Se richiesto, correggi il Word tramite la skill Documents/Word dell'host e il
contratto `../revisione-contratti/references/word-handoff.md`, preservando originale
e revisioni. Non sostituire numeri o massime con ricordi plausibili.

Consegna rapporto, fonti acquisite consentite, correzioni e lacune. Per domande
ancora aperte usa `matter-progress.md` nella directory condivisa dei documenti.
Non bloccare l'inventario o le correzioni già supportate per una sola fonte
inaccessibile. Firma, deposito e decisioni professionali restano all'avvocato.
