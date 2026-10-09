"""Source-cell arithmetic for annual OIC statements, without inferred mappings.

Code is used for mechanically verifiable cell identity, arithmetic and receipts.
The calling model owns mapping, note selection and interpretation. Missing facts
propagate as unavailable; a reconstructed total never replaces a source total.
"""

from __future__ import annotations

import hashlib
import io
import re
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path, PurePosixPath
from typing import Any

from preparation_contract_kernel import file_snapshot_beneath

__all__ = ["FIELDS", "FORMULAS", "CHECKS", "source_paths", "analyse"]

FIELDS = {
    "revenue": "Ricavi",
    "production_value": "Valore della produzione",
    "production_costs": "Costi della produzione",
    "ebit": "Risultato operativo A meno B",
    "depreciation": "Ammortamenti materiali",
    "amortisation": "Ammortamenti immateriali",
    "credit_impairment": "Svalutazioni crediti",
    "other_impairment": "Altre svalutazioni delle immobilizzazioni",
    "b10": "Totale B.10 dichiarato",
    "pretax": "Risultato prima delle imposte",
    "tax": "Imposte",
    "net_profit": "Risultato netto",
    "fixed_assets": "Immobilizzazioni dichiarate",
    "inventory": "Rimanenze",
    "receivables": "Crediti",
    "current_financial_assets": "Attività finanziarie non immobilizzate",
    "cash": "Disponibilità liquide",
    "current_assets": "Attivo circolante dichiarato",
    "prepayments": "Ratei e risconti attivi",
    "total_assets": "Totale attivo dichiarato",
    "total_liabilities_equity": "Totale passivo dichiarato",
    "equity": "Patrimonio netto",
    "total_debt": "Debiti complessivi",
    "financial_debt": "Debito finanziario nel perimetro mappato",
    "current_liabilities": "Passività correnti nel perimetro mappato",
    "personnel": "Costi del personale",
    "third_party_assets": "Godimento beni di terzi",
}
# Ordered dependencies are also the editable Excel formula specification.
FORMULAS = {
    "da": ("Ammortamenti", (("depreciation", 1), ("amortisation", 1))),
    "ebitda_da": ("EBITDA: A meno B più soli ammortamenti", (("ebit", 1), ("da", 1))),
    "ebitda_b10": (
        "A meno B più tutto B.10 (definizione distinta)",
        (("ebit", 1), ("b10", 1)),
    ),
    "ebitda_definition_gap": (
        "Differenza fra le due definizioni",
        (("ebitda_b10", 1), ("ebitda_da", -1)),
    ),
    "current_assets_rebuilt": (
        "Attivo circolante ricostruito",
        (
            ("inventory", 1),
            ("receivables", 1),
            ("current_financial_assets", 1),
            ("cash", 1),
        ),
    ),
    "assets_from_reported_subtotals": (
        "Attivo da subtotali dichiarati",
        (("fixed_assets", 1), ("current_assets", 1), ("prepayments", 1)),
    ),
    "assets_from_components": (
        "Attivo da componenti",
        (("fixed_assets", 1), ("current_assets_rebuilt", 1), ("prepayments", 1)),
    ),
    "mapped_debt_less_cash": (
        "Debito finanziario mappato meno liquidità (non PFN completa)",
        (("financial_debt", 1), ("cash", -1)),
    ),
}
CHECKS = {
    "current_assets_components": (
        "Attivo circolante dichiarato meno componenti",
        (("current_assets", 1), ("current_assets_rebuilt", -1)),
    ),
    "assets_subtotals": (
        "Attivo dichiarato meno subtotali dichiarati",
        (("total_assets", 1), ("assets_from_reported_subtotals", -1)),
    ),
    "assets_components": (
        "Attivo dichiarato meno componenti ricostruite",
        (("total_assets", 1), ("assets_from_components", -1)),
    ),
    "balance_sheet": (
        "Totale attivo meno totale passivo",
        (("total_assets", 1), ("total_liabilities_equity", -1)),
    ),
    "operating_profit": (
        "Valore meno costi della produzione meno risultato operativo",
        (("production_value", 1), ("production_costs", -1), ("ebit", -1)),
    ),
    "net_profit": (
        "Risultato ante imposte meno imposte meno risultato netto",
        (("pretax", 1), ("tax", -1), ("net_profit", -1)),
    ),
    "b10_components": (
        "B.10 dichiarato meno ammortamenti e svalutazioni",
        (("b10", 1), ("da", -1), ("credit_impairment", -1), ("other_impairment", -1)),
    ),
}
RATIOS = {
    "ebitda_margin_percent": (
        "EBITDA con soli ammortamenti / ricavi (%)",
        "ebitda_da",
        "revenue",
        100,
    ),
    "equity_assets_percent": (
        "Patrimonio netto / attivo (%)",
        "equity",
        "total_assets",
        100,
    ),
    "current_ratio_reported": (
        "Attivo circolante dichiarato / passività correnti",
        "current_assets",
        "current_liabilities",
        1,
    ),
    "current_ratio_rebuilt": (
        "Attivo circolante ricostruito / passività correnti",
        "current_assets_rebuilt",
        "current_liabilities",
        1,
    ),
}


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: non-empty text required")
    return value


def _number(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("A finite numeric cell is required; blank is not zero")
    text = str(value)
    if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", text):
        raise ValueError(f"Ambiguous numeric cell: {text!r}")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal") from exc
    if len(result.as_tuple().digits) > 28 or result.as_tuple().exponent < -6:
        raise ValueError("Amount exceeds 28 digits or six decimal places")
    return result


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def source_paths(case: dict[str, Any], root: Path) -> dict[str, Path]:
    """Resolve declared paths lexically before the Archive gate opens sources."""
    sources = case.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("sources must be a non-empty object")
    paths = {}
    for key, source in sources.items():
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]*", key):
            raise ValueError("Invalid source ID")
        path = PurePosixPath(_text(source["path"], "source path"))
        if path.is_absolute() or ".." in path.parts or "\\" in str(path):
            raise ValueError("Source paths must be relative and cannot escape the case")
        paths[key] = root.joinpath(*path.parts)
    return paths


def _source_bytes(case: dict[str, Any], root: Path) -> dict[str, bytes]:
    result = {}
    for key, path in source_paths(case, root).items():
        count, digest = file_snapshot_beneath(path, root=root)
        if digest != case["sources"][key]["sha256"]:
            raise ValueError(f"Source hash changed: {key}")
        content = path.read_bytes()
        if len(content) != count or hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f"Source changed during read: {key}")
        result[key] = content
    return result


def _validate_case(case: dict[str, Any]) -> tuple[list[str], Decimal]:
    if case.get("schema_version") != "vera.annual_statements_case.v1":
        raise ValueError("Unsupported annual statements case schema")
    if case.get("accounting_basis") != "italian_oic_positive_expenses":
        raise ValueError(
            "This recipe requires an explicit OIC positive-expense mapping"
        )
    _text(case.get("entity"), "entity")
    _text(case.get("mapping_basis"), "mapping_basis")
    if not re.fullmatch(r"[A-Z]{3}", str(case.get("currency", ""))):
        raise ValueError("Explicit currency required")
    years = case.get("years")
    if (
        not isinstance(years, list)
        or not 2 <= len(years) <= 10
        or any(
            not isinstance(y, str) or not re.fullmatch(r"[12][0-9]{3}", y)
            for y in years
        )
        or years != sorted(set(years))
    ):
        raise ValueError("years must contain two to ten distinct ordered years")
    tolerance = _number(case["tolerance"])
    if tolerance < 0:
        raise ValueError("Tolerance cannot be negative")
    fields = case["fields"]
    if not isinstance(fields, dict) or not fields or set(fields) - set(FIELDS):
        raise ValueError("Unknown or empty financial field mapping")
    for values in fields.values():
        if not isinstance(values, dict) or set(values) != set(years):
            raise ValueError(
                "Every mapped field must explicitly cover every year (null for missing)"
            )
    if not isinstance(case.get("limitations"), list) or not case["limitations"]:
        raise ValueError("Record scope limitations explicitly")
    for limit in case["limitations"]:
        _text(limit, "limitation")
    return years, tolerance


def _read_facts(
    case: dict[str, Any], contents: dict[str, bytes], years: list[str]
) -> list[dict[str, Any]]:
    import openpyxl

    books: dict[str, Any] = {}
    facts = []
    used: set[tuple[str, str, str]] = set()
    try:
        for key in FIELDS:
            for year in years:
                ref = case["fields"].get(key, {}).get(year)
                if ref is None:
                    facts.append(
                        {
                            "key": key,
                            "year": year,
                            "value": None,
                            "source": None,
                            "status": "not_available",
                        }
                    )
                    continue
                if set(ref) != {"source_id", "sheet", "cell", "scale"}:
                    raise ValueError(
                        "Cell mappings require source_id, sheet, cell, scale"
                    )
                source_id = ref["source_id"]
                if source_id not in contents or not case["sources"][source_id][
                    "path"
                ].lower().endswith(".xlsx"):
                    raise ValueError("Financial cells require a declared XLSX source")
                if not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}", ref["cell"]):
                    raise ValueError("Invalid cell coordinate")
                identity = (source_id, ref["sheet"], ref["cell"])
                if identity in used:
                    raise ValueError(
                        "A source cell cannot supply multiple years or fields"
                    )
                used.add(identity)
                if source_id not in books:
                    books[source_id] = openpyxl.load_workbook(
                        io.BytesIO(contents[source_id]),
                        read_only=True,
                        data_only=False,
                        keep_links=False,
                    )
                book = books[source_id]
                if ref["sheet"] not in book.sheetnames:
                    raise ValueError("Mapped sheet does not exist")
                cell = book[ref["sheet"]][ref["cell"]]
                if cell.data_type in {"f", "e"}:
                    raise ValueError(
                        "Formula/error source cells require a verified values export"
                    )
                scale = _number(ref["scale"])
                if scale <= 0:
                    raise ValueError("Source scale must be positive")
                value = _number(cell.value) * scale
                facts.append(
                    {
                        "key": key,
                        "year": year,
                        "value": _decimal(value),
                        "source_value": str(cell.value),
                        "source": ref,
                        "status": "mapped",
                    }
                )
    finally:
        for book in books.values():
            book.close()
    return facts


def _sum(
    values: dict[str, Decimal | None], terms: tuple[tuple[str, int], ...]
) -> Decimal | None:
    if any(values[key] is None for key, _sign in terms):
        return None
    return sum((values[key] * sign for key, sign in terms), Decimal(0))  # type: ignore[operator]


def _commentary(
    case: dict[str, Any], contents: dict[str, bytes]
) -> list[dict[str, Any]]:
    """Validate reference closure, never certify a paragraph's meaning."""
    notes = case.get("commentary", [])
    if not isinstance(notes, list):
        raise ValueError("commentary must be a list")
    for note in notes:
        if note.get("kind") not in {"observed", "inferred", "question"}:
            raise ValueError(
                "Commentary must distinguish observed, inferred and question"
            )
        _text(note.get("text"), "commentary text")
        if not isinstance(note.get("references"), list) or not note["references"]:
            raise ValueError("Every commentary item needs explicit source references")
        for ref in note["references"]:
            if ref["source_id"] not in contents:
                raise ValueError("Unknown commentary source")
            _text(ref.get("locator"), "commentary locator")
    coverage = case.get("coverage")
    if not isinstance(coverage, dict) or set(coverage) != set(contents):
        raise ValueError(
            "Coverage must record every supplied source, including unread sources"
        )
    for entry in coverage.values():
        if entry.get("status") not in {"read", "partial", "unread"}:
            raise ValueError("Coverage status must be read, partial or unread")
        _text(entry.get("basis"), "coverage basis")
    return notes


def analyse(case: dict[str, Any], root: Path) -> dict[str, Any]:
    """Calculate fixed annual comparisons, preserving source exceptions."""
    years, tolerance = _validate_case(case)
    contents = _source_bytes(case, root)
    notes = _commentary(case, contents)
    with localcontext() as context:
        context.prec = 80
        facts = _read_facts(case, contents, years)
        values_by_year = {
            year: {
                f["key"]: None if f["value"] is None else Decimal(f["value"])
                for f in facts
                if f["year"] == year
            }
            for year in years
        }
        metrics, checks = [], []
        for index, year in enumerate(years):
            values = values_by_year[year]
            for key, (label, terms) in FORMULAS.items():
                values[key] = _sum(values, terms)
                metrics.append(
                    {
                        "key": key,
                        "label": label,
                        "year": year,
                        "value": _decimal(values[key]),
                        "unit": case["currency"],
                        "dependencies": [k for k, _ in terms],
                    }
                )
            for key, (label, numerator, denominator, scale) in RATIOS.items():
                n, d = values[numerator], values[denominator]
                value = (
                    None
                    if n is None or d in (None, 0)
                    else (n / d * scale).quantize(Decimal("0.000001"))
                )
                metrics.append(
                    {
                        "key": key,
                        "label": label,
                        "year": year,
                        "value": _decimal(value),
                        "unit": "percent" if scale == 100 else "ratio",
                        "dependencies": [numerator, denominator],
                    }
                )
            previous = (
                None if index == 0 else values_by_year[years[index - 1]]["revenue"]
            )
            revenue = values["revenue"]
            growth = (
                None
                if previous in (None, 0) or revenue is None
                else ((revenue / previous - 1) * 100).quantize(Decimal("0.000001"))
            )
            metrics.append(
                {
                    "key": "revenue_change_percent",
                    "label": "Variazione ricavi rispetto al periodo precedente disponibile (%)",
                    "year": year,
                    "value": _decimal(growth),
                    "unit": "percent",
                    "dependencies": ["revenue"],
                }
            )
            for key, (label, terms) in CHECKS.items():
                difference = _sum(values, terms)
                status = (
                    "not_available"
                    if difference is None
                    else "passed" if abs(difference) <= tolerance else "exception"
                )
                checks.append(
                    {
                        "key": key,
                        "label": label,
                        "year": year,
                        "difference": _decimal(difference),
                        "status": status,
                        "dependencies": [k for k, _ in terms],
                    }
                )
    return {
        "schema_version": "vera.annual_statements_result.v1",
        "recipe_id": "annual_oic_source_cells.v1",
        "entity": case["entity"],
        "currency": case["currency"],
        "years": years,
        "status": (
            "qualified"
            if any(c["status"] != "passed" for c in checks)
            else "calculated"
        ),
        "professional_review": "pending",
        "report_ready": False,
        "source_tie_out": "mapped_cells_only_not_filing_audit",
        "tolerance": case["tolerance"],
        "mapping_basis": case["mapping_basis"],
        "facts": facts,
        "metrics": metrics,
        "checks": checks,
        "sources": case["sources"],
        "coverage": case["coverage"],
        "commentary": notes,
        "limitations": case["limitations"],
        "definitions": [
            "EBITDA con soli ammortamenti: risultato operativo A meno B più ammortamenti materiali e immateriali; le svalutazioni restano a costo.",
            "La variante A meno B più tutto B.10 include anche le svalutazioni: non è intercambiabile con la prima definizione.",
            "I totali dichiarati e quelli ricostruiti sono distinti. Una quadratura interna non prova la correttezza dei subtotali della fonte.",
            "Valori mancanti non sono zero. Una cella zero documenta il valore nell'export, non l'assenza di un saldo economico nelle note.",
            "Debito finanziario mappato meno cassa non dimostra la completezza della PFN. Non si usa il totale dei debiti come debito finanziario.",
            "Indici arrotondati a sei decimali; importi e differenze calcolati in Decimal. Nessun rendiconto finanziario ricavato come residuo.",
        ],
    }
