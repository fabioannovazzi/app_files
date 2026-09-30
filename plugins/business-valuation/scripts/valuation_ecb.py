"""Read explicitly selected ECB AAA spot observations without inventing a vintage.

CSV structure, series identity and decimal units are mechanically verifiable.
Economic relevance, maturity selection and historical availability require review.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from decimal import localcontext

from valuation_case import fields, require
from valuation_engine import ValuationError, decimal

__all__ = ["PARSER", "validate_selection", "parse_ecb_spot"]
PARSER = "ecb-aaa-spot-csv/v1"
HEADERS = (
    "KEY,FREQ,REF_AREA,CURRENCY,PROVIDER_FM,INSTRUMENT_FM,PROVIDER_FM_ID,"
    "DATA_TYPE_FM,TIME_PERIOD,OBS_VALUE,OBS_STATUS,OBS_CONF,OBS_PRE_BREAK,"
    "OBS_COM,TIME_FORMAT,BREAKS,COLLECTION,COMPILING_ORG,DISS_ORG,DOM_SER_IDS,"
    "FM_CONTRACT_TIME,FM_COUPON_RATE,FM_IDENTIFIER,FM_LOT_SIZE,FM_MATURITY,"
    "FM_OUTS_AMOUNT,FM_PUT_CALL,FM_STRIKE_PRICE,PUBL_MU,PUBL_PUBLIC,"
    "UNIT_INDEX_BASE,COMPILATION,COVERAGE,DECIMALS,SOURCE_AGENCY,SOURCE_PUB,"
    "TITLE,TITLE_COMPL,UNIT,UNIT_MULT"
).split(",")
PREFIX = "YC.B.U2.EUR.4F.G_N_A.SV_C_YM."


def validate_selection(selection: dict) -> None:
    """Require an explicit AAA spot series and exact observation date."""
    fields(selection, {"series_key", "observed_on"})
    key = selection["series_key"]
    require(
        isinstance(key, str)
        and re.fullmatch(re.escape(PREFIX) + r"SR_(?:[1-9]\d?Y)?(?:[1-9]\d?M)?", key)
        is not None
        and not key.endswith("SR_"),
        "Select an explicit ECB AAA spot series, not a forward or par rate",
    )
    observed = selection["observed_on"]
    require(
        isinstance(observed, str)
        and date.fromisoformat(observed).isoformat() == observed,
        "Expected canonical ECB observation date",
    )


def parse_ecb_spot(raw: bytes, charset: str, selection: dict) -> dict:
    """Preserve one CSV row and continuous rate; publication/vintage stay unknown."""
    validate_selection(selection)
    require(len(raw) <= 2 * 1024 * 1024 and b"\x00" not in raw, "Invalid ECB CSV bytes")
    reader = csv.reader(io.StringIO(raw.decode(charset)), strict=True)
    rows: dict[tuple[str, str], list[str]] = {}
    try:
        require(
            next(reader, None) == HEADERS, "ECB CSV headers changed; review the parser"
        )
        for values in reader:
            require(len(values) == len(HEADERS), "ECB CSV row shape changed")
            identity = (values[0], values[8])
            require(identity not in rows, "Duplicate ECB series/date observation")
            rows[identity] = values
    except csv.Error as exc:
        raise ValuationError("Malformed ECB CSV") from exc
    selected = rows.get((selection["series_key"], selection["observed_on"]))
    require(selected is not None, "Selected ECB observation is unavailable")
    row = dict(zip(HEADERS, selected or []))
    expected = {
        "FREQ": "B",
        "REF_AREA": "U2",
        "CURRENCY": "EUR",
        "PROVIDER_FM": "4F",
        "INSTRUMENT_FM": "G_N_A",
        "PROVIDER_FM_ID": "SV_C_YM",
        "DATA_TYPE_FM": selection["series_key"].removeprefix(PREFIX),
        "TIME_FORMAT": "P1D",
        "COLLECTION": "E",
        "UNIT": "PCPA",
        "UNIT_MULT": "0",
    }
    require(
        all(row[k] == v for k, v in expected.items()), "ECB series metadata changed"
    )
    require(
        "continuous compounding" in row["TITLE_COMPL"]
        and "Yield curve spot rate," in row["TITLE_COMPL"],
        "ECB rate definition changed",
    )
    require(row["OBS_STATUS"] in {"A", "M"}, "ECB observation status needs review")
    require(row["OBS_CONF"] == "F", "ECB observation confidentiality changed")
    require(
        not any(row[k] for k in ("OBS_PRE_BREAK", "OBS_COM", "BREAKS")),
        "ECB observation has qualifications requiring review",
    )
    original = row["OBS_VALUE"]
    require(row["OBS_STATUS"] != "M" or not original, "Missing ECB status has a value")
    value = None
    if original:
        with localcontext() as ctx:
            ctx.prec = 40
            value = format(decimal(original) / 100, "f")
    return {
        "parser": PARSER,
        "selection": selection,
        "value": value,
        "unit": "ratio",
        "original_value": original,
        "original_unit": "percent per annum (PCPA), unit multiplier 0",
        "transformation": "canonical_decimal_percent / 100; continuous compounding unchanged",
        "compounding": "continuous",
        "rate_kind": "spot",
        "currency": "EUR",
        "original_row": row,
        "observed_on": row["TIME_PERIOD"],
        "observed_basis": "Selected series CSV TIME_PERIOD; not the publication date",
        "published_on": None,
        "vintage": None,
        "publication_basis": "CSV has no observation publication/vintage evidence; HTTP metadata and scheduled releases do not establish it",
        "definition": row["TITLE_COMPL"],
        "geography": "Euro area (changing composition), AAA-rated government issuers",
    }
