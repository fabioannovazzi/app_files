"""Retain actual evaluation artifacts; hashes never establish research quality."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import secrets
import sys
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "record_evaluation",
    "verify_evaluation",
    "record_assessment",
    "export_blinded_comparison",
    "main",
]

WORKFLOWS = {"vera", "lucia", "standard_codex", "previous_pipeline"}
KINDS = {"fixed_source_reasoning", "authority_discovery"}
ROLES = {
    "assignment",
    "material",
    "source_capture",
    "source_inventory",
    "research_history",
    "answer_revision",
    "final_review",
    "final_answer",
    "execution_evidence",
    "host_configuration",
    "plugin_package",
}


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Evaluation record must be a JSON object")
    return value


def _file(root: Path, name: object) -> Path:
    if (
        not isinstance(name, str)
        or not name
        or Path(name).is_absolute()
        or ".." in Path(name).parts
    ):
        raise ValueError("Evaluation input requires a relative path inside its root")
    path = root
    for part in Path(name).parts:
        path /= part
        if path.is_symlink():
            raise ValueError("Evaluation input cannot be a symlink")
    if not path.resolve(strict=True).is_relative_to(root) or not path.is_file():
        raise ValueError("Evaluation input escapes its root")
    return path


def _bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()


def record_evaluation(root: Path, specification: dict[str, Any]) -> Path:
    """Freeze selected, already-existing run evidence without executing or grading it."""
    root = root.resolve(strict=True)
    workflow, kind = specification.get("workflow"), specification.get("evaluation_kind")
    if (
        not isinstance(workflow, str)
        or workflow not in WORKFLOWS
        or not isinstance(kind, str)
        or kind not in KINDS
    ):
        raise ValueError("Declare the evaluated workflow and evaluation kind")
    for key in ("case_id", "evaluation_id"):
        if not isinstance(specification.get(key), str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]*", specification[key]
        ):
            raise ValueError(f"Missing or invalid evaluation identity: {key}")
    supplied = specification.get("artifacts")
    if not isinstance(supplied, list) or not supplied:
        raise ValueError("Actual evaluation artifacts are required")
    selected = []
    for item in supplied:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("role"), str)
            or item["role"] not in ROLES
        ):
            raise ValueError("Unknown evaluation artifact role")
        path = _file(root, item.get("path"))
        selected.append((item["role"], path, path.read_bytes()))
    roles = [role for role, _, _ in selected]
    for role in ("assignment", "final_answer", "host_configuration"):
        if roles.count(role) != 1:
            raise ValueError(f"Evaluation requires one actual {role}")
    if "execution_evidence" not in roles:
        raise ValueError("Evaluation requires retained execution evidence")
    configuration = json.loads(
        next(raw for role, _, raw in selected if role == "host_configuration")
    )
    if not isinstance(configuration, dict) or any(
        not isinstance(configuration.get(key), str) or not configuration[key].strip()
        for key in ("host", "model", "configuration_observation", "research_date")
    ):
        raise ValueError(
            "Record the observed host, model, research date and configuration limits"
        )
    date.fromisoformat(configuration["research_date"])
    if not isinstance(configuration.get("research_tools"), list) or any(
        not isinstance(tool, str) or not tool.strip()
        for tool in configuration["research_tools"]
    ):
        raise ValueError("Record the actual available research tools")
    if workflow == "standard_codex":
        if (
            roles.count("plugin_package")
            or configuration.get("specialist_plugins_exposed") != []
        ):
            raise ValueError(
                "Standard Codex requires an explicitly recorded specialist-free configuration"
            )
        product = None
    else:
        if roles.count("plugin_package") != 1 or not {
            "research_history",
            "final_review",
            "source_inventory",
        }.issubset(roles):
            raise ValueError(
                "Plugin evaluation requires its actual package, research history, source inventory and final review"
            )
        archive = next(raw for role, _, raw in selected if role == "plugin_package")
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            manifests = []
            for name in package.namelist():
                if name.endswith(
                    (".codex-plugin/plugin.json", ".claude-plugin/plugin.json")
                ):
                    info = package.getinfo(name)
                    if info.file_size > 100000:
                        raise ValueError("Invalid plugin manifest size")
                    manifest = json.loads(package.read(name))
                    if manifest.get("name") in {"vera", "lucia"}:
                        manifests.append(manifest)
        if len(manifests) != 1 or not isinstance(manifests[0].get("version"), str):
            raise ValueError(
                "Evaluation package must identify one actual product version"
            )
        product = {
            "name": manifests[0]["name"],
            "version": manifests[0]["version"],
            "package_sha256": hashlib.sha256(archive).hexdigest(),
        }
        if (
            workflow != "previous_pipeline" and workflow != product["name"]
        ) or configuration.get("observed_plugin_version") != product["version"]:
            raise ValueError("Recorded host version differs from the evaluated package")
        retained = {path for role, path, _ in selected if role == "source_capture"}
        for role, inventory_path, raw in selected:
            if role != "source_inventory":
                continue
            inventory = json.loads(raw)
            if not isinstance(inventory, dict) or not isinstance(
                inventory.get("sources"), list
            ):
                raise ValueError("Invalid evaluated source inventory")
            for source in inventory["sources"]:
                if not isinstance(source, dict) or not isinstance(
                    source.get("capture_history", []), list
                ):
                    raise ValueError("Invalid evaluated source capture history")
                for capture in [source, *source.get("capture_history", [])]:
                    if not isinstance(capture, dict):
                        raise ValueError("Invalid evaluated source capture")
                    for field in ("captured_text_path", "captured_original_path"):
                        if capture.get(field):
                            path = _file(
                                root,
                                (
                                    inventory_path.parent.relative_to(root)
                                    / capture[field]
                                ).as_posix(),
                            )
                            if path not in retained:
                                raise ValueError(
                                    "Evaluation must retain every inventoried source capture"
                                )
    limits = specification.get("trace_limits")
    if not isinstance(limits, list) or any(
        not isinstance(item, str) or not item.strip() for item in limits
    ):
        raise ValueError(
            "Record actual trace limits, using an empty list only when none are known"
        )
    record = {
        "schema_version": "1.0",
        "evaluation_id": specification["evaluation_id"],
        "case_id": specification["case_id"],
        "workflow": workflow,
        "evaluation_kind": kind,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "host_configuration": configuration,
        "product": product,
        "trace_limits": limits,
        "artifacts": [],
        "assessment_status": "pending",
        "quality": "not_assessed_by_helper",
        "execution_authenticity": "not_certified_by_file_hashes",
    }
    destination = root / "evaluation_runs" / specification["evaluation_id"]
    if not destination.resolve().is_relative_to(root):
        raise ValueError("Evaluation output escapes its root")
    destination.mkdir(parents=True, exist_ok=False)
    artifact_dir = destination / "artifacts"
    artifact_dir.mkdir()
    for index, (role, source, raw) in enumerate(selected):
        name = f"{index:03d}-{role}{source.suffix}"
        (artifact_dir / name).write_bytes(raw)
        record["artifacts"].append(
            {
                "role": role,
                "original_path": source.relative_to(root).as_posix(),
                "path": f"artifacts/{name}",
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    record_raw = _bytes(record)
    (destination / "evaluation_record.json").write_bytes(record_raw)
    (destination / "evaluation_receipt.json").write_bytes(
        _bytes({"record_sha256": hashlib.sha256(record_raw).hexdigest()})
    )
    verify_evaluation(destination)
    return destination


def verify_evaluation(run: Path) -> dict[str, Any]:
    """Verify retained bytes and assessment identity, without inferring quality."""
    run = run.resolve(strict=True)
    record = _json(_file(run, "evaluation_record.json"))
    receipt = _json(_file(run, "evaluation_receipt.json"))
    if hashlib.sha256(
        (run / "evaluation_record.json").read_bytes()
    ).hexdigest() != receipt.get("record_sha256"):
        raise ValueError("Evaluation metadata changed")
    if record.get("schema_version") != "1.0" or not isinstance(
        record.get("artifacts"), list
    ):
        raise ValueError("Invalid evaluation record")
    for item in record["artifacts"]:
        if (
            hashlib.sha256(_file(run, item["path"]).read_bytes()).hexdigest()
            != item["sha256"]
        ):
            raise ValueError("Evaluation artifact changed")
    if (run / "assessment_receipt.json").exists():
        assessment = _json(_file(run, "assessment_receipt.json"))
        if assessment.get("evaluation_record_sha256") != receipt["record_sha256"]:
            raise ValueError("Assessment applies to a different evaluation revision")
        path = _file(run, assessment["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != assessment["sha256"]:
            raise ValueError("Evaluation assessment changed")
        if _json(path).get("final_answer_sha256") != _answer_digest(record):
            raise ValueError("Assessment applies to a different answer revision")
        record["assessment_status"] = "recorded"
        record["assessment"] = assessment
    return record


def _answer_digest(record: dict[str, Any]) -> str:
    answers = [
        item["sha256"] for item in record["artifacts"] if item["role"] == "final_answer"
    ]
    if len(answers) != 1:
        raise ValueError("Evaluation final answer identity is missing or ambiguous")
    return answers[0]


def record_assessment(run: Path, assessment: dict[str, Any]) -> None:
    """Attach an actual rater's assessment to the exact delivered answer revision."""
    run = run.resolve(strict=True)
    record = verify_evaluation(run)
    if record.get("assessment"):
        raise ValueError("An existing assessment cannot be silently overwritten")
    if assessment.get("final_answer_sha256") != _answer_digest(record):
        raise ValueError("Assessment applies to a different answer revision")
    if (
        any(
            not isinstance(assessment.get(key), str) or not assessment[key].strip()
            for key in ("reviewer", "reviewer_role", "assessment")
        )
        or type(assessment.get("workflow_label_known")) is not bool
    ):
        raise ValueError(
            "An actual reviewer, assessment and label-exposure declaration are required"
        )
    path = run / "assessment.json"
    with path.open("xb") as stream:
        stream.write(_bytes(assessment))
    receipt = {
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "evaluation_record_sha256": hashlib.sha256(
            (run / "evaluation_record.json").read_bytes()
        ).hexdigest(),
    }
    temporary = run / ".assessment_receipt.tmp"
    with temporary.open("xb") as stream:
        stream.write(_bytes(receipt))
    temporary.replace(run / "assessment_receipt.json")


def export_blinded_comparison(runs: list[Path], output: Path) -> Path:
    """Withhold workflow labels; preserve delivered content and known blinding limits."""
    if len(runs) < 2:
        raise ValueError("A comparison requires at least two actual runs")
    if len({run.resolve() for run in runs}) != len(runs):
        raise ValueError("A comparison requires distinct actual runs")
    records = [verify_evaluation(run) for run in runs]
    assignments = [
        {item["sha256"] for item in record["artifacts"] if item["role"] == "assignment"}
        for record in records
    ]
    materials = [
        sorted(
            item["sha256"] for item in record["artifacts"] if item["role"] == "material"
        )
        for record in records
    ]
    if (
        any(value != assignments[0] for value in assignments)
        or any(value != materials[0] for value in materials)
        or any(
            record["evaluation_kind"] != records[0]["evaluation_kind"]
            or record["host_configuration"]["research_date"]
            != records[0]["host_configuration"]["research_date"]
            or record["host_configuration"]["model"]
            != records[0]["host_configuration"]["model"]
            or sorted(record["host_configuration"]["research_tools"])
            != sorted(records[0]["host_configuration"]["research_tools"])
            for record in records
        )
    ):
        raise ValueError(
            "Compare the same assignment, materials, evaluation kind, model, research tools and date"
        )
    output.mkdir(parents=True, exist_ok=False)
    assessor = output / "assessor"
    assessor.mkdir()
    order = list(zip(runs, records))
    secrets.SystemRandom().shuffle(order)
    mapping = []
    for run, record in order:
        identifier = secrets.token_hex(8)
        destination = assessor / identifier
        destination.mkdir()
        for index, item in enumerate(record["artifacts"]):
            if item["role"] in {
                "assignment",
                "material",
                "final_answer",
                "source_capture",
            }:
                source = _file(run.resolve(), item["path"])
                (
                    destination / f'{index:03d}-{item["role"]}{source.suffix}'
                ).write_bytes(source.read_bytes())
        mapping.append(
            {
                "blind_id": identifier,
                "evaluation_id": record["evaluation_id"],
                "workflow": record["workflow"],
                "final_answer_sha256": _answer_digest(record),
            }
        )
    (output / "private_mapping.json").write_bytes(_bytes({"mapping": mapping}))
    (assessor / "blinding_limits.txt").write_text(
        "Workflow mapping is withheld. Original answer/source content is unchanged and may reveal a workflow. Each reviewer must record whether the workflow label was known. Hashes do not certify execution, expertise or legal quality.\n",
        encoding="utf-8",
    )
    return assessor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record")
    record.add_argument("--root", type=Path, required=True)
    record.add_argument("--specification", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--run", type=Path, required=True)
    assess = commands.add_parser("assess")
    assess.add_argument("--run", type=Path, required=True)
    assess.add_argument("--assessment", type=Path, required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("--run", type=Path, action="append", required=True)
    compare.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "record":
        result = str(record_evaluation(args.root, _json(args.specification)))
    elif args.command == "verify":
        result = verify_evaluation(args.run)
    elif args.command == "assess":
        record_assessment(args.run, _json(args.assessment))
        result = verify_evaluation(args.run)
    else:
        result = str(export_blinded_comparison(args.run, args.output_dir))
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
