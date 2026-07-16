---
name: hypothesis-site-polish
description: Add, repair, or visually quiet product hypothesis concept websites under concept_sites for /review/product-hypotheses, including listing links, PDP links, hero image paths, artifact captions, de-branded page chrome, and shared Mparanza review styling.
---

# Hypothesis Site Polish

Use this skill when working on static product hypothesis websites served from
`/review/product-hypotheses/site/{doc_id}/` and listed at
`/review/product-hypotheses/page?lang=en`.

## Design Target

Treat each site as a Mparanza review artifact, not as a brand-endorsed
microsite.

- Make the page quiet, professional, and edited.
- Let the hero image carry product character; keep the page shell neutral.
- Use the same neutral Mparanza surface as the listing page unless the user
  explicitly asks for a different treatment.
- Remove page-shell endorsement labels that make the review artifact look like
  an official brand microsite, while preserving relevant analytical evidence.
- Keep the artifact notice directly below hero/board images, never overlapping
  buttons or sitting inside the image.

For typography or intensity work, apply the project design context in
`.impeccable.md` and use the same judgement as `$typeset`, `$quieter`, and
`$critique`: reduce oversized display type, decorative shadows, loud tinted
backgrounds, and brand-like chrome.

## Important Paths

- Static sites: `concept_sites/{doc_id}/`
- Site listing route: `/review/product-hypotheses/page`
- Site viewer route: `/review/product-hypotheses/site/{doc_id}/`
- Shared serving and polish hook: `modules/projects/api.py`
- Focused tests: `tests/modules/projects/test_projects_api.py`
- Repo doc: `docs/product_hypothesis_sites.md`
- Document-permission schema: `config/concept_permissions.example.json`
- Page permission structure: `config/permission_structure.json`

The listing auto-discovers each `concept_sites/{doc_id}/index.html`; the display
title is derived from the directory name.

## Add Or Repair A Site

1. Extract the zip into a stable snake-case directory, for example
   `concept_sites/example_product_hypothesis/`.
2. Ensure the root contains `index.html`.
3. Add or verify the matching `doc_id` in the runtime concept-permissions file;
   use `config/concept_permissions.example.json` as the public schema.
4. Confirm the listing link opens:
   `/review/product-hypotheses/site/{doc_id}/?lang=en`.
5. Confirm the relevant `Open PDP website` or equivalent CTA points to the
   requested external PDP URL and opens outside the static site.
6. Keep internal links relative so nested pages work through the FastAPI
   catch-all route.

## Hero Image Handling

Broken hero images have been the recurring failure mode. Prefer deterministic
HTML fixes over relying on fragile relative paths.

- Inspect every HTML page that should show a hero/board image.
- If an image has broken before or the zip uses brittle asset paths, embed the
  board image as a `data:image/png;base64,...` URI in each page that references
  it.
- If keeping file paths for non-board assets, use local relative paths only and
  verify the exact file exists under the site directory.
- Use an HTML parser such as BeautifulSoup for repeated updates; avoid broad
  string replacement across whole pages.

## Open Board Image Buttons

Do not point `Open board image` buttons directly to `assets/*.png` or other
image files. Those direct image URLs have been brittle in the deployed review
site. Also do not point the button to a `data:image/...` URL, because browsers
can block or ignore top-level navigation to `data:` URLs.

Instead, create a local HTML wrapper page next to the hypothesis page, named
from the board asset, for example
`example_product_board_image.html`. Put the board image in that
wrapper page as an embedded `data:image/...` source, then point the button to
the wrapper HTML page:

```html
<a
  class="button"
  href="example_product_board_image.html"
  target="_blank"
  rel="noopener"
>
  Open board image
</a>
```

Before finishing, verify every `Open board image` link ends in `.html`, its
target exists under the same `concept_sites/{doc_id}/` directory, and the target
HTML contains an embedded `src="data:image/..."` board image.

The shared artifact caption is injected by
`_inject_concept_site_image_overlay()` in `modules/projects/api.py`. If a new
site uses a new hero-image wrapper class, add that selector to the selector list
there instead of manually adding captions to every HTML file.

For linked board images such as `.hypCard > a > img`, insert the notice inside
the link immediately after the image. Do not insert it as a sibling of the link:
grid cards will place that sibling in the text column instead of under the
image.

## Shared Quiet Styling

For cross-site visual changes, edit the central injected `review_style` in
`_inject_concept_site_image_overlay()` rather than each static site's CSS.

Current baseline:

- Background: `linear-gradient(180deg, #ffffff 0%, #fbfcfd 100%)`
- Surface: `#ffffff`
- Card surfaces: force card-like containers to the same white surface with
  `background-image: none`; remove decorative card pseudo-elements such as
  tinted `::after` circles.
- Text: `#0e1525`
- Muted text: `#667085`
- Lines: `rgba(226, 232, 240, 0.82)`
- Shadow token: `none`
- Font stack: `"Instrument Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif`

Keep headings controlled. These sites should not use campaign-scale typography
outside the hero image itself.

## Neutral Page Chrome

Keep `.logo`, `title`, `h1`, `h2`, `.eyebrow`, `.footerTitle`,
`.productTitle`, and footer labels neutral. They should describe the hypothesis
or review workspace, not imply that the page is an official brand property.

## Verification

Run the focused checks after changing the shared hook or adding a site:

```bash
python -m black --check modules/projects/api.py tests/modules/projects/test_projects_api.py
pytest -q tests/modules/projects/test_projects_api.py::test_concept_site_overlay_targets_figure_hero_images tests/modules/projects/test_projects_api.py::test_concept_site_redirects_to_slash_and_serves_nested_page
```

Then scan all concept-site HTML through the injection path:

```bash
python - <<'PY'
from pathlib import Path
from modules.projects.api import _inject_concept_site_image_overlay

root = Path("concept_sites")
missing_style = []
missing_bg = []
count = 0

for path in sorted(root.glob("**/*.html")):
    count += 1
    injected = _inject_concept_site_image_overlay(path.read_text(encoding="utf-8"))
    if "mparanza-hypothesis-review-style" not in injected:
        missing_style.append(str(path))
    if "--mparanza-hypothesis-review-bg: linear-gradient(180deg, #ffffff 0%, #fbfcfd 100%)" not in injected:
        missing_bg.append(str(path))

print(f"checked {count} html files")
print(f"missing style: {len(missing_style)}")
print(f"missing neutral bg: {len(missing_bg)}")
if missing_style or missing_bg:
    print("missing_style=", missing_style[:10])
    print("missing_bg=", missing_bg[:10])
    raise SystemExit(1)
PY
```

If the user reports a visual placement issue, verify the affected URL in a real
browser or screenshot when feasible, especially for cards where captions can
push or overlap CTA buttons.
