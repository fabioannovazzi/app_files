#!/usr/bin/env python3
"""Exact calculations and renderers for one reviewed Centrale Rischi dataset."""

from __future__ import annotations

import csv
import hashlib
import html
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

__all__ = [
    "ANALYSIS_SCHEMA",
    "COMMENTARY_SCHEMA",
    "CentraleRischiContractError",
    "SourceTable",
    "build_analysis",
    "build_inspection",
    "build_model_context",
    "finalize_commentary",
    "load_json",
    "load_source_tables",
    "render_html",
    "render_markdown",
    "sha256_file",
    "write_excel",
    "write_json",
]

ANALYSIS_SCHEMA = "vera.centrale_rischi_analysis.v2"
COMMENTARY_SCHEMA = "vera.centrale_rischi_commentary.v1"
RECIPE_SCHEMA = "vera.centrale_rischi_recipe.v2"
WORKFLOW_ID = "centrale-rischi-review"
ORIGINAL_TERM_CLASSES = (
    "short",
    "medium",
    "long",
    "not_relevant",
    "unclassified",
)
RESIDUAL_TERM_CLASSES = (
    "within_one_year",
    "over_one_year",
    "not_relevant",
    "unclassified",
)
EXPOSURE_FAMILIES = ("performing", "suffering", "other")


class CentraleRischiContractError(ValueError):
    """Raised when supplied evidence does not satisfy the reviewed contract."""


@dataclass(frozen=True)
class SourceTable:
    """One source table with stable lineage metadata."""

    table_id: str
    source_path: Path
    table_label: str
    headers: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    source_sha256: str


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def write_json(path: Path, payload: Any) -> None:
    """Write stable UTF-8 JSON."""

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict[str, Any]:
    """Load one JSON object."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CentraleRischiContractError(f"Expected a JSON object: {path}")
    return payload


def _cell(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if value is None:
        return ""
    return value


def _source_table(
    path: Path, label: str, headers: Sequence[Any], raw_rows: Sequence[Sequence[Any]]
) -> SourceTable:
    names = tuple(str(value).strip() for value in headers)
    if not names or any(not value for value in names) or len(names) != len(set(names)):
        raise CentraleRischiContractError(
            f"Table {label!r} has blank or duplicate headers."
        )
    source_hash = sha256_file(path)
    table_id = (
        "table_"
        + hashlib.sha256(f"{source_hash}:{label}".encode("utf-8")).hexdigest()[:16]
    )
    rows = tuple(
        {name: _cell(value) for name, value in zip(names, row)}
        for row in raw_rows
        if any(value not in (None, "") for value in row)
    )
    return SourceTable(table_id, path.resolve(), label, names, rows, source_hash)


def load_source_tables(paths: Sequence[Path]) -> list[SourceTable]:
    """Read CSV and Excel tables without assigning semantic roles."""

    tables: list[SourceTable] = []
    for path in paths:
        if not path.is_file():
            raise CentraleRischiContractError(f"Source file not found: {path}")
        suffix = path.suffix.lower()
        if suffix == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                rows = list(reader)
            if not rows:
                raise CentraleRischiContractError(f"CSV is empty: {path}")
            tables.append(_source_table(path, "CSV", rows[0], rows[1:]))
        elif suffix in {".xlsx", ".xlsm"}:
            workbook = load_workbook(path, read_only=True, data_only=True)
            try:
                for sheet in workbook.worksheets:
                    rows = list(sheet.iter_rows(values_only=True))
                    if rows and any(value not in (None, "") for value in rows[0]):
                        tables.append(
                            _source_table(path, sheet.title, rows[0], rows[1:])
                        )
            finally:
                workbook.close()
        else:
            raise CentraleRischiContractError(
                f"Unsupported source format: {path.suffix}"
            )
    if not tables:
        raise CentraleRischiContractError("No readable source table was found.")
    return tables


def _type_name(value: Any) -> str:
    if value in (None, ""):
        return "empty"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float, Decimal)):
        return "number"
    return "text"


def build_inspection(
    tables: Sequence[SourceTable],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build a bounded inspection and a deliberately unreviewed recipe."""

    public_tables: list[dict[str, Any]] = []
    private_tables: list[dict[str, Any]] = []
    for table in tables:
        observed_types = {
            header: sorted({_type_name(row.get(header)) for row in table.rows})
            for header in table.headers
        }
        public_tables.append(
            {
                "table_id": table.table_id,
                "table_label": table.table_label,
                "row_count": len(table.rows),
                "columns": list(table.headers),
                "observed_types": observed_types,
                "preview_rows": [
                    {key: str(value)[:200] for key, value in row.items()}
                    for row in table.rows[:10]
                ],
                "source_sha256": table.source_sha256,
            }
        )
        private_tables.append(
            {
                "table_id": table.table_id,
                "absolute_path": table.source_path.as_posix(),
                "table_label": table.table_label,
                "source_sha256": table.source_sha256,
            }
        )
    inventory_hash = hashlib.sha256(_json_bytes(public_tables)).hexdigest()
    inspection = {
        "schema_version": "vera.centrale_rischi_inspection.v1",
        "workflow_id": WORKFLOW_ID,
        "inventory_sha256": inventory_hash,
        "tables": public_tables,
        "semantic_roles_assigned": False,
    }
    control = {
        "schema_version": "vera.centrale_rischi_inspection_control.v1",
        "workflow_id": WORKFLOW_ID,
        "inventory_sha256": inventory_hash,
        "tables": private_tables,
    }
    recipe = {
        "schema_version": RECIPE_SCHEMA,
        "workflow_id": WORKFLOW_ID,
        "inventory_sha256": inventory_hash,
        "entity": "",
        "currency": "EUR",
        "analysis_mode": "descriptive",
        "analysis_objective": "",
        "audience": "professional",
        "source_kind": "tabular_export",
        "source_document_sha256": "",
        "table_id": "",
        "columns": {
            "reference_month": "",
            "intermediary": "",
            "risk_category": "",
            "residual_duration": "",
            "granted": "",
            "operational_granted": "",
            "used": "",
            "guarantee_type": "",
            "guaranteed_amount": "",
            "prejudicial_event": "",
            "reporting_type": "",
            "original_duration": "",
            "relationship_status": "",
            "record_status": "",
            "valid_from": "",
            "valid_to": "",
            "source_page": "",
            "source_region": "",
            "source_row_locator": "",
            "extraction_confidence": "",
        },
        "value_mappings": {
            "original_term": {},
            "residual_term": {},
            "exposure_family": {},
        },
        "control_totals": {},
        "control_tolerance": "0.01",
        "mapping_review": {"status": "pending", "reviewer": "", "reviewed_at": ""},
    }
    return inspection, control, recipe


def _decimal(value: Any, *, field: str, row_number: int) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    normalized = str(value).strip().replace(" ", "")
    if normalized.count(",") == 1 and normalized.count(".") == 0:
        normalized = normalized.replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise CentraleRischiContractError(
            f"Invalid {field} at source row {row_number}: {value!r}"
        ) from exc


def _month(value: Any, *, row_number: int) -> str:
    text = str(value).strip()
    for fmt in ("%Y-%m", "%Y-%m-%d", "%d/%m/%Y", "%m/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m")
        except ValueError:
            continue
    raise CentraleRischiContractError(
        f"Invalid reference_month at source row {row_number}: {value!r}"
    )


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _mapped_text(
    row: Mapping[str, Any], columns: Mapping[str, str], field: str, default: str = ""
) -> str:
    """Return one optional mapped text value without guessing a source column."""

    column = columns.get(field, "")
    return _text(row.get(column, "")) if column else default


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    return (
        None
        if denominator == 0
        else (numerator / denominator * Decimal("100")).quantize(Decimal("0.01"))
    )


def _require_reviewed_recipe(
    recipe: Mapping[str, Any], tables: Sequence[SourceTable]
) -> tuple[SourceTable, Mapping[str, str]]:
    if (
        recipe.get("schema_version") != RECIPE_SCHEMA
        or recipe.get("workflow_id") != WORKFLOW_ID
    ):
        raise CentraleRischiContractError(
            "Recipe schema or workflow does not match Centrale Rischi Review."
        )
    review = recipe.get("mapping_review")
    if (
        not isinstance(review, Mapping)
        or review.get("status") != "reviewed"
        or not review.get("reviewer")
        or not review.get("reviewed_at")
    ):
        raise CentraleRischiContractError(
            "A named, timestamped mapping_review.status=reviewed is required."
        )
    inspection, _, _ = build_inspection(tables)
    if recipe.get("inventory_sha256") != inspection["inventory_sha256"]:
        raise CentraleRischiContractError(
            "Recipe inventory_sha256 does not match the supplied sources."
        )
    selected = [table for table in tables if table.table_id == recipe.get("table_id")]
    if len(selected) != 1:
        raise CentraleRischiContractError(
            "Recipe must select exactly one inspected exposure table."
        )
    columns = recipe.get("columns")
    if not isinstance(columns, Mapping):
        raise CentraleRischiContractError("Recipe columns must be an object.")
    required = (
        "reference_month",
        "intermediary",
        "risk_category",
        "original_duration",
        "residual_duration",
        "granted",
        "operational_granted",
        "used",
    )
    for field in required:
        column = columns.get(field)
        if (
            not isinstance(column, str)
            or not column
            or column not in selected[0].headers
        ):
            raise CentraleRischiContractError(
                f"Missing or invalid reviewed column mapping: {field}"
            )
    for field in (
        "guarantee_type",
        "guaranteed_amount",
        "prejudicial_event",
        "reporting_type",
        "relationship_status",
        "record_status",
        "valid_from",
        "valid_to",
        "source_page",
        "source_region",
        "source_row_locator",
        "extraction_confidence",
    ):
        column = columns.get(field, "")
        if column and column not in selected[0].headers:
            raise CentraleRischiContractError(
                f"Invalid optional column mapping: {field}"
            )
    if recipe.get("analysis_mode") not in {"descriptive", "trend", "reconciled"}:
        raise CentraleRischiContractError(
            "analysis_mode must be descriptive, trend, or reconciled."
        )
    if recipe.get("analysis_mode") == "reconciled":
        raise CentraleRischiContractError(
            "Reconciled mode requires an external-evidence adapter that is not part of this initial analysis layer."
        )
    if recipe.get("source_kind") not in {
        "tabular_export",
        "native_pdf_extraction",
        "scanned_pdf_extraction",
    }:
        raise CentraleRischiContractError("Unsupported source_kind.")
    if recipe.get("source_kind") != "tabular_export":
        if not recipe.get("source_document_sha256"):
            raise CentraleRischiContractError(
                "PDF-derived rows require source_document_sha256."
            )
        for field in (
            "record_status",
            "valid_from",
            "valid_to",
            "source_page",
            "source_region",
            "source_row_locator",
            "extraction_confidence",
        ):
            if not columns.get(field):
                raise CentraleRischiContractError(
                    f"PDF-derived rows require the provenance mapping: {field}"
                )
    return selected[0], {str(key): str(value) for key, value in columns.items()}


def _metric(
    metric_id: str,
    label: str,
    value: Decimal | int | None,
    unit: str,
    availability: str = "available",
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "label": label,
        "value": _decimal_text(value) if isinstance(value, Decimal) else value,
        "unit": unit,
        "availability": availability,
        "reason": reason,
    }


def build_analysis(
    tables: Sequence[SourceTable], recipe: Mapping[str, Any]
) -> dict[str, Any]:
    """Calculate exact CR exposure tables and source-bounded KPI metrics."""

    table, columns = _require_reviewed_recipe(recipe, tables)
    mappings = recipe.get("value_mappings")
    if not isinstance(mappings, Mapping):
        raise CentraleRischiContractError("value_mappings must be an object.")
    original_term_map = mappings.get("original_term")
    residual_term_map = mappings.get("residual_term")
    family_map = mappings.get("exposure_family")
    if (
        not isinstance(original_term_map, Mapping)
        or not isinstance(residual_term_map, Mapping)
        or not isinstance(family_map, Mapping)
    ):
        raise CentraleRischiContractError(
            "Reviewed original_term, residual_term and exposure_family mappings are required."
        )
    normalized: list[dict[str, Any]] = []
    missing_original_term: set[str] = set()
    missing_residual_term: set[str] = set()
    missing_family: set[str] = set()
    for row_number, row in enumerate(table.rows, start=2):
        original_duration_value = _text(row[columns["original_duration"]])
        residual_duration_value = _text(row[columns["residual_duration"]])
        risk_value = _text(row[columns["risk_category"]])
        original_term = original_term_map.get(original_duration_value)
        residual_term = residual_term_map.get(residual_duration_value)
        family = family_map.get(risk_value)
        if original_term not in ORIGINAL_TERM_CLASSES:
            missing_original_term.add(original_duration_value)
        if residual_term not in RESIDUAL_TERM_CLASSES:
            missing_residual_term.add(residual_duration_value)
        if family not in EXPOSURE_FAMILIES:
            missing_family.add(risk_value)
        if (
            original_term not in ORIGINAL_TERM_CLASSES
            or residual_term not in RESIDUAL_TERM_CLASSES
            or family not in EXPOSURE_FAMILIES
        ):
            continue
        record_status = _mapped_text(
            row, columns, "record_status", "current"
        ).casefold()
        if record_status not in {"current", "previous"}:
            raise CentraleRischiContractError(
                f"Invalid record_status at source row {row_number}: {record_status!r}"
            )
        operational = _decimal(
            row[columns["operational_granted"]],
            field="operational_granted",
            row_number=row_number,
        )
        used = _decimal(row[columns["used"]], field="used", row_number=row_number)
        overrun = (
            Decimal("0")
            if family == "suffering"
            else max(used - operational, Decimal("0"))
        )
        guarantee_type = (
            _text(row.get(columns.get("guarantee_type", ""), ""))
            if columns.get("guarantee_type")
            else ""
        )
        guaranteed = (
            _decimal(
                row.get(columns.get("guaranteed_amount", ""), ""),
                field="guaranteed_amount",
                row_number=row_number,
            )
            if columns.get("guaranteed_amount")
            else Decimal("0")
        )
        prejudicial = (
            _text(row.get(columns.get("prejudicial_event", ""), ""))
            if columns.get("prejudicial_event")
            else ""
        )
        normalized.append(
            {
                "source_row": row_number,
                "reference_month": _month(
                    row[columns["reference_month"]], row_number=row_number
                ),
                "intermediary": _text(row[columns["intermediary"]])
                or "Unspecified intermediary",
                "risk_category": risk_value,
                "exposure_family": family,
                "original_duration": original_duration_value,
                "original_term": original_term,
                "residual_duration": residual_duration_value,
                "residual_term": residual_term,
                "granted": _decimal(
                    row[columns["granted"]], field="granted", row_number=row_number
                ),
                "operational_granted": operational,
                "used": used,
                "available": max(operational - used, Decimal("0")),
                "overrun": overrun,
                "guarantee_type": guarantee_type,
                "guaranteed_amount": guaranteed,
                "prejudicial_event": prejudicial,
                "reporting_type": _mapped_text(row, columns, "reporting_type"),
                "relationship_status": _mapped_text(
                    row, columns, "relationship_status"
                ),
                "record_status": record_status,
                "valid_from": _mapped_text(row, columns, "valid_from"),
                "valid_to": _mapped_text(row, columns, "valid_to"),
                "source_page": _mapped_text(row, columns, "source_page"),
                "source_region": _mapped_text(row, columns, "source_region"),
                "source_row_locator": _mapped_text(row, columns, "source_row_locator"),
                "extraction_confidence": _mapped_text(
                    row, columns, "extraction_confidence"
                ),
            }
        )
    if missing_original_term or missing_residual_term or missing_family:
        details = []
        if missing_original_term:
            details.append(
                "unmapped original_duration values: "
                + ", ".join(sorted(missing_original_term))
            )
        if missing_residual_term:
            details.append(
                "unmapped residual_duration values: "
                + ", ".join(sorted(missing_residual_term))
            )
        if missing_family:
            details.append(
                "unmapped risk_category values: " + ", ".join(sorted(missing_family))
            )
        raise CentraleRischiContractError("; ".join(details))
    if not normalized:
        raise CentraleRischiContractError(
            "The selected exposure table has no data rows."
        )

    current_rows = [row for row in normalized if row["record_status"] == "current"]
    previous_rows = [row for row in normalized if row["record_status"] == "previous"]
    if not current_rows:
        raise CentraleRischiContractError(
            "The selected exposure table has no current records."
        )
    months = sorted({str(row["reference_month"]) for row in current_rows})
    latest_month = months[-1]
    latest = [row for row in current_rows if row["reference_month"] == latest_month]
    original_term_totals: dict[str, dict[str, Decimal]] = {
        value: {
            "granted": Decimal("0"),
            "operational_granted": Decimal("0"),
            "used": Decimal("0"),
            "overrun": Decimal("0"),
        }
        for value in ORIGINAL_TERM_CLASSES
    }
    residual_term_totals: dict[str, dict[str, Decimal]] = {
        value: {
            "granted": Decimal("0"),
            "operational_granted": Decimal("0"),
            "used": Decimal("0"),
            "overrun": Decimal("0"),
        }
        for value in RESIDUAL_TERM_CLASSES
    }
    monthly: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    intermediary: dict[str, Decimal] = defaultdict(Decimal)
    category_totals: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    for row in current_rows:
        month = str(row["reference_month"])
        for field in (
            "granted",
            "operational_granted",
            "used",
            "available",
            "overrun",
            "guaranteed_amount",
        ):
            monthly[month][field] += row[field]
    for row in latest:
        original_bucket = original_term_totals[str(row["original_term"])]
        residual_bucket = residual_term_totals[str(row["residual_term"])]
        for field in original_bucket:
            original_bucket[field] += row[field]
            residual_bucket[field] += row[field]
        intermediary[str(row["intermediary"])] += row["used"]
        for field in (
            "granted",
            "operational_granted",
            "used",
            "available",
            "overrun",
        ):
            category_totals[str(row["risk_category"])][field] += row[field]

    total_granted = sum((row["granted"] for row in latest), Decimal("0"))
    total_operational = sum(
        (row["operational_granted"] for row in latest), Decimal("0")
    )
    total_used = sum((row["used"] for row in latest), Decimal("0"))
    total_available = sum((row["available"] for row in latest), Decimal("0"))
    total_overrun = sum((row["overrun"] for row in latest), Decimal("0"))
    total_guaranteed = sum((row["guaranteed_amount"] for row in latest), Decimal("0"))
    top_bank = max(intermediary.values()) if intermediary else Decimal("0")
    prior_used = monthly[months[-2]]["used"] if len(months) > 1 else None
    metrics = [
        _metric(
            "cr.total_granted",
            "Accordato",
            total_granted,
            str(recipe.get("currency", "EUR")),
        ),
        _metric(
            "cr.total_operational_granted",
            "Accordato operativo",
            total_operational,
            str(recipe.get("currency", "EUR")),
        ),
        _metric(
            "cr.total_used",
            "Utilizzato",
            total_used,
            str(recipe.get("currency", "EUR")),
        ),
        _metric(
            "cr.available_resources",
            "Margine disponibile",
            total_available,
            str(recipe.get("currency", "EUR")),
        ),
        _metric(
            "cr.overrun_amount",
            "Sconfinamento",
            total_overrun,
            str(recipe.get("currency", "EUR")),
        ),
        _metric(
            "cr.overrun_count",
            "Linee con sconfinamento",
            sum(1 for row in latest if row["overrun"] > 0),
            "count",
        ),
        _metric(
            "cr.guarantee_coverage_pct",
            "Copertura importi garantiti sulle esposizioni",
            _ratio(total_guaranteed, total_used),
            "percent",
        ),
        _metric(
            "cr.top_intermediary_share_pct",
            "Quota primo intermediario",
            _ratio(top_bank, total_used),
            "percent",
        ),
        _metric(
            "cr.original_term.short_share_pct",
            "Quota breve per durata originaria",
            _ratio(original_term_totals["short"]["used"], total_used),
            "percent",
        ),
        _metric(
            "cr.original_term.medium_share_pct",
            "Quota media per durata originaria",
            _ratio(original_term_totals["medium"]["used"], total_used),
            "percent",
        ),
        _metric(
            "cr.original_term.long_share_pct",
            "Quota lunga per durata originaria",
            _ratio(original_term_totals["long"]["used"], total_used),
            "percent",
        ),
        _metric(
            "cr.previous_record_count",
            "Segnalazioni precedenti escluse dai totali correnti",
            len(previous_rows),
            "count",
        ),
        _metric(
            "cr.used_mom_change",
            "Variazione utilizzato mese su mese",
            None if prior_used is None else total_used - prior_used,
            str(recipe.get("currency", "EUR")),
            "unavailable" if prior_used is None else "available",
            "Requires at least two reference months." if prior_used is None else None,
        ),
        _metric(
            "financial.net_debt_ebitda",
            "PFN / EBITDA",
            None,
            "ratio",
            "unavailable",
            "Requires reviewed financial-statement evidence outside Centrale Rischi.",
        ),
        _metric(
            "financial.debt_equity",
            "Debt / Equity",
            None,
            "ratio",
            "unavailable",
            "Requires reviewed balance-sheet evidence outside Centrale Rischi.",
        ),
        _metric(
            "financial.dscr",
            "DSCR",
            None,
            "ratio",
            "unavailable",
            "Requires reviewed cash-flow and debt-service evidence outside Centrale Rischi.",
        ),
    ]

    category_summary: list[dict[str, Any]] = []
    for category in sorted(category_totals):
        totals = category_totals[category]
        category_id = hashlib.sha256(category.encode("utf-8")).hexdigest()[:10]
        utilization = _ratio(totals["used"], totals["operational_granted"])
        category_summary.append(
            {
                "risk_category": category,
                **{field: _decimal_text(value) for field, value in totals.items()},
                "utilization_pct": _decimal_text(utilization),
            }
        )
        category_metrics = (
            (
                "used",
                f"Utilizzato — {category}",
                totals["used"],
                str(recipe.get("currency", "EUR")),
                "available",
                None,
            ),
            (
                "available_resources",
                f"Margine disponibile — {category}",
                totals["available"],
                str(recipe.get("currency", "EUR")),
                "available",
                None,
            ),
            (
                "utilization_pct",
                f"Utilizzo su accordato operativo — {category}",
                utilization,
                "percent",
                "unavailable" if utilization is None else "available",
                (
                    "Operational granted is zero for this category."
                    if utilization is None
                    else None
                ),
            ),
        )
        for suffix, label, value, unit, availability, reason in category_metrics:
            metrics.append(
                {
                    **_metric(
                        f"cr.category.{category_id}.{suffix}",
                        label,
                        value,
                        unit,
                        availability,
                        reason,
                    ),
                    "dimension": {"risk_category": category},
                }
            )

    controls: list[dict[str, Any]] = []
    tolerance = _decimal(
        recipe.get("control_tolerance", "0.01"), field="control_tolerance", row_number=0
    )
    available_totals = {
        "granted": total_granted,
        "operational_granted": total_operational,
        "used": total_used,
    }
    declared_controls = recipe.get("control_totals") or {}
    if not isinstance(declared_controls, Mapping):
        raise CentraleRischiContractError("control_totals must be an object.")
    for name, expected_value in declared_controls.items():
        if name not in available_totals:
            raise CentraleRischiContractError(f"Unsupported control total: {name}")
        expected = _decimal(
            expected_value, field=f"control_totals.{name}", row_number=0
        )
        actual = available_totals[name]
        controls.append(
            {
                "control_id": f"control.latest.{name}",
                "expected": _decimal_text(expected),
                "actual": _decimal_text(actual),
                "difference": _decimal_text(actual - expected),
                "status": "passed" if abs(actual - expected) <= tolerance else "failed",
            }
        )
    failed_controls = [item for item in controls if item["status"] == "failed"]
    status = (
        "blocked"
        if failed_controls
        else (
            "partial"
            if any(
                row["original_term"] == "unclassified"
                or row["residual_term"] == "unclassified"
                for row in latest
            )
            or (recipe.get("analysis_mode") == "trend" and len(months) < 2)
            else "complete"
        )
    )

    def public_row(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: _decimal_text(value) if isinstance(value, Decimal) else value
            for key, value in row.items()
        }

    exposures = [public_row(row) for row in normalized]
    original_term_summary = [
        {
            "original_term": key,
            **{field: _decimal_text(value) for field, value in totals.items()},
        }
        for key, totals in original_term_totals.items()
    ]
    residual_term_summary = [
        {
            "residual_term": key,
            **{field: _decimal_text(value) for field, value in totals.items()},
        }
        for key, totals in residual_term_totals.items()
    ]
    monthly_series = [
        {
            "reference_month": month,
            **{field: _decimal_text(value) for field, value in monthly[month].items()},
        }
        for month in months
    ]
    guarantees = [public_row(row) for row in latest if row["guaranteed_amount"] > 0]
    overruns = [public_row(row) for row in latest if row["overrun"] > 0]
    prejudicial = [public_row(row) for row in latest if row["prejudicial_event"]]
    limitations = [
        "L'utilizzo è calcolato per categoria di rischio confermata; non viene presentato un unico rapporto trasversale perché gli importi utilizzati hanno significati specifici per categoria.",
        "Breve, medio e lungo derivano dai valori confermati della durata originaria. La durata residua è esposta separatamente come entro un anno, oltre un anno, non rilevante o non classificata e non consente di distinguere medio da lungo termine.",
        "L'Importo garantito su un'esposizione del cliente non coincide con la tabella Garanzie ricevute per obbligazioni di terzi. L'analisi delle esposizioni non unisce le due popolazioni.",
        "La Centrale Rischi da sola non consente di calcolare PFN/EBITDA, Debt/Equity o DSCR.",
        "L'output non riproduce né stima il rating proprietario di una banca.",
    ]
    if not columns.get("prejudicial_event"):
        limitations.append(
            "Le evidenze pregiudizievoli non sono disponibili perché non è stata fornita una colonna proveniente da una fonte separata e confermata."
        )
    return {
        "schema_version": ANALYSIS_SCHEMA,
        "workflow_id": WORKFLOW_ID,
        "status": status,
        "review_status": "draft_pending_professional_review",
        "entity": str(recipe.get("entity", "")),
        "currency": str(recipe.get("currency", "EUR")),
        "analysis_mode": str(recipe.get("analysis_mode")),
        "analysis_objective": str(recipe.get("analysis_objective", "")),
        "audience": str(recipe.get("audience", "professional")),
        "latest_reference_month": latest_month,
        "source": {
            "table_id": table.table_id,
            "source_sha256": table.source_sha256,
            "source_kind": str(recipe.get("source_kind")),
            "source_document_sha256": str(recipe.get("source_document_sha256", "")),
            "inventory_sha256": recipe["inventory_sha256"],
            "row_count": len(normalized),
            "current_row_count": len(current_rows),
            "previous_row_count": len(previous_rows),
        },
        "metrics": metrics,
        "exposures": exposures,
        "original_term_summary": original_term_summary,
        "residual_term_summary": residual_term_summary,
        "risk_category_summary": category_summary,
        "monthly_series": monthly_series,
        "guarantees": guarantees,
        "overruns": overruns,
        "prejudicial_events": prejudicial,
        "coverage": {
            "pregiudizievoli": (
                "available" if columns.get("prejudicial_event") else "unavailable"
            ),
            "multiple_months": "available" if len(months) > 1 else "unavailable",
            "trend_analysis": "available" if len(months) > 1 else "unavailable",
            "previous_records": "available" if previous_rows else "unavailable",
            "reconciled_analysis": "unavailable",
            "financial_statement_ratios": "unavailable",
        },
        "controls": controls,
        "assurance_levels": {
            "documentary": (
                "pdf_rows_with_reviewed_layout_provenance"
                if recipe.get("source_kind") != "tabular_export"
                else "reviewed_tabular_mapping_not_original_report_validation"
            ),
            "arithmetic": "failed" if failed_controls else "passed",
            "semantic": "reviewed_recipe",
            "professional": "pending",
        },
        "limitations": limitations,
    }


def build_model_context(analysis: Mapping[str, Any]) -> dict[str, Any]:
    """Project bounded calculated evidence for model-led interpretation."""

    return {
        "schema_version": "vera.centrale_rischi_model_context.v1",
        "workflow_id": WORKFLOW_ID,
        "status": analysis["status"],
        "entity": analysis["entity"],
        "currency": analysis["currency"],
        "latest_reference_month": analysis["latest_reference_month"],
        "metrics": analysis["metrics"],
        "original_term_summary": analysis["original_term_summary"],
        "residual_term_summary": analysis["residual_term_summary"],
        "risk_category_summary": analysis["risk_category_summary"],
        "monthly_series": analysis["monthly_series"][-36:],
        "top_overruns": sorted(
            analysis["overruns"],
            key=lambda row: Decimal(str(row["overrun"])),
            reverse=True,
        )[:20],
        "top_guarantees": sorted(
            analysis["guarantees"],
            key=lambda row: Decimal(str(row["guaranteed_amount"])),
            reverse=True,
        )[:20],
        "prejudicial_events": analysis["prejudicial_events"][:20],
        "coverage": analysis["coverage"],
        "controls": analysis["controls"],
        "assurance_levels": analysis["assurance_levels"],
        "limitations": analysis["limitations"],
        "excluded_by_default": [
            "raw source population",
            "absolute paths",
            "original filenames",
        ],
    }


def finalize_commentary(
    analysis: Mapping[str, Any], commentary: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate commentary shape and metric-reference closure."""

    if (
        analysis.get("schema_version") != ANALYSIS_SCHEMA
        or analysis.get("workflow_id") != WORKFLOW_ID
    ):
        raise CentraleRischiContractError(
            "Analysis contract does not match this workflow."
        )
    if analysis.get("status") == "blocked" or any(
        item.get("status") == "failed" for item in analysis.get("controls", [])
    ):
        raise CentraleRischiContractError("Blocked analysis cannot be finalized.")
    if (
        commentary.get("schema_version") != COMMENTARY_SCHEMA
        or commentary.get("workflow_id") != WORKFLOW_ID
    ):
        raise CentraleRischiContractError("Commentary schema or workflow is invalid.")
    metric_ids = {str(item["metric_id"]) for item in analysis.get("metrics", [])}
    normalized: dict[str, Any] = {
        "schema_version": COMMENTARY_SCHEMA,
        "workflow_id": WORKFLOW_ID,
    }
    for section in ("observations", "hypotheses"):
        items = commentary.get(section, [])
        if not isinstance(items, list):
            raise CentraleRischiContractError(f"Commentary {section} must be a list.")
        normalized_items = []
        for item in items:
            if not isinstance(item, Mapping) or not _text(item.get("text")):
                raise CentraleRischiContractError(f"Each {section} item requires text.")
            references = item.get("metric_ids")
            if (
                not isinstance(references, list)
                or not references
                or not set(map(str, references)) <= metric_ids
            ):
                raise CentraleRischiContractError(
                    f"Each {section} item requires only existing metric_ids."
                )
            normalized_items.append(
                {
                    "text": _text(item["text"]),
                    "metric_ids": [str(value) for value in references],
                }
            )
        normalized[section] = normalized_items
    for section in ("questions", "limitations"):
        items = commentary.get(section, [])
        if not isinstance(items, list) or any(
            not isinstance(item, str) or not item.strip() for item in items
        ):
            raise CentraleRischiContractError(
                f"Commentary {section} must contain non-empty strings."
            )
        normalized[section] = [item.strip() for item in items]
    normalized["status"] = "draft_pending_professional_review"
    return normalized


def _metric_rows(analysis: Mapping[str, Any]) -> str:
    return "".join(
        f"<tr><td>{html.escape(str(item['label']))}</td><td>{html.escape(str(item['value'] if item['value'] is not None else 'Non disponibile'))}</td><td>{html.escape(str(item['unit']))}</td><td>{html.escape(str(item['availability']))}</td></tr>"
        for item in analysis["metrics"]
    )


def _term_label(value: str) -> str:
    return {
        "short": "breve",
        "medium": "medio",
        "long": "lungo",
        "within_one_year": "entro un anno",
        "over_one_year": "oltre un anno",
        "not_relevant": "non rilevante",
        "unclassified": "non classificato",
    }.get(value, value)


def render_markdown(
    analysis: Mapping[str, Any], commentary: Mapping[str, Any] | None = None
) -> str:
    """Render calculated facts and optional reviewed-draft commentary."""

    lines = [
        f"# Centrale Rischi — {analysis['entity']}",
        "",
        f"Periodo più recente: {analysis['latest_reference_month']}",
        "",
        f"Stato: `{analysis['review_status']}`",
        "",
        "## KPI",
        "",
        "| Metrica | Valore | Unità | Disponibilità |",
        "| --- | ---: | --- | --- |",
    ]
    for item in analysis["metrics"]:
        lines.append(
            f"| {item['label']} | {item['value'] if item['value'] is not None else 'Non disponibile'} | {item['unit']} | {item['availability']} |"
        )
    lines.extend(
        [
            "",
            "## Esposizioni per durata originaria",
            "",
            "| Scadenza | Accordato | Operativo | Utilizzato | Sconfinamento |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in analysis["original_term_summary"]:
        lines.append(
            f"| {_term_label(str(item['original_term']))} | {item['granted']} | {item['operational_granted']} | {item['used']} | {item['overrun']} |"
        )
    lines.extend(
        [
            "",
            "## Esposizioni per durata residua",
            "",
            "| Durata residua | Accordato | Operativo | Utilizzato | Sconfinamento |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in analysis["residual_term_summary"]:
        lines.append(
            f"| {_term_label(str(item['residual_term']))} | {item['granted']} | {item['operational_granted']} | {item['used']} | {item['overrun']} |"
        )
    lines.extend(
        [
            "",
            "## Indicatori per categoria di rischio",
            "",
            "| Categoria | Accordato operativo | Utilizzato | Margine | Utilizzo % |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in analysis["risk_category_summary"]:
        lines.append(
            f"| {item['risk_category']} | {item['operational_granted']} | {item['used']} | {item['available']} | {item['utilization_pct'] if item['utilization_pct'] is not None else 'Non disponibile'} |"
        )
    lines.extend(
        [
            "",
            f"Garanzie: {len(analysis['guarantees'])}",
            f"Sconfinamenti: {len(analysis['overruns'])}",
            f"Pregiudizievoli: {len(analysis['prejudicial_events'])}",
            "",
            "## Limiti",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in analysis["limitations"])
    if commentary:
        lines.extend(
            ["", "## Commento — bozza in attesa di revisione professionale", ""]
        )
        for heading, key in (
            ("Osservazioni", "observations"),
            ("Ipotesi", "hypotheses"),
        ):
            lines.extend([f"### {heading}", ""])
            lines.extend(
                f"- {item['text']} ({', '.join(item['metric_ids'])})"
                for item in commentary[key]
            )
        for heading, key in (
            ("Domande", "questions"),
            ("Limiti aggiuntivi", "limitations"),
        ):
            lines.extend(["", f"### {heading}", ""])
            lines.extend(f"- {item}" for item in commentary[key])
    return "\n".join(lines).rstrip() + "\n"


def render_html(
    analysis: Mapping[str, Any], commentary: Mapping[str, Any] | None = None
) -> str:
    """Render a self-contained, read-only review dashboard."""

    commentary_html = ""
    if commentary:
        blocks = []
        for title, key in (("Osservazioni", "observations"), ("Ipotesi", "hypotheses")):
            items = "".join(
                f"<li>{html.escape(item['text'])} <code>{html.escape(', '.join(item['metric_ids']))}</code></li>"
                for item in commentary[key]
            )
            blocks.append(
                f"<h3>{title}</h3><ul>{items or '<li>Nessuna voce.</li>'}</ul>"
            )
        commentary_html = (
            "<section><h2>Commento professionale — bozza</h2>"
            + "".join(blocks)
            + "</section>"
        )
    original_term_rows = "".join(
        f"<tr><td>{html.escape(_term_label(str(item['original_term'])))}</td><td>{item['granted']}</td><td>{item['operational_granted']}</td><td>{item['used']}</td><td>{item['overrun']}</td></tr>"
        for item in analysis["original_term_summary"]
    )
    residual_term_rows = "".join(
        f"<tr><td>{html.escape(_term_label(str(item['residual_term'])))}</td><td>{item['granted']}</td><td>{item['operational_granted']}</td><td>{item['used']}</td><td>{item['overrun']}</td></tr>"
        for item in analysis["residual_term_summary"]
    )
    category_rows = "".join(
        f"<tr><td>{html.escape(item['risk_category'])}</td><td>{item['operational_granted']}</td><td>{item['used']}</td><td>{item['available']}</td><td>{item['utilization_pct'] if item['utilization_pct'] is not None else 'Non disponibile'}</td></tr>"
        for item in analysis["risk_category_summary"]
    )
    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Centrale Rischi — {html.escape(str(analysis['entity']))}</title><style>body{{font-family:'Instrument Sans',Arial,sans-serif;margin:0;color:#171816;background:#fff}}main{{max-width:1120px;margin:auto;padding:48px 24px}}header{{border-top:5px solid #002060;border-bottom:1px solid #c9ccd1;padding-bottom:24px}}.eyebrow{{color:#006b8f;font-weight:700;text-transform:uppercase;letter-spacing:.08em}}h1{{font-size:clamp(2.2rem,5vw,4.5rem);line-height:.98;margin:.4rem 0}}section{{margin-top:42px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px 8px;border-bottom:1px solid #d9dadd;text-align:left}}th{{color:#002060}}.status{{display:inline-block;border:1px solid #002060;padding:6px 10px}}code{{font-size:.8em;color:#006b8f}}@media(max-width:700px){{main{{padding:28px 16px}}table{{font-size:.82rem}}}}</style></head><body><main><header><p class="eyebrow">Vera · Centrale Rischi</p><h1>{html.escape(str(analysis['entity']))}</h1><p>Periodo più recente: {analysis['latest_reference_month']} · <span class="status">{analysis['review_status']}</span></p></header><section><h2>KPI</h2><table><thead><tr><th>Metrica</th><th>Valore</th><th>Unità</th><th>Copertura</th></tr></thead><tbody>{_metric_rows(analysis)}</tbody></table></section><section><h2>Esposizioni per durata originaria</h2><table><thead><tr><th>Classe</th><th>Accordato</th><th>Operativo</th><th>Utilizzato</th><th>Sconfinamento</th></tr></thead><tbody>{original_term_rows}</tbody></table></section><section><h2>Esposizioni per durata residua</h2><table><thead><tr><th>Classe</th><th>Accordato</th><th>Operativo</th><th>Utilizzato</th><th>Sconfinamento</th></tr></thead><tbody>{residual_term_rows}</tbody></table></section><section><h2>Indicatori per categoria</h2><table><thead><tr><th>Categoria</th><th>Operativo</th><th>Utilizzato</th><th>Margine</th><th>Utilizzo %</th></tr></thead><tbody>{category_rows}</tbody></table></section><section><h2>Eccezioni</h2><p>Garanzie sulle esposizioni: {len(analysis['guarantees'])} · Sconfinamenti: {len(analysis['overruns'])} · Pregiudizievoli: {len(analysis['prejudicial_events'])}</p></section>{commentary_html}<section><h2>Limiti</h2><ul>{''.join(f'<li>{html.escape(item)}</li>' for item in analysis['limitations'])}</ul></section></main></body></html>"""


def write_excel(path: Path, analysis: Mapping[str, Any]) -> None:
    """Write a reviewable workbook from the exact analysis payload."""

    workbook = Workbook()
    summary = workbook.active
    summary.title = "KPI"
    summary.append(
        ("Metric ID", "Metrica", "Valore", "Unità", "Disponibilità", "Motivo")
    )
    for item in analysis["metrics"]:
        summary.append(
            (
                item["metric_id"],
                item["label"],
                item["value"],
                item["unit"],
                item["availability"],
                item["reason"] or "",
            )
        )
    sections = {
        "Durata originaria": analysis["original_term_summary"],
        "Durata residua": analysis["residual_term_summary"],
        "Categorie": analysis["risk_category_summary"],
        "Esposizioni": analysis["exposures"],
        "Garanzie": analysis["guarantees"],
        "Sconfinamenti": analysis["overruns"],
        "Pregiudizievoli": analysis["prejudicial_events"],
        "Serie mensile": analysis["monthly_series"],
        "Controlli": analysis["controls"],
    }
    for title, rows in sections.items():
        sheet = workbook.create_sheet(title)
        if rows:
            headers = list(rows[0])
            sheet.append(headers)
            for row in rows:
                sheet.append([row.get(header) for header in headers])
        else:
            sheet.append(("Stato", "Nessun dato disponibile"))
    for sheet in workbook.worksheets:
        sheet.freeze_panes = "A2"
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="002060")
        for column_cells in sheet.columns:
            width = min(
                42,
                max(12, max(len(str(cell.value or "")) for cell in column_cells) + 2),
            )
            sheet.column_dimensions[column_cells[0].column_letter].width = width
    workbook.save(path)
