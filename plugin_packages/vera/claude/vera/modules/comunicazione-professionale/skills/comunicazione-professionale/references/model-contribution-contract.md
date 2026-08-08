> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Model contribution contract

Write UTF-8 JSON matching `schemas/model_contribution.schema.json`.

Use `recommendation: "publish"` only when the inspected evidence supports a
useful communication for the selected audience. Otherwise use
`recommendation: "no_publish"`, explain the reason, and leave `claims`,
`channel_drafts`, and `visual_story.slides` empty.

Every contribution includes `editorial_value`. Assess the audience-specific
reason now, concrete usefulness, distinct angle, repetition against selected
history, and whether silence is better. This is a model-led editorial judgment,
not a deterministic novelty score.

For `publish`:

- source assessments identify authority and limitations without treating a
  mechanically registered file as semantically sufficient;
- claims are atomic and preserve modality, dates, exceptions, uncertainty, and
  the commercialista's judgment boundary;
- every claim and every substantive visual slide references registered source
  IDs;
- the master brief contains only conclusions represented in the claim set;
- channel drafts adapt the same claim set to requested channels;
- the visual story contains two to eight slides and uses the content roles
  `cover`, `change`, `audience`, `timeline`, `action`, `caveat`, or `close`;
- `studio_profile_proposal` is present only when selected prior communications
  were read. It covers voice plus document, email, website, social, letterhead,
  numbering, heading, byline, footer, sign-off, CTA conventions, PDF font
  family, margins, logo geometry, contact-rail geometry, type sizes, leading,
  and rule weight. Do not reduce studio format to logo and colors.

The contribution must never contain credentials, session material, invented
client stories, engagement claims unsupported by supplied metrics, or an
instruction to send or publish automatically.
