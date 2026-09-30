# Patent Box review — development integration

The archive workflow prepares selected software, patent and design evidence,
normalizes reviewed CSV/XLSX/PDF ledger populations, checks explicit component
controls, calculates reviewed amounts and exports traceable draft A/B documents
in Word and PDF. Source acquisition, cryptographic verification and signed
professional review have separate recorded evidence and acceptance boundaries.

Real rules remain DRAFT. Real calculation requires current source preflight,
reviewed rules and a certificate-authenticated, firm-authorized decision.
No real firm mandate or trust policy is configured by this implementation.
Synthetic tests do not establish professional UAT, provider acceptance or an
installed runtime. The full recovered specification remains in progress.

See `skills/patent-box-review/SKILL.md` for execution and
`references/implementation-status.md` for interface mapping and acceptance.

The calculation core, schemas, control catalog and synthetic fixtures derive
from Francesco's `Vera_Patent_Box_Developer_Pack_v0.1.0.zip`, recovered from
Discord message 1552213594513612880 on 2026-09-29. Original SHA-256:
`35e95ba861640e548dfb9577dcd11b22eae6c91d686dfa761a928163ec09dc2d`.
All 55 original manifest entries matched before integration. The original
documents under `references/` describe the wider proposal, not shipped scope.

For type validation, use the component configuration so the repository-wide
`ignore_errors` setting does not suppress diagnostics:

```sh
python -m mypy --config-file=plugins/patent-box-review/mypy.ini \
  plugins/patent-box-review/patent_box plugins/patent-box-review/scripts
```
