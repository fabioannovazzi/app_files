"""Invoke unchanged Centrale Rischi producers in an isolated interpreter."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

__all__ = ["main"]


def source_page(request: dict) -> dict:
    """Page unchanged public parsed rows and exact mapping keys, never classify them."""
    from centrale_rischi_core import _text, build_inspection, load_source_tables
    from run_analysis import _resolve_calculation_inputs

    inputs, _ = _resolve_calculation_inputs(
        [Path(p) for p in request["inputs"]], Path(request["recipe"])
    )
    tables = load_source_tables(inputs)
    inspection, _, _ = build_inspection(tables)
    if inspection["inventory_sha256"] != request["inventory_sha256"]:
        raise ValueError("CR source inventory changed")
    selector = request["selector"]
    offset = selector["offset"]
    if not selector["table_id"]:
        entries = [
            {k: row[k] for k in ("table_id", "table_label", "row_count", "columns")}
            for row in inspection["tables"]
        ]
        return {
            "kind": "tables",
            "entries": entries[offset : offset + 30],
            "offset": offset,
            "total": len(entries),
            "has_more": offset + 30 < len(entries),
        }
    table = next((t for t in tables if t.table_id == selector["table_id"]), None)
    if table is None:
        raise ValueError("Choose an exact inspected CR table")
    column = selector["column"]
    if column and column not in table.headers:
        raise ValueError("Choose an exact inspected CR column")
    if selector["kind"] == "values":
        if not column:
            raise ValueError("Observed values require an explicit column")
        observed: dict[str, dict] = {}
        for number, row in enumerate(table.rows, start=2):
            # This is the public calculator's mapping-key normalizer, not semantics.
            key = _text(row.get(column, ""))
            if key not in observed:
                observed[key] = {"value": key, "count": 0, "first_source_row": number}
            observed[key]["count"] += 1
        entries = list(observed.values())
    else:
        columns = (column,) if column else table.headers
        entries = [
            {
                "source_row": number,
                "values": {key: row[key] for key in columns if key in row},
            }
            for number, row in enumerate(
                table.rows[offset : offset + 30], start=offset + 2
            )
        ]
    total = len(observed) if selector["kind"] == "values" else len(table.rows)
    return {
        "kind": selector["kind"],
        "table_id": table.table_id,
        "table_label": table.table_label,
        "source_sha256": table.source_sha256,
        "columns": list(table.headers),
        "column": column,
        "row_count": len(table.rows),
        "missing_cell_count": (
            sum(column not in row for row in table.rows) if column else None
        ),
        "entries": (
            entries[offset : offset + 30] if selector["kind"] == "values" else entries
        ),
        "offset": offset,
        "total": total,
        "has_more": offset + 30 < total,
        "row_locator_contract": "public parsed table row number, header=1; empty physical rows omitted by public loader; PDF source_page/source_region/source_row_locator cells retained separately",
        "value_key_contract": "public calculator _text: string conversion and outer whitespace stripping; blank/None become empty string; no meaning or class inferred",
    }


def main() -> None:
    """Keep the public PDF, arithmetic and evidence-reference contracts authoritative."""
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root / "scripts"))
    request = json.loads(sys.stdin.read(128001))
    operation = request["operation"]
    if operation == "implementation":
        result = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root / "scripts").glob("*.py"))
        }
    elif operation in {"inspect", "calculate", "finalize"}:
        arguments = [
            "--client-engagement",
            request["context"],
            "--output-dir",
            request["output"],
        ]
        if operation == "finalize":
            from finalize_analysis import main as producer

            arguments += [
                "--analysis",
                request["analysis"],
                "--commentary",
                request["commentary"],
            ]
        else:
            for path in request["inputs"]:
                arguments += ["--input", path]
            if operation == "inspect":
                from inspect_inputs import main as producer
            else:
                from run_analysis import main as producer

                arguments += ["--recipe", request["recipe"]]
        status = producer(arguments)
        if status not in {0, 2}:
            raise ValueError("Unexpected Centrale Rischi producer outcome")
        result = {"exit_status": status}
    elif operation == "source_page":
        result = source_page(request)
    elif operation == "recipe_contract":
        from centrale_rischi_core import (
            EXPOSURE_FAMILIES,
            ORIGINAL_TERM_CLASSES,
            RESIDUAL_TERM_CLASSES,
        )

        result = {
            "original_term": ORIGINAL_TERM_CLASSES,
            "residual_term": RESIDUAL_TERM_CLASSES,
            "exposure_family": EXPOSURE_FAMILIES,
        }
    elif operation == "validate_commentary":
        from centrale_rischi_core import finalize_commentary

        result = finalize_commentary(
            json.loads(Path(request["analysis"]).read_bytes()), request["proposal"]
        )
    elif operation == "validate_recipe":
        from centrale_rischi_core import build_analysis, load_source_tables
        from run_analysis import _resolve_calculation_inputs

        inputs, _ = _resolve_calculation_inputs(
            [Path(p) for p in request["inputs"]],
            Path(request["recipe"]),
        )
        result = {
            "status": build_analysis(load_source_tables(inputs), request["proposal"])[
                "status"
            ]
        }
    else:
        raise ValueError("Unknown Centrale Rischi operation")
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
