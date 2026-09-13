# Shared Python runtime launcher release — 13 September 2026

Vera 0.1.246, Clara 0.1.195 and Lucia 0.1.43 verify the shared runtime's
identity using its managed CPython 3.12 executable. Starting a dependency check
from an older system Python no longer produces a false platform mismatch.
Actual interpreter or platform changes still require explicit maintenance.

The fix was merged through PR #618 as
`379d1547a15ec1f7e9a0a009a461ca3e049c9d02` and deployed through a production
fast-forward pull and the documented API restart. Production was clean at that
commit. All three product pages returned HTTP 200 and the public Cowork ZIPs
matched the validated repository artifacts byte for byte.

## Validation

- 626 local tests passed; two optional checks were skipped.
- Shared-runtime coverage was 86.40%.
- All 23 PR checks passed, including cold installation from Python 3.14.7 with
  an empty PATH on Windows, macOS and Linux, provisioning CPython 3.12 and
  launching each product.
- Black, isort, mypy and Bandit checks passed. All generated Codex, ChatGPT and
  Cowork packages passed their source-alignment checks.
- OpenAI skill scans passed for all 37 Vera, 16 Clara and 10 Lucia skills.

Identity probes use `-I -S` to avoid site hooks and reader-lease deadlocks during
exclusive setup. Policy revision 4 preserves the managed interpreter and OCR
components during recipe updates. Validation used isolated test environments;
the user's shared local runtime and installed plugin caches were not rebuilt.

## Marketplace publication

OpenAI Platform directly showed Vera 0.1.246, Clara 0.1.195 and Lucia 0.1.43
as Published. The public directory independently showed each exact version.
Submission URLs and exact uploaded archive hashes are recorded in
`marketplace-publications.json`.

The public update manifest now advertises the published Vera and Clara versions.
Its reviewed data path is unchanged. Updating this governed source refreshed
Clara's update-check privacy fingerprint and rebuilt its archives. A ZIP member
comparison confirms that only
`privacy/hosted-services/plugin-update-check.json` differs from the published
Clara archive; executable files, instructions and Cowork bytes are unchanged.
The registry records the published and repository archive hashes separately.
