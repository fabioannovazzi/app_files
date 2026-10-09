---
name: new-client
description: "Use when a studio starts work on a new client: prepare files, identify missing evidence, and build a source-bound setup covering identity, engagement, privacy, AML, and monitoring."
---

<!-- VERA_CONNECTED_KNOWLEDGE_BEGIN -->
## Connected studio knowledge

When the user or an adopted studio instruction requests relevant repository
evidence, read `../vera/references/connected-studio-knowledge.md` before the
dependent work, including direct specialist invocation. Use only callable host
search/read tools; preserve citations and this workflow's qualification gates.
Without a repository, continue ordinary work. Studio skills remain independently
invoked by the user; Vera does not dispatch them.
<!-- VERA_CONNECTED_KNOWLEDGE_END -->

<!-- VERA_OPENAI_ONBOARDING_BEGIN -->
Onboarding is optional. Continue ordinary professional work immediately,
including direct specialist invocation, without checking or completing a local
onboarding profile. Missing, unfinished, inaccessible or corrupt onboarding state,
or unavailable voice/window controls, must never block ordinary work. Do not
automatically start, resume or repeatedly offer onboarding.
Only for a user-requested tutorial or a native teaching handoff, read
`../vera/references/local-onboarding.md`. A verified paired lesson worker
executes only its bound lesson and token; never bypass tutorial validation.
Tutorial profiles, progress, examples and feedback remain local; never send a
change request, stamp a tutorial receipt or call hosted interviews for a tutorial.
Current user requests take precedence over saved preferences.
<!-- VERA_OPENAI_ONBOARDING_END -->

# New Client

For a Geneva (CH-GE) mandate, read `../vera/references/localization/geneva.md` first and use this existing function’s Geneva adaptation in its resolved component skill. Language alone never selects jurisdiction.


After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

For substantive AML investigation or a later AML reassessment, use
`vera:aml-review` with the same client's selected evidence and reviewed setup;
do not repeat the whole onboarding intake.

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

For either prepared phase-one or professional-setup run in Codex, when native workspace tools
and its exact trusted run binding are available, read
`../vera/references/native-workspace.md` and open “Lavori dello studio”. Applying
review preserves all dossier gates and never activates the relationship;
material fact edits or an expired package require specialist regeneration.
For phase one, the panel's ordinary explanations read the exact selected evidence
from the hash-verified model handoff; complete memo/email drafts enter discussion
only when explicitly selected. Apply uses the existing transactional regeneration
and sealing route. Neither phase has installed native-host acceptance merely
because its source regression passes. Without native tools or a trusted binding,
including Cowork, retain the persistent component route.

Phase one accepts `italy`, `geneva`, `zurich`, `uk`, or `mixed`; its review,
memo, client request, inventory, extraction report, and fiscal summary follow
`it`, `en`, `fr`, `de`, or `es`. Low-level machine records retain stable field and
status codes. The current professional setup country pack is Italy only.
Promote a reviewed phase-one run with the
resolved `new-client` module's
`scripts/promote_client_file_preparation.py`; the command verifies the sealed
manifest and every listed output, inherits the phase-one language, and must
reject non-Italian or mixed runs rather than implying another country pack.

Real client data may enter the current model context when useful for the professional
work. Do not add a per-case model-use authority or minimisation declaration
that Vera cannot verify. Keep credentials, cookies, tokens, session URLs, and
raw local paths outside the review payload.

For phase one, when `model_handoff.json` exists, both Codex and Cowork use it
and every declared page as their default context. Use only the item kinds
listed for the current phase. Keep `review_payload.json` as the local MCP/UI
contract; do not use its broader draft previews as ordinary synthesis context.
Exact local identifiers remain available in professional artifacts and may be
loaded when the work requires them. The generic `CLIENT-001` reference applies
only to phase-one email drafting; it is not blanket anonymization.

For an explicit CH-GE mandate, an owned running `client-file-preparation` run
can also prepare an already reviewed invoice source group in the native panel.
Select its registered canonical JSON and map every declared original explicitly
to a registered document. Preserve the JSON, extraction review and original
bytes. Recoverable mapping drafts never restore confirmation; supply actual
grouping attribution and confirm the complete mapping. The public reader rejects
invalid extraction review before official output writes. Completed retries replay
the exact group; uncertain intent and retained files require specialist inspection.
This action groups existing reviewed evidence; it does not perform extraction,
manufacture professional review or activate the client relationship. Declare and
seal each group file through the separate Archive closure before explicitly
selecting its canonical JSON and originals as upstream audit inputs. Only an
explicit selected-source discussion returns a bounded excerpt to the model.

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
