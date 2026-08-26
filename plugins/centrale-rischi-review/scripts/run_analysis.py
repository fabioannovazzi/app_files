#!/usr/bin/env python3
"""Calculate and render one reviewed Centrale Rischi analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
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
    COMMENTARY_SCHEMA,
    CentraleRischiContractError,
    build_analysis,
    build_model_context,
    load_json,
    load_source_tables,
    render_html,
    render_markdown,
    sha256_file,
    write_excel,
    write_json,
)
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

__all__ = ["main"]
LOGGER = logging.getLogger(__name__)


def _resolve_calculation_inputs(
    source_paths: list[Path], recipe_path: Path
) -> tuple[list[Path], list[Path]]:
    """Resolve and verify the inspected workbook for one native PDF source."""

    pdf_paths = [path for path in source_paths if path.suffix.casefold() == ".pdf"]
    if not pdf_paths:
        return source_paths, []
    if len(source_paths) != 1:
        raise CentraleRischiContractError(
            "PDF analysis accepts exactly one source document per run."
        )
    normalized_path = recipe_path.parent / "centrale_rischi_normalized.xlsx"
    normalization_receipt_path = recipe_path.parent / "pdf_normalization_receipt.json"
    recipe = load_json(recipe_path)
    receipt = load_json(normalization_receipt_path)
    source_sha256 = sha256_file(pdf_paths[0])
    if recipe.get("source_kind") != "native_pdf_extraction":
        raise CentraleRischiContractError(
            "A PDF source requires a reviewed native_pdf_extraction recipe."
        )
    if (
        recipe.get("source_document_sha256") != source_sha256
        or receipt.get("source_document_sha256") != source_sha256
    ):
        raise CentraleRischiContractError(
            "The PDF no longer matches the reviewed normalization receipt."
        )
    if (
        receipt.get("schema_version")
        != "vera.centrale_rischi_pdf_normalization_receipt.v1"
        or receipt.get("workflow_id") != "centrale-rischi-review"
        or receipt.get("normalized_workbook_sha256") != sha256_file(normalized_path)
    ):
        raise CentraleRischiContractError(
            "The normalized PDF workbook does not match its inspection receipt."
        )
    return [normalized_path], [normalized_path, normalization_receipt_path]


def main(argv: list[str] | None = None) -> int:
    """Run exact calculations and write the normal review outputs."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="centrale-rischi-review",
            input_paths=[*args.input, args.recipe],
            output_dir=args.output_dir,
        )
        calculation_inputs, derived_inputs = _resolve_calculation_inputs(
            args.input, args.recipe
        )
        if derived_inputs:
            load_client_engagement_context_file(
                args.client_engagement,
                expected_workflow_id="centrale-rischi-review",
                input_paths=derived_inputs,
                output_dir=args.output_dir,
            )
        analysis = build_analysis(
            load_source_tables(calculation_inputs), load_json(args.recipe)
        )
    except (
        AssuranceContractError,
        CentraleRischiContractError,
        OSError,
        ValueError,
    ) as exc:
        parser.error(str(exc))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    analysis_path = args.output_dir / "centrale_rischi_analysis.json"
    write_json(analysis_path, analysis)
    write_json(args.output_dir / "model_context.json", build_model_context(analysis))
    (args.output_dir / "centrale_rischi_facts.md").write_text(
        render_markdown(analysis), encoding="utf-8"
    )
    (args.output_dir / "centrale_rischi_dashboard.html").write_text(
        render_html(analysis), encoding="utf-8"
    )
    write_excel(args.output_dir / "centrale_rischi_analysis.xlsx", analysis)
    analysis_sha256 = sha256_file(analysis_path)
    write_json(
        args.output_dir / "commentary_template.json",
        {
            "schema_version": COMMENTARY_SCHEMA,
            "workflow_id": "centrale-rischi-review",
            "analysis_sha256": analysis_sha256,
            "evidence_ref_contract": {
                "metric": "metric:<existing metric_id>",
                "control": "control:<existing control_id>",
                "source_row": "row:<existing source_row_locator>",
            },
            "observations": [],
            "hypotheses": [],
            "questions": [],
            "limitations": [],
        },
    )
    write_json(
        args.output_dir / "open_issues_template.json",
        {
            "schema_version": "vera.centrale_rischi_open_issues.v1",
            "workflow_id": "centrale-rischi-review",
            "analysis_sha256": analysis_sha256,
            "status": "open",
            "items": [],
            "allowed_kinds": [
                "documentary",
                "arithmetic",
                "semantic",
                "professional",
            ],
        },
    )
    output_names = (
        "centrale_rischi_analysis.json",
        "model_context.json",
        "centrale_rischi_facts.md",
        "centrale_rischi_dashboard.html",
        "centrale_rischi_analysis.xlsx",
        "commentary_template.json",
        "open_issues_template.json",
    )
    receipt = {
        "schema_version": "vera.centrale_rischi_execution_receipt.v1",
        "workflow_id": "centrale-rischi-review",
        "status": analysis["status"],
        "recipe_sha256": sha256_file(args.recipe),
        "inputs": [
            {
                "input_id": f"input_{index:03d}",
                "sha256": sha256_file(path),
                "byte_count": path.stat().st_size,
            }
            for index, path in enumerate(args.input, start=1)
        ],
        "outputs": [
            {
                "path": name,
                "sha256": sha256_file(args.output_dir / name),
                "byte_count": (args.output_dir / name).stat().st_size,
            }
            for name in output_names
        ],
        "implementation_reason": "Arithmetic, reviewed-value mapping, schema validation and content hashes are deterministic because they are mechanically verifiable; interpretation and materiality remain model-led and professional.",
    }
    receipt["content_sha256"] = hashlib.sha256(
        (
            json.dumps(
                receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    write_json(args.output_dir / "execution_receipt.json", receipt)
    LOGGER.info("Wrote Centrale Rischi analysis with status %s.", analysis["status"])
    return 0 if analysis["status"] != "blocked" else 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
