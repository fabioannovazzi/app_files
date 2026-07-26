# Concordato Plan Review Workflow Reference

This reference defines the review and assurance boundary implemented by the
plugin. It is an execution contract, not an accounting, legal, tax, or
going-concern conclusion.

## 1. Inspection and authority

The first run is an inspection pass. It captures source bytes, records source
receipts, and extracts advisory numeric tokens. Filename-based source roles are
suggestions only. The pass emits no authoritative amount candidates or
candidate matches.

A reviewer then approves two separate receipts:

1. `source_role_mapping` binds every supported source to its role, currency,
   unit, and every extracted token to `candidate_amount` or
   `excluded_non_amount`. Exactly one source must be the authoritative
   `concordato_plan`.
2. `calculation_formula_authority` binds the same source perimeter and candidate
   identities to the reference period, tolerance, implementation receipts, and
   the fixed calculation below.

```text
difference = plan_amount - support_amount
abs_difference = abs(difference)
within_tolerance = abs_difference <= tolerance
```

The sign convention is fixed:

- positive: the plan amount exceeds the support amount;
- zero: the amounts are equal;
- negative: the plan amount is below the support amount.

Missing, unreviewed, malformed, stale, or source-mismatched authority blocks the
qualified parser. A candidate-perimeter mismatch discovered after extraction
withholds all authoritative candidates and matches.

## 2. Qualified deterministic run

With current receipts, the qualified run:

- reopens the captured sources and verifies their byte receipts;
- preserves monetary values as exact decimal text;
- applies only reviewed token dispositions;
- compares compatible role, currency, and unit populations;
- writes candidate amounts, signed differences, absolute differences,
  tolerance values, and comparison results;
- retains source artifact identities and cell/page locators.

The canonical decimal domain is finite, at most 38 significant digits and at
most 18 fractional places. Formula evaluation uses an isolated working context
large enough for any two admitted operands; it never depends on the process
global `Decimal` precision. Values outside that domain are rejected before
authoritative rows are emitted.

An equal amount is only a candidate match. It is not proof that the source
semantically supports the plan line.

## 3. Numeric evidence closure

`numeric_evidence_ledger.json` records:

- every extracted and selected amount candidate;
- every plan and support amount participating in a match;
- every signed and absolute difference;
- the reviewed tolerance and each tolerance result;
- unmatched plan residuals;
- deterministic summary and source-role counts;
- every material numeric address rendered in the CSV, XLSX, and DOCX outputs.

Replay reconstructs candidates, matches, residuals, and population counts from
the current source bytes and reviewed authority. It then reopens each declared
CSV row, workbook cell, and Word table/paragraph address and checks that the
ledger exactly equals that reconstruction and covers the complete current
material-address population. A changed last row is treated the same as a
changed first row.

The execution boundary is an exact 25-file contract across plugin
configuration, UI assets, Python/Node code, and the shared assurance kernel.
Supported Python entries validate that physical tree before importing local
workflow code; MCP-launched Python uses isolated imports with bytecode disabled.
Unowned caches and other physical entries therefore fail before execution.
The resulting hashes are consistency evidence, not publisher or reviewer
authentication.

## 4. Whole-output closure

`workflow_output_closure.json` is written only after all normal run artifacts
exist. It contains an exact, sorted path declaration and a byte receipt for
every declared file. The declaration comes from a closed workflow allowlist,
not from discovering whatever happens to be in the directory.

Validation fails closed when the physical tree contains:

- a missing declared file;
- an unexpected regular file;
- a symlink, hard link, or special file;
- a changed declared file;
- an unsafe or non-canonical path.

Reviewer saves and applications run in a bounded working-tree transaction.
After authorized writes, a successor closure is produced with phase
`review_save_finalization` or `review_apply_finalization`. Its
`previous_closure_content_sha256` must equal the trusted predecessor closure.
The parent process replays the successor before replacing the canonical
directory. A failure leaves the canonical tree unchanged.

Standalone replay also regenerates the immutable workflow outputs in a fresh
directory from the source root and persisted reviewed decisions. It compares
JSON/CSV/Markdown bytes, workbook cell structure, Word structure, intake state,
review payload state, and the audit record. Rehashing a changed narrative such
as `review_packet.md` therefore cannot create new authority.

Reviewer choices in `ui_decisions.json` are authority inputs rather than
deterministic conclusions. Replay validates their identity, allowed actions,
item binding, counts, and status. It then independently derives and checks the
application effects, blockers, counts, status, next actions, and final-artifact
state. The review handoff is regenerated and compared in both the pending and
applied states.

Run a fresh replay with:

```bash
python scripts/replay_assurance.py --output-dir /path/to/reviewed-output
```

## 5. Gates and judgment boundary

The deterministic gates can establish only that source capture, reviewed
preparation, exact arithmetic, address coverage, and receipt replay completed.
They never grant reporting or publication authority.

The following remain human or Codex-assisted reviewer judgment:

- whether two equal amounts concern the same claim;
- whether evidence is sufficient, current, and appropriately authorized;
- accounting classification, rectification, or reclassification;
- legal and tax relevance;
- materiality;
- going-concern implications;
- the final professional conclusion and publication decision.

`final_ready` therefore remains `false` after all review actions are applied.

## 6. Validation limitation

Synthetic and adversarial fixtures exercise the mechanical contract, including
precision boundaries, stale receipts, source mutation, last-row output
mutation, rogue files, transaction rollback, and successor replay. They do not
establish performance on real corporate concordato plans.

Before field use, run a separate holdout containing a real, previously unseen
corporate plan and its support package. A qualified reviewer must compare the
plugin's complete candidate population, differences, omissions, and evidence
requests with an independently prepared workpaper. Do not describe the plugin
as validated on real corporate plans until that holdout is completed and its
limitations are recorded.
