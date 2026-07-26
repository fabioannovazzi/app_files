# Journal–Bank independent successor commission

Status: ready to commission; not promotion evidence.

This packet commissions a fresh unseen holdout for the production
`journal_bank.tabular.v6` adapter under the frozen v5 evaluation contract. It
does not authorize an orchestrator or a professional accounting conclusion.

## Frozen basis

- Normative contract:
  `journal-bank-evaluation-contract.v5.json`
- Contract SHA-256:
  `4824652ecdb990a844fd9b72d799a2537f46a21ddb9fefb8a664f828c0ec6657`
- Required adapter: `journal_bank.tabular.v6`
- Required relationship adapter: `journal_bank.relationship.v2`
- Required production schemas: the exact schemas named in the frozen contract
- Prior evidence that must remain excluded from promotion:
  v2/Aurora, v3/v5, v4, adjudicated r3, v7, the sealed 23/24 successor, and
  every exposed diagnostic or remediation replay

The commissioner must give the author an independently verified read-only copy
of the exact contract bytes. Any changed byte creates a different evaluation
and cannot promote this contract.

## Required separation of duties

| Role | May see before candidate seal | Must not see before candidate seal |
| --- | --- | --- |
| Holdout author | Frozen contract, production schemas, public authoring brief | Candidate outputs, prior hidden bundles, prior hidden oracles |
| Candidate operator | Public input packet, execution instructions, frozen implementation identity | Hidden oracle, author notes, expected rows or outcomes |
| Evaluator | Sealed public packet, sealed candidate outputs, hidden oracle after release | Unsealed or mutable inputs |
| Adjudicator | Contract, manifests, candidate and oracle evidence, evaluator report | No additional private expectation outside the sealed record |

One person may not act as both candidate operator and holdout author. The author
must disclose any access to prior hidden evidence; such access makes the case
diagnostic rather than promotional.

## Author deliverables

The public packet must contain wholly fictitious, non-identifying,
rights-clear bank and journal sources plus reviewed mapping authorities needed
by the frozen contract. It must not contain expected normalized rows, expected
matches, expected gates, or an oracle-authored workbook.

At minimum, author:

1. two positive cases using materially different supported layouts;
2. two independent executions per positive case;
3. one case for each required delimiter transport (`LF`, `CRLF`, and `CR`);
4. date-convention, direction-vocabulary, monetary-column-disposition, and
   source-role authorities bound to exact source receipts;
5. all negative families required by the v5 contract, including ambiguous and
   unsupported delimiters, numeric-separator confusion, ambiguous and invalid
   populated dates, missing stable references, unknown direction values,
   duplicate candidates, evidence reuse, cross-currency relationships,
   truncation, malformed records, and pre-run and mid-run byte or membership
   changes;
6. native-output mutations that change a non-first material row or cell as well
   as a first-row value; and
7. a hidden machine-readable oracle covering exact rows, source outcomes,
   gates, block codes, matches, residuals, native material-value addresses, and
   expected abstentions.

Every case must have a stable opaque identifier. Do not encode the expected
outcome in the identifier or filename.

## Separate localized-date capability track

A private real-source diagnostic observed an otherwise reviewable legacy Excel
bank layout whose populated dates use localized textual month names. The
frozen v5 contract correctly withheld every row from that layout. The case is
exposed diagnostic evidence and is not part of this v5 commission.

Do not amend the v5 contract or its oracle during this commission. Localized
month-name support is now implemented only under the separately frozen
`journal-bank-tabular-v7-extension-contract.v1.json` contract. That additive
contract contains:

- an explicit locale and complete accepted month vocabulary;
- an exact normalization rule and ambiguity/invalid-date policy;
- representative positives across capitalization, spacing, day boundaries,
  leap years, and supported Excel transports;
- negatives for unknown or mixed languages, partial month tokens, ambiguous
  numeric/text hybrids, invalid calendar dates, blanks without stable
  references, and source mutation; and
- a requirement for a new independent holdout after the extension and tests are
  frozen.

Deterministic parsing is appropriate for that bounded track because the
accepted representation, calendar validity, and normalized date can be
mechanically verified and replayed. Semantic inference, model repair, or a
silent locale fallback is outside the source adapter.

The unprocessed sibling statements from the exposed private correspondence
must not be relabelled as the independent v5 successor. They may be used only
under a separately declared custody and evaluation status appropriate to an
already known source family.

The authorized private v7 rerun is complete-population diagnostic evidence:
202 bank and 8,141 journal movements qualified, 83,826 material-value addresses
and 42 assurance receipts replayed, and unresolved rows kept reconciliation
withheld. It cannot promote v5 or v7. A separate v7 commission must use a fresh
independently authored source family and hidden oracle.

## Seal and custody protocol

1. Validate the public packet against the frozen public construction rules.
2. Seal the public manifest, hidden-oracle manifest, bundle manifest, and root
   seal before candidate execution.
3. Copy only the public packet into a read-only candidate directory.
4. Deny candidate network access and access to the author tree, oracle tree,
   prior private bundles, and evaluator source.
5. Record the candidate implementation tree SHA-256 before execution.
6. Execute every case twice in independent output directories.
7. Seal both candidate output trees before releasing the oracle.
8. Release a read-only oracle copy to the evaluator and seal the comparison
   inputs.
9. Retain a machine-readable no-oracle-access ledger through the final
   adjudication.
10. Store private source trees outside the repository and Marketplace package.

The custody record must contain timestamps, actor or system identifiers,
commands, source and destination roots, permissions, and SHA-256 values. It
must not rely on a narrative assertion of blindness.

## Mechanical acceptance rule

Promotion is `GO` only if all of the following are true:

- the contract hash and implementation hash remain unchanged;
- construction validation passes before candidate execution;
- the public and hidden trees remain sealed and custody checks pass;
- every positive A/B pair repeats the contract-declared deterministic artifacts
  byte for byte, excluding only explicitly run-scoped fields;
- every exact oracle comparison passes;
- every unsupported or mutated source emits zero plausible prepared rows and
  the exact required source outcome and block code;
- every native-output mutation is rejected fail-closed;
- every source, mapping, implementation, output, and relationship receipt
  replays;
- all exact Decimal values, signs, magnitudes, residuals, gates, and native
  output addresses conform to the frozen contract; and
- no unsealed expectation is introduced during adjudication.

Any mismatch is `NO-GO`. A later replay after exposure is regression evidence
only and cannot change the sealed result.

## Commissioning record

Complete this table before any authoring starts:

| Field | Value |
| --- | --- |
| Commission identifier | pending |
| Commissioner | pending |
| Holdout author | pending |
| Candidate operator | pending |
| Evaluator | pending |
| Adjudicator | pending |
| Contract-copy SHA-256 | pending |
| Independence/conflict disclosure | pending |
| Private custody root | pending; do not commit |
| Authoring start time | pending |
