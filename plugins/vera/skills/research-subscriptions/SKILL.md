---
name: research-subscriptions
description: Connect, check or disconnect the user's existing Eutekne or One FISCALE research subscription for optional evidence inside Vera's existing legal and tax research. Use the user's authorised browser or a callable connector; no publisher API or partnership is required as a Vera policy.
---

<!-- VERA_WORK_CONTINUITY_BEGIN -->
## Work continuity

Before substantive work, read `../vera/references/work-continuity.md` (from the
Vera root skill, `references/work-continuity.md`). Resolve prerequisites upfront,
retain passed choices and the exact job context, and recover failed operations
without discarding progress or making the user repeat settled setup. This also
applies to direct invocation, standalone work and studio-wide workflows.
<!-- VERA_WORK_CONTINUITY_END -->


# Existing research subscriptions

Read `../vera/references/research-subscriptions.md` completely. Open
`vera_research_sources_open` when callable for the native connection panel.
Connecting authorises source use; it never establishes live subscriber access.
Use the actual host browser/connector tools to perform requested access checks.
Do not substitute generic browser-process development or a separate research.

When the UI is unavailable, use the same local register through
`node scripts/research-sources.cjs --state` from the Vera root. For a user's explicit
connection/disconnection, pass JSON on stdin to that executable with
`--action configure`: `provider_id` (`eutekne` or `one-fiscale`), current
`revision`, `enabled`, and `user_authorized: true`. Never ask for a password,
token, cookie, browser profile export or technical configuration file.

The helper uses Node's standard library only. It never installs dependencies,
opens a browser, calls a model, purchases access or independently verifies an
account. If the host cannot run Node or its tools are absent, preserve the
user's explicit choice in the current task and continue available research;
state that cross-chat persistence was unavailable. Do not require setup before
ordinary unsubscribed research.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.
