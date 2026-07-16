## PDP Review API (alpha)

This service exposes the PDP attribute review data without UI so you can
experiment with a standalone UI or call the data directly. The legacy UI is
deprecated/optional during the migration to FastAPI.

### 1. Run the service

```bash
uvicorn src.fastapi_app_entry:app --reload
```

* The server binds to `http://127.0.0.1:8000` by default. Use `--host` /
  `--port` to change these values as needed.
* The API reads the shared PDP store. With `PDP_DATABASE_URL` configured, this
  is Postgres by default.
* Endpoints rely on normal authentication and per-page permissions. No separate
  token is required.

### 2. Key endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/review/retailers` | List retailers and brands currently in the cache. |
| `GET` | `/review/categories` | Categories for the requested retailer/brand scope. |
| `GET` | `/review/filters` | Attribute metadata (values, active status) for the selected categories. |
| `GET` | `/review/records` | Parent or variant rows filtered by categories, brands, and attribute selections. |
| `GET` | `/review/debug` | Raw deterministic, LLM, or merged attribute rows for chosen products. |
| `POST` | `/review/brief/jobs` | Submit a Markdown brief job (share-based charts + LLM interpretation) for NotebookLM (async; preferred). |
| `GET` | `/review/brief/jobs/{job_id}` | Poll brief job status and fetch the Markdown when ready. |
| `POST` | `/review/brief/generate` | Legacy endpoint: now submits a brief job and returns immediately (prevents 504 timeouts). |

All endpoints accept the optional `retailer`, `brand`, and `category` query parameters.
The `/review/records` endpoint accepts attribute filters via repeated `filters`
arguments in the format `ATTRIBUTE_ID:value|value2`.

Example:

```
GET /review/records?retailer=kiko&category=bronzer&record_type=parent&filters=form:liquid%20fluid
```

 

### 3. OpenAPI schema

Visit `http://127.0.0.1:8000/docs` to explore the automatically generated
interactive API documentation.

### 5. Minimal HTML prototype

The same FastAPI app now serves the React view at `http://127.0.0.1:8000/review/page`.
Use the buttons to load retailers, categories, parent records, and the
deterministic/LLM/merged stage tables. This page is a lightweight stand-in
while we migrate off UI (deprecated/optional).

The former sales chart explorer has been removed. Chart rendering for plugins
belongs in the plugin legacy charting paths rather than this review app.

The NotebookLM brief view is available at `http://127.0.0.1:8000/review/brief`.

### 4. Next steps

* Use these endpoints from a new React/Svelte front-end.
* Replace the UI tab (deprecated) with a link to the standalone UI once
  comfortable.

## Journal Sampling

The legacy Sample Entries FastAPI workflow has been retired. Journal sampling
now lives in the Journal Sampling Codex plugin. Codex performs the adaptive
inspection and mapping work, while plugin scripts produce deterministic
normalized rows, samples, diagnostics, and audit trails.
