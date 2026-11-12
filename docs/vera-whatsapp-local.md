# Vera local WhatsApp implementation

The local mode uses the professional's authenticated WhatsApp Desktop through
Codex Computer Use. Vera's local MCP stores requests and receipts; it has no
WhatsApp credentials, network client or background receiver. The official Meta
API connection through Mparanza remains a separate future implementation.

## Shipped components

- `plugins/vera/scripts/whatsapp_requests.py`: owner-local SQLite records,
  confirmed account/client bindings, revisioned document requests and item
  evidence, on-demand follow-ups, private retained attachment bytes and hashes,
  Archive recovery receipts, exclusive UI ownership and one-time dispatch claims.
- `plugins/vera/mcp/whatsapp.cjs`: twelve `vera_whatsapp_*` tools exposed by the
  existing studio-work service and generated on-demand catalogue.
- `plugins/studio-archive/scripts/whatsapp_local.mjs`: current native CUA adapter,
  capability probe, exact contact-info verification accepting saved aliases,
  selected-chat extraction and exact claimed text composition/submission.
- Studio Archive routing, privacy declarations and scenario evals cover selected
  downloads and authorized one-to-one sends. Legacy standalone/Lucia read-only
  routing remains available.

The register uses the existing owner data root, under `studio-work/whatsapp`.
Windows defaults to `%LOCALAPPDATA%/Mparanza/Vera/studio-work/whatsapp`.
macOS defaults to `~/.local/share/mparanza/vera/studio-work/whatsapp`.
Operator/host storage overrides use the existing studio-work configuration.
Neither plugin cache upgrades nor a new conversation reset the register.

Mechanical checks protect exact identities, revisions, file bytes and dispatch
uniqueness. The host model interprets messages, document relevance and completion.
User authorization and UI evidence are recorded as supplied by that host; this
local service is not an independent attestation of WhatsApp delivery.

## Native compatibility evidence, 12 November 2026

| Check | macOS 27.0 / WhatsApp 26.41.74 | Windows |
| --- | --- | --- |
| Inventory and read current controls | Observed | Live host unavailable |
| Search complete international phone | Passed, digit-by-digit | Requires live test |
| Exact contact-info phone, saved self alias | Passed | Requires live test |
| Labelled authorized text send/read-back | Passed, one outgoing bubble at 22:46 | Requires live test |
| Synthetic document send | Passed, one outgoing bubble at 22:48 | Requires live test |
| Save document and compare retained bytes | Passed, 282 bytes, identical SHA-256 | Requires live test |
| Existing draft preservation | Synthetic regression | Synthetic regression |
| Restart and concurrent-session recovery | Synthetic SQLite/process tests | CI matrix configured |

The controlled destination was explicitly selected by the operator. No client
documents were used. The synthetic file was `vera-whatsapp-test-2026-11-12.txt`;
its original and downloaded bytes both hash to
`f4e780bf2075aef0750bafdd3b32f9bd8fca2bc25cc16f1bf547d010fd85c46d`.
Actual contact/operation records stay in the local test workspace, outside git.
No resend occurred during recovery. Final search and composer were empty.

Observed native issues and recovery:

1. The old guard rejected a unique phone search result because its saved alias
   differed from the user's name. The new route treats it as an unverified
   candidate and requires the exact contact-info phone before reading/sending.
2. Current Mac contact info uses `ContactInfo_CloseButton`, including self-chat
   headings with directional marks. A closed sheet can expose an empty window
   until the next CUA call. Verification now preserves a pending phone proof and
   requires a separate successful chat observation before continuing.
3. Clipboard paste left the composer empty; `setValue` was unavailable on the
   empty composer. Plain `typeText` into the freshly verified composer worked.
   The maintained adapter uses this method and checks the exact result.
4. The synthetic document bubble was visible in a screenshot but omitted from
   the accessibility tree. Native screenshot/context-menu `Save as` recovered
   the selected document. Missing AX content does not imply absence of a file.

## Acceptance limits and recovery

The live run exercised source helpers and the durable local ledger in the
development checkout, not a freshly installed released plugin. The text send
required the documented typing fallback before that correction was incorporated.
Full native regression of the final packaged helper, a fresh conversation,
independent client-number chat and professional document review remain acceptance
work. Actual Archive import was not exercised; retention through Archive failure
and matching-hash receipts are covered synthetically.

Windows code/bridge tests run in the `whatsapp-local` CI matrix. The screenshot
route discovers the actual Windows window and controls without Mac selectors.
CI does not establish authenticated Windows UI compatibility. Run the same
controlled native tests on a real Windows installation before declaring support.

A dispatch claim is persisted before UI composition or attachment selection.
Only its first response permits execution. Timeouts/crashes retain uncertainty;
inspect the selected chat before resolving, never blindly resend. Repeated
content reuses its receipt. Deliberate repeats of accepted content require a
new specific instruction and `repeat_of`; failed/cancelled retries use `retry_of`.
Locks never silently expire. Recovery exposes the existing owner/token and
unresolved operation so an ended session can be reconciled before release.

Follow-up dates surface when a session asks for account context. They neither
install a scheduler nor authorize unattended messages. Attachment staging
retains bytes even when Archive is unavailable. Incoming receipt and professional
checking/completion are distinct item states.

Privacy declarations describe selected local retention, model-visible records
and authorized WhatsApp transmissions. Host initial app/file-picker observations
can expose unrelated previews or filenames; later reads are narrowed. No full
host-exposure measurement or signed privacy report was produced for this
development UI test. This gap is separate from the observed messaging/hash result.
