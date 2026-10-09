"""Isolated calls to maintained bank inspection and reviewed-receipt builders."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["main"]


def project(result: Any, output: Path, core: Any) -> dict[str, Any]:
    """Retain producer metadata/20-row previews, never its full row dispositions."""
    files = []
    for side in ("bank", "journal"):
        for record in getattr(result, side)["files"]:
            files.append(
                {
                    "side": side,
                    **{
                        key: record[key]
                        for key in (
                            "source_file",
                            "qualification_status",
                            "failure_kind",
                            "header_rows",
                            "raw_columns",
                            "mapping",
                            "row_count",
                            "preview",
                            "potential_monetary_columns",
                            "excluded_monetary_columns",
                            "unresolved_monetary_columns",
                            "limitations",
                        )
                        if key in record
                    },
                }
            )
    directory = output / "native-preview"
    directory.mkdir()
    index = []
    for record in files:
        ref = (
            "bank-file-"
            + core.canonical_json_sha256([record["side"], record["source_file"]])[:24]
        )
        if len(record.get("preview", [])) > 20:
            raise ValueError("Producer inspection preview exceeds its contract")
        core.write_json(directory / (ref + ".json"), record)
        index.append(
            {"id": ref, "side": record["side"], "title": record["source_file"]}
        )
    core.write_json(directory / "index.json", {"files": index})
    return {
        "bank_rows": result.bank["row_count"],
        "journal_rows": result.journal["row_count"],
    }


def main() -> None:
    """Close the maintained implementation boundary before importing its engine."""
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root / "scripts"))
    from implementation_bootstrap import activate_implementation_boundary

    activate_implementation_boundary()
    import journal_bank_core as core
    from vera_assurance import load_client_engagement_context_file

    request = json.loads(sys.stdin.read(128001))
    if request["operation"] == "implementation":
        sys.stdout.write(
            json.dumps(
                {
                    "sha256": core.canonical_json_sha256(
                        core.build_implementation_artifact_receipts()
                    )
                }
            )
        )
        return
    bank, journal, output = (
        Path(request[key]) for key in ("bank", "journal", "output")
    )
    sample = Path(request["sample"]) if request.get("sample") else None
    recipe = Path(request["recipe"]) if request.get("recipe") else None
    context = load_client_engagement_context_file(
        request["context"],
        expected_workflow_id="journal-bank-reconciliation",
        input_paths=[
            bank,
            journal,
            *([sample] if sample else []),
            *([recipe] if recipe else []),
        ],
        output_dir=output,
    )
    if request["operation"] == "review":
        try:
            proposed = request["proposal"]
            original = core.read_json(recipe)
            if set(proposed) != {"bank", "journal", "policy"}:
                raise ValueError("Review requires exactly bank, journal and policy")
            receipts = core.read_json(recipe.parent / "input_receipts.json")["receipts"]
            for side in ("bank", "journal"):
                if set(proposed[side]) != set(original[side]["files"]):
                    raise ValueError(
                        "Review must retain the exact inspected file population"
                    )
                side_receipts = {
                    row["path"]: row["artifact_id"]
                    for row in receipts
                    if row["root_id"] == "source_" + side
                }
                for name, supplied in proposed[side].items():
                    allowed = {
                        "header_rows",
                        "mapping",
                        "potential_monetary_columns",
                        "excluded_monetary_columns",
                        "direction_value_mapping",
                        "date_convention",
                        "date_locale",
                        "non_movement_summary_labels",
                        "csv_field_delimiter",
                        "decimal_separator",
                        "thousands_separator",
                    }
                    if set(supplied) - allowed:
                        raise ValueError("Unexpected source mapping field")
                    decision = core.build_mapping_review_receipt(
                        decision_id="native.mapping."
                        + core.canonical_json_sha256([side, name])[:24],
                        reviewer_ref=request["actor"],
                        reviewed_on=request["reviewed_on"],
                        source_artifact_ref=side_receipts[name],
                        side=side,
                        source_file=name,
                        **supplied,
                    )
                    original[side]["files"][name] = {
                        **supplied,
                        "mapping_decision": decision,
                    }
            policy = proposed["policy"]
            original["relationship"] = {
                "policy": policy,
                "review_content_sha256": core.canonical_json_sha256({"policy": policy}),
                "decision": core.build_relationship_review_receipt(
                    decision_id="native.relationship",
                    reviewer_ref=request["actor"],
                    reviewed_on=request["reviewed_on"],
                    source_artifact_refs=[
                        row["artifact_id"]
                        for row in receipts
                        if row["root_id"] in {"source_bank", "source_journal"}
                    ],
                    policy=policy,
                ),
            }
            original["matching"]["amount_tolerance"] = policy["amount_tolerance"]
            original["matching"]["date_window_days"] = policy["date_window_days"]
        except (ValueError, KeyError, TypeError) as error:
            sys.stdout.write(json.dumps({"review_refused": str(error)}))
            return
        recipe = output / "reviewed_recipe.json"
        core.write_json(recipe, original)
    if request["operation"] in {"inspect", "review"}:
        result = core.inspect_inputs(
            bank,
            journal,
            output,
            recipe,
            sample_path=sample,
            language=request["language"],
            document_language=request["document_language"],
        )
        counts = project(result, output, core)
        qualification = core.read_json(output / "source_qualifications.json")["status"]
        sys.stdout.write(json.dumps({**counts, "qualification_status": qualification}))
        return
    if request["operation"] != "reconcile":
        raise ValueError("Unknown bank preparation operation")
    policy = core.read_json(recipe)["relationship"]["policy"]
    result = core.run_reconciliation(
        bank,
        journal,
        output,
        recipe,
        sample_path=sample,
        tolerance=policy["amount_tolerance"],
        date_window_days=policy["date_window_days"],
        language=request["language"],
        document_language=request["document_language"],
        client_run_id=context["run_id"],
        client_run_root=Path(context["run_root"]),
    )
    sys.stdout.write(
        json.dumps(
            {
                "status": "reconciled",
                "matched": result.matches.height,
                "unmatched_bank": result.unmatched_bank.height,
                "unmatched_journal": result.unmatched_journal.height,
            }
        )
    )


if __name__ == "__main__":
    main()
