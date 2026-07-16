---
name: plugin-release
description: Use after changing any Codex plugin under plugins/ to rebuild downloadable plugin ZIPs from repo source, verify package layout, and ensure generated plugin artifacts have not drifted from the editable source.
---

# Plugin Release

Use this skill after editing any Codex plugin under `plugins/<plugin-name>` or when the user asks to package, publish, refresh, or verify a downloadable Codex plugin ZIP.

## Source Rule

Only edit plugin source in the repo:

```text
plugins/<plugin-name>
```

Do not edit downloaded plugin folders, Codex cache folders, or extracted ZIP contents as source:

```text
~/Documents/codexplugins/...
~/.codex/plugins/cache/...
static/shared/*/downloads/*.zip
```

The ZIP is generated. Codex cache is generated. Downloaded install folders are generated or user-local.

## Required Workflow

1. Finish source edits under `plugins/<plugin-name>`.
2. Ensure the plugin declares runtime dependencies in `requirements.txt` when it
   uses Python libraries beyond the standard library.
3. Ensure the plugin includes `scripts/check_dependencies.py` and its skill tells
   Codex to run it before helper scripts. If optional dependencies exist, document
   when to check the optional requirement file.
4. Run the relevant plugin tests.
5. Rebuild the ZIP from repo source:

```bash
.venv/bin/python scripts/build_codex_plugin_zip.py <plugin-name>
```

Use `all` or omit the plugin name to rebuild every configured plugin package.

6. Verify package drift:

```bash
.venv/bin/python scripts/build_codex_plugin_zip.py <plugin-name> --check
```

7. Run package integrity tests:

```bash
.venv/bin/python -m pytest tests/plugins/test_codex_plugin_packages.py
```

8. In the final response, report:

- plugin source path;
- ZIP path;
- tests run;
- whether the ZIP matches repo source.

## Post-publish update notification

Clara and Vera include a `SessionStart` hook that checks the public manifest at
`static/shared/codex-plugin-versions.json`. Codex asks the user to trust this hook
before it runs. The manifest must describe what OpenAI has actually released,
not what is merely built or submitted.

After OpenAI shows a new Clara or Vera version as **Published**:

1. Update that plugin's `published_version` in
   `static/shared/codex-plugin-versions.json` to the exact released manifest
   version.
2. Deploy the static manifest through `deploy-app-files`.
3. Verify the public JSON URL returns the released version.

Do not update `published_version` while a submission is draft, pending, rejected,
or still under review. Advertising an unreleased version would notify users about
an update they cannot install.

## Failure Rule

If a ZIP check fails, rebuild the ZIP from source. If a test says source and ZIP differ, do not patch the ZIP manually; fix source or rebuild with `scripts/build_codex_plugin_zip.py`.
