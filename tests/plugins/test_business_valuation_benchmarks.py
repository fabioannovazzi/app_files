"""Public acquisition, preserved vintages and imported benchmark replay."""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import sys
from copy import deepcopy
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/business-valuation/scripts"
sys.path.insert(0, str(SCRIPTS))

import valuation_benchmarks as benchmarks
import valuation_case
import valuation_download as download
from valuation_engine import ValuationError

LANDING = "https://pages.stern.nyu.edu/index.html"
DATASET = "https://pages.stern.nyu.edu/country.html"
TERMS = "https://pages.stern.nyu.edu/terms.html"
CLOCK = datetime(2026, 9, 29, tzinfo=timezone.utc)
FIXTURE = ROOT / "tests/fixtures/business_valuation"


@pytest.fixture(autouse=True)
def preserve_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    for module in (benchmarks, valuation_case, download):
        monkeypatch.setitem(sys.modules, module.__name__, module)


def request() -> dict:
    return {
        "parser": benchmarks.PARSER,
        "landing_url": LANDING,
        "dataset_url": DATASET,
        "terms_url": TERMS,
        "terms_note": "Fictional permissive source for tests",
        "copy_permitted": True,
        "observed_on": "2026-01-01",
        "observed_basis": "Explicit fictional source date; not a live observation",
        "selection": {"country": "Example Country", "metric": "Country Risk Premium"},
        "public_query": "Fictional public country risk premium",
    }


def table(value: str = "2.50%", released: str = "January 5, 2026") -> bytes:
    headers = "".join(f"<td>{name}</td>" for name in benchmarks.HEADERS)
    row = f"<tr><td>Example Country</td><td>Aa1</td><td>1.00%</td><td>{value}</td><td>6.50%</td><td>20.00%</td><td>NA</td><td>NA</td></tr>"
    return f"<html><p>Last updated: {released}</p><table><tr>{headers}</tr>{row}</table></html>".encode()


def fixture_fetch(body: bytes | None = None):
    files = {
        LANDING: b'<html><a href="country.html">Data</a><a href="terms.html#rules">Terms</a></html>',
        TERMS: b"<html>Fictional usage terms</html>",
        DATASET: body or table(),
    }

    def fetch(url: str) -> tuple[bytes, dict]:
        raw = files[url]
        return raw, {
            "requested_url": url,
            "final_url": url,
            "redirect_urls": [url],
            "mime": "text/html",
            "charset": "utf-8",
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "etag": None,
            "last_modified": None,
        }

    return fetch


def bound_case(tmp_path: Path, result: dict) -> dict:
    case = valuation_case.read_json(FIXTURE / "case.json")
    shutil.copyfile(FIXTURE / "evidence.txt", tmp_path / "evidence.txt")
    directory = Path(result["output_dir"])
    for identifier, name in (
        ("benchmark-record", "acquisition.json"),
        ("benchmark-document", "dataset.source"),
    ):
        path = directory / name
        case["sources"].append(
            {
                "id": identifier,
                "path": str(path.relative_to(tmp_path)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "description": "Synthetic public evidence",
                "allowed_audiences": ["internal"],
                "status": "reviewed",
            }
        )
    observed = result["record"]["observation"]
    rate = case["inputs"][2]
    rate.update(
        value=observed["value"], source_ids=["benchmark-record", "benchmark-document"]
    )
    rate["benchmark"] = {
        key: observed[key]
        for key in (
            "source_url",
            "observed_on",
            "published_on",
            "retrieved_on",
            "vintage",
            "definition",
            "geography",
        )
    }
    rate["benchmark"].update(
        max_age_days=1000,
        selection_reason="Synthetic test rate only",
        acquisition={
            "record_source_id": "benchmark-record",
            "document_source_id": "benchmark-document",
            "observation_id": observed["observation_id"],
        },
    )
    return case


def test_acquisition_preserves_original_percentage_and_independent_dates(
    tmp_path: Path,
) -> None:
    result = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(), now=CLOCK
    )
    observation = result["record"]["observation"]
    assert result["record"]["status"] == "acquired"
    assert observation["value"] == "0.025"
    assert observation["original_value"] == "2.50%"
    assert observation["observed_on"] == "2026-01-01"
    assert observation["published_on"] == "2026-01-05"
    assert observation["retrieved_on"] == "2026-09-29"
    assert (Path(result["output_dir"]) / "dataset.source").read_bytes() == table()


def test_acquisition_does_not_invent_missing_observation_date(tmp_path: Path) -> None:
    candidate = request()
    candidate["observed_on"] = None
    result = benchmarks.acquire_benchmark(
        candidate, tmp_path, fetch=fixture_fetch(), now=CLOCK
    )
    assert result["record"]["status"] == "metadata_or_value_missing"
    assert result["record"]["observation"]["observed_on"] is None


@pytest.mark.parametrize("missing", ["NA", "N/A", "-", ""])
def test_missing_public_value_is_not_zero(missing: str, tmp_path: Path) -> None:
    result = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(table(missing)), now=CLOCK
    )
    assert result["record"]["status"] == "metadata_or_value_missing"
    assert result["record"]["observation"]["value"] is None


def test_same_day_retry_is_idempotent_and_detects_changed_saved_bytes(
    tmp_path: Path,
) -> None:
    initial = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(), now=CLOCK
    )
    replay = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(), now=CLOCK.replace(hour=3)
    )
    assert replay == initial
    (Path(initial["output_dir"]) / "dataset.source").write_bytes(b"changed")
    with pytest.raises(ValuationError, match="Existing acquisition bytes changed"):
        benchmarks.acquire_benchmark(
            request(), tmp_path, fetch=fixture_fetch(), now=CLOCK
        )


def test_new_release_retains_previous_snapshot(tmp_path: Path) -> None:
    first = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(), now=CLOCK
    )
    revised = table("3.00%", "July 1, 2026")
    result = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(revised), now=CLOCK
    )
    assert first["output_dir"] != result["output_dir"]
    assert (Path(first["output_dir"]) / "dataset.source").read_bytes() == table()
    assert result["record"]["observation"]["value"] == "0.03"


def test_unavailable_source_never_substitutes_cached_value(tmp_path: Path) -> None:
    initial = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(), now=CLOCK
    )

    def unavailable(url: str):
        raise TimeoutError("Source timeout")

    result = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=unavailable, now=CLOCK
    )
    assert result["record"]["status"] == "unavailable"
    assert result["record"]["observation"] is None
    assert result["output_dir"] != initial["output_dir"]


def test_reference_only_reuse_decision_does_not_fetch_or_copy(tmp_path: Path) -> None:
    candidate = request()
    candidate["copy_permitted"] = False

    def unexpected(url: str):
        pytest.fail("Reference-only acquisition must not download")

    result = benchmarks.acquire_benchmark(
        candidate, tmp_path, fetch=unexpected, now=CLOCK
    )
    assert result["record"]["status"] == "reference_only"
    assert result["record"]["captures"] == {}


def test_unobserved_link_is_not_downloaded(tmp_path: Path) -> None:
    candidate = request()
    candidate["dataset_url"] = DATASET + "?guessed=1"
    result = benchmarks.acquire_benchmark(
        candidate, tmp_path, fetch=fixture_fetch(), now=CLOCK
    )
    assert result["record"]["status"] == "unavailable"
    assert "not observed" in result["record"]["failure"]["reason"]
    assert "dataset" not in result["record"]["captures"]


@pytest.mark.parametrize(
    "body",
    [
        table().replace(b"Country Risk Premium", b"Changed Definition"),
        table().replace(b"<tr><td>Example Country", b"<tr><td>Different Country"),
        table().replace(b"Last updated:", b"No publication date:"),
        table("1,000%"),
    ],
)
def test_parser_drift_preserves_source_and_visible_failure(
    body: bytes, tmp_path: Path
) -> None:
    result = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(body), now=CLOCK
    )
    assert result["record"]["status"] == "unavailable"
    assert (Path(result["output_dir"]) / "dataset.source").read_bytes() == body


def test_imported_observation_replays_into_valuation(tmp_path: Path) -> None:
    acquired = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(), now=CLOCK
    )
    case = bound_case(tmp_path, acquired)
    result = valuation_case.build_valuation(case, tmp_path)
    assert result["methods"][0]["status"] == "ready_for_professional_review"
    assert set(result["methods"][0]["source_ids"]) >= {
        "benchmark-record",
        "benchmark-document",
    }


@pytest.mark.parametrize("change", ["value", "observation_id", "vintage"])
def test_changed_acquisition_binding_blocks_silently_substituted_input(
    change: str, tmp_path: Path
) -> None:
    acquired = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(), now=CLOCK
    )
    case = bound_case(tmp_path, acquired)
    if change == "value":
        case["inputs"][2]["value"] = "0.123"
    elif change == "observation_id":
        case["inputs"][2]["benchmark"]["acquisition"][change] = "a" * 64
    else:
        case["inputs"][2]["benchmark"][change] = "Invented earlier release"
    with pytest.raises(ValuationError, match="Acquisition|acquisition|acquired"):
        valuation_case.build_valuation(case, tmp_path)


def test_revised_historical_observation_cannot_enter_earlier_cutoff(
    tmp_path: Path,
) -> None:
    acquired = benchmarks.acquire_benchmark(
        request(),
        tmp_path,
        fetch=fixture_fetch(table("3.00%", "July 1, 2026")),
        now=CLOCK,
    )
    case = bound_case(tmp_path, acquired)
    case["mandate"]["information_cutoff"] = "2026-06-30"
    with pytest.raises(ValuationError, match="look-ahead"):
        valuation_case.build_valuation(case, tmp_path)


def test_new_acquisition_revision_invalidates_only_dependent_method_reviews(
    tmp_path: Path,
) -> None:
    acquired = benchmarks.acquire_benchmark(
        request(), tmp_path, fetch=fixture_fetch(), now=CLOCK
    )
    initial_case = bound_case(tmp_path, acquired)
    initial = valuation_case.build_valuation(initial_case, tmp_path)
    updated = benchmarks.acquire_benchmark(
        request(),
        tmp_path,
        fetch=fixture_fetch(table("3.00%", "July 1, 2026")),
        now=CLOCK,
    )
    revised_case = bound_case(tmp_path, updated)
    for method, prior in zip(revised_case["methods"], initial["methods"]):
        method["review"] = {
            "dependency_sha256": prior["dependency_sha256"],
            "decision": "accepted",
            "reviewer": "Synthetic test reviewer",
            "reviewed_at": CLOCK.isoformat(),
        }

    result = valuation_case.build_valuation(revised_case, tmp_path)

    assert result["methods"][0]["stale_review"] is True
    assert result["methods"][3]["status"] == "accepted_workpaper"
    assert Path(acquired["output_dir"]).is_dir()


def test_redirect_rebinding_is_rejected_before_second_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import public_http

    answers = iter(["93.184.216.34", "127.0.0.1"])
    monkeypatch.setattr(
        download.socket,
        "getaddrinfo",
        lambda *a, **kw: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (next(answers), 443))
        ],
    )
    opened = []

    class Connection:
        def request(self, *args, **kwargs):
            return None

        def getresponse(self):
            response = Response(b"", "text/html")
            response.status = 302
            response.headers["Location"] = DATASET + "?redirected=1"
            return response

        def close(self):
            return None

    def connect(**kwargs):
        opened.append(kwargs["address"])
        return Connection()

    monkeypatch.setattr(public_http, "_open_pinned_connection", connect)

    with pytest.raises(ValuationError, match="non-public"):
        download.download_html(DATASET)

    assert opened == ["93.184.216.34"]


@pytest.mark.parametrize(
    "url",
    [
        "http://pages.stern.nyu.edu/file",
        "https://127.0.0.1/file",
        "https://pages.stern.nyu.edu.evil.example/file",
        "https://user:password@pages.stern.nyu.edu/file",
        "https://pages.stern.nyu.edu:444/file",
        "https://pages.stern.nyu.edu/file\n",
    ],
)
def test_acquisition_rejects_unapproved_destinations_before_dns(
    url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*args, **kwargs):
        pytest.fail("Unsafe URL reached DNS")

    monkeypatch.setattr(download.socket, "getaddrinfo", unexpected)
    with pytest.raises(ValueError):
        download.resolve_public_target(url)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_dns_mixed_public_private_answers_are_rejected(
    ip: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
        for address in ("93.184.216.34", ip)
    ]
    monkeypatch.setattr(download.socket, "getaddrinfo", lambda *a, **kw: answers)
    with pytest.raises(ValuationError, match="non-public"):
        download.resolve_public_target(DATASET)


class Response:
    def __init__(self, raw: bytes, mime: str, length: str | None = None) -> None:
        self.raw = raw
        self.status = 200
        self.headers = Message()
        self.headers["Content-Type"] = mime
        self.headers["Content-Length"] = length or str(len(raw))

    def read(self, amount: int) -> bytes:
        return self.raw[:amount]

    def geturl(self) -> str:
        return DATASET

    def close(self) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


@pytest.mark.parametrize(
    ("raw", "mime", "length"),
    [
        (b"PK\x03\x04", "application/zip", None),
        (b"PK\x03\x04", "text/html", None),
        (b"\xd0\xcf\x11", "application/vnd.ms-excel", None),
        (b"<html>partial", "text/html", "1000"),
        (b"<html>small", "text/html", str(download.MAX_BYTES + 1)),
    ],
)
def test_download_rejects_archives_macros_and_incomplete_or_oversized_content(
    raw, mime, length, monkeypatch
):
    monkeypatch.setattr(
        download, "open_public_url", lambda *args: Response(raw, mime, length)
    )
    with pytest.raises(ValuationError):
        download.download_html(DATASET)


def test_download_records_actual_redirects_and_byte_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    monkeypatch.setattr(download.socket, "getaddrinfo", lambda *a, **kw: answers)

    def transport(req, timeout, resolver):
        assert req.get_method() == "GET"
        assert req.data is None
        assert resolver(req.full_url) == (
            "pages.stern.nyu.edu",
            443,
            ("93.184.216.34",),
        )
        return Response(table(), "text/html; charset=utf-8")

    monkeypatch.setattr(download, "open_public_url", transport)
    raw, metadata = download.download_html(DATASET)
    assert raw == table()
    assert metadata["redirect_urls"] == [DATASET]
    assert metadata["sha256"] == hashlib.sha256(table()).hexdigest()
