# Vera workflow UI theme

The canonical stylesheet is `plugins/_shared/ui/vera-theme.css`. It uses the
Vouching review's neutral surfaces, green-grey accent, system font stack,
rounded controls and quiet status colours. This is Vera CSS, not OpenAI CSS.

Edit that file to change the palette, font, heading scale, control spacing,
radius or focus treatment. Keep layout and workflow behaviour in the individual
surface's CSS and JavaScript. Do not edit installed plugin caches.

After editing the theme, activate the repository environment and synchronize:

```sh
source .venv/bin/activate
python scripts/sync_vera_ui_theme.py
python scripts/sync_vera_ui_theme.py --check
```

The synchronizer embeds the theme in the native workspace (including its
study-work panel), research subscription panel, agency acquisition panel,
bilancio workspace, treasury editor, company-visit intake, model-selection
panel and all 13 specialist review widgets. The 11 generated review widgets
also receive the theme whenever their normal generator runs. Generated blocks
are marked with `VERA_SHARED_THEME_START` / `VERA_SHARED_THEME_END` and must not
be maintained separately.

Embedding is intentional: MCP resources and exported local pages remain
self-contained, with no stylesheet network requests or dependency on Codex's
own CSS. The package builder includes `ui/theme.css` and themes Vera's copies
of shared courseware before computing the package integrity manifest. It also
embeds the latest canonical theme in the workflow resources, so a normal host
package rebuild picks up a central edit even before source previews are synced.
Lesson metadata pins the themed bytes and retains the original source hashes.
Other products' courseware is unchanged. Regenerate and verify host packages through
the normal release process after source changes.

Legacy variables such as `--blue`, `--navy` and `--cyan` are neutral aliases
of `--accent`. Their names are retained so layout-specific selectors and
generated views keep working. They no longer imply a blue brand treatment.
Errors, warnings and successful states retain distinct muted semantic colours.

This theme governs plugin workflow interfaces. It does not restyle the public
website, professional report templates, quantitative chart palettes or plugin
icons. Inline and fullscreen versions use the same compiled stylesheet; host
placement, review state and persistence are unaffected.
