"""Exercise an exact Clara Cowork ZIP without repository or installed dependencies.

Fixed fixture arithmetic and content hashes are mechanically verifiable. This
gate does not judge agent routing, business interpretation, or visual quality.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import logging
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

__all__ = [
    "main",
    "extract_package",
    "module_choices",
    "verify_acceptance",
    "verify_coverage",
]
LOGGER = logging.getLogger(__name__)
CASE = "reporting-engine.period_comparison.trend"
GATE_VERSION = 4
REQUIRED_HOST_AXES = ("Linux/3.10", "macOS/3.12", "Windows/3.10", "Windows/3.12")


def verify_coverage(path: Path, zip_hash: str, workflows: set[str]) -> str:
    """Enforce C18's mechanical coverage/hash contract, not semantic quality."""
    original_hash = digest(path)
    receipt = read_json(path)
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema_version") != 1
        or receipt.get("zip_sha256") != zip_hash
        or receipt.get("status") != "pass"
        or not workflows
    ):
        raise ValueError("Coverage is missing, failed, or for a different ZIP")
    for field in ("reviewer", "reviewed_at"):
        if not isinstance(receipt.get(field), str) or not receipt[field].strip():
            raise ValueError(f"Coverage needs {field}")
    for section, names, checks in (
        ("workflows", sorted(workflows), ("normal_path", "material_failure_path")),
        (
            "hosts",
            REQUIRED_HOST_AXES,
            ("fresh_core_setup", "optional_setup", "blocked_install", "failure_report"),
        ),
    ):
        records = receipt.get(section)
        if not isinstance(records, dict):
            raise ValueError(f"Coverage needs {section}")
        for name in names:
            record = records.get(name)
            if not isinstance(record, dict):
                raise ValueError(f"Coverage needs {section}/{name}")
            for check in checks:
                axis = record.get(check)
                if (
                    not isinstance(axis, dict)
                    or axis.get("status") != "pass"
                    or axis.get("zip_sha256") != zip_hash
                    or not isinstance(axis.get("evidence"), list)
                    or not axis["evidence"]
                ):
                    raise ValueError(f"Coverage needs passing {section}/{name}/{check}")
                for evidence in axis["evidence"]:
                    if not isinstance(evidence, dict):
                        raise ValueError("Invalid coverage evidence record")
                    relative = evidence.get("path")
                    if (
                        not isinstance(relative, str)
                        or not relative
                        or Path(relative).is_absolute()
                    ):
                        raise ValueError("Coverage evidence needs a relative path")
                    artifact = (path.parent / relative).resolve()
                    if (
                        not artifact.is_relative_to(path.parent.resolve())
                        or not artifact.is_file()
                        or artifact.stat().st_size == 0
                        or digest(artifact) != evidence.get("sha256")
                    ):
                        raise ValueError("Missing or changed coverage evidence")
    if digest(path) != original_hash:
        raise ValueError("Coverage changed during verification")
    return original_hash


def verify_hook_registration(root: Path) -> None:
    """Check exact paths: Claude auto-loads the standard hooks file."""
    manifest = read_json(root / ".claude-plugin/plugin.json")
    automatic = root / "hooks/hooks.json"
    if not automatic.is_file():
        raise ValueError("Clara is missing its automatic startup hooks file")
    hooks = manifest.get("hooks", [])
    references = [hooks] if isinstance(hooks, str) else hooks
    if isinstance(references, list) and any(
        isinstance(reference, str)
        and (root / reference).resolve() == automatic.resolve()
        for reference in references
    ):
        raise ValueError(
            "Duplicate hooks file: hooks/hooks.json is loaded automatically"
        )
    if not read_json(automatic).get("hooks", {}).get("SessionStart"):
        raise ValueError("Clara is missing SessionStart hooks")


def digest(path: Path) -> str:
    """Hash the actual artifact, not its version label."""
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def read_json(path: Path) -> Any:
    """Read an evidence or package JSON document."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    """Persist evidence even when a later stage fails."""
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def extract_package(archive: Path, destination: Path) -> None:
    """Reject unsafe entries before extracting a release candidate."""
    with ZipFile(archive) as package:
        names = package.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP entries")
        for entry in package.infolist():
            target = (destination / entry.filename).resolve()
            if not target.is_relative_to(destination.resolve()) or stat.S_ISLNK(
                entry.external_attr >> 16
            ):
                raise ValueError(f"Unsafe ZIP entry: {entry.filename}")
        if ".claude-plugin/plugin.json" not in names:
            raise ValueError("Expected a root-layout Cowork ZIP")
        package.extractall(destination)


def module_choices(root: Path) -> list[str]:
    """Read the CLI's literal component list without importing package code."""
    tree = ast.parse((root / "scripts/check_dependencies.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "COMPONENTS"
            for target in node.targets
        ):
            choices = ast.literal_eval(node.value)
            if choices and all(isinstance(name, str) for name in choices):
                return list(choices)
    raise ValueError("Cannot discover documented module choices")


def verify_acceptance(
    receipt_path: Path, zip_hash: str, script_report: dict[str, Any]
) -> None:
    """Require human-reviewed Cowork evidence for these exact candidate bytes."""
    receipt = read_json(receipt_path)
    if script_report["status"] != "pass":
        raise ValueError("Packaged script checks have not passed")
    if (
        receipt.get("schema_version") != 2
        or receipt.get("zip_sha256") != zip_hash
        or receipt.get("status") != "pass"
        or receipt.get("host") != "Claude Cowork"
        or receipt.get("workflow") != CASE
        or receipt.get("fresh_install") is not True
        or receipt.get("fresh_session") is not True
        or receipt.get("plugin_version")
        != script_report.get("plugin", {}).get("version")
    ):
        raise ValueError("Cowork acceptance is missing, failed, or for a different ZIP")
    for field in ("reviewer", "tested_at", "cowork_version", "environment"):
        if not isinstance(receipt.get(field), str) or not receipt[field].strip():
            raise ValueError(f"Cowork acceptance needs {field}")
    for check in ("plugin_load", "startup_hooks", "synthetic_workflow"):
        if receipt.get("checks", {}).get(check) != "pass":
            raise ValueError(f"Cowork acceptance needs a passing {check} check")
    for field in (
        "normal_answer",
        "report",
        "transcript",
        "visual_review",
        "plugin_load",
        "startup_hooks",
    ):
        record = receipt.get("evidence", {}).get(field, {})
        relative = record.get("path", "")
        path = (receipt_path.parent / relative).resolve()
        if (
            not relative
            or not path.is_relative_to(receipt_path.parent.resolve())
            or not path.is_file()
            or path.stat().st_size == 0
            or digest(path) != record.get("sha256")
        ):
            raise ValueError(f"Missing or changed Cowork evidence: {field}")


class CheckRun:
    """Run actual commands with isolated state and retain every command's log."""

    def __init__(self, archive: Path, output: Path, timeout: int) -> None:
        if (output / "result.json").exists():
            raise FileExistsError(
                f"Gate evidence already exists in {output}; use a new output directory"
            )
        self.archive, self.output, self.timeout = archive, output, timeout
        self.root = output / "package"
        self.python = (
            output
            / "bootstrap"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        self.env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("PYTHON", "MPARANZA_"))
            and key
            not in {
                "VIRTUAL_ENV",
                "PLUGIN_DATA",
                "CLAUDE_PLUGIN_DATA",
                "CLAUDE_ENV_FILE",
            }
        }
        self.env.update(
            PYTHONNOUSERSITE="1",
            PYTHONDONTWRITEBYTECODE="1",
            CLAUDE_PLUGIN_DATA=str(output / "managed"),
            MPLCONFIGDIR=str(output / "matplotlib"),
            XDG_CACHE_HOME=str(output / "cache"),
            PIP_DISABLE_PIP_VERSION_CHECK="1",
        )
        self.report: dict[str, Any] = {
            "schema_version": 1,
            "gate_version": GATE_VERSION,
            "zip_sha256": digest(archive),
            "status": "fail",
            "workflow": CASE,
            "cowork_agent_acceptance": "unverified",
            "environment": {
                "platform": platform.platform(),
                "python": sys.version,
                "python_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
                "os": platform.system(),
            },
            "steps": [],
        }

    def command(
        self,
        name: str,
        args: list[str],
        *,
        negative: bool = False,
        expected_error: str = "",
    ) -> bool:
        """Record real failures and timeouts; a negative check must actually reject."""
        started = time.monotonic()
        try:
            result = subprocess.run(
                args,
                cwd=self.root,
                env=self.env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=self.timeout,
                check=False,
            )
            code, log = result.returncode, result.stdout
        except subprocess.TimeoutExpired as error:
            code = -1
            captured = error.stdout or b""
            log = (
                captured.decode(errors="replace")
                if isinstance(captured, bytes)
                else captured
            ) + "\nCOMMAND TIMEOUT\n"
        passed = (code > 0 and expected_error in log) if negative else code == 0
        (self.output / f"{name}.log").write_text(log, encoding="utf-8")
        self.report["steps"].append(
            {
                "name": name,
                "command": args,
                "returncode": code,
                "expected_rejection": negative,
                "status": "pass" if passed else "fail",
                "seconds": round(time.monotonic() - started, 2),
                "log": f"{name}.log",
            }
        )
        write_json(self.output / "result.json", self.report)
        LOGGER.info("[%s] %s", "PASS" if passed else "FAIL", name)
        return passed

    def direct(
        self,
        name: str,
        script: str,
        *args: str,
        negative: bool = False,
        expected_error: str = "missing required role bindings",
    ) -> bool:
        return self.command(
            name,
            [
                str(self.python),
                f"modules/reporting-engine/scripts/{script}",
                *args,
            ],
            negative=negative,
            expected_error=expected_error,
        )

    def execute(self) -> None:
        """Install declared dependencies, then exercise the packaged reporting path."""
        extract_package(self.archive, self.root)
        self.report["plugin"] = read_json(self.root / ".claude-plugin/plugin.json")
        if self.report["plugin"]["name"] != "clara":
            raise ValueError("Expected Clara")
        verify_hook_registration(self.root)
        if not self.command(
            "bootstrap",
            [sys.executable, "-I", "-m", "venv", str(self.python.parent.parent)],
        ):
            return
        if not self.command(
            "isolated-python",
            [
                str(self.python),
                "-I",
                "-c",
                "import importlib.util; assert importlib.util.find_spec('polars') is None; "
                "assert importlib.util.find_spec('modules') is None",
            ],
        ):
            return
        # Public CLIs bootstrap dependencies; probe the isolated interpreter itself.
        self.command(
            "reject-uninstalled-dependency",
            [
                str(self.python),
                "-I",
                "-c",
                "import polars",
            ],
            negative=True,
            expected_error="No module named 'polars'",
        )
        self.direct(
            "cold-cli-profile",
            "profile_dataset.py",
            str(
                self.root
                / "modules/reporting-engine/fixtures/semantic_layer/retail_monthly.csv"
            ),
            "--output",
            str(self.output / "cold_profile.json"),
        )
        choices = module_choices(self.root)
        self.report["dependency_modules"] = choices
        self.command(
            "dependencies-core", [str(self.python), "scripts/check_dependencies.py"]
        )
        for module in choices:
            self.command(
                f"dependencies-{module}",
                [str(self.python), "scripts/check_dependencies.py", "--module", module],
            )
        registry = read_json(self.root / "components.json")["plugins"]
        if not set(choices) <= set(registry):
            raise ValueError("CLI accepts modules missing from components.json")
        for module in sorted(set(registry) - set(choices)):
            self.command(
                f"dependencies-{module}",
                [
                    str(self.python),
                    "scripts/managed_python_runtime.py",
                    "--module",
                    module,
                    "run",
                    "scripts/check_dependencies.py",
                ],
            )
        # Install only the published optional render declaration, through its manager.
        if not self.command(
            "render-dependencies",
            [
                str(self.python),
                "scripts/managed_python_runtime.py",
                "--module",
                "reporting-engine",
                "--requirements",
                "requirements.txt",
                "--requirements",
                "requirements-render.txt",
                "install",
            ],
        ):
            return
        fixture = self.root / "modules/reporting-engine/fixtures/semantic_layer"
        dataset = fixture / "retail_monthly.csv"
        profile = self.output / "intake/dataset_profile.json"
        self.direct(
            "intake",
            "dataset_intake.py",
            str(dataset),
            "--dataset-contract-id",
            "retail_monthly",
            "--output-dir",
            str(profile.parent),
        )
        self.direct(
            "semantics",
            "semantic_layer.py",
            "acceptance",
            "--dataset",
            str(dataset),
            "--dataset-id",
            "retail_monthly",
            "--layer",
            str(fixture / "retail_monthly.semantic.json"),
            "--source",
            str(fixture / "retail_monthly_source_notes.md"),
            "--snapshot-suite",
            str(fixture / "retail_monthly.snapshot_cases.json"),
            "--output",
            str(self.output / "semantic_acceptance.json"),
        )
        self.direct(
            "compatibility",
            "check_compatibility.py",
            str(profile),
            "--output",
            str(self.output / "compatibility.json"),
        )
        bindings = json.dumps(
            {
                "comparison_metric": "Sales",
                "period_axis": {
                    "date_column": "Date",
                    "current_period_label": "2026",
                    "previous_period_label": "2025",
                },
            }
        )
        self.direct(
            "render",
            "render_capability.py",
            "period_comparison.trend",
            str(dataset),
            "--output-dir",
            str(self.output / "render"),
            "--role-bindings-json",
            bindings,
            "--artifact-mode",
            "data_and_render",
        )
        self.direct(
            "reject-missing-role",
            "render_capability.py",
            "period_comparison.trend",
            str(dataset),
            "--output-dir",
            str(self.output / "rejected"),
            "--role-bindings-json",
            "{}",
            negative=True,
        )
        verify_rejected_render(self.output / "rejected")
        verify_outputs(self.output, dataset)
        self.direct(
            "reviewed-monthly-render",
            "run_capability.py",
            str(dataset),
            "--layer",
            str(fixture / "retail_monthly.semantic.json"),
            "--profile",
            str(profile),
            "--acceptance",
            str(self.output / "semantic_acceptance.json"),
            "--source",
            str(fixture / "retail_monthly_source_notes.md"),
            "--analysis-id",
            "analysis.sales_current_vs_prior_by_month",
            "--capability-id",
            "period_comparison.multitier_column",
            "--output-dir",
            str(self.output / "reviewed-render"),
        )
        if self.direct(
            "export-delivery",
            "run_capability.py",
            "--export-output",
            str(self.output / "reviewed-render"),
            "--delivery-dir",
            str(self.output / "delivery-staging"),
        ):
            delivery = self.output / "delivery"
            (self.output / "delivery-staging").rename(delivery)
            self.direct(
                "verify-moved-delivery",
                "run_capability.py",
                "--verify-output",
                str(delivery),
            )
            tampered = self.output / "delivery-tampered"
            shutil.copytree(delivery, tampered)
            (tampered / "period_comparison_monthly.csv").write_text("changed")
            self.direct(
                "reject-tampered-delivery",
                "run_capability.py",
                "--verify-output",
                str(tampered),
                negative=True,
                expected_error="Reviewed render artifact changed",
            )
        if digest(self.archive) != self.report["zip_sha256"]:
            raise ValueError("ZIP changed during acceptance")
        if all(step["status"] == "pass" for step in self.report["steps"]):
            self.report["status"] = "pass"


def verify_rejected_render(output: Path) -> None:
    """Require an inspectable preflight failure without published deliverables."""
    manifest = read_json(output / "render_manifest.json")
    if (
        manifest.get("status") != "failed_or_interrupted"
        or manifest.get("runner", {}).get("status") != "failed"
        or "missing required role bindings"
        not in manifest.get("failure", {}).get("message", "")
        or manifest.get("evidence", {}).get("outputs")
    ):
        raise ValueError("Invalid request did not retain the expected failure receipt")
    if read_json(output / "current_reporting.json") != manifest:
        raise ValueError("Invalid request left an inconsistent publication state")
    for path in output.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(output)
        if relative.parts[0] == ".logs" or relative.as_posix() in {
            ".render.lock",
            "render_manifest.json",
            "current_reporting.json",
        }:
            continue
        raise ValueError(f"Invalid request left a published artifact: {relative}")


def verify_outputs(output: Path, dataset: Path) -> None:
    """Verify the normal path's proof and exact bytes, not just exit status."""
    if read_json(output / "intake/dataset_intake.json")["status"] != "review_required":
        raise ValueError("First intake must require semantic review")
    if read_json(output / "semantic_acceptance.json")["result"] != "pass":
        raise ValueError("Reviewed semantics or negative snapshot cases failed")
    compatibility = read_json(output / "compatibility.json")
    trend = next(
        (
            item
            for item in compatibility["results"]
            if item["capability_id"] == "period_comparison.trend"
        ),
        {},
    )
    if trend.get("status") != "mechanically_compatible":
        raise ValueError("Fixture trend is not mechanically compatible")
    manifest = read_json(output / "render/render_manifest.json")
    if manifest["render_proof"]["status"] != "rendered":
        raise ValueError("Expected an actual chart render")
    if manifest["evidence"]["input"]["sha256"] != digest(dataset):
        raise ValueError("Render input proof mismatch")
    if not manifest["evidence"]["outputs"]:
        raise ValueError("Render has no output evidence")
    for record in manifest["evidence"]["outputs"]:
        artifact = (output / "render" / record["path"]).resolve()
        if not artifact.is_relative_to((output / "render").resolve()):
            raise ValueError("Output proof escapes render directory")
        if (
            digest(artifact) != record["sha256"]
            or artifact.stat().st_size != record["size_bytes"]
        ):
            raise ValueError(f"Render output proof mismatch: {record['path']}")
    verify_monthly_values(output / "render/period_comparison_monthly.csv")
    png = output / "render/year_over_year_line.png"
    content = png.read_bytes()
    if content[:8] != b"\x89PNG\r\n\x1a\n" or len(content) < 1000:
        raise ValueError("Missing or invalid PNG; HTML-only fallback is not a PNG pass")


def verify_monthly_values(path: Path) -> None:
    """Compare chart-side aggregates against independently specified fixture totals."""
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    values = [
        (row["Date"], float(row["AC"] or 0), float(row["PY"] or 0))
        for row in rows
        if float(row["AC"] or 0) or float(row["PY"] or 0)
    ]
    if values != [("Jan", 405000.0, 360000.0), ("Feb", 426000.0, 379500.0)]:
        raise ValueError(f"Chart totals or period order differ from fixture: {values}")


def evidence_index(output: Path) -> list[dict[str, str]]:
    """Index portable outputs and logs, excluding installed environments."""
    files = [
        *output.glob("*.log"),
        *output.glob("*.json"),
        *(output / "intake").rglob("*"),
        *(output / "render").rglob("*"),
        *(output / "rejected").rglob("*"),
        *(output / "reviewed-render").rglob("*"),
        *(output / "delivery").rglob("*"),
        *(output / "delivery-tampered").rglob("*"),
    ]
    return [
        {"path": path.relative_to(output).as_posix(), "sha256": digest(path)}
        for path in sorted(files)
        if path.is_file() and path != output / "result.json"
    ]


def verify_saved_evidence(output: Path, report: dict[str, Any]) -> None:
    """Prevent a stale result or altered outputs from authorizing promotion."""
    if (
        report.get("gate_version") != GATE_VERSION
        or report.get("workflow") != CASE
        or not report.get("artifacts")
    ):
        raise ValueError("Missing current gate evidence")
    if not report.get("steps") or any(
        step["status"] != "pass" for step in report["steps"]
    ):
        raise ValueError("Missing or failed script steps")
    for record in report["artifacts"]:
        path = (output / record["path"]).resolve()
        if (
            not path.is_relative_to(output.resolve())
            or digest(path) != record["sha256"]
        ):
            raise ValueError("Saved script evidence has changed")


def main(argv: list[str] | None = None) -> int:
    """Run candidate checks, optionally requiring a real Cowork acceptance receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--cowork-acceptance", type=Path)
    parser.add_argument(
        "--coverage-evidence",
        type=Path,
        help="Reviewed exact-ZIP workflow and supported-host coverage; required for release.",
    )
    parser.add_argument(
        "--verify-release",
        action="store_true",
        help="Verify saved script evidence and real Cowork acceptance; do not rerun.",
    )
    parser.add_argument(
        "--promote-to",
        type=Path,
        help="Copy the exact verified ZIP only after both gates pass.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    output = args.output.resolve()
    if args.verify_release:
        try:
            write_json(output / "release-verification.json", {"status": "unverified"})
            report = read_json(output / "result.json")
            if not args.cowork_acceptance:
                raise ValueError("Release requires real Cowork acceptance")
            if not args.coverage_evidence:
                raise ValueError("Release requires complete workflow and host coverage")
            if report["zip_sha256"] != digest(args.zip) or report["status"] != "pass":
                raise ValueError("Script acceptance failed or is for a different ZIP")
            verify_saved_evidence(output, report)
            with tempfile.TemporaryDirectory(
                prefix="clara-release-check-"
            ) as directory:
                root = Path(directory)
                extract_package(args.zip, root)
                verify_hook_registration(root)
                if read_json(root / ".claude-plugin/plugin.json") != report["plugin"]:
                    raise ValueError("Saved plugin identity differs from candidate")
                # Privacy review is an internal governance skill, not a user pipeline.
                workflows = {
                    skill.parent.name
                    for skill in (root / "skills").glob("*/SKILL.md")
                    if skill.parent.name != "privacy-surface-review"
                }
                coverage_hash = verify_coverage(
                    args.coverage_evidence, report["zip_sha256"], workflows
                )
            if report["environment"]["os"] != "Linux":
                raise ValueError(
                    "Release requires passing clean Linux Cowork package evidence"
                )
            verify_acceptance(args.cowork_acceptance, digest(args.zip), report)
            if args.promote_to:
                args.promote_to.parent.mkdir(parents=True, exist_ok=True)
                # Verify the staged bytes before atomically replacing any release.
                with tempfile.TemporaryDirectory(
                    dir=args.promote_to.parent
                ) as directory:
                    staged = Path(directory) / "candidate.zip"
                    shutil.copyfile(args.zip, staged)
                    if digest(staged) != report["zip_sha256"]:
                        raise ValueError("ZIP changed before promotion")
                    staged.replace(args.promote_to)
            write_json(
                output / "release-verification.json",
                {
                    "status": "pass",
                    "zip_sha256": report["zip_sha256"],
                    "plugin_version": report["plugin"]["version"],
                    "acceptance_sha256": digest(args.cowork_acceptance),
                    "coverage_sha256": coverage_hash,
                },
            )
            LOGGER.info("[PASS] Script and Cowork acceptance match this ZIP")
            return 0
        except (OSError, ValueError, KeyError, BadZipFile) as error:
            LOGGER.error("Release blocked: %s", error)
            return 1
    if args.promote_to:
        parser.error("--promote-to requires --verify-release")
    output.mkdir(parents=True, exist_ok=False)
    run = CheckRun(args.zip.resolve(), output, args.timeout)
    try:
        run.execute()
        if args.cowork_acceptance:
            verify_acceptance(
                args.cowork_acceptance, run.report["zip_sha256"], run.report
            )
            run.report["cowork_agent_acceptance"] = "pass"
    except (OSError, ValueError, KeyError, BadZipFile) as error:
        run.report["status"] = "fail"
        run.report["error"] = str(error)
        LOGGER.error("%s", error)
    finally:
        run.report["artifacts"] = evidence_index(output)
        write_json(output / "result.json", run.report)
    return 0 if run.report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
