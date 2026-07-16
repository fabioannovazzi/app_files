---
name: plugin-icon-theme
description: Use whenever creating, updating, reviewing, or releasing Codex plugins under plugins/ so plugin icons stay on the shared Mparanza black seal theme, are generated from scripts/generate_plugin_icons.py, remain distinct, and package ZIPs are rebuilt after icon or manifest changes.
---

# Plugin Icon Theme

Use this skill for any Codex plugin work under `plugins/`, especially when
creating a new plugin, changing `assets/icon.svg`, changing plugin manifests, or
rebuilding plugin ZIPs.

## Theme Rule

All plugin icons must use the shared Mparanza seal theme:

- black rounded tile: `#171816`;
- ivory glyphs: `#F7F0DF`;
- one small colored corner/stamp accent per plugin;
- simple, distinct workflow glyphs;
- no random scripts, pseudo-Chinese characters, generic AI symbols, gradients,
  duplicated icons, or one-off visual systems.

The aim is family resemblance first, distinct recognition second.

## Required Workflow

1. Edit icon specs in `scripts/generate_plugin_icons.py`, not individual SVGs,
   unless doing a short-lived experiment.
2. Run:

```bash
source .venv/bin/activate
python scripts/generate_plugin_icons.py
```

3. If a plugin icon changes, bump that plugin manifest patch version in
   `plugins/<plugin>/.codex-plugin/plugin.json`.
4. Run:

```bash
pytest -q tests/plugins/test_plugin_icon_theme.py
```

5. Before delivery, follow `plugin-release`: rebuild affected plugin ZIPs and
   verify with `python scripts/build_codex_plugin_zip.py --check`.

## Adding A New Plugin

When a new plugin is added:

- add an `IconSpec` for it in `scripts/generate_plugin_icons.py`;
- choose a distinct `motif` or add a new simple glyph body;
- run the generator;
- ensure `tests/plugins/test_plugin_icon_theme.py` passes;
- rebuild the plugin ZIP after the manifest and icon are final.
