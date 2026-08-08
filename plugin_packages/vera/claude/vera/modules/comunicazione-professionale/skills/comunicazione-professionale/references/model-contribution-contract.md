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
reason now, concrete usefulness, distinct angle, source-specific information,
the next decision or verification enabled, the limit of that use, banality
risk, repetition against selected history, and whether silence is better. Do
not claim to know what the reader already knew. This is a model-led editorial
judgment, not a deterministic novelty score.

For `publish`:

- source assessments identify authority and limitations without treating a
  mechanically registered file as semantically sufficient;
- claims are atomic and preserve modality, dates, exceptions, uncertainty, and
  the commercialista's judgment boundary;
- every claim and every substantive visual slide references registered source
  IDs;
- the master brief contains only conclusions represented in the claim set;
- channel drafts adapt the same claim set to requested channels;
- `visual_story.decision` is `render` only when its stated incremental value is
  credible relative to the channel draft; otherwise it is `omit` with no
  slides;
- a rendered visual story contains two to eight slides and uses the content
  roles `cover`, `change`, `audience`, `timeline`, `action`, `caveat`, or
  `close`; each slide states its reader use, its relationship to the post, a
  human-readable public source note, and internal source IDs for traceability;
- every rendered slide selects a `layout_variant`. This is a model-led editorial
  composition choice, not a keyword rule: choose the structure that best
  expresses the slide's actual job. The deterministic renderer preserves that
  choice and verifies exact copy, sources, identity placement, and overflow;
- no public draft or slide exposes `SRC-*`, `HIST-*`, or `CLAIM-*` identifiers;
- every Studio-profile leaf is covered exactly once by `field_provenance`.
  Use `observed_history` only for a convention actually evidenced by the cited
  selected history; use `user_supplied` for an explicit Studio instruction or
  asset; use `vera_default_proposal` for a proposed convention the evidence
  does not establish. Professional approval may adopt a default as the future
  Studio standard, but it does not make that convention historically observed;
- `studio_profile_proposal` is present only when selected prior communications
  were read. It covers voice plus document, email, website, social, letterhead,
  numbering, heading, byline, footer, sign-off, CTA conventions, PDF font
  family, margins, logo geometry, contact-rail geometry, type sizes, leading,
  and rule weight. Do not reduce studio format to logo and colors.

The contribution must never contain credentials, session material, invented
client stories, engagement claims unsupported by supplied metrics, or an
instruction to send or publish automatically.

Creative Production, when explicitly selected, receives a mechanically locked
art-direction handoff only after this contribution has passed the independent
editorial assessment. It cannot change the contribution's recommendation,
claims, source notes, exact slide copy, numbers, dates, identity rule, or logo.
Its output is a non-publishable reference. Any material translation of a
selected direction into `layout_variant` or Studio-profile choices creates a
new contribution and therefore requires a fresh assessment.

Before generation, write a communication-specific `answer_contract.json` with
the full-claim validation profile. After generation, write a separate
`claim_assurance.json` covering every material claim and separating source
identity, semantic support, reasoning, and professional judgment. Correct all
support and reasoning defects before editorial assessment.

Then write a separate `editorial_assessment.json` matching its schema and bound
to the exact canonical contribution and claim-assurance digests. Use a fresh
blinded model-led pass from a currently qualified provider/model/template and
record its isolated assessment protocol. `ready` means the assessor found a specific, useful,
bounded reason to publish and agreed with the visual `render` or `omit`
decision. `revise` and `no_publish` require regeneration; never relabel them as
ready to pass the mechanical gate.

The assessment must not merely repeat the contribution's self-justification. It
must identify the exact reader payoff, professional expertise beyond summarizing
the source, genericity risk, counterfactual value, and weakest element. It gives
a separate verdict for every channel and, when a visual is proposed, every
slide. A contribution cannot be recorded while a channel is `revise`/`omit` or a
slide is `weak`/`redundant`. Those labels are semantic model judgments; the
workflow code only preserves and enforces them.

The assessment also judges whether public evidence is identifiable to the
intended reader. A source footer is not useful merely because it contains the
word “Fonte”: when exact evidence is available, the published note should
identify the authority and instrument and include the material date, number,
version, or link needed to retrieve it. This remains a model-led,
context-sensitive editorial judgment; deterministic validation only prevents
empty notes and internal traceability IDs from being published.
