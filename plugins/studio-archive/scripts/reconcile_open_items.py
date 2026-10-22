"""Import, calculate and deliver one explicitly selected reconciliation.

The agent supplies reviewed mappings; this operation owns the mechanical Archive
sequence. Repeating a request reopens its result without repeating calculation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import subprocess
import sys
from pathlib import Path
from typing import Any

__all__ = ["finish_reconciliation", "reconcile", "main"]

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import archive_core as archive  # noqa: E402


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _command(script: str, arguments: list[str], log: Path) -> dict[str, Any]:
    component = SCRIPTS.parent.parent / "open-item-reconciliation" / "scripts"
    product = SCRIPTS.parents[2]
    execution_root = None
    if (product / "scripts/verified_execution.py").is_file():
        sys.path.insert(0, str(product / "scripts"))
        from verified_execution import bind_execution_run, release_execution_root

        context = Path(arguments[arguments.index("--client-engagement") + 1])
        # Use the existing run lease so later review survives a plugin update.
        execution_root = bind_execution_run(context.parent, product)
        component = execution_root / "modules/open-item-reconciliation/scripts"
    try:
        with log.open("w", encoding="utf-8") as handle:
            # Fixed published component and Python; no shell or caller code.
            result = subprocess.run(  # nosec B603
                [sys.executable, "-I", "-B", str(component / script), *arguments],
                stdout=handle,
                stderr=subprocess.STDOUT,
                check=False,
            )
    finally:
        if execution_root is not None:
            release_execution_root(execution_root)
    if result.returncode:
        raise archive.ArchiveError(
            f"Reconciliation {script} failed; retained diagnostics: {log}"
        )
    # The producer's stdout is a local diagnostic, never an alternate source.
    return _json(log) if script == "audit_assurance.py" else {}


def _declarations(output: Path) -> list[dict[str, str]]:
    declarations = []
    for path in sorted(output.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(output).as_posix()
        declarations.append(
            {
                "artifact_id": "reconciliation-"
                + hashlib.sha256(relative.encode()).hexdigest()[:32],
                "path": relative,
                "purpose": f"Reconciliation workpaper or supporting record: {relative}",
                "audience": "review",
                "media_type": mimetypes.guess_type(path.name)[0]
                or "application/octet-stream",
            }
        )
    return declarations


def _delivery(loaded: dict[str, Any], terminal: dict[str, Any]) -> dict[str, Any]:
    output = Path(loaded["output_dir"])
    final = _json(output / "reconciliation/final_artifacts.json")
    reporting = terminal.get("reporting", {})
    warnings = []
    if (
        reporting.get("status") == "unavailable"
        or reporting.get("collection_status") == "incomplete"
    ):
        warnings.append(
            {
                "kind": "data_usage_reporting_incomplete",
                "message": "Data-usage measurement is incomplete; the accounting result is unchanged.",
                "report_path": str(output / "model_data_report.md"),
            }
        )
    ready = final.get("assurance", {}).get("report_ready", False)
    return {
        "status": terminal["status"],
        "accounting_status": "verified" if ready else "review_required",
        "report_ready": ready,
        "client_id": loaded["context"]["client_id"],
        "engagement_id": loaded["run"]["engagement_id"],
        "run_id": loaded["run"]["run_id"],
        "output_dir": str(output / "reconciliation"),
        "artifacts": [
            str(output / "reconciliation" / item["path"])
            for item in final["outputs"]
            if item.get("kind") in {"xlsx", "docx", "pdf"}
        ],
        "review_handoff": final.get("review_handoff"),
        "next_actions": final.get("next_actions", []),
        "reporting": reporting,
        "warnings": warnings,
    }


def finish_reconciliation(
    client_id: str, engagement_id: str, run_id: str, *, state_dir: Path | None = None
) -> dict[str, Any]:
    """Finish existing work, including an ordinarily reviewed/regenerated draft."""
    root = Path(
        archive.get_studio_client_folder(client_id, state_dir=state_dir)[
            "client_folder"
        ]["client_root"]
    )
    loaded = archive.ledger.load_run(root, engagement_id, run_id)
    if loaded["context"]["client_id"] != client_id:
        raise archive.ArchiveError("Selected run belongs to another client.")
    if loaded["run"]["workflow_id"] != "open-item-reconciliation":
        raise archive.ArchiveError("Selected run is not an open-item reconciliation.")
    output = Path(loaded["output_dir"])
    if loaded["run"]["status"] in {"completed", "ready_for_review"}:
        terminal = archive.complete_studio_client_workflow(
            client_id, engagement_id, run_id, state_dir=state_dir
        )
        return _delivery(loaded, terminal)
    if loaded["run"]["status"] != "running":
        raise archive.ArchiveError(
            f"Existing run is {loaded['run']['status']}; its evidence is retained."
        )
    # Keep replay diagnostics outside the sealed package. Reopening a review
    # draft never launches the producer or a semantic worker again.
    replay = _command(
        "audit_assurance.py",
        [
            "--client-engagement",
            str(loaded["context_path"]),
            "validate-run-json",
            str(output / "reconciliation"),
        ],
        output / "reconciliation-validation.json",
    )
    if not replay.get("ok"):
        raise archive.ArchiveError("Reconciliation assurance replay did not pass.")
    if not replay["assurance"]["report_ready"]:
        reported = archive.ledger._finish_terminal_reporting(loaded)
        return _delivery(
            loaded, {"status": "review_required", "reporting": reported["reporting"]}
        )
    if loaded["run"]["status"] == "running":
        archive.finalize_studio_client_workflow(
            client_id, engagement_id, run_id, _declarations(output), state_dir=state_dir
        )
    terminal = archive.complete_studio_client_workflow(
        client_id, engagement_id, run_id, state_dir=state_dir
    )
    return _delivery(loaded, terminal)


def reconcile(
    request: dict[str, Any], *, state_dir: Path | None = None
) -> dict[str, Any]:
    """Run the public workflow once, with explicit sources and reviewed mappings."""
    client_id, engagement_id = request["client_id"], request["engagement_id"]
    request_id = request["request_id"]
    if not isinstance(request_id, str) or not request_id.strip():
        raise archive.ArchiveError("A stable request_id is required for resumption.")
    if not request["sources"]:
        raise archive.ArchiveError("Select the reconciliation sources.")
    mappings = {}
    input_ids = []
    for source in request["sources"]:
        mapping = source["mapping"]
        imported = archive.import_studio_client_document(
            client_id,
            Path(source["path"]),
            "source",
            engagement_id=engagement_id,
            expected_sha256=source.get("sha256"),
            state_dir=state_dir,
        )
        receipt = imported["input_receipt"]
        relative = f"imports/{receipt['input_id']}/{receipt['stored_name']}"
        if relative in mappings and mappings[relative] != mapping:
            raise archive.ArchiveError("The same source has conflicting mappings.")
        mappings[relative] = mapping
        if imported["input_id"] not in input_ids:
            input_ids.append(imported["input_id"])
    prepared = archive.prepare_studio_client_workflow(
        engagement_id,
        "open-item-reconciliation",
        input_ids=input_ids,
        label=request.get("title"),
        purpose=request.get("purpose"),
        idempotency_key=request_id,
        state_dir=state_dir,
    )
    if prepared["client_id"] != client_id:
        raise archive.ArchiveError("Selected engagement belongs to another client.")
    run_id = prepared["run"]["run_id"]
    output = Path(prepared["client_engagement"]["output_dir"])
    retained_request = output / "reconciliation-request.json"
    if retained_request.exists() and _json(retained_request) != request:
        raise archive.ArchiveError(
            "This request_id already has different mappings or settings; select a new request_id."
        )
    if prepared["run"]["status"] != "prepared":
        return finish_reconciliation(
            client_id, engagement_id, run_id, state_dir=state_dir
        )
    archive.start_studio_client_workflow(
        client_id, engagement_id, run_id, state_dir=state_dir
    )
    try:
        retained_request.write_text(
            json.dumps(request, indent=2) + "\n", encoding="utf-8"
        )
        assumptions = {
            **request.get("assumptions", {}),
            "reviewed_source_decisions": mappings,
        }
        assumptions_path = output / "reconciliation-assumptions.json"
        assumptions_path.write_text(
            json.dumps(assumptions, indent=2) + "\n", encoding="utf-8"
        )
        _command(
            "raw_input_runner.py",
            [
                "--client-engagement",
                prepared["client_engagement_path"],
                "--assumptions-json",
                str(assumptions_path),
                "--output-subdirectory",
                "reconciliation",
                "--language",
                request.get("language", "it"),
                "--title",
                request.get("title", "Riconciliazione partite"),
                "--narrative",
                request.get("narrative", ""),
            ],
            output / "reconciliation-execution.log",
        )
        return finish_reconciliation(
            client_id, engagement_id, run_id, state_dir=state_dir
        )
    except Exception as exc:
        archive.fail_studio_client_workflow(
            client_id, engagement_id, run_id, str(exc), state_dir=state_dir
        )
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument(
        "--finish-run", help="Resume delivery after ordinary review/regeneration."
    )
    args = parser.parse_args()
    request = _json(args.request)
    if args.finish_run:
        result = finish_reconciliation(
            request["client_id"],
            request["engagement_id"],
            args.finish_run,
            state_dir=args.state_dir,
        )
    else:
        result = reconcile(request, state_dir=args.state_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
