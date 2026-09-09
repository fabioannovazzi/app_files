# Budget di tesoreria

Vera component for one company's EUR cash forecast, from six fixed tables.
Start with actual cash and supplied outstanding/planned flows. Updates reconcile
actual bank cash and settlement evidence, retain applicable reviewed dates and
explain differences against the accepted predecessor.

Read [the workflow](skills/treasury-forecast/SKILL.md) and
[the input contract](references/input-contract.md). Run inside a current Studio
Archive engagement using Vera's managed interpreter. Required missing data stops
the workflow. No generic extractor, business plan or Agenzia connection is required.

The local review saves dates and bases into recalculated, immutable versions.
Outputs include Excel, HTML/Markdown, daily/weekly CSVs and canonical JSON.
Acceptance records a professional decision on the exact proposal. Alternative
dates are persisted separately. Hashes do not authenticate a reviewer or prove
the truth or completeness of supplied evidence.

Validation includes synthetic three-run settlement/credit-note cases, actual
Studio Archive import/finalization, file formats, review persistence and artifact
readback. Real studio data and actual host-level operation still require a pilot;
unit and integration tests are not that evidence.
