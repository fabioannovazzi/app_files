---
name: browser-automation
description: Use when an authorized operator or developer wants Vera to teach, discover, build, validate, or run a repeatable process on Agenzia delle Entrate, TeamSystem, Gmail, or another website through the operator's existing Chrome session, including when the developer cannot access the target system.
---

# Automazione web

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

In Codex Desktop, resolve `../../modules/browser-automation` from this skill
directory when it exists; otherwise resolve `../../../browser-automation` in
the repository. Read that module's `skills/browser-automation/SKILL.md`
completely and follow it. Treat the resolved module root as the plugin working
directory for its contracts, example capabilities, references, and validation
commands.

This is a generic capability factory with process-specific outputs. The
operator may demonstrate the process (`guided`), let the model explore safe
reversible paths (`autonomous`), or combine both (`hybrid`). A reviewed
sanitized developer pack lets another person understand and implement the
process without receiving credentials or browser state. A later, separately
approved capability is the executable handoff.

The live route requires the installed Chrome control skill and the user's
connected Chrome extension. It reuses existing Chrome state and does not launch
or install a separate browser or Playwright package. If that Chrome surface is
unavailable, report the one setup instruction provided by the Chrome skill and
stop the live run. Continue with useful process scoping or capability review,
but never claim discovery, execution, or validation without browser evidence.

This workflow has no Computer Use or desktop-control fallback. A required
native or non-browser step is a `native_gap`: hand that exact step to the
operator and exclude it from capability execution and clean replay evidence.

Never look for runtime scripts inside this wrapper directory. The executable
runtime and deterministic capability pipeline live in the resolved module and
have no third-party dependency.
Authentication is always performed by the operator; never request, inspect,
enter, retain, or transfer login secrets or reusable browser state.

On a surface without compatible Chrome control, review or edit a supplied
capability if useful, but state that live discovery and validation require Codex
Desktop with the connected Chrome extension.
