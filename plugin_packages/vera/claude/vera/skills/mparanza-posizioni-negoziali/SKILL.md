---
name: mparanza-posizioni-negoziali
description: Summarize a selected tracked Word agreement into source-linked negotiating positions for a commercialista, with complete revision/comment accounting, saved rounds and blank responses unless requested. Uses shared document helpers; does not accept changes or send negotiation material.
---

## Operational incident continuity

At task startup, follow `skills/mparanza-vera/references/incident-recovery.md`. Call the
independent `vera_incident_register` tool with empty arguments to reuse the saved
anonymous connector identity across fresh tasks. If local startup context or the
installed `scripts/operational_incidents.py context` provides an opaque local
capability, pass it to register to link queued local reports. Never put OAuth
tokens in prompts or diagnostic evidence. Read `vera_incident_status` and deliver
any new remedy without interrupting ordinary work. Automatically report observed
technical failures with complete relevant technical evidence and record the
resumed original operation's actual outcome. Do not ask the user to report the
failure or answer a support questionnaire. Never send professional stdout,
client documents or unrelated personal information. Service failure does not
block the original task.

## Cowork execution contract

Public workflow names select skills; component IDs select module paths.
`financial-report-builder` uses component `report-builder`, `vouching` (historically
called Check Entries) uses `check-entries`, and `purchase-invoice-review` uses
`passive-invoice-audit`. These component IDs are not additional workflows.

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, financial-report-builder and vouching only, optional cache
cleanup uses the corresponding component ID from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
This supported maintenance command is the only cache-cleanup exception to the
prohibition on editing the installed tree by hand. It is optional: ordinary
validation and execution tolerate incidental bytecode without removing it.
On a read-only installation, skip cleanup. If the command reports a permission
error, retain that error and continue the ordinary validated workflow when its
checks pass; do not chmod, delete files manually, copy or patch the installation,
or bypass the host's permissions to make cleanup succeed.
If `validate_implementation_tree` ever fails with a file/directory-contract
mismatch, do not delete or modify files inside the installed plugin tree by hand
and do not bypass a sandbox/permission rejection to do so. Stop and report the
exact error instead.

Work from the connected folder and supplied files first. Before a module's Python
helpers, locate the installed plugin root. When it contains `components.json` and
`scripts/managed_python_runtime.py` (as Vera does), run from that root:

```bash
python3 scripts/check_dependencies.py --module <module>
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

If the enclosing plugin does not ship this managed launcher, use the module's
dependency checker and only already-installed dependencies; do not assume that a
standalone module script provisions them.

The managed launcher provisions and reuses one user-scoped CPython 3.12
environment per OS host with the published shared requirements, outside client
folders. Modules and products share this dependency environment; it does not
isolate client matters. This declared dependency setup is authorized as
part of running the workflow; never install arbitrary packages or use ambient
Python for subsequent module helpers. Repeat any declared `--requirements` options
on both commands. Missing ambient imports are a reason to run this setup, not to
abandon the calculation. If setup fails, report its exact error and do not replace
the required calculation with an invented result. Optional OCR setup still needs
separate approval. If setup reports `Host not in allowlist` for PyPI, explain that
Claude Settings > Capabilities > Allow network egress is disabled or restricted.
Ask the user or organization administrator to authorize package-registry access;
never change network permissions silently or work around the restriction. Retry
the same managed setup after access is approved, in a new session if needed.

MCP tools, browser or computer control, and local review servers are optional
enhancements, never completion gates. Cloud Cowork sessions may not expose local
plugin MCP servers even when the plugin is installed; use the packaged Python
workflow through the managed launcher in that case. Do not equate missing MCP
registration with a failed calculation engine. When an optional capability is
unavailable, continue with Markdown and file-based review and state the limitation.

The normal Cowork deliverable is a reviewable draft, artifact card, and
source/review files. A callable persistence interface may optionally record or
apply reviewer actions, but its absence never blocks delivery. Never claim
`applied` or `final_ready` unless corresponding persisted artifacts prove it;
otherwise report that professional review remains pending.

Use host-neutral user-facing artifact names. Name assistant-authored review
folders and files for Vera or their professional purpose (for example,
`vera-review/`, `vera_phase1_synthesis_reviewed.md`, and `run_review.md`).
Never put host, platform, or model-provider names in assistant-authored
user-facing artifact paths, document headings, field labels, narrative text,
or status summaries. Describe execution routes generically, such as
`external review route`, `connected tool`, or `local review interface`.

Derive any run ID, status, artifact count, or package hash quoted in an
assistant-authored supplement from the final delivered manifests.
After any rebuild, regenerate or resynchronize those supplements before
delivery. When a workflow ships a complete-delivery validator or sealer, run it
against the exact connected-folder copy after the last write.
In this contract, the base package validator alone does not validate extra
narrative files.

When a workflow declares owner-only or private output and uses a private scratch
directory before copying the final package into the connected folder, reapply
the privacy modes after that transfer: `0700` for the package root and every
directory, and `0600` for every file. Verify the connected-folder tree with
`stat` or `lstat` before claiming completion. If the host filesystem cannot
preserve those modes, do not claim owner-only delivery; keep the package in the
private scratch location or report the limitation and ask for a safer
destination.

Do not use WhatsApp, live INPS browser capture, hosted suggestion or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract. When invoked through Vera, Clara or Lucia, task
usage, signed receipts, technical recovery and 1–5-star feedback through the
invoking product's incident service and rating form remain available. Follow the
primary task's workflow-usage contract and product identity. Tutorials retain
their no-reporting boundary.

<!-- VERA_WORKFLOW_USAGE_BEGIN -->
## Task usage and user feedback

Before substantive work, follow `../mparanza-vera/references/workflow-usage.md`: start one
retained task UUID for the primary user process (including AI-led work), reuse
it across helpers/resumption, and record only observed outcomes. Discover the
native `vera_incident_host_link` tool, including deferred tools, and verify the
same run's Computer ID on the server. Build the model-data report from the actual
task even for chat-only drafts, then link its actual signed receipt. After delivery ask once for the user's 1–5 stars and optional
comment; never infer a score. Studio Archive is infrastructure, not another rated
process. Synthetic/agent tests are marked and excluded. Flush pending delivery
at task startup and after outcomes. The shared contract applies even on direct
skill invocation and on both Claude and Cowork.
<!-- VERA_WORKFLOW_USAGE_END -->


<!-- VERA_CONNECTED_KNOWLEDGE_BEGIN -->
## Connected studio knowledge

When the user or an adopted studio instruction requests relevant repository
evidence, read `../mparanza-vera/references/connected-studio-knowledge.md` before the
dependent work, including direct specialist invocation. Use only callable host
search/read tools; preserve citations and this workflow's qualification gates.
Without a repository, continue ordinary work. Studio skills remain independently
invoked by the user; Vera does not dispatch them.
<!-- VERA_CONNECTED_KNOWLEDGE_END -->

# Posizioni negoziali con Vera

Risolvi `../../vendor/modules/deal_redux` dalla directory della skill se
presente; nel repository usa `../../../_shared/vendor/modules/deal_redux`.
Leggi integralmente `workflow.md` e i riferimenti e applica il metodo condiviso.
Il commercialista sceglie il materiale e l'obiettivo dell'incarico; il nome del
prodotto non dimostra poteri negoziali, mandato o competenza per un atto legale.

Dal root del prodotto esegui `python scripts/check_dependencies.py` e
`python scripts/managed_python_runtime.py status`; usa il Python condiviso
riportato, senza creare ambienti nel cliente. Il root è `../..` dalla skill.
Nel pacchetto `<helper-dir>` è `../../vendor/modules/scripts`; nel repository,
se manca, usa `../../../lucia/scripts`. Risolvi i percorsi in assoluto:
i helper canonici sono inclusi in Vera e non richiedono Lucia installata.

Per una pratica già gestita in Studio Archive leggi `../mparanza-studio-archive/SKILL.md`
e prepara una run distinta `posizioni-negoziali` nell'incarico, con il Word
e gli altri materiali scelti. Usa una nuova sottocartella del suo output
autorizzato per il pack; non usare il contenitore già creato come nuova run
di `legal_documents.py prepare`. Per una richiesta diretta su un documento
continua il lavoro autorizzato senza inventare cliente, incarico o percorso.
Conserva gli originali, riusa il contesto già noto e chiedi solo fatti materiali.

Finché Archive è aperto, riprendi la medesima cartella e i record salvati.
Per un nuovo round o aggiornamenti di una run sigillata/completata prepara
una run successiva, con il nuovo Word come input e la review precedente scelta
come upstream. Non modificare snapshot, output o record della run sigillata.
Registra elaborati, snapshot della review e report nella nuova run.

Quando serve risolvere una questione giuridica sostanziale leggi
`../mparanza-quesito-legale-fiscale/SKILL.md` e usa il metodo completo del prodotto.
Per un Word della tabella usa Documents/Word dell'host, il modello scelto
dallo studio e verifica il file renderizzato. Non modificare né accettare
revisioni del contratto sorgente come effetto della sintesi.

Alla consegna leggi `../mparanza-vera/references/model-data-report-contract.md`.
Mostra il report leggibile e collega quello salvato, indicando originali,
revisioni, commenti, autori/date, contesto, precedente round, gruppi, risposte
richieste e pagine effettivamente letti. Il helper non invia dati o documenti;
inferenza e capacità Documents/Word seguono l'account del modello ospite.
