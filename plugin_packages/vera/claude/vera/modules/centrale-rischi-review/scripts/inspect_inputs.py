#!/usr/bin/env python3
"""Inventory Centrale Rischi exports without assigning semantic roles."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))
for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        sys.path.insert(0, str(_vendor_root))
        break

from centrale_rischi_core import (  # noqa: E402
    CentraleRischiContractError,
    build_inspection,
    load_source_tables,
    sha256_file,
    write_json,
)
from centrale_rischi_pdf import (  # noqa: E402
    normalize_pdf,
    write_normalized_workbook,
)
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

__all__ = ["main"]
LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Write bounded inspection, private control, and recipe skeleton."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="centrale-rischi-review",
            input_paths=args.input,
            output_dir=args.output_dir,
        )
        pdf_inputs = [path for path in args.input if path.suffix.casefold() == ".pdf"]
        if pdf_inputs and len(args.input) != 1:
            raise CentraleRischiContractError(
                "PDF intake accepts exactly one source document per inspection run."
            )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        if pdf_inputs:
            normalization = normalize_pdf(pdf_inputs[0])
            normalized_path = args.output_dir / "centrale_rischi_normalized.xlsx"
            write_normalized_workbook(normalized_path, normalization)
            write_json(args.output_dir / "pdf_normalization.json", normalization)
            source_tables = load_source_tables([normalized_path])
        else:
            normalization = None
            normalized_path = None
            source_tables = load_source_tables(args.input)
        inspection, control, recipe = build_inspection(source_tables)
        if normalization is not None:
            recipe["source_kind"] = "native_pdf_extraction"
            recipe["source_document_sha256"] = normalization["source"][
                "source_document_sha256"
            ]
    except (
        AssuranceContractError,
        CentraleRischiContractError,
        OSError,
        ValueError,
    ) as exc:
        parser.error(str(exc))
    write_json(args.output_dir / "inspection.json", inspection)
    write_json(args.output_dir / "inspection_control.json", control)
    write_json(args.output_dir / "suggested_recipe.json", recipe)
    if normalized_path is not None:
        write_json(
            args.output_dir / "pdf_normalization_receipt.json",
            {
                "schema_version": "vera.centrale_rischi_pdf_normalization_receipt.v1",
                "workflow_id": "centrale-rischi-review",
                "status": "pending_professional_review",
                "source_document_sha256": normalization["source"][
                    "source_document_sha256"
                ],
                "normalized_workbook_sha256": sha256_file(normalized_path),
                "normalized_row_counts": {
                    key: len(rows) for key, rows in normalization["tables"].items()
                },
                "issue_count": len(normalization["issues"]),
                "unclassified_table_count": len(normalization["unclassified_tables"]),
            },
        )
    LOGGER.info("Inspected Centrale Rischi sources; semantic mappings remain pending.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
