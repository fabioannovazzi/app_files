---
name: prompt-optimizer
description: Use when a user wants Codex to turn a legal, tax, or compliance question into a source-backed Deep Research prompt, with fact preservation, research posture, source hierarchy, citation rules, and deterministic validation. Do not use for general copywriting or ordinary prompt polishing unrelated to Deep Research.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Optimize Prompt

Use this skill when a legal, tax, or compliance question must be turned into a structured Deep Research prompt. The plugin is a guided Codex workflow: Codex inspects the question, confirms only essential assumptions, writes the optimized prompt, runs deterministic validation, repairs gaps, and delivers a reviewable prompt package.

The workflow is not Italian-only. Support the same five working locales used by the Mparanza plugins: `it`, `en`, `fr`, `de`, and `es`. Keep artifact file names and JSON keys in English for stability, but speak to the user in the chosen working language.

Detailed wording guidance and validation expectations live in `../../references/workflow-reference.md` from this skill directory. Load that reference when the run needs extra detail beyond the workflow below.

## Jurisdiction Policy

Output language and legal jurisdiction are separate decisions. The user may ask
for an English answer about Swiss/Geneva law, an Italian answer about German
law, or any other combination.

The deterministic inspection layer must not choose governing law, legal topic,
research phasing, or source domains. It only inventories raw
jurisdiction/framework cues from the question text. It must not use output language as a legal fallback, and it must not silently treat French as Geneva,
German as Zurich, English as UK, or any language as a jurisdiction.

Before writing the optimized prompt, tell the user the output language, the
detected legal-framework cues, and that the governing framework is unconfirmed.
If `prompt_recipe.json["jurisdiction_confirmation"]["required"]` is true, stop
and get the user's framework choice in chat before drafting. Do not use the
fast path for required jurisdiction confirmation.

## Complexity And Phasing Policy

Codex owns complexity and phasing judgment. Do not rely on deterministic topic
flags to decide whether a matter is broad. When Codex determines that a broad or
multi-specialist matter needs phasing, the optimized prompt must not request a
single compressed mega-memo. It must require a modular workflow with:

- a Phase 0 source map, fact-preservation checklist, and chronology table;
- separate phases for distinct specialist areas;
- a final synthesis only after the specialist phases;
- explicit scope controls for specialist subtopics such as tax, trusts, asset
  recovery, procedure, or foreign-law issues;
- a confidence protocol for major conclusions;
- an anti-fabricated-authority instruction.

For broad legal/tax/compliance matters, require every major conclusion to
distinguish black-letter law, unsettled doctrine, cantonal or local practice,
likely litigation or response strategy, and evidentiary dependency. Then require
a confidence label: high confidence, moderate confidence, or
uncertain/practice-dependent.

Always include a hard authority-safety rule in broad legal prompts: do not
invent cases, court decisions, tax circulars, treaty provisions, administrative
practice, or professional commentary. If authority cannot be verified from
official or reliable sources, the Deep Research answer must say verification
was not possible.

## Codex-Native Run UX

Keep the interaction conversational. The user can speak naturally to Codex;
Codex should respond like a careful lawyer doing intake. Do not recreate the
old web form unless the user explicitly asks for a structured UI.

Default output policy: produce the richest normal package for the workflow.
`optimized_prompt.md`, source-domain sidecars, validation audit, prompt package,
and human README are not choices to propose when they are natural outputs of
the plugin; generate them whenever dependencies and source data permit. Ask
only when an output is technically impossible, unsafe, or the user explicitly
requests a reduced/debug run.

Default currency policy: use Euro (`EUR`) unless the user or source file explicitly states another currency. Do not ask for currency when it is otherwise unresolved; record `EUR` as the assumption.

The plugin has two host-mode behaviors:

- Default mode is the normal starting point. Inspect the question, identify
  material assumptions and doubts, then proceed with explicit assumptions unless
  a material choice is unresolved. If a material choice is unresolved, state the
  proposed defaults and say that the user can switch this chat to Plan mode to
  change them with structured choices. The user may also answer in chat; if they
  do, use that answer and continue in the same run.
- Plan mode is an optional structured-intake lane. When `request_user_input` is
  available and a material choice is unresolved, use the native widget instead
  of a textual multiple-choice list. Use the recipe's preferred option as the
  default and show only the most relevant options; the host-provided custom or
  free-form path covers anything outside the listed choices.

The plugin must never claim that it switched modes itself. Mode transitions are
host/user controlled. Codex may ask the user to switch to Plan mode for
structured intake, but it cannot programmatically enter or leave that mode.

Run UX:

1. First check whether there is a material research-angle decision: the
   controlling frame, decision lens, risk appetite, scope boundaries, audience,
   or source posture. Ask the choice in chat when a material research-angle
   decision is still unresolved.
2. When `angle_confirmation.required` is true in Default mode, state the
   inferred angle and preferred default, then pause for chat confirmation or ask
   the user to switch to Plan mode if they want the native choices. In Plan
   mode, use `request_user_input` when available.
3. State the inferred jurisdiction cues, posture, objective, and scope in plain
   language after the angle is fixed.
4. When `jurisdiction_confirmation.required` is true, handle it as a
   plugin-specific legal-framework choice before drafting. In Default mode,
   state the framework cues and proposed default or unresolved status; in Plan
   mode, use the native widget when available.
5. Ask only the material missing questions before drafting. Prefer 2-5
   numbered questions with a short "why this matters" phrase for each, unless
   a native widget is available for the same decision.
6. Do not ask whether to package, validate, or write source-domain sidecars.
   If output format materially changes the research logic, infer a complete
   client-ready structure from the facts and ask only when that inference is
   genuinely not possible.
7. After required choices are fixed, state a concise execution plan naming
   confirmed assumptions, remaining caveats, scripts to run, and deliverables,
   then proceed. Ask for extra approval only when a material unresolved choice,
   external write, unsafe action, or reduced/debug output request changes the
   work.
8. If the user wants speed, or the missing facts can be handled as caveats,
   continue with explicit assumptions instead of blocking, except for required
   angle or jurisdiction confirmation.
9. End with concise artifact paths and unresolved assumptions.

Use tables only when they make the answer easier to scan. Do not ask the user
to fill a form.

## Intake And Confirmation

First check whether the run has a material research-angle decision. If it does,
Default mode should state the inferred defaults and pause only when confirmation
is materially required, or invite the user to switch to Plan mode for native
choices. In Plan mode, use `request_user_input` when it is available. If the
user answers in chat, use that answer and continue in the same run.

Research-angle confirmation means the controlling frame before plugin-specific
details: problem framing, decision lens, risk appetite, scope boundaries,
audience, and source posture. Legal frameworks, named
regulators, tax years, document classes, or mapping details are later domain
choices generated from the actual inputs and facts, not the generic model. Do
not offer named laws or regulators unless the facts cue them or the user must
supply a missing custom value.

If `angle_confirmation` or `jurisdiction_confirmation` is required, resolve it
before drafting. Use native Plan-mode choices when available; otherwise ask the
options in chat and wait. Do not draft under an unconfirmed angle or framework.

For repository-wide Codex UX compatibility, map the standard artifacts to this
conversational flow: a checklist can be a short progress note; a Run Intake table
and Decision Table are optional compact summaries when the facts are complex;
an execution checkpoint can state command intent, output folder, and expected
artifacts before long-running or write-heavy steps; ask for approval only when
the step is external, destructive, approval-sensitive, or still depends on an
unresolved material choice. An Artifact Card can be the final concise list of
generated outputs and review status. If a run produces many files, create
`codex_run_review.md` in the output folder. Do not edit generated ZIPs during a
run.

## Conversational Lawyer Intake

After deterministic inspection, read `prompt_recipe.json["lawyer_intake"]`.
Use it as an intake guide, not as UI copy. Translate or adapt the questions to
the user's language and facts.

The intake should feel like a lawyer narrowing the case:

- explain the inferred angle: e.g. "This looks like a defensive response to a
  past event, not future planning";
- ask the missing facts that change legal analysis, deadlines, evidence, or
  output format;
- explain why each question matters in one short clause;
- avoid generic administrative questions when the answer can be inferred;
- keep the fast path available by stating assumptions and caveats, except where
  `angle_confirmation_required` or `jurisdiction_confirmation_required` is true.

## Core Principle

Codex owns the reasoning and prompt writing: research posture, objective, scope, source strategy, fact summary, and final wording.

Deterministic Python code owns only question inventory, anchor extraction, validation, and packaging. The plugin scripts must not make direct OpenAI API calls or other model API calls.

The user should not interact directly with CLI scripts. Treat scripts as internal tools Codex runs on behalf of the user.

## Qualified Source Domains

The old web workflow produced a copyable list of reliable websites for Deep
Research. Preserve that behavior in the plugin.

Do not use deterministic source-domain selection. Codex must curate any
"Qualified source domains" list from the confirmed legal framework and the
actual issue. Do not copy domains from `prompt_recipe.json["source_domains"]`;
that field is intentionally empty for legal prompts.

Validation writes `source_domains.txt` next to the optimized prompt for
backward-compatible packaging and `source_domains_comma.txt` for Deep Research
website fields that require comma-separated URLs. Deterministic validation must
not choose legal source domains; Codex must curate the list and pass it as a
sidecar file. Treat any domains extracted from the optimized prompt as
model-curated fallback data only, and review them for legal relevance before
delivery.

Preferred artifact shape:

- Keep concrete websites out of the optimized prompt unless the user explicitly
  asks for a single self-contained prompt.
- Save the curated websites in `<output-dir>/draft_source_domains.txt`, one URL or
  domain per line, or comma-separated if easier.
- Pass that file to validation with `--source-domains-file`.

## Inputs

Required:

- a legal, tax, or compliance question or case text, preferably saved to a UTF-8 `.txt` or `.md` file in the work folder.

Optional:

- working language: `it`, `en`, `fr`, `de`, or `es`;
- legal jurisdiction hints, independent from output language;
- research posture: `planning_ex_ante`, `assessment_ex_post`, `defense_audit_dispute`, or `compare_approaches`;
- objective: `efficient`, `defensible_conservative`, or `balanced`;
- scope: `domestic_only`, `domestic_plus_EU`, or `cross_border_multi_jurisdiction`;
- source preferences or excluded sources.

## First Run Workflow

1. Ask for the question text only if it is missing. Do not ask for working language, jurisdiction, posture, objective, scope, or output format as form fields when they can be inferred, except that required angle and jurisdiction confirmations must be explicit.
2. Save the source question in the work folder as `question.md` or `question.txt`.
3. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the environment allows it or explain what dependency capability is missing.

4. Run deterministic inspection:

```bash
python scripts/inspect_question.py <question-file> --output-dir <output-dir> --language <auto|it|en|fr|de|es>
```

5. Read `question_inventory.json` and `prompt_recipe.json`. Summarize key fact anchors, explicit questions, jurisdiction hints, possible frameworks, `policy_source`, inferred posture/objective/scope, `angle_confirmation`, and `jurisdiction_confirmation`. Tell the user the output language, detected legal-framework cues, inferred research lens, proposed defaults, and unresolved assumptions. Do not describe a deterministic jurisdiction, legal topic, phasing choice, or source-domain list as resolved.
6. If `prompt_recipe.json["angle_confirmation"]["required"]` is true, resolve the general angle-confirmation step before domain-specific choices. In Default mode, state the preferred angle and pause for chat confirmation or tell the user they can switch to Plan mode for native choices. In Plan mode, use `request_user_input` when available. Do not draft before the angle is fixed.
7. If `prompt_recipe.json["jurisdiction_confirmation"]["required"]` is true, resolve the legal-framework choice before drafting. In Default mode, state the framework cues and unresolved points, then pause for chat confirmation or invite Plan mode for native choices. In Plan mode, use `request_user_input` when available. Do not draft under an unconfirmed framework.
8. Use `prompt_recipe.json["lawyer_intake"]` to ask a short conversational intake when material facts are missing. Ask no more than five questions. If Plan mode is active and a question is a discrete material choice, prefer native choices. If the user wants a fast draft, continue with explicit assumptions and caveats only after any required angle and jurisdiction confirmation is resolved.
9. Write the optimized Deep Research prompt in Codex. It must preserve all material facts, dates, percentages, amounts, entities, chronology, and explicit questions from the source question. A name or other personal fact is not removed merely because it is personal; omit it only when it is professionally immaterial, and never describe that omission as anonymization of text already read by Codex. Include an explicit "Research lens" / "Lente di ricerca" section naming posture, objective, and scope, plus the selected or assumed output format. Include source hierarchy and citation rules, but keep concrete websites in the separate source-domain sidecar unless the user asks for a self-contained prompt. If Codex judges that the matter needs a phased workflow, include chronology, confidence, legal-realism, specialist scope-control, and anti-fabricated-authority instructions.
10. Save the draft prompt in the work folder as `draft_prompt.md`.
10a. Curate qualified source websites from the confirmed framework and actual issue, then save them in the work folder as `draft_source_domains.txt`. Do not copy domains from `prompt_recipe.json["source_domains"]`; that field is intentionally empty.
11. Run deterministic validation:

```bash
python scripts/validate_prompt.py <question-file> <output-dir>/draft_prompt.md --output-dir <output-dir> --language <auto|it|en|fr|de|es> --source-domains-file <output-dir>/draft_source_domains.txt
```

12. Read `prompt_audit.json`. If any check fails, repair the prompt in Codex, overwrite `draft_prompt.md`, and rerun validation until the prompt passes or only explainable residual gaps remain.
13. Deliver `optimized_prompt.md`, `source_domains_comma.txt`, `source_domains.txt`, `prompt_package.md`, `README_HUMAN.md`, and `prompt_audit.json`. Tell the user that `optimized_prompt.md` goes into Deep Research and `source_domains_comma.txt` goes into the Deep Research websites field. Report any failed checks or assumptions explicitly.

## Prompt Requirements

The optimized prompt must require:

- a professional role aligned with the question;
- a user-facing jurisdiction assumption notice that distinguishes output language from legal jurisdiction;
- a clear research posture, objective, and scope;
- a selected or assumed output format;
- source hierarchy favoring primary legislation, case law, official tax/administrative guidance, court portals, EU/international official portals where relevant, and professional doctrine;
- a model-curated source hierarchy and an instruction to use the separate qualified website list;
- numeric citations in the answer body and a final notes/source section;
- official, stable URLs and broken-link replacement or flagging;
- cross-checking substantive claims against independent references;
- explicit residual uncertainty;
- no loss of source facts, numbers, dates, ownership percentages, entities, steps, chronology, or explicit questions;
- up to three clarifying questions only when essential facts are missing;
- client-ready structure such as premises, analysis, conclusions, notes, and caveats.

When Codex determines that the matter is broad or multi-specialist, the
optimized prompt must additionally require:

- phased workflow instead of a one-pass memorandum;
- chronology table or timeline before substantive conclusions;
- confidence labels for major conclusions;
- legal-realism categories separating black-letter law, unsettled doctrine,
  local or cantonal practice, strategy, and evidentiary dependency;
- hard prohibition on fabricated cases, circulars, treaties, and authorities;
- constrained trust, tax, foreign-law, or procedure sections where those topics
  are present.

## Expected Outputs

- `question_inventory.json`;
- `prompt_recipe.json`;
- `optimized_prompt.md`;
- `prompt_audit.json`;
- `prompt_package.md`.
- `source_domains.txt`.
- `source_domains_comma.txt`;
- `README_HUMAN.md`;
- `run_intake.json`;
- `review_payload.json`;
- `ui_decisions.json`;
- `applied_decisions.json` after reviewer decisions are applied;
- `final_artifacts.json`.

`draft_prompt.md` and `draft_source_domains.txt` are temporary working files during validation, not delivered outputs.

## MCP Review UI

Use MCP/HTML for the final generated package review, not for simple intake
choices.

When the local MCP server is available after validation:

1. Read `run_intake.json`, `review_payload.json`, `ui_decisions.json`, and
   `final_artifacts.json` from the output folder.
2. Call `validate_prompt_optimizer_review` with `review_payload` before
   rendering.
3. If validation succeeds, call `render_prompt_optimizer_review` with the same
   payload objects so Codex can show the local HTML widget
   `ui://widget/prompt-optimizer-review.html`.
4. Use the widget to inspect failed prompt-audit checks, `optimized_prompt.md`,
   source-domain sidecars, `prompt_package.md`, and `README_HUMAN.md`.
5. When the reviewer records actions in the widget or Codex collects decisions
   through fallback review, call `save_prompt_optimizer_decisions` so
   `ui_decisions.json` is validated and persisted. When the reviewer is done,
   call `apply_prompt_optimizer_decisions` so `applied_decisions.json` and
   `final_artifacts.json` reflect accepted, edited, unclear, skipped, or
   document-requested items before treating the prompt package as reviewed.

If MCP rendering is unavailable, fall back to a markdown review summary from
`review_payload.json`, `prompt_audit.json`, `optimized_prompt.md`,
`prompt_package.md`, and the source-domain sidecars. Keep review decisions
pending unless they are recorded in `ui_decisions.json` and consumed into
`applied_decisions.json`.

Do not build an HTML page for `angle_confirmation`,
`jurisdiction_confirmation`, or a 2-3 option legal-framework choice. Those
remain chat choices in Default mode and native Plan-mode choices when this
conversation is in Plan mode and `request_user_input` is available.

## Language Policy

Ask for or infer the working/output language:

- `it`: Italian;
- `en`: English;
- `fr`: French;
- `de`: German;
- `es`: Spanish.

If the user writes in a supported language, default to that working language. If language is unclear, use `auto` for inspection and ask only if the final prompt language matters.

Starter prompts:

```text
IT: Usa Optimize Prompt su questo quesito fiscale/legale. Lingua output: it. Inventaria i possibili indizi di giurisdizione senza scegliere il diritto applicabile; conferma il framework con l'utente prima dell'esecuzione. Ispeziona i fatti, proponi postura/obiettivo/ambito, fai una breve intake da avvocato se mancano fatti materiali, scrivi un prompt Deep Research completo con fonti ufficiali, citazioni, note, controllo link e vincolo di preservazione dei fatti. Valida e ripara il prompt prima di consegnarlo.
EN: Use Optimize Prompt on this legal/tax question. Output language: en. Inventory possible jurisdiction/framework cues without choosing governing law; confirm the framework with the user before execution. Inspect the facts, propose posture/objective/scope, run a short lawyer-style intake if material facts are missing, write a complete Deep Research prompt with official sources, citations, notes, link checks, and fact-preservation constraints. Validate and repair the prompt before delivery.
FR: Utilise Optimize Prompt sur cette question juridique/fiscale. Langue de sortie: fr. Inventorie les indices possibles de juridiction/cadre juridique sans choisir le droit applicable; confirme le cadre avec l'utilisateur avant l'exécution. Inspecte les faits, propose posture/objectif/portee, fais une brève intake de juriste si des faits matériels manquent, redige un prompt Deep Research complet avec sources officielles, citations, notes, controle des liens et contrainte de preservation des faits. Valide et repare le prompt avant livraison.
DE: Verwende Optimize Prompt fuer diese Rechts-/Steuerfrage. Ausgabesprache: de. Inventarisiere moegliche Hinweise auf Rechtsordnung/Framework, ohne das anwendbare Recht auszuwaehlen; bestaetige das Framework vor der Ausfuehrung mit dem Nutzer. Pruefe die Fakten, schlage Posture/Ziel/Scope vor, fuehre bei fehlenden wesentlichen Fakten eine kurze anwaltsartige Intake durch und schreibe einen vollstaendigen Deep-Research-Prompt mit offiziellen Quellen, Zitaten, Notizen, Linkpruefung und Faktenerhalt. Validiere und repariere den Prompt vor der Lieferung.
ES: Usa Optimize Prompt con esta cuestión jurídica/fiscal. Idioma de salida: es. Identifica los posibles indicios de jurisdicción o marco jurídico sin elegir el derecho aplicable; confirma el marco con el usuario antes de ejecutar. Examina los hechos, propón postura, objetivo y alcance, realiza una breve entrevista jurídica si faltan hechos materiales y redacta un prompt completo para Deep Research con fuentes oficiales, citas, notas, comprobación de enlaces y preservación de los hechos. Valida y corrige el prompt antes de entregarlo.
```

## Failure Modes

- If the source question is empty, ask the user for the question before running scripts.
- If deterministic validation flags missing fact anchors, repair the prompt rather than dismissing the warning.
- If a source question asks for legal/tax advice directly, produce a research prompt, not the substantive legal/tax answer.
- If the question requests evasion, concealment, forged evidence, or other unsafe conduct, refuse to optimize it and explain the boundary.
- If the user wants a general marketing or writing prompt, do not use this plugin.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting the deliverables, briefly identify concrete improvements that would have made this plugin run better. Base suggestions on the actual session, such as a missing jurisdiction pattern, weak source-class rule, brittle fact-anchor extraction, missing deterministic validation check, unclear assumption, needed fixture, output gap, installation friction, or repeated manual step.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts. Do not submit it to
Mparanza automatically. When this workflow runs through Vera, use Vera's
consent-based Plugin Improvement Feedback process for any transmission.
