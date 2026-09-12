#!/usr/bin/env python3
"""Prepare an isolated tutorial using the real portable Studio Archive ledger.

No archive configuration is changed. The native model selects inputs and the
specialist workflow; this adapter creates actual hash-bound contexts without
fabricating an engagement or bypassing the production input/output contract.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import secrets
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


def prepare_case(
    store: Store,
    *,
    thread_id: str,
    workflow: str,
    token: str,
    sources: list[Path],
    phase: str,
) -> dict[str, Any]:
    """Return a real started run, keeping every tutorial beneath its local marker."""
    handoff = store.worker(thread_id, workflow, token)
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
    root = Path(handoff["lesson"]["directory"])
    if not (store.root / MARKER).is_file():
        raise OnboardingError(
            "Restore the enrollment's local-only marker before running a tutorial"
        )
    case = root / f"{phase}-{secrets.token_hex(8)}"
    case.mkdir(mode=0o700)
    ledger = _ledger()
    client_id = "client_" + secrets.token_hex(12)
    ledger.create_client_manifest(case, client_id)
    engagement = ledger.create_engagement(
        case, client_id, f"Vera tutorial: {workflow} ({phase})"
    )
    engagement_id = engagement["engagement_id"]
    role = "journal" if workflow in {"journal-sampling", "check-entries"} else "source"
    inputs = [
        ledger.import_document(case, client_id, engagement_id, source, role)
        for source in source_paths
    ]
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
        input_ids=[item["receipt"]["input_id"] for item in inputs],
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
    (case / "tutorial_case.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    """Prepare selected local files for the active paired lesson."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--phase", choices=["demo", "practice"], required=True)
    parser.add_argument("--source", type=Path, action="append", required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare_case(
            Store(args.state_root),
            thread_id=args.thread_id,
            workflow=args.workflow,
            token=args.token,
            sources=args.source,
            phase=args.phase,
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0
    except (ValueError, OSError) as exc:
        sys.stdout.write(json.dumps({"status": "blocked", "error": str(exc)}) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
