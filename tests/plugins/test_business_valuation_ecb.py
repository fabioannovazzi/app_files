"""ECB public-source acquisition preserves dates, units and missing vintage evidence."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins/business-valuation/scripts"
sys.path.insert(0, str(SCRIPTS))

import valuation_benchmarks as benchmarks
import valuation_download as download
import valuation_ecb as ecb
from valuation_engine import ValuationError

LANDING = "https://www.ecb.europa.eu/stats/example.html"
TERMS = "https://www.ecb.europa.eu/services/terms.html"
DATASET = "https://data-api.ecb.europa.eu/service/data/YC/example?format=csvdata"
SERIES = ecb.PREFIX + "SR_10Y"
OBSERVED = "2026-09-28"
CLOCK = datetime(2026, 9, 29, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def preserve_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    for module in (benchmarks, download, ecb):
        monkeypatch.setitem(sys.modules, module.__name__, module)


def selection() -> dict:
    return {"series_key": SERIES, "observed_on": OBSERVED}


def row(**changes: str) -> dict:
    result = dict.fromkeys(ecb.HEADERS, "")
    result.update(
        KEY=SERIES,
        FREQ="B",
        REF_AREA="U2",
        CURRENCY="EUR",
        PROVIDER_FM="4F",
        INSTRUMENT_FM="G_N_A",
        PROVIDER_FM_ID="SV_C_YM",
        DATA_TYPE_FM="SR_10Y",
        TIME_PERIOD=OBSERVED,
        OBS_VALUE="3.50",
        OBS_STATUS="A",
        OBS_CONF="F",
        TIME_FORMAT="P1D",
        COLLECTION="E",
        UNIT="PCPA",
        UNIT_MULT="0",
        TITLE="Fictional AAA ten-year spot observation",
        TITLE_COMPL="Fictional Svensson model - continuous compounding - Yield curve spot rate, 10-year maturity",
    )
    result.update(changes)
    return result


def csv_bytes(*rows: dict) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=ecb.HEADERS)
    writer.writeheader()
    writer.writerows(rows or (row(),))
    return buffer.getvalue().encode()


def request() -> dict:
    return {
        "parser": ecb.PARSER,
        "landing_url": LANDING,
        "dataset_url": DATASET,
        "terms_url": TERMS,
        "terms_note": "Fictional source reuse decision",
        "copy_permitted": True,
        "observed_on": None,
        "observed_basis": "Read the selected CSV observation date",
        "selection": selection(),
        "public_query": "Fictional public ECB AAA spot rate",
    }


def fixture_fetch(body: bytes | None = None):
    files = {
        LANDING: f'<html><a href="{DATASET}">CSV</a><a href="{TERMS}">Terms</a></html>'.encode(),
        TERMS: b"<html>Fictional terms; attribute source</html>",
        DATASET: body if body is not None else csv_bytes(),
    }

    def fetch(url: str) -> tuple[bytes, dict]:
        raw = files[url]
        return raw, {
            "requested_url": url,
            "final_url": url,
            "redirect_urls": [url],
            "mime": "text/csv" if url == DATASET else "text/html",
            "charset": "utf-8",
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "etag": "synthetic-snapshot",
            "last_modified": "Tue, 29 Sep 2026 10:00:00 GMT",
        }

    return fetch


@pytest.mark.parametrize(
    ("original", "expected"), [("3.50", "0.035"), ("-0.50", "-0.005"), ("0", "0")]
)
def test_selected_spot_rate_preserves_continuous_compounding(original, expected):
    result = ecb.parse_ecb_spot(
        csv_bytes(row(OBS_VALUE=original)), "utf-8", selection()
    )
    assert result["value"] == expected
    assert result["compounding"] == "continuous"
    assert result["rate_kind"] == "spot"
    assert result["original_value"] == original
    assert result["observed_on"] == OBSERVED
    assert result["published_on"] is None
    assert result["vintage"] is None


def test_multiple_dates_require_the_explicit_selected_observation():
    result = ecb.parse_ecb_spot(
        csv_bytes(row(TIME_PERIOD="2026-09-25", OBS_VALUE="2.75"), row()),
        "utf-8",
        selection(),
    )
    assert result["value"] == "0.035"
    assert result["original_row"]["TIME_PERIOD"] == OBSERVED


@pytest.mark.parametrize(
    "key",
    [
        ecb.PREFIX + "IF_10Y",
        ecb.PREFIX + "PY_10Y",
        SERIES.replace("G_N_A", "G_N_C"),
        ecb.PREFIX + "SR_",
        "auto",
    ],
)
def test_non_spot_or_non_aaa_selection_is_rejected(key):
    with pytest.raises(ValuationError, match="explicit ECB AAA spot"):
        ecb.parse_ecb_spot(csv_bytes(), "utf-8", {**selection(), "series_key": key})


@pytest.mark.parametrize(
    "changes",
    [
        {"UNIT": "PURE_NUMB"},
        {"UNIT_MULT": "2"},
        {"FREQ": "M"},
        {"INSTRUMENT_FM": "G_N_C"},
        {"DATA_TYPE_FM": "IF_10Y"},
        {"TITLE_COMPL": "effective annual par rate"},
        {"OBS_STATUS": "P"},
        {"OBS_CONF": "C"},
        {"OBS_COM": "Specific caution"},
        {"BREAKS": "break"},
        {"OBS_PRE_BREAK": "3.4"},
        {"OBS_VALUE": "=1+1"},
        {"OBS_STATUS": "M"},
    ],
)
def test_changed_definition_qualified_status_or_executable_value_stops_parsing(changes):
    with pytest.raises(ValuationError):
        ecb.parse_ecb_spot(csv_bytes(row(**changes)), "utf-8", selection())


@pytest.mark.parametrize("status", ["A", "M"])
def test_missing_rate_is_retained_without_zero_substitution(status):
    result = ecb.parse_ecb_spot(
        csv_bytes(row(OBS_VALUE="", OBS_STATUS=status)), "utf-8", selection()
    )
    assert result["value"] is None


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (csv_bytes(row(), row()), "Duplicate"),
        (csv_bytes(row(TIME_PERIOD="2026-09-25")), "unavailable"),
        (csv_bytes().replace(b"OBS_VALUE", b"VALUE"), "headers changed"),
        (csv_bytes() + b"truncated,row\n", "row shape"),
        (csv_bytes().splitlines(keepends=True)[0] + b'"unterminated', "Malformed"),
        (b"PK\x00", "Invalid ECB CSV"),
    ],
)
def test_csv_ambiguity_and_shape_changes_fail_explicitly(body, message):
    with pytest.raises(ValuationError, match=message):
        ecb.parse_ecb_spot(body, "utf-8", selection())


def test_http_timestamp_never_becomes_publication_or_vintage(tmp_path):
    result = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(), now=CLOCK
    )
    record = result["record"]
    assert record["status"] == "metadata_or_value_missing"
    assert record["observation"]["observed_on"] == OBSERVED
    assert record["observation"]["published_on"] is None
    assert record["observation"]["vintage"] is None
    assert record["captures"]["dataset"]["last_modified"] is not None
    assert (Path(result["output_dir"]) / "dataset.source").read_bytes() == csv_bytes()


def test_incomplete_ecb_acquisition_cannot_bind_a_case_input(tmp_path):
    from tests.plugins.test_business_valuation_benchmarks import bound_case

    result = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(), now=CLOCK
    )
    case = bound_case(tmp_path, result)
    sources = {source["id"]: source for source in case["sources"]}
    with pytest.raises(ValuationError, match="not a complete observation"):
        benchmarks.validate_benchmark_bindings(case, sources, tmp_path)


def test_relabelled_acquisition_with_invented_publication_fails_source_replay(tmp_path):
    from tests.plugins.test_business_valuation_benchmarks import bound_case

    result = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(), now=CLOCK
    )
    record = result["record"]
    observed = record["observation"]
    record["status"] = "acquired"
    observed.update(published_on=OBSERVED, vintage=OBSERVED)
    observed["observation_id"] = benchmarks.digest(
        {k: v for k, v in observed.items() if k != "observation_id"}
    )
    record["acquisition_id"] = benchmarks.digest(
        {k: v for k, v in record.items() if k not in {"retrieved_at", "acquisition_id"}}
    )
    (Path(result["output_dir"]) / "acquisition.json").write_text(json.dumps(record))
    case = bound_case(tmp_path, result)
    sources = {source["id"]: source for source in case["sources"]}
    with pytest.raises(ValuationError, match="parser replay differs"):
        benchmarks.validate_benchmark_bindings(case, sources, tmp_path)


def test_later_source_revision_preserves_original_snapshot(tmp_path):
    first = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(), now=CLOCK
    )
    result = benchmarks.acquire_benchmark(
        request(),
        tmp_path,
        fetch=fixture_fetch(csv_bytes(row(OBS_VALUE="3.75"))),
        now=CLOCK,
    )
    assert first["output_dir"] != result["output_dir"]
    assert (Path(first["output_dir"]) / "dataset.source").read_bytes() == csv_bytes()
    assert result["record"]["observation"]["value"] == "0.0375"


def test_request_cannot_override_csv_observation_date(tmp_path):
    candidate = {**request(), "observed_on": "2025-01-01"}
    with pytest.raises(ValuationError, match="cannot override"):
        benchmarks.acquire_benchmark(
            candidate, tmp_path, fetch=fixture_fetch(), now=CLOCK
        )


def test_future_observation_is_preserved_as_failed_acquisition(tmp_path):
    result = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(), now=CLOCK.replace(day=27)
    )
    assert result["record"]["status"] == "unavailable"
    assert result["record"]["failure"]["reason"] == "Acquisition dates are inconsistent"


def test_unobserved_dataset_link_is_not_fetched(tmp_path):
    candidate = {**request(), "dataset_url": DATASET + "&guessed=1"}
    result = benchmarks.acquire_benchmark(
        candidate, tmp_path, fetch=fixture_fetch(), now=CLOCK
    )
    assert result["record"]["status"] == "unavailable"
    assert "not observed" in result["record"]["failure"]["reason"]
    assert "dataset" not in result["record"]["captures"]


def test_ecb_request_does_not_authorize_nyu_destinations(tmp_path):
    candidate = {**request(), "dataset_url": "https://pages.stern.nyu.edu/other.csv"}
    with pytest.raises(ValuationError, match="allowed HTTPS host"):
        benchmarks.acquire_benchmark(
            candidate, tmp_path, fetch=fixture_fetch(), now=CLOCK
        )


def test_ecb_acquisition_routes_html_and_csv_with_separate_mime_contracts(
    tmp_path, monkeypatch
):
    fetched = []
    fixture = fixture_fetch()

    def html(url, *, hosts):
        assert hosts == download.ECB_HOSTS
        fetched.append((url, "html"))
        return fixture(url)

    def csv_fetch(url):
        fetched.append((url, "csv"))
        return fixture(url)

    monkeypatch.setattr(download, "download_html", html)
    monkeypatch.setattr(download, "download_csv", csv_fetch)
    result = benchmarks.acquire_benchmark(request(), tmp_path, now=CLOCK)
    assert result["record"]["status"] == "metadata_or_value_missing"
    assert fetched == [(LANDING, "html"), (TERMS, "html"), (DATASET, "csv")]


def test_csv_download_revalidates_redirect_host(monkeypatch):
    def transport(req, timeout, resolver):
        return resolver("https://pages.stern.nyu.edu/redirected.csv")

    monkeypatch.setattr(download, "open_public_url", transport)
    with pytest.raises(ValuationError, match="allowed HTTPS host"):
        download.download_csv(DATASET)


@pytest.mark.parametrize(
    ("body", "mime"),
    [
        (b"<html>error</html>", "text/html"),
        (b"PK\x03\x04", "text/csv"),
        (b"KEY,FREQ,\x00", "text/csv"),
    ],
)
def test_csv_download_rejects_error_html_and_disguised_binary(body, mime, monkeypatch):
    from tests.plugins.test_business_valuation_benchmarks import Response

    monkeypatch.setattr(download, "open_public_url", lambda *args: Response(body, mime))
    with pytest.raises(ValuationError):
        download.download_csv(DATASET)


def test_csv_download_retains_original_bytes_without_formula_execution(monkeypatch):
    from tests.plugins.test_business_valuation_benchmarks import Response

    body = csv_bytes(row(TITLE='=HYPERLINK("https://example.invalid")'))
    monkeypatch.setattr(
        download, "open_public_url", lambda *args: Response(body, "text/csv")
    )
    raw, metadata = download.download_csv(DATASET)
    assert raw == body
    assert metadata["mime"] == "text/csv"
    assert metadata["sha256"] == hashlib.sha256(body).hexdigest()
