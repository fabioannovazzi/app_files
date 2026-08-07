> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Product thesis — intelligent grant execution

## Thesis

The professional grant process already exists: select the governing call,
reconstruct requirements, collect beneficiary evidence, assess eligibility and
exclusions, qualify costs, prepare documents and fields, draft narratives,
cross-check the dossier, and review it before an authorized person uses the
portal. Vera should not replace that process with a generic AI answer. Vera
should make each professional step more intelligent, reviewable, and resumable
through bounded Claude contributions attached to exact case state.

The unit of intelligence is therefore one task packet, not an autonomous case
decision. A packet contains bounded, task-oriented reviewed context for one
semantic job and labels source material as untrusted content. It does not claim
automatic anonymization or legal data minimization; the professional must judge
which case facts and excerpts are relevant. A strict response
can propose guidance or changes, cites only packet evidence, records provider,
model, prompt-template version, input hashes, and output, and starts as
`MODEL_SUGGESTED`. A professional must explicitly accept, reject, or return it.
Acceptance copies valid proposals into the workbench as `proposed`; ordinary
professional confirmation remains separate.

## Model-led jobs

Use model reasoning for source interpretation, atomic requirement drafting,
evidence mapping, eligibility and exclusion reasoning, cost classification,
manual portal guidance, narrative drafting, conflict significance, missing
information and red flags, adversarial authority simulation, and contextual
workflow guidance. These jobs depend on language, context, and professional
meaning. The model must expose rationale, evidence references, requested
evidence, alternatives, risk flags, and confidence; it may not invent facts or
authority.

## Deterministic controls and their justification

- Packet bounding, exact output shape, identifier syntax, reference closure,
  input hashes, and model attribution are deterministic because they are closed
  technical contracts whose reproducibility is required for privacy and audit.
- The intelligence-output byte limit is deterministic because the case loader
  has a closed artifact-size boundary and must fail before writing an artifact
  that it cannot safely reload; it does not judge semantic relevance.
- Task-to-collection permissions are deterministic because they are a security
  boundary against an otherwise valid response mutating unrelated case state.
- Proposal normalization is deterministic because model work must never acquire
  professional authority through formatting: facts remain model inferences,
  assessments remain model-led, issues remain open, and all artifacts remain
  proposed.
- Protected declaration, authentication, signature, payment, save, and
  submission controls are deterministic because the prohibition is a product
  security boundary, not a semantic judgment.
- Stale-input detection and two-phase application are deterministic because the
  same accepted suggestion must bind to the same bytes and recover without
  duplicate or partial application.
- Automatic next-task selection uses only mechanically observable completeness
  and review states. It does not infer legal importance, applicability, source
  authority, or eligibility.
- Exact decimal and ISO-date comparisons remain the only semantic-adjacent rule
  families, for the bounded reasons in `workflow-method.md`.

## Professional boundary

The professional owns source authority, interpretation, applicability,
eligibility and exclusion conclusions, cost admissibility, factual acceptance,
narrative claims, issue resolution, and dossier disposition. The authorized
person additionally owns portal authentication, declarations, signature,
payment, saving, and transmission. Vera never represents a suggestion,
simulation, accepted contribution, or dossier as an authority decision or as
ready to file.

## Evaluation thesis

Offline tests can prove packet minimization, output strictness, reference
closure, non-authoritative state, stale detection, idempotent application,
protected-control enforcement, and packaging traceability. They cannot prove
legal accuracy. Semantic release evidence requires a separately governed set of
licensed or synthetic representative calls reviewed by qualified professionals,
with requirement/source precision, missed-material-requirement rate, unsupported
claim rate, cost-classification agreement, red-flag recall, and reviewer
override patterns reported by task and call family.
