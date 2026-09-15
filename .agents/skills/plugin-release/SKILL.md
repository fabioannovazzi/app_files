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

## One Product Version Across Hosts

Each product has one release version, stored in
`plugins/<plugin-name>/.codex-plugin/plugin.json`. The Codex, ChatGPT upload,
and Cowork builders use that same version. Claude source manifests are metadata
templates and must not declare a separate version. Bump the canonical patch
version for a release on either host, then rebuild every affected host package.
Do not maintain independent Codex and Cowork version sequences.

Before reserving a patch version, inspect the current canonical version and the
product manifest changes in other open release PRs. Choose a version above all
those candidates; do not let independent worktrees publish different packages
with the same version. Immediately before publication, check the authoritative
Published version again. Never publish a lower version over a newer release
unless the user explicitly requests that rollback. If main has advanced, integrate
its source, rebuild and rerun checks before publishing; do not drop the intervening
release or reuse an already-uploaded archive after source changes.

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
.venv/bin/python -m pytest tests/plugins/test_plugin_update_notifications.py
```

The update-notification suite compares the public manifest with locally
installed `openai-curated-remote` marketplace versions when that cache is
available. If it reports that the manifest is behind, verify the marketplace
listing is Published, update the manifest to that exact version, and deploy it
before completing the release.

8. In the final response, report:

- plugin source path;
- ZIP path;
- tests run;
- whether the ZIP matches repo source.

## Installed-version acceptance

Source tests, ZIP parity, server deployment and Marketplace publication never
prove that a user's enabled plugin or already-open conversation updated.
Before reporting a fix as working for a user:

1. Use `codex plugin list --json` to inspect the actual enabled installation.
   Do not infer it from cache directories. A local `mp-vera`/`mp-clara` copy is
   a separate installation; publishing an official version does not replace it.
2. Compare the exact version with the release being accepted. Use the exact
   skill path exposed in the current host catalog, not a newer path discovered
   on disk:

   ```sh
   python scripts/check_installed_product.py vera \
     --expected-version <published-version> \
     --skill-path <currently-exposed-SKILL.md>
   ```

   This command rejects missing, disabled, duplicate, local or wrong-version
   installations and missing or stale exposed skills. Run its unit regressions
   in CI; run the live command on the acceptance host after installation.
3. After replacing an obsolete installation, use a fresh conversation and
   repeat the check there. Never substitute the new cache path into an old
   conversation to manufacture a pass. If fresh-session inspection is unavailable,
   report installation repaired and active-session acceptance outstanding.
4. Exercise the user's actual acceptance case. For privacy-report delivery,
   an ordinary synthetic analysis must show its readable privacy report without
   prompting; a later request must reopen that saved report without rerunning
   the analysis. Backend receipts and saved file paths do not prove delivery.

When repairing an authorized stale local installation, install the official
plugin first, verify it is enabled at the expected version, and only then remove
the obsolete local plugin registration and marketplace entry. Preserve user
case files and tutorial data. Use supported plugin-management commands; never
edit a generated cache or approve hook trust on the user's behalf.

The release is not accepted on every user's computer merely because it passed
on one host. Older copies, declined updates, disabled hooks and already-open
conversations remain explicit rollout limits. Do not promise that a plugin can
force the host to update or replace instructions in an existing conversation.

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
