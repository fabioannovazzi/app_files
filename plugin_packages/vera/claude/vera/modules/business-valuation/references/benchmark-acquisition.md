> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Public benchmark acquisition v1

Research and select the relevant source semantically. Versioned adapters support
the **NYU Damodaran country-risk HTML table** and an **explicitly selected ECB AAA
spot-rate CSV observation**. They do not select a country, metric, maturity, rate
or vintage for the professional. Regional Excel datasets, historical workbook
formats and other publishers remain separate reviewed import routes.

The host prepares a public-only request. Never put client names, private
documents, forecasts, account identifiers, tokens or secrets in a URL or query.
Use the actual landing page and dataset link observed in the current source.
The helper captures that landing page and requires both the dataset and terms
URLs to appear in its links, resolving relative URLs and removing link fragments.
It does not guess filenames, upgrade HTTP links or use a fallback mirror.

```json
{
  "parser": "nyu-country-risk-html/v1",
  "landing_url": "https://pages.stern.nyu.edu/adamodar/New_Home_Page/datacurrent.html",
  "dataset_url": "https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ctryprem.html",
  "terms_url": "https://pages.stern.nyu.edu/adamodar/New_Home_Page/datahistory.html",
  "terms_note": "Record the inspected terms and the basis for local retention here.",
  "copy_permitted": false,
  "observed_on": null,
  "observed_basis": "Exact observation date has not yet been established.",
  "selection": {"country": "Italy", "metric": "Country Risk Premium"},
  "public_query": "NYU country risk premium Italy, public release and date evidence"
}
```

The example is a request shape, not current adoption of a parameter or permission
to copy. Check the live links and usage terms. A reference-only decision writes
the request/status locally and performs no network reads. With copying permitted:

```sh
python scripts/valuation_benchmarks.py --request <public-request.json> --output-dir <engagement-evidence-staging>
```

Choose a staging directory in the selected client engagement, then import the
result through Studio Archive. The public acquisition helper itself does not
read the client's case, create a run or grant source/method acceptance. It writes
`acquisition.json` and permitted original bytes as inert `landing.source`,
`terms.source`, `dataset.source` files in an immutable `benchmark-<hash>` folder.
Do not open raw HTML as an active page; use the structured record or a passive
source reader. Report failures and retain their records; never substitute an old
successful snapshot when the current source is unavailable.

The record preserves requested/final URLs, redirects, byte hashes, MIME/encoding,
ETag/Last-Modified when supplied, retrieval time, reuse decision, parser version,
original row/value, exact percent-to-ratio conversion and selected country/metric.
ETag, retrieval time and Last-Modified never establish historical publication.
The parser reads the source's displayed “Last updated” date as its release date
and vintage; it does not prove that today's bytes were available then. Supply an
observation date only with actual evidence and explain its basis. Missing dates
or N/A values remain missing and make the observation ineligible for automatic
binding. Review historical availability separately for a historical mandate.

Exact headers and row shape are required. Changed layouts/definitions, duplicate
countries, absent selected rows, missing release dates and malformed percentages
stop parsing while retaining the permitted original document. Values remain
proposals. The first adapter covers the displayed adjusted default spread,
country/equity risk premiums, corporate tax rate and CDS columns; selecting a
tax-rate column does not determine the applicable tax rate for a business.

Networking uses the existing public HTTP transport, with a 20-second elapsed
budget per document, at most five redirects, a 2 MiB limit and format-specific
MIME/byte checks. The NYU parser permits only its supported NYU hosts. The ECB
parser permits only `www.ecb.europa.eu` and `data-api.ecb.europa.eu`; its landing
and terms documents must be HTML and its dataset must be `text/csv`. Only HTTPS
standard-port requests are allowed. Every redirect revalidates its parser's
host boundary and DNS answers; private/mixed
addresses are rejected and the connection uses the vetted numeric address with
the original hostname for TLS verification. No cookies, account credentials,
body, referer or environment proxy are used. DNS resolution itself is synchronous
and cannot be interrupted; it consumes the deadline and cannot lead to a request
after expiry. Archives and office files are rejected; no ZIP extraction or macro
execution occurs. None of these controls decides economic relevance or truth.

## ECB AAA spot CSV

Read the official [yield-curve page](https://www.ecb.europa.eu/stats/financial_markets_and_interest_rates/euro_area_yield_curves/html/index.en.html)
and its linked usage terms. Follow an actual CSV link visible there; do not
construct an endpoint or filename from this example. The source describes the
curves as informational and identifies its market-data/rating sources. Preserve
that limitation and source attribution; relevance to a mandate remains a
professional decision. With the same common request fields, select:

```json
{
  "parser": "ecb-aaa-spot-csv/v1",
  "observed_on": null,
  "observed_basis": "Use the selected CSV TIME_PERIOD, not its HTTP timestamp.",
  "selection": {
    "series_key": "YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y",
    "observed_on": "2026-09-28"
  }
}
```

This is a partial request illustration, not a rate/maturity recommendation or a
current availability claim. The full request still needs observed landing,
dataset and terms URLs, reuse decision/note and public-only query. The helper
requires the exact series/date; it does not select the latest available row or
substitute another maturity. The 40-column CSV shape, series dimensions, unit
`PCPA`, multiplier zero, continuous-compounding definition and observation status
are checked. Forward, par and all-rating curves are separate series and are not
accepted by this adapter. Missing values stay null; qualified/changed rows stop
parsing for review. Signed rates are allowed.

The only numeric conversion is percent divided by 100. **Continuous compounding
remains continuous**: the result is not an effective annual rate or WACC. No
curve interpolation, economic selection or compounding conversion occurs.
The original complete row, document bytes and definition are retained.

The observed CSV provides `TIME_PERIOD` but no observation-level publication date
or independently established historical vintage. Both `published_on` and
`vintage` therefore remain null, even when HTTP Last-Modified or a daily release
schedule is known. The snapshot has its own byte hash and retrieval timestamp;
those do not prove earlier availability. This adapter deliberately returns
`metadata_or_value_missing`, so its record cannot automatically bind a value into
a valuation. Independently evidenced publication/vintage and a reviewed import
route are still required. Do not edit an acquisition record to manufacture them.
Revised bytes create a new snapshot and never rewrite an earlier case.

## Binding the observation into a case

Import `acquisition.json` and `dataset.source` as exact Studio Archive inputs.
Include both imported source IDs in the selected input's `source_ids`. Copy the
proposed value/unit and benchmark metadata exactly; set the input's confirmation
state only after the professional's review. Add this optional field under the
input's `benchmark`, using actual imported IDs and the acquired observation ID:

```json
"acquisition": {
  "record_source_id": "benchmark-record",
  "document_source_id": "benchmark-document",
  "observation_id": "<64-character SHA-256 from the acquisition record>"
}
```

The valuation compiler reads only receipted local files. It checks record and
document hashes, replays the versioned parser and rejects a substituted value,
unit, observation ID or benchmark metadata. Publication/cutoff and case-specific
age checks still apply. Source revisions produce new records and invalidate
dependent method reviews; unrelated reviews and old outputs remain intact.
For a failed/missing observation, keep the limitation and a null dependent input
instead of attaching an ineligible binding or inventing a number. Acquisition
records and local review declarations are not publisher or reviewer signatures.
