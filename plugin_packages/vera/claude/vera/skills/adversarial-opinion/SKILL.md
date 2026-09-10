---
name: adversarial-opinion
description: Develop and review the strongest evidence-bound opposing case to a legal, tax, or compliance position in Vera's legal-opinion journey, independently of the original validation outcome, and compare both positions for the professional.
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

The managed launcher provisions and reuses one user-scoped CPython 3.12
environment per OS host with the published shared requirements, outside client
folders. Modules and products share this dependency environment; it does not
isolate client matters. This declared dependency setup is authorized as
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

# Adversarial Opinion

Run this distinct fourth stage after preparation, drafting, and validation in
`vera:quesito-legale-fiscale`. It is routine even when the original opinion is
well supported. Validation asks whether that opinion is supported; this stage
develops the strongest credible case for an incompatible conclusion. Use the
current model and selected runtime. A different model, separate agent, special
mode, or additional user confirmation is not a prerequisite.

For a supplied position, first use the legal-question journey to establish its
facts, scope and answer contract and review it. Keep `adversarial_policy` set to
`required` in the original answer contract. Do not apply this stage to other
Vera workflows merely because their output mentions law or tax.

## Develop the opposing case

1. Read the complete reviewed position, original facts and question, answer
   contract, source evidence and validation limits. State precisely which
   conclusion is challenged. Preserve the original question, jurisdiction,
   relevant dates and evidence posture. Clearly separate established facts,
   disputed facts and hypothetical facts; never invent a factual premise.
2. Choose the opponent's plausible perspective from the case, such as the
   counterparty or authority, when that perspective matters. Ask only if a
   consequential ambiguity remains. Seek competing authorities, exceptions,
   materially different readings of the same authorities or facts, and
   challenges to the original framing. Research beyond the original citations
   when needed within the authorized source boundary. Record the searches or
   sources actually examined and their findings.
3. Develop the strongest substantiated opposing conclusion as a coherent
   opinion, with the reasoning needed to get there. A list of defects, a
   rhetorical objection, or a negation of the original conclusion is not a
   counter-opinion. Identify the decisive premises, strongest evidence, and
   qualifications. Do not invent authorities, exaggerate weak objections, force
   symmetry, or assign unsupported probabilities of success.
4. Record one model-led outcome: `credible_counterposition`,
   `no_substantial_counterposition`, or `evidence_limited`. The second outcome
   requires a reasoned account of what was examined and why no substantial
   opposing case was found within that scope. It does not prove that no such
   case exists. Inaccessible decisive sources or missing facts remain explicit
   evidence limits, not proof of absence. Do not choose an outcome from the
   original validation result or from a fixed number of objections or searches.
5. Review the opposing opinion or reasoned negative result using
   `vera:deep-research-validator`: source identity and support, reasoning,
   qualifications, coverage and professional judgment. Correct supported
   defects. This is validation of the fourth-stage output, not a recursive
   request for another adversarial opinion. Preserve both review records.

## Compare and deliver

Write a concise comparison containing the original conclusion, opposing
conclusion, decisive differences, evidence that could change the assessment,
and choices requiring professional judgment. Review that comparison against
both opinions and the underlying sources. Keep substantive statements traceable
to the reviewed documents; research and validate any new material claim.

The original may remain unchanged despite a credible opposing case. If the
exercise exposes a defect requiring correction, identify it explicitly,
correct and revalidate the original when supported, then refresh the opposing
exercise against that exact version. Do not silently merge the opinions or
present a preferred legal strategy as an established fact. If missing evidence
or professional judgment prevents closure, preserve the partial package and
state what remains rather than looping or manufacturing a resolution.

Deliver the reviewed original, the reviewed opposing opinion or reasoned
negative/limited result, their source and validation records, and the comparison.
A client letter retains its requested form; the opposing opinion and comparison
are separate working documents for the professional. Final legal choices and
approval remain with the professional.

## Durable execution

When local run tooling is available, read
`references/durable-opinion.md` completely. Keep the two opinions in `position/`
and `adversarial/` under the **same** Studio Archive `deep-research-validator`
run. The planning run remains separate in that engagement. Do not finalize the
validation run after the original opinion alone. The helper's `prepare`,
`package`, and `verify` commands bind the exact position and both review records;
they do not generate or evaluate legal arguments.

When local tools are unavailable, complete the same substantive exercise in
chat with the available research capabilities. Show both positions, sources,
comparison and limits; state that no durable run or hash verification occurred.
If current-source research is unavailable, keep the result evidence-limited.

Include the original review, adversarial research/drafting, opposing review and
comparison as distinct model-visible phases in Vera's model-data report. They
can expose complete opinions, material case facts and selected source text to
the selected model runtime. The stage does not require a new provider account.

At delivery, include `vera:adversarial-opinion` in workflow provenance only when
this exercise actually ran. Follow Vera's existing feedback and reporting rules.
