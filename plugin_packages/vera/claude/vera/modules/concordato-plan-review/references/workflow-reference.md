> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Concordato Preventivo Workflow Reference

This reference defines the plugin's authority and replay contract. It is not a
legal, accounting, tax, feasibility, or attestation conclusion.

## 1. Inspection

The inspection run captures every supported source, records byte receipts,
extracts advisory text and numeric tokens, and writes an explicitly unreviewed
case-model template.

The deterministic inspection does not assign semantic document roles from file
names. Every captured source starts as `needs_review` in the case model and
`unclassified` in the numerical appendix.

## 2. Semantic authority

The operative case model uses schema `concordato.preventivo.case.v1` and covers:

- `legal_framework`;
- `procedure`;
- `document_perimeter`;
- `creditor_population`;
- `sources_and_uses`;
- `liquidity`;
- `milestones`;
- `review_questions`;
- `assumptions`;
- `issues`.

A reviewer-authored model becomes operative only after
`review_case_model.py`:

1. validates the exact schema and enumerations;
2. requires at least one cited legal authority and its as-of date;
3. requires one semantic classification for every captured source;
4. requires every professional review area;
5. validates evidence references against current source receipts;
6. normalizes decimal and date values;
7. seals the canonical content in a reviewed `semantic_review` decision
   receipt;
8. binds that receipt to the current captured-source perimeter.

Any changed source byte, missing source, added source, changed reference date,
non-canonical model, or altered decision makes the recipe stale.

The receipt records an asserted reviewer identity. It does not authenticate
the person cryptographically or prove professional qualification.

## 3. Deterministic semantic schedules

Only after semantic authority is valid may the workflow derive:

- creditor and class aggregations;
- proposed and liquidation recoveries;
- plan-versus-liquidation differences;
- sources-and-uses totals and funding gap;
- liquidity bridges and minimum closing cash;
- exact consistency checks.

The derivation uses exact decimal arithmetic. It validates arithmetic and
structure, not the legal or professional correctness of the inputs.

## 4. Independent numerical appendix authority

The legacy amount-matching control remains a separate optional authority path.
A reviewed `source_role_mapping` binds supported sources to numerical roles,
currency, unit, and each extracted token to `candidate_amount` or
`excluded_non_amount`. A reviewed `calculation_formula_authority` binds the
source and candidate perimeters, reference date, tolerance, implementation
receipts, and:

```text
difference = plan_amount - support_amount
abs_difference = abs(difference)
within_tolerance = abs_difference <= tolerance
```

This authority can prove exact transport and differences. It cannot qualify
the semantic case model or prove that an accounting amount supports a plan
statement.

If the semantic recipe is valid and the numerical recipe is absent, the
reconciliation gate is `not_applicable`. If both are valid, the numerical
ledger and reconciliation gate describe the appendix.

## 5. Outputs

Primary semantic outputs:

- `concordato_case_model.json`;
- `concordato_semantic_checks.json`;
- `creditor_treatment.csv`;
- `creditor_class_summary.csv`;
- `sources_and_uses.csv`;
- `liquidity_schedule.csv`;
- `concordato_review_workpaper.xlsx`;
- `concordato_semantic_review.md`;
- `concordato_preventivo_review_summary.docx`.

Numerical appendix outputs include `amount_candidates.csv`,
`exact_amount_matches.csv`, `concordato_tie_out_workpaper.xlsx`, and
`concordato_review_summary.docx`.

The current execution boundary covers 27 exact plugin and shared-assurance
implementation files. Python entry points validate the physical tree before
local imports; MCP-launched Python uses isolated imports with bytecode
disabled. Unexpected caches, links, files, or changed implementation bytes
block execution.

## 6. Assurance envelope and gates

The source gate may pass from a reviewed, source-bound document perimeter even
when the numerical role mapping is not used. The semantic-review and reporting
gates require the reviewed semantic decision and primary semantic artifacts.
The publication gate remains withheld.

Every source qualification referenced by a passed source gate is included in
the gate evidence. The semantic qualification proves reviewed document-role
coverage and source binding only; it does not prove legal compliance,
feasibility, or evidence sufficiency.

The immutable assurance envelope binds the semantic model, schedules,
workpaper, and semantic Markdown. The reviewable
`concordato_preventivo_review_summary.docx` is a mutable presentation artifact:
an authorized memo edit may regenerate it, so its current bytes are bound by
`final_artifacts.json` and the chained whole-output closure rather than by the
predecessor assurance envelope.

## 7. Numeric evidence and output closure

When the numerical appendix is qualified, `numeric_evidence_ledger.json`
reopens every material numeric address in CSV, XLSX, and DOCX and compares it
with reconstructed exact values.

`workflow_output_closure.json` declares every allowed output path and stores a
byte receipt. Missing, unexpected, changed, linked, or special files fail
closed. Review saves and applications create successor closures bound to the
trusted predecessor before replacing canonical output state.

## 8. Replay

Replay reconstructs immutable outputs from source bytes and persisted reviewed
decisions in a fresh directory. It compares semantic JSON, CSV, Markdown,
workbook structure, Word structure, numerical appendix outputs, review-session
state, assurance data, and audit records.

Run:

```bash
python scripts/replay_assurance.py --output-dir /path/to/reviewed-output
```

Reviewer UI decisions are authority inputs. Replay validates their item
identity, allowed actions, payload binding, effects, blockers, counts, output
state, and successor closure.

## 9. Limits

The workflow never decides:

- which legal interpretation is correct;
- whether creditor priority, class, or treatment is lawful;
- whether an attestation is sufficient;
- whether the liquidation comparator is professionally supportable;
- whether the plan is feasible or should be approved;
- whether tax, social-security, or accounting treatment is correct;
- whether the output may be published.

Representative synthetic fixtures prove only contract behavior. A qualified
review of a previously unseen real case remains required before any claim of
field validation.
