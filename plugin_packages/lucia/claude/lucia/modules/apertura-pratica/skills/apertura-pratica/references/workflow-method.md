> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Apertura pratica · metodo

## Confine del lavoro

Una pratica è l'unità professionale. Un cliente può avere più pratiche e una
pratica può includere cliente, parte assistita, controparti, soggetti collegati,
autorità e altri professionisti. Non fondere automaticamente soggetti omonimi e
non usare il nome della cartella come prova del ruolo.

## Giudizio model-led

Usa ragionamento model-led per proporre:

- identità e ruolo dei soggetti;
- materia, obiettivo, fatti e postura procedurale;
- candidati del controllo conflitti;
- perimetro ed esclusioni dell'incarico;
- possibili scadenze, fatto generatore e autorità rilevante;
- applicabilità AML, esigenze di riservatezza e informazioni mancanti;
- struttura del fascicolo.

Collega ogni proposta alle evidenze e conserva ambiguità e interpretazioni
alternative. Una proposta plausibile non diventa un fatto confermato.

## Controlli meccanici

Usa codice deterministico soltanto per schema, identificatori univoci, hash,
dimensioni, riferimenti chiusi, percorsi relativi sicuri, duplicati esatti,
completezza delle decisioni, stato delle review e coerenza dei digest. Questi
controlli non possono dichiarare l'assenza di conflitti, scegliere la disciplina
applicabile o confermare una scadenza.

## Stato

- `blocked`: manca una condizione necessaria o esiste una decisione negativa.
- `partial`: il dossier è utile ma restano fatti o verifiche non bloccanti.
- `ready_for_review`: il pacchetto può essere esaminato dall'avvocato.
- `ready_to_open`: i controlli meccanici sono superati e le quattro review
  correnti su conflitti, incarico, scadenze e apertura sono accettate.

`ready_to_open` non significa assenza certificata di conflitti, correttezza
legale dell'incarico o adempimento di obblighi esterni. Significa che l'esatta
versione del dossier ha ricevuto le decisioni professionali richieste.
