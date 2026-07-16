# Product Hypothesis Sites

Static product hypothesis websites live under `concept_sites/{doc_id}/` and are
served at `/review/product-hypotheses/site/{doc_id}/`.

## Board Image Rule

Do not make an `Open board image` button point directly to an image asset such
as `assets/*_board.png`. These direct PNG URLs have proven brittle in the
deployed review site.

Also do not make the button point to a `data:image/...` URL. Browsers can block
or ignore top-level navigation to `data:` URLs from a normal page.

Use this pattern instead:

1. Keep the visible board image on the page as an embedded `data:image/...`
   source when the image path has broken before or came from a generated zip.
2. Create a small local HTML wrapper page next to the hypothesis page, named
   from the board asset, for example
   `example_product_board_image.html`.
3. Put the board image in that wrapper page as an embedded `data:image/...`
   source.
4. Point the `Open board image` button to the wrapper HTML page:

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

This keeps the page image reliable and keeps the button as normal HTTP
navigation through the concept-site HTML route.

## Verification

Before shipping a hypothesis site, check every `Open board image` link:

- The `href` must end in `.html`, not `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`,
  or a `data:` URL.
- The target HTML file must exist under the same `concept_sites/{doc_id}/`
  directory.
- The target HTML file must contain an embedded `src="data:image/..."`
  board image.
- The button should include `target="_blank"` and `rel="noopener"`.
