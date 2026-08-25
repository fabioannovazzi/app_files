# Vera audit assurance representative evaluation log

Status: active

This log records promotion evidence without retaining private source files,
company names, source paths, or source contents in the repository. Holdout
labels are intentionally anonymous.

## Journal Sampling holdout 2026-07-24

Five independently supplied Italian journal exports were inspected with no
source recipe preselected.

| Holdout | Source family observed | Result | Mechanical evidence |
| --- | --- | --- | --- |
| A | Native flat legacy Excel journal | Qualified after explicit mapping review | 4,406 monetary candidates, 4,406 canonical rows, zero rejected monetary rows, one account-only metadata row explicitly excluded, twenty additional numeric or monetary columns explicitly reviewed as non-posting fields |
| B | Print-oriented workbook with unstable row ownership | Unsupported | Proposed mapping failed dry-run closure: 5,814 monetary candidates, 5,410 emitted candidates, 404 rejected candidates |
| C | Two-row/grouped print export | Unsupported | No mechanically valid date ownership was established |
| D | Two-row/grouped print export | Unsupported | No mechanically valid date ownership was established |
| E | Report-like text distributed across spreadsheet cells | Unsupported | Required source-owned monetary roles were not established |

Observed controls:

- no unreviewed holdout emitted canonical rows;
- the positive holdout required a complete reviewed-decision receipt bound to
  its source artifact, adapter version, mapping digest, posting identity,
  carry-forward policy, currency, unit, and monetary-field dispositions;
- source bytes were receipted before and after parsing, and the source artifact,
  implementation, normalized CSV, assurance gates, and assurance envelope were
  replayed before sampling;
- physical workbook rows and the exact worksheet name were retained as source
  locators;
- corrupt spreadsheet containers now become an unsupported source result
  rather than terminating a multi-file intake;
- account-only metadata does not enter the monetary population and is counted
  separately;
- systematic sampling over the 4,406-row qualified population produced
  byte-identical 25-row CSV samples in two independent output directories;
- the source and preparation gates passed while semantic sufficiency remained
  explicitly `not_assessed`.

Regression coverage derived from the holdout includes:

- wide native journals with unrelated `Importo` columns;
- precedence of explicit debit and credit columns over generic amount fields;
- mandatory mapping or reviewed exclusion of every monetary-looking column;
- mandatory disposition of neutral-header numeric columns and print-layout
  numeric columns, not only fields identified by monetary keywords;
- explicit registration and line identifiers;
- explicit posting identity, carry-forward, currency, unit, and
  source-reported increment;
- physical row and worksheet locators;
- multi-worksheet whole-source abstention;
- source mutation during parsing as well as after normalization;
- parsing from captured immutable bytes so swap-and-restore source mutation
  cannot change normalized values;
- source-artifact mutation after normalization;
- corrupt sources inside a mixed intake;
- proposed-mapping dry-run failure;
- reviewed-decision and assurance-envelope tampering;
- byte-identical repeated sampling;
- exact candidate-to-emitted population closure.

Unknown:

- the four unsupported layouts do not yet have bounded positive adapters;
- no capability claim is made for arbitrary journal PDFs or report-like
  spreadsheets;
- promotion remains blocked until V5 privacy, regression, package, and
  requirement audits are complete.

## Open-item Reconciliation public projection 2026-07-24

A twelve-row holdout was selected from the receipted 200-row
[Connecticut Open Expenditures Ledger](https://data.ct.gov/resource/jz5u-r6jf.csv?$limit=200).
The public rows were projected into independently sealed open-item and
bank-like views with exact public row, invoice, payment, amount, currency,
department, vendor, and physical-row identities. All source and run artifacts
remain outside the repository and Marketplace package.

| Evidence | Result |
| --- | --- |
| Public source SHA-256 | `6247b8fb4f9ddd2a52f935cbf53c4cd613676478762745ad9509be8ead75ffe4` |
| Open-item projection SHA-256 | `63d19ebe17f612ff68d0b67e377e3eb59cfebe836b6c708f3e4dd8cdbedcbb5c` |
| Bank-like projection SHA-256 | `5456e7f69cb59d0368f7114c7741953c548c99d8b763243f85ba848da0dd5e72` |
| Rows and exact USD total | 12 rows; `157763.60` |
| Positive mechanical result | 12 closed rows; 12 balanced one-to-one allocation ledgers |
| Repeated mechanical-result SHA-256 | `8ac0843614bb5d51df9ecc22cc9242a14f955564949f825887aab54d0c157743` |
| Repeated audit workbook SHA-256 | `1fbea23da6afae1349776d18ff4962b540b4aa2172d5d1a2184e4015a3abbd78` |
| Repeated accountant workbook SHA-256 | `0b7d25255a38baadcf3a5850456591aa73650de7878b8d56af95e12da646e76c` |
| Repeated Word report SHA-256 | `0b45383ec2ce7d8c3bb88d57890dda82bf94101e682d2f92ba8e85a75219a277` |
| Professional review | every selected review row remained `PENDING` |

Mutation-based negatives changed one dimension at a time:

- a party mismatch changed the affected row to `needs_evidence` with a failed
  relationship control;
- a cross-currency allocation did the same;
- duplicating an open row while reusing one evidence row withheld both
  closures;
- removing the first evidence row left the corresponding open item
  `unresolved`.

This is positive evidence for deterministic identity, party, currency,
one-to-one allocation, conservation, replay, and final-review blocking. The
bank-like view is an evaluation projection derived from the public payment
population, not an authentic bank statement. It therefore does not establish
external audit-evidence sufficiency or satisfy the second independent-source
promotion requirement.

## Open-item Reconciliation independent HMRC projection 2026-07-24

A second twelve-row holdout was selected after the first case from the official
[HMRC September 2025 spending return](https://www.data.gov.uk/dataset/008d307b-5434-4218-9b62-2eabdef48778/financial-transactions-data-hmrc/datafile/8b0d2b77-c7aa-43b0-bdcf-9a6323097115/preview),
published under the Open Government Licence. Only transaction numbers occurring
once in the source and positive, exactly parseable GBP amounts entered the
positive population. The public rows were projected into separately sealed
open-item and bank-like views. No source or run artifact is retained in the
repository or Marketplace package.

| Evidence | Result |
| --- | --- |
| Public source SHA-256 | `c6627c3052773331fc5915bba39402e743975d614667e5d7ca910a40bda8eac3` |
| Open-item projection SHA-256 | `b226182377a31630a9b9f36078c956759c1056083a491101910cceece55277f0` |
| Bank-like projection SHA-256 | `473e75c225ccf4369d153b931f286b609e4d97ae5ad29e1006c23703836c205d` |
| Rows and exact GBP total | 12 rows; `3075230.66` |
| Positive mechanical result | 12 closed rows; 12 balanced one-to-one allocation ledgers |
| Repeated mechanical-result SHA-256 | `972864fd810866fb2aef98c8bbe9771ec430940a8506f0318914319a3766f9c6` |
| Repeated audit workbook SHA-256 | `96fbf96b5fdfffe91862488e44bb6581ef69c72e39bf6fd16f82fcbe55576183` |
| Repeated accountant workbook SHA-256 | `a5f087a8308902614dbfbeb1ada360977713df0441d89e8c08c44f04867cbc95` |
| Repeated Word report SHA-256 | `bf583f9a8c7ee24ef361bc982f73c8696dea89337431bd367159417268698bd5` |
| Professional review | every selected review row remained `PENDING` |

The same party, currency, evidence-reuse, and truncation mutations all withheld
closure. The first execution also exposed run-clock metadata in the two XLSX
packages. Open-item Reconciliation now normalizes OOXML core properties, member
order, and ZIP timestamps; a focused regression and both public cases prove
byte-identical workbooks after that repair.

Together, the Connecticut and HMRC cases satisfy the two-independent-population
requirement for the deterministic relationship/allocation kernel. They do not
qualify a raw bank-statement adapter: both bank-like views are reviewed
evaluation projections from published payment rows, not authentic independent
bank statements. External evidence sufficiency and every professional
conclusion remain unassessed.

## Open-item Reconciliation successor re-audit 2026-07-25

The review-successor boundary was remediated after an implementation audit and
then exercised through its intended browser, Python, and MCP process surfaces.
The exact 25-file implementation tree is checked before workflow imports. A
later review requires the predecessor checkpoint supplied through a separate
operator channel, archives and replays the exact predecessor transition, and
binds the successor to that checkpoint.

| Evidence | Result |
| --- | --- |
| Scoped remediation suite | 308 passed; 0 failed; 0 errors; 0 skipped |
| Remediation evidence-bundle root SHA-256 | `a10f4a489f550f11439b54b472e4f5c9a484b5c79944d69e68f4220c0933c440` |
| Separate root attack suite | 32 passed; 0 failed; 0 errors; 0 skipped |
| Root JUnit SHA-256 | `f5584ae3a9214db81e89734344982ceea4998db5e6552b1df80c4c0b17815a45` |
| Static gates | Black, isort, mypy, Bandit, Python compilation, Node syntax, widget parity, and scoped diff checks passed |

The targeted root attacks cover implementation expansion, timestamp-valid
local bytecode, missing and wrong browser checkpoints, isolated CLI and MCP
checkpoint enforcement, alternative self-resealed predecessors, and changes
to material amount, currency, cutoff date, run date, run ID, scope year, and
tolerance. Rejected operations preserve the exact prior tree.

The checkpoint authenticates no person and is useful only if retained outside
the candidate tree through a trustworthy operational channel. This re-audit
does not change the public-case limitation: the evaluated bank-like views are
projections, not authentic raw bank statements.

## Journal Sampling public qualification probe 2026-07-24

A 200-row slice of the public
[Connecticut Open Expenditures Ledger](https://data.ct.gov/resource/jz5u-r6jf.csv?$limit=200)
was retrieved from the official Socrata endpoint for dataset `jz5u-r6jf`. The
raw slice remains outside the repository and will not be included in the
Marketplace package.

| Evidence | Result |
| --- | --- |
| Source SHA-256 | `6247b8fb4f9ddd2a52f935cbf53c4cd613676478762745ad9509be8ead75ffe4` |
| Source size | 89,359 bytes |
| Candidate rows | 200 |
| Emitted prepared rows | 0 |
| Rejected proposed rows | 200 |
| Qualification | `unsupported_source_layout` |

The probe correctly abstained. Although the source has explicit payment date,
account, amount, and row identity fields, nine additional populated numeric
identifier or classification fields had no reviewed disposition and the
unreviewed proposed mapping failed complete-population dry-run closure. The
result is useful negative evidence; it is not a positive example of the claimed
native-journal family and cannot satisfy the two-positive-source promotion
requirement.

## Journal Sampling two public reviewed-mapping cases 2026-07-24

The Connecticut probe above was rerun only after a reviewer explicitly mapped
the operative amount and date fields, disposed every other numeric-looking
field, selected the posting identity, and fixed currency, unit, and sign
convention. A second, independently published population came from the official
[San Francisco Vendor Payments (Purchase Order Summary)](https://catalog.data.gov/dataset/vendor-payments-purchase-order-summary)
dataset. Both 200-row source slices and all run artifacts remain outside the
repository and Marketplace package.

The first Connecticut rerun exposed that the bounded tabular adapter rejected
otherwise valid ISO datetimes with a time component. Support for the mechanical
`YYYY-MM-DD[T or space]...` representation and a focused regression test were
added before either result below was accepted.

| Evidence | Connecticut | San Francisco |
| --- | --- | --- |
| Source SHA-256 | `6247b8fb4f9ddd2a52f935cbf53c4cd613676478762745ad9509be8ead75ffe4` | `fdbbb5ef919dcc36f6e521e24433af66b191fe56eece6de0667138db56037087` |
| Source and normalized rows | 200 / 200 | 200 / 200 |
| Exact signed USD total | `1121377.07` | `66022448.53` |
| Repeated normalized CSV SHA-256 | `a94ccb8892af0b881700e797b2b60ab6bc3275710169db21f563808a99711905` | `774463511b858f7cc054208c839b2dbb4d3f69a5214d7fb855e34d42c24e9f43` |
| Repeated assurance-envelope content SHA-256 | `fe50c591ee6c764dbec65048ef5269161db68fc5b5ca98c08259bc1982fd3397` | `e59ed9b6f76c5fb9cfdcecef431f9654b50c7267b77cffd27c363b09bd3662f4` |
| Repeated 25-row systematic-sample CSV SHA-256 | `97dcae2b6de6906fd4904fa837344cc435e61bc723e8bef4beb0a54f43ebb40a` | `8415918dc6362ec9e56cea81913e75dab9ce30e02f36009b32ad4853d07b47bb` |
| Source / preparation gates | `passed` / `passed` | `passed` / `passed` |
| Semantic review | `not_assessed` | `not_assessed` |

For each source, three one-dimension mutations were then applied:

- leaving one numeric-looking column undisposed withheld the whole population;
- changing the reviewed unit from currency to cents withheld the whole
  population;
- changing the source after normalization blocked sampling when the original
  source receipt was replayed.

This establishes the bounded explicit-mapping, exact-value,
complete-population, immutable-source, and deterministic-sampling mechanics on
two unrelated official flat transaction populations. These are expenditure and
payment tables, not complete double-entry general ledgers. The evidence does
not establish accounting-population completeness, professional sample-design
appropriateness, or external-evidence sufficiency.

## Journal Sampling review-successor re-audit 2026-07-25

The earlier review probe showed that an accepted review could write
`applied_decisions.json`, report `final_ready`, and leave the pre-review output
seal stale. The remediated workflow now archives the exact trusted stage before
each save or apply, binds the successor to that predecessor manifest, rederives
all review effects and status fields, reseals the complete file/directory/mode
tree, and replays the full stage chain.

| Evidence | Result |
| --- | --- |
| Complete Journal Sampling suite | 160 passed; 0 failed; 0 errors; 0 skipped |
| JUnit SHA-256 | `350bec6303ff3c79fe76f792409b7e7a14ec025099503fad2aa11479a1eb31c0` |
| Sampling core SHA-256 | `accb85a27a0972fa5c006540152dc20a9450c1f362ef77f804aee20d379e0222` |
| Review-successor bridge SHA-256 | `1e118ef7ab6e0ab129a0625974a6761a0d9065cabe4fb8eec4a4e98314cec037` |
| MCP boundary SHA-256 | `cced0bc9bb96103147da49fa5c5f1e883f7a3b5497c8c38d3a2ecc5112505e77` |
| Static checks | Black, isort, mypy, Bandit, Node syntax, and diff checks passed |

Real save and apply regressions prove the initial-to-save-to-apply chain,
canonical archive names, exact revision paths, freshly blocked successors, and
the permanent limits `semantic_review=not_assessed`, `reporting=blocked`,
`publication=withheld`, and `report_ready=false`. The attack matrix rejects
missing/rogue files, empty directories, links, FIFOs, stale modes, changed
archived bytes or manifests, predecessor rebinding, stale decision/effect
fields, and a rogue file present before archiving.

This establishes internal successor-chain integrity for the bounded sample
review. The archive is local current-tree evidence, not an external signature
or a separately retained checkpoint against wholesale honest-history
substitution before review begins.

## Report Builder public numeric-role probe 2026-07-24

The same receipted 200-row public source was used to test whether exact numeric
transport could still create a semantically false total.

Observed before remediation:

- eleven columns were numerically parseable, including fiscal year, account,
  fund code, vendor ID, payment ID, invoice-line identifiers, and amount;
- the generic report path rendered the first eight as deterministic totals;
- source, prepared, and output values closed exactly, but most columns were
  identifiers rather than measures.

This was a real deterministic/judgment contract failure: reproducible
arithmetic did not make the classification correct.

Observed after remediation:

- all eleven numeric-looking columns remained review candidates;
- without a source-bound measure decision, zero totals were reported and no
  numeric evidence ledger was emitted;
- a reviewed decision bound only `amount` to the exact source receipt, table,
  header row, and column name;
- an independent Polars Decimal sum and the sealed source/prepared/output
  ledger both produced `1121377.07`;
- two independent runs produced byte-identical numeric ledgers, DOCX files,
  and XLSX files;
- repeated hashes were:
  - numeric ledger:
    `459e0add60a3a085e4396f5d5b8b996fab8e1573fd1bbce7c31f9f2b73143a87`;
  - DOCX:
    `e09c6ef9e81155f74b20a7e3a4037fd2cc1c949d5f8584de3d5891e6937081c9`;
  - XLSX:
    `bf37f8bef7bf21eac8d9147c045d1fe247b0c07516e41c953b44c8caa1dad5bd`.

This probe establishes the reviewed numeric-role boundary and replay mechanics
for one public CSV. A subsequent independent adversarial review found that the
same implementation still reused stale ZIP extractions, lost formula/cache
status, allowed incomplete candidate dispositions, and could erase an accepted
artifact edit while reporting readiness. The hashes above are therefore
retained as defect-discovery evidence, not promotion evidence. The case must be
rerun after remediation. It does not satisfy the two-positive-company-report
promotion requirement and does not validate narrative interpretation.

## Report Builder three-company SEC selected-fact evaluation 2026-07-24

The remediated implementation was evaluated against official SEC EDGAR
companyfacts and matching inline-XBRL annual filings. Apple was the
implementation case. Microsoft was a second positive case but had appeared in
an earlier local evaluation and is not labelled a holdout. Nike was first
selected and retrieved only after the implementation and adversarial-remediation
tree was frozen, so it is the post-remediation blind holdout. Source and run
artifacts remain in temporary local paths and are excluded from the Marketplace
package.

| Case | Evaluation role | Exact FY2025 selected facts, USD millions | Repeated ledger / DOCX / XLSX SHA-256 |
| --- | --- | --- | --- |
| Apple | Implementation case | Revenue `416161`; operating income `133050`; net income `112010`; total assets `359241` | `51dd559a1331e6ddbf847aa1a125222cc20a26f7a324272b6546ca3431f7d4c7` / `017d7271d8b18f897328ea811f61516ce1fcf6f6353cdbff665e595c539be019` / `e2ec3d7677924f40863f317bfc8bddbae3e08826a1e77584a68d8b7d37992f98` |
| Microsoft | Second positive, non-holdout | Revenue `281724`; operating income `128528`; net income `101832`; total assets `619003` | `3d56da12f638d57af8f1ea755fcb52e946743abcd68ee0b449a19305bcf0e76b` / `7d0fa9c80918d6f0b8de655e3a0cbcc80a2e8104fc2d38c1de497ecab86f1a2d` / `0b67b4c13d74b85b57e42c0948ba0311e2e6477b155a6f7f7ac05bc145c18e28` |
| Nike | Post-remediation blind holdout | Revenue `46309`; net income `3219`; total assets `36579` | `1400b842bcf539ab37b1da81cdf297326bc796bc5601c75509361ad4c4ae7f28` / `202a33900f2c18a93823fb82589a1101d1f0040c9c032af3a17916b39ed39cac` / `58541313ff447e85d03bd786c87ad0bbf80b8ad6cbdce35b173aff47b3dc4def` |

The official source receipts were:

- Apple
  [companyfacts](https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json)
  SHA-256
  `31f9ab4398402faabc733178497af89dbf94dd5038c6e36d4c894317de8a4647`
  and
  [filing](https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm)
  SHA-256
  `548ae59778cf08ee0f2ee088e7ece20d947076c3c01f74d2d65db4c2777e436a`;
- Microsoft
  [companyfacts](https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json)
  SHA-256
  `352bbb036cbf65b74e126bb7ac040d2a8f9538dc0a85a0363a9a28a22039c4c3`
  and
  [filing](https://www.sec.gov/Archives/edgar/data/789019/000095017025100235/msft-20250630.htm)
  SHA-256
  `99d693f6c1544144ebeee92954f151a85bc62111837530a42855953bc01d0bbe`;
- Nike
  [companyfacts](https://data.sec.gov/api/xbrl/companyfacts/CIK0000320187.json)
  SHA-256
  `54abad8b001c9e08bb81b83c12f30e36867f6462a12e040cc329e94d46e6fc5c`
  and
  [filing](https://www.sec.gov/Archives/edgar/data/320187/000032018725000047/nke-20250531.htm)
  SHA-256
  `ccd82759b90821813fd2efa622c97900d46eafceeaa2586ff82ddd4abdcc6cd1`.

The recorded capture evidence uses local post-capture file modification times:
Apple `2026-07-24T19:54:42+0200` and `2026-07-24T20:14:01+0200`;
Microsoft `2026-07-24T19:54:43+0200` and
`2026-07-24T20:14:02+0200`; Nike `2026-07-24T21:08:53+0200` and
`2026-07-24T21:09:22+0200`. These are local filesystem evidence, not
server-provided retrieval telemetry.

For each case, an independent oracle reopened the exact accession, SEC tag,
USD unit, inline-XBRL scale, and duration or instant context. The selected
current-period cells were explicitly included, all other candidate cells and
columns were disposed, the reviewed scale was `1000000`, and exact
source-to-prepared-to-Markdown/XLSX/DOCX closure passed. Two output directories
produced identical bytes for every deterministic artifact; the audit JSON also
matched after excluding its intentionally unique review-session identifier.

One-dimension mutations of source value, reviewed scale, reviewed unit, report
period, candidate disposition, and rendered numeric text all withheld or
blocked the affected evidence. Separate negatives rejected duplicate canonical
ZIP member identity, rejected a missing selected SEC fact, and retained a
non-text PDF as `unsupported_source_layout` with OCR requested and
accept/skip unavailable.

An independent review passed the M3-M6 mechanics and the M7 representative-case
component. The earlier public numeric-role probe remains defect-discovery
evidence and is superseded by this evaluation for the current mechanics.
The Report Builder retained adversarial regressions and substantive privacy
review subsequently passed; global Vera promotion is still withheld until the
complete test/coverage and release/package gates pass. This evaluation
establishes only exact selected-fact transport through reviewed schedules and
rendered totals. It does not assess professional interpretation, narrative
quality, complete-statement coverage, SEC endorsement, or legal reuse
obligations.

## Report Builder predecessor-checkpoint re-audit 2026-07-25

An independent audit reproduced an alternative-honest-predecessor
substitution: locally replacing a genuine history object and officially
resealing the tree was accepted. The product was then changed to require the
prior `integrity_checkpoint` through an external argument for every later
review and successor validation. The archived predecessor is replayed, and the
checkpoint is enforced by both the isolated Python and MCP surfaces.

| Evidence | Result |
| --- | --- |
| Complete current Report Builder suite | 142 passed; 0 failed; 0 errors; 0 skipped |
| JUnit SHA-256 | `9275abdce81cca3a149fba9357ea43d33f568c43ed00256829ad092aedcb3944` |
| Integrity validator SHA-256 | `89634b47786f67287aa1b06f54381f1019e7c8c47c7c7f1e7daad469531bee34` |
| Successor replay SHA-256 | `97617a6f695429d86c0163bf63bd426b8f786662eca74858458aee0605308135` |
| Physical output-set SHA-256 | `2a7894b2676f3bdf19a4063310e57e4fa00d15c6bd888d884e1167e43272f7d2` |
| MCP boundary SHA-256 | `12c96716ee988fba3dbd4094ca678055386adcaf3655d1e5692c1d6aaccc337e` |
| Static gates | Black, isort, mypy, Bandit, Node syntax, generator parity, and scoped diff checks passed |

The exact reproduced substitution is now retained as a regression and is
rejected against the genuine checkpoint. Missing, malformed, and wrong
checkpoints cannot mutate the tree. These controls establish local transition
continuity only when the operator preserves the checkpoint independently; they
do not authenticate the reviewer or resist replacement of both the complete
package and its external checkpoint channel.

## Check Entries official FatturaPA example 2026-07-24

The illustrative XML in the official
[Docs Italia 18app invoicing guide](https://docs.italia.it/italia/18app/18app-esercenti-docs/it/bozza/linee-guida-fatturazione.html)
was extracted from the guide source and paired with a separately authored,
reviewed one-row native journal. The public source and all run artifacts remain
outside the repository and will not be included in the Marketplace package.

| Evidence | Result |
| --- | --- |
| Retrieved guide-source SHA-256 | `f46d1ff58f89f9901081b1bdaf5ff23dab3bf54548f460486915a10dd55ef658` |
| Extracted illustrative XML SHA-256 | `e4c499220bfadaecf3262d12fff467602aef43c2d42645d5177eed6bcd5407c4` |
| Extracted XML size | 2,983 bytes |
| Reviewed normalized journal SHA-256 | `f6fd685cc10e2d78941ed43d330dbb34596f06f6a71ab45d7f8bf313f71afd21` |
| Strong relationship evidence | invoice number `1`, amount `10`, date `2017-01-10`, currency `EUR` |
| Mechanical result | `ok`; support type `fatturapa_xml`; reconciliation gate `passed` |
| Professional result | semantic gate `withheld`; `report_ready=false` |
| Repeated-result equality | byte-identical normalized-entries and check-results CSV files |

The two independent output directories produced these repeated hashes:

- `normalized_entries.csv`:
  `4a55014aae0596986ebc3ba71f32855f0bf84e200fa4f23619b63c0251411a4e`;
- `check_results.csv`:
  `197be748ff361280c05620a4d0231d4fc3d91333b0ad8379a17ff5985ca8d13b`.

Observed controls:

- the journal entered Check Entries only after Journal Sampling qualification,
  reviewed mapping, exact normalization, and upstream assurance replay;
- the XML relationship used the explicit invoice number plus exact amount,
  date, and currency rather than amount/date coincidence alone;
- source, prepared, and result artifacts were receipted in the assurance
  envelope;
- mechanical success did not promote evidence sufficiency or a professional
  conclusion.

A subsequent independent adversarial review reproduced a support-byte
swap-and-restore attack and showed that this run had no reviewed supplier or
customer perimeter. The mechanical pass is therefore invalidated as promotion
evidence: the hashes remain useful defect-discovery evidence, but the official
example must be rerun against immutable support capture and an exact reviewed
party perimeter. It is not evidence for arbitrary invoices, P7M containers,
OCR-only PDFs, or general professional evidence sufficiency. A second
independently authored multi-line FatturaPA holdout is also still required by
the promotion matrix.

## Check Entries remediated two-case evaluation 2026-07-24

The invalidated result above was rerun after immutable support capture, exact
reviewed party/relationship/currency controls, and a separate reviewed journal
direction contract were implemented. The original public Docs Italia invoice
case and a fresh, independently authored, wholly fictitious multi-line
FatturaPA holdout were each run twice. The holdout oracle was authored without
inspection of the implementation and was not changed after execution.

| Evidence | Result |
| --- | --- |
| Evaluator assertions | 112 passed; 0 failed |
| Evaluator SHA-256 | `8c982094a478d07c4b3d6d0147e1b33db3203c0c39ea2f1113fd0327e0358781` |
| Evaluation-summary SHA-256 | `218d20f6a2443bcd5310c139d7628350a9a6325adfb9875d4071cac527082618` |
| Unchanged holdout-oracle SHA-256 | `5f6ac9e4e57966c5edf536682277944b6488ef70bc75071b9647af382afd55ae` |
| Official case | `ok` in A/B; source, preparation, and reconciliation passed |
| Fresh holdout | `ok` in A/B; journal and support both `-3965`; signed and absolute difference `0` |
| Repeated-result equality | CSV, XLSX, and numeric-ledger artifacts were byte-identical within each A/B pair |
| Professional result | semantic `withheld`; reporting `blocked`; publication `withheld`; `report_ready=false` |

The holdout's direction decision was an exact reviewed
`check_entries_direction` receipt bound to one prepared entry, the captured
support receipt, the exact XML locator, and `credit`. FatturaPA `TD01` remained
diagnostic document polarity and did not determine the journal side. The same
contract has retained regressions proving that `TD01` and `TD04` can support
either a reviewed debit or a reviewed credit line; absent, stale, or opposite
direction decisions cannot emit signed support values or mechanical `ok`.

All preserved negative recipes produced zero `ok` rows or failed before
output: deleted or stale upstream envelope, upstream source mutation,
amount/date coincidence without identity, wrong supplier, currency mismatch,
support reuse, a sole unrelated PDF, and support-byte mutation. This evidence
supports the bounded source-capture, exact-money, reviewed-direction, replay,
and deterministic-output mechanics on these two cases. It does not establish
professional evidence sufficiency, general invoice coverage, P7M support, or
OCR-only PDF support. The public example is an invoice rather than a public
journal. Numeric or otherwise untransported invoice identifiers still require
an exact reviewed support relationship, and semantic, reporting, and
publication conclusions remain withheld.

An independent frozen-byte runtime/security audit then passed the complete
137-test Check Entries file, all ten direction regressions, 37 retained
forgery/status/path cases, 39 additional persisted-result, typed-child, and
direction-bound tamper cases, and twenty historical filesystem/race/sanitized
failure probes. A separate genuine commit regenerated one native workbook,
declared seventeen authorized outputs, verified nine current-byte receipts,
and left only canonical relative trace paths with no staging residue. The
privacy review was updated after that audit; its governed-source fingerprint is
`98921f919926b46de821635e121b52b60c47b5d02c15df0f831f6520d386ce92`.

A later cross-workflow transaction audit invalidated the runtime/security
promotion conclusion above. On a rejected MCP apply, a same-user helper could
rewrite, delete, or replace the sibling rollback snapshot before restoration.
The exact probe restored attacker-written Check Entries bytes, restored the
canonical output as a symlink or FIFO, or removed it entirely while exposing an
absolute recovery path. The two-case arithmetic/direction/replay evaluation
remains evidence for the deterministic analysis path, but Check Entries cannot
be promoted until rollback no longer trusts child-writable disk state, the
attacks are retained as regressions, an independent frozen-byte audit passes
again, and the privacy fingerprint is refreshed after remediation.

## Check Entries successor and output-set re-audit 2026-07-25

The rejected-apply rollback defect and the later dynamic-output discovery gap
were remediated before a fresh root re-audit. The current workflow uses an
in-memory bounded transaction for canonical writes and an exact physical
output contract for the initial run, review transition, and accepted
successor. The expected successor set is derived only from the reviewed effect
perimeter and canonical revision/backup paths; an unexpected regular file is
not added to the inventory.

| Evidence | Result |
| --- | --- |
| Complete Check Entries suite | 189 passed; 0 failed; 0 errors; 0 skipped |
| JUnit SHA-256 | `c32a931df85e2eb55fe1ac623e2fecaee8484422da00bf7a1b20c946b1094d4a` |
| Physical-output validator SHA-256 | `db7476ac9b3ac97101f4f8f27478b74735698403201af73535b5c54e4f07a745` |
| Core SHA-256 | `9aa352ee39593e2e9debd7a61c48109fc1c86d159f4b62abef66f02877d63c50` |
| Apply boundary SHA-256 | `442b02ad809501d27aa21d0cc9ced34697f3a0581aa5143acca915d224760697` |
| MCP boundary SHA-256 | `c5044f59c5c4816d7d70b7d4ddb1d600b3a07fd870b3708f07c86aa5bfc4d1f1` |
| Static checks | Black, isort, mypy, Bandit, Node syntax, and diff checks passed |

The retained matrix includes foreign files before review, a foreign file
injected after review-session generation, pre-existing internal links,
post-preflight link swaps, dangling canonical replacement, hardlink and FIFO
attacks, typed-child failures, exact rollback, source/support mutation, and
fresh successor replay. All rejected operations preserved or restored the
prior canonical tree.

This closes the previously recorded runtime and physical-set blockers for the
bounded product claim. The result does not authenticate the reviewer or an
external checkpoint channel, and an attacker who can replace an entire honest
run plus all of its external source history remains outside the current-tree
self-consistency claim.

## Concordato two-case synthetic evaluation 2026-07-24

Two wholly fictitious workbook bundles were authored independently from the
runtime implementation and kept outside the repository. Each bundle was first
inspected without operative roles, then received a complete reviewed
source-role, currency, unit, and numeric-token disposition receipt. Each
qualified pass was repeated in two output directories and replayed through the
persisted assurance envelope.

| Evidence | Case A | Case B |
| --- | --- | --- |
| Raw numeric candidates | 8 | 7 |
| Explicitly excluded non-amount candidates | 3 | 2 |
| Exact plan amounts matched | `100000`; `-12500.5` | `345678.91`; `45000` |
| Unmatched prospective amount | `50000` | `123456.78` |
| Repeated mechanical-result SHA-256 | `643fbe9688982372d156a74bd4c9b2673a34fd5ad0271220dca9dff87c4d7a85` | `a2adc5d5acac73123dcc6e2603f3ffe194cc84f31be47dcdbec352684aa2759b` |
| Repeated numeric-ledger SHA-256 | `7124d9c3a33bf31727f4d5fd93bff14ad56f8d17cad12525104c198377d6e61b` | `f043f4928283fd46846064aecc76510f7ece375b90f3f8b3e734ba5e77c9e241` |
| Repeated tie-out workbook SHA-256 | `9adac5ff43eb1eb3c582007f5bbd8e436ede26fc62f0049350b3fc3cbe208e1a` | `b9dc958d7fb8ac9d7e7d510eae7ea5a9c961d12a3aeabf5a8f3f065a72eecbad` |
| Repeated Word summary SHA-256 | `ffc040cc865cdc36985cf0e070a31200476fdcb9dc7c4d2d2aa7a79b7a852053` | `64b122d738b73f02342586d761dd61cc9e2c5fb6b79570f5a5e2051ac85b8b54` |

In Case A, a support-side account code equalled the plan's prospective amount.
In Case B, a practice identifier equalled the prospective amount. Both were
explicitly disposed as non-amounts and therefore created no false support.
Additional pipeline negatives established:

- a one-cent difference produced zero exact matches at zero tolerance;
- a plan-only bundle produced an unmatched amount and never became
  report-ready;
- a workbook exceeding the reviewed row budget became
  `unsupported_source_layout` and emitted zero candidates;
- prospective values never received a semantic category from deterministic
  matching.

Both cases passed source, preparation, and mechanical reconciliation gates.
Semantic review remained `withheld`, reporting `blocked`, publication
`withheld`, and `report_ready=false`. This satisfies the two-case requirement
for exact candidate arithmetic and replay on these bounded synthetic workbook
layouts. It does not prove real-plan generality, legal/tax framing, support
sufficiency, or going-concern conclusions; a rights-cleared real corporate case
is still required before any such claim.

## Concordato closure and successor re-audit 2026-07-25

The current implementation was independently re-audited against the normative
Concordato workflow reference after the synthetic evaluation. The audit
exercised the exact implementation perimeter, reviewed formula authority,
complete material-value address ledger, whole-output closure, standalone
replay, bounded review transaction, and review-successor chain.

| Evidence | Result |
| --- | --- |
| Complete Concordato suite | 103 passed; 0 failed; 0 errors; 0 skipped |
| JUnit SHA-256 | `d336a797f42a7a43af3e924650159817c70708fa7d4d84764fb5183d11c99b9a` |
| Production core SHA-256 | `69313a8663fbf511d095ee96ca813fe278fce7db706bd8725b41ea608c55b1f6` |
| Implementation bootstrap SHA-256 | `2d236a29edb6dc788adcbc1463d26149fb708a4a80b53ffa9d597c6073212397` |
| Output closure SHA-256 | `a711c95bc3461491dfde77b45c11ff00fe41b1e1a6fe8d9b83e14dae8aafa340` |
| Standalone replay SHA-256 | `5ba76365fb142814364cf99e51d0a631cdb7468cf70206483f6f159e75b3ec13` |
| Successor finalizer SHA-256 | `e0f42e9702ecad4bcbfe1021c2ad399f4ed39aae952b2fbd6916d74f43822b03` |
| Reviewed-authority command SHA-256 | `e316765768467ff86021bbfa301bf71e2767b431b1dbd3e7773ac1210a5ef0dd` |
| MCP boundary SHA-256 | `964f747a43a09351ce8cccc47218add59b6267fb4e5c586933f77008c0e2db15` |
| Static gates | Black, isort, mypy, Bandit, Node syntax, and diff checks passed |

The retained attacks reject stale or forged formula/source authority,
candidate-perimeter reorder, any unowned implementation entry, numeric-ledger
and rendered-value forgery, last-row CSV/XLSX/DOCX mutation, unexpected files
and directories, symlinks, hardlinks, FIFOs, late artifact mutation, forged
successors, stale parent receipts, child self-authorization, and failed
transaction writes without preserving residue. Accepted save and apply
transitions seal a new closure bound to the exact predecessor and never set
professional readiness.

This closes the recorded implementation, output-set, material-address,
formula-authority, replay, and successor gaps for the bounded synthetic
contract. It is not representative evidence for a real corporate plan. A
rights-cleared real case selected outside the implementation remains required
before claiming generality across real plans.

## Journal–Bank blind cross-layout evaluation 2026-07-25

An oracle author who did not inspect or run the current repository
implementation sealed two temporary cases before execution. Case A used the
official NatWest Bankline CSV layout and a synthetic projection from a
rights-cleared HMRC public transaction population. Case B used newly authored
synthetic rows faithful to the official 24-column Westpac BankRec Extended CSV
schema. Official layout material and the temporary Westpac-derived evaluation
remain outside the repository and Marketplace package.

| Evidence | Result |
| --- | --- |
| Frozen-bundle manifest SHA-256 | `9f0c55075ec9d1b5c8299af820d56bb63b312ddda28118dc8c3f1ba280a9c970` |
| Evaluator report SHA-256 | `7dafe64c4fe8e6ee4a0f4782cedb7b9de1c8ca271333c0bddff37b98155fc4cc` |
| Assertion ledger SHA-256 | `6cfdab5f611bff284052417669ae1f8501d949a3b7e3756a2c8a4fc3bf134202` |
| Total assertions | 523 passed; 4 failed; 336 not evaluated |
| Case A | 216/216 passed across two fresh runs |
| Case A repeatability | all eight semantic categories and reviewed-recipe bytes passed |
| Case B | blocked twice as `unsupported_source_layout`; zero prepared or reconciliation rows |
| Full frozen implementation test file | 168 passed with the bundled Node runtime |
| Promotion result | withheld |

Case A produced six bank and six journal rows, five exact explicit-reference
allocations, one residual on each side, exact Decimal totals, physical lineage,
and withheld reconciliation, semantic, reporting, and publication readiness.

Case B exposed two separate problems. First, Westpac's official compact
`YYYYMMDD` date representation was not supported by the current bounded
tabular adapter, so its bank source emitted zero rows before matching. Second,
the frozen oracle was authored against the installed Vera 0.1.30 workflow,
which still documented `beneficiary` and `description_tokens` match stages.
The current repository contract intentionally permits only explicit
`reference`, `amount_date_unique`, and `amount_date_single`; beneficiary and
description remain review context. The obsolete text-based expectations are
therefore contract drift, not a reason to restore inferential matching.

Because Case B and its ten derived tabular negatives never reached the matcher,
their 336 target assertions remain unevaluated even though every run failed
closed. This evaluation is retained as defect-discovery evidence and is not
relabelled as a pass.

The mechanically unambiguous transport gap was remediated separately:
tabular adapter v3 accepts valid compact ISO dates, rejects invalid calendar
values such as `20260231`, and invalidates v2 mapping receipts. The focused
positive and negative regressions pass, and the complete Journal–Bank file
passes 170 tests after the change. A new blind Westpac holdout authored solely
against the current explicit-reference/amount-date contract is still required
before Journal–Bank representative promotion.

## Journal–Bank successor blind evaluation 2026-07-25

A second author who did not inspect or run the repository implementation
sealed a fresh Westpac Extended CSV case against the current three-stage
matching contract. The bundle remained byte-identical before and after two
base runs and eleven independently generated mutation scenarios.

| Evidence | Result |
| --- | --- |
| Frozen-bundle manifest SHA-256 | `d03ca7c0acb7ff1f57cfe3a7ee305c34d55c52b587d532ad5442ffc30e60f8b4` |
| Detached bundle anchor SHA-256 | `3573133125bca01393fcb055e4c206c7a35427ab2df392c44c101356cbb5260b` |
| Evaluator report SHA-256 | `a0ee1b34432bfc748e5ed46ab29f4b58f15b613aaf9fd66e312e7e32895e0c2f` |
| Assertion ledger SHA-256 | `90758ba8b5106e9f687f9a9e0273578d4b28359112f011ba8bc2f48dc0fdbb68` |
| Atomic assertions | 778 passed; 184 failed; 12 not evaluated |
| Base runs | both qualified and normalized 6 bank plus 6 journal rows; both produced 0 matches and 6 plus 6 unmatched |
| Repeatability | passed for the identical but incorrect zero-match result |
| Mutation execution | all 9 recipes and all 11 executable scenarios completed |
| Promotion result | withheld |

Compact `YYYYMMDD` dates qualified correctly. The failure was instead a real
mapping-contract gap: the journal mapping retained raw `debit` and `credit`
values while `same_sign` matching accepted only canonical `positive`,
`negative`, or `zero`. Every candidate was rejected before stage selection.
The intended two-by-two ambiguity therefore remained unmatched for the wrong
reason. Repeatability, current-byte receipts, and a workbook that reproduced
the current CSVs did not cure the wrong pair membership.

The same evaluation found a separate output-closure defect:
`final_artifacts.json` was assembled before the final audit, artifact-receipt
bundle, review handoff, and assurance envelope had settled. It consequently
contained stale byte counts and omitted the late assurance envelope. That
finding is retained independently of the direction failure.

The direction gap was remediated in tabular adapter v4. A non-canonical
direction column now requires a complete source-bound vocabulary mapping to
canonical signs, every mapped direction must agree with the exact signed
amount, and changed vocabularies invalidate the reviewed mapping receipt.
Focused positive, abstention, conflict, stale-receipt, and compact-date
regressions pass; the complete Journal–Bank file passes 174 tests. This is
implementation evidence, not representative promotion. A third clean-room v4
holdout and current-output closure remediation remain required.

## Journal–Bank v4 clean-room evaluation and contract audit 2026-07-25

A third independently authored synthetic Westpac Extended case was sealed
before the repository implementation was run. The bundle contained twelve bank
rows, twelve journal rows, a complete source-specific direction vocabulary,
twelve negative scenarios, two repeatability runs, and a hidden row-level
oracle. Both candidate runs were frozen read-only before the oracle was opened.

| Evidence | Result |
| --- | --- |
| Bundle self-validation | 94/94 before and after evaluation |
| Frozen manifest SHA-256 | `68ac99aac11deb1fb2c696760d315d61dd4c0d8120753984191c47dc073483d6` |
| Detached root-seal SHA-256 | `52cb403cd4d2f1f9d69af7dea61fd254ae89aa25302910c281cce9f57856a4bb` |
| Evaluation JSON SHA-256 | `f8c3a0ddce7c57543863ab6f0fe9410749d1618cfcfa0b8b5dc843a7408b6bee` |
| Evaluation Markdown SHA-256 | `1acf6a727b9065980762e28f3954cc60e5ff206c47bbcf28db4e82cc5dffb330` |
| Result-ledger SHA-256 | `fe6731435e10e1a7dff07ea3de3fc9ebd71cd3aaf11d3a57b40d10c83c3877ba` |
| Base normalization and pair identity | 12/12 bank rows, 12/12 journal rows, and 9/9 pairs exact |
| Base residuals and gates | 3 plus 3 unmatched; all six independent gate statuses exact; `report_ready=false` |
| Negative threats | 11/12 exact holdout outcomes; the remaining scenario also rejected the forbidden reference token |
| Core repeatability | normalized CSVs, matches, unmatched partitions, relationship ledger, and gates byte-identical |
| Promotion result | withheld |

This run found two valid implementation defects independently of the hidden
row expectations:

- the row-wise `amount_date_unique` pass consumed later singleton candidates,
  making the documented `amount_date_single` stage effectively unreachable;
- logically identical workbooks had different ZIP timestamps and
  `docProps/core.xml` values, so the XLSX and its dependent receipts were not
  byte-repeatable.

The post-run concordance audit also found that the holdout author had invented
requirements that were not the repository's product contract. The holdout
required same-day `amount_date_unique`, a source-wide signature definition for
`amount_date_single`, date-window sufficiency for explicit-reference matches,
a four-sheet capitalized workbook, a standalone `totals.json`, and
`report_ready=true` in one scenario despite semantic review remaining
unassessed. Vera's published contract instead permits actual dates inside the
reviewed window, defines the later stage by residual candidate elimination,
allows a stable explicit identifier when date evidence is absent, retains the
native six-sheet workbook and audit/relationship totals, and keeps semantic
readiness independent.

Those comparisons are evaluation-contract drift, not reasons to change Vera
to the invented oracle. The exact normalization, pair identities, residuals,
gates, direction controls, source-byte replay, cross-currency exclusion,
one-to-one reuse rejection, ambiguity preservation, forbidden-text exclusion,
and workbook-tamper rejection remain useful evidence. They are not promotion
evidence because the evaluation contract itself was not product-concordant.

The two valid implementation defects require retained regressions. A successor
blind case must receive a frozen machine-readable copy of Vera's exact
relationship, native-output, readiness, and repeatability contract before it
is authored; the oracle author may vary the data but may not redefine the
product.

The repository defects were remediated separately without adopting the
drifted oracle. Relationship adapter v2 selects each matching wave from an
unchanged residual snapshot, accepts only unconflicted singleton targets, and
labels only later amount/date waves `amount_date_single`; v1 relationship
receipts are stale. OOXML core timestamps, member order, and ZIP timestamps are
now normalized, and duplicate members are rejected. Forward/reverse collision,
later-wave, stale-receipt, logical-workbook, and byte-repeatability regressions
pass; the complete Journal–Bank file passes 183 tests.

The frozen successor-author contract is
`journal-bank-evaluation-contract.v2.json`, SHA-256
`183d3bcae2a0674c637e55c26a76fca7c1647732b3b51979f160a2b1bccd6944`.
It requires logical workbook closure to the native six-sheet package and byte
identity between equivalent candidate runs; it expressly does not require an
independently invented OOXML package. These are implementation and evaluation
protocol results, not representative promotion.

## Journal–Bank contract-v2 successor pre-oracle block 2026-07-25

A fresh context-free author received only the frozen v2 product contract and
the public workflow layout documentation. The resulting synthetic Aurora
bundle passed its public structural and contract-concordance checks before a
separate evaluator ran the repository implementation. The evaluator froze two
independent candidates read-only before attempting the oracle boundary.

| Evidence | Result |
| --- | --- |
| Detached root-seal SHA-256 | `c1919a5481b71056f31c3ae0aa739b9801eb9637c26c99c120a741963ec18724` |
| Public concordance SHA-256 | `f47f1f67f1be1a6b60e25471887acbf04f8c6940cd993ee4c11d93ce19ef75cb` |
| Public-only self-validation | 434/434 |
| Full author self-validation | 501/501 |
| Candidate A tree SHA-256 | `0dc444b4747bf7e201112e5ce9f68bda1a890991a204435f2c4235b8ad8b51eb` |
| Candidate B tree SHA-256 | `f11dc9162923e0e5ee906532fea5c8881921b735247578159cedbec53e7e4d1d` |
| Available deterministic surface | 6/6 emitted files byte-identical |
| Required deterministic surface | 8/14 files absent in both blocked runs |
| Oracle access | prohibited; no pre-open candidate receipt could close |
| Promotion result | withheld |

Both official runs failed closed before reconciliation. The bank source
reported thirteen candidates but emitted zero rows because the public reviewed
intent omitted dispositions for `Closing balance` and `Value Date`. Supplying
those exclusions would have required evaluator judgment and was therefore not
permitted. The semicolon-delimited journal was read as one composite column,
reported zero candidate rows, and lacked every declared field.

The evidence separates three issues:

- the holdout's public reviewed intent was incomplete because it omitted the
  complete potential-monetary-column disposition required by the executable
  adapter;
- the frozen contract used the ambiguous phrase `separator convention`
  without distinguishing CSV field delimiters from decimal and thousands
  separators; and
- the implementation advertised generic CSV input while `_read_csv_raw`
  always used Polars' default comma delimiter and ignored the reviewed
  semicolon declaration.

A diagnostic with evaluator-inferred bank exclusions qualified the bank
thirteen of thirteen but still left the journal at zero rows. It is retained
only to isolate the delimiter defect and is not pass evidence. The hidden
oracle and its twenty negative outcomes remain unknown.

The v2 contract and this blocked result remain historical evidence. Remediation
requires a versioned tabular adapter with an explicit bounded CSV field-
delimiter decision, a new machine-readable contract that separately requires
complete monetary dispositions, and a newly sealed successor holdout. The
existing oracle must not be retrofitted or relabelled as a pass.

## Journal–Bank contract-v3 successor pre-oracle block 2026-07-25

A new context-free author received only immutable contract v3 and public
primary-source layout documentation. The author produced a read-only
First-National-Bank-layout synthetic bundle with two positive sources,
thirteen isolated negatives, separate public and oracle manifests, and a
self-validating oracle. A different context-free evaluator verified every
declared bundle byte and mode but was prohibited from reading oracle content.

The evaluator completed initial inspection and built both v5 mapping receipts.
It could not build the required relationship receipt: public reviewed intent
used
`signed_amount_controls_after_reviewed_vocabulary_mapping`, while production
accepts only `absolute_amount`, `same_sign`, or `opposite_sign`. Contract v3
required `direction_policy` but did not enumerate those values or their exact
eligibility semantics. Selecting one would have invented missing professional
intent, so candidate execution and all oracle access were correctly withheld.

| Evidence | Result |
| --- | --- |
| Author bundle root-seal SHA-256 | `785365826024977209ad7390c7756c409639335f83d66f5c00eac803a3952d89` |
| Contract-v3 SHA-256 | `13b7f430805767962f7c531872cd8d91b6bb68adc74ff895acb0e6b3a2e99046` |
| Public-manifest SHA-256 | `5a40d383117c371eb61058aecd0f9a3909d224f69e4d76fb59fadfea0b4787bd` |
| Oracle-manifest SHA-256 | `cc264637fbda7bfec0c79adcabda801a501ab982481253bfd62520e56012af2a` |
| Bundle inventory | 71 files / 400,400 bytes |
| Initial positive inspection | bank 0, journal 0, both `needs_review` |
| Current mapping receipts built | 2 |
| Current relationship receipts built | 0 |
| Candidate A/B | not created |
| Public negative scenarios executed | 0/13 |
| Oracle validator executions | 0 |
| Pre-oracle receipt SHA-256 | `9827e2291c020d0d22b6adac8e5a062d817cb7664bb1bff9f9ad111d019b495f` |
| Evaluator final tree SHA-256 | `5ff797b23d0df51da5d5b965cecb9778769774b37c0ab9ca81eb2917d498cfd5` |
| Promotion result | withheld |

The evaluator access ledger SHA-256 is
`3580a13b28c76be59d59ec3a07799ebdb44894a7086cd94d98cda50156b4d27c`.
It records hash/stat-only access to oracle bytes, no parsing, printing,
importing, execution, or authorization transition. This block is jointly:

- a public-fixture defect because its free-text policy is not executable; and
- a contract ambiguity because v3 supplied no allowed policy vocabulary from
  which a blind author could choose.

It is not implementation-failure evidence and it is not oracle drift; neither
candidate nor oracle behavior was observed. Contract v3 and the entire sealed
bundle remain immutable pre-oracle evidence. They must not be patched,
relabelled, or used as a promotion case.

The successor contract must enumerate every executable relationship direction
policy and its exact semantics. A fresh bundle must be authored from that
versioned contract and evaluated through the same two-phase protocol.

## Journal–Bank contract-v4 r3 adjudicated mechanical regression 2026-07-25

The contract-v4 r2 evaluator reached the exact oracle after its public phase
passed. Its final `NO-GO` was isolated to oracle drift: five unique match
amount fields had been converted from signed endpoint values to non-negative
magnitudes, and the ambiguous/unsupported delimiter cases used failure labels
that contradicted the retained production tests and workflow contract.

An evidence-first adjudication preserved production behavior and the complete
public tree. R3 changed only the private semantic expectations, their scoring
contract and construction validator, the adjudication receipt, and the
dependent manifests/seal.

| Evidence | Result |
| --- | --- |
| R3 public-manifest SHA-256 | `f441bf8817c92210976b9d8d707764cc916ae07b8ad41eae3679683ab2901f61` |
| R3 oracle-manifest SHA-256 | `877eb4b585c8e410b1ce5a97d870bcc477d5a19cc610027a437afdaa784c6404` |
| R3 root-manifest SHA-256 | `92fa932ec1bf5a03cfa4b5f6565b13faeb4f665c1a73d9b5a907a42162bcab74` |
| R3 root-seal file SHA-256 | `433ab084f62363a0509c332e487eed139c979af43944b67f192723a54edc9ebc` |
| Sealed adjudication-receipt SHA-256 | `5d1b38fc78fa6d938ce92faf39b9af513b322abef16e58fee281e5311eb6651d` |
| Construction validation | public 1,511 checks; full 1,561 checks; 136 files / 541,226 bytes |
| Mechanical regression result | `GO` |
| M7 promotion result | `NO-GO` |

R3 is regression evidence, not a fresh unseen holdout: its oracle is an
adjudicated successor to already-inspected contract-v4 evidence. Prospective
contract v5 now states the signed-source/magnitude split and exact delimiter
taxonomy directly. Its SHA-256 is
`4824652ecdb990a844fd9b72d799a2537f46a21ddb9fefb8a664f828c0ec6657`.
V5 is frozen but not promoted. A newly authored unseen holdout bound to those
exact v5 bytes is still required before Journal–Bank can pass M7.

## Journal–Bank contract-v5 v7 holdout and adjudication 2026-07-25

The v7 author bundle was sealed against the exact prospective v5 contract
before candidate execution. The public packet contained eighteen cases and the
candidate produced two equivalent runs per case. Candidate outputs were sealed
before the hidden evaluator was opened. The author disclosed that the bundle
was recovered through an authoring chain rather than two demonstrably blind,
independent oracle authors; this is a limitation in addition to the observed
result.

| Evidence | Result |
| --- | --- |
| Contract v5 SHA-256 | `4824652ecdb990a844fd9b72d799a2537f46a21ddb9fefb8a664f828c0ec6657` |
| Author bundle root SHA-256 | `07d15685607b4322f00200f19b2e09648770e20302198477b22d833518de4f80` |
| Public phase root SHA-256 | `ab2e27bda23bbe673b7e1125573bb99249bdee314e56abb6548a0644957820c4` |
| Hidden phase root SHA-256 | `22e9c55628822b386416ce272d1a49559314ec8cd8ba20ffbae5e65fd20a5f38` |
| Original candidate submission root SHA-256 | `c2783ee2e52447c89e72f5b0648ef800596cc3a3a5faeb987daff052c0948f1b` |
| Original evaluation report SHA-256 | `1b6c6f1eec548fd26be5650c509649fee588daf640753e3aac6ac10ef252b34a` |
| Original hidden result | 0/18 cases passed; every A/B pair was byte-repeatable |
| Product remediation regression | 299/299 tests passed; 0 failures, errors, or skips |
| Exposed diagnostic submission root SHA-256 | `c74768b087cf287bd14b8640ae7d4586ff4ae55875e686cca0cd91777a98a03b` |
| Exposed diagnostic report SHA-256 | `2e2e75022e20a51e2a4887d9814a6e4424cd380c8c61c7cdcdf9c07942f23573` |
| M7 promotion result | `NO-GO` |

The first hidden run found one product-contract defect: a blocked initial run
persisted only ten files instead of the complete initial native package. The
run already abstained from matching, but its missing empty/native review
artifacts made the block less reviewable and violated the frozen output-set
contract. Blocked runs now persist the exact initial package except
`material_value_ledger.json`, whose absence is explicitly required when source
qualification or relationship authority blocks. Their normalized and unmatched
partitions, empty matches and residuals, workbook, blocked relationship ledger,
review payload, handoff, receipts, envelope, and final artifact closure are
retained. `source_qualifications.json` also exposes an explicit per-side
condition outcome while the shared source-qualification records remain
unchanged and independently validated.

The exposed post-remediation rerun removed all native-output-set and
source-outcome-reader failures except case 002, where the evaluator considered
an authority containing an unobserved `Z` direction label valid. Production
correctly rejected that extra label under v5's
`unknown_or_extra_labels_withhold_source` rule and therefore correctly omitted
the material ledger.

The other remaining comparisons are not product-concordant:

- the evaluator expected only the numeric fragment of `INV-41001`,
  `PAY-55002`, and `MOV-66006`, while v5's exact token rules also retain their
  non-generic compact forms;
- it expected `entity_ref` and `party_ref` on allocation rows even though v5
  fixes `vera.allocation_ledger.v1`, whose allocation record has no such
  fields; the values remain present on source/target records and exact residual
  rows;
- its material reader did not recognize production's `dataset_id`,
  `canonical_value`, `prepared`, and two-entry `outputs` representation, even
  though the production validator freshly replays every declared CSV and XLSX
  address and v5 does not prescribe those internal key names;
- it searched `assurance_gates.json` for `run_block_code`, although v5 does not
  assign that field to the gate-register schema and production records it in
  `reconciliation_audit.json`.

The sealed v7 result remains an immutable `NO-GO`; the exposed diagnostic is
regression/adjudication evidence only. Neither is relabelled as a pass.
Journal–Bank still requires a new independently authored unseen holdout that
uses the exact production schemas and v5 bytes, with evaluator concordance
checked before hidden expectations are sealed.

## Journal–Bank contract-v5 sealed successor holdout 2026-07-25

A new synthetic, non-identifying and rights-clear holdout was independently
authored from the exact frozen v5 contract. The public packet contained two
positive cases, eighteen pre-run or in-run negative cases, and four native
output mutations. The candidate process received only a read-only copy of the
public packet; network access and all access to the original sealed bundle,
private oracle, and author metadata were denied. Candidate outputs and the
no-oracle-access ledger were sealed before oracle release.

| Evidence | Result |
| --- | --- |
| Contract v5 SHA-256 | `4824652ecdb990a844fd9b72d799a2537f46a21ddb9fefb8a664f828c0ec6657` |
| Bundle-manifest/root-seal SHA-256 | `c7e9076a1907dcd20f1574cf3f83bd24ba5ad374a6e991af071ea51021542714` |
| Public-manifest SHA-256 | `ff5c2a90f43befcc01ea492be21500a5086e3eee4fc35cf0df7bf874cdefe6dd` |
| Oracle-manifest SHA-256 | `4e080ebc5b1af3a394f1efd1e3973b77549a91b52b64b9bad5718b091d329188` |
| Candidate implementation SHA-256 | `f94653f03785c27b85688160478974d9eae6a4f9917a06ccbac688dbb27f375f` |
| Candidate-phase seal SHA-256 | `c21cf94b332e552b8c279a0536f16504a053036a8d95bc2ff6f01302f45ada90` |
| Comparison-input seal SHA-256 | `05674081c7718b3cd02eeea8e73c17e14ce2a6697c54a818a80334171d3c3c03` |
| Adjudication artifact SHA-256 | `1988a5a597670ac6d8397a810e13dcfc154148fac16a877ee7646a72ecdf522c` |
| Final no-oracle ledger SHA-256 | `df1d40e708aacac37680fd9a275ad4f85c55fa8a5ed8815689229fe448ef6b59` |
| Ledger schema validation | passed |
| Positive repeatability | both cases; all fourteen declared paths byte-identical across A/B runs |
| Native-output mutation result | 4/4 rejected fail-closed |
| Exact adjudication | 23/24 passed; `NO-GO` |

The only mismatch was `N18_mid_run_source_membership`. The workflow correctly
blocked, cleared the normalized bank output, recorded the changed `late.csv`,
and emitted no match. Its source-qualification artifact nevertheless retained
the pre-change bank outcome of one emitted row with no failure kind. That
contradicted the final zero-row state and the frozen fail-closed contract.

The affected-root rule was corrected: any byte or membership change within a
bank or journal source root now marks every diagnostic for that root as
`unsupported_source_layout`, reports `source_changed_during_run`, and records
zero emitted rows. A focused byte-change regression and a new membership-change
regression pass. At that checkpoint, the complete Journal–Bank file collected
300 tests: 211 passed, 89 dependency-gated cases skipped, and none failed or
errored. Its retained JUnit SHA-256 is
`589c42af248f03d68a102924aa1abe136067cce284ad50883c0a0d2c121bbb35`.
The later additive-v7 extension increases the current file to 317 collected
cases; its separate current-tree record appears below.

A post-exposure replay of N18 confirms the corrected source outcome, failed
source gate, zero-row normalized bank CSV, and block code. Its
`source_qualifications.json`, `reconciliation_audit.json`, and empty normalized
CSV hashes are respectively
`4fbb2acab2c27790327a5f9928032cea5a56fca719c68dbfc601dc1e80084388`,
`7c1fbfd37e8f17d3d3e36202838ba4061194994b5e78d4f1b531596737cdfa7d`,
and `20dc85bc2f4118803d8ab87c8cf57342ac4b623c9c0c34e11473aae87640f73f`.
This replay is regression evidence only because the oracle was already
exposed. The sealed 23/24 result remains immutable `NO-GO`; promotion requires
a fresh independently authored unseen successor.

## Journal–Bank private real-source qualification diagnostic 2026-07-25

With the user's authorization, one private monthly bank export and its
corresponding journal ledger were retrieved from the user's mailbox into a
restricted temporary evaluation directory. No source, recipe, normalized row,
or output artifact is retained in the repository or Marketplace package. This
case is diagnostic only: the source family and result were visible to the
implementation process, no independent oracle was sealed, and no professional
reviewer participated.

| Evidence | Result |
| --- | --- |
| Anonymous bank-source receipt | 88,064 bytes; SHA-256 `eedd2c5ab1f1fca36f2dabff17f3cec231c41a6a27d6da165d14c76d26fe4f61` |
| Anonymous journal-source receipt | 607,962 bytes; SHA-256 `d7df1fade3fad7bbdb9f55a01ba08d94f8dd66e79a9776a5b1159e1c6a7f0b98` |
| Reviewed diagnostic recipe SHA-256 | `bc5848fd545d385fa766ab1d9a0cc386e12dc6c06f3cb520e223d458966b27b8` |
| Unreviewed inspection | 0 bank rows; 0 journal rows; `needs_review` |
| Reviewed journal qualification | 8,141 candidates; 8,141 emitted; all candidate rows disposed |
| Reviewed bank qualification | 203 monetary candidates; 0 emitted; `unsupported_source_layout` |
| Bank row dispositions | 202 invalid date values; 1 missing date without stable reference; 1 additional non-monetary row excluded |
| Workflow result | `unsupported_source_layout`; 0 matches; 8,141 unmatched journal rows; `report_ready=false` |
| Native blocked package | 23 files; 2 source and 20 output receipts replayed |
| Assurance replay | passed; 41 envelope receipts, including 23 exact implementation receipts |
| Assurance-envelope content SHA-256 | `d51af46ebdc1a2dbaa72fc413c0925731930c465963db8427de8fbbdee437a0a` |
| Temporary package root SHA-256 | `02694eba456cbff44e0994a11113456058d35dcef5f603cb12eea42f205a09f2` |

The bank source used populated localized textual-month dates. The frozen
tabular-v6 date contract parsed none of the 202 populated date values, so the
source gate failed, preparation and reconciliation blocked, the normalized
bank and match partitions remained empty, and no
`material_value_ledger.json` was emitted. The complete blocked review package,
including the qualified journal partition and empty bank/match partitions,
remained receipted and replayable. This was the intended fail-closed behavior
for a source outside the bounded adapter-v6 contract, not a defect against the
immutable v5 evaluation contract.

### Authorized additive v7 capability follow-up

The user then authorized a separate production capability extension. The
default adapter-v6 contract and its evidence were left unchanged. The additive
contract was frozen first in
`journal-bank-tabular-v7-extension-contract.v1.json` with SHA-256
`74f779325acf234cbbf126b2060d43ea63a2788f6f645d36a750cd3ec4910347`.
Adapter v7 is selected only by a current source-bound mapping receipt that
explicitly contains `date_locale: it` or an exact reviewed
`non_movement_summary_labels` list.

The implementation accepts only the frozen full Italian month vocabulary,
horizontal-space variants, four-digit years, and valid Gregorian dates.
Unknown, abbreviated, mixed-language, embedded, or invalid forms fail the
complete source. A reviewed summary label remains a semantic reviewer
decision: deterministic code applies it only by exact normalized equality on a
blank-date row with no stable explicit reference. An actual date, stable
reference, substring, fuzzy match, or stale receipt cannot exclude a row.
There is no model repair or silent locale fallback.

The private source was then rerun from a fresh v7 recipe and current
implementation receipts:

| Evidence | Result |
| --- | --- |
| Frozen additive v7 contract | SHA-256 `74f779325acf234cbbf126b2060d43ea63a2788f6f645d36a750cd3ec4910347`; prospective; not promoted |
| Reviewed v7 diagnostic recipe | SHA-256 `4b14a7d31a47e61d53ee0b923f4259fafa7fddbd4ce390c996628bbff3e27843` |
| Qualified bank population | 203 populated monetary source rows; 1 exact reviewed non-movement summary excluded; 202 candidate movements emitted |
| Qualified journal population | 8,141/8,141 candidate movements emitted |
| Deterministic relationship output | 36 `amount_date_unique` candidate matches; 166 unmatched bank rows; 8,105 unmatched journal rows; 8,343 exact relationship residual rows |
| Gate outcome | source and preparation passed; reconciliation withheld; semantic review not assessed; reporting and publication blocked; `report_ready=false` |
| Material-value replay | 83,826/83,826 prepared-to-CSV/XLSX entries replayed |
| Assurance replay | passed; 42 envelope receipts, including the exact 23-file implementation perimeter |
| Receipt bundle | 2 source and 21 output receipts replayed; 24 files in the run package |
| Assurance-envelope content SHA-256 | `059d2b601df98ba0a4cb50483bab4931df5536eae7c630bd7ce3eb2dcf27bd24` |
| Canonical package-manifest SHA-256 | `82c7865b7cb99d07b8775544569a448f40bbf0621e50e6cbeea54953c1f8a083` |
| Complete Journal–Bank regression | 317 collected; 228 passed; 89 dependency-gated skips; 0 failures/errors; JUnit SHA-256 `539b3461b4729b003070c17796a1ed1a8f4a63b48b87b1950a9a4e1a4dbe248b` |

The material XLSX replay originally scaled poorly because a read-only worksheet
was accessed through repeated random cells. It now traverses every required row
sequentially while retaining the exact worksheet, dimension, duplicate-member,
CSV, XLSX, receipt, and material-value checks. The full private run and replay
complete on the complete population rather than a sample.

The 36 deterministic pairs are candidate matches under the reviewed
relationship perimeter, not a professional accounting conclusion. The
unmatched rows and residuals correctly keep reconciliation and reporting
withheld. This case remains diagnostic only: the implementation process knew
the source family, the reviewer identity is not independent, and no hidden
oracle was sealed. Additional statements from the same correspondence remain
ineligible as independent holdouts. Neither this result nor the v7 extension
promotes the frozen v5 Journal–Bank contract; v7 itself also requires a fresh
independently authored unseen holdout before any representative promotion
claim.

## Concordato official-court filing bounded real-source probe 2026-07-25

A 120-page corporate concordato plan was obtained from the official
[Tribunale di Isernia filing](https://tribunale-isernia.giustizia.it/cmsresources/cms/documents/piano_concordato_def.pdf).
The source PDF and all run artifacts remain outside the repository and
Marketplace package.

The bounded evaluation mechanically projected filing page 116, containing the
accounting reconciliation, and page 117, containing the concordato debt plan,
into two separately receipted PDF inputs. The first unreviewed pass inspected
both inputs while correctly emitting zero authoritative candidates and zero
matches.

That inspection exposed a real parser defect: an Italian currency token such as
`€ 1.730.547,50` was split into `1` and `730.547,50`. The currency-token
grammar was corrected to preserve grouped thousands before the decimal comma,
and a focused public-behaviour regression was added before the case was rerun.

| Evidence | Result |
| --- | --- |
| Original official PDF | 799,698 bytes; 120 pages; SHA-256 `ba4a3982a8f641c391cf71ab2c9f1daed7dce420b57eb8ddb0cb6d162c1d61fc` |
| Accounting-reconciliation page projection | SHA-256 `85aad436904abf90bef24599b52d536d895a1b0ce5e520ae1c0dabc5bc108070` |
| Concordato-plan page projection | SHA-256 `31a2037aefaadc87619b377481fde8f60087c2c9a068be758685fc792d681b2e` |
| Unreviewed inspection | 2 files; 0 authoritative candidates; 0 matches |
| Reviewed candidate perimeter | 21/21 extracted monetary tokens explicitly retained as candidate amounts |
| Qualified comparison | 2 candidate matches for the repeated accounting-table bank balance |
| Plan and support amounts | `1730547.5` and `1730548` EUR |
| Exact signed / absolute residual | `-0.5` / `0.5` EUR |
| Reviewed tolerance | `1` EUR; both repeated source occurrences within tolerance |
| Repeated amount-candidate CSV SHA-256 | `bd03df423739a0907204e58317246b9263149ea927bbc69a1c891694fe4ad807` |
| Repeated match CSV SHA-256 | `ace18db848303a6fd823f5e45bf17da55c3857899b53d79429db9e61ef6aaee1` |
| Equal repeated numeric-ledger SHA-256 | `e831221d334234258db93e361ff8587c4c6d6d6b450257d0697b248ed3efd921` |
| Standalone replay | passed for both qualified runs |
| Complete Concordato suite | 104/104; JUnit SHA-256 `960549c0fa93b2fcbaf4c3ec6434a812431435fee7f6311f6fad0f7e5371f929` |

The source, preparation, and deterministic reconciliation gates passed.
Semantic review remained withheld, reporting remained blocked, publication
authority remained withheld, and `report_ready` remained false.

The official case menu was also inspected for a separately authored numerical
support source. The original petition, the term-setting decree, and the later
bankruptcy judgment were downloaded only to the temporary evaluation area:

| Additional official document | SHA-256 | Support result |
| --- | --- | --- |
| Case menu | `d93d1d6b85e51339dd6f49c1937edd4b1410f4add211b95dbcbd79257fd02748` | Lists the petition, decree, commissioner contact, and judgment; no attestazione or accounting attachment is linked. |
| Original petition | `4db7ec1afb76f635072655dc4b2e664da7a7d1b236e5219e3231b08bc95a37cf` | Confirms that three annual financial statements and a creditor schedule were filed, but does not reproduce the plan balances and the attachments are not published. |
| Term-setting decree | `9a40351fe18b36332cd2980e0df81470b3b087a8b519db737cc628452fb29a06` | Procedural evidence only. |
| Bankruptcy judgment | `85d69c24642243f8ed21ef744142d42ae9acdd6d440f0892641fb10b7fde9092` | Independently states that realizable assets were below debts, but provides no corresponding plan amounts for deterministic tie-out. |

Those additional documents therefore provide procedural and qualitative
corroboration, not independent numerical support. They were not promoted into
the positive tie-out population.

This is real-corporate-PDF evidence for bounded extraction, reviewed source
roles, exact Italian money parsing, reviewed tolerance arithmetic, numeric
address closure, repeatability, and replay. It is not independent supporting
evidence: both projections come from the same filed plan, and the accounting
page repeats the bank balance within that document. It therefore does not
establish source sufficiency, legal or accounting correctness, or arbitrary
real-plan generality.

## Concordato EVIVA independent-document bounded support case 2026-07-25

The public [EVIVA procedure site](https://www.cpeviva.it/) separately publishes
the 149-page
[plan and proposal](https://www.cpeviva.it/pdf/02_piano_proposta.pdf), the
229-page
[attester's report](https://www.cpeviva.it/pdf/11_attestazione_fattibilit%C3%A0.pdf),
and the 364-page
[judicial commissioners' article 172 report](https://www.cpeviva.it/pdf/20_eviva_spa_liqne_relazione_art172.pdf).
All 742 source pages and run artifacts remain outside the repository and
Marketplace package. This is a public procedure publication site, not asserted
to be a court-operated domain.

The full unreviewed inspection found 10,101 raw candidate rows and correctly
emitted zero authoritative candidates because no source roles or token
dispositions had been reviewed. To keep the positive claim auditable, the
qualified evaluation was bounded to plan PDF page 129, attestation PDF page 40,
and commissioners PDF page 25. A reviewer assigned the plan role only to the
plan page, assigned both other pages the `other_support` role, and explicitly
disposed every extracted numeric token.

| Evidence | Result |
| --- | --- |
| Plan PDF | 149 pages; 1,421,477 bytes; SHA-256 `37bba99296d759e2e4fffb530e17ee300cc98c0d678edea5ef7a5bf5aff54cd2` |
| Attester PDF | 229 pages; 4,099,330 bytes; SHA-256 `3831bae9e42a0265dbf1f4a197c676e93e08d6329b47a6d795406d13733c4375` |
| Commissioners PDF | 364 pages; 2,598,838 bytes; SHA-256 `c4ffeec6c03ccfa28395b26dfd3178f847df4e9ac28bb6220148bd1bce6b286b` |
| Bounded page projections | plan `2e05c43d80f15748ecdb8910493613ff3a2f03c9014224f38648e2911e4f9e43`; attester `f9af8db4572b6651d50b3bc48b877715ea080eaa2dc009ce54c7aac4a3560940`; commissioners `944d7adffa3e45098b17e6a00cc57cffd89be04b78e46b3f2a14711d6922bc39` |
| Reviewed perimeter | 224 raw tokens; 197 authoritative amounts; 27 explicit non-amount exclusions |
| Candidate comparison | 112 plan amounts; 30 exact match pairs; 15 unique matched plan amounts |
| Standalone replay | passed; run `concordato-plan-review-bounded_input-202607251224380000` |
| Review payload content SHA-256 | `45783ae9f22e47dc4b668551b27bedd68b585b7db0010b29eff7b936a93954f1` |
| Assurance-envelope content SHA-256 | `cc7438815b1ff0be29f3ead0e3ede01f7936befe72e191edd42393815ea38e03` |
| Output-closure content SHA-256 | `daec4886a26c2bbf0bc905cdeaff313677f3441978d62d2354f9eeb905910f03` |

The bounded documents establish these exact mechanical comparisons:

| Comparison | Plan EUR | Separate-document EUR | Plan less support EUR |
| --- | ---: | ---: | ---: |
| Initial total assets / funding need | 163,479,218 | 163,479,218 | 0 |
| Plan total assets vs attester's final adjusted total | 163,479,218 | 159,024,122 | 4,455,096 |
| Pre-deduction claims | 23,570,910 | 23,973,181 | -402,271 |
| Unsecured-creditor payout | 84,316,509 | 83,914,237 | 402,272 |
| Gross unsecured debt | 371,004,802 | 371,004,802 | 0 |

The commissioners' three stated payment components sum to EUR 163,479,217,
one euro below the stated EUR 163,479,218 funding need; the plan components sum
exactly to EUR 163,479,218. More importantly, the matching aggregate total
coexists with a material attester adjustment and a reallocation between
creditor classes. This demonstrates why exact deterministic matching is useful
but aggregate equality cannot be treated as a semantic support conclusion.

One visible commissioners' amount, EUR 55,591,799, was extracted as a split
token with only `591,799` retained. The reviewer excluded that token instead of
silently repairing it, leaving the privileged-claims comparison open. Source,
preparation, and deterministic reconciliation gates passed; semantic review
remained withheld, reporting blocked, publication withheld, and
`report_ready=false`.

This closes the prior narrow gap of having no separately authored numerical
support document for a real corporate case. It does not promote the workflow
for broad real-plan generality or professional source sufficiency: only three
selected pages were evaluated, and no qualified independent reviewer compared
the full candidate population or a separately prepared workpaper.

## Journal–Bank recovered v7 sealed rerun 2026-07-25

The recovered v7 author bundle was independently reverified and kept hidden
from the candidate operator until two candidate runs for all eighteen public
cases had completed and the submission was sealed. The candidate accepted
successful closed runs and fail-closed blocked runs without inspecting hidden
expected outcomes.

| Evidence | Result |
| --- | --- |
| Contract v5 SHA-256 | `4824652ecdb990a844fd9b72d799a2537f46a21ddb9fefb8a664f828c0ec6657` |
| Author bundle root SHA-256 | `07d15685607b4322f00200f19b2e09648770e20302198477b22d833518de4f80` |
| Hidden phase root SHA-256 | `22e9c55628822b386416ce272d1a49559314ec8cd8ba20ffbae5e65fd20a5f38` |
| Candidate submission seal root | `60682f16c57c977364b83497d1ec47515341bad36b6e50bc1f8dc7cd359ad4e7` |
| Candidate execution | 36 runs: 14 completed and 22 blocked fail-closed |
| Repeatability | 18/18 A/B pairs passed |
| Hidden evaluation | 0/18; immutable `NO-GO` |
| Evaluation report SHA-256 | `c0f9aa62a50b7aee358fdd7f697b275aba52072ce71d82cdf3de4ccf538839bf` |

Post-seal adjudication found that the evaluator was not concordant with the
frozen product contract:

- it required a material ledger when qualification or relationship authority
  blocked, although v5 explicitly requires that ledger to be absent;
- its reader expected `dataset`, `value`, and singular locator keys rather
  than the current `dataset_id`, `canonical_value`, prepared address, and
  output-address representation;
- it searched for a top-level `run_block_code` in
  `vera.assurance_gates.v1`, whose exact schema permits only the version, gate
  register, and `report_ready`; production retains the block code in the
  reconciliation audit and blocked relationship ledger;
- it expected party and entity values directly on allocation rows although
  the frozen allocation schema retains them on bound source and target
  records; and
- public case 002 supplied an extra unobserved direction label, which the v5
  contract requires production to reject.

The result is retained as immutable `NO-GO` evidence. It does not justify
changing product schemas to satisfy the evaluator and cannot promote M7.
