# Engineering boundary review — 29 September 2026

Reviewed source: transformation skill, wrapper, record contract, local helper,
demo and tests; Vera's routing/catalog and Marketplace-card additions; canonical
manifest version change 0.1.277 to 0.1.280; components registration. The candidate
was raised after inspecting concurrent local candidates at 0.1.278 and 0.1.279.

The helper imports inert synthetic bytes and stores hashes, versioned proposals,
exact calculations and attributed review decisions. It contains no network,
model API, shell command or external filing route. The selected host model may
read synthetic inputs, snapshots and dossiers. Synthetic declaration does not
detect personal information. The operator identity is not authenticated.

Shared-service impact was checked against Git base 6f26f0e82. `git diff` under
`plugins/vera/scripts`, `plugins/vera/hooks`, `plugins/_shared`,
`modules/run_receipts` and `modules/change_requests` returned no runtime changes.
The changed shared governed files are limited to metadata and routing additions:

| Record | Changed governed source | Effect inspected |
| --- | --- | --- |
| datev-starter | router, catalog, Marketplace cards | Adds the separate synthetic transformation route; DATEV request instructions and runtime are unchanged. |
| local-onboarding | router, catalog, Marketplace cards | Prototype has its own demo and is outside the ordinary course list; no profile, lesson, connector or teaching code changes. |
| managed-python-runtime | components, router | Adds a standard-library-only component; recipes, installers and dependency retrieval code are unchanged. |
| plugin-feedback | router | Adds the prototype scope; feedback consent, destination, payload and transport are unchanged. |
| plugin-update-check | canonical version, router | Candidate identity changes to 0.1.280; the public Published manifest is untouched. GET destination/payload/runtime are unchanged. |
| run-receipt-stamping | canonical version, router | Prototype uses a local report boundary and does not call the stamping client; existing professional-run stamping code and endpoint are unchanged. |

Each shared record's governed paths, destinations, activation, payload classes
and concrete security controls were inspected. Refresh is limited to these
identified changed-source fingerprints after this impact review; it does not
represent a new audit of remote services, provider settings or legal compliance.
The existing service claims are not expanded. The new workstream has its own
model-context review and no external boundary. Package freshness and tests are
separate evidence recorded in the implementation report.
