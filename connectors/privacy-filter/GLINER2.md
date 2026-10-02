# GLiNER2-PII connector for desktop apps

Use the [separate installer download](https://mparanza.com/static/shared/vera-integrazioni/downloads/anonymization-connectors.zip)
and [SETUP.md](SETUP.md) for **Codex, Claude Cowork and Google Antigravity**.
Guided setup: `python3.12 install.py --setup` (Windows: `py -3.12 install.py --setup`).
The installer generates all three host formats; it does not edit host settings.
The command-line examples below also remain available.

An optional local MCP connector for Fastino's
[GLiNER2-PII model](https://huggingface.co/fastino/gliner2-privacy-filter-PII-multi).
Users choose this connector, [OpenAI Privacy Filter](README.md) or
[Rizzo PII](RIZZO.md), and may install more than one separately. None is part of
Vera's runtime. No API key is used.

## Install

Requirements: Python 3.12+, Internet access during setup, and disk space for
PyTorch, the model checkpoint and filtered output. CPU is the default, including
on Apple Silicon. CUDA can be selected in the generated server arguments when
supported by the user's hardware. This connector does not use Apple MPS.

Create the input folder, then run from this repository:

```sh
python3.12 connectors/privacy-filter/install.py --engine gliner2 \
  --input-dir "$HOME/Documents/GLiNER2/Input" \
  --output-dir "$HOME/Documents/GLiNER2/Output"
```

On Windows use `py -3.12` and Windows directory paths. The installer creates a
dedicated runtime at `~/.local/share/mparanza/gliner2-pii` on macOS/Linux or
`%LOCALAPPDATA%/Mparanza/gliner2-pii` on Windows. `--runtime-dir` overrides this
location. It installs only the selected engine's declared model dependencies;
GLiNER2 installation does not install the OpenAI model or `opf` library.

Add the single `[mcp_servers.gliner2_pii]` entry from that runtime's
`codex-mcp.toml` to your user `~/.codex/config.toml`, preserving other entries.
Restart the MCP connection in Codex desktop and call `gliner2_pii_status`.
The installer does not edit your Codex configuration. The server uses local
stdio and opens no HTTP listener.

The OpenAI and GLiNER2 installations have separate environments, models and tool
names. A runtime directory cannot be switched silently between engines.

## Use

Place the document inside the configured input folder and ask:

> Use GLiNER2-PII on `letter.docx` in its input folder and save the filtered copy.

| Tool | Input | Result |
| --- | --- | --- |
| `gliner2_pii_status` | None | Model readiness, engine, formats and limits |
| `gliner2_pii_file` | A path inside the configured input folder | Artifact ID, filtered file path, counts and checksum |
| `gliner2_pii_batch` | One to five paths | Results or fixed error codes, indexed in request order |
| `gliner2_pii_read` | Artifact ID; optional offset and limit | Up to 16,000 characters of filtered text |

The connector reads UTF-8 TXT/Markdown, DOCX and PDFs with an extractable text
layer. It saves a UTF-8 `.txt` copy with placeholders such as `[PERSON]`,
`[EMAIL]` and `[IBAN]`. It leaves originals unchanged and does not preserve
layout. Review the saved copy locally; request `gliner2_pii_read` when you want
the filtered text in the conversation.

DOCX extraction includes body text, tables, headers, footers, notes, comments
and tracked deleted text. Embedded files and text in images are not extracted.
Encrypted PDFs and PDFs with any page lacking extractable text are rejected.
Scans require separate OCR; this connector does not perform or install OCR.

Limits: 25 MiB and 500,000 extracted characters per file, 64 MiB expanded DOCX
content, five files per batch and ten minutes per file. The model scans long
text in overlapping 256-word chunks with a 64-word overlap. All 42 supported
PII labels are requested at threshold 0.5. Overlapping detections are masked as
one region; counts report unique detected spans per label, which may exceed
the number of placeholders. These fixed settings are recorded here so users
can understand the connector's behavior.

## What enters the model and Codex

The local GLiNER2 worker receives the extracted original text. It loads the
pinned weights, encoder configuration and tokenizer from the selected runtime.
Hugging Face and Transformers run offline during filtering, with Python
outbound socket connections blocked. This is an application-level boundary,
not an operating-system sandbox. Downloads happen only during explicit setup.

The worker validates model offsets against the original text and builds fixed
placeholders. Original text, detected values, upstream result dictionaries and
library diagnostics are not returned. Codex receives requested paths, artifact
paths, counts, checksums and engine/model metadata; filtered text enters the
conversation only when read. Use neutral filenames if filenames themselves
contain personal information. Do not attach the original as part of this flow.

Each artifact contains only `redacted.txt` and `receipt.json`, without a reverse
mapping to original values. Saved results remain available after restarting.

The model can miss information or remove useful text. Its model card describes
synthetic training data covering seven languages, including Italian. This is
not a promise that all Italian tax, company or other identifiers will be found.
Review the copy for the intended use. The choice of engine belongs to the user;
this integration does not rank the models.

## Versions and removal

- GLiNER2 library: `2.0.0`, declared in `requirements-gliner2.txt`.
- Model: `fastino/gliner2-privacy-filter-PII-multi`, revision
  `1cb4166094dc58fa8d836429f060d6c95f62b495`.
- Code and model retain their upstream Apache-2.0 licensing.

To disable, set `enabled = false` in this server's Codex entry. To uninstall,
remove that entry and its dedicated runtime directory. Filtered outputs stay
in the separate output directory selected by the user.

Developers can run the opt-in real-model test after preparing the assets:

```sh
GLINER2_TEST_MODEL=PATH python -m pytest \
  connectors/privacy-filter/tests/test_gliner_model_acceptance.py -v
```
