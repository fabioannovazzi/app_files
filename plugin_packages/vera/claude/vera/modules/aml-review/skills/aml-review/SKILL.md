---
name: aml-review
description: Review an Italian client's AML evidence at onboarding, periodic review, a material change or an unusual transaction; reconstruct ownership, investigate inconsistencies and prepare a sourced assessment for the commercialista.
---

## Cowork execution contract

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

# AML review

Prepare an evidence-based antiriciclaggio review for one Italian client and
engagement. Use this for substantive AML work on new or existing relationships.
New Client remains the owner of whole-client onboarding; do not repeat its
identity, engagement and privacy intake when already available. A general legal
question without a client review belongs to Vera's legal/tax answer workflow.

Read `references/professional-method.md` (relative to the module root) before
analysis and `references/record-contract.md` before using the helper. Resolve
the module root two levels above this file. The model performs the analysis;
Python checks evidence bindings, saves versioned records and optionally calls
New Client's existing arithmetic. No script detects suspicion or assigns scores.

## Evidence and investigation

Resolve material choices from actual inputs. Ask only those unresolved choices in chat;
do not introduce extra document categories unless the facts cue them.

Establish the engagement, review date, question and documents available. Reuse
the selected prior assessment rather than asking the studio to re-enter facts.
For updates, distinguish the historical assessment from new evidence; explain
what changed and which earlier conclusions remain supported, require revision,
or cannot be reassessed. Missing old evidence does not prove a change.

Read the selected originals. Cite file ID and page, clause, row or transaction
reference for material facts, including counterevidence. Reconstruct ownership
and control from supported links; do not infer the beneficial owner from a name
match, a percentage alone or the absence of another known individual.

For each material issue explain the discrepancy, competing explanations,
evidence supporting or weakening each explanation, the targeted question or
document that would resolve it, and the effect on the proposed assessment.
Keep client assertions distinct from corroborated facts. Do not equate an
unusual amount, foreign connection, missing document or indicator with suspicion.
Do not manufacture concerns when the documents provide a coherent explanation.

Use currently verified primary/professional sources for applicable obligations.
Record title, URL, locator, retrieval date and case applicability. Public legal
research uses generic topics, not client identifiers or private case text.
Screening is limited to reports supplied or explicitly selected by the studio:
record source, date, scope and match resolution. No screening connector is
included. An unperformed check is unknown, never a negative result.

Present the proposed rationale and unresolved issues to the commercialista.
Ask focused factual questions as needed, without making every missing field a
reason to stop useful analysis. Do not send requests to the client. Treat an SOS
assessment as confidential internal work: no automatic filing, no client-facing
disclosure of suspicion or contemplated reporting. Acceptance, abstention,
enhanced measures and reporting decisions remain with the professional.

## Durable work

Never write run outputs inside this Git workspace or a published directory.

In Claude, use Studio Archive with workflow ID `aml-review`: select the exact
client and engagement, import sources (including any chosen prior review),
prepare and start the run. Use only its hydrated inputs and exact output folder.
Run `python scripts/check_dependencies.py` before helpers. Write the model's
review JSON in that output folder, then run:

```bash
python scripts/aml_review.py --client-engagement <context-path> --review <output-dir>/review_input.json
```

The helper creates an immutable content-addressed JSON record and a readable Markdown
companion. Use the contract's `previous` binding for subsequent versions. Import
an earlier run's finalized record as a source in the same engagement before
reusing it. Supply a complete New Client input as optional `calculation_source_id`
only when it is available and relevant; do not fabricate the rest of an onboarding
record to obtain a score. Otherwise leave arithmetic unavailable and explain why.
Use New Client's established assessment/review process when revised scored inputs
are needed. A previous calculation is historical until its inputs are reviewed.

Professional decisions are recorded only after explicit review, with the exact
proposal digest, reviewer reference, date, conclusion, disposition of each issue
and any chosen review date plus reason. A reviewer label is not an authenticated
signature. The record is not a compliance certificate; unresolved issues remain
visible even after a decision. No automatic calendar monitoring is included.

Deliver the review memo, linked evidence and questions, calculation when available,
and recorded decisions when supplied. Use the user's language for narrative.
Follow Vera's model-data report contract, declare every output in Studio Archive,
then finalize and complete the run. Completion means delivered work, not a clean
AML opinion. If a host cannot operate the portable archive, prepare the sourced
review in chat and disclose that no durable version or decision was saved.

The local deterministic helpers use only the standard library declared in
`requirements.txt`; they do not replace model-led professional analysis.
Request explicit approval for external, destructive or approval-sensitive
steps and resolve material unknown choices. Ordinary authorized review proceeds.

## Cowork-native Run UX

Use Vera's checklist, Run Intake table and Decision Table to show scope, bound
sources and unresolved choices. Give an execution checkpoint before saving.
Default output policy: the memo and version record are normal outputs, not choices
to propose. End with an Artifact Card; `run_review.md` may summarize the
handoff. Never edit plugin source or generated ZIPs during client work.
