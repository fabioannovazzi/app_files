---
name: mparanza-posizioni-negoziali
description: Turn a selected tracked Word agreement into source-linked negotiating positions, with every revision and comment accounted for, blank responses by default and saved round comparisons. Use for a concise negotiation table, not automatic acceptance, sending or a replacement contract redline.
---

# Posizioni negoziali con Lucia

Per un Word revisionato o una richiesta di tabella delle posizioni negoziali,
riusa il pack e il contesto già preparati per `confronto-documenti` o revisione
contratti; il DOCX revisionato può anche essere l'unico input iniziale.
Leggi `../mparanza-revisione-contratti/references/prassi-italiana.md` e, per un Word
della tabella o successive revisioni richieste, `../mparanza-revisione-contratti/references/word-handoff.md`.
Il confronto ordinario fra due documenti conserva il proprio contratto.

Risolvi `../../vendor/modules/deal_redux` dalla directory della skill se
presente; nel repository usa `../../../_shared/vendor/modules/deal_redux`.
Leggi integralmente `workflow.md` e i suoi riferimenti e applica il metodo.
Il root del prodotto è `../..`; `<helper-dir>` è `../../scripts`, in assoluto.
Dal root esegui `python scripts/check_dependencies.py` e
`python scripts/managed_python_runtime.py status`; usa il Python condiviso
riportato per i helper, fuori dalle cartelle del cliente.

Scegli la cartella autorizzata della pratica. Riprendi inventario, review e
snapshot già salvati; non reinizializzare una run. Per un nuovo round prepara
una nuova cartella con le nuove prove e la precedente review scelta.
L'avvocato decide posizione e risposta; il modello raggruppa e spiega gli effetti.
Non accettare revisioni, modificare l'originale o inviare il risultato.

Quando occorre un approfondimento giuridico, leggi
`../mparanza-quesito-legale-fiscale/SKILL.md` e usa il metodo completo del prodotto
senza ricerche parallele sul medesimo quesito o dati del cliente nelle query.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../mparanza-lucia/SKILL.md`.
