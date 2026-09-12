# Choose how to research the answer

Use this handoff for the invoking product's `quesito-legale-fiscale` journey. It changes the
second stage, research and answer generation. Validation follows both routes;
the adversarial stage follows only when the separately recorded
`adversarial_policy` is `required`. Apply
`adversarial-scope.md` independently of
the research-mode choice.

## One choice after preparation

Prepare the question, material facts, jurisdiction, source posture, audience
and requested output first. Before finalizing the generation route in the
answer contract or beginning substantive answer research, check whether the
host exposes OpenAI's installed `deep-research` skill. Use the current skill
catalog; do not assume it is installed or available on every host.

When available, ask once in the conversation language, using an available and
permitted native question tool or ordinary chat:

> Ho preparato il quesito. Vuoi svolgere la ricerca e la stesura della risposta
> con Deep Research, oppure proseguire con la ricerca ordinaria?

Options: **Deep Research** / **Ricerca ordinaria**. In English:

> The question is prepared. Would you like Deep Research to research and draft
> the answer, or continue with ordinary research?

Options: **Deep Research** / **ordinary research**. Localize the same choice
in French, German or Spanish. Do not promise greater accuracy, a particular
model, a fixed duration or price. Explain the two routes only as needed.

Wait for the choice before generation; silence is not a selection. Reuse an
explicit choice already made for this answer, including a request for Deep
Research or ordinary research. Do not ask again when resuming the same answer.
Do not make the choice a permanent preference for unrelated future matters.

## Execute the selected route

- **Deep Research plugin:** record `generation_route: deep_research_plugin`.
  Read and follow the installed OpenAI `deep-research` skill using the host's
  supported skill access. Carry `optimized_prompt.md`, `answer_contract.json`,
  the curated source list and the already selected case material into that
  research. Keep the confirmed jurisdiction, audience, language, scope and
  source restrictions. Ask only for material information still missing; do
  not repeat the completed intake. The user's contracted artifact and length take
  precedence over the research skill's default report format and length.
  Use only available, authorized sources and tools. Do not create a new task,
  change models or settings, or transfer the case to another account merely
  because this skill is selected.
- **ordinary research:** record `generation_route: codex_direct`, generate
  from the same brief with available source tools, and continue the journey.

Retain the actual generated answer and source record with the answer contract.
With local tooling, keep the finalized preparation in its Studio Archive run
and import the resulting answer into the same engagement's validation run.
Record the selected route and model-visible research material in the run's
model-data report. Without local tooling, retain the same context in chat and
state which durable artifacts were not created. Once the answer is available,
resume `deep-research-validator`. An informational assignment with
`adversarial_policy: not_required` finishes with that reviewed answer. Run
`adversarial-opinion` only with `required`; choosing Deep Research does not
activate it. An unvalidated research report is not completion of either path.

## Availability and the separate ChatGPT handoff

If the plugin is unavailable and the user has not requested it, continue the
ordinary route and state that the installed-plugin option is unavailable in
this session. If the user chose Deep Research but it is unavailable or fails,
report the actual limitation and ask whether to use ordinary research or the
separate ChatGPT handoff. Do not silently relabel ordinary research as Deep
Research or switch to another account.

`chatgpt_deep_research` remains the separately chosen ChatGPT-window route
described in the resolved Prompt Optimizer component skill. Its manual handoff and destination-account choice
do not apply merely because the installed plugin runs in the current host.
Do not claim a native ChatGPT Deep Research job was started, monitored or
retrieved without a callable tool that actually performed that operation.
