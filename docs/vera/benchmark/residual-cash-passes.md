# Residual cash matching before semantic review

After replaying the strict matcher and admitting explicit reference groups, new
runs apply exact same-day residual matching. Existing allocations are preserved.
Dates, signed amounts, currency, unit and entity scope must agree; conflicting
explicit party or reference identities remain unresolved. Zero amounts and
invalid dates are not admitted by these passes.

A unique same-day pair is linked as cash only. Equal-count repeated bank-fee
populations are linked as one balanced group, with no invented individual
pairing. Group admission requires a many-to-many relationship. These rules do
not establish invoice closure or correct expense classification. Accounting
review retains those questions when that purpose is requested.

A bounded search also supplies same-day, same-sign two/three-entry exact-sum
candidates in both directions. They are not allocated locally, even when only
one combination is found. Conflicting explicit identities are excluded. At
most 4096 combinations are examined per admission; exhausting this budget
leaves the remaining transactions available to semantic review, and is never
evidence of absence. Dense searches are not exhaustive.

The saved local evidence version is now 3. Resumed historical runs use their
saved version, so the new rules do not silently reinterpret previous decisions.
No transaction IDs, customer names, dates or case amounts are decision constants.
Fee wording is a conservative multilingual-description limitation: currently
commission/commissioni, bank fee and bank charge descriptions are recognized.
Other fee wording remains available to semantic review.

## Validation

The original two-PDF benchmark was replayed from its normalized CSV sources and
70 strict match edges, without reading Accounting's decisions as matching input.
The integrated admission produced 89 linked bank movements and two unallocated
aggregation candidates, reproducing the prototype's result. This is evidence
of coverage on one real case, not a general accuracy score.

Independent synthetic populations exercise different amounts, currencies,
entities, credit and debit directions, equal/unequal fee multiplicities, source
ordering, conflicting references, existing allocations, invalid dates, reverse
and three-row sums, competing combinations, historical replay, and end-to-end
workbook delivery with no model invocation when all cash links are local.
Existing grouped retrieval/retry fixtures use next-day ledger rows so that they
continue testing actual missing-evidence review rather than newly local matches.

The original benchmark remains non-blind. Broader synthetic regression coverage
does not substitute for adjudicated real-client accuracy evaluation.
