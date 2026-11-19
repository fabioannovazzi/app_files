# Reconciliation orchestrator pilot

The pilot objective is practical supported reconciliation, not proof of exact
identifier identity. Mechanical source scope, arithmetic, row ownership and
receipt integrity remain mandatory; judgment about names, timing and accounting
context belongs to the model. Missing codes alone do not defeat a supported cash
link. Supported links, tentative proposals and unresolved cases must be distinct.

## Execution design

1. Replay strict matches, then apply the verified local residual passes.
2. Present residual diagnostics, bounded focus rows and candidate membership to
   a model. Let it choose the next action: inspect/search, run a named local
   routine, generate a bounded discovery expression, decide supported/proposed
   links, escalate, or finish with unresolved work.
3. Local actions return candidates and evidence, never self-authorize semantic
   acceptance. Model-generated expressions run in a fuel-bounded AST interpreter
   over supplied JSON rows; no eval/exec, imports, files, network, processes,
   reflection or source mutation. Case-specific ID constants are rejected.
4. Validate model decisions using existing source, scope, financial and ownership
   checks. Cash matching is separate from invoice closure and expense treatment.
5. Persist every action and native invocation. Source-bound replay must verify
   evidence and must not re-run model calls. Bound total calls, wall time, working
   context and repetitive actions. Technical limits produce an explicit partial
   result with retained valid work, not an accounting conclusion or empty failure.
6. Deliver complete population coverage in the workbook, with uncertainty,
   unprocessed rows and next information needs visible. Preserve final revisions;
   a resume produces a new result revision when partial output already exists.

## Acceptance evidence required before practitioner use

- Public workflow entry reaches the pilot, while existing workflow stays usable.
- Actual model-selected action sequences, including semantic reasoning without
  exact IDs, are exercised; mocked selection alone is not model acceptance.
- Generated routines cannot access ambient capabilities or alter matches.
- Conflicts, nonzero balances and duplicate ownership cannot be silently accepted.
- Tentative links do not reserve rows as final matches.
- Exhausted time/call budgets and worker interruptions deliver partial output;
  resume preserves reviewed results and source integrity.
- Privacy contracts and package boundaries reflect the actual action data path.
- Local and CI engineering checks pass. Representative synthetic tests and
  practitioner trials establish distinct evidence; one real PDF case does not
  establish broad accuracy.

Deployment is on hold. The acceptance record below distinguishes implemented behavior from unverified host and practitioner outcomes.

## Implemented pilot and validation — 19 November 2026

The maintained `semantic_review.py run-all` entry now accepts
`--review-strategy orchestrator` for `bank_open_items`. The default staged route
remains unchanged. The three new modules separate local discovery, restricted
expression interpretation and the next-action controller. The package's Python
and MCP implementation inventories include all three modules.

Engineering validation: 195 focused tests pass, with 87.76% aggregate coverage
across ten reconciliation modules (new controller 89%, action tools 86%,
expression interpreter 85%). This covers source changes, native diagnostic
changes, rejected decisions, repeated allocations, mixed-sign net settlements,
no-code semantic links, tentative alternatives, public CLI delivery/logging, context/call budgets, missing
model capability, native-host pending/resume, local candidate expressions,
filesystem capability escapes and preserved workbook revisions. A further 103
open-item, invoice-boundary and privacy-source tests pass; stale test wording was
aligned with the existing native-review guidance and implementation-contract
error without changing those production behaviors. Twenty-four product privacy
contract tests pass; other-product archive tests require their own built ZIPs.

A real isolated Codex worker test used three synthetic bank rows and five ledger
rows. The requested selection was `gpt-6.1-terra`, high reasoning; the receipt
records the requested configuration rather than independently certifying model
identity. The model chose inspect, decide, corrected decide, then finish. It:

- linked a stationery purchase to its nine-day-later ledger posting;
- linked a 97.50 deposit to 100 gross receipts and a -2.50 processing fee;
- left two indistinguishable -42 ledger entries as unreserved alternatives,
  requesting evidence instead of picking one.

The first decision omitted required accounting-scope citations and was rejected;
the next decision supplied evidence. The four observed calls took 71.954 seconds
in worker processes, 74.3 seconds including controller overhead, and reported
54,881 input / 3,087 output tokens. One earlier single-case native test took
about 22 seconds. These are small engineering demonstrations, not estimates of
production throughput or broad matching accuracy. Model orchestration still has
per-call overhead; local matches require no model calls. The default six-call /
120-second budget makes that tradeoff explicit and returns partial work.

The final real-model result was replayed and reopened without further calls.
The full workbook exporter was exercised with those real model conclusions and
synthetic source-qualification fixtures, preserving two matches and one doubt.
LibreOffice successfully opened and rendered the workbook outside the outer
sandbox (the sandboxed converter aborted). The wide detailed worksheets are
intended for screen inspection; automatic fit-to-page PDF output is too small
and is not a validated client PDF deliverable. Native panel installation and
end-to-end client Archive execution of this pilot have not been performed.

Privacy review covers the new packet, local expression capability boundary,
selected-source context and inherited shared-worker routes. Local package/source
checks do not establish a signed run report: the standalone native engineering
test had no Studio Archive run, so no Archive privacy report was produced. Its
actual packets, receipts, timing and usage were retained locally. Practitioner
trials must use the ordinary Archive/reporting route and assess the actual
report separately from reconciliation success. Cowork/Windows/Antigravity live
pilot acceptance remains unverified; packaging or mocked pending/resume tests
must not be presented as real-host acceptance.

Production deployment, installed-plugin changes and Marketplace publication are
not part of this implementation delivery and remain on hold. PR CI must be
checked on the final commit before merging. The implementation and tests are
reviewed by the agent; no code review is requested from the user.


## Batch-size correction in the unreleased pilot

A subsequent 25-transaction residual test exposed a real defect in v1: verbose
per-row decision JSON exceeded the 45-second call budget, accepting zero links.
The v2 pilot adds compact explicit semantic approvals of visible candidates and
caps detailed responses at four groups. It expands each selected candidate into
an individual decision with literal source evidence, validating every group
through the same source, signed-sum and non-reuse checks. Candidate discovery by
itself still cannot accept a match. The prototype protocol changed before any
practitioner deployment; earlier synthetic v1 artifacts remain retained, not
silently rewritten or represented as v2 acceptance.

On the identical 25-row synthetic inputs, the actual native model generated a
general beneficiary/amount comparison expression and then explicitly approved
the visible candidates with selected description, beneficiary and date evidence.
All 25 individual pairings matched the independent synthetic ground truth,
including reversed ledger ordering. Two calls took 18.0 seconds (8.329 and 8.778
seconds inside the workers), with no hard-coded pairs, identifiers or amounts.
This demonstrates useful batch progress and actual model-authored code execution;
it is not a broad accuracy benchmark. Regression cases reject competing candidate
approvals, unseen group members and amount-only semantic evidence.

The corrected v2 route also passed a full synthetic Archive run through real CSV
intake, source qualification/receipts and the public command. Twenty-five
independently authored source pairings, with reversed ledger ordering and no
reference codes, were all retained as separate correct links. The native actions
were inspect, generate and decide_candidates: 26.35 seconds controller time and
24.856 seconds in workers. Cached reopening made no additional call. The run was
finalized/completed, its closed report recorded three emissions without collection
errors, and server receipt verification returned `verified`. This supplements the
earlier standalone and two-row prototype tests; installed native-panel and
real-client practitioner acceptance are still separate future steps.

## Opt-in milestone: truthful partial results

A subsequent independent Sol-observed synthetic case used nine bank movements
and eleven ledger rows, with a held-out answer key. The first native run retained
all seven supported links correctly (four local, two contextual and one net
settlement), with no false allocations. One ambiguity was explained and one
no-counterpart movement was still unreviewed at the six-call limit. The controller
took 118.135 seconds. A rejected answer consumed 31.945 seconds because separate
accounting evidence was missing despite supported cash-link evidence.

That run exposed incorrect summary counters: a reviewed doubt and an unreviewed
movement were both counted as technical errors, the open-item flag was false,
and the CLI called the review completed. The milestone correction separates
movement dispositions from controller stop diagnostics, counts only actual
reviewed groups, derives the open-item flag from outstanding relations and labels
incomplete CLI exports accurately. Regression coverage checks the workbook,
status JSON and reviewed counts after a cutoff with both a doubt and an untouched
movement. Runtime/call limits, matching policy and opt-in selection are unchanged.

A fresh native rerun on identical sources stopped after two evidence-format
rejections rather than reproducing the seven links. Its controller took 58.543
seconds and retained four correct local links, zero false links and five unreviewed
movements. The corrected status and CLI reported exactly those dispositions and
an incomplete review with open items. This confirms truthful partial delivery,
not improved matching or repeatability. Redundant accounting-evidence friction
and variable model completion remain known pilot limitations. Neither synthetic
run establishes superiority over Accounting or previous Vera.
