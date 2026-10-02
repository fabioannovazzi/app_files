# Rizzo PII connector for Codex desktop

An optional local MCP connector to the separately installed
[Rizzo PII app](https://github.com/Rizzo-AI-Academy/rizzo-pii). Users choose
[OpenAI Privacy Filter](README.md), [GLiNER2-PII](GLINER2.md), Rizzo PII, or more
than one. None is part of Vera's runtime, and this integration does not rank them.

## Install

1. Install Rizzo PII from its [official releases](https://github.com/Rizzo-AI-Academy/rizzo-pii/releases)
   or follow its source/Docker instructions. Start the app and wait for its model
   to load. Keep it running on the same computer as Codex. Its default local
   address is `http://127.0.0.1:5005`.
2. Install Python 3.12 or later and create the input folder below.
3. From this repository, install the connector:

```sh
python3.12 connectors/privacy-filter/install.py --engine rizzo \
  --input-dir "$HOME/Documents/Rizzo PII/Input" \
  --output-dir "$HOME/Documents/Rizzo PII/Output"
```

On Windows use `py -3.12` and Windows directory paths. The connector runtime is
`~/.local/share/mparanza/rizzo-pii` on macOS/Linux or
`%LOCALAPPDATA%/Mparanza/rizzo-pii` on Windows. `--runtime-dir` overrides it.
The installer creates only the lightweight connector environment. It does not
install, start, modify or redistribute the Rizzo app, its model or PyMuPDF.

Add the `[mcp_servers.rizzo_pii]` entry from that runtime's `codex-mcp.toml` to
your user `~/.codex/config.toml`, preserving existing entries. Restart the MCP
connection and call `rizzo_pii_status`. The installer does not edit your Codex
configuration. Status reports model readiness and the app/model versions
reported by Rizzo; these are not independently verified model hashes.

If your Rizzo app uses another port, add `--rizzo-port 5010` to the installation
command (substitute its actual port). The connector accepts only a port and
always connects to `127.0.0.1`. Remote servers and office LAN addresses are not
supported. With Docker, publish the port on `127.0.0.1` as shown upstream.

## Use

Put a document in the configured input folder and ask:

> Use Rizzo PII on `letter.docx` in its input folder and save the filtered copy.

| Tool | Input | Result |
| --- | --- | --- |
| `rizzo_pii_status` | None | Local app/model readiness, reported versions, formats and limits |
| `rizzo_pii_file` | Path inside the configured input folder | Artifact ID, filtered file path, counts and checksum |
| `rizzo_pii_batch` | One to five paths | Results or fixed errors in request order |
| `rizzo_pii_read` | Artifact ID; optional offset and limit | Up to 16,000 characters of filtered text |

The connector extracts UTF-8 TXT/Markdown, DOCX and PDFs with extractable text,
then passes the text to Rizzo. It saves a UTF-8 `.txt` copy and leaves originals
unchanged. It does not preserve layout, return PDFs or perform OCR. Encrypted
PDFs and PDFs with any page lacking extractable text are rejected. Embedded
files and text in images are not extracted. DOCX extraction includes body text,
tables, headers, footers, notes, comments and tracked deleted text.

Rizzo applies its own model and regex/checksum detectors. Each request specifies
`exclude_tags: []` and `include_mapping: false`: all supported categories are
requested, with the restoration dictionary disabled for that request. This does
not change the app's saved settings. Numbered placeholders can still identify
repeated values within a document; this connector does not restore original values.
Rizzo trims leading/trailing whitespace when processing the extracted text.

Limits are 25 MiB and 500,000 extracted characters per file, 64 MiB expanded DOCX
content, five files per batch and ten minutes per file. The connector bounds
each upstream response to 16 MiB. An unavailable app, incompatible response or
timeout produces a fixed error instead of returning raw diagnostic text.

## What reaches Rizzo and Codex

The extracted original text is sent over loopback HTTP to the Rizzo process on
the same computer. The connector does not contact a cloud API, follow HTTP
redirects or use environment-configured proxies. Rizzo's own installation,
model downloads and network behavior remain under the separately installed
app's control; the connector does not sandbox that process.

Only the returned filtered text and validated category counts are accepted.
Original-text fields, detected-value mappings, preview segments and upstream
diagnostics are discarded. If the response says mapping is enabled, contains a
nonempty mapping or excludes categories, processing fails without saving it.
Artifacts contain `redacted.txt` and `receipt.json`, without a restoration
dictionary. Receipts identify the engine and mark the model as managed by the
local Rizzo app; the connector does not pin or download its model.

Codex receives requested paths, artifact paths, counts, checksums and safe
version metadata. Filtered text enters the conversation only when requested
through `rizzo_pii_read`. Use neutral filenames and pass the local path rather
than attaching the original. Review the filtered copy: successful processing
does not prove that every sensitive value was detected.

## Tested interface and removal

The real-service acceptance test used app version `2.0.0`, model version `1.5.0`,
source commit `30d6f9c675e245bc8494df959adaeaa9d8de35c7`. It uses `GET /health`
and JSON `POST /analyze` with per-request mapping/tag overrides. Other versions
need the same response contract. Rizzo app upgrades are managed separately.
The test ran on macOS with CPU inference; Windows and CUDA were not tested.

Rizzo's source and distributed app have their own
[licensing terms](https://github.com/Rizzo-AI-Academy/rizzo-pii/blob/main/THIRD_PARTY_LICENSES.md).
This connector communicates with the user's installation over its HTTP API.

Disable or remove the `rizzo_pii` Codex entry to disconnect it. Removing the
connector runtime does not uninstall Rizzo or delete the selected output folder.

Developers can test a running local Rizzo app with synthetic documents:

```sh
RIZZO_TEST_PORT=5005 python -m pytest \
  connectors/privacy-filter/tests/test_rizzo_model_acceptance.py -v
```
