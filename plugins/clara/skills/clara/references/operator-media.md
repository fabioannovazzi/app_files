# Local operator media

Use `clara_media_open` in Codex for transcription, recorded deck feedback and
approved research-video narration. Keep the operator in the native MCP panel
and this chat. Do not open an upload page or ask the operator to transfer JSON
or ZIP files. External participant interviews retain their hosted participant
link; that is a different audience and workflow.

1. Use the explicit case/work folder. For narration this is the prepared,
   already-approved research-video run. For existing audio, pass its selected
   absolute path as `source`; otherwise the panel can select a file and save
   it locally. Do not ask users to type local paths if the chat already has them.
2. Open with operation `transcribe`, `deck_feedback` or `narration` and the
   user's supported language. No media is sent externally by opening/selecting.
3. The panel records the user's Continue action and hands an opaque session
   back to this chat. Read `clara_media_status`. Use `clara_media_run` with an
   already-authorized private Mparanza session-cookie file, when available.
   Never extract browser cookies or ask the user to paste credentials into chat.
   No API key is required by this workflow. An unavailable authenticated session
   is an explicit `authentication_required` limitation; preserve local selection
   and do not claim processing completed. Local MCP does not grant a new account.
4. The local worker calls the existing authenticated Mparanza service, retains
   the bundle, imports transcription into the work folder/case or attaches the
   verified narration to its approved run. It sends selected audio without case
   context, or the exact approved narration request, not source documents.
5. Consume the saved result: review speaker attribution/transcript for
   transcription; for deck feedback continue the existing timeline and deck
   revision workflow using the original retained recording; for narration
   continue the existing local render and verification steps. Processing a file
   does not itself complete a deck correction or research video.
6. `complete` is only recorded after bundle import/attachment. Repeated completed
   calls verify retained output. `processing`/`needs_review` after interruption
   must be reconciled with retained job files before any retry; do not submit a
   second remote job merely because the first call timed out.

The panel requests microphone capability, but uses it only after the host grants
it and the user presses Record. If unavailable, keep file selection available.
Screen capture is not declared by this MCP resource; use an existing screen
recording for deck feedback. Do not silently open another browser or weaken host
permissions. Report this host-dependent live-capture limitation separately from
successful local file handoff and processing.

For Cowork or a host without the native panel, continue with existing file-based
helpers and clearly state the available interaction. Do not claim a native panel
was used. Normal draft work is never gated on optional media capture.
