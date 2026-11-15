# Selected input verification contract

Use the native `verify_studio_client_inputs` tool for saved-input integrity.
The fallback CLI, only where the workflow permits CLI use, is `verify-inputs`
with `--client-id`, `--engagement-id` and repeated `--input-id` arguments.
It calls the same public operation. A blocked verification exits nonzero while
retaining its complete structured result; MCP exposes that result with isError.
Neither route creates a report, workflow run, replacement record or repair.

The required tool arguments select one registered client, its exact engagement,
and 1–100 distinct input IDs. The existing session ownership and approved-root
resolution apply. No arbitrary client root or source path is accepted.

Optional `expected_receipts` contains one `input_id` and `content_sha256`
per selected input. Use the seal from an earlier native import, listing or
verification result, not a fabricated hash. CLI accepts the same complete array
with `--expected-receipts-json`. This seal binds role, filename, byte count,
document digest and immutable receipt identity; it is distinct from `sha256`,
which identifies the document bytes. The baseline is caller-supplied evidence,
not authenticated professional approval or independent proof of history.

Optional `require_exact_input_set` (CLI `--require-exact-input-set`) means
the selection is the complete expected population. It reads all input receipts
and controlled bytes in that engagement, then rejects additions or omissions.
Without it, unselected inputs are outside the check. For more than 100 selected
inputs, verify explicit batches without claiming an exact full-population check.

The `vera.input_verification.v1` result includes:

- `status`: verified or blocked; `verified` must be true for a pass.
- `inputs`: each selected input's status. Valid current inputs include the
  maintained hydrated `receipt` with `path`, `relative_path`, original and
  imported names, role, byte count, file digest and receipt seal.
- `expected_receipt_matches`: true/false only when a baseline was supplied;
  null otherwise. A valid current receipt can fail the historical comparison.
- `input_set_matches`: true/false only for an explicit exact-set check; null
  otherwise. `failures` names the failed input or population check and reason.
- `not_checked`: evidence boundaries that this operation cannot establish.

The public reader validates the sealed receipt, selected ownership, safe ordinary
paths and complete file identity. The verifier rechecks receipt metadata after
hashing, and rechecks engagement identity before return. This is an observation
at read time, not a permanent lock on files or a guarantee against later edits.
Metadata may enter the selected host model context; complete file hashing is
local and returns no document text. This does not promise local-only model
processing. External fixture originals and copied delivery trees need their
separate existing checks.

For exact-retry acceptance, retain the import tool's actual `already_imported`
result and same input ID; verify the prior receipt seals and exact expected set.
For a new continuation, import a distinct derived support document, preserve its
authored source lineage, and verify both the earlier and new receipts. No amount,
currency, payment, client attribution or professional conclusion is inferred.
