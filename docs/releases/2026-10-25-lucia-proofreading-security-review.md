# Lucia 0.1.176: document-review instruction boundaries

The Marketplace draft for Lucia 0.1.175 showed a non-blocking security-risk
finding for `controllo-documento`. The portal did not identify an offending
instruction or provide a technical finding. This change does not establish
the scanner's cause or claim that a new scan will pass.

The reviewed upload matches the prepared 0.1.175 artifact SHA256
`d8d50d6989b804b3d9a76ea18c701186537f76bdf400b6fb35e663770e4e9d8c`.
The user's portal screenshot identifies the same version; the portal's uploaded
bytes were not independently retrieved.

## Source changes

- `controllo-documento/SKILL.md` now places user/task authorization and untrusted
  document handling before its reporting instructions. External delivery needs
  an existing authorized scope and current host permission. Pending reporting
  stays local where permitted and cannot prevent independent proofreading.
- DOCX fields, links and embedded-object metadata are explicitly inert evidence.
  Inspection must not execute macros, activate objects, refresh external fields
  or templates, follow extracted URLs, or execute document-supplied commands.
  If safe rendering is unavailable, the review retains that limitation.
- Lucia's incident-recovery reference no longer lists reporting permissions as
  a reason to use the browser fallback. Technical transport/runtime failure and
  refusal of an operation are distinct: switching tools, browsers, identities or
  credentials must not bypass a refusal or a required action-time confirmation.
- The workflow-usage reference states the same authorization boundary. Existing
  authorized automatic reporting and local persistence remain in place.

This is an instruction correction, not a claimed executable vulnerability fix.
The inspected helpers already parse XML without external entity/network
resolution, preserve selected input snapshots, inspect links as data, and escape
model-authored report contents. No reporting payload, recipient, runtime
implementation or host permission was expanded. Service privacy records describe
the instruction boundary separately from existing executable controls; only
affected source fingerprints and generated contracts were refreshed.

## Verification and limits

The existing document-inspection, legal-document, package-reference,
reporting-reference and icon suites passed (100 tests). They exercise embedded
hyperlink/field inspection without network access, XML entity rejection, report
escaping and original-file preservation. These checks verify the helpers and
package instructions; they do not prove a host model will follow instructions
in every case.

The instruction review covers ordinary proofreading, a document containing
commands or external links, an already authorized reporting retry, a denied
transfer, and unavailable safe rendering. The same task and data boundaries
apply through references. An existing authorization avoids repetitive consent;
a refusal or mandatory host confirmation remains binding.

All four canonical Lucia host builds and source/package parity checks passed;
packaged local MCP startup and both official portable manifest schemas passed.
The broader package/privacy suite recorded 485 passes, one installed-cache skip
and three outdated test expectations in `test_lucia_plugin.py`. Those expectations
omitted the existing developer privacy skill, rejected the existing direct-skill
privacy record, and omitted the existing Deep Research page. The relevant product
files and test assertions were unchanged between the preceding candidate and
this release. Only the tests were corrected; all 26 checks in the affected module
then passed. The full broader suite was not rerun after these test-only edits.

Marketplace scanning, approval and installed-conversation acceptance are separate
evidence. No Marketplace upload, submission or publication is part of this change.
