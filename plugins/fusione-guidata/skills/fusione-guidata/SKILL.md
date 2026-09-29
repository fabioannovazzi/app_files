---
name: fusione-guidata
description: Prepare and demonstrate Vera's P0 multi-company merger case foundation with explicit evidence imports, known/unknown/disputed facts, version-bound professional decisions and selective change review. Merger calculations and legal execution branches are not implemented.
---

# Fusione guidata — P0

Use the existing authenticated Codex or Cowork session. This component needs no
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
local-only processing guarantee. Codex and Cowork use their selected provider account.
No hosted upload, network fetch, model API call, signature or filing occurs in the
helper. The local report is evidence about this workflow, not provider telemetry.

## Plugin Improvement Feedback

Keep the improvement note local to chat or run artifacts. Development/demo runs do
not send feedback or receipts. For an ordinary Vera professional run, after showing
its readable model-data report follow Vera's existing feedback instructions; this
component grants no independent permission to transmit anything.
