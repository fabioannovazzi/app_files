Sales FastAPI Smoke Tests
=========================

Quick checks to verify the new `/sales` headless flow. Run from the repo root with an active venv and the API started on port 8000.

Upload & prepare
----------------
```bash
curl -s -X POST http://localhost:8000/sales/upload \
  -F "file=@tests/fixtures/pdp/sample_sales.csv" \
  | jq
```
Note the `session_id`, then:
```bash
curl -s -X POST http://localhost:8000/sales/session/<SESSION_ID>/prepare | jq
```

Variance
--------
```bash
curl -s -X POST http://localhost:8000/sales/session/<SESSION_ID>/variance/run \
  -H "Content-Type: application/json" \
  -d '{"index_columns":["product"],"value_columns":["amount"],"period_column":"period","period_from":"2023","period_to":"2024","mode":"basic"}' \
  | jq
```

Plan
----
```bash
curl -s -X POST http://localhost:8000/sales/session/<SESSION_ID>/plan/run \
  -H "Content-Type: application/json" \
  -d '{"amount_column":"amount","units_column":"units","period_column":"period","index_columns":["product"],"price_change_pct":5}' \
  | jq
```

UI sanity
---------
- Visit `http://localhost:8000/sales/page` and confirm:
  - “Load data” disabled until a file is chosen; actions remain disabled until upload succeeds.
  - Status bar surfaces backend messages after prepare/variance/plan.
  - Buttons show a brief disabled/loading state during long calls.
