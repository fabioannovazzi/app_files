---
name: fusione-guidata
description: Prepare and demonstrate Vera's P0 multi-company merger case foundation with explicit evidence imports, known/unknown/disputed facts, version-bound professional decisions and selective change review. Merger calculations and legal execution branches are not implemented.
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

# Fusione guidata — P0

Use the existing authenticated Claude or Cowork session. This component needs no
model API key and makes no network requests. It manages a durable case foundation;
it does not execute a merger or determine the legal path. Use the user's language.

Resolve this component's root before commands. Use Vera's shared managed Python
runtime and run `python scripts/check_dependencies.py` first. Its `requirements.txt`
declares standard-library-only dependencies; never install packages at runtime. Read
`references/case-contract.md` for the exact request and record contracts.

Never write run outputs inside this Git workspace or plugin source. Use the
selected engagement output directory, or a separate user-authorized demo directory.

Explicit approval is reserved for external, destructive, approval-sensitive or
material steps. The user's prior authorization covers reversible case preparation;
professional confirmation still requires the actual named reviewer's decision.
Deterministic local scripts own parsing, hashes and structural validation; the model
owns semantic interpretation and proposed dependency selection.

Start from the supplied operation, company identities and selected evidence. Ask
only for missing choices that change the scope. Keep absent facts `unknown` and
conflicting evidence `disputed`, with null values; never replace either with zero,
false, non-applicability or approval. Explain why an unresolved fact matters.

## Supported work

The helper stores Operation, Entity, OwnershipEdge, Evidence, Fact, SourceVersion,
RuleVersion, BranchDecision, Decision, ChangeImpact and Artifact records. It uses
immutable revisions and exact case/object/version/hash dependencies. SQLite
transactions and expected-version checks prevent partially applied or stale writes.

The model interprets documents, selects relevant sources, proposes branch decisions
and maps material dependencies. Code checks exact shapes, references, declared
company scopes, hashes and types. A valid record does not prove semantic completeness,
source authority, legal applicability or a correct professional conclusion.

For an illustrative walkthrough, run:

```sh
python scripts/run_fusione.py demo --output /absolute/new-demo-directory
```

Open the before/after reports and `demo-results.json`. Explain what actually passed
and what was not run. Every demo entity, source, rule and approval is synthetic.

For a scoped local case, create an operation using `init`, then use `apply` with
one reviewed request at a time. Record each company's permitted source directories
explicitly. An import is one selected file, not permission to scan its parent or
another company. Preserve original documents; the helper snapshots their bytes.

Read the registered companies and grants before operations. Use the operator's
declared actor; do not switch to an administrator or invent a reviewer to bypass a
denial. Actor IDs are local workflow declarations, not authenticated identities.
Filesystem permissions, account authentication and encryption remain outside this
component. A person with direct database access can bypass its workflow controls.

Bind each conclusion/draft to all its material evidence, facts and rules. The
helper cannot discover omitted dependencies. Record professional confirmation only
after the named reviewer actually approves the exact version, and retain their
role, time, scope and confirmation evidence. Never approve on their behalf.
Rule approval is a separate Decision; JSON validation never promotes a candidate.

After a source or fact changes, inspect the new ChangeImpact and affected statuses.
Historical drafts and approvals remain unchanged. Re-read the evidence, revise
dependent records to the reviewed input versions, and obtain any new approval
needed. Independent records can continue. A failed source retrieval is an explicit
SourceVersion with its error and attempt date, never “no change”; prior successful
snapshots remain available. Public research itself belongs to the host's separately
authorized research workflow, not this local helper.

## Boundaries and handoff

Every legal merger branch returns `unsupported` in P0, including ordinary domestic
OIC incorporation, wholly owned, partial, inverse, sister-company, MLBO, IFRS and
cross-border operations. Do not use the contributor's illustrative formulas as a
supported calculation engine. Statutory calendars, signatures, filing, tax treatment
and real-case professional acceptance are not implemented. Record a requested
branch and the unresolved work; continue independent case preparation.

No live Studio Archive adapter is claimed. Its client and engagement identifiers
cannot be pasted into a reference to bypass case boundaries. Client-bound work still
uses Vera's selected Studio Archive engagement/output folder and explicitly selected
receipted source directories; importing the selected files into this case creates
new local evidence records. Do not auto-discover other client folders. Keep P0
professional use provisional until the actual multi-company adapter and acceptance
case have been reviewed. Do not alter or close the underlying engagements here.

Export using `export --output /absolute/new-review-directory`; this writes a scoped
Markdown overview, complete accessible revision history in JSON, and the canonical
local model-data report. Show the readable report and its link with the result.
The automatic export cannot observe host model exposure: real cases remain
`not_measurable` unless the orchestrator adds actual observed phases through Vera's
report workflow. Do not describe an exported file as transmitted to a model.

## What data reaches the model

The selected runtime may read company names, ownership, file paths, evidence text,
facts, proposed rules, drafts, approvals and questions needed for the assignment.
The helper validates and snapshots complete selected files locally; report output
contains only the declared actor's company scopes. This is not anonymization or a
local-only processing guarantee. Claude and Cowork use their selected provider account.
No hosted upload, network fetch, model API call, signature or filing occurs in the
helper. The local report is evidence about this workflow, not provider telemetry.
