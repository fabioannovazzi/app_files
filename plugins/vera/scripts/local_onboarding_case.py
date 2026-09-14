#!/usr/bin/env python3
"""Prepare an isolated tutorial using the current workflow intake.

The user's archive configuration is unchanged. The native model selects inputs and the
specialist workflow; this adapter stages archive inputs or creates actual
hash-bound ledger contexts without bypassing the production input/output contract.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import secrets
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from local_onboarding import MARKER, OnboardingError, Store

__all__ = ["prepare_case", "main"]


def _ledger() -> ModuleType:
    vera = Path(__file__).resolve().parents[1]
    packaged = vera / "modules/studio-archive/scripts/client_ledger.py"
    source = vera.parent / "studio-archive/scripts/client_ledger.py"
    spec = importlib.util.spec_from_file_location(
        "vera_tutorial_ledger", packaged if packaged.is_file() else source
    )
    if spec is None or spec.loader is None:
        raise OnboardingError("The packaged Studio Archive ledger is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _archive() -> ModuleType:
    vera = Path(__file__).resolve().parents[1]
    packaged = vera / "modules/studio-archive/scripts/archive_core.py"
    source = vera.parent / "studio-archive/scripts/archive_core.py"
    spec = importlib.util.spec_from_file_location(
        "vera_tutorial_archive", packaged if packaged.is_file() else source
    )
    if spec is None or spec.loader is None:
        raise OnboardingError("The packaged Studio Archive is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _stage_archive_sources(sources: list[Path], root: Path, destination: Path) -> None:
    """Copy selected ordinary kit files while retaining their folder structure."""
    for source in sources:
        target = destination / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        before = hashlib.sha256(source.read_bytes()).digest()
        shutil.copyfile(source, target)
        if (
            hashlib.sha256(source.read_bytes()).digest() != before
            or hashlib.sha256(target.read_bytes()).digest() != before
        ):
            raise OnboardingError("A teaching source changed during staging")


def prepare_case(
    store: Store,
    *,
    thread_id: str,
    workflow: str,
    token: str,
    sources: list[Path],
    phase: str,
    source_root: Path | None = None,
) -> dict[str, Any]:
    """Stage archive search or start a ledger run beneath the local marker."""
    handoff = store.worker(thread_id, workflow, token)
    if not handoff["local_only"]:
        raise OnboardingError(
            "Use the specialist normal real-work intake, not the tutorial adapter"
        )
    if phase not in {"demo", "practice"} or not sources:
        raise OnboardingError(
            "A tutorial case needs demo/practice and selected source files"
        )
    if phase == "practice" and not handoff["lesson"].get("demo"):
        raise OnboardingError(
            "Explain and record the demonstration before preparing practice"
        )
    source_paths = [path.expanduser().absolute() for path in sources]
    if any(
        not path.is_file() or path.is_symlink() or path.resolve() != path
        for path in source_paths
    ):
        raise OnboardingError(
            "Select existing ordinary local files without symbolic links"
        )
    archive_source = None
    if workflow in {"studio-archive", "archive-organization"}:
        if source_root is None:
            raise OnboardingError("Archive teaching needs the prepared archive root")
        archive_source = source_root.expanduser().absolute()
        if (
            not archive_source.is_dir()
            or archive_source.resolve() != archive_source
            or any(
                not path.is_relative_to(archive_source)
                or len(path.relative_to(archive_source).parts)
                < (2 if workflow == "studio-archive" else 1)
                or path.relative_to(archive_source).parts[0].casefold() == "vera"
                for path in source_paths
            )
        ):
            raise OnboardingError(
                "Select only prepared files beneath their client folders"
            )
    elif source_root is not None:
        raise OnboardingError("An archive source root applies only to archive lessons")
    if workflow == "vouching" and (
        sum(path.suffix.lower() in {".csv", ".xlsx", ".xls"} for path in source_paths)
        != 1
        or not any(
            path.suffix.lower() in {".xml", ".zip", ".pdf"} for path in source_paths
        )
    ):
        raise OnboardingError(
            "Vouching teaching needs one CSV/Excel journal and selected invoice documents"
        )
    root = Path(handoff["lesson"]["directory"])
    if not (store.root / MARKER).is_file():
        raise OnboardingError(
            "Restore the enrollment's local-only marker before running a tutorial"
        )
    attempt = root / f"{phase}-{secrets.token_hex(8)}"
    case = (
        attempt / "archive" / "Teaching client" if workflow == "vouching" else attempt
    )
    case.mkdir(mode=0o700, parents=True)
    if archive_source is not None and workflow == "studio-archive":
        # Search indexes client folders, not a workflow's ledger input view.
        # Stage only the selected kit files; never configure the real archive.
        archive = case / "archive"
        _stage_archive_sources(source_paths, archive_source, archive)
        result = {
            "tutorial": True,
            "local_only": True,
            "phase": phase,
            "workflow_id": workflow,
            "archive_root": str(archive),
            "archive_state_dir": str(case / "private-index"),
            "archive_session_id": "tutorial-" + secrets.token_hex(12),
            "setup_required": True,
            "execution_receipt": False,
        }
        (case / "tutorial_case.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return result
    if workflow == "presenza-digitale-studio":
        # This specialist owns a website workspace, rather than a ledger run.
        inputs = case / "inputs"
        outputs = case / "outputs"
        inputs.mkdir()
        outputs.mkdir()
        records = []
        for index, source in enumerate(source_paths):
            target = inputs / f"{index + 1}-{source.name}"
            shutil.copyfile(source, target)
            records.append(
                {
                    "path": str(target),
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                }
            )
        result = {
            "tutorial": True,
            "local_only": True,
            "phase": phase,
            "workflow_id": workflow,
            "directory": str(case),
            "inputs": records,
            "output_dir": str(outputs),
            "status": "prepared",
        }
        (case / "tutorial_case.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return result
    if archive_source is not None:
        _stage_archive_sources(source_paths, archive_source, case)
    ledger = _ledger()
    client_id = "client_" + secrets.token_hex(12)
    ledger.create_client_manifest(case, client_id)
    engagement = ledger.create_engagement(
        case, client_id, f"Vera tutorial: {workflow} ({phase})"
    )
    engagement_id = engagement["engagement_id"]
    # These wrappers delegate to the same published intake component; exact IDs,
    # not a classifier of the user's professional request.
    ledger_workflow = (
        "client-file-preparation"
        if workflow
        in {
            "fatture-xml-check",
            "dati-fiscali-strutturati",
            "avviso-intake",
            "email-cliente",
        }
        else workflow
    )
    components = json.loads(
        (Path(__file__).parents[1] / "components.json").read_text(encoding="utf-8")
    )
    skill_components = {
        metadata["skill"]: component
        for component, metadata in components["workflow_roles"].items()
        if "skill" in metadata
    }
    ledger_workflow = skill_components.get(workflow, ledger_workflow)
    if workflow == "vouching":
        # Raw kit sources are not a prepared Vouching population. First run
        # actual Journal Sampling; its closed artifacts feed the later check.
        ledger_workflow = "journal-sampling"
    inputs = (
        [ledger.snapshot_client_folder(case, client_id, engagement_id)]
        if workflow == "archive-organization"
        else [
            ledger.import_document(
                case,
                client_id,
                engagement_id,
                source,
                (
                    "journal"
                    if ledger_workflow == "journal-sampling"
                    and source.suffix.lower() in {".csv", ".xlsx", ".xls"}
                    else (
                        "support"
                        if workflow == "vouching"
                        and source.suffix.lower() in {".xml", ".zip", ".pdf"}
                        else "source"
                    )
                ),
            )
            for source in source_paths
        ]
    )
    manifest = json.loads(
        (Path(__file__).parents[1] / ".codex-plugin/plugin.json").read_text(
            encoding="utf-8"
        )
    )
    run = ledger.prepare_run(
        case,
        client_id,
        engagement_id,
        ledger_workflow,
        manifest["version"],
        input_ids=[
            item["receipt"]["input_id"]
            for item in inputs
            if workflow != "vouching" or item["receipt"]["role"] != "support"
        ],
        purpose="Local Vera onboarding tutorial; no Mparanza transmission",
    )
    started = ledger.start_run(case, engagement_id, run["run"]["run_id"])
    result = {
        "tutorial": True,
        "local_only": True,
        "phase": phase,
        "workflow_id": workflow,
        "client_root": str(case),
        **started,
    }
    if workflow == "vouching":
        # The normal handoff resolves client IDs through an archive index.
        # This private tutorial index never changes the user's archive setup.
        state = attempt / "archive-state"
        _archive().configure_archive(case.parent, state_dir=state)
        result.update(
            prerequisite_workflow="journal-sampling",
            archive_state_dir=str(state),
            support_input_ids=[
                item["receipt"]["input_id"]
                for item in inputs
                if item["receipt"]["role"] == "support"
            ],
        )
    metadata = case / (
        "Vera/tutorial_case.json"
        if workflow == "archive-organization"
        else "tutorial_case.json"
    )
    result["tutorial_case_path"] = str(metadata)
    metadata.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    """Prepare selected local files for the active paired lesson."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument(
        "--session", help="Repeated teaching session; omit for onboarding"
    )
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--phase", choices=["demo", "practice"], required=True)
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args(argv)
    try:
        store = Store(args.state_root)
        if args.session:
            from local_teaching import TeachingStore

            store = TeachingStore(args.state_root, args.session)
        result = prepare_case(
            store,
            thread_id=args.thread_id,
            workflow=args.workflow,
            token=args.token,
            sources=args.source,
            phase=args.phase,
            source_root=args.source_root,
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0
    except (ValueError, OSError) as exc:
        sys.stdout.write(json.dumps({"status": "blocked", "error": str(exc)}) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
