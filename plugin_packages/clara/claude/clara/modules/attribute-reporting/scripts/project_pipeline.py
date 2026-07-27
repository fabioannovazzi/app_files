"""Development adapter for the existing app_files scrape and evidence pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _private_output_path(path: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve()
    for parent in (resolved, *resolved.parents):
        if (parent / ".git").exists():
            raise ValueError(f"{label} cannot be inside a Git workspace")
    return resolved


def _python_for_app(app_root: Path) -> Path:
    candidate = app_root / ".venv" / "bin" / "python"
    return candidate if candidate.is_file() else Path(sys.executable)


def _required_script(app_root: Path, name: str) -> Path:
    path = app_root / "scripts" / name
    if not path.is_file():
        raise FileNotFoundError(f"Required app script is missing: {path}")
    return path


def _run(
    command: list[str],
    *,
    app_root: Path,
    local_workspace: Path,
    receipt_path: Path,
    stage: str,
) -> int:
    local_workspace.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(app_root)
        if not existing_pythonpath
        else os.pathsep.join([str(app_root), existing_pythonpath])
    )
    started = datetime.now(timezone.utc).isoformat()
    LOGGER.info("Running existing %s stage in %s", stage, local_workspace)
    completed = subprocess.run(
        command,
        cwd=local_workspace,
        env=env,
        check=False,
        text=True,
    )
    receipt = {
        "schema_version": "attribute_reporting.project_stage_receipt.v1",
        "stage": stage,
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "execution_location": "local",
        "app_root": str(app_root),
        "local_workspace": str(local_workspace),
        "command": command,
        "exit_code": completed.returncode,
        "model_api_calls": False,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return completed.returncode


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--local-workspace", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="stage", required=True)

    discover = subparsers.add_parser("discover")
    discover.add_argument("--retailer", required=True)
    discover.add_argument("--category", required=True)
    discover.add_argument("--remote-url", default="http://127.0.0.1:9222")
    discover.add_argument("--max-pages", type=int, default=10)

    fetch = subparsers.add_parser("fetch-pdps")
    fetch.add_argument("--retailer", required=True)
    fetch.add_argument("--category", required=True)
    fetch.add_argument("--remote-url", default="http://127.0.0.1:9222")
    fetch.add_argument("--max-per-run", type=int, default=0)

    mapping = subparsers.add_parser("deterministic-map")
    mapping.add_argument("--retailer", required=True)
    mapping.add_argument("--category", required=True)

    package = subparsers.add_parser("build-package")
    package.add_argument("--retailer", required=True)
    package.add_argument("--category", required=True)
    package.add_argument("--output-root", type=Path, required=True)
    return parser


def main() -> int:
    """Run one existing deterministic/local pipeline stage."""

    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    app_root = args.app_root.expanduser().resolve()
    try:
        workspace = _private_output_path(
            args.local_workspace,
            label="local workspace",
        )
        receipt_path = _private_output_path(
            args.receipt,
            label="stage receipt",
        )
    except ValueError as exc:
        LOGGER.error("Project pipeline adapter failed: %s", exc)
        return 1
    python = str(_python_for_app(app_root))
    if args.stage == "discover":
        script = _required_script(app_root, "run_retailer_listing_discovery_cdp.py")
        discovery_root = workspace / "discovery"
        command = [
            python,
            str(script),
            "--retailer",
            args.retailer,
            "--categories",
            args.category,
            "--remote-url",
            args.remote_url,
            "--max-pages",
            str(args.max_pages),
            "--output-root",
            str(discovery_root),
            "--links-path",
            str(workspace / "links.json"),
            "--filter-evidence-root",
            str(workspace / "filter_evidence"),
            "--attribute-cache-root",
            str(workspace / "attribute_cache"),
        ]
    elif args.stage == "fetch-pdps":
        script = _required_script(app_root, "cdp_fetch_pdp.py")
        command = [
            python,
            str(script),
            "--retailer",
            args.retailer,
            "--categories",
            args.category,
            "--task-source",
            "latest-listing",
            "--remote-url",
            args.remote_url,
            "--max-per-run",
            str(args.max_per_run),
            "--links-path",
            str(workspace / "links.json"),
        ]
    elif args.stage == "deterministic-map":
        script = _required_script(app_root, "export_pdp_attributes.py")
        command = [
            python,
            str(script),
            "--retailer",
            args.retailer,
            "--category",
            args.category,
            "--deterministic-only",
            "--no-notify",
        ]
    else:
        script = _required_script(app_root, "build_retailer_category_evidence_pack.py")
        try:
            output_root = _private_output_path(
                args.output_root,
                label="evidence-package output",
            )
        except ValueError as exc:
            LOGGER.error("Project pipeline adapter failed: %s", exc)
            return 1
        command = [
            python,
            str(script),
            "--retailer",
            args.retailer,
            "--category",
            args.category,
            "--output-root",
            str(output_root),
        ]
    try:
        return _run(
            command,
            app_root=app_root,
            local_workspace=workspace,
            receipt_path=receipt_path,
            stage=args.stage,
        )
    except FileNotFoundError as exc:
        LOGGER.error("Project pipeline adapter failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
