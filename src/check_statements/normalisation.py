from __future__ import annotations

"""Normalisation utilities for parsing and cleaning input data."""

from datetime import date, datetime, timedelta
from pathlib import Path
import json
import logging
import re
import unicodedata
from typing import Any

import polars as pl

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency
    np = None  # type: ignore

try:
    from rapidfuzz import fuzz  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    fuzz = None  # type: ignore

try:
    from dateutil.parser import parse as dateutil_parse  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    dateutil_parse = None  # type: ignore

from parsers.extractors import normalise_name

logger = logging.getLogger(__name__)

IT_MONTHS = {
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12,
    "gen": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "mag": 5,
    "giu": 6,
    "lug": 7,
    "ago": 8,
    "set": 9,
    "ott": 10,
    "nov": 11,
    "dic": 12,
}

_CONFIG_DIR_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "config",
    Path(__file__).resolve().parent.parent / "config",
)

# Optional alias map for brand/counterparty normalisation
_ALIAS_PATH_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "brand_aliases.json",
    Path(__file__).resolve().parent.parent / "brand_aliases.json",
)
_ALIAS_MAP: dict[str, str] | None = None


def _load_alias_map() -> dict[str, str]:
    global _ALIAS_MAP
    if _ALIAS_MAP is not None:
        return _ALIAS_MAP
    for p in _ALIAS_PATH_CANDIDATES:
        try:
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # normalise keys/values to lowercase without accents/punct via normalise_name
                    mapped: dict[str, str] = {}
                    for k, v in data.items():
                        try:
                            nk = normalise_name(str(k))
                            nv = normalise_name(str(v))
                            mapped[nk] = nv
                        except Exception:
                            continue
                    _ALIAS_MAP = mapped
                    return _ALIAS_MAP
        except Exception:
            continue
    _ALIAS_MAP = {}
    return _ALIAS_MAP


def _norm_token(s: str) -> str:
    """Lowercase, strip accents, and drop punctuation for robust comparisons."""
    if s is None:
        return ""
    value = unicodedata.normalize("NFKD", str(s))
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    value = re.sub(r"\s+", " ", value).strip()
    return re.sub(r"[^a-z0-9]", "", value)


def _token_intersection_ratio(a: str, b: str) -> int:
    if not a or not b:
        return 0
    tok_a = set(re.findall(r"[A-Z0-9]+", a.upper()))
    tok_b = set(re.findall(r"[A-Z0-9]+", b.upper()))
    if not tok_a or not tok_b:
        return 0
    overlap = len(tok_a & tok_b)
    return int(100.0 * overlap / max(len(tok_a), len(tok_b)))


def _similarity(a: str, b: str) -> float:
    """Return a fuzzy similarity score in ``[0, 100]`` for two strings."""
    if not a or not b:
        return 0.0
    if fuzz:
        return float(fuzz.token_set_ratio(a, b))
    return float(_token_intersection_ratio(a, b))


def _clean_description_local(desc: str) -> str:
    """Return a simplified upper-case description for fuzzy matching (IT-first)."""
    if not desc:
        return ""

    s = str(desc)

    patterns = [
        r"(?i)bonifico\s+o/c:?",
        r"(?i)bonifico(?:\s+sepa|\s+istantaneo)?",
        r"(?i)sepa",
        r"(?i)commissione|\bcomm\b",
        r"(?i)disposizione\s+a\s+favore\s+di",
        r"(?i)a\s+favore\s+di",
        r"(?i)ordine\s+di",
        r"(?i)pag\.?\s*deb\.?",
        r"(?i)addebito|accredito",
        r"(?i)\b(?:sdd|rid)\b",
        r"(?i)num(?:ero)?\.?\s*(?:bon(?:ifico)?|pratica|rif(?:erimento)?)\b[^\n]*",
    ]
    for pattern in patterns:
        s = re.sub(pattern, " ", s)

    s = re.sub(r"(?i)abi-?cab[:]?\s*\d{5}[ -]?\d{5}", " ", s)
    s = re.sub(r"(?i)\bcro[:\s-]*[A-Z0-9]+", " ", s)
    s = re.sub(r"(?i)\btrn[:\s-]*[A-Z0-9]+", " ", s)
    s = re.sub(r"(?i)\biban[:\s]*[A-Z]{2}[0-9A-Z]+", " ", s)
    s = re.sub(r"(?i)\bcig\w+", " ", s)
    s = re.sub(r"(?i)\bcup\w+", " ", s)

    s = re.sub(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", " ", s)
    s = re.sub(r"\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)?\b", " ", s)
    s = re.sub(r"\b\d{1,3}(?:\.\d{3})*,\d+\b", " ", s)
    s = re.sub(r"\b\d{1,3}(?:,\d{3})*\.\d+\b", " ", s)
    s = re.sub(r"\b\d+\b", " ", s)

    s = re.sub(r"[^A-Za-z]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    if not s:
        return ""

    default_stop = {
        "BONIFICO",
        "SEPA",
        "ISTANTANEO",
        "COMMISSIONE",
        "COMM",
        "ADDEBITO",
        "ACCREDITO",
        "DISPOSIZIONE",
        "ORDINE",
        "PAG",
        "PAGAMENTO",
        "NUM",
        "NUMERO",
        "PRATICA",
        "RIF",
        "RIFERIMENTO",
        "DEB",
        "CRO",
        "TRN",
        "IBAN",
        "DI",
        "DA",
        "IN",
        "SU",
        "CON",
        "PER",
        "E",
        "IL",
        "LA",
        "LO",
        "L",
        "I",
        "GLI",
        "LE",
        "DEL",
        "DELLA",
        "DELL",
        "DEI",
        "DEGLI",
        "DELLE",
        "UN",
        "UNA",
        "UNO",
        "AL",
        "AI",
    }
    default_keep = {
        "STIPENDIO",
        "AFFITTO",
        "RIMBORSO",
        "ASSICURAZIONI",
        "BOLLETTA",
        "IMU",
        "TARI",
        "IVA",
        "TELEPASS",
    }

    for fname in ("normalisation_stopwords.it.json", "normalisation_stopwords.en.json"):
        for base in _CONFIG_DIR_CANDIDATES:
            cfg_path = base / fname
            if not cfg_path.exists():
                continue
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - optional config
                logger.warning("Failed to load %s: %s", cfg_path, exc)
                continue
            stop_extra = {str(x).upper() for x in cfg.get("stopwords", [])}
            keep_extra = {str(x).upper() for x in cfg.get("keepwords", [])}
            default_stop |= stop_extra
            default_keep |= keep_extra

    tokens = [t for t in s.upper().split() if t]
    filtered = [t for t in tokens if (t in default_keep) or (t not in default_stop)]
    if not filtered:
        filtered = tokens
    return " ".join(filtered)


def _amount_expr(col: str) -> pl.Expr:
    """Return a Polars expression that normalises amount strings."""
    return (
        pl.col(col)
        .cast(pl.Utf8, strict=False)
        .str.replace_all(r"[€\u00A0\s]", "")
        .str.replace_all(r"^\((.*)\)$", r"-\1")
        .str.replace_all(r"^(.*)-$", r"-\1")
        .str.replace_all(r"\.", "")
        .str.replace_all(r",", ".")
        .str.replace_all("€", "")
        .str.replace_all("£", "")
        .cast(pl.Float64, strict=False)
    )


def _parse_dates_expr(col: str) -> pl.Expr:
    """Vectorised date parsing expression used when ingesting spreadsheets."""
    return pl.coalesce(
        [
            pl.col(col).cast(pl.Date, strict=False),
            pl.col(col)
            .cast(pl.Utf8, strict=False)
            .str.replace_all(
                r"[T ]\d{1,2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+\-]\d{2}:\d{2})?$",
                "",
            )
            .str.strptime(pl.Date, "%Y-%m-%d", strict=False),
            pl.col(col)
            .cast(pl.Utf8, strict=False)
            .str.strptime(pl.Date, "%d/%m/%Y", strict=False),
            pl.col(col)
            .cast(pl.Utf8, strict=False)
            .str.strptime(pl.Date, "%d-%m-%Y", strict=False),
            pl.col(col)
            .cast(pl.Utf8, strict=False)
            .str.strptime(pl.Date, "%m/%d/%Y", strict=False),
            pl.col(col)
            .cast(pl.Utf8, strict=False)
            .str.strptime(pl.Date, "%d.%m.%Y", strict=False),
            pl.col(col).cast(pl.Utf8, strict=False).str.to_date(strict=False),
        ]
    )


def _parse_date_any(value: Any) -> date | None:
    """Parse many date representations into a :class:`datetime.date`."""
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()

    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().date()  # type: ignore[arg-type]
        except (TypeError, ValueError, OverflowError):
            pass

    if np is not None and isinstance(value, np.datetime64):
        try:
            ts = value.astype("datetime64[s]").astype(int)
            return datetime.utcfromtimestamp(int(ts)).date()
        except (TypeError, ValueError, OverflowError):
            pass

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            base = datetime(1899, 12, 30)
            return (base + timedelta(days=int(value))).date()
        except (TypeError, ValueError, OverflowError):
            pass

    s = str(value).strip()
    if not s:
        return None

    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        try:
            base = datetime(1899, 12, 30)
            return (base + timedelta(days=int(float(s)))).date()
        except (TypeError, ValueError, OverflowError):
            pass

    if re.fullmatch(
        r"\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+\-]\d{2}:\d{2})?)?",
        s,
    ):
        s2 = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s2)
            return dt.date() if isinstance(dt, datetime) else dt
        except ValueError:
            try:
                return datetime.strptime(s[:10], "%Y-%m-%d").date()
            except ValueError:
                pass

    m = re.match(
        r"^(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s+\d{1,2}:\d{2}(:\d{2})?(?:\.\d+)?(?:Z|[+\-]\d{2}:\d{2})?$",
        s,
    )
    if m:
        s = m.group(1)

    for fmt in (
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%d.%m.%Y",
        "%d.%m.%y",
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    tokens = re.split(r"[\s/-]+", s.lower())
    if len(tokens) >= 2 and tokens[1] in IT_MONTHS:
        try:
            day = int(tokens[0])
            month = IT_MONTHS[tokens[1]]
            year = datetime.today().year
            if len(tokens) >= 3:
                year_token = tokens[2]
                year = int(year_token)
                if year < 100:
                    year += 2000 if year < 70 else 1900
            return date(year, month, day)
        except ValueError:
            return None

    if dateutil_parse is not None:
        if "," in s and not re.search(r"\d{4}", s):
            return None
        try:
            return dateutil_parse(s, dayfirst=True, fuzzy=True).date()
        except Exception as exc:  # pragma: no cover - dateutil quirks
            logger.debug("dateutil fallback failed: %s", exc)

    return None


_parse_date = _parse_date_any


def _parse_amount(value: Any) -> float | None:
    """Parse a numeric amount from many string representations."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    if s.endswith("-"):
        negative = True
        s = s[:-1]

    s = s.replace("€", "").replace("£", "")
    s = re.sub(r"[€$£\s\u00A0]", "", s)

    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "." in s:
        s = s.replace(",", "")
    try:
        val = float(s)
    except ValueError:
        match = re.search(r"[-+]?[0-9]+(?:[.,][0-9]+)?", s)
        if not match:
            return None
        try:
            val = float(match.group(0).replace(",", "."))
        except ValueError:
            logger.warning("Could not parse amount from substring '%s'", match.group(0))
            return None
    return -val if negative else val


def normalize_name(s: str) -> str:
    """Public wrapper returning a normalised counterparty name."""
    name = normalise_name(s)
    try:
        alias_map = _load_alias_map()
        return alias_map.get(name, name)
    except Exception:
        return name


def beneficiary_similarity(a: str, b: str) -> float:
    """Return similarity as a fraction in ``[0, 1]``."""
    return _similarity(a, b) / 100.0


__all__ = (
    "IT_MONTHS",
    "_amount_expr",
    "_clean_description_local",
    "_norm_token",
    "_parse_amount",
    "_parse_date",
    "_parse_date_any",
    "_parse_dates_expr",
    "_similarity",
    "_token_intersection_ratio",
    "beneficiary_similarity",
    "normalize_name",
)
