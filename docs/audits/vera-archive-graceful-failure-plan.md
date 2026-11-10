# Studio Archive graceful failure — implementation plan

Goal: an Archive infrastructure failure must not, by itself, stop otherwise
possible processing or delivery. This applies across Vera, not only accounting.
Professional source validation and real missing inputs remain separate.

## Inspected starting point

- Reporting startup/finalization and checkpoint writes already have partial
  failure isolation. Source tests cover these individual boundaries.
- `work-continuity.md` still requires a retained recovery checkpoint before
  dependent work. Most component instructions require Archive setup before
  inspection. These instructions can turn secondary storage failures into
  processing prerequisites.
- The shared engine context validates exact inputs and output ownership without
  an index or an Archive service connection. The portable local ledger can
  supply those contracts independently of Archive discovery/configuration.
- The current standalone helper supports only three engines. Simply using it
  for all workflows would break engines that need the richer portable context.
- Indexing, semantic tidying, checkpointing and recovery are distinct operations.
  Failure of one must not imply failure of unrelated professional work.

## Implementation sequence

1. Add a maintained independent working-folder route using the existing
   portable execution contracts. It must need no configured Archive, index,
   profile, network or registration. A software-managed general workspace is
   explicitly unregistered; it does not assert a professional client identity.
   Preserve an explicitly supplied known client identity when available.
   Retain exact inputs, an idempotent request, run identity and outputs.
2. Keep processing/delivery status separate from Archive status. Provide local
   completion and explicit retryable registration of retained work without
   recalculation. Never overwrite another client/run, duplicate a committed
   retry, infer missing client ownership, or announce successful archiving before
   byte verification. Use existing restore support for already-started runs.
3. Repair remaining optional-service exceptions and instructions. A failed
   index, private pointer, checkpoint or readable index must not block work
   whose actual source/output contracts remain usable. A failed filing operation
   stops that operation, not unrelated work. Report reduced recovery coverage.
4. Test failure before preparation, during work and after useful output exists;
   verify unchanged bytes, repeatable retries and distinct result/archive
   outcomes. Exercise several real engine entrypoints and audit every exposed
   route, distinguishing source coverage from installed acceptance.
5. Refresh affected privacy evidence and generated packages; run focused source
   checks, package integrity and required repository gates. Report any source,
   package or installed-host gaps explicitly. Do not touch Marketplace state.

## Acceptance criteria

- With selected readable inputs and a writable authorized task folder, an
  unavailable Archive does not require another setup conversation or prevent
  calculation/drafting and delivery.
- A useful saved output remains available when optional finalization, reporting,
  indexing, registration or checkpoint services fail.
- Failure status is durable when storage permits, visible independently of the
  professional result, and never falsely marked complete.
- An exact retry retains the same job and saved outputs. Recovery never accepts
  altered evidence as the original or repeats already completed professional work.
- Missing required evidence, damaged sole execution copies, unavailable actual
  output storage, or ambiguous authorization remain specific affected-step
  failures; no blanket catch converts them into success.

No product modifications are yet included in this initial plan. Existing dirty
work in the primary checkout is excluded from the isolated implementation branch.
