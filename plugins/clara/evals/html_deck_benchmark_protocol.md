# Clara HTML deck controlled benchmark protocol

This protocol compares HTML and PPTX creation and revision without allowing one
format run to inherit the other run's reasoning. The suite file is the contract;
the runner is the evidence producer. Agent-authored `run_report.json` files are
not accepted as benchmark evidence.

## 1. Prepare and verify sealed inputs

The runner resolves the fixture root from `--fixture-root`, then from
`CLARA_DECK_BENCHMARK_FIXTURE_ROOT`, then from the suite default. It verifies
every source file against its SHA-256 and verifies the canonical source
manifest fingerprint. It separately verifies the sealed baseline-evidence
manifest, which binds the historical experiment summaries, artifacts, HTML
support files/assets, and historical renders. Baseline evidence is never copied
into a candidate work directory.

Each run receives a format-specific rewritten specification. It includes only
that format's target and, for revision, only that format's baseline. Common
source assets are copied beside the task specification at their relative
`assets/...` paths. The opposite format's paths and bytes are absent.

The rewritten task tree is stored outside the writable Codex working directory,
made read-only, and exposed inside the run through a `task` symlink. A canonical
manifest binds every directory and file, including the specification, assets,
amendments, and revision baseline. The runner verifies the link and complete
tree immediately before launch, immediately after Codex returns, and again
before mechanical checks. Any mutation or replacement aborts evidence
production; mechanical checks always read the trusted external task tree.

Before preparation, the runner verifies the installed and source candidate
identities. The suite binds the Clara version, Clara HTML `SKILL.md` hash, Clara
plugin-manifest hash, and deterministic Clara runtime-tree hash. It also binds
the Presentations runtime version/path, `SKILL.md` hash, and full Presentations
skill-tree hash, including its renderer and authoring tools. A missing, stale,
or mismatched source/cache candidate stops the run before Codex is launched.

Preparation is non-billable:

```bash
source .venv/bin/activate
python plugins/clara/scripts/run_clara_deck_benchmark.py \
  --output-root <repo-root>/output/clara_html_deck_eval_20260714
```

The command fails if the output directory already exists, preventing accidental
reuse. Inspect `benchmark_plan.json` before execution. For each case the HTML
and PPTX prompts have the same normalized SHA-256; the literal prompts differ
only at `TARGET_FORMAT`.

## 2. Execute fresh paired runs

Run the paid evaluation only after the candidate Clara plugin is installed:

```bash
source .venv/bin/activate
python plugins/clara/scripts/run_clara_deck_benchmark.py \
  --output-root <repo-root>/output/clara_html_deck_eval_20260714 \
  --model gpt-5.6-sol \
  --reasoning-effort xhigh \
  --execute
```

Because preparation refuses an existing directory, use a new output path when
moving from a dry run to execution. The runner launches HTML and PPTX
concurrently inside each case, pins the model and reasoning effort with explicit
Codex CLI overrides, uses `--ephemeral`, and gives each run a distinct working
directory. Creation completes before the revision pair begins; no candidate run
uses another candidate artifact as its revision baseline.

Raw Codex JSONL and stderr are retained in each run directory. The runner reads
input, cached-input, and output token usage plus tool-call events from JSONL,
measures wall time itself, hashes the event log and artifacts, audits tool
commands for forbidden fixture or opposite-format paths, and performs
mechanical artifact checks independently. Non-cached cost is reported as
`input_tokens - cached_input_tokens + output_tokens`; total tokens remain
`input_tokens + output_tokens`.

Candidate-supplied PNGs are never benchmark evidence. HTML is independently
rendered with Playwright Chromium after Clara validation and browser QA in the
narrow `--profile static` compatibility mode. PPTX is independently rendered
with the installed Presentations renderer. Both must produce two exact
1280×720 slides. After all candidates are complete, the runner re-renders each
sealed baseline with the same current renderer. Historical PNGs remain sealed
audit evidence only. Missing artifacts, malformed usage, or renderer failures
abort record production.

## 3. Conduct blinded semantic review

The runner writes a separate review packet for every case and format. Each
packet randomly assigns current-renderer candidate and baseline slides to `A`
and `B`; the private mapping remains in runner protocol evidence and is not
copied into the packet. The packet also contains a hash-bound review prompt and
response template. Give reviewers only the packet directory, never
`candidate_runs.json`, builder logs, or the private mapping.
Each packet also includes a hash-bound neutral `source_requirements.json`, the
task brief, amendments, and any common source assets so source fidelity can be
judged without disclosing the A/B mapping.

Collect one independent model review per packet. The reviewer thread ID must
differ from the builder thread ID. A genuine blinded human review is useful but
optional; never fabricate one. Each review must bind the packet ID, review
prompt hash, reviewer identity/thread, both artifact hashes, both current
render-set hashes, and raw 1–5 scores, pass decisions, and rationales under the
unchanged `A` and `B` labels for:

- source fidelity;
- narrative quality;
- visual hierarchy;
- decision usefulness.

Copy completed label-based records into `candidate_runs.json` under
`semantic_reviews`; do not manually translate A/B into candidate/baseline.
Semantic judgements remain model/human-led. The summarizer validates the review
contract and bindings, applies the runner-held private mapping, and derives
candidate-versus-baseline non-regression deterministically from those raw label
scores.

## 4. Summarize against the sealed baseline

```bash
source .venv/bin/activate
python plugins/clara/scripts/summarize_html_deck_benchmark.py \
  --suite plugins/clara/evals/html_deck_capability_benchmarks.json \
  --runs <repo-root>/output/clara_html_deck_eval_20260714/candidate_runs.json \
  --output <repo-root>/output/clara_html_deck_eval_20260714/summary.json
```

Exit `0` means every protocol control, mechanical check, semantic
non-regression gate, and cost target passed. Exit `1` is a valid failing
experiment. Exit `2` means the suite or evidence is malformed. The summarizer
rejects duplicate/missing matrix entries, unsealed sources, mismatched artifact
or render hashes, self-reported controls, non-finite values, fractional count
fields, reused builder/reviewer threads, and incomplete review packets.

The 30% HTML target is conjunctive: both median total-token improvement and
median duration improvement versus the sealed historical figures must reach the
threshold. Per-mode HTML-to-PPTX token and duration ratios are separate gates;
one cannot compensate for the other. Because raw JSONL from the historical runs
is unavailable, historical comparisons are directional and bound to preserved
summaries. The primary format comparison is the current runner-derived HTML and
PPTX pair under identical controls.
