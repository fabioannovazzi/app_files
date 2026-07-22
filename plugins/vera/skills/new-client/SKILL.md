---
name: new-client
description: "Use whenever a studio starts work on a new client: prepare incoming files, identify missing evidence, then build the owner-only, source-bound professional setup covering identity, engagement, privacy, AI, AML, document planning, and monitoring."
---

# New Client

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

This is Vera's sole new-client workflow. Do not route users to separate
document-preparation or professional-setup workflows.

Resolve the workflow root as `../../modules/new-client` when installed or
`../../../new-client` in repository source. Resolve its subordinate file
preparation engine as `../../modules/client-file-preparation` when installed or
`../../../client-file-preparation` in repository source.

Read that module's `skills/new-client/SKILL.md` completely. When incoming
documents need preparation, also read the engine's
`skills/client-file-preparation/SKILL.md` completely and execute that as phase
one. Both MCP toolsets belong to this workflow:

- `validate_client_file_preparation_review`,
  `render_client_file_preparation_review`,
  `save_client_file_preparation_decisions`, and
  `apply_client_file_preparation_decisions` review phase one;
- `validate_new_client_review`, `render_new_client_review`,
  `save_new_client_decisions`, and `apply_new_client_decisions` review the
  professional-setup phases.

Treat the relevant resolved module root as the plugin working directory for each
command. Present every phase and artifact to the user under **New Client**.

Phase one accepts `italy`, `geneva`, `zurich`, `uk`, or `mixed`; its review,
memo, client request, inventory, extraction report, and fiscal summary follow
`it`, `en`, `fr`, or `de`. Low-level machine records retain stable field and
status codes. The current professional setup country pack is Italy only.
Promote a reviewed phase-one run with the
resolved `new-client` module's
`scripts/promote_client_file_preparation.py`; the command verifies the sealed
manifest and every listed output, inherits the phase-one language, and must
reject non-Italian or mixed runs rather than implying another country pack.

Real client data may enter the Codex context when useful for the professional
work. Do not add a per-case model-use authority or minimisation declaration
that Vera cannot verify. Keep credentials, cookies, tokens, session URLs, and
raw local paths outside the review payload.

When host MCP tools are unavailable, use each resolved module's persistent
loopback workbench instead of treating chat text as saved decisions. From an
installed/package module root, run:

```bash
python scripts/review_server.py <phase-output-directory>
```

From either component root in repository source, run:

```bash
python ../../scripts/serve_review_workbench.py <phase-output-directory> --plugin-dir .
```

The packaged workbench invokes the same validate/render/save/apply contract.
If it cannot run, the review may continue in Markdown for inspection only;
leave its JSON decisions pending and say they were not applied.
