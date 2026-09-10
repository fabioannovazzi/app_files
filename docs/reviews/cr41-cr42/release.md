# CR-41 and CR-42 release evidence

Release candidate: Vera 0.1.235, 10 September 2026.

CR-41's seven reproduced defects are covered by the prepared fix commit
`de40cc39`: treasury same-period opening balances, empty passive-invoice audit,
actual dependency imports, FatturaPA precision, Italian dot-thousands parsing,
corrupt open-item amount rejection and negative journal sample minimum.
This release also corrects its five documentation/privacy findings: the optional
ChatGPT Deep Research destination is separate from the originating account;
only declared recipes may be installed; Cowork carries the managed-runtime
privacy service and both download boundaries; the dependency environment is
shared across products; and the underlying Studio Archive CLI does not itself
impose the managed launcher's CPython 3.12 requirement. Cowork's documented
base ledger invocation now uses that launcher.

CR-42 adds optional ECONS processing to the existing acquisition collector.
Reviewed local phase bindings select each invoice line, set the association
checkbox true, confirm mappings, reread complete mappings, review the displayed
journal and client-specific VAT treatment, then attempt an authorized registration.
A completed result requires a protocol and invoice absence from the complete
Non contab. population of the same client. Per-client and batch reports preserve
attempts, exceptions and completed outcomes. Existing batch review commands keep
human checks and correction requests separate from completed entries.

The supported journal is a positive purchase invoice with one concordant cost
account. Mixed accounts, VAT codes, incomplete grids, other journal shapes and
unexplained rounding remain exceptions. The model supplies accounting review,
queue classification and authorization; exact identity, row count, checkbox
state and arithmetic checks do not decide accounting meaning.

## Validation

- Client-file preparation, passive-invoice audit and treasury suites: 226 passed,
  1 skipped.
- Journal Sampling suite in its own process: 176 passed.
- Open-item reconciliation helpers: 74 passed.
- Browser batch review, teaching checkpoints, pipeline and installation: 140 passed.
- ECONS synthetic runtime suite: 28 passed, including checkbox initially empty
  and already checked, conflicting accounts, mixed VAT, incomplete line counts,
  failed mapping, unbalanced journal, client-specific 100% non-deductible VAT,
  rounding explanation, stale journal after approval, wrong verification client,
  retained non-posted invoice and consecutive-red stopping.
- Package, privacy, update notification, icons and MCP startup: 478 passed,
  2 skipped. The corrected invocation includes repository fixtures.
- Product release build/check: Vera 0.1.235, Clara 0.1.190 and Lucia 0.1.39
  aligned. Lucia's Cowork archive is regenerated because it embeds the shared
  execution-contract documentation; its canonical source version is unchanged.
- Packaged startup: Vera's 18 MCP servers initialize and list tools.
- Changed builder: Black, Isort, Mypy and Bandit passed; no medium/high findings.

An initial combined accounting invocation collided on shared Python module names;
the component suites passed in isolated processes. No production code was changed
to accommodate that test-isolation issue.

## Remaining external evidence

The CR-42 submission contains operator reports and explicitly lacks complete
live screen bindings and two clean target-system replays. Synthetic tests prove
the implementation path, not live ECONS compatibility or portable validation.
Keep CR-42 open until the affected operator completes the reviewed binding and
two clean runs with the released package. Do not fabricate discovery or receipts.

Deployment, OpenAI Published status and the public update registry are separate
release steps. Update the registry only after OpenAI shows the exact version as
Published. CR-41 closure requires that publication evidence; CR-42 additionally
requires the target-system verification above.
