"""Preserve observed-link benchmark acquisitions and replay exact observations.

Parsing a fixed table, decimal conversion and byte identity are mechanical.
Country/metric selection, observation-date evidence and economic use are explicit
model/professional decisions. A parsed number is always a proposal.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import localcontext
from html.parser import HTMLParser
from http.client import HTTPException
from pathlib import Path
from urllib.parse import urldefrag, urljoin

from valuation_case import digest, fields, read_json, require, text
from valuation_engine import ValuationError, decimal

__all__ = [
    "acquire_benchmark",
    "parse_country_risk",
    "validate_benchmark_bindings",
    "main",
]
PARSER = "nyu-country-risk-html/v1"
HEADERS = (
    "Country",
    "Moody's rating",
    "Adj. Default Spread",
    "Country Risk Premium",
    "Equity Risk Premium",
    "Corporate Tax Rate",
    "Sovereignn CDS",
    "ERP based on sovereign CDSS",
)
METRICS = HEADERS[2:]
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


class _Page(HTMLParser):
    """Extract literal links, visible text and table cells without running HTML."""

    def __init__(self, raw: bytes, charset: str) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.parts: list[str] = []
        self.tables: list[list[list[str]]] = []
        self.stack: list[dict] = []
        self.hidden = 0
        self.feed(raw.decode(charset))
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "template"}:
            self.hidden += 1
        if self.hidden:
            return
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)
        if tag == "table":
            self.stack.append({"rows": [], "row": None, "cell": None})
        elif self.stack:
            if tag == "tr":
                self.stack[-1]["row"] = []
            elif tag in {"td", "th"}:
                self.stack[-1]["cell"] = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "template"} and self.hidden:
            self.hidden -= 1
            return
        if self.hidden or not self.stack:
            return
        frame = self.stack[-1]
        if tag in {"td", "th"} and frame["cell"] is not None:
            if frame["row"] is not None:
                frame["row"].append(" ".join(" ".join(frame["cell"]).split()))
            frame["cell"] = None
        elif tag == "tr" and frame["row"] is not None:
            frame["rows"].append(frame["row"])
            frame["row"] = None
        elif tag == "table":
            self.tables.append(self.stack.pop()["rows"])

    def handle_data(self, value: str) -> None:
        if not self.hidden:
            self.parts.append(value)
            if self.stack and self.stack[-1]["cell"] is not None:
                self.stack[-1]["cell"].append(value)


def _iso(value: str) -> str:
    require(
        isinstance(value, str) and date.fromisoformat(value).isoformat() == value,
        "Expected canonical benchmark date",
    )
    return value


def parse_country_risk(raw: bytes, charset: str, selection: dict) -> dict:
    """Parse the observed v1 NYU HTML shape; stop if headers or rows drift."""
    fields(selection, {"country", "metric"})
    text(selection["country"], "country selection")
    require(selection["metric"] in METRICS, "Select an explicit supported table metric")
    page = _Page(raw, charset)
    visible = " ".join(" ".join(page.parts).split())
    releases = re.findall(
        r"Last updated:\s*([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", visible
    )
    require(
        len(releases) == 1 and releases[0][0] in MONTHS,
        "Source release date is missing or ambiguous",
    )
    month, day, year = releases[0]
    published = date(int(year), MONTHS.index(month) + 1, int(day)).isoformat()
    tables = [table for table in page.tables if table and tuple(table[0]) == HEADERS]
    require(len(tables) == 1, "Country-risk table headers changed; review the parser")
    rows = tables[0][1:]
    require(
        bool(rows) and all(len(row) == len(HEADERS) for row in rows),
        "Country-risk table row shape changed",
    )
    countries = [row[0] for row in rows]
    require(len(set(countries)) == len(countries), "Duplicate country observations")
    chosen = [row for row in rows if row[0] == selection["country"]]
    require(len(chosen) == 1, "Selected country observation is unavailable")
    original = chosen[0][HEADERS.index(selection["metric"])]
    value = None
    if original not in {"NA", "N/A", "-", ""}:
        require(original.endswith("%"), "Expected an explicit percentage unit")
        with localcontext() as ctx:
            ctx.prec = 40
            value = format(decimal(original[:-1]) / 100, "f")
    return {
        "parser": PARSER,
        "selection": selection,
        "value": value,
        "unit": "ratio",
        "original_value": original,
        "original_unit": "percent",
        "transformation": "canonical_decimal_percent / 100",
        "original_row": dict(zip(HEADERS, chosen[0])),
        "published_on": published,
        "vintage": published,
        "publication_basis": "Source-displayed Last updated date; historical availability not independently proven",
        "definition": selection["metric"],
        "geography": selection["country"],
    }


def _request(request: dict) -> None:
    from valuation_download import validate_url

    fields(
        request,
        {
            "parser",
            "landing_url",
            "dataset_url",
            "terms_url",
            "terms_note",
            "copy_permitted",
            "observed_on",
            "observed_basis",
            "selection",
            "public_query",
        },
    )
    require(request["parser"] == PARSER, "Unsupported benchmark parser")
    for key in ("landing_url", "dataset_url", "terms_url"):
        validate_url(request[key])
    for key in ("terms_note", "observed_basis", "public_query"):
        text(request[key], key)
    require(type(request["copy_permitted"]) is bool, "Record the source reuse decision")
    if request["observed_on"] is not None:
        _iso(request["observed_on"])
    fields(request["selection"], {"country", "metric"})
    text(request["selection"]["country"], "country")
    require(request["selection"]["metric"] in METRICS, "Unsupported selected metric")


def _persist(root: Path, record: dict, captures: dict[str, bytes]) -> dict:
    require(
        not any(path.is_symlink() for path in (root, *root.parents)),
        "Acquisition output path must not contain symlinks",
    )
    identity = digest(
        {key: value for key, value in record.items() if key != "retrieved_at"}
    )
    record = {**record, "acquisition_id": identity}
    target = root / f"benchmark-{identity}"
    require(not target.is_symlink(), "Acquisition revision must not be a symlink")
    if target.exists():
        existing = read_json(target / "acquisition.json")
        require(
            {k: v for k, v in existing.items() if k != "retrieved_at"}
            == {k: v for k, v in record.items() if k != "retrieved_at"},
            "Existing acquisition record changed",
        )
        for name, raw in captures.items():
            path = target / f"{name}.source"
            require(
                path.is_file() and not path.is_symlink() and path.read_bytes() == raw,
                "Existing acquisition bytes changed",
            )
        return {"record": existing, "output_dir": str(target)}
    target.mkdir(parents=True)
    for name, raw in captures.items():
        with (target / f"{name}.source").open("xb") as handle:
            handle.write(raw)
    with (target / "acquisition.json").open("x", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return {"record": record, "output_dir": str(target)}


def acquire_benchmark(
    request: dict,
    output_root: Path,
    *,
    fetch: Callable | None = None,
    now: datetime | None = None,
) -> dict:
    """Capture one selected public observation or preserve its explicit failure."""
    from valuation_download import download_html

    _request(request)
    current = now or datetime.now(timezone.utc)
    require(current.tzinfo is not None, "Acquisition clock must be timezone-aware")
    retrieved_on = current.astimezone(timezone.utc).date().isoformat()
    record: dict = {
        "schema_version": "vera.business_valuation.acquisition.v1",
        "request": request,
        "retrieved_at": current.isoformat(),
        "retrieved_on": retrieved_on,
        "captures": {},
        "observation": None,
        "status": "reference_only",
        "failure": None,
    }
    captures: dict[str, bytes] = {}
    if not request["copy_permitted"]:
        return _persist(output_root, record, captures)
    fetch = fetch or download_html
    try:
        for name, url in (
            ("landing", request["landing_url"]),
            ("terms", request["terms_url"]),
            ("dataset", request["dataset_url"]),
        ):
            if name != "landing":
                landing = record["captures"]["landing"]
                page = _Page(captures["landing"], landing["charset"])
                links = {
                    urldefrag(urljoin(landing["final_url"], link))[0]
                    for link in page.links
                }
                require(
                    url in links,
                    "Selected URL was not observed on the captured landing page",
                )
            raw, metadata = fetch(url)
            captures[name] = raw
            record["captures"][name] = metadata
        dataset = record["captures"]["dataset"]
        observation = parse_country_risk(
            captures["dataset"], dataset["charset"], request["selection"]
        )
        observed = request["observed_on"]
        require(
            observation["published_on"] <= retrieved_on
            and (observed is None or observed <= observation["published_on"]),
            "Acquisition dates are inconsistent",
        )
        observation.update(
            source_url=dataset["final_url"],
            observed_on=observed,
            observed_basis=request["observed_basis"],
            retrieved_on=retrieved_on,
            document_sha256=dataset["sha256"],
            status="proposed",
        )
        observation["observation_id"] = digest(observation)
        record["observation"] = observation
        record["status"] = (
            "acquired"
            if observed is not None and observation["value"] is not None
            else "metadata_or_value_missing"
        )
    except (ValueError, OSError, HTTPException) as exc:
        record["status"] = "unavailable"
        record["failure"] = {"kind": type(exc).__name__, "reason": str(exc)}
    return _persist(output_root, record, captures)


def validate_benchmark_bindings(case: dict, sources: dict, root: Path) -> None:
    """Replay imported acquisition evidence before a value can enter calculations."""
    for item in case["inputs"]:
        benchmark = item.get("benchmark", {})
        binding = benchmark.get("acquisition")
        if binding is None:
            continue
        fields(binding, {"record_source_id", "document_source_id", "observation_id"})
        record_id, document_id = (
            binding["record_source_id"],
            binding["document_source_id"],
        )
        require(
            {record_id, document_id} <= set(item["source_ids"]) <= sources.keys(),
            "Acquisition record and document must be declared input sources",
        )
        record = read_json(root / sources[record_id]["path"])
        fields(
            record,
            {
                "schema_version",
                "request",
                "retrieved_at",
                "retrieved_on",
                "captures",
                "observation",
                "status",
                "failure",
                "acquisition_id",
            },
        )
        require(
            digest(
                {
                    key: value
                    for key, value in record.items()
                    if key not in {"retrieved_at", "acquisition_id"}
                }
            )
            == record["acquisition_id"],
            "Acquisition record identity changed",
        )
        require(
            record["schema_version"] == "vera.business_valuation.acquisition.v1"
            and record["status"] == "acquired",
            "Acquisition is not a complete observation",
        )
        observation = record["observation"]
        require(
            observation["observation_id"] == binding["observation_id"]
            and digest({k: v for k, v in observation.items() if k != "observation_id"})
            == binding["observation_id"],
            "Acquisition observation identity changed",
        )
        require(
            sources[document_id]["sha256"] == observation["document_sha256"],
            "Acquisition document revision changed",
        )
        document = root / sources[document_id]["path"]
        require(
            document.stat().st_size <= 2 * 1024 * 1024,
            "Acquisition replay exceeds 2 MiB",
        )
        parsed = parse_country_risk(
            document.read_bytes(),
            record["captures"]["dataset"]["charset"],
            observation["selection"],
        )
        require(
            all(observation[key] == value for key, value in parsed.items()),
            "Acquisition parser replay differs",
        )
        require(
            item["value"] == observation["value"]
            and item["unit"] == observation["unit"],
            "Selected input differs from acquired observation",
        )
        require(
            all(
                benchmark[key] == observation[key]
                for key in (
                    "source_url",
                    "observed_on",
                    "published_on",
                    "retrieved_on",
                    "vintage",
                    "definition",
                    "geography",
                )
            ),
            "Benchmark metadata differs from acquired observation",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = acquire_benchmark(read_json(args.request), args.output_dir)
    except (ValueError, OSError) as exc:
        logging.error("Benchmark acquisition blocked: %s", exc)
        return 2
    logging.info(
        "%s",
        json.dumps(
            {"status": result["record"]["status"], "output_dir": result["output_dir"]}
        ),
    )
    return 0 if result["record"]["status"] == "acquired" else 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
