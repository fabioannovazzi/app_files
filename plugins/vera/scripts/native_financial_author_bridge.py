"""Replay maintained contract/source checks without running or approving a recipe."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

__all__ = ["main", "PENDING_FDD_FIELDS"]
PENDING_FDD_FIELDS = (
    "schema_version",
    "case_id",
    "scope_id",
    "entity_refs",
    "pack_id",
    "currency",
    "unit",
    "reporting_period",
    "package",
    "datasets",
    "relationships",
    "crosswalks",
    "request_id",
    "decisions",
    "inputs",
    "limitations",
)


def main() -> None:
    """Use exact fixed producer checks; accounting interpretation remains external."""
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root / "scripts"))
    import run_pack
    from vera_assurance import (
        load_client_engagement_context_file,
        validate_client_workflow_run,
    )

    args = json.loads(sys.stdin.read(128001))
    if args.get("operation") == "review_value":
        value = args["value"]
        if args["pack_id"] not in {
            "monthly_pnl",
            "working_capital",
            "customer_concentration",
        }:
            from preparation_contract_kernel import canonical_json_sha256
            from vera_financial_analysis import build_fdd_case

            review = {
                "status": "reviewed",
                "reviewed_on": args["reviewed_at"],
                "reviewer_ref": args["reviewer_ref"],
                "basis": args["basis"],
            }
            pending = value.get("schema_version") == "vera.native.fdd_case_proposal.v1"
            case = value if pending else value["fdd_case"]
            stack = value if pending else case["contract_stack"]
            decisions = (
                [
                    {**decision, **review, "basis": decision["basis"]}
                    for decision in case["decisions"]
                ]
                if pending
                else [
                    {
                        **decision,
                        "reviewed_on": review["reviewed_on"],
                        "reviewer_ref": review["reviewer_ref"],
                    }
                    for decision in case["reviewed_decisions"]
                ]
            )
            reviewed = build_fdd_case(
                case_id=case["case_id"],
                scope_id=case["scope_id"],
                entity_refs=case["entity_refs"],
                pack_id=case["pack_id"],
                currency=case["currency"],
                unit=case["unit"],
                reporting_period=case["reporting_period"],
                package=stack["package"],
                datasets=stack["datasets"],
                relationships=stack["relationships"],
                crosswalks=stack["crosswalks"],
                request_id=(
                    stack["request_id"] if pending else stack["request"]["request_id"]
                ),
                review=review,
                reviewed_decisions=decisions,
                inputs=case["inputs"],
                limitations=case["limitations"],
            )
            content = {
                "schema_version": "vera.fdd_execution_bundle.v2",
                **{
                    k: reviewed["contract_stack"][k]
                    for k in [
                        "package",
                        "datasets",
                        "relationships",
                        "crosswalks",
                        "request",
                    ]
                },
                "fdd_case": reviewed,
            }
            value = {**content, "content_sha256": canonical_json_sha256(content)}
        sys.stdout.write(json.dumps({"case": value}, ensure_ascii=False))
        return
    if args.get("operation") == "bindings":
        # Only lexical declaration parsing occurs here; no original is opened.
        with tempfile.TemporaryDirectory(prefix="financial-case-shape-") as temporary:
            candidate = Path(temporary).resolve() / "case.json"
            candidate.write_text(json.dumps(args["value"]), encoding="utf-8")
            slots = run_pack.declared_case_input_bindings(candidate, args["pack_id"])
            result = {
                "sources": [
                    {
                        "source_id": identity,
                        "locator": path.relative_to(candidate.parent).as_posix(),
                    }
                    for identity, path in slots
                ]
            }
        sys.stdout.write(json.dumps(result))
        return
    case = Path(args["case"])
    pack = args["pack_id"]
    try:
        context = load_client_engagement_context_file(
            Path(args["context"]),
            expected_workflow_id="financial-analysis",
            input_paths=[case],
            output_dir=case.parent,
        )
        validate_client_workflow_run(
            context,
            expected_workflow_id="financial-analysis",
            input_paths=run_pack.declared_case_input_paths(case, pack),
            output_dir=case.parent,
        )
        if pack == "monthly_pnl":
            import prepare_monthly_pnl_case as producer

            producer._load_case(case)
        elif pack == "customer_concentration":
            import prepare_customer_concentration_case as concentration

            concentration._load_case(case)
        elif pack == "working_capital":
            import prepare_working_capital_case as working

            value = working.strict_json_load(case)
            working._validate_case_shape(value)
            for identity, receipt in value["files"].items():
                working._validate_file_receipt(case.parent, receipt, label=identity)
        else:
            import prepare_fdd_case as fdd

            value = json.loads(case.read_bytes())
            if value.get("schema_version") == "vera.native.fdd_case_proposal.v1":
                from preparation_contract_kernel import (
                    file_snapshot_beneath,
                    resolve_local_file,
                )
                from vera_financial_analysis import (
                    validate_crosswalk_manifest,
                    validate_data_package_manifest,
                    validate_dataset_contract,
                    validate_relationship_contract,
                )

                required = set(PENDING_FDD_FIELDS)
                if (
                    set(value) != required
                    or value["pack_id"] != pack
                    or not isinstance(value["decisions"], list)
                    or any(
                        not isinstance(d, dict) or set(d) != {"decision_ref", "basis"}
                        for d in value["decisions"]
                    )
                ):
                    raise ValueError(
                        "Invalid pending FDD constructor fields or decision identities/bases"
                    )
                package = validate_data_package_manifest(value["package"])
                for key, validator in [
                    ("datasets", validate_dataset_contract),
                    ("relationships", validate_relationship_contract),
                    ("crosswalks", validate_crosswalk_manifest),
                ]:
                    for contract in value[key]:
                        validator(contract)
                for source in package["sources"]:
                    path = resolve_local_file(
                        case.parent, source["locator"], label="Pending FDD source"
                    )
                    size, digest = file_snapshot_beneath(path, root=case.parent)
                    if (
                        path.name != source["file_name"]
                        or size != source["byte_count"]
                        or digest != source["sha256"]
                    ):
                        raise ValueError("Pending FDD source receipt changed")
                sys.stdout.write(
                    json.dumps(
                        {
                            "valid": False,
                            "reviewable": True,
                            "report_ready": False,
                            "recipe_executed": False,
                            "scope": "Pending FDD constructor fields with validated source contracts/receipts. No public FDD case or review exists yet. Named human review supplies real review metadata to the unchanged public builder, which checks full FDD inputs/reference closure before conservation.",
                        }
                    )
                )
                return
            fdd._validate_bundle(value, expected_pack_id=pack, bundle_root=case.parent)
        result = {"valid": True}
    except (ValueError, KeyError, TypeError) as error:
        result = {"valid": False, "error": str(error)}
    result.update(
        scope="Maintained case-shape, contract-reference and source-receipt checks only. Source table parsing, reconciliation and recipe execution are separate; no professional approval or source tie-out.",
        report_ready=False,
        recipe_executed=False,
    )
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
