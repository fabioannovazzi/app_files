# Prompt Optimizer versus FiscalPrompt benchmark protocol

This benchmark compares two prompt strategies on the same synthetic Italian tax
cases:

- `optimize_prompt`: the full Prompt Optimizer planning and answer journey;
- `fiscalprompt`: the case-matched template extracted from the user's purchased
  FiscalPrompt PDF and applied to the same facts.

The benchmark measures prompt quality, final-answer quality, and execution cost.
It does not treat fluent output, prompt length, deterministic checks, or a model
judge alone as evidence of tax correctness.

## Evidence and copyright boundary

The purchased PDF is an external benchmark input. Do not add the PDF, extracted
text, or template excerpts to git. Preparation refuses a PDF or output directory
inside this repository. It records the PDF hash and writes the selected template
text only under the external benchmark output root.

The committed cases are synthetic and original. They contain no client data and
do not reproduce FiscalPrompt wording.

## Experimental controls

The suite contains eight cases and two repeats per case, producing 16 paired
comparisons and 32 fresh builder runs. Within each pair:

- both treatments receive the identical case facts and `as_of_date`;
- both use the same model and reasoning effort in fresh ephemeral sessions;
- both ignore user configuration and disable automatic plugin and skill discovery;
- treatment launch order is randomized and the pair runs concurrently;
- neither treatment may inspect the other treatment or another run;
- Prompt Optimizer receives no FiscalPrompt text;
- FiscalPrompt receives only its matched extracted template and may not inspect
  Prompt Optimizer;
- both must write `answer.md`, `prompt_used.md`, and `sources.json` under their
  isolated result directory.

The comparison is end-to-end. Prompt Optimizer therefore carries the cost of its
planning, prompt generation, source controls, and answer generation. FiscalPrompt
carries the cost of applying its static template and generating the answer.
Cost is reported, but it cannot compensate for a quality regression.

## 1. Prepare the non-billable plan

Use the repository virtual environment and an output directory outside git:

```bash
cd ~/Documents/GitHub/app_files
source .venv/bin/activate
python plugins/prompt-optimizer/scripts/run_fiscalprompt_benchmark.py \
  --pdf /absolute/path/to/FiscalPrompt_Ver3_merged.pdf \
  --output-root /private/tmp/prompt-optimizer-fiscalprompt-benchmark
```

Preparation requires Poppler's `pdftotext`. It locates only the template IDs
declared by the suite, verifies the standard template sections, seals each task,
and writes `benchmark_plan.json`. Inspect that plan before authorizing paid model
runs. Preparation does not call a model.

## 2. Execute the prepared paired runs

Execution is a separate command so the plan can be reviewed first:

```bash
source .venv/bin/activate
python plugins/prompt-optimizer/scripts/run_fiscalprompt_benchmark.py \
  --output-root /private/tmp/prompt-optimizer-fiscalprompt-benchmark \
  --execute \
  --model gpt-5.6-sol \
  --reasoning-effort xhigh
```

The runner verifies that the suite, Prompt Optimizer skill, sealed task bytes,
and task links have not changed. It retains Codex JSONL, stderr, token use, wall
time, tool counts, artifact hashes, and exact fact-anchor presence. It then
creates one blinded A/B packet per case and repeat.

The Prompt Optimizer treatment reads the exact candidate skill path recorded in
the sealed instructions. Automatic plugins and skill discovery remain disabled
for both treatments so globally installed skills cannot contaminate the baseline.

If a run fails or an artifact is missing, do not repair the artifact manually.
Record the failure and prepare a new benchmark output root for a rerun.

## 3. Collect independent blinded reviews

Each directory under `review_packets/` contains:

- the synthetic case;
- `prompt_A.md` and `prompt_B.md`;
- `answer_A.md` and `answer_B.md`;
- hash-bound review instructions;
- `review_template.json`;
- an empty `reviews/` directory.

Reviewers receive only their packet. They must not receive
`benchmark_runs.json`, builder logs, or the private label mapping.

Every packet requires:

1. one independent model review in a fresh thread; and
2. one independent Italian tax-professional review.

The builder may not review its own outputs. Reviewers score raw A/B labels from
1 to 5 and record hard failures with evidence. They must not guess which system
produced A or B. Copy each completed review JSON into the packet's `reviews/`
directory without changing the packet ID or artifact hashes.

Tax correctness, issue coverage, source relevance, and uncertainty calibration
are semantic judgments. Deterministic code validates score shape and evidence
bindings, but it does not generate or overrule those judgments.

## 4. Summarize after review completion

```bash
source .venv/bin/activate
python plugins/prompt-optimizer/scripts/summarize_fiscalprompt_benchmark.py \
  --suite plugins/prompt-optimizer/evals/fiscalprompt_benchmark_suite.json \
  --runs /private/tmp/prompt-optimizer-fiscalprompt-benchmark/benchmark_runs.json \
  --reviews-root /private/tmp/prompt-optimizer-fiscalprompt-benchmark/review_packets \
  --output /private/tmp/prompt-optimizer-fiscalprompt-benchmark/summary.json
```

Exit codes:

- `0`: complete benchmark and Prompt Optimizer is non-inferior or superior;
- `1`: complete benchmark and Prompt Optimizer regressed;
- `2`: malformed or incomplete evidence.

The summarizer maps A/B labels only after validating reviewer independence and
artifact hashes. It reports paired weighted-score deltas, a deterministic 95%
bootstrap interval, win counts, hard failures, fact-anchor checks, tokens, and
duration.

No superiority claim is allowed until all 16 pairs have both required reviews.
The suite calls superiority only when the mean answer-score improvement reaches
0.20 points and the lower bootstrap bound is positive. A quality regression or
additional hard failure cannot be offset by lower cost.

## Interpretation limits

- This is a comparative product benchmark, not tax assurance.
- Synthetic cases improve control but do not capture every studio workflow.
- Open-web research can change as official sources and law change; the case
  `as_of_date`, URLs used, and raw run evidence must be retained.
- Pairwise model review is useful for consistency and structure, but the
  tax-professional review is mandatory for substantive conclusions.
- A result applies to the exact Prompt Optimizer skill hash, FiscalPrompt PDF
  hash, model, reasoning effort, and run date recorded in the evidence.
