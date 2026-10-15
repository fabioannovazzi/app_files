---
name: mparanza-contenzioso-tributario
description: "Prepare or resume Italian tax litigation for a lawyer: case events, procedural steps, sourced deadlines, evidence, first-instance appeals, appellate pleadings and subsequent submissions. Preparation and saved progress only; not filing, service, signature or background reminders."
---

# Contenzioso tributario con Lucia

Lucia fornisce il metodo; l'avvocato conferma incarico, fatti e prove e compie
gli atti professionali. Non deve programmare il workflow. Verifica abilitazione
e limiti della fase richiesta; la guida non implementa integralmente i rimedi
successivi di Cassazione, revocazione e ottemperanza.

## Metodo condiviso

Risolvi `../../vendor/modules/italian_tax_litigation` dalla directory di questa
skill se presente; nel repository risolvi invece
`../../../_shared/vendor/modules/italian_tax_litigation`. Leggi `workflow.md`
integralmente e tutti i suoi riferimenti. Non parafrasare, abbreviare o sostituire
il metodo. Leggi anche `../mparanza-quesito-legale-fiscale/SKILL.md` quando il metodo
richiede ricerca. I passaggi e i termini dipendono dai fatti e dalle fonti,
non da un classificatore o dal nome della professione.

Dal root del prodotto controlla `python scripts/check_dependencies.py` e
`python scripts/managed_python_runtime.py status`; usa il Python dell'ambiente
condiviso riportato per i helper. Le dipendenze sono dichiarate nei requirements
del prodotto e nella ricetta condivisa, fuori dalle cartelle dei clienti.

Il root è `../..` da questa skill. `<helper-dir>` è `../../scripts`, risolto
in assoluto. Scegli la cartella autorizzata della pratica e non reinizializzare
una run già esistente. Per citazioni e Word leggi anche
`../mparanza-verifica-citazioni/SKILL.md`, `../mparanza-controllo-documento/SKILL.md` e
`../mparanza-revisione-contratti/references/word-handoff.md`. Questi controlli completano
il medesimo incarico; non aprire una seconda ricerca per la stessa questione.
