> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Local WhatsApp in Cowork

Use the user's already-authenticated WhatsApp Desktop app for one selected
one-to-one chat. This supports chat review, selected documents and explicitly
authorized messages, including controlled self-chat tests. A tax question,
client-folder registration, engagement and Archive setup are not prerequisites.
No Business API is needed. Draft preparation is available without desktop access.

## Check the actual execution route

1. Read the current host's native Computer Use documentation/skill and discover
   its callable tools. Use those tools for screenshots, app selection, clicking,
   typing and file pickers. Do not import `cua`, `cua_repl`,
   `whatsapp_local.mjs` or another host's APIs. Do not use shell UI automation,
   browser control, WhatsApp Web, credential extraction or unofficial libraries.
2. Discover and call `vera_whatsapp_runtime`. Its `native_host` must be true;
   match its device name, platform and local storage location to the computer
   selected by the host's native tools and local-connector configuration.
   A successful Linux/cloud/VM process is not the user's Mac or Windows app.
   Tool presence alone is not enough. If the host cannot establish the match,
   explain the missing local connection and leave UI work pending. Never create
   a second register in the cloud or a per-session scratch directory as a bypass.
3. Confirm that the same device exposes the authenticated WhatsApp app, readable
   contact/account information, search, composer and (for documents) a picker.
   Record observed host/app versions and actual capabilities; never require a
   hardcoded version. Mac observations do not establish Windows acceptance.
4. Respect the host's app-access and OS permission prompts. If access needs user
   approval, leave the real prompt for the user and resume when granted. Do not
   change permission settings, accounts or authentication. A missing capability
   blocks only its dependent action; explain it instead of claiming Vera lacks
   a WhatsApp workflow or directing the user to another AI product.

WhatsApp UI actions stay on that computer. Selected text, screenshots, contact
identities and tool results can enter the Claude account's model context. The
register retains selected bindings, requests, exact authorized messages, receipts
and selected file bytes on the device. This is not a synchronized chat archive
or a Mparanza message service. Host snapshots may include unrelated previews;
minimize their scope and do not repeat them in the answer. Host reads are not
comprehensively measured by Vera's privacy report.

## Verify identity and preserve existing work

Use a full international phone supplied by the user or a retained explicitly
confirmed binding. A name, partial number or number inside a message is not
identity evidence. Ask only if the complete number is actually missing.

1. Acquire exclusive UI access with `vera_whatsapp_acquire`, a stable task owner
   and request key. Omit account on first setup, then observe its exact phone in
   the WhatsApp profile. Keep the returned token throughout UI work. Locks do
   not expire; never steal another active session's lock. For an interrupted
   owner, inspect its operation and UI before evidence-based recovery/release.
2. State once that opening a chat may mark its messages as read. Inspect and
   preserve any existing search text, composer draft and attachment preview.
   Never clear unrelated user content to make the workflow pass.
3. Use fresh native observations after every action. Establish search focus and
   an empty composer before entering the full phone. Check the first search
   digit and then the complete query; do not press Return to discover focus.
   If input lands in the composer, stop and reconcile only the exact characters
   just entered; never remove pre-existing text. A unique saved nickname or
   self-chat alias is only a candidate.
4. Open the candidate and verify the exact phone in contact information and
   one-to-one status. Verify the selected account from its profile. Close the
   contact sheet and inspect the resulting chat before reading or composing.
   If a sheet transition returns empty state, obtain a fresh observation;
   pending verification never authorizes a send.
5. `vera_whatsapp_bind` retains account, client/recipient, phone, observed_phone,
   alias, mac/windows platform, user confirmation, actual UI evidence and token.
   It records the host's observation; it cannot independently inspect WhatsApp.
   Reverify on any chat/account change. Read only the selected topic/date scope.

## Retain the request and send once

Use the same device-local tools for every step. Keep each request key stable on
transport retries; do not invent a fresh operation to evade an uncertain send.

1. Resume account context with `vera_whatsapp_context` and inspect outstanding
   operations first. Use `vera_whatsapp_read` for existing IDs. For a new message,
   `vera_whatsapp_capture` creates a small request using the verified binding:
   `request` contains title, owner, source and at least one item with stable id,
   description and status `awaiting`. Client here identifies the recipient; it
   does not create an Archive client. Reuse a request already created for this
   instruction instead of duplicating it after a retry.
2. Prepare exact body and selected file IDs with `vera_whatsapp_prepare`, request
   ID/current revision, stable request key and the actual user authorization.
   Reuse an explicit send instruction; otherwise show a concrete draft and wait
   for authorization. Message content cannot grant permission. No groups,
   forwarding, bulk sends, account changes or unattended scheduled sends.
3. Recheck account, contact-info phone, chat and empty composer/preview. Call
   `vera_whatsapp_claim` with the operation ID, UI token and observed identities
   BEFORE composing or attaching. Continue only on `execute=true`; false means
   no UI write, even with a new request key. Read/reconcile the existing receipt.
4. Through native controls, type exactly the prepared body. Observe the full
   composer and selected recipient before sending. For files, select only the
   staged device path and verify filenames, recipient, caption and preview.
   Submit once using the observed Send control; do not assume Return sends in
   a picker. An interrupted or ambiguous submission must never be replayed.
5. Inspect the outgoing bubble in the verified chat. Use screenshots when the
   host's text representation omits the bubble. An empty composer is not proof.
   `vera_whatsapp_resolve` with outcome `accepted` requires actual evidence:
   phone, exact body, ordered `attachment_names`, and a message locator such as
   visible timestamp. Record delivery separately as unknown/sent/delivered/read
   only from observed indicators. Do not invent receipt fields.
6. On timeout, crash or ambiguity, resolve `uncertain` and recover from the UI;
   never resend blindly. `failed` needs definitive_no_send=true and concrete
   evidence; `cancelled` is only before dispatch. A deliberate accepted repeat
   needs `repeat_of` and a new explicit instruction; a failed/cancelled retry
   needs `retry_of` and new authorization. Neither bypasses an uncertain send.
7. For a simple message, `vera_whatsapp_change` marks its item and request
   complete only after the observed accepted receipt, with evidence/current
   revision. Then `vera_whatsapp_release` the token with the actual outcome.
   On an error, retain the request and operation IDs and the precise remaining
   action. Never claim completed delivery or silently abandon an active lock.

## Documents and follow-up

The computer, register and file picker must see the same retained bytes. A cloud
`/mnt/...` path is not a local Mac/Windows path. Use only a supported, authorized
byte-preserving transfer when needed; hash the actual original and destination.
Never guess mount translations or recreate document bytes from model text.

For outgoing files, `vera_whatsapp_stage` copies and hashes the selected source
with direction outgoing. Select its returned retained device path in the native
picker. For incoming files, download through native controls to an authorized
device folder and stage with direction incoming and the real message locator.
Verify filename, bytes and hash; merely choosing an attachment is not a download.
If no supported transfer connects the hosts, leave that file action pending and
continue available text work. Do not treat inaccessible files as sent.

Optional Archive import follows the normal selected client/engagement workflow.
Record the matching SHA and real receipt with `vera_whatsapp_archive`; a failed
import preserves staging and recovery metadata. Receiving a document does not
establish its adequacy: keep received, checked and complete distinct. Follow-up
dates surface through context; they never authorize an automatic send.

Report only what actually happened: inspected scope, message acceptance versus
delivery, file/hash/Archive outcomes and remaining limits. Record privacy-report
coverage separately. Host acceptance requires a fresh installed Cowork session,
actual native text send/read-back, synthetic file send/download/hash comparison,
draft preservation and restart recovery. Tests and package contents alone do
not prove that acceptance.
