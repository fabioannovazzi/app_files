---
name: browser-automation
description: Use when an authorized operator wants Vera to record how a supported web procedure is performed in a visible browser so a reviewed automation can be developed from observed controls and transitions. The current supported procedure is the post-login Agenzia delle Entrate active/passive invoice request and ZIP-retrieval journey; do not use for ordinary web research, Studio Archive retrieval, desktop-app automation, or autonomous portal operation.
---

# Automazione web

The current workflow records a bounded implementation map. It does not acquire
invoices, create an executable automation, or establish a reusable portal
connection. Use Italian for every user-facing message in this workflow.

## Supported procedure: Agenzia invoice flow

Use this procedure when an authorized operator asks to show or teach Vera how
active or passive invoices and their ZIP are requested and retrieved from the
Agenzia delle Entrate portal.

1. State that the operator must use their own authority, login, taxpayer
   profile, and delegation. Never ask for or enter a username, password, PIN,
   SPID/CIE/CNS material, QR code, one-time code, cookie, token, or session URL.
2. From this component directory, run:

   ```bash
   python scripts/check_dependencies.py --requirements requirements-portal-recorder.txt
   ```

3. Create a fresh owner-only temporary output directory outside the Git
   workspace. Start the recorder in a PTY so the process remains alive across
   the operator's checkpoints:

   ```bash
   python scripts/record_agenzia_invoice_flow.py --output-dir <fresh-private-directory>
   ```

4. At the optional private-term prompt, send an empty line by default. Never
   ask the operator to put private redaction terms in chat. Custom terms must be
   typed directly into the local terminal.
5. The recorder opens a dedicated ephemeral Chrome context and creates an
   explicit page before authentication. On Windows it restores and positions
   that Chrome window and verifies that Windows exposes a visible, non-empty
   desktop window owned by the browser process launched for this recording.
   An unrelated or background Chrome process cannot satisfy the gate; stop
   before authentication when it fails. The operator authenticates and selects
   the correct taxpayer or delegated profile. Say: “Quando hai completato
   l'accesso, di' a voce oppure scrivi `pronto`; va bene anche `ready`.” Then
   send one newline to the still-running PTY. Do not inspect or operate the
   authentication screens.
6. Ask the operator to perform one representative mass-download journey,
   including active/passive scope and a completed ZIP retrieval when available.
   Say: “Quando hai finito, di' a voce oppure scrivi `fatto`; va bene anche
   `done`.” Then send one newline to stop. If submission and later retrieval
   cannot occur in one session, make two separate recordings.
7. The recorder closes its Playwright-managed temporary browser profile,
   deletes Playwright-managed download bytes, and writes only
   `agenzia_invoice_flow_recording.json` with owner-only permissions. Never
   save or request a Playwright trace, HAR, storage state, cookies, screenshots,
   HTML, or invoice ZIP for this procedure.
8. Do not read the JSON into model context until the operator has opened it,
   reviewed it for private information, and explicitly said it is safe to use.
   If approval is withheld, leave it unread and explain how to delete it. An
   approved recording is implementation evidence for page paths, control
   identities, transitions, and download shape only.

The recorder strips URL queries and fragments, blocks non-Agenzia origins after
recording starts, suppresses table-cell text, hashes suggested download names,
excludes typed or selected values and downloaded bytes, and marks every result
as requiring human review. These controls reduce exposure; they do not
guarantee anonymization. Read
`references/agenzia_invoice_flow_recording.md` completely before a run.

The local deterministic script owns only the mechanical capture boundary,
window-visibility gate, allowlists, redaction patterns, and output validation.
It does not decide authority, professional relevance, privacy sufficiency, or
whether the observed journey should become an automation.

Reserve explicit approval for an external, destructive, approval-sensitive, or
material step. In this workflow, entering the portal is the operator's external
action and approving the reviewed JSON for model use is the material data
boundary; ordinary recorder progress does not require repeated approvals.

Material choices are limited to the authorized portal procedure, whether the
representative journey covers active invoices, passive invoices, or both, and
whether delayed ZIP retrieval requires a separate recording. Derive them from
the actual inputs, ask only those unresolved choices in chat, and do not offer
named automation frameworks, capture formats, or output packages unless the
facts cue them. Do not propose any additional choice unless the facts cue them.

## Codex-Native Run UX

1. Start with a visible checklist for dependency readiness, authority boundary,
   private output location, login handoff, representative journey, local review,
   and approval for model use.
2. Show a compact Run Intake table with the portal procedure, active/passive
   scope, output directory, recorder status, assumptions, and exclusions.
3. Put unresolved scope or privacy questions in a Decision Table with the
   evidence basis, proposed next action, and operator decision. Facts already
   established by the operator are not choices to propose.
4. Before starting the recorder, show an execution checkpoint with the private
   output location, the no-credential boundary, and the expected JSON artifact.
5. Default output policy: create only the owner-readable recording JSON and,
   when useful, a private `codex_run_review.md` that records status, privacy
   review, unresolved items, and next action without copying portal content.
6. End with an Artifact Card listing each local path, purpose, review status,
   unresolved items, and next action. No generated ZIPs are part of this
   recording workflow and must not be created from portal or run artifacts.

## Output location

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or another published folder. Use a fresh private local
directory selected for the recording and do not overwrite an earlier result.

## Plugin Improvement Feedback

Keep the improvement note local to chat or run artifacts. Do not transmit it,
include client or portal data in it, or turn a workflow result into feedback.
