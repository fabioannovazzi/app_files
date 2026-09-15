# Vera browser automation: development to ordinary use

## Evidence and scope

Inspected baseline: `07689c38`, Vera 0.1.257, browser-automation 0.5.21.
The existing teaching, development-request and capability-pipeline suites pass
(119 tests). Immutable teaching checkpoints, sealed reviewed handoffs, exact
capability contracts, runtime receipts and idempotent CR submission already exist.
Generic startup nevertheless depends on a conversation path or capability name;
the records have no shared enforced process identity. CR registration sends text,
not a ZIP. Both client and server reject an unknown occurrence timestamp.

This change connects those components. It does not claim live Agenzia/ECONS
validation, measure unavailable model/token consumption, or transfer fiscal files.
Existing ECONS startup and action-time permissions remain in force.

## Implementation plan

1. Add an owner-private local process register at a stable user-scoped location.
   Store an opaque process identity, an exact professional objective and boundary,
   immutable attempt identities, installed/revised capability versions, CR receipts,
   and qualification evidence. Provide bounded catalog/resume commands; no old
   conversation, CR number or capability path is required from the accountant.
2. Start an attempt before teaching/testing/use. Reuse `teaching_checkpoint.py`
   inside that attempt and `executeCapability` for its executable contract. Save
   a readable attempt report immediately and after execution, including preflight
   failures, interruptions, output counts/hashes and locally measured elapsed time.
   Unavailable host/model/token data has a value of null and an explicit reason.
3. Extend the existing reviewed development request with process/attempt lineage
   and a bounded technical evidence projection. Submit the exact reviewed CR body
   through Vera's existing durable client. Persist the actual returned CR identity;
   retry the frozen body. Attach the useful evidence as structured CR text; report
   any ZIP as local/exported, never uploaded. Permit partial problem diagnostics
   only with explicit missing-data reasons and useful attributed evidence.
4. Import revised contracts under the same process and immutable version identity.
   Link development/release evidence and earlier CRs. Qualification reuses the
   existing two-clean-live-run finalizer and adds explicit result review and a
   measured performance bound. Simulation never qualifies a real process. A
   changed contract, environment, recovery or later failure requires retesting.
5. Add distinct teaching/development and ordinary-use instructions. The current
   model selects an exact supported process semantically from the scoped register,
   asks only for missing professional parameters, and prepares the selected run.
   Code enforces identity, types, qualification and host capabilities; it does not
   classify intent using keywords. Keep installed specialist routes explicit.
6. Exercise the connected journey with synthetic browser fixtures and a mocked
   CR service, including restart, partial evidence, server receipt persistence,
   retry, revised release, qualification guards, fresh-context use and regression
   feedback. Validate readable instructions/reports and package contents as well
   as helpers. Refresh privacy review and rebuild all affected host packages.

## Judgment and release boundaries

Model reasoning owns process meaning, interpretation of demonstrations, business
decisions, routing, result review and sanitization. Deterministic code is limited
to auditable identity, immutable file/hash linkage, measurements, contract and
permission gates, persistence and packaging.

This task authorizes implementation and a concrete reviewable change. Merge and
server deployment need authorization for this change. Existing-listing Marketplace
publication follows standing authorization after applicable release checks; built
artifacts and test fixtures are not evidence of publication or live validation.
Keep this task's worktree for the requested reviewable implementation; do not
create another worktree or remove unrelated active work.
