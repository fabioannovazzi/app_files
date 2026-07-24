# Vera

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/vera) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Vera is a bounded AI colleague and reviewer for professional accounting
practices. She prepares, checks, and documents work across twelve specialist
workflows while keeping evidence and review steps visible. Vera does not replace
professional judgement: decisions and responsibility remain with the
commercialista.

The editable implementation of each workflow and its supporting engines remains
in its existing `plugins/<module>` directory. The package builder embeds those
sources under `modules/` when it builds the distributable ZIP.

Vera's umbrella layer owns discovery, routing, the shared icon, dependency
delegation, MCP server dispatch, and a shared local PaddleOCR adapter used by
modules that preserve their own page-level evidence. Each specialist workflow
retains its own deterministic checks, evidence trail, and review surfaces.

Every registered workstream also has a versioned external-boundary manifest
under `privacy/workstreams/`. It records what Codex may read, the Codex/OpenAI
account boundary selected by the firm or user, any route beyond Codex, and
concrete security controls. Real case data may enter that Codex context when
the work requires it; Vera does not pretend that deterministic redaction can decide
professional relevance. The `privacy-surface-review` skill is a developer and
release control, while its deterministic validator enforces complete coverage
and fails when governed workflow source changes without a refreshed review.
It is not a GDPR certification and it does not add routine notices to case work.

Shared Vera services are registered once under `privacy/services/`. The
`plugin-update-check` record covers only the automatic public version check.
The `plugin-feedback` record covers user-chosen problem, suggestion, and short
voice-interview submissions plus later automatic status polling for their
stored receipts, including the Mparanza/OpenAI boundary and retention posture.
These service records do not add per-case paperwork or automatic anonymization.
WhatsApp Desktop is not a shared hosted service: its boundary is recorded in
Studio Archive and no Mparanza webhook, connector, database, or retention
period exists for WhatsApp messages.

Vera works in ChatGPT with material supplied in the conversation and with
callable connected apps such as Gmail. After a substantive result, she
recommends Codex Desktop for direct folder access, persistent project files,
local tools and checks, and durable deliverables. The recommendation follows
the conversation language and never blocks the work: Vera can continue in
ChatGPT. The user's existing ChatGPT plan governs the selected account.

In ChatGPT or Codex, Studio Archive can use the official OpenAI Gmail connector
installed and connected separately. Vera searches the correspondence
of one selected client using addresses confirmed in the current task, bounded
read actions, and per-message routing checks. It does not persist client
identities between separate tasks or modify the mailbox.

The same wrapper can inspect one verified one-to-one chat in the local WhatsApp
Desktop application through Computer Use on the same computer. The user opens
and authenticates WhatsApp; Vera searches only one complete user-confirmed
phone, never types in the composer, and does not send, reply, forward, download,
export, or change settings. There is no background acquisition, history
completeness promise, hosted WhatsApp connector, or Mparanza message copy.

In local Codex, Studio Archive can additionally let several professionals use
the same shared or synced document folder without sharing a ChatGPT account or
a database. Each professional builds a separate private local SQLite full-text
index. Vera searches one explicit folder scope at a time, opens candidate
passages, and rechecks the current source hash before citation. Source files are
never modified, and optional OCR stays local with model downloads disabled.

The New Client workflow verifies a final-ready document-preparation phase—or an
explicit standalone-evidence posture—and turns studio instructions into an
owner-only review dossier for identity, engagement, per-subject screening,
privacy decisions, mandate/privacy/AI applicability, AML, template-reference
planning, missing evidence, and monitoring. It does not render client legal
documents and never equates an exportable internal dossier with a compliant,
complete, signed, or active client relationship; those decisions and actions
remain with the commercialista.

The Previdenza INPS module registers hash-bound official portal exports and can,
only when the particular service's terms or another applicable permission have
been checked separately, take a read-only local snapshot of one already-open
INPS browser tab. The human performs login, profile/delegation selection, and
navigation with their own credentials. User or studio approval alone does not
establish INPS permission for software-assisted capture. Vera stores no cookies
or browser state and cannot submit or activate anything. Official downloads are
the default evidence; every conclusion remains a draft for professional review.

The Registro Imprese e SARI module prepares a source-backed draft for a
Registro Imprese/REA/Comunicazione Unica practice and keeps DIRE, INPS, INAIL,
SUAP, and IVASS/RUI questions separate. Its ordinary SARI flow is public,
browser-assisted, read-only, and human-selected. SARI's undocumented JSON routes
remain disabled without separately verified written reuse authorization. Vera
does not receive filing credentials, operate a live DIRE session, contact SARI
support, sign, pay, or submit.
