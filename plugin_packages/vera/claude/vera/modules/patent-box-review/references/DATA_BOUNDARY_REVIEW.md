> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Revisione dei confini dei dati — pacchetto di sviluppo

Data: 23 settembre 2026. Ambito: codice e proposta di integrazione consegnati; nessuna pratica cliente reale eseguita.

## Prototipo effettivo

Il nucleo Python legge i JSON e i file di evidenza indicati dall'operatore, verifica riferimenti e impronte, calcola e scrive output locali. Il confronto fonti legge snapshot forniti. Questi script non contengono un client LLM, chiamate HTTP o un processo in background.

Il modello di questa conversazione ha letto la richiesta e la specifica riportata dall'utente, fonti pubbliche e relative porzioni, istruzioni tecniche del plugin, codice e risultati di esecuzione. Non sono stati caricati documenti di clienti per lo sviluppo. Il contesto preesistente fornito dall'ambiente non è misurabile integralmente in questa revisione; non si afferma un conteggio esatto dei dati trasmessi al provider.

Gli esempi sono inventati esclusivamente per test e contrassegnati `demo=true`; non costituiscono evidenze legali o contabili. Le regole reali sono in DRAFT. Non è stato creato un run professionale di Patent Box nel registro di Vera.

## Integrazione futura

Il modulo dovrà registrare le classi di dati che il modello può leggere: identità/contesto della pratica, titoli e contratti IP, relazioni tecniche, estratti contabili, dati del personale quando necessari, prospetti derivati, questioni e decisioni. È ammesso che dati reali arrivino al modello quando servono al lavoro; non promettere anonimizzazione automatica o trattamento esclusivamente locale.

Fare riferimento ai profili condivisi `openai-codex` e `anthropic-cowork` della versione di Vera utilizzata. Il piano e le impostazioni dell'account sono scelti dallo studio/utente e non verificati da questo pacchetto. La compatibilità del workflow con ciascun host dovrà essere collaudata, non deriva dalla sola presenza dei profili.

Ricerca pubblica: usare quesiti generici, senza inviare fatti identificativi dei clienti ai motori di ricerca. Accesso a banche dati, connettori, servizi di firma e invii esterni sono adattatori distinti da descrivere quando implementati. Il monitor condiviso non deve contenere l'archivio delle pratiche. Il confronto di impatto deve operare nell'ambito privato autorizzato.

## Controlli concreti presenti

| Controllo | Implementazione | Effetto |
|---|---|---|
| Percorsi evidenze confinati | `contracts.verify_evidence` risolve path e symlink sotto la radice | Rifiuta file fuori dall'ambito assegnato |
| Integrità file | SHA-256 confrontato con evidenza dichiarata | File mutato o riferimento errato blocca il calcolo |
| Contratti chiusi | `contracts.validate`, importi stringa e chiavi duplicate rifiutate | Input ambigui o extra non vengono interpretati automaticamente |
| Risultato legato agli input | Hash caso/regole/output | Decisione su risultato non aggiornato o alterato rifiutata |
| Output nuovo | Apertura esclusiva e cartella nuova | Riduce sovrascritture accidentali |
| Ponte Node senza shell | `spawnSync` con array di argomenti e `shell:false` | Gli argomenti non sono interpretati come comandi shell |

Questi controlli non autenticano la provenienza dei documenti, non certificano la correttezza delle decisioni e non sostituiscono isolamento/permessi del sistema ospitante. Autenticazione revisori, audit log immutabile, autorizzazioni per cliente, policy dei fetcher e gestione credenziali sono ancora da integrare.

## Registrazione nel prodotto

È stato consultato il metodo `vera:privacy-surface-review`, compresi il contratto dei manifest, `components.json` e i profili runtime della versione 0.1.258. Questa è una revisione progettuale del nuovo componente, non una validazione di rilascio del plugin.

Il manutentore dovrà creare il manifest di workstream secondo lo schema della versione corrente, indicare percorsi effettivi, classi di contesto e confini esterni, aggiornare l'impronta ed eseguire il validatore dell'intero plugin. Non è stato modificato il registro installato e il suo validatore non certifica questo ZIP.

La revisione non è una DPIA né una certificazione di conformità privacy. Il report della sessione è `model_data_report.md`; nessuna ricevuta server è stata richiesta o dichiarata.
