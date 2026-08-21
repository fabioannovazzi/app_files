---
name: browser-automation
description: Use when an authorized operator wants Vera to record a supported visible-browser procedure for later automation development; currently the post-login Agenzia delle Entrate active/passive invoice request and ZIP-retrieval journey.
---

# Automazione web

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

In Codex Desktop, resolve `../../modules/browser-automation` from this skill
directory when it exists; otherwise resolve `../../../browser-automation` in
the repository. Read that module's `skills/browser-automation/SKILL.md`
completely and follow it. Treat the resolved module root as the plugin working
directory for all commands, scripts, requirements, references, and run setup.

For the supported Agenzia procedure, resolve the Vera root as `../..` from this
wrapper directory and start one PTY command:

```bash
python <vera-root>/scripts/managed_python_runtime.py --module browser-automation --requirements requirements-portal-recorder.txt run scripts/record_agenzia_invoice_flow.py --output-dir <fresh-private-directory>
```

The managed launcher installs and validates the selected optional requirements
and starts the recorder in the same process. A missing-Playwright result is not
a completed preflight. If setup reports `MPARANZA_NETWORK_PERMISSION_REQUIRED`,
immediately rerun that exact PTY command with Codex host network approval. This
approval may retrieve only the published requirement file selected by the
command. Do not stop with a missing-Playwright diagnosis, ask the operator to
install it manually, or split setup and recorder launch into separate commands.
If the operator denies approval, report that denial as the blocker. Never look
for `requirements.txt` or `scripts/` inside this wrapper directory.

On another surface, explain that the current privacy-bounded recorder requires
Codex Desktop and a local visible Chrome session. Continue with any useful
scope preparation, but never request credentials, substitute a video, claim
that recording created an executable automation, or control authentication on
the operator's behalf.
