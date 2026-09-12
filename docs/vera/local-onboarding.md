# Vera local onboarding: implementation and acceptance

Vera 0.1.243 introduces a mandatory one-off desktop introduction at the next
Vera invocation for both new and existing users. A short Italian-default native
voice conversation creates a user-confirmed professional profile, then teaches
three or four relevant workflows through demonstration and guided practice.
The native model chooses questions, workflow relevance and professional meaning.
Local Python enforces storage integrity, revision conflicts, exact lesson
handoffs, evidence hashes and completion prerequisites.

The entry contract lives in `plugins/vera/skills/vera/references/local-onboarding.md`.
It runs before ordinary routing and is also present in every professional entry
wrapper. Setup is itself a supported Vera action. The startup hook reports only
state, suppressing update/CR requests while onboarding is pending. Completion
is independent of installed plugin version and current client/project.

`local_onboarding.py` uses only the standard library, one OS-user directory and
an enrollment sentinel. It saves interview checkpoints, the confirmed profile,
paired native thread IDs, lesson state and optional local feedback. It rejects
stale writers, corrupt/missing enrolled state, invalid handoffs and changed
lesson artifacts. It preserves a prior checkpoint for explicit local recovery.
An entire deleted directory or a changed OS account cannot be detected without
an existing local record; instructions require reconnecting known prior state.
There is no hosted recovery or cross-device synchronization.

`local_onboarding_case.py` prepares genuine portable Studio Archive contexts
beneath a tutorial directory, without changing the studio's archive configuration.
The actual specialist scripts retain their normal input, review and artifact
contracts. Tutorial reports and direct stamp retries remain local under the
`.vera-onboarding-local-only` marker. No Mparanza interview, custom speech/model
API, API key, telemetry, feedback or receipt transmission is introduced.
Ordinary native OpenAI model/voice processing still applies.

The initial teaching chat is Codex. A separate native working chat runs examples
and shows their files. The pair is reused; voice stays in the teaching chat.
Native voice selection remains the user's setting. Local ChatGPT Work receives
the same source-derived helper and must read the same OS-user profile explicitly.
Cloud/mobile chats cannot assume access to this local record. Cowork receives
no onboarding scripts, assets, hook or instruction blocks.

## Verified on 12 September 2026

- 31 onboarding tests pass, covering lifecycle, interruption, profile edits,
  shared discovery, concurrency, recovery, path boundaries, scoped/revoked worker
  handoffs, evidence identity, startup behavior, packaged Codex/Work reuse and
  execution of the real managed XML workflow. New helper coverage: 85.61%.
- 507 existing/extended regression tests pass and two environment-dependent
  tests are skipped across Codex/Cowork packaging, update hooks, privacy,
  model-data reports, workflow registry and release alignment.
- All three synthetic starters were exercised through the genuine managed
  contexts: XML inspection found one invoice (EUR 1,000 + 220 = 1,220);
  journal qualification/normalization accepted six rows and sampled two;
  Actual/Budget analysis produced four account/month comparison rows.
  These calculations do not certify the user's learning or professional approval.
- A real second native Codex task accepted the exact active-lesson token, loaded
  the shared synthetic profile, executed the XML demonstration, reviewed the
  values, built a valid local model-data report and sealed 11 artifacts in the
  portable ledger at `ready_for_review`. It did not simulate user practice or
  mark onboarding complete. Native file-panel openings returned `queued`.
- All 35 affected Cowork skill projections and its receipt runtime compare
  byte-for-byte with the pre-feature behavior. Package identity advances together
  to 0.1.243; Cowork's onboarding behavior is unchanged.
- Python formatting, import order, type checks, Bandit and skill validation pass.
  Privacy source fingerprints and Codex/ChatGPT-upload/Cowork packages were
  regenerated from canonical source, with packaged MCP startup checks.

## Remaining native acceptance and release boundary

The desktop app refuses computer-use automation of its own UI. The plugin
cannot force microphone permission, start voice, choose an account voice or
prove two separate windows are visible. Its instructions guide the user through
those native actions. Actual voice interaction, interruptions and visible
side-by-side teaching require a live user check; they are not certified by task
creation or queued panels. Native local ChatGPT Work has not been exercised in
this run; its packaged helper was executed against the same local state in a
separate process, and host access must still be checked in a live Work session.

A release package is not an installed plugin or a Published Marketplace version.
Keep the public published-version registry unchanged until publication is
actually verified. The synthetic acceptance profiles are separate from the
professional's default profile and do not complete onboarding for the user.
