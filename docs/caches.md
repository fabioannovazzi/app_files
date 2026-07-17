Centralized caches

This project stores persistent caches under a single root directory. The root is chosen in this order:

1) <repo>/caches (if the repository root is discoverable)
2) <cwd>/caches (fallback when a repo root cannot be found)

Helpers
- `modules.utilities.cache.get_cache_root()` returns the selected root and ensures it exists.
- `modules.utilities.cache.get_cache_dir(*parts)` builds directories under the root.
- `modules.utilities.cache.get_cache_path(name)` returns a file path under the root for single files.

Key files and subdirectories
- `category_websites.json`: per-category website lookups.
- `merchant_brand_websites.json`: website lookups for merchant/brand names.
- `alias_index.json`: alias → canonical leaf mapping for attribute taxonomy.
- `description_cache.json`: normalized transaction descriptions cache.
- `attribute_classifications/attribute_classifications.parquet`: persisted attribute classification progress.
- `product_attribute_cache/product_attributes.json`: product attribute cache.
- `llm/record.json`: serialized LLM calls for write/replay modes.

Overrides and environment variables
- Cache locations are fixed; environment variables do not move cache files.

Cleaning
- Prefer the script at the repo root: `python3 delete_caches.py` (removes known caches safely).

Notes
- LLM records are standardized to `llm/record.json` across the codebase.
- Modules never create a directory with a file name (e.g., no `alias_index.json/` folders); file paths are constructed with `get_cache_path()`.
