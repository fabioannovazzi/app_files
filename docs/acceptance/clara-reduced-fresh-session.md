# Reduced Clara fresh-session trial

Outcome: incomplete at the test harness's 600-second limit. The session had not
sent its final answer; this is not a completed native-session acceptance pass.
The presentation itself was produced and reviewed successfully. Its missing privacy
report is recorded separately and is not the reason for the incomplete verdict.

A new isolated Codex CLI home registered only `clara@clara-local-acceptance`
0.1.384, extracted from the corrected ZIP with SHA-256
`f86dbc35ca5274e6c55dab43aa83b7fc087d56a1e9352f4317411cb29cc21af0`.
Installed plugin bytes were unchanged after the test. No active plugin installation
was replaced. The temporary authentication copy was removed after the session ended.

The test inherited the configured model and effort: gpt-6-astra, xhigh. It used a
normal Italian request for two slides from a synthetic brief, with no prewritten
slide plan. The isolated test instructed local-only reporting and prohibited
other plugins, repository fallbacks, external data and publication.

Observed:
- The fresh session discovered the reduced Clara skills and selected HTML-deck.
- It preserved the supplied USD 25.356.432,55 revenue and A/B/C shares 16%, 13%, 9%.
  It distinguished recommended checks from facts and did not conclude on acquisition.
- It generated editable sources, a standalone HTML presentation and a ZIP.
- Browser startup first failed under sandbox restrictions. A diagnostic command
  also exited 1 because the failed attempt had produced no screenshot files.
  The session preserved the failed QA evidence, used the normal approval path and
  reran successfully with the available Chromium executable.
- Mechanical QA reported pass while a sidebar covered slide text. The session's
  subsequent visual-review/correction sequence removed the overlap and increased
  label contrast; the parent independently inspected original and corrected images.
  Final QA: 151 pass, 1 inapplicable fragment check, 4 viewports, 8 screenshots.
- Planning and privacy instructions occupied a substantial part of preparation.
  Reading/reviewing source and visual correction also took time. No controlled
  comparison establishes how much delay each contributed.
- At 600 seconds the harness stopped the session. Final conversational handoff and
  readable privacy report were absent. No server report was transmitted.

Evidence: `output/clara-distribution-candidates-2026-11-06/fresh-session-evidence/`
contains the transcript, input prompt, summary, initial overlap screenshots and
copied work folder. The corrected final HTML is
`work/7e8ea08a1c2111c2cd29d201181c2c34276f836341d15f015316640a6167725d/index.html`.

This establishes fresh Codex skill discovery and functioning local generation with
visual recovery. It does not establish timely end-to-end completion or Marketplace
host compatibility. No upload, publication or product-code change occurred.

Repository inventory: 9 local branches, 8 remote branches, 9 worktrees, 0 stashes. This trial created none.
