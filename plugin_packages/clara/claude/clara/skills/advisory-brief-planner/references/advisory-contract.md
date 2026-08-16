# Advisory contract 1.0

`advisory_contract.json` is Clara's stable cross-workflow assignment contract.
It is written before substantial advisory generation and passed unchanged to
the selected downstream Clara workflow. Semantic contents are authored by
Clara's active model session or confirmed by the user. The local validator may
check shape, references, status consistency, exact literal anchors, and stable
packaging; it does not choose or correct advisory meaning.

## Stable fields

| Field | Stable meaning |
| --- | --- |
| `schema_version` | Always `"1.0"` for this contract. |
| `contract_status` | Whether the assignment is ready for handoff, needs a material clarification, or is a useful partial contract. |
| `decision` | The decision, choice, or professional position the assignment must support. |
| `purpose` | Why the work is being performed and what it should enable. |
| `audience` | The intended reader, meeting, or decision-maker audience. |
| `deliverable_type` | The concrete requested output, independent from the workflow used to create it. |
| `output_language` | One of `it`, `en`, `fr`, `de`, or `es`. |
| `scope_included` | Work and questions explicitly inside the assignment. |
| `scope_excluded` | Work explicitly outside the assignment or reserved for another professional. |
| `available_inputs` | Stable input IDs, descriptions, current availability, and optional human-readable source references. |
| `evidence_requirements` | Evidence needed to support the decision, why it matters, its availability, and linked input IDs. |
| `analysis_plan` | Ordered analytical objectives, methods, inputs, and intermediate outputs selected with model-led judgement. |
| `assumptions` | Explicit or provisional assumptions and their materiality. |
| `unresolved_questions` | Remaining questions, why each matters, and whether it blocks handoff. |
| `success_criteria` | Observable criteria for judging whether the assignment output succeeds. |
| `selected_clara_workflow` | The existing `clara:*` workflow that owns execution after planning. |
| `validation_profile` | The kind of output validation expected after generation. |
| `validation_scope` | Concrete contents, claims, calculations, sources, or presentation properties to validate. |
| `correction_policy` | What the downstream workflow should correct and what must instead be returned for review. |
| `professional_judgement_policy` | Which decisions stay with the consultant and how judgement-dependent conclusions are marked. |
| `source_facts` | Material facts, dates, numbers, entities, and constraints with exact source anchors and input IDs. |
| `explicit_questions` | Questions stated by the user or source, preserved verbatim with input IDs. |
| `generation_handoff` | The objective, inputs, instructions, expected outputs, and specialist-authority boundary passed downstream. |
| `model_review` | An explicit model-led conformance review of meaning and completeness before handoff. |

The published JSON Schema is
`contracts/advisory_contract.v1.schema.json` from the Clara root. The
required semantic fields above remain top-level so an independently developed
validator can consume them without interpreting a second nested vocabulary.

## Input and evidence records

An `available_inputs` record contains:

- `id`: stable contract-local identifier;
- `description`: what the input is;
- `status`: `available`, `planned`, or `missing`;
- optional `source_ref`: a readable source label, not a required physical path.

An `evidence_requirements` record contains its own stable ID, the required
evidence, why it matters, availability status, and linked input IDs. Evidence
strategy is semantic. Deterministic code checks only that referenced input IDs
exist.

An `analysis_plan` record contains a stable step ID, objective, method, linked
input IDs, and expected intermediate output. The model chooses all of these.
The plan cannot override the selected specialist skill after handoff.

## Source preservation

Every material fact must be represented in `source_facts` with:

- `category`: `fact`, `date`, `number`, `entity`, or `constraint`;
- `text`: the fact as it should be carried into the assignment;
- `source_anchor`: an exact literal excerpt that preserves the source detail;
- `literal_value`: required for a declared `date` or `number`, containing the
  exact mechanically recognizable value within the source anchor;
- `input_id`: the input containing that anchor.

Every source question remains verbatim in `explicit_questions`. When exact
UTF-8 sources are supplied to the helper, it checks declared anchors and
declared date and number values, and mechanically inventories recognizable
dates, numbers, URLs, and question sentences. That whole-source inventory is
observational, not a completeness gate. The model-led review remains
responsible for deciding which facts, dates, numbers, entities, constraints,
and questions are material and for detecting semantic omissions or distortion.

## Handoff and review

`generation_handoff.workflow` must equal `selected_clara_workflow`, its
`input_ids` must be non-empty and include every input referenced by evidence
requirements, analysis steps, source facts, or explicit questions, all input
references must resolve, and `preserve_specialist_authority` must be `true`.
The handoff can constrain the work but cannot replace the specialist workflow's
evidence, review, privacy, or completion rules.

If a packaging attempt fails after a prior successful run, the helper moves the
prior canonical contract to a content-hashed recovery filename and writes a
current failed validation report. The stable `advisory_contract.json` path is
therefore absent until a new attempt passes.

The fixed model-review dimensions cover:

1. facts, dates, numbers, entities, constraints, and explicit questions;
2. decision, purpose, audience, and deliverable;
3. scope, inputs, and evidence;
4. analysis and success criteria;
5. workflow selection and generation handoff; and
6. validation and professional judgement.

Each dimension is `conforms`, `partially_conforms`, `does_not_conform`, or
`uncertain`. `ready_for_handoff` requires all dimensions and the overall review
to be `conforms`, with no blocking unresolved question.
