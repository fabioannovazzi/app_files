# T10 routing evaluation results

Status: **executed after explicit user approval**, 5 September 2026. The first
transfer was rejected by automatic approval review before execution; the user
subsequently approved the exact two-file, ten-synthetic-case evaluation. All ten
retained event streams contain a completed turn, and the recorded source hashes
match the approved snapshot.

The evaluation sent the current Vera router and workflow catalog plus
one synthetic request per run to Codex gpt-6-astra at low effort. Tool execution
is disabled. It assesses only routing selection and the proposed first response,
not execution of a specialist workflow, professional correctness, native-worker
isolation or superiority over an older model.

Expected routes below come from the inspected workflow catalog. Missing documents
needed to execute a known workflow do not count as routing ambiguity. The vague
R13 request does require clarification. Host-constrained cases must not claim
operations were performed. Narrative responses need manual review in addition to
the mechanical field checks.

| Case | Expected workflow | Routing clarification needed | Synthetic request |
| --- | --- | --- | --- |
| R01 | open-item-reconciliation | No | Ho un elenco di fatture ancora aperte al 31 dicembre. Verifica quali sono chiuse o parzialmente chiuse usando mastri, incassi e compensazioni. |
| R02 | journal-bank-reconciliation | No | Confronta ogni movimento dell’estratto conto con le scritture del giornale. Non ho una popolazione di partite aperte da verificare. |
| R03 | passive-invoice-audit | No | Controlla la popolazione delle fatture passive FatturaPA contro le registrazioni effettive di costo e IVA, evidenziando omissioni e duplicazioni. |
| R06 | new-client | No | Apriamo un nuovo cliente dello studio: organizza i documenti, identifica cosa manca e prepara le verifiche iniziali, inclusa antiriciclaggio. |
| R07 | aml-review | No | Il fascicolo cliente esiste già. Rivedi titolari effettivi, struttura proprietaria e spiegazioni economiche per la revisione antiriciclaggio. |
| R10 | browser-automation | No | Vorrei insegnarti il processo su Chrome del mio computer e farti ripetere i click. Puoi iniziare ora a controllare il browser? |
| R11 | archive-organization | No | Vera, questi sono i nomi dei file del fascicolo: avviso.pdf, copia_avviso.pdf, nota.txt. Aiutami a preparare un piano di riordino; non eseguire spostamenti. |
| R12 | No fixed workflow | No | Vera, scrivi una poesia fantastica su un drago che gioca a calcio. |
| R13 | No fixed workflow | Yes | Vera, confronta questi dati. |
| R14 | open-item-reconciliation | No | Aggiungi anche gli incassi di gennaio per distinguere le partite pagate dopo la data di chiusura. |

R10 has no browser or local tools in ChatGPT. R11 has only a supplied filename
list and asks for a plan, not actual moves. R14 explicitly continues an existing
Open Item engagement. Other specified Codex cases have local tools available.

## Exact evaluated source files

- `/Users/fabio/Documents/GitHub/app_files/plugins/vera/skills/vera/SKILL.md` — SHA-256 `305a0b57e906758d45d33693e923ced8b07910fe0640a4f0ae4faad7e58472de`.
- `/Users/fabio/Documents/GitHub/app_files/plugins/vera/skills/vera/references/workflow-catalog.md` — SHA-256 `aeedfd83565d0b8293cbaa4afd441905e4015e861bb7c8e55e1160b44b50f04e`.

The catalog matches the installed published Vera 0.1.201 bytes. The router differs
by the ChatGPT runtime guidance, generated-registry pointer and corrected archive
host description. The approved evaluation used this exact snapshot and the originally proposed
model route.

Retained runner: `/private/tmp/vera-remediation-01a07083/evaluate_routing.py`.
Future runs require a fresh snapshot check because other tasks share this checkout.

## Results and manual review

All ten cases selected the expected workflow (including no fixed workflow for
R12/R13), and all ten made the expected routing-clarification decision. None
claimed completed operations. The initial scorer reported eight workflow
mismatches because answers used the valid `vera:` namespace. Raw results remain
unchanged; a separate reviewed result removes only that exact optional prefix.

The reasons and first responses were also inspected. R10 explicitly declined
unavailable Chrome control. R11 correctly avoided inferring duplicates or
claiming moves from filenames, but requested contents before offering a
provisional plan; route selection passes, while lightweight planning usefulness
is not established. R12 reported no matching specialist, R13 asked one relevant
question, and R14 preserved the existing Open Item engagement. No comparative
model advantage or complete workflow acceptance follows from this run.

Evidence directory: `/private/tmp/vera-remediation-01a07083/routing-current/`.
`results.json` retains raw answers and original scoring; `reviewed-results.json`
binds that raw file by SHA-256 and records normalized comparisons and narrative
review. Each case retains the prompt, structured answer, events and stderr.
