---
name: prompt-optimizer
description: Use internally when Vera or Claude receives a legal, tax, or compliance question and must define the answer contract, choose a model-led generation route, and prepare source-backed generation instructions. The user does not need to ask for prompt optimization. Do not use for unrelated copywriting or ordinary prompt polishing.
---

## Cowork execution contract

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, report-builder and check-entries only, optional cache
cleanup is available from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
If `validate_implementation_tree` ever fails with a file/directory-contract
mismatch, do not delete or modify files inside the installed plugin tree by hand
and do not bypass a sandbox/permission rejection to do so. Stop and report the
exact error instead.

Work from the connected folder and supplied files first. Before a module's Python
helpers, locate the installed plugin root. When it contains `components.json` and
`scripts/managed_python_runtime.py` (as Vera does), run from that root:

```bash
python3 scripts/check_dependencies.py --module <module>
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

If the enclosing plugin does not ship this managed launcher, use the module's
dependency checker and only already-installed dependencies; do not assume that a
standalone module script provisions them.

The managed launchers provision and reuse an isolated environment containing only the
module's published requirements. This declared dependency setup is authorized as
part of running the workflow; never install arbitrary packages or use ambient
Python for subsequent module helpers. Repeat any declared `--requirements` options
on both commands. Missing ambient imports are a reason to run this setup, not to
abandon the calculation. If setup fails, report its exact error and do not replace
the required calculation with an invented result. Optional OCR setup still needs
separate approval. If setup reports `Host not in allowlist` for PyPI, explain that
Claude Settings > Capabilities > Allow network egress is disabled or restricted.
Ask the user or organization administrator to authorize package-registry access;
never change network permissions silently or work around the restriction. Retry
the same managed setup after access is approved, in a new session if needed.

MCP tools, browser or computer control, and local review servers are optional
enhancements, never completion gates. Cloud Cowork sessions may not expose local
plugin MCP servers even when the plugin is installed; use the packaged Python
workflow through the managed launcher in that case. Do not equate missing MCP
registration with a failed calculation engine. When an optional capability is
unavailable, continue with Markdown and file-based review and state the limitation.

The normal Cowork deliverable is a reviewable draft, artifact card, and
source/review files. A callable persistence interface may optionally record or
apply reviewer actions, but its absence never blocks delivery. Never claim
`applied` or `final_ready` unless corresponding persisted artifacts prove it;
otherwise report that professional review remains pending.

Use host-neutral user-facing artifact names. Name assistant-authored review
folders and files for Vera or their professional purpose (for example,
`vera-review/`, `vera_phase1_synthesis_reviewed.md`, and `run_review.md`).
Never put host, platform, or model-provider names in assistant-authored
user-facing artifact paths, document headings, field labels, narrative text,
or status summaries. Describe execution routes generically, such as
`external review route`, `connected tool`, or `local review interface`.

Derive any run ID, status, artifact count, or package hash quoted in an
assistant-authored supplement from the final delivered manifests.
After any rebuild, regenerate or resynchronize those supplements before
delivery. When a workflow ships a complete-delivery validator or sealer, run it
against the exact connected-folder copy after the last write.
In this contract, the base package validator alone does not validate extra
narrative files.

When a workflow declares owner-only or private output and uses a private scratch
directory before copying the final package into the connected folder, reapply
the privacy modes after that transfer: `0700` for the package root and every
directory, and `0600` for every file. Verify the connected-folder tree with
`stat` or `lstat` before claiming completion. If the host filesystem cannot
preserve those modes, do not claim owner-only delivery; keep the package in the
private scratch location or report the limitation and ask for a safer
destination.

Do not use WhatsApp, live INPS browser capture, hosted feedback or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract.

## Output Location Rule

Never write run outputs inside this Git workspace or a published folder. Use
only the Studio Archive run path described below.

## Client engagement gate

Select one Studio Archive client and engagement, import or materialize the
question in its managed inputs, then call `prepare_studio_client_workflow` with
workflow ID `prompt-optimizer`. Pass the returned `client_engagement_path` as
`--client-engagement` to inspection and validation. Cross-engagement inputs
and arbitrary outputs are rejected.

Start the prepared run before inspection. After the last output write, call
`finalize_studio_client_workflow` and declare every physical file with a stable
artifact ID, relative path, concrete purpose, audience, and media type. Review
the closed declaration, then call `complete_studio_client_workflow`; record
`failed` or explicitly cancel an abandoned run instead of treating a partial
directory as a result.

# Plan The Answer

Use this skill as the internal planning stage of Vera's question-to-validated-
answer journey. Claude inspects the question, confirms only essential
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

Claude owns complexity and phasing judgment. Do not rely on deterministic topic
flags to decide whether a matter is broad. When Claude determines that a broad or
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

## Cowork-native Run UX

Keep the interaction conversational. The user can speak naturally to Claude;
Claude should respond like a careful lawyer doing intake. Do not recreate the
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
host/user controlled. Claude may ask the user to switch to Plan mode for
structured intake, but it cannot programmatically enter or leave that mode.

Run UX:

1. First check semantically whether there is a material research-angle decision: the
   controlling frame, decision lens, risk appetite, scope boundaries, audience,
   or source posture. Ask the choice in chat when a material research-angle
   decision is still unresolved.
2. Treat `angle_confirmation.required` and
   `jurisdiction_confirmation.required` as non-decisions from the inspection
   layer. Their normal value is `false` with decision owner `codex_or_user`.
   Claude—not keyword inspection—decides whether to ask.
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
confirmation is required and does not provide generic preferred options. Claude
must make that semantic determination from the actual matter. When confirmation
is materially required, generate fact-specific options, use native Plan-mode
choices when available, or ask in chat and wait.

For repository-wide Claude UX compatibility, map the standard artifacts to this
conversational flow: a checklist can be a short progress note; a Run Intake table
and Decision Table are optional compact summaries when the facts are complex;
an execution checkpoint can state command intent, output folder, and expected
artifacts before long-running or write-heavy steps; ask for approval only when
the step is external, destructive, approval-sensitive, or still depends on an
unresolved material choice. An Artifact Card can be the final concise list of
generated outputs and review status. If a run produces many files, create
`run_review.md` in the output folder. Do not edit generated ZIPs during a
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

Claude owns the reasoning and instruction writing: professional intent,
generation route, document type, research posture, objective, scope, source
strategy, fact summary, and final wording.

Deterministic Python code owns only question inventory, exact anchor checks,
answer-contract and semantic-review record shape validation, prompt-control
presence checks, cross-field consistency, and packaging. Claude owns prompt-to-
question and prompt-to-contract semantic conformance. Deterministic code must not
select a legal domain, generation route, document type, jurisdiction, audience,
source strategy, or validation posture. Plugin scripts must not make direct OpenAI API calls
or other model API calls.

The user should not interact directly with CLI scripts. Treat scripts as internal tools Claude runs on behalf of the user.

## Qualified Source Domains

The old web workflow produced a copyable list of reliable websites for Deep
Research. Preserve that behavior in the plugin.

Do not use deterministic source-domain selection. Claude must curate any
"Qualified source domains" list from the confirmed legal framework and the
actual issue. Do not copy domains from `prompt_recipe.json["source_domains"]`;
that field is intentionally empty for legal prompts.

Validation writes `source_domains.txt` next to the optimized prompt for
backward-compatible packaging and `source_domains_comma.txt` for Deep Research
website fields that require comma-separated URLs. Deterministic validation must
not choose legal source domains; Claude must curate the list and pass it as a
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
python scripts/inspect_question.py <managed-question-file> --client-engagement <client_engagement_path> --output-dir <client-run-output> --language <auto|it|en|fr|de|es>
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
9. Write `draft_answer_contract.json` in Claude. It must contain:
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
10. Write the optimized answer-generation instructions in Claude. They must
   preserve all material facts, dates, percentages, amounts, entities,
   chronology, and explicit questions. Include the selected document type,
   audience, purpose, source hierarchy, citation or source-record rules, and
   the research lens when research is required. If Claude judges that the
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
python scripts/validate_prompt.py <managed-question-file> <client-run-output>/draft_prompt.md --client-engagement <client_engagement_path> --output-dir <client-run-output> --language <auto|it|en|fr|de|es> --source-domains-file <client-run-output>/draft_source_domains.txt --answer-contract-file <client-run-output>/draft_answer_contract.json --prompt-contract-review-file <client-run-output>/draft_prompt_contract_review.json
```

15. Read `prompt_audit.json`. If any check fails, repair
   `draft_answer_contract.json` or `draft_prompt.md` in Claude, rerun the
   model-led prompt-contract review, and then rerun validation. Literal
   explicit-question overlap is observational, not gating; exact missing dates,
   amounts, percentages, URLs, and legal-form entity names are gating.
16. Deliver `answer_contract.json`, `optimized_prompt.md`,
   `prompt_contract_review.json`,
   `source_domains_comma.txt`, `source_domains.txt`, `prompt_package.md`,
   `README_HUMAN.md`, and `prompt_audit.json`. For
   `chatgpt_deep_research`, provide the ChatGPT-window handoff. For
   `codex_direct`, use the instructions to generate the answer in Claude and
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

When Claude determines that the matter is broad or multi-specialist, the
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

## Cowork review handoff

The normal Cowork completion point is delivery
of the reviewable draft, artifact card, and source/review files in the connected
folder. Review those artifacts directly. Report the package as
`ready_for_professional_review` where that status exists, otherwise as
`pending_review`.

When a validated MCP tool, browser interface, or local workbench is callable, it
may optionally persist or apply reviewer actions. Its absence never blocks
delivery. Never claim `applied` or `final_ready` unless corresponding persisted
artifacts prove it. A file or chat review without those artifacts remains
pending professional review.

Review actions cannot waive a failed deterministic check. Keep failed checks,
missing evidence, unresolved decisions, and applicable blockers visible in the
artifact card and final response.

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
