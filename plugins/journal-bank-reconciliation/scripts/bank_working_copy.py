"""Reproduce explicitly reviewed bank-sheet preparation with original-row lineage."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import fastexcel

__all__ = ["prepare_reviewed_bank_copies"]


def _date(value: Any, convention: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (datetime(1899, 12, 30) + timedelta(days=value)).date()
    formats = ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S"]
    formats += (
        ["%d/%m/%Y", "%d/%m/%y"]
        if convention == "day_first"
        else ["%m/%d/%Y", "%m/%d/%y"]
    )
    for pattern in formats:
        try:
            return datetime.strptime(str(value).strip(), pattern).date()
        except ValueError:
            continue
    raise ValueError("A retained bank row has no reviewed, parseable date")


def prepare_reviewed_bank_copies(
    decisions: Mapping[str, Any],
    output_dir: Path,
    *,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    """Exclude only exact reviewed rows; never infer that an undated amount is safe.

    Explicit physical row decisions and source SHA-256 prevent silent omission
    of economic movements. Every excluded cell and every source-row link stays
    in the preparation evidence. This is source preparation, not reconciliation.
    """
    if set(decisions) != {"reviewer_ref", "reviewed_on", "files"}:
        raise ValueError("Bank preparation needs explicit reviewer, date and files")
    date.fromisoformat(decisions["reviewed_on"])
    if not decisions["reviewer_ref"] or not isinstance(decisions["files"], list):
        raise ValueError("Invalid bank preparation review")
    admitted = {Path(item["path"]): item for item in context["input_bindings"]}
    bank_dir = output_dir / "bank-prepared"
    bank_dir.mkdir(parents=True, exist_ok=True)
    if bank_dir.is_symlink():
        raise ValueError("Bank working directory must be ordinary")
    evidence = []
    names: set[str] = set()
    for choice in decisions["files"]:
        if set(choice) != {
            "source_path",
            "source_sha256",
            "sheet",
            "date_column",
            "description_column",
            "amount_column",
            "date_convention",
            "excluded_rows",
        }:
            raise ValueError("Incomplete physical bank preparation decision")
        path = Path(choice["source_path"])
        if (
            path not in admitted
            or path.is_symlink()
            or not path.is_file()
            or path.stat().st_nlink != 1
        ):
            raise ValueError("Bank preparation source is not a bound ordinary input")
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        if before != choice["source_sha256"] or before != admitted[path]["sha256"]:
            raise ValueError("Bank preparation source bytes changed")
        if choice["date_convention"] not in {"day_first", "month_first"}:
            raise ValueError("Bank dates need an explicit convention")
        excluded = choice["excluded_rows"]
        if (
            not isinstance(excluded, list)
            or len(set(excluded)) != len(excluded)
            or any(type(i) is not int or i < 1 for i in excluded)
        ):
            raise ValueError("Excluded bank rows must be unique positive physical rows")
        columns = [
            choice[k] for k in ("date_column", "description_column", "amount_column")
        ]
        if any(type(i) is not int or i < 0 for i in columns) or len(set(columns)) != 3:
            raise ValueError("Bank column roles must be explicit and distinct")
        frame = (
            fastexcel.read_excel(path)
            .load_sheet(choice["sheet"], header_row=None)
            .to_polars()
        )
        movements = []
        excluded_evidence = []
        links = []
        observed_rows: set[int] = set()
        for row_number, row in enumerate(frame.iter_rows(), 1):
            observed_rows.add(row_number)
            if row_number in excluded:
                excluded_evidence.append(
                    {
                        "excel_row": row_number,
                        "cells": [str(v) if v is not None else None for v in row],
                    }
                )
                continue
            if max(columns) >= len(row):
                raise ValueError("Reviewed bank columns exceed the physical sheet")
            value = Decimal(str(row[choice["amount_column"]]))
            if not value.is_finite() or value != value.quantize(Decimal("0.01")):
                raise ValueError("A bank amount needs explicit precision review")
            movements.append(
                [
                    _date(
                        row[choice["date_column"]], choice["date_convention"]
                    ).isoformat(),
                    str(row[choice["description_column"]] or ""),
                    format(value, ".2f"),
                ]
            )
            links.append(
                {"csv_row": len(movements) + 1, "source_excel_row": row_number}
            )
        if set(excluded) - observed_rows:
            raise ValueError("Excluded bank row does not exist")
        target = bank_dir / (path.stem + ".csv")
        if target.name in names:
            raise ValueError("Bank preparation would overwrite an existing source")
        names.add(target.name)
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(["date", "description", "amount"])
        writer.writerows(movements)
        candidate = buffer.getvalue().encode()
        if target.is_symlink() or (
            target.exists() and target.read_bytes() != candidate
        ):
            raise ValueError("Existing bank preparation has different bytes")
        target.write_bytes(candidate)
        if hashlib.sha256(path.read_bytes()).hexdigest() != before:
            raise ValueError("Bank preparation source changed during reading")
        evidence.append(
            {
                "source": path.name,
                "source_sha256": before,
                "source_path": str(path),
                "working_copy": str(target),
                "working_copy_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "movement_count": len(movements),
                "net_amount": str(
                    sum((Decimal(row[2]) for row in movements), Decimal(0))
                ),
                "excluded_rows": excluded_evidence,
                "row_links": links,
                "reviewer_ref": decisions["reviewer_ref"],
                "reviewed_on": decisions["reviewed_on"],
            }
        )
    evidence_path = output_dir / "bank-preparation-evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    decision_bytes = (
        json.dumps(decisions, indent=2, ensure_ascii=False) + "\n"
    ).encode()
    (
        output_dir
        / f"bank_preparation_decisions.{hashlib.sha256(decision_bytes).hexdigest()}.json"
    ).write_bytes(decision_bytes)
    return {
        "bank_dir": bank_dir,
        "evidence": evidence_path,
        "movement_count": sum(e["movement_count"] for e in evidence),
    }
