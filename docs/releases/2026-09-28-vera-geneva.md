# Vera common-core localization: Geneva

## Scope

The reusable `.agents/skills/localize-vera` method inventories the existing Vera
catalogue before judging a new jurisdiction. Its complete CH-GE assessment is
packaged under `plugins/vera/skills/vera/references/localization/geneva/`. It covers
35 professional functions plus four internal helpers. Language, jurisdiction,
currency and source format are separate choices. No Swiss-only service has been
added. France, Zurich and Germany require their own assessments.

## Implemented adaptations

- Studio Archive: explicit OCR language with reindexing after language changes,
  and canonical matching of Swiss enterprise identifiers.
- Treasury: CHF arithmetic, source-currency checks and currency-correct records,
  reports, workbook and review page. Fixed interface text remains Italian.
- Business Planning: shared French presentation and formatting; existing CHF
  financial calculations are retained for Vera and Clara.
- Accounting evidence: French textual bank dates under additive adapter v8,
  explicit source currency, reviewed Swiss invoice extraction feeding the same
  matching and semantic audit, and PDF-based vouching instructions.
- New Client and annual accounts: source-bound CH-GE adapters within the same
  existing workflows, with French/English memos, reviewed mappings, exact
  arithmetic, open evidence states and content-bound professional decisions.
- AML, organisational review, contribution evidence, registry and grants:
  explicit mandate/framework/source adaptations. Italian AML scoring and portal
  procedures are not reused as Swiss authority. No filing operation is added.

The new shared helper is included explicitly in every affected closed
implementation-file contract; unexpected files still fail closed.

## Verification and limits

Dedicated Geneva tests exercise actual Studio Archive execution, source
mutation, decision/client binding, immutable saved output, mixed-currency
rejection, CHF reports, French OCR, registry initialization and contribution
review packaging. The new setup/accounts/helper modules have 82.15% measured
coverage in the dedicated suite. Italian and French date regressions test
independent adapter selection and rejection of unsupported forms.

The release also runs the affected accounting/archive/planning regression suites,
exact-file attack checks, privacy validators, static checks, package integrity
tests and source/package drift checks. Packaged MCP startup is checked by the
builders. CI must be green on the merged candidate before deployment.

Synthetic checks do not establish professional acceptance on real Geneva client
material. The accounts adapter does not implement FER, IFRS, consolidation or
automatic statutory-completeness certification. Centrale Rischi equivalence,
restructuring procedure, the actual DATEV application and Swiss structured
invoice output remain unresolved in the assessment.

## Delivery boundary

Canonical versions: Vera 0.1.272, Clara 0.1.215 and Lucia 0.1.59. The latter two
include changed shared components. Codex, ChatGPT-upload and Cowork packages are
rebuilt from source at those versions. The user authorized git-based server
deployment and explicitly excluded Marketplace publication. Do not upload,
submit or publish to OpenAI Marketplace, change `published_version`, or claim an
enabled installation has updated. Server deployment is verified separately.
