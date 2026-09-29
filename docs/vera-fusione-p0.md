# Fusione guidata: P0 implementation and recovery

Origin: https://discord.com/channels/1550191335917625474/1554383364012642355/1554534721579655315

Recovered on 2026-09-29 through the configured Discord connector: all six available
messages in channel `1554383364012642355` (empty pages before/after confirmed the
history bounds), the two `risposta-vera.md` attachments, and `fusione_vera_v0.1.zip`.
The ZIP was shared by a Vera relay attributing the original contribution to Francesco
Giraldo on 2026-09-22. It is a design proposal, not an installed implementation.

Original ZIP SHA-256:
`6e2bdd8e2b379fdb6b1bda09acbeee5e59619ba8f0a97b732a0d6b3db63941dd`.
All 20 entries passed path/symlink/size inspection. All 19 hashes listed in the
supplied verification report matched. Contributor code was read, not executed.
Raw messages, originals, inspected documents and a separate inventory are retained
in the authorized local recovery folder under `outputs/discord-fusione-recovery/`.
The two response attachments are distinguished by their message IDs in that raw log.

The latest Discord implementation brief explicitly proposes the P0 foundation.
Its P1 legal/numerical branches are not claimed by this change. Existing legal
statements and the contributor's reported verification results have not been
independently validated as current law.

## Requirement to inspected component map

| Requirement | Inspected existing component | Gap and implemented choice |
|---|---|---|
| Discoverable Vera function | `components.json`, specialist wrappers, Vera router and ChatGPT router projection | Added `fusione-guidata` module, wrapper and routes. |
| Multi-company versioned case | Studio Archive `client_ledger.py`: single-client engagement receipts and runs | A separate P0 operation stores company-scoped records and explicit file snapshots. No implicit cross-client adapter. |
| Sources, facts and dependencies | No `scissione` or merger implementation found in the inspected base | Added exact references, source attempt history, tri-state facts and dependency review. |
| Approval tied to content | Existing module-specific professional-review patterns | Added immutable Decision records and derived effective approval for unchanged dependencies. |
| Import access and provenance | Studio Archive `import_document` verifies an exact client/engagement and creates immutable snapshots | P0 uses explicitly bound company directories and a selected file per import. A live ledger adapter remains unimplemented. |
| Exact numeric/date representation | Contributor formulas demonstrate Decimal/Fraction but no production workflow | P0 validates decimal strings, fraction strings and ISO dates; no merger calculation or deadline engine. |
| Model-context disclosure | Vera canonical `model_data_report.py` and privacy register | Reused local report builder with measured local item counts and unmeasured host exposure, added governed privacy manifest. |
| Package parity | Existing Codex, ChatGPT and Cowork builders | Register the source component and include it through the normal builders. |

Deterministic checks are justified by mechanically verifiable type/reference/hash
correctness, transaction consistency and explicit access scoping. The model retains
semantic source selection, materiality, dependency selection and branch proposals;
the professional retains approval. No heuristic legal classifier or API-key runtime
was introduced.

## Run and verify

From the repository with its activated Python environment:

```sh
python plugins/fusione-guidata/scripts/check_dependencies.py
python plugins/fusione-guidata/scripts/run_fusione.py demo --output /absolute/new-demo-directory
python -m pytest -q -o addopts='' --confcutdir=tests/plugins tests/plugins/test_fusione_guidata.py
```

The demo persists a case database and before/after review outputs. It exercises
missing facts, candidate rules, an approved draft, a later liability change,
selective reopening, failed source access, historical preservation, unsupported
branches and per-company access. Its JSON separates passed, failed and not-run work.
Regression tests add cross-case forgery, exact numeric types, stale writes,
dependency cycles, retained scope, corrupt snapshots, permissions and restart cases.

## Limits and next increment

P0 is a local case foundation. Actor IDs are declared workflow identities; the
database is not an authentication or encryption boundary. Approval records do not
prove professional identity or constitute signatures. Dependency completeness is
model-led and reviewed, not inferred by the helper. No legal branch, statutory
calendar, concambio calculation, tax decision, filing or live client acceptance is
implemented. The contributor's 36 scenarios are not reported as executed tests.

P1 should cover only the two proposed domestic OIC branches after current primary
source verification, approved assumptions, calculation/calendar contracts, actual
Studio Archive multi-company integration and professional end-to-end acceptance.
Partial ownership, inverse/sister-company mergers, MLBO, IFRS and cross-border
combinations require their own reviewed increments.

## Observed local verification

On 2026-09-29, the new foundation suite passed 55 tests with 86.73% statement
coverage. Black, Isort, Mypy and Bandit passed for the new Python component.
The full package/update suite passed 398 tests with two installed Marketplace cache
checks skipped because that cache was unavailable. The privacy, icon, update and
skill-alignment group passed 81 tests with the same two cache-dependent skips.

The Codex, ChatGPT and Cowork archives use candidate version 0.1.279 and pass the
normal product build `--check`. Each archive's extracted P0 component passed its
12-check synthetic demonstration. Cowork's build initialized all 18 included MCP
servers and listed their tools. The explanation page was inspected at desktop and
mobile sizes and in all five languages. These are local/package observations;
publication, deployment, enabled-installation acceptance and real-client testing
are not established by them. A dedicated CI matrix covers Linux, macOS and Windows;
its remote results must be checked separately.
