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

During teaching, the operator explains the work, and Vera owns its technical
translation. Resume supplied checkpoints and saved decisions before asking new
questions. Keep TeamSystem posting and Agenzia invoice download distinct.
For record review, acquire one real record and its proposed mapping within the
authorized data boundary, then produce one populated review entry before
expanding a workbook. Choose a plain layout yourself; do not ask the operator to
select spreadsheet styles, write code or reconstruct understood steps. Ask only
one unresolved process question at a time. A template is not working extraction;
a checked example is not a validated replay. Follow the module's acquisition
loop and persist a precise next step.

This is a generic capability factory with process-specific outputs. The
model leads one example, interprets each demonstrated step and saves a resumable
teaching checkpoint before continuing. It announces when observation stops;
unexplained button changes are not a learned procedure. A paused checkpoint is
distinct from a completed reviewed developer pack. The
operator may demonstrate the process (`guided`), let the model explore safe
reversible paths (`autonomous`), or combine both (`hybrid`). A reviewed
sanitized developer pack lets another person understand and implement the
process without receiving credentials or browser state. A later, separately
approved capability is the executable handoff.

The live route uses Google Chrome managed under Settings → Computer Use →
Google Chrome and the user's connected Chrome extension. Follow the current
connection's browser API documentation and reuse its `tab.playwright` surface
and existing Chrome profile. A separate Chrome plugin is not required. If the
connection is unavailable, direct the operator to that settings page and stop
the live run. Continue with useful process scoping or capability review, but
never claim discovery, execution, or validation without browser evidence.

Local filesystem verification of browser downloads in the normal Downloads
folder is part of the runtime, like writing receipts; it is not desktop control.
The runtime handles it automatically without a documented download `path()` API.

This workflow has no native desktop-control fallback. A required
native or non-browser step is a `native_gap`: hand that exact step to the
operator and exclude it from capability execution and clean replay evidence.

Never look for runtime scripts inside this wrapper directory. The executable
runtime and deterministic capability pipeline live in the resolved module and
have no third-party dependency.
For acceptance testing, run the resolved module's
`scripts/check_installation.py` and use the version returned from that active
manifest as the version under test. Never reject a newer installed Vera because
an old test prompt names a historical version; an exact-version check applies
only when the operator explicitly asks to test that exact release.
For cross-platform acceptance, use the resolved module's shipped
`scripts/acceptance_fixture.py`; do not improvise a local server. Follow the
module skill's exact self-probe and committed-navigation checks before treating
a connected-Chrome `goto` timeout as a terminal fixture failure.
Authentication is always performed by the operator; never request, inspect,
enter, retain, or transfer login secrets or reusable browser state.

On a surface without compatible Chrome control, review or edit a supplied
capability if useful, but state that live discovery and validation require Codex
Desktop with the connected Chrome extension.

For invoice batches, follow the module’s `references/batch-review.md` and use
`scripts/batch_review.py`. Save a durable local report for review after processing,
with exceptions first, proposed and actual treatment, reasons and source evidence.
Francesco need not watch Vera work. Record his later checks and correction requests;
never silently replace a posted entry or mistake a request for a completed fix.

When asked to prepare the saved work for Fabio or a developer, follow the module’s
`references/development-request.md`. Vera locates saved evidence in the known run,
prepares a sanitized development request with results, gaps and acceptance checks,
shows the exact contents for review and exports one approved ZIP. Do not ask the
operator to locate code, reconstruct known steps or zip files. A working local
process can be handed off without calling it broken. CR registration uses the
existing explicit submission route only when transmission is authorized.
