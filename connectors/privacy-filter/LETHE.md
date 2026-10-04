# Lethe: one reviewed job across documents

Separate optional connector: [download the ZIP](https://mparanza.com/static/shared/vera-integrazioni/downloads/anonymization-connectors.zip).
Upstream: https://github.com/moonlight-lupin/lethe, pinned source
`736c3ea53f4f60aeb7024b6d4b8dae6f820e695b` (1.3.1).

Install with Python 3.12: `python install.py --engine lethe --input-dir INPUT --output-dir OUTPUT`.
Setup installs declared Lethe dependencies. Generated `codex-mcp.toml`,
`cowork-connector.zip` and `antigravity-mcp.json` connect the selected engine.

Before creating the session, prepare the entire job locally using the installed
connector Python (the `venv/bin/python` or `venv/Scripts/python.exe` in its runtime):

```sh
python -m mparanza_privacy_filter.lethe_review A.txt B.txt C.txt --output INPUT/review.json
```

Lethe detects across all supplied documents using its local entity dictionary,
patterns and suggestions. Review `review.json` **locally**, correct the selection
using Lethe's item fields, set `include` for approved items and `approved` to
`true`. Suggestions are initially excluded by Lethe. Do not put this file in
chat: it contains real names. All names needed in later documents must be in the
reviewed set; this connector does not add or merge new identities during a job.
You can manage dictionary names and aliases in the separately started Lethe UI.
NLP is optional upstream and is not installed by this connector; without it,
Lethe uses its own heuristic suggestions, which require local review.

1. Call `lethe_session_create(state_path="review.json")`.
2. Pass the returned `session_id` to `lethe_file(path="A.txt", session_id=...)`,
   then B and C, or to `lethe_batch` (1–5 paths).
3. Read filtered copies with `lethe_read` when requested. Keep tokens verbatim.
4. Save the AI's output as a local file in INPUT, then call
   `lethe_restore(session_id=..., path="answer.txt")`.
5. Open the restored path locally. It is never returned as text or exposed by
   the connector's read tool. `lethe_session_open` reopens the exact job after restart.

Lethe allocates its tokens once and provides the replacer/restorer. The connector
persists that upstream item state, checks integrity, serializes concurrent use
and enforces engine/session isolation. It does not invent, infer or repair
semantic mappings. Uncertain partial state is blocked instead of silently reused.

## What data reaches the model

Originals are extracted locally from TXT/Markdown, DOCX or text-readable PDF.
Lethe receives extracted text locally. Its reviewed identities and token mapping
are stored privately under the selected runtime's `model/sessions`; they are
not encrypted by this connector. POSIX permissions are 0700/0600; Windows relies
on the selected user's directory ACLs. The upstream encrypted desktop vault is
not used by this adapter. Back up or remove this sensitive state deliberately.

The host receives requested paths, random session/artifact IDs, aggregate counts
and checksums. Only requested filtered text is exposed through `lethe_read`.
Restoration returns a local path and checksum. Text in images is not extracted;
scans require prior OCR. Detection quality and token changes in AI output remain
limitations of the engine/workflow. No semantic mapping repair occurs in Vera.
