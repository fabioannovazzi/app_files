Taxonomy patches — 2-minute guide
=================================

You never edit JSON by hand. Use the two CLI helpers below:

1) List IDs you can patch
-------------------------

- All categories:
  `python tools/taxonomy_list_ids.py`

- One category:
  `python tools/taxonomy_list_ids.py lipstick`

This prints:
- Category id and label
- Attribute ids and labels
- Leaf node ids and labels

2) Apply a patch
----------------

Use `tools/taxonomy_apply_patch.py`. It validates and saves safely.

Option A — use names (easiest)

- Replace a weak synonym with a better one:

```
python tools/taxonomy_apply_patch.py \
  --category lipstick \
  --remove-syn-label "Finish:Semi-matte:no-shine" \
  --add-syn-label    "Finish:Semi-matte:soft matte"
```

Option B — use IDs (power users)

```
python tools/taxonomy_apply_patch.py \
  --category lipstick \
  --remove-syn finish:semi_matte:no-shine \
  --add-syn    finish:semi_matte:"soft matte"
```

Add a new leaf (JSON patch file)
--------------------------------

Create `patch.json`:

```
{
  "add_nodes": [
    {"attribute_id": "finish", "id": "soft_matte", "label": "Soft matte"}
  ],
  "add_synonyms": [
    {"attribute_id": "finish", "node_id": "soft_matte", "synonym": "soft matte"}
  ]
}
```

Apply it:

```
python tools/taxonomy_apply_patch.py --category lipstick --patch-file patch.json
```

Rules (what the tool enforces for you)
-------------------------------------
- Synonyms only on leaves (not parents) and must be unique across siblings.
- IDs are snake_case; labels/synonyms are normalized (case, hyphens/underscores, punctuation).
- Budgets are enforced (max synonyms/leaf, max nodes/attribute).
- Unknown/Other leaves are preserved.
- Atomic save: writes to a temp file, then replaces.

Tips
----
- Don’t remember IDs? Use the label form (`--add-syn-label`).
- Need IDs? Run `python tools/taxonomy_list_ids.py lipstick`.
- Nothing happens? The patch may be a no‑op or pruned by validation; check spelling/case.

Help
----
Use `--help` on both tools:

- `python tools/taxonomy_apply_patch.py --help`
- `python tools/taxonomy_list_ids.py --help`

