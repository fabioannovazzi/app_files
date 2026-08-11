> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Plan Answer Workflow Reference

This reference expands the core workflow in `SKILL.md`. Load it when a run needs detailed wording guidance, source strategy, or validation interpretation.

## Research Lens

Use these codes in summaries and in any working notes:

- `planning_ex_ante`: the user asks how to structure future action before implementation.
- `assessment_ex_post`: the user asks to evaluate a setup, transaction, or conduct that already exists.
- `defense_audit_dispute`: the user asks how to defend or prepare in audit, challenge, or litigation.
- `compare_approaches`: the user asks for alternatives or the posture is unclear.
- `efficient`: prioritize speed, simplicity, and operational cost.
- `defensible_conservative`: prioritize legal robustness and low challenge risk.
- `balanced`: trade off practicality and defensibility.
- `domestic_only`: one-country domestic law focus.
- `domestic_plus_EU`: domestic law plus EU law relevance.
- `cross_border_multi_jurisdiction`: multiple national jurisdictions are materially relevant.

## Conversational Lawyer Intake

Claude should not recreate the old web form. After deterministic inspection,
use the generated `lawyer_intake` recipe as a boundary: it intentionally does
not supply semantic questions or choices. Claude should:

- select or assume the research lens semantically and state it when useful;
- in Default mode, state proposed defaults and unresolved assumptions before
  asking the user to confirm or switch to Plan mode for native choices;
- in Plan mode, use `request_user_input` when it is available for unresolved
  discrete choices, with the recipe's preferred option as the default;
- disregard the inspection layer as a confirmation decision maker; its
  `required: false` values mean only that confirmation is model-led;
- ask only material missing facts, normally no more than 3 questions;
- explain briefly why each answer matters;
- ask about output format only when it changes the prompt, such as client memo,
  risk/options matrix, local-counsel brief, checklist, or draft response
  outline;
- continue with explicit assumptions when the user asks for speed or the
  missing facts can be carried as caveats.

## Intake Confirmation

First check whether the run has a material research-angle decision. This is the
controlling research angle: problem framing, decision lens, risk appetite, scope
boundaries, audience, output artifact, and source posture. If that choice exists
and materially changes the run, Default mode should state the inferred default
and pause for chat confirmation or invite Plan mode for native choices before
legal-framework details or drafting. In Plan mode, use the native choice widget
when the host exposes it. Mode transitions are host/user controlled; Claude can
request Plan mode, but must not claim that it can switch modes itself.

After required choices are fixed, produce a concise execution plan that names
the confirmed angle, framework, output language, remaining caveats, scripts to
run, and deliverables, then proceed. Ask for extra approval only when a material
unresolved choice, external write, unsafe action, or reduced/debug output request
changes the work. A later Default-mode execution run should use the confirmed
handoff and should not re-ask unless the facts conflict.

## Answer Contract And Generation Route

Treat prompt optimization as an internal stage. The user supplies a legal, tax,
or compliance question; do not ask whether they want a prompt optimized.

Claude must write `answer_contract.json` before generation. Keep these decisions
separate:

- generation route: `codex_direct`, `chatgpt_deep_research`, or
  `external_document`;
- document type: the requested artifact, such as a research report, legal memo,
  one-page letter, response letter, checklist, or counsel brief.
- validation scope: all material claims by default, selected material claims
  only when that limit is explicit, or a limited review;
- correction policy: correct the answer when the evidence supports a correction,
  or produce review findings only;
- professional-judgment policy: flag judgment-dependent conclusions for
  professional review rather than certifying them.

Choose both with model-led judgment or user confirmation. Deterministic scripts
only validate that the explicit contract has the required fields and allowed
codes. They must not infer the route or document type from keywords.

Native Deep Research is a ChatGPT-window handoff, not a Claude or Work tool.
Direct Claude drafting skips that handoff but still carries the answer contract
and source record into the validator.

## Output Language And Jurisdiction Scope

Treat output language and legal jurisdiction as separate decisions. The
deterministic layer must not select governing law and must not use output
language as a jurisdiction fallback. It must not select legal topics, research
phasing, or source domains. It may inventory possible country, state, canton,
forum, or source-framework cues, but the confirmed framework and source
strategy must come from Claude's model-led legal judgment after user
confirmation.

The final prompt must state both the output language and the selected legal or
source framework before the research task. The framework may be user-confirmed
or an explicit model-led assumption when the question is sufficiently clear.
Ask only when a material ambiguity would change the answer.

`prompt_recipe.json["angle_confirmation"]` and
`prompt_recipe.json["jurisdiction_confirmation"]` record that deterministic
inspection did not make these semantic decisions. Claude determines whether
confirmation is material and generates any choices from the facts. Named laws,
regulators, and issue categories are plugin-specific domain choices; offer them
only when the facts cue them or the user must supply a missing custom value.

## Complexity And Phasing

Claude owns the complexity and phasing judgment. Do not rely on deterministic
topic flags to decide whether a matter is broad. When Claude determines that a
broad multi-specialist legal question needs phasing, it must write a phased
prompt because those questions degrade if forced into one pass.

For phased matters, require:

- Phase 0 for source map, fact preservation, chronology, missing facts, and
  workplan;
- later phases grouped by specialist area;
- a final synthesis only after the specialist phases;
- a mandatory chronology table or timeline when timing affects causation,
  capacity, limitation periods, transfers, or tax;
- confidence labels for every major conclusion;
- separation of black-letter law, unsettled doctrine, local or cantonal
  practice, likely strategy, and evidentiary dependency;
- hard anti-fabrication wording for cases, decisions, tax circulars, treaty
  provisions, administrative practice, and professional commentary;
- explicit scope controls for trust, tax, asset-recovery, procedure, or
  foreign-law sections when those topics are present.

If a model cannot complete all phases at a high quality level in one answer,
the prompt should instruct it to complete the early phases first and identify
the remaining phases, instead of compressing doctrine or inventing authority.

## Source Strategy

The final prompt should ask Deep Research to prefer stable, official sources:

- legislation and official consolidated law portals;
- official gazettes;
- tax authority guidance;
- court portals and reported decisions;
- EU or treaty sources where relevant;
- professional doctrine only after primary and official sources.

Use source domains tied to the confirmed framework and actual legal issue. Do
not use deterministic source-domain suggestions for legal prompts.

The plugin keeps `prompt_recipe.json["source_domains"]` as a
backward-compatible recipe field, but deterministic validation must not choose a
legal source-domain list. Claude must curate source websites from the confirmed
legal framework and the actual issue, save them as a sidecar list, and pass that
file to validation. Keep the source hierarchy and domain list separate:

- the hierarchy explains which source classes are preferred;
- `source_domains.txt` gives the user concrete websites/domains one per line;
- `source_domains_comma.txt` gives the same websites as comma-separated URLs to
  paste into Deep Research source controls;
- the list is model-curated and must be reviewed for relevance before delivery.

Ask Deep Research to flag unavailable or broken URLs and avoid making unsupported claims.

## Prompt Structure

The final prompt should include:

- role and task framing;
- output language and jurisdiction assumption notice;
- explicit research lens: posture, objective, and scope;
- selected or assumed output format;
- factual background copied or summarized without losing key anchors;
- research questions;
- model-curated qualified source domains/websites when useful;
- source hierarchy and coverage period;
- citation and notes rules;
- link-quality and cross-check rules;
- required output structure;
- uncertainty/caveat section;
- clarifying-question policy.

When Claude determines that the matter needs phasing, the final prompt should
also include sections titled or equivalent to "Core Method: Modular Workflow",
"Authority Safety", "Confidence Protocol", and "Chronology".

## Deterministic Validation Interpretation

`prompt_audit.json` is a minimal packaging and fact-preservation guardrail, not
a legal conclusion. If it fails, repair mechanical issues such as missing
facts, missing citations/notes instructions, missing jurisdiction notice, or
missing output structure. Deterministic validation must not force legal topic,
source-domain, or research-phasing choices.

Before the deterministic audit can pass, Claude must write
`prompt_contract_review.json` as a model-led semantic comparison of the source
question, `answer_contract.json`, and the optimized prompt. It separately
reviews question and material facts, generation route, document type, purpose,
audience, language, jurisdiction, evidence display, research lens, validation
policy, and source strategy. Deterministic code checks only that this review is
complete and explicitly accepted. Literal question overlap is an observation,
not a semantic proxy. Any later edit to the prompt makes the review stale and
requires a new semantic review.
