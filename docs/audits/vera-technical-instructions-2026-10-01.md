# Vera: technical instruction audit follow-up

## Evidence and baseline

The original evidence is Nicola's `Vera_registro_rilievi_2026-09-30.xlsx`,
recovered as `1554910873552683121-Vera_registro_rilievi_2026-09-30.xlsx` in the
local audit output, and its `workbook-extracted.json` (first 22 findings).
The seven finding IDs and evidence cells were checked against the workbook.
The earlier investigation's conclusions were not used as authority.

The reproduction baseline is `origin/main` at
`f9f69bc0b`, including PR #721 / `71c145f111e69d2eab0a609dd7169d086451072a`
and canonical Vera 0.1.299. Both editable source and the distributed Cowork
projection were inspected. That prior packaging fix is retained.

## Findings and bounded changes

| Finding | Observed | Change or disposition |
| --- | --- | --- |
| R03 | The router's broad prohibition and catalogue's “without filing” conflicted with the router's grants route and the specialist `portal-preparation.md`. That reference already permits an exact-final-application submission after explicit approval. | Align the broad router boundary and grants catalogue row with that existing exception. Project approval or compilation approval still does not authorize submission. Authentication, declaration acceptance, signature and payment remain manual. Changed application, attachments, destination or control effect requires approval again. No new portal driver or authority is added. |
| R14 | The source catalogue named native Codex GPT-5.6 Luna. The general host-name projection produced “native Claude GPT-5.6 Luna”. Cowork actually ships `worker_config.json` with `runtime=cowork-haiku`, and an agent with `model: haiku`. | Refer to the selected workflow's configured native semantic worker and its host qualification. Retain the distinction between screening and professional approval/audit opinion. No runtime selection changes. |
| R17 | `report-builder`, `check-entries` and `passive-invoice-audit` are real component IDs, with real packaged skills named `financial-report-builder`, `vouching` and `purchase-invoice-review`. “Check Entries” is a historical display name and remains in the archive handoff command. | Explain these three mappings in the generated execution contract. Use public workflow names in its cache-cleanup scope and component IDs in paths. Retain the existing names and commands; no alias resolver is needed. |
| R18 | The builder injects the same contract into root wrappers and component skills. A specialist may be invoked directly, without first reading the router. | Retain the repeated contract. A regression verifies exactly one current central contract in every projected skill; it can no longer quietly diverge in one skill. No reduction of execution/review obligations. |
| R19 | `treasury-forecast` appeared after the public-process-page instructions. Its wrapper, component skill, managed CLI and registry entries already existed. | Move the row into Professional workflows. Verify a single row in that section and that all treasury registry paths exist in the Cowork projection. No routing engine or forecast calculations change. |
| R20 | Cowork's projected browser skill already excludes live discovery/replay while retaining supplied developer-pack/capability review and packaged local pipelines. Its unchanged frontmatter, router, catalogue and registry still described broader live work. | Give those four instruction surfaces the same bounded capability description. Preserve offline review and local pipelines, using the existing managed Python launcher. Preserve the existing live-browser restriction. Do not mark the whole workflow unavailable. |
| R21 | `--repair` validates the implementation before deleting only eligible own-vendor cache bytecode. On read-only copies it raises `PermissionError`; ordinary implementation validation tolerates the retained bytecode. | Clarify the supported maintenance exception, its optional nature, and read-only/permission-error handling. Do not change helper behavior, weaken validation, modify permissions or permit manual installation edits. |

## Model and capability evidence

The default source runtime is `codex-luna`. Its native adapter defaults to
`gpt-5.6-luna` and supports the existing reviewed worker-selection contract.
The Cowork builder sets the separate `cowork-haiku` configuration. The Cowork
adapter prepares `cowork_request.json`, requires the configured native agent
and a matching host-reported invocation record, and leaves missing responses
pending. Historical `luna_chunks` names are storage identifiers, not evidence
that Luna ran in Cowork. Configured Haiku does not prove the host's effective
model identity or equal accuracy. The installed skill already requires that
distinction; the catalogue now follows it.

Browser automation's local pipeline and evidence-pack scripts remain packaged.
Their tests exercise local contracts and evidence handling, not a connected
Cowork browser. General availability of some host browser tool does not qualify
the documented Chrome/Playwright discovery and replay contract in Cowork.
The grants workflow separately checks its host's available tools before any
approved portal action; it does not inherit a browser-automation capability.

## Validation and release scope

Regression checks cover source/projected grants boundaries, configured worker
evidence, component paths, treasury placement and entrypoints, matching browser
scope, and identical contracts under direct specialist invocation. CI runs these
checks and the packaged repair tests.

For each of the six supported components, tests extract the exact implementation
from the built Cowork ZIP. Writable repair must remove the inserted cache file
while preserving every original file byte. POSIX read-only repair must fail,
preserve cache bytes and still pass ordinary implementation validation. Existing
source tests retain contract-mismatch, symlink and hardlink failure checks.

Vera's candidate is 0.1.310. Lucia's candidate is 0.1.74 because its shared Vera
components use the same generated contract; its source workflows are unchanged.
All affected Codex, ChatGPT-upload and Cowork archives are generated from source.
Clara is checked for parity without a source or package change. Shared-service
privacy changes are fingerprint refreshes only; no data-boundary policy is changed.
The Geneva catalogue snapshot is refreshed while preserving its prior dispositions.

These are review candidates. Merge, deployment, Marketplace publication and
release notification have not been performed for these candidates.

Local validation includes the package/instruction suites, the browser evidence
pipeline suite (107 passed), the passive-invoice suite (111 passed, one optional
native-worker test skipped; 87.63% coverage), and release-alignment tests
(13 passed; 98.44% coverage). Package parity, bundled MCP initialization,
changed-file Black/Isort, builder Mypy/Bandit and privacy/catalogue fingerprints
are checked. Effective native-host operation remains a separate acceptance step.

The broad `src` formatting checks expose baseline failures: Black reports 27
files and Isort reports existing import-order violations. The `src` tree is byte-identical to the inspected
main baseline and is not modified by this change. Its Mypy and medium/high Bandit
checks pass. These findings are not repaired as part of this instruction PR,
and the whole-repository quality gate is not represented as green.

## Unknowns and product decisions

Native Cowork agent invocation, effective model identity, live portal submission
and Nicola's exact affected installed package are not established by these tests.
No new product-policy decision is required for the reproduced instruction defects:
the bounded grants exception and Cowork browser limits are explicit in source.
Nicola's manual-only filing preference, studio-specific policy, formatting,
course acceptance and Second Brain integration are outside this change.
