"""Invoke the maintained valuation reader, compiler and exporter in isolation."""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Verify fixed receipts and arithmetic; never select methods or attest review."""
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root / "scripts"))
    import check_dependencies

    if check_dependencies.main([]):
        raise ValueError("Valuation declared dependencies are unavailable")
    import run_valuation
    import valuation_case
    import valuation_report
    import vera_assurance

    request = json.loads(sys.stdin.read(128001))
    if request["operation"] == "contract":
        paths = [
            *(root / "scripts").glob("*.py"),
            *(root / "references").glob("*.json"),
            root / "requirements.txt",
        ]
        result = {
            "implementation": {
                p.relative_to(root)
                .as_posix(): hashlib.sha256(p.read_bytes())
                .hexdigest()
                for p in sorted(paths)
            }
        }
        for p in sorted(Path(vera_assurance.__file__).parent.rglob("*.py")):
            result["implementation"][
                "vera_assurance/"
                + p.relative_to(Path(vera_assurance.__file__).parent).as_posix()
            ] = hashlib.sha256(p.read_bytes()).hexdigest()
        planning = root.parent / "business-planning"
        for p in sorted(
            [
                *(planning / "scripts").glob("*.py"),
                *(planning / "assets").glob("report-interaction.*"),
            ]
        ):
            result["implementation"][
                "business-planning/" + p.relative_to(planning).as_posix()
            ] = hashlib.sha256(p.read_bytes()).hexdigest()
        for candidate in (
            root / "vendor/modules",
            root.parent.parent / "vendor/modules",
            root.parent / "_shared/vendor/modules",
        ):
            table = candidate / "reporting_table.py"
            if table.is_file():
                result["implementation"]["reporting_table.py"] = hashlib.sha256(
                    table.read_bytes()
                ).hexdigest()
                break
    else:
        case_path = Path(request["case"])
        context_path = Path(request["context"])
        case = valuation_case.read_json(case_path)
        context = vera_assurance.load_client_engagement_context_file(
            context_path,
            expected_workflow_id="business-valuation",
            input_paths=[case_path],
        )
        valuation_case.require(
            context["schema_version"] == "vera.client_workflow_context.v2",
            "Valuation requires a portable v2 context",
        )
        source_root = Path(context["run_root"]) / "inputs"
        sources = valuation_case.source_paths(case, source_root)
        valuation_case._sources(case, source_root)
        context = vera_assurance.load_client_engagement_context_file(
            context_path,
            expected_workflow_id="business-valuation",
            input_paths=[case_path, *sources],
            output_dir=Path(context["output_dir"]),
        )
        if "plan_binding" in case:
            source = next(
                r
                for r in case["sources"]
                if r["id"] == case["plan_binding"]["source_id"]
            )
            path = (source_root / source["path"]).resolve()
            binding = next(
                (
                    r
                    for r in context["input_bindings"]
                    if Path(r["path"]).resolve() == path
                ),
                None,
            )
            valuation_case.require(
                binding is not None
                and binding["kind"] == "upstream_artifact"
                and binding["upstream_workflow_id"] == "business-planning",
                "Plan must be a finalized same-engagement Business Planning artifact",
            )
        if request["operation"] == "select":
            result = {"case": case}
        else:
            if request["operation"] == "prepare":
                run_valuation.run_case(case_path, context_path)
            elif request["operation"] not in {"read", "review"}:
                raise ValueError("Unknown valuation operation")
            report = valuation_case.build_valuation(
                case,
                source_root,
                replay_parent=Path(context["output_dir"]) / "plan-replay",
            )
            directory = Path(context["output_dir"]) / (
                "valuation-" + report["case_sha256"][:20]
            )
            retained = valuation_case.read_json(directory / "valuation.json")
            valuation_case.require(
                retained == report, "Valuation differs from public replay"
            )
            valuation_case.require(
                (directory / "valuation_report.html").read_text(encoding="utf-8")
                == valuation_report.compile_html(report),
                "Valuation HTML differs from public replay",
            )
            artifacts = json.loads((directory / "artifacts.json").read_bytes())
            declared = set()
            for row in artifacts:
                name = row["path"]
                path = directory / name
                valuation_case.require(
                    isinstance(name, str)
                    and Path(name).name == name
                    and name not in declared
                    and path.is_file()
                    and not path.is_symlink()
                    and path.stat().st_nlink == 1
                    and path.stat().st_size == row["bytes"]
                    and hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"],
                    "Valuation public artifact changed",
                )
                declared.add(name)
            valuation_case.require(
                {p.name for p in directory.iterdir()} == declared | {"artifacts.json"},
                "Valuation artifact population differs",
            )
            if request["operation"] == "review":
                collection, index = request["collection"], request["index"]
                value = (
                    [
                        {**item, "normalization_id": group["id"]}
                        for group in report["normalizations"]
                        for item in group.get("adjustments", [])
                    ]
                    if collection == "normalization_adjustments"
                    else report[collection]
                )
                records = value if isinstance(value, list) else [value]
                record = records[index]
                reviewed_case = deepcopy(case)
                if collection == "mandate_assessment":
                    target = reviewed_case["mandate_details"]
                elif collection == "conclusion":
                    target = reviewed_case["conclusion"]
                elif collection == "normalization_adjustments":
                    group = next(
                        item
                        for item in reviewed_case["normalizations"]
                        if item["id"] == record["normalization_id"]
                    )
                    target = next(
                        item
                        for item in group["adjustments"]
                        if item["id"] == record["id"]
                    )
                else:
                    identity = "method_id" if collection == "methods" else "id"
                    target = next(
                        item
                        for item in reviewed_case[collection]
                        if item["id"] == record[identity]
                    )
                target["review"] = {
                    **request["review"],
                    **(
                        {"dependency_sha256": record["dependency_sha256"]}
                        if record.get("dependency_sha256")
                        else {}
                    ),
                }
                updated = valuation_case.build_valuation(
                    reviewed_case,
                    source_root,
                    replay_parent=Path(context["output_dir"]) / "plan-replay",
                )
                updated_value = (
                    [
                        {**item, "normalization_id": group["id"]}
                        for group in updated["normalizations"]
                        for item in group.get("adjustments", [])
                    ]
                    if collection == "normalization_adjustments"
                    else updated[collection]
                )
                updated_record = (
                    updated_value[index]
                    if isinstance(updated_value, list)
                    else updated_value
                )
                valuation_case.require(
                    request["review"]["decision"] != "accepted"
                    or updated_record["status"] == "accepted_workpaper",
                    "Public dependencies do not permit acceptance of this record",
                )
                result = {"case": reviewed_case, "record": updated_record}
            else:
                result = {"report": report, "directory": directory.name}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
