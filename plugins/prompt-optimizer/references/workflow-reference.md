# Optimize Prompt Workflow Reference

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

Codex should not recreate the old web form. After deterministic inspection,
use the generated `lawyer_intake` recipe as a conversational guide:

- state the inferred research lens in plain language;
- in Default mode, state proposed defaults and unresolved assumptions before
  asking the user to confirm or switch to Plan mode for native choices;
- in Plan mode, use `request_user_input` when it is available for unresolved
  discrete choices, with the recipe's preferred option as the default;
- if `prompt_recipe.json["angle_confirmation"]["required"]` is true, resolve
  the research-angle choice before legal-framework details or drafting;
- if `prompt_recipe.json["jurisdiction_confirmation"]["required"]` is true,
  resolve the listed legal-framework choice before drafting;
- ask only material missing facts, normally 2-5 questions;
- explain briefly why each answer matters;
- ask about output format only when it changes the prompt, such as client memo,
  risk/options matrix, local-counsel brief, checklist, or draft response
  outline;
- continue with explicit assumptions when the user asks for speed or the
  missing facts can be carried as caveats, but not when angle or jurisdiction
  confirmation is marked required.

## Intake Confirmation

First check whether the run has a material research-angle decision. This is the
controlling research angle: problem framing, decision lens, risk appetite, scope
boundaries, audience, output artifact, and source posture. If that choice exists
and materially changes the run, Default mode should state the inferred default
and pause for chat confirmation or invite Plan mode for native choices before
legal-framework details or drafting. In Plan mode, use the native choice widget
when the host exposes it. Mode transitions are host/user controlled; Codex can
request Plan mode, but must not claim that it can switch modes itself.

After required choices are fixed, produce a concise execution plan that names
the confirmed angle, framework, output language, remaining caveats, scripts to
run, and deliverables, then proceed. Ask for extra approval only when a material
unresolved choice, external write, unsafe action, or reduced/debug output request
changes the work. A later Default-mode execution run should use the confirmed
handoff and should not re-ask unless the facts conflict.

## Output Language And Jurisdiction Scope

Treat output language and legal jurisdiction as separate decisions. The
deterministic layer must not select governing law and must not use output
language as a jurisdiction fallback. It must not select legal topics, research
phasing, or source domains. It may inventory possible country, state, canton,
forum, or source-framework cues, but the confirmed framework and source
strategy must come from Codex's model-led legal judgment after user
confirmation.

The final prompt must state both the output language and the user-confirmed
legal/source framework before the research task. If no framework has been
confirmed, stop and ask rather than drafting under a deterministic assumption.

`prompt_recipe.json["angle_confirmation"]` is the deterministic guidance for
general angle confirmation. When `required` is true, Codex must not draft until
the user confirms the research angle or supplies a custom framing.

`prompt_recipe.json["jurisdiction_confirmation"]` is the deterministic guidance
for legal-framework confirmation. When `required` is true, Codex must not draft until the
user confirms one of the possible framework cues or supplies a custom
framework. Named laws, regulators, and issue categories are
plugin-specific domain choices after the research angle is fixed; offer them
only when the source facts cue them or the user must supply a missing custom
value.

## Complexity And Phasing

Codex owns the complexity and phasing judgment. Do not rely on deterministic
topic flags to decide whether a matter is broad. When Codex determines that a
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
legal source-domain list. Codex must curate source websites from the confirmed
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

When Codex determines that the matter needs phasing, the final prompt should
also include sections titled or equivalent to "Core Method: Modular Workflow",
"Authority Safety", "Confidence Protocol", and "Chronology".

## Deterministic Validation Interpretation

`prompt_audit.json` is a minimal packaging and fact-preservation guardrail, not
a legal conclusion. If it fails, repair mechanical issues such as missing
facts, missing citations/notes instructions, missing jurisdiction notice, or
missing output structure. Deterministic validation must not force legal topic,
source-domain, or research-phasing choices.
