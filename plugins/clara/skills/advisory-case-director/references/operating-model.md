# Advisory case-director operating model

This reference defines how the case director uses Clara's existing artifacts.
It is an operating contract for the model, not a schema for advisory meaning.

## One owner, several contributors

The case director owns the current answer and the map of work required to test
it. A research, interview, data-analysis, reporting, or presentation workflow
owns the quality of its bounded contribution. It does not own the overall case
position.

The assignment planner establishes what the engagement is for. The case
director determines how the case should move as evidence changes. The
deliverable validator reviews a completed output. Keeping these authorities
separate prevents both the planner and the validator from becoming substitute
orchestrators.

## Artifact responsibilities

| Artifact | Role | Authorship | Never use it as |
| --- | --- | --- | --- |
| `advisory_contract.json` | Reviewed assignment and initial handoff | Model-authored, mechanically validated | A permanent analytical roadmap |
| `case_manifest.json` | Stable case identity, objective, audience, status | Mechanically maintained from declared facts | A semantic issue tree |
| `clara_mandate.json` | Kickoff understanding and partner direction | Model-authored, structurally stored | The latest case answer |
| `material_registry.json` | Inventory and provenance of available material | Mechanically maintained | Evidence that a source is true |
| `advisory_evidence_register.json` | Durable receipts for evidence actually used | Model-declared, mechanically checked | A source summary or relevance score |
| `advisory_claim_register.json` | Durable claims, relationships, dependencies, limitations, and states | Model-authored, mechanically checked | A deterministic truth engine |
| `judgement_log.json` | Facts, inferences, partner judgement, and decision implications with review status | Model or partner authored | The partner-readable narrative |
| `open_questions.json` | Material questions and status | Model or partner authored | A generic request list |
| `case_issues.json` | Optional grouping of connected claims and tests | Model-authored | A mandatory universal taxonomy |
| `case_brief.md` | Derived resume and orientation view | Mechanically rendered | The authoritative case direction |
| `advisory_evidence_map.md` | Readable navigation across claim lineage | Mechanically rendered | The full analytical story |
| `advisory_workpaper.md` | Current answer and case-specific semantic spine | Model-authored | The evidence database or polished client deck |
| `advisory_workpaper_checkpoint.json` | Exact workpaper bytes and model-declared current claim/evidence closure | Mechanically committed from model-authored inputs | Proof that the prose is semantically complete or correct |
| `history/advisory_workpaper.<timestamp>.md` | Prior meaningful versions of the spine | Mechanical copy of model-authored work | A second current workpaper |
| deck, memo, or brief | Milestone view for a specific audience and decision | Specialist-authored from the spine | The memory or controller of the case |

## Start mode

When no workpaper exists:

1. read the assignment contract if present, case manifest, mandate, registered
   materials, evidence and claim registers, questions, and relevant sources;
2. state a provisional answer even if the answer is conditional;
3. invent the smallest analytical structure that makes the reasoning visible;
4. identify the few unknowns that could change the decision;
5. propose the first bounded work branch;
6. stage the model-authored workpaper, marking assumptions and target-data
   limits explicitly; and
7. commit it through `commit_advisory_workpaper.py` against the model-selected
   current claim IDs.

Do not start by populating a generic industry framework. Start from the
decision and the evidence already available.

## Resume mode

Read the current workpaper and compare it with the structured registers. Check
for evidence, claims, question states, or partner decisions added after the
workpaper's last revision. Reconcile them before proposing more work. If the
workpaper and registers disagree, report the disagreement instead of silently
choosing the newest file.

## Contribution integration mode

For each returned contribution:

1. identify the exact question it was intended to answer;
2. register the artifact or source when it is not already registered;
3. create evidence receipts with scope and limitations;
4. add or revise claim records using `supports`, `weakens`, `contradicts`, or
   `creates` relationships as applicable;
5. preserve claims that have been superseded or weakened rather than deleting
   their history;
6. update related open questions and optional issue groupings;
7. decide the contribution's effect on the current answer; and
8. commit the staged workpaper through `commit_advisory_workpaper.py` only after
   those lineage updates; the helper archives the prior version and writes the
   current checkpoint.

A report can answer its bounded research question while opening a more
decision-relevant target question. That is a valid result, not a failure.

## Partner challenge mode

When the partner supplies a question or objection:

1. record its origin as partner judgement and link any resulting open question
   through that judgement entry;
2. identify which link in the current reasoning it attacks;
3. determine whether existing evidence can answer it;
4. revise the answer immediately if the evidence already warrants revision;
5. otherwise define the smallest evidence branch capable of resolving it; and
6. expose Clara's recommended answer and why the partner may disagree.

Do not treat the partner's wording as automatically true. Do not hide that the
partner, rather than Clara, found the important question.

## Research return standard

A research branch should return:

- concise answer to the bounded question;
- sources with exact URLs or durable local copies;
- finding-level support and limitations;
- counterevidence and alternative explanations;
- geography, period, population, product, and comparability boundaries;
- what the result establishes at market level;
- what remains unproven about the target; and
- new questions created by the result.

The director integrates those elements into existing claim lineage. It does
not paste the report wholesale into the workpaper or discard prior loops.

## Deliverable round trip

The normal relationship is:

```text
current spine -> working deliverable -> partner challenge
      -> updated spine -> bounded work -> updated spine -> revised deliverable
```

This is one case-direction cycle with milestone outputs, not separate inner and
outer loops. The deliverable may be created early to make the answer testable.
Semantic feedback always returns to the spine. Pure design or wording feedback
does not need to reopen the case thesis.

For a case-bound HTML milestone, the final handoff adds one mechanical closure
step after HTML static/browser QA and the model-led advisory validator:
`verify_advisory_html_delivery.py` binds the exact HTML bytes to the current
workpaper checkpoint, current evidence and claim registers, reviewed direct
claims, and unchanged format-check artifacts. It does not decide whether the
claims are true or the recommendation is good.

## Partner checkpoint

Show no more than the judgement bottlenecks. A useful checkpoint normally
contains:

- current answer;
- why Clara currently believes it;
- the strongest evidence against it or the largest unproven link;
- the next branch Clara recommends and what it could change;
- Clara's default if the partner does not intervene; and
- the exact partner decisions needed now.

The checkpoint is a decision surface, not a request for the partner to design
the analysis from scratch.
