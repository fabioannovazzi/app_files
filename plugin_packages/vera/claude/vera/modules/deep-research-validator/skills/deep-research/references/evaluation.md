> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Evaluate complete answers, not record completeness

Use `evals/research_loop_cases.json` from the resolved component root for
synthetic exercises. Its authorities are fictional: do not research them on
the public web or reuse them as professional law. Give the execution context
only the assignment, supplied materials and any specified provisional position;
keep reviewer expectations separate. Introduce a specified final-review finding
only at final review so reopening is exercised.

Run both product adapters against the same materials and retain actual issue
histories, queried/read material, answer revisions, final reviews and artifacts.
Evaluate the delivered answer and treatments against the supplied evidence,
not by checking that particular words or fields appear. Record defects,
untreated issues, unsupported certainty, lost qualifications, factual invention,
failure to revisit dependent claims and forced opposition. A coherent alternate
interpretation can be appropriate without invalidating the original.

For a quality comparison, retain standard Claude's output and the earlier pipeline's output on the same
assignment and have a professional review both outputs without workflow labels.
Assess authority/version accuracy, material issue coverage, source entailment,
reasoning, opposing-case quality, uncertainty and usefulness of the requested
document. Repeat representative real legal/tax cases with authorized materials;
synthetic exercises alone cannot establish professional quality.

Unit and package tests establish record integrity, managed-path enforcement and
shared bytes across hosts. They do not establish semantic research quality,
installed-host acceptance or superiority over the earlier method. Record only
evaluations actually executed; never convert filled records or repeated model
agreement into a claim that the best possible answer was achieved.

Use `scripts/research_evaluation.py` to retain executed runs. This developer
helper does not run research or grade answers. Its `record` command takes
`--root` and `--specification`; `verify` takes `--run`; `assess` takes `--run`
and `--assessment`; `compare` takes repeated `--run` and `--output-dir`.
Consult `--help` for each action. Do not call a prepared specification a run.

The specification records `evaluation_id`, `case_id`, `workflow` (`vera`,
`lucia`, `standard_codex`, or `previous_pipeline`), `evaluation_kind`
(`fixed_source_reasoning` or `authority_discovery`), `trace_limits`, and
`artifacts`: a list of actual relative `path` and `role` objects. Every run
requires assignment, final_answer, host_configuration and execution_evidence.
Optional materials use role `material`. Plugin runs also require plugin_package
(the exact installed product ZIP), research_history, final_review and
source_inventory, with all inventoried original/text files as source_capture.
Preserve answer_revision artifacts, actual searches and read material when
available; document missing trace explicitly. Retention copies exact bytes,
version, package hash, host configuration and timestamps into an immutable run.

Host configuration records the observed `host`, `model`, `research_date`,
`research_tools` and `configuration_observation`, plus
`observed_plugin_version` for a plugin run. A standard Claude baseline records
`specialist_plugins_exposed: []`; run it in a separate clean context with the
same assignment/materials, model, tools and research date. File hashes cannot
prove that this configuration was active or that a supplied transcript is true.
Retain actual host evidence and record observation limits.

An actual assessor submits `reviewer`, `reviewer_role`, `assessment`,
`workflow_label_known` and `final_answer_sha256` for the delivered bytes. Assess source
entailment, authority/version accuracy, issue coverage, dependent reasoning,
uncertainty, opposition and professional usability. Assessment never rewrites
the original run. `compare` rejects unequal assignments, materials, models,
tools, dates or evaluation kinds and exports opaque randomized identifiers
under `assessor/`; keep `private_mapping.json` from raters. Answer content can
reveal a workflow: preserve it faithfully and record recognition. A retained
run, a hash check or a blinded export does not establish superior quality.
