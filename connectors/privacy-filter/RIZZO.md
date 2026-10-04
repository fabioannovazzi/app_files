# Rizzo PII: native per-document pseudonymization

[Download the separate connector ZIP](https://mparanza.com/static/shared/vera-integrazioni/downloads/anonymization-connectors.zip).
[HTML explanation](https://mparanza.com/static/shared/vera-integrazioni/rizzo/index.html?lang=it).
The separately installed [Rizzo PII app](https://github.com/Rizzo-AI-Academy/rizzo-pii)
provides detection and its own numbered placeholder-to-original dictionary.
The connector preserves that dictionary locally; it does not allocate, infer,
merge or repair identities. It is optional and independent of Vera.

## Setup

Start Rizzo on the same computer and wait for its model to load. Default port:
5005. Configure the separate connector with Python 3.12:

```sh
python install.py --engine rizzo --input-dir INPUT --output-dir OUTPUT
```

Guided setup: `python install.py --setup`; on Windows use `py -3.12`.
The installer generates Codex, Cowork and Antigravity configuration files without
editing host settings. The runtime lives under `~/.local/share/mparanza/rizzo-pii`
on macOS/Linux or `%LOCALAPPDATA%/Mparanza/rizzo-pii` on Windows. It installs no
Rizzo app or model. Re-run setup when updating so the generated command includes
`--model-dir`, which selects private session storage in the runtime.
Existing manually configured commands without that option store state under
`OUTPUT/.rizzo-state/sessions`, rather than in the current working directory.

A different local app port can be selected with `--rizzo-port 5010`. The connector
always uses `127.0.0.1`; remote/LAN services, proxies and redirects are unsupported.
It requests `exclude_tags: []` and `include_mapping: true` per analysis without
changing saved app preferences.

## Filter and restore

1. Call `rizzo_pii_file(path="letter.docx")`. The response includes a filtered
   `artifact_id`, its local path, and a **document `session_id`**.
2. Read the filtered copy with `rizzo_pii_read(artifact_id=...)` when requested.
   Review detections locally; successful processing does not establish complete
   detection. Keep native placeholders such as `[FULLNAME_1]` unchanged.
3. Save the AI response as a local file under INPUT. Call
   `rizzo_pii_restore(session_id=..., path="answer.txt")` with that document's ID.
4. Open the restored output locally. The tool returns only a path and checksum;
   its restored file is not readable through `rizzo_pii_read`.
5. After restart, `rizzo_pii_session_open` reopens that exact document's mapping.
   Restoration also works with Rizzo closed because the native dictionary is local.

`rizzo_pii_batch` accepts 1–5 files and creates a **separate document session for
 each file**. An explicit session can process only one document. A second analysis
with the same ID is rejected without overwriting or invalidating the first mapping.
`rizzo_pii_session_create` can pre-create an empty document session if needed.

**Mapping is not cross-document identity consistency.** Rizzo's inspected
`analyze()` resets `counters`, `seen` and `mapping` on each call. The same
`[FULLNAME_1]` may therefore denote different people in separate files. Do not
combine answers using those different dictionaries. The connector does not merge
or renumber them. Lethe and PII-Shield provide separate multi-document workflows.

Restoration performs one exact dictionary-lookup pass over canonical bracketed
placeholders. It does not interpret changed, bare or guessed tokens. It cannot
match `[FULLNAME_1]` inside `[FULLNAME_10]`, and inserted original values are not
processed again. This uses the native dictionary and single-pass principle of
Rizzo's desktop `reverse()`; unlike the desktop UI it requires unchanged tokens.

## Formats, limits and verification

The connector extracts UTF-8 TXT/Markdown, DOCX and text-readable PDFs and saves
UTF-8 `.txt` copies. Originals remain unchanged; layout, OCR, embedded files and
text in images are outside this adapter. DOCX extraction covers body, tables,
headers, footers, notes, comments and tracked deleted text. Limits are 25 MiB,
500,000 extracted characters, 64 MiB expanded DOCX, five files per batch and ten
minutes per file. Native responses are bounded to 16 MiB.

The inspected interface is `GET /health` and JSON `POST /analyze` from source
`30d6f9c675e245bc8494df959adaeaa9d8de35c7`, app 2.0.0 and model 1.5.0. Rizzo's
app/model upgrades and licensing remain managed by the separately installed app.
Transport tests check dictionary privacy, persisted state, independent document
sessions and exact restoration. The opt-in real model tests are run with:

```sh
RIZZO_TEST_PORT=5005 python -m pytest connectors/privacy-filter/tests/test_rizzo_model_acceptance.py
```

These tests cover three documents with five reordered people, independent native
dictionaries, restart/restoration, four input formats and long text. Native
Windows/CUDA and live desktop-host acceptance require their own session tests.

## What data reaches the model

Extracted original text reaches the local Rizzo process and its model over
loopback HTTP. The connector does not contact a cloud API or sandbox Rizzo's
separately managed process. Rizzo returns its native dictionary to the isolated
connector worker, which stores it under `model/sessions/<random-id>/rizzo.json`.
That dictionary contains original identities. It is not encrypted; POSIX folders
and files use 0700/0600 permissions, while Windows relies on user-directory ACLs.
It remains until deliberately removed; Rizzo's web UI dictionary is separate.

Original text, mapping values, previews and diagnostics are excluded from worker
stdout, MCP responses and filtered artifacts. The host receives requested paths,
random session/artifact IDs, category counts, checksums and validated version
metadata. Requested filtered text enters the conversation through `rizzo_pii_read`.
Restoration substitutes native tokens locally, saves a private file and returns
its path and checksum without its text or a readable artifact ID.
