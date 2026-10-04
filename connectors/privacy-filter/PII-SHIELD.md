# PII-Shield: extend the anonymizer's own session

Separate optional connector: [download the ZIP](https://mparanza.com/static/shared/vera-integrazioni/downloads/anonymization-connectors.zip).
This adapter uses **gregmos/PII-Shield Node.js CLI 2.2.0**, not the similarly
named log sanitizer or the older Python fork.
Source: https://github.com/gregmos/PII-Shield/tree/e2e0fed96c93bcbb87857ee600c379556fb36c27/nodejs-v2.

Install Node.js 22+ and Python 3.12. Supply the absolute Node executable and
`npm-cli.js` paths (on Windows use `node.exe` and the npm installation's
`node_modules/npm/bin/npm-cli.js`):

```sh
python install.py --engine pii-shield --input-dir INPUT --output-dir OUTPUT \
  --node /absolute/path/to/node --npm /absolute/path/to/npm-cli.js
```

Setup installs `pii-shield@2.2.0` into the selected user runtime, downloads its
GLiNER model and explicitly warms its pinned NER dependencies using synthetic
text. It writes readiness only after NER loads. This is a separate Node engine,
not an additional Python classifier. Re-run explicit setup if prepared assets
are damaged. Processing checks hashes before invoking the engine, never requests
model downloads and rejects upstream patterns-only fallback.

1. Call `pii_shield_session_create()` and retain its random connector session ID.
2. Call `pii_shield_file(path="A.txt", session_id=...)`, then B and C with the
   **same ID**, or use `pii_shield_batch` for up to five paths.
3. PII-Shield creates its native session on the first document. Each subsequent
   invocation uses its native `--session` option. Its own mapping pool determines
   entity identity, aliases and pseudonyms; the connector does not modify it.
4. Read selected filtered text with `pii_shield_read`.
5. Save AI output locally under INPUT, then call
   `pii_shield_restore(session_id=..., path="answer.txt")`. Open the returned
   restored path locally. Do not read the restored document into the model.
6. `pii_shield_session_open` validates/reopens the exact job after restart.

The connector extracts TXT/Markdown, DOCX and PDFs with readable text into a
neutral temporary TXT input. Layout and upstream DOCX editing tools are outside
this adapter. It uses `--no-review`; review the filtered copy locally. Its output
is bounded by the existing 25 MiB / 500,000-character extraction limits.

## What data reaches the model

Extracted originals reach the local PII-Shield CLI and local GLiNER model.
Native mappings live in a dedicated directory for each connector session;
models/dependencies live in the runtime's `model/upstream`. Mapping/review files
may contain raw identities and document text. They stay local and are treated
as opaque. POSIX permissions are restricted; Windows relies on directory ACLs.
They are not encrypted by this connector. Upstream TTL defaults to seven days;
expired/missing/corrupt state cannot be reconstructed by the connector.

MCP returns random connector IDs, paths, counts and checksums, and requested
filtered text. Raw upstream diagnostics, mappings and review records are never
forwarded. Restoration uses the native session and returns only a saved path
and checksum; the connector read tool cannot expose restored files. Successful
transport does not certify semantic mapping quality or complete detection.

### Platform acceptance boundary

On the tested macOS arm64 host, both Node.js 22 and 24 completed inference but
PII-Shield's pinned ONNX Runtime 1.22.0 aborted during CLI teardown. This matches
[upstream ONNX issue #24579](https://github.com/microsoft/onnxruntime/issues/24579).
The adapter rejects a nonzero process exit, writes no successful readiness
receipt, and does not repair or replace the engine. macOS native acceptance is
therefore **not established**. A dedicated Linux CI job performs the actual
three-document, five-person, same-session restoration test. Unit tests and
host configuration files do not establish Windows or desktop-host acceptance.
