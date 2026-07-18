# Preserved legacy reference data

These files are tracked so that working reference data cannot disappear during a
clean clone or deployment. They are not loaded by the current application and
must not be mistaken for the active taxonomy or a reviewed website catalog.

- `taxonomy_snapshots/pre_wipe_2025-08-21/` preserves the 8-category,
  36-attribute taxonomy from immediately before the repository-wide delete.
  Source SHA-256: `c3f1584fdd3a962d97e0dc488206011fb7eff5c5215e6351be4228635ba3ad2a`.
- `taxonomy_snapshots/production_backup_2025-10-06/` preserves the unique
  production backup with 7 categories and 56 attributes. Source SHA-256:
  `9242a4da14876e57fff555c60d7c3ec0621790a9ab3250da8a8ff17fa28252e6`.
- `taxonomy_snapshots/pre_split_2026-04-03/` preserves the final taxonomy
  before the split-file migration, with 6 categories and 69 attributes. Source
  SHA-256: `9502024648cde2da87c67e9489396604977eb8b27accbb4fb22c07e69558d455`.
- `taxonomy_snapshots/expanded_candidate_2025-09-07/` preserves the deleted
  `attribute_taxonomy_new.json` candidate with 7 categories and 80 attributes.
  Source SHA-256:
  `489920b5a3d514237771be12fb4178a1e460474474037b6752c6ba8d4dcacb5e`.
- `taxonomy_snapshots/attribute_taxonomy_old_2025-10-29/` preserves the final
  deleted `attribute_taxonomy_old.json` variant with 7 categories and 56
  attributes. Source SHA-256:
  `d5bf895efb3a7d3345e0299eb2dd74a46d3b5635610d6685ba6b2649424d60e9`.
- `taxonomy_snapshots/taxonomy_tmp_2026-04-17/` preserves the final deleted
  split staging tree with 22 categories and 239 attributes. Each archived
  category file is byte-identical to its historical source.

Every taxonomy snapshot follows the same rule as the active taxonomy: one JSON
file per category plus a small manifest. No all-category taxonomy file is
tracked in these recovery archives.
- `taxonomy_review_queue_2025-09-04/` preserves the deleted 20-row foundation
  taxonomy review queue as one category file plus a manifest. Source SHA-256:
  `0e6e685b5ac879fae601d3455aae9307040c58ef364c080a2d869191c9b859d3`.
- `category_websites_legacy_2025-08-11.json` preserves three deleted lip-oil
  PDP source URLs. Its adjacent manifest records the source blob, commit, and
  SHA-256.
- `product_line_catalog.json` preserves the deleted catalog of 214 lipstick and
  foundation product-line names. Its canonical JSON content matches source
  SHA-256 `755d37760d447add33ba6ce87bf24aacaf41deeae604e1b8f8a88f90cde9348c`.
- `merchant_brand_websites_legacy_2026-05-10.json` preserves the separate
  87-entry legacy runtime cache. It includes 85 names absent from the production
  snapshot and is retained for review, not activated automatically. Its
  source SHA-256 is
  `bb63f0a08cb892ba0c455a9d8de858d985f07c54b90a27c4254ef3b975e62ab0`;
  its canonical JSON content matches SHA-256
  `0faae8150944cfd02d6f5da54c8d29b3c4ec1430a15a86f816e9bd5dfd6a6017`.
- `merchant_brand_websites_meta_production_2026-02-14.json` and
  `merchant_brand_websites_meta_legacy_2026-05-10.json` preserve the associated
  failed-lookup timestamps for provenance. They are expired retry state and are
  not activated.

The active split taxonomy remains under `config/attribute_taxonomy/`. The
tracked website seed at `config/merchant_brand_websites.json` is sourced from
the active 740-entry production cache (source SHA-256
`a30ffd160adb1a3e45e6e037121a0c73ea0ac5242e92d2f85f8b309b109e3ef7`);
the ignored writable cache overlays it at runtime. The legacy snapshot contains
29 additional resolved names and one conflicting candidate for `tom ford`; it
is preserved for review rather than silently changing production lookups.

The tracked category website seed at `config/category_websites.json` preserves
the production-only 5-category, 15-URL cache (source SHA-256
`34519bef629a9b6be475daf7935ce5596e85abc4813c8665efbd449168d8c816`).
