# Preservation-aware revision workflow

Revision mode applies only to a Clara HTML stage deck or its editable work
folder. It is not a generic arbitrary-web-page patcher.

## Inspect and map

```bash
python skills/html-deck/scripts/inspect_html_deck.py \
  <baseline-work-folder-or-index.html> \
  --report <output>/baseline-inventory.json
```

Create a revision map using schema `clara.html_deck_revision_map.v1`. Bind it
to `deck.normalized_dom_fingerprint` from the inventory. Classify every
baseline slide exactly once as untouched, protected, targeted, removed, or
renamed. Every edit target needs a reason.

```json
{
  "schema_version": "clara.html_deck_revision_map.v1",
  "baseline_fingerprint": "<64-lowercase-hex>",
  "global_edits": ["custom-css"],
  "edit_targets": [
    {
      "slide_id": "decision",
      "scope": "components",
      "component_ids": ["recommendation"],
      "reason": "Apply the approved recommendation wording."
    }
  ],
  "untouched_slides": ["opening", "evidence"],
  "protected_slides": [],
  "protected_components": [
    {
      "slide_id": "decision",
      "component_id": "brand-mark",
      "reason": "Approved identity."
    }
  ],
  "slide_changes": {
    "add": [],
    "remove": [],
    "rename": [],
    "after_order": ["opening", "evidence", "decision"]
  }
}
```

Global edit scopes are source-kind specific: `metadata`, `custom-css`,
`content-ledger`, `deck-plan`, `styles`, `runtime`, and `shell`. Declare only
the resources the request actually changes. Slide-local ledger entries are
checked independently, so changing provenance for an untouched slide fails.

Mark inline protected elements with a stable `id` or `data-component-id` plus
`data-revision-protected="true"`. Optionally add
`data-revision-protection-reason`.

Validate the map before editing:

```bash
python skills/html-deck/scripts/validate_revision_map.py \
  <baseline> <revision-map.json> \
  --report <output>/revision-map-validation.json
```

## Edit and compare

Copy the baseline work folder or standalone file to a separate revision path.
Edit only declared targets. Keep stable slide/component IDs unless the map
declares a rename.

```bash
python skills/html-deck/scripts/compare_html_deck_revision.py \
  <baseline> <revised> \
  --revision-map <revision-map.json> \
  --report <output>/revision-comparison.json
```

The comparison fails for undeclared global changes, changed untouched or
protected slides, edits outside component targets, moved/changed protected
components, unplanned order/ID changes, cross-slide provenance changes, and
declared targets that did not actually change. After it passes, rebuild,
validate, and run browser QA on the revised artifact.
