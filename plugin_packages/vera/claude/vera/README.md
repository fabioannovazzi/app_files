# Vera

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/vera) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Vera is a bounded AI colleague and reviewer for professional accounting
studios. She prepares, checks, and documents work while keeping evidence,
limitations, and professional-review steps visible. Vera does not replace the
commercialista: decisions, approval, and responsibility remain with the
qualified professional.

## One source, two packages

Vera is maintained once in this repository. The same skills and component
modules produce separate generated packages for:

- Claude Cowork, described by `.claude-plugin/plugin.json`; and
- Codex, described by `.codex-plugin/plugin.json`.

Generated package directories and ZIP files are build artifacts. They are not
separate implementations and must not be edited by hand. A release is valid
only when both packages are built from the same source commit. Each surface
keeps its own manifest version.

Both install-package builders require Node.js on `PATH`. Building or checking a
package extracts its ZIP into a clean temporary directory and runs every
registered local MCP launcher through `initialize` and `tools/list`. A missing
runtime dependency, invalid response, crash, or timeout fails the release check.
The build checks the candidate before replacing downloadable artifacts.

Cowork retains nested component manifests because server startup and integrity
receipts read them. Only the root `.claude-plugin/plugin.json` identifies the
Cowork plugin. Review adapters with `injectLocalServer: false` declare an exact
implementation tree; the install builders must not inject the generic local UI
server into those trees. The separate ChatGPT upload projection still includes
its review bridge.

The `Packaged plugin runtime` CI job exercises both Vera install ZIP layouts and
negative packaging cases, then checks the committed Cowork download for drift
and startup failures. These checks establish tool availability, not successful
completion of professional workflows or acceptance inside the Cowork desktop
app; those still need representative host-level smoke tests.

## Skill identities

Vera owns one public skill namespace. Codex exposes every registered specialist
as `vera:<skill-name>`, for example `vera:journal-sampling`. Skill frontmatter
keeps only the bare internal name because the host supplies `vera:`. A bare
specialist name is not a public Vera identity, and a frontmatter name that
already contains `vera:` would create a redundant namespace.

Install only one Vera distribution at a time. Before enabling the curated Vera
plugin, remove or disable an older local `vera@mp-vera` installation. If the
same Vera skill appears twice, both distributions are active and the legacy
copy must be removed.

## Cowork v1 contract

Cowork is Vera's Anthropic marketplace surface. Ordinary Claude Chat is not a
supported Vera surface.

Cowork uses the connected folder as the primary workspace. Vera inspects
supplied evidence, preserves source lineage, and creates reviewable artifacts
in that workspace. Callable read-only connectors may supplement connected
files. Local MCP servers and local review interfaces are optional enhancements,
not prerequisites for the basic file-first workflow.

Vera must continue with the useful file-based portion of a task when an
optional local capability is unavailable and must state which operation remains
pending. It must never claim that a script, connector, MCP tool, or durable
write ran when it did not.

The Cowork package does not claim or execute:

- WhatsApp Desktop inspection;
- live INPS browser capture;
- hosted feedback or voice-interview submission; or
- Vera's custom update checker.

Studio Archive is included in Cowork. Its portable customer-folder ledger uses
the connected studio folder for durable client, engagement, input, run,
lifecycle, and artifact records. Local indexing is available when its declared
dependencies are already callable. A read-only Anthropic Gmail connector may
add evidence for one confirmed client; Vera does not send or modify mail.

## Shared implementation

Vera's umbrella layer owns discovery, routing, package metadata, dependency
delegation, MCP dispatch, and shared support modules. The editable
implementation of each specialist workflow remains in its existing
`plugins/<module>` directory. Package builders embed those modules under
`modules/` so each distributable is self-contained.

Before a module helper runs, Vera prepares only that module's published core
requirements in a fingerprinted, user-scoped managed virtual environment and reuses it
across restarts. Helpers run through `scripts/managed_python_runtime.py`; module
environments are isolated from one another, and the optional shared OCR runtime
remains a separate explicitly approved setup.

The shared specialist workflows cover:

- new-client file preparation, evidence gaps, identity, engagement, privacy,
  AML, document planning, and monitoring;
- accounting evidence reconciliation, journal sampling, entry checks, and
  journal-to-bank reconciliation;
- forward-looking sales Plan scenarios from reviewed Actuals and confirmed
  commercial or FX assumptions;
- integrated business plans for startups and new ventures, using
  reviewed evidence and confirmed assumptions to link profit and loss, cash
  flow, balance sheet, scenarios, and funding needs;
- source-bound historical financial analysis and fixed due-diligence recipes,
  management variance analysis with the shared calculation and plot suite,
  plus reviewable financial reports and concordato preventivo review;
- complete source-backed answers to legal, tax, and compliance questions,
  using separate prompt-planning and answer-validation stages;
- evidence-backed INPS case review from supplied documents or official exports;
  and
- Registro Imprese, REA, Comunicazione Unica, DIRE, and SARI preparation.

Each workflow preserves its deterministic checks, evidence trail, and review
surfaces. A host-specific adapter may gate a tool or interaction, but it does
not fork the professional method.

## Portable customer-folder runs in Codex and Cowork

Every client-bound Vera workflow uses one explicit Studio Archive
customer-folder ledger. The customer folder—not chat history or a session-local
directory pointer—holds the stable client manifest,
engagements, immutable input receipts, exact run input manifests, lifecycle,
outputs, and artifact manifests.

The flow is: identify or create the customer folder; create or select an
engagement; import authorized files as immutable receipts; prepare an
idempotent run from exact receipt IDs and upstream artifacts; start; execute
only the bound run-local inputs; finalize every output with its purpose and
audience; review; and complete. Failed and cancelled runs remain explicit.
Folder renames and a fresh local installation recover from the portable
manifests. Retention reporting never deletes data automatically.

Journal Sampling declares its normalized population, diagnostics, and exact
sample as artifacts. Each Check Entries support evidence batch is represented
by a separate run bound to those exact Journal Sampling artifacts and its own
immutable support receipts; an intentionally separate identical selection uses
the explicit new-run option. It checks only the bound sample, and later imports
do not expand an existing run.

In Cowork, the packaged Studio Archive CLI creates and advances the same
portable lifecycle in the exact connected folder. Session-local configuration
is rebuildable; a later task reconfigures and recovers the same durable ledger
rather than relying on chat history.

## Runtime capability policy

Skills select behavior from capabilities that are actually callable:

1. connected files and native artifact writes;
2. authorized read-only connectors;
3. local scripts and declared dependencies;
4. local MCP review interfaces; and
5. browser or computer control only where the runtime-specific contract permits
   it.

Missing optional capabilities narrow the execution; they do not justify
inventing results or silently changing the evidence basis. Vera never installs
packages at runtime.

## Privacy and professional review

Every registered workstream has a versioned external-boundary record under
`privacy/workstreams/`; shared services are registered under
`privacy/services/`. The records identify the model context, runtime account
boundary, additional external routes, and concrete controls. Client or case
material read by the model may enter the selected runtime's model context.

The `privacy-surface-review` workflow validates coverage and source
fingerprints before release. It is a development control, not a GDPR
certification, and it does not replace the professional's purpose-based data
minimisation and legal assessment.

Vera never signs, files, sends, activates, or approves professional work on the
user's behalf. Every substantive output remains a draft for qualified review.

## AML review

`vera:aml-review` examines ownership, economic explanations, evidence discrepancies
and changes since a prior assessment for Italian clients. It prepares a sourced
memo and records professional decisions through the existing client archive.
Its Python helper reuses validated New Client arithmetic when available; screening
reports are supplied by the studio and no automatic SOS or monitoring is included.
