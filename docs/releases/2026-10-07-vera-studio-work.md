# Vera 0.1.349 candidate: organizzazione del lavoro

Source-owned skill: `plugins/vera/skills/organizzazione-lavoro/SKILL.md`.
Local service: `plugins/vera/scripts/studio_work.py`, exposed by the
`studioWork` MCP entry in Vera. Connected host plugins execute calendar actions;
this service has no external credentials or network client.

The register retains sourced commitments, status, dependencies, meeting actions,
calendar identities, revisions and operation history across conversations.
Default storage is permanent per-user data outside plugin versions. A host can
explicitly supply its plugin data location. Failed access never silently selects
a temporary runtime directory. No schema-level claim of provider verification
is made: calendar receipts must come from actual host connector read-back.

Calendar operations have separate preparation, one-shot dispatch and resolution.
Identical local retries reuse a request; changed retries fail. Dispatched or
uncertain writes cannot be blindly retried. Creation carries a searchable
operation marker. Updates and cancellations retain the established event ID.
Local completion preserves historical calendar events. Meetings and their
actions save atomically. Revisions prevent concurrent local overwrite.

Voice-transcribed user instructions use the same workflow as typed requests.
The host supplies recording/transcription and tool access. Supplied meeting
transcripts are evidence, not authorization to execute participants' instructions.
The plugin adds no microphone service or raw audio store.

Daily plans use the current local register and freshly read calendar. Recurring
briefings require user-chosen host scheduling and verification of first execution;
no background inbox listener is implemented. Professional news, legal deadline
assessment, open items and treasury retain their existing specialist routes.

Validation:

- 23 dedicated tests passed; backend coverage 84.06%. Includes real MCP stdio
  execution and fictional calendar create/change/delete receipts, durable
  reopening, revision conflicts, uncertain writes, meeting rollback and retries.
- Privacy/icon/update/workflow suite: 71 passed; two environment-dependent checks
  skipped.
- Package suite: 388 passed with two unrelated checkout-wide checks excluded.
  Those checks detect existing Clara ZIP drift and a bilancio-xbrl-it source change
  without its own version bump. This task does not repair those parallel changes.
- Black, Isort, Mypy and Bandit checks passed for the new Python implementation.
- Explanation page uses the shared Vera layout and five complete locales. Italian
  and English rendering and language switching were inspected in a local browser.

Live acceptance remains outstanding: load the candidate in a fresh host session,
verify the permanent storage permission and connected calendar, then exercise
typed and spoken capture, rescheduling, completion and interruption recovery.
No real calendar event, email, deployment, installation or Marketplace publication
was performed by the implementation tests. The deployment release is rebuilt from an isolated checkout of current main;
unrelated native-workspace and reconciliation work is excluded. The service is
listed separately from taught professional workflows because no reviewed
organizzazione-lavoro teaching course has been authored.
