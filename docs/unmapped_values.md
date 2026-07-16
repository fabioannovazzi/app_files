Unmapped values: manual review

Overview
- Classification normalizes low‑confidence or unknown outputs:
  - "no idea", "unknown", "n/a", etc. → `N/A`
  - Values outside the allowed list are stored as `not in taxonomy`.
- These observations are queued for follow‑up:
  - A review item is appended to `taxonomy_review_queue.json` with category, attribute, value and product

Follow‑up actions
- Review queue (manual approval): open the Taxonomy page and use "Pending Attribute Values" to approve valid new values. Approved items are validated and added as new leaves in the taxonomy.

Where files live
- `taxonomy_review_queue.json` (repo root)

Notes
- Promotions and novelty tracking have been removed from the application. Use manual taxonomy updates as needed.
