# Privacy Filter connector for Codex desktop

An optional local MCP server using [OpenAI Privacy Filter](https://github.com/openai/privacy-filter).
It is installed separately from Vera. Vera, Clara and Lucia do not import it,
start it or install its model. No OpenAI API key is used.

[GLiNER2-PII](GLINER2.md) is also available as a separate optional local
connector. Choose the engine you want to install; each has its own runtime,
model and MCP tool names. The connectors share file-handling code, without
installing the other engine's model dependencies.

## Install

Requirements: Python 3.12+, Internet access during installation, and disk space
for PyTorch, the approximately 2.8 GB checkpoint and filtered output. CPU is the
default, including on Apple Silicon. CUDA can be selected in the generated
server arguments if your PyTorch installation and hardware support it. This
version does not use Apple MPS.

From this repository, run:

```sh
python3.12 connectors/privacy-filter/install.py \
  --input-dir "$HOME/Documents/Privacy Filter/Input" \
  --output-dir "$HOME/Documents/Privacy Filter/Output"
```

Create the input folder first. On Windows, use `py -3.12` and your Windows
directory paths. The installer creates a dedicated user runtime under
`~/.local/share/mparanza/privacy-filter` on macOS/Linux or
`%LOCALAPPDATA%/Mparanza/privacy-filter` on Windows. `--runtime-dir` overrides
that location. It installs declared dependencies, downloads the pinned official
model and caches its tokenizer. Installation is explicit; tool calls never
install packages or download missing assets.

The installer writes `codex-mcp.toml` in that runtime directory. Add that single
`[mcp_servers.privacy_filter]` entry to your user `~/.codex/config.toml`, preserving
your other settings. Restart the MCP connection in Codex desktop, then call
`privacy_filter_status`. The generated entry uses stdio; it starts no HTTP server.
See [OpenAI's MCP configuration documentation](https://learn.chatgpt.com/docs/extend/mcp).

The generated configuration uses a long tool timeout for CPU inference. A batch
has at most five files, processed sequentially, with a ten-minute processing
limit per file. Existing filtered results remain available after a restart.

## Use

Place originals inside the selected input directory. Ask Codex, for example:

> Use Privacy Filter on `letter.docx` in its input folder. Save the filtered copy.

The tool returns an artifact identifier, the filtered file path and counts.
Open the local `.txt` copy for review. Ask Codex to read that artifact when you
want its filtered text in the conversation. Do not attach the original to chat
as part of this workflow.

| Tool | Input | Result |
| --- | --- | --- |
| `privacy_filter_status` | None | Model readiness, formats and limits |
| `privacy_filter_file` | One relative or absolute path inside the configured input directory | New `.txt` artifact, ID, counts and checksum |
| `privacy_filter_batch` | One to five explicit paths | Per-file results or fixed error codes, indexed in request order |
| `privacy_filter_read` | Artifact ID, optional character offset and limit | Filtered text only, at most 16,000 characters per response |

Originals are not modified. Output is UTF-8 plain text, with placeholders such
as `[PRIVATE_PERSON]` and `[PRIVATE_EMAIL]`. Layout, styles and page geometry are
not preserved. Output filenames use random IDs rather than source filenames.

Supported inputs:

- UTF-8 TXT and Markdown, including a UTF-8 BOM.
- DOCX text, including paragraphs, tables, text boxes, headers, footers, notes,
  comments and deleted text in tracked changes. Embedded files and text in
  images are not extracted.
- PDFs with an extractable text layer. Encrypted PDFs and PDFs containing a
  page with no extractable text are rejected. Image content within otherwise
  readable pages is not OCRed. Run OCR separately when needed; this connector
  does not install OCR software.

Inputs are limited to 25 MiB and 500,000 extracted characters per file. DOCX
uncompressed content is limited to 64 MiB. An empty input, extraction error,
tokenizer mismatch or inference error produces no successful artifact. Batch
errors do not discard the successfully filtered files.

## Data boundary

Only the processing worker reads the original contents. The model runs in that
local subprocess. The server never serializes OpenAI's `RedactionResult`, its
original `text`, `detected_spans`, span values, warnings or exceptions. It applies
validated model spans with fixed placeholders and returns an allowlist of
filtered text and aggregate counts. Worker stderr is discarded; stdout contains
only the restricted response. Error messages use fixed codes.

At inference time the model path is explicit, Hugging Face is offline, and the
worker blocks Python outbound socket connections, including tokenizer download
attempts. This is an application-level boundary, not an operating-system sandbox.
Model and dependency downloads happen only in the separately invoked installer.

Tool arguments (including paths), artifact paths, summaries and any filtered
text requested with `privacy_filter_read` enter Codex's tool context. Source
filenames can themselves contain personal information, so neutral filenames are
useful. No reversible mapping of placeholders to detected values is persisted.
Each artifact directory contains only `redacted.txt` and `receipt.json`.

Detection can miss sensitive information and can remove useful information.
OpenAI describes the model as primarily English, with possible lower accuracy
in other languages and domains. Review the local copy for your intended use.
Completing a run does not establish anonymity or regulatory compliance.

## Reproducibility and development

Upstream code is pinned in `requirements-model.txt`. Model weights are pinned
to Hugging Face revision `7ffa9a043d54d1be65afb281eddf0ffbe629385b`.
The original OpenAI software and model retain their Apache 2.0 license.

In an isolated development environment:

```sh
python -m pip install -r connectors/privacy-filter/requirements-dev.txt -e connectors/privacy-filter
python -m pytest connectors/privacy-filter/tests/test_connector.py \
  --cov=mparanza_privacy_filter --cov-report=term-missing --cov-fail-under=80
```

The unit and stdio tests use synthetic inputs and do not download model weights.
The opt-in model acceptance test additionally needs `requirements-model.txt` and
a model prepared by `python -m mparanza_privacy_filter.prepare --model-dir PATH`:

```sh
PRIVACY_FILTER_TEST_MODEL=PATH python -m pytest \
  connectors/privacy-filter/tests/test_model_acceptance.py -v
```

To disable the connector, set `enabled = false` in its Codex server entry. To
uninstall it, remove that entry and the dedicated runtime directory. Filtered
outputs live in the user-selected output directory and can be retained separately.
