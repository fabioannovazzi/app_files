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
only when both packages are built from the same source commit and carry the same
version.

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

The initial Cowork package does not claim or execute:

- WhatsApp Desktop inspection;
- live INPS browser capture;
- persistent local archive indexing;
- hosted feedback or voice-interview submission; or
- Vera's custom update checker.

For Studio Archive, Cowork v1 supports connected files and a callable,
read-only Anthropic Gmail connector for one confirmed client. It does not send
or modify mail.

## Shared implementation

Vera's umbrella layer owns discovery, routing, package metadata, dependency
delegation, MCP dispatch, and shared support modules. The editable
implementation of each specialist workflow remains in its existing
`plugins/<module>` directory. Package builders embed those modules under
`modules/` so each distributable is self-contained.

The shared specialist workflows cover:

- new-client file preparation, evidence gaps, identity, engagement, privacy,
  AML, document planning, and monitoring;
- accounting evidence reconciliation, journal sampling, entry checks, and
  journal-to-bank reconciliation;
- reviewable financial reports and concordato preventivo review;
- source-backed legal, tax, and compliance research prompts and validation;
- evidence-backed INPS case review from supplied documents or official exports;
  and
- Registro Imprese, REA, Comunicazione Unica, DIRE, and SARI preparation.

Each workflow preserves its deterministic checks, evidence trail, and review
surfaces. A host-specific adapter may gate a tool or interaction, but it does
not fork the professional method.

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
