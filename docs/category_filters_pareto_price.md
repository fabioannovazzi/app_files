## Category filters for Pareto and price bands

This doc defines the fields and logic to add Pareto (sales contribution) and price-band filters to the category view. No code here—just the contract and expectations.

### Per-product fields
- `sales_share`: float 0–1 share of category sales/GMV.
- `cumulative_sales_share`: float 0–1 cumulative share when products are sorted by sales desc.
- `pareto_rank`: int, 1-based rank by sales (tie-break: `parent_product_id` ascending).
- `pareto_bucket`: string `A`/`B`/`C` using cutpoints:
  - `A`: cumulative ≤ 0.80
  - `B`: cumulative ≤ 0.95
  - `C`: cumulative > 0.95
- `price_band`: string `premium`/`mid`/`value` using category price percentiles:
  - `premium`: >85th percentile
  - `mid`: 35th–85th percentile (inclusive)
  - `value`: <35th percentile
  - Adjust thresholds if needed, but keep them consistent across categories.

### Category-level metadata
- `pareto_shares`: `{ "A": <float 0–1>, "B": <float>, "C": <float> }`
- `price_band_shares`: `{ "premium": <float>, "mid": <float>, "value": <float> }`
- `as_of`: ISO timestamp of the sales/price snapshot used to compute the fields.

### Filter logic (client)
- Sales filter options: `all`, `A`, `B`, `C`; filter by `pareto_bucket` when set.
- Price filter options: `all`, `premium`, `mid`, `value`; filter by `price_band` when set.
- Combine with AND: product must satisfy both filters unless set to `all`.
- Show applied filters as pills and surface counts/sales share (e.g., “Pareto A · Premium · 48 products · 80% of sales”).
- Disable with tooltip if required fields are missing; default to `all`.

### Computation notes (server/batch)
- Sort products by sales/GMV desc; compute `sales_share`, `cumulative_sales_share`, and assign `pareto_bucket` using the tie-break rule above.
- Compute category price percentiles and assign `price_band`.
- Persist these fields alongside the category payload so the UI filters are instant (no per-interaction recompute).

