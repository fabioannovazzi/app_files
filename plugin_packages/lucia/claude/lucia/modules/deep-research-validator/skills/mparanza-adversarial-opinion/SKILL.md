---
name: mparanza-adversarial-opinion
description: Develop and review the strongest evidence-bound opposing case when the invoking product is asked for an opinion on a concrete legal, tax, or compliance position or explicitly for an opposing opinion. Do not activate for informational research alone; when selected, run independently of the original validation outcome and compare both positions.
---

## Cowork execution contract

Select the exact files needed for this request. Folder access does not select
all its contents: if the task needs two files in a folder containing four, use
only those two. Resolve genuinely ambiguous choices with the user; reuse clear
choices without another confirmation.

Before parsing documents or creating a client, engagement or run, call
`check_studio_import_sources` with all selected paths on the actual importer
host. It needs no configured Archive and creates no records. If the MCP tool is
unavailable, use the packaged `check-import-sources --source-path <path>` CLI
through the maintained managed launcher on that same host (repeat the flag per
file). A cloud-shell `ls` is not proof of access by a computer-side importer.
Readable attachments, including `/mnt/user-data/uploads/` paths when the importer
can read them, continue directly without requiring a connected computer folder.

If files are unavailable, explain the cause immediately before creating anything:
"The file is in the chat, but the import tool looks for it on your computer."
Do not keep trying that same inaccessible path. Use this recovery sequence:

1. Inspect the host's actual callable file-transfer capabilities and the already
   connected folders. Reuse an authorized ordinary working folder outside the
   managed `Vera/engagements/.../inputs` tree. Offer **Add folder** from the **+**
   menu only when the current host offers it; otherwise explain the available
   connection method. Ask for a folder only if an accessible destination is needed.
2. With a supported bridge, copy only the selected original attachments to that
   folder as files. Compute each original SHA-256 through the host file tools.
   Do not recreate CSV text, convert encodings or line endings, relay document
   contents through model-authored tool arguments, guess a mount translation,
   overwrite a different file with the same name, or scan unrelated folders.
   A verified byte-for-byte copy may reuse its destination on retry.
3. Check the actual destination paths with `check_studio_import_sources`, passing
   `expected_sha256` as the original hashes in the same order as `source_paths`.
   The CLI takes one `--expected-sha256` per source. Archive hashes the destination
   locally and returns `ready=true` only when all supplied original hashes match.
   If no byte-preserving host transfer is available, say so and ask the user to
   save the original selected files to the accessible working folder; then verify
   them. Do not promise a bridge operation that is not callable.
4. Only after all selected sources are ready, select/create the client and
   engagement and import each through `import_studio_client_document` (CLI
   `import-document`). Pass that file's `expected_sha256` / `--expected-sha256`
   when a transfer was required. The importer checks it again during copying and
   creates the input ID and SHA receipt itself. Never manually populate `inputs`.

The path importer does not itself fetch chat attachments. Direct attachment use
requires actual importer access or a demonstrated host transfer. If neither an
importer-side check nor transfer is callable, explain the missing capability
before creating records; do not create a cloud-only replacement for a local Archive.

On any later import failure, disclose the existing `client_id` and `engagement_id`
and resume those same records. A folder-name collision calls for inspecting the
returned existing scope and reusing it when its identity matches; never clear old
folders or change the client's name just to get past the error. A deliberately
separate synthetic test may have a distinct name; retries retain their identities.
Documentless client work needs no file check. Standalone workflows check access
on their own execution host and do not require Archive or a computer folder when
that engine can read the inputs.

Public workflow names select skills; component IDs select module paths.
`financial-report-builder` uses component `report-builder`, `vouching` (historically
called Check Entries) uses `check-entries`, and `purchase-invoice-review` uses
`passive-invoice-audit`. These component IDs are not additional workflows.

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, financial-report-builder and vouching only, optional cache
cleanup uses the corresponding component ID from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
This supported maintenance command is the only cache-cleanup exception to the
prohibition on editing the installed tree by hand. It is optional: ordinary
validation and execution tolerate incidental bytecode without removing it.
On a read-only installation, skip cleanup. If the command reports a permission
error, retain that error and continue the ordinary validated workflow when its
checks pass; do not chmod, delete files manually, copy or patch the installation,
or bypass the host's permissions to make cleanup succeed.
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
environment per OS host with the published, hash-checked dependency locks, outside client
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

Do not use WhatsApp, live INPS browser capture, hosted suggestion or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract. When invoked through Vera, Clara or Lucia, task
usage, signed receipts, technical recovery and 1–5-star feedback through the
invoking product's incident service and rating form remain available. Follow the
primary task's workflow-usage contract and product identity. Tutorials retain
their no-reporting boundary.

# Adversarial Opinion

Run this distinct fourth stage after preparation, drafting, and validation in
the invoking product's `quesito-legale-fiscale` journey only when its original answer contract records
`adversarial_policy: required`. Read and follow
`../mparanza-legal-tax-answer-review/references/adversarial-scope.md` before activating it.
It is routine for an opinion on a concrete position, even when that opinion is
well supported; informational research alone does not activate it. Validation asks whether that opinion is supported; this stage
develops the strongest credible case for an incompatible conclusion. Use the
current model and selected runtime. A different model, separate agent, special
mode, or additional user confirmation is not a prerequisite.

For a supplied position, first use the legal-question journey to establish its
facts, scope and answer contract and review it. Respect a user's explicit
instruction to omit the stage; do not change `not_required` merely because
research has produced conclusions. Do not apply this stage to other
product workflows merely because their output mentions law or tax.

Early challenges within `../mparanza-deep-research/SKILL.md` guide research but never
complete this final assignment. Re-read the reviewed original and sources under
an opposing assignment rather than endorsing the research narrative. Keep
adverse evidence and alternative interpretations visible.

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
   the invoking product's `deep-research-validator` stage: source identity and support, reasoning,
   qualifications, coverage and professional judgment. Correct supported
   defects. This is validation of the fourth-stage output, not a recursive
   request for another adversarial opinion. Preserve both review records.

Match the working document's detail to the outcome. Develop a credible opposing
case as far as its reasoning and sources require. When none is established,
write a concise reasoned account of the scope, work performed and result; do
not pad it into a full counter-opinion. When evidence is limiting, identify the
decisive missing source or fact, the question it leaves unresolved and the next
useful check. These shorter results still retain the search and review records.

## Compare and deliver

Write a concise comparison containing the original conclusion, opposing
conclusion, decisive differences, evidence that could change the assessment,
and choices requiring professional judgment. Review that comparison against
both opinions and the underlying sources. Keep substantive statements traceable
to the reviewed documents; research and validate any new material claim.

The original may remain unchanged despite a credible opposing case. If the
exercise exposes a defect requiring correction, identify it explicitly,
correct and revalidate the original when supported, then refresh the opposing
exercise against that exact version. Reopen the shared research issue register
and targeted investigation for any material defect or new evidence exposed by
the opposing review or comparison. Record the treatment and changed/dependent
claims, then refresh the final reviews and research bindings. A credible
alternative interpretation alone does not establish a defect in the original.
Do not silently merge the opinions or
present a preferred legal strategy as an established fact. If missing evidence
or professional judgment prevents closure, preserve the partial package and
state what remains rather than looping or manufacturing a resolution.

Refresh the shared native research review with `research_record.py review-ui`
after the comparison is reviewed. Include both exact opinion revisions and
`adversarial_assessment.json` / `opinion_comparison.md`; consume saved/applied
professional decisions through the shared issue loop. The UI must not treat
acceptance as legal certification or replace either substantive review.

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

Vera excludes legal opinions from comparison reporting. For other invoking products,
record the original review, adversarial research/drafting, opposing review and
comparison under their reporting contract. These phases
can expose complete opinions, material case facts and selected source text to
the selected model runtime. The stage does not require a new provider account.

At delivery, include the invoking product's `adversarial-opinion` stage in workflow provenance only when
this exercise actually ran. Follow the invoking product's existing feedback and reporting rules.
