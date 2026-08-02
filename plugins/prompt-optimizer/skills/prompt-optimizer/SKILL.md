---
name: prompt-optimizer
description: Use internally when Vera or Codex receives a legal, tax, or compliance question and must define the answer contract, choose a model-led generation route, and prepare source-backed generation instructions. The user does not need to ask for prompt optimization. Do not use for unrelated copywriting or ordinary prompt polishing.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Plan The Answer

Use this skill as the internal planning stage of Vera's question-to-validated-
answer journey. Codex inspects the question, confirms only essential
assumptions, writes `answer_contract.json`, chooses the generation route with
model-led judgment, prepares the generation instructions, runs deterministic
shape validation, and delivers a reviewable handoff package.

Do not ask the user whether to optimize a prompt. The user supplies the
professional question; this workflow is internal orchestration.

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

Before writing the optimized prompt, decide the legal framework semantically
from the question and available context. The deterministic recipe only records
possible cues and never decides whether confirmation is required. Ask the user
only when a material governing-law, forum, or source-framework ambiguity would
change the answer; otherwise record the framework as confirmed or explicitly
assumed in `answer_contract.json` and proceed.

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
`answer_contract.json`, `optimized_prompt.md`, source-domain sidecars,
validation audit, prompt package, and human README are not choices to propose
when they are natural outputs. Generate them whenever dependencies and source
data permit.

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

1. First check semantically whether there is a material research-angle decision: the
   controlling frame, decision lens, risk appetite, scope boundaries, audience,
   or source posture. Ask the choice in chat when a material research-angle
   decision is still unresolved.
2. Treat `angle_confirmation.required` and
   `jurisdiction_confirmation.required` as non-decisions from the inspection
   layer. Their normal value is `false` with decision owner `codex_or_user`.
   Codex—not keyword inspection—decides whether to ask.
3. State the selected or assumed jurisdiction, posture, objective, and scope in
   plain language when useful. Do not force a confirmation ceremony when the
   question already resolves them.
4. If semantic review finds a material unresolved choice, propose the most
   likely default and ask in chat; in Plan mode, use the native widget when
   available.
5. Ask only the material missing questions before drafting. Prefer at most 3
   numbered questions with a short "why this matters" phrase for each, unless
   a native widget is available for the same decision.
6. Do not ask whether to optimize, package, validate, or write source-domain
   sidecars. Infer `generation_route` and `document_type` from the question
   when they are clear. Ask only when the choice materially changes the answer
   and cannot be inferred.
7. After required choices are fixed, state a concise execution plan naming
   confirmed assumptions, remaining caveats, scripts to run, and deliverables,
   then proceed. Ask for extra approval only when a material unresolved choice,
   external write, unsafe action, or reduced/debug output request changes the
   work.
8. If missing facts can be handled as caveats, continue with explicit
   assumptions instead of blocking.
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

The inspection artifact does not decide that angle or jurisdiction
confirmation is required and does not provide generic preferred options. Codex
must make that semantic determination from the actual matter. When confirmation
is materially required, generate fact-specific options, use native Plan-mode
choices when available, or ask in chat and wait.

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

After deterministic inspection, read `prompt_recipe.json["lawyer_intake"]` as
a decision boundary. It intentionally contains no keyword-generated intake
questions or document options. Generate any question from the user's facts and
ask only when the answer would materially change the work.

The intake should feel like a lawyer narrowing the case:

- explain the selected or assumed angle when it helps the user understand the
  answer plan;
- ask the missing facts that change legal analysis, deadlines, evidence, or
  output format;
- explain why each question matters in one short clause;
- avoid generic administrative questions when the answer can be inferred;
- keep the fast path available by stating assumptions and caveats.

## Core Principle

Codex owns the reasoning and instruction writing: professional intent,
generation route, document type, research posture, objective, scope, source
strategy, fact summary, and final wording.

Deterministic Python code owns only question inventory, exact anchor checks,
answer-contract and semantic-review record shape validation, prompt-control
presence checks, cross-field consistency, and packaging. Codex owns prompt-to-
question and prompt-to-contract semantic conformance. Deterministic code must not
select a legal domain, generation route, document type, jurisdiction, audience,
source strategy, or validation posture. Plugin scripts must not make direct OpenAI API calls
or other model API calls.

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
- desired document type or generation route when the user has already chosen
  one.

## First Run Workflow

1. Ask for the question text only if it is missing. Do not ask whether to
   optimize it. Infer working language, jurisdiction, posture, objective,
   scope, document type, and generation route semantically when they are clear.
   Ask only about a consequential ambiguity.
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

5. Read `question_inventory.json` and `prompt_recipe.json`. Treat dates,
   amounts, percentages, URLs, entity strings, explicit questions, and legal-
   framework mentions as inventory. Treat posture, objective, scope, legal
   topic, phasing, document type, route, and source strategy as model-led
   decisions. The recipe's confirmation records say only that deterministic
   inspection did not make those decisions.
6. Understand the question semantically and choose the research angle,
   document type, generation route, audience, purpose, framework, evidence
   display, validation scope, and source strategy. Ask only when an unresolved
   choice would materially change the answer.
7. If confirmation is materially required, generate choices from the actual
   facts. In Plan mode, prefer `request_user_input`; otherwise ask in chat and
   wait. Do not use generic keyword-generated choices.
8. Proceed with explicit assumptions and caveats when the matter is clear
   enough to answer. The default journey is question to answer to validated
   answer, without requiring the user to manage the optimizer.
9. Write `draft_answer_contract.json` in Codex. It must contain:
   - `schema_version`: `1.0`;
   - `question_domain`: `legal`, `tax`, `compliance`, or `mixed`;
   - `generation_route`: `codex_direct`, `chatgpt_deep_research`, or
     `external_document`;
   - free-text `document_type`, `purpose`, `audience`, `output_language`, and
     `jurisdiction`;
   - `jurisdiction_status`: `confirmed`, `assumed`, `unresolved`, or
     `not_applicable`;
   - `evidence_display`: `inline_citations`, `footnotes`,
     `source_record_only`, `mixed`, or `not_specified`;
   - `validation_profile`: `source_identity_support_reasoning_and_judgment`;
   - `validation_scope`: `all_material_claims`, `selected_material_claims`, or
     `limited`;
   - `correction_policy`: `correct_when_supported` or `review_only`;
   - `judgment_policy`: `flag_for_professional_review`.
   These values are model-led or user-confirmed; helper scripts only validate
   their shape.
10. Write the optimized answer-generation instructions in Codex. They must
   preserve all material facts, dates, percentages, amounts, entities,
   chronology, and explicit questions. Include the selected document type,
   audience, purpose, source hierarchy, citation or source-record rules, and
   the research lens when research is required. If Codex judges that the
   matter needs a phased workflow, include chronology, confidence,
   legal-realism, specialist scope-control, and anti-fabricated-authority
   instructions.
11. Save the draft instructions in the work folder as `draft_prompt.md`.
12. Semantically review `draft_prompt.md` against the source question and
    `draft_answer_contract.json`. Write `draft_prompt_contract_review.json`
    with `schema_version: 1.0`,
    `review_method: model_led_semantic_conformance_review`, an assessment for
    every required dimension, `overall_status`, and `reviewer_action`. The
    required dimensions are `question_and_material_facts`, `generation_route`,
    `document_type`, `purpose`, `audience`, `output_language`, `jurisdiction`,
    `evidence_display`, `research_lens`, `validation_policy`, and
    `source_strategy`. Every dimension must be `conforms` before delivery.
13. Curate qualified source websites from the confirmed framework and actual
    issue, then save them in the work folder as
    `draft_source_domains.txt`. Do not copy domains from
    `prompt_recipe.json["source_domains"]`; that field is intentionally empty.
14. Run deterministic validation:

```bash
python scripts/validate_prompt.py <question-file> <output-dir>/draft_prompt.md --output-dir <output-dir> --language <auto|it|en|fr|de|es> --source-domains-file <output-dir>/draft_source_domains.txt --answer-contract-file <output-dir>/draft_answer_contract.json --prompt-contract-review-file <output-dir>/draft_prompt_contract_review.json
```

15. Read `prompt_audit.json`. If any check fails, repair
   `draft_answer_contract.json` or `draft_prompt.md` in Codex, rerun the
   model-led prompt-contract review, and then rerun validation. Literal
   explicit-question overlap is observational, not gating; exact missing dates,
   amounts, percentages, URLs, and legal-form entity names are gating.
16. Deliver `answer_contract.json`, `optimized_prompt.md`,
   `prompt_contract_review.json`,
   `source_domains_comma.txt`, `source_domains.txt`, `prompt_package.md`,
   `README_HUMAN.md`, and `prompt_audit.json`. For
   `chatgpt_deep_research`, provide the ChatGPT-window handoff. For
   `codex_direct`, use the instructions to generate the answer in Codex and
   continue directly to answer validation.

## Prompt Requirements

The optimized prompt must require:

- a professional role aligned with the question;
- a user-facing jurisdiction assumption notice that distinguishes output language from legal jurisdiction;
- a clear research posture, objective, and scope;
- a selected or assumed output format;
- an explicit generation route and answer contract;
- an explicit validation scope, correction policy, and professional-judgment
  policy for the later answer review;
- source hierarchy favoring primary legislation, case law, official tax/administrative guidance, court portals, EU/international official portals where relevant, and professional doctrine;
- a model-curated source hierarchy and an instruction to use the separate qualified website list;
- source traceability appropriate to `evidence_display`; require numeric
  citations and a final source section for research outputs, but permit a
  source-backed internal validation record when the intended letter should not
  display citations;
- official, stable URLs and broken-link replacement or flagging;
- cross-checking substantive claims against independent references;
- explicit residual uncertainty;
- no loss of source facts, numbers, dates, ownership percentages, entities, steps, chronology, or explicit questions;
- up to three clarifying questions only when essential facts are missing;
- a structure appropriate to the contracted document type, audience, and
  purpose.

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
- `answer_contract.json`;
- `optimized_prompt.md`;
- `prompt_contract_review.json`;
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

`draft_answer_contract.json`, `draft_prompt.md`,
`draft_prompt_contract_review.json`, and `draft_source_domains.txt` are
temporary working files during validation, not delivered outputs.

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
   `prompt_contract_review.json`, source-domain sidecars, `prompt_package.md`,
   and `README_HUMAN.md`.
5. When the reviewer records actions in the widget or Codex collects decisions
   through fallback review, call `save_prompt_optimizer_decisions` so
   `ui_decisions.json` is validated and persisted. When the reviewer is done,
   call `apply_prompt_optimizer_decisions` so `applied_decisions.json` and
   `final_artifacts.json` reflect accepted, edited, unclear, skipped, or
   document-requested items before treating the prompt package as reviewed.
   An edit to `optimized_prompt.md` invalidates the prior semantic conformance
   review. Rerun that model-led review and validation before final handoff.

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
IT: Pianifica la risposta a questo quesito legale o fiscale. Lingua output: it. Comprendi semanticamente l'intento, proponi tipo di documento e percorso di generazione, conferma solo le scelte professionali irrisolte che cambiano materialmente la risposta, scrivi answer_contract.json e istruzioni complete per la generazione, quindi valida la forma del pacchetto.
EN: Plan the answer to this legal or tax question. Output language: en. Understand the intent semantically, propose the document type and generation route, confirm only unresolved professional choices that materially change the answer, write answer_contract.json and complete generation instructions, then validate the package shape.
FR: Planifie la réponse à cette question juridique ou fiscale. Langue de sortie: fr. Comprends l'intention sémantiquement, propose le type de document et le parcours de génération, confirme uniquement les choix professionnels non résolus qui changent matériellement la réponse, rédige answer_contract.json et les instructions complètes de génération, puis valide la forme du paquet.
DE: Plane die Antwort auf diese Rechts- oder Steuerfrage. Ausgabesprache: de. Erfasse die Absicht semantisch, schlage Dokumenttyp und Generierungsweg vor, bestätige nur ungeklärte professionelle Entscheidungen, die die Antwort wesentlich ändern, erstelle answer_contract.json und vollständige Generierungsanweisungen und validiere anschließend die Paketstruktur.
ES: Planifica la respuesta a esta cuestión jurídica o fiscal. Idioma de salida: es. Comprende semánticamente la intención, propón el tipo de documento y la ruta de generación, confirma solo las decisiones profesionales no resueltas que cambien materialmente la respuesta, redacta answer_contract.json y las instrucciones completas de generación y valida después la forma del paquete.
```

## Failure Modes

- If the source question is empty, ask the user for the question before running scripts.
- If deterministic validation flags missing fact anchors, repair the prompt rather than dismissing the warning.
- If a source question asks for a legal, tax, or compliance answer directly,
  treat it as the start of the question-to-validated-answer journey. Do not ask
  the user to request prompt optimization.
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
