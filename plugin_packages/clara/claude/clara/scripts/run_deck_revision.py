"""Resume mechanical deck-revision preparation using existing canonical helpers."""

from __future__ import annotations

# Direct CLI calls must select dependencies before importing workflow modules.
if __name__ == "__main__":
    import runpy as _runpy
    from pathlib import Path as _Path

    for _parent in _Path(__file__).resolve().parents:
        _launcher = _parent / "scripts" / "self_relaunch.py"
        if not _launcher.is_file():
            _launcher = _parent / "clara" / "scripts" / "self_relaunch.py"
        if _launcher.is_file():
            _runpy.run_path(str(_launcher))["ensure_running_in_managed_venv"](__file__)
            break
    else:
        # Standalone components retain their host's dependency setup.
        if any(
            (_p / "components.json").is_file()
            for _p in _Path(__file__).resolve().parents
        ):
            raise SystemExit(
                "Managed Python launcher is missing; rebuild the plugin package."
            )


import argparse
import hashlib
import json
import logging
from dataclasses import fields
from pathlib import Path
from typing import Any, Callable

from advisor_case_core import CaseWorkspaceError, validate_case_workspace
from analyze_deck_revision_materials import analyze_deck_revision_materials
from apply_deck_revision_plan import apply_deck_revision_plan
from build_deck_revision_execution_packets import build_deck_revision_execution_packets
from build_deck_revision_execution_plan import build_deck_revision_execution_plan
from build_deck_revision_interpretation_packets import (
    build_deck_revision_interpretation_packets,
)
from build_deck_revision_workbench import build_deck_revision_workbench
from case_store import atomic_text, transaction
from complete_deck_revision_output_review import (
    _verified_output_review,
    verify_deck_revision_output_review,
)
from finalize_deck_revision_plan import finalize_deck_revision_plan

__all__ = ["run_deck_revision", "main"]
LOGGER = logging.getLogger(__name__)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CaseWorkspaceError(f"Expected object: {path}")
    return value


def _hashes(paths: list[Path]) -> dict[str, str | None]:
    result = {}
    for path in paths:
        if not path.is_file():
            result[str(path)] = None
            continue
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        result[str(path)] = digest.hexdigest()
    return result


def run_deck_revision(
    case_dir: Path, *, voice_session: Path, apply_approved: bool = False
) -> dict[str, Any]:
    """Regenerate views by exact dependency identity; never invent interpretation or approval."""
    case_dir = case_dir.resolve()
    errors = validate_case_workspace(case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))
    session = (case_dir / voice_session).resolve()
    if not session.is_relative_to(case_dir / "voice_sessions") or not session.is_dir():
        raise CaseWorkspaceError("An existing case-owned voice session is required")
    receipt = session / "deck_revision_runner.json"
    with transaction(case_dir):
        state = (
            _read(receipt) if receipt.is_file() else {"schema_version": 1, "stages": {}}
        )
        state["status"] = "preparing"
        state["semantic_review_performed"] = False
        state["interpretation_stale"] = False
        state.pop("missing_material", None)
        state.pop("material_needs", None)
        state.pop("final_review_error", None)

        def step(
            name: str,
            function: Callable[..., Any],
            dependencies: list[Path],
            **kwargs: Any,
        ) -> list[Path]:
            # Exact cache identity is mechanical; no semantic stage selection occurs here.
            code = Path(__file__).parent / f"{function.__name__}.py"
            identity = _hashes([*dependencies, code, Path(__file__)])
            previous = state["stages"].get(name, {})
            outputs = [Path(path) for path in previous.get("outputs", {})]
            if (
                outputs
                and previous.get("inputs") == identity
                and _hashes(outputs) == previous["outputs"]
                and all(value is not None for value in previous["outputs"].values())
            ):
                return outputs
            result = function(case_dir, voice_session=session, **kwargs)
            outputs = []
            for field in fields(result):
                value = getattr(result, field.name)
                # The finalizer replaces the initial workbench review template;
                # only that finalizer owns its identity after interpretation.
                if name == "workbench" and field.name == "review_path":
                    continue
                if not isinstance(value, Path) or field.name == "session_dir":
                    continue
                outputs.extend(sorted(value.rglob("*")) if value.is_dir() else [value])
            outputs = [path for path in outputs if path.is_file()]
            if _hashes([*dependencies, code, Path(__file__)]) != identity:
                raise CaseWorkspaceError(
                    "Deck preparation inputs changed while generating views"
                )
            state["stages"][name] = {"inputs": identity, "outputs": _hashes(outputs)}
            atomic_text(receipt, json.dumps(state, indent=2) + "\n")
            return outputs

        intake_path = session / "deck_revision_intake.json"
        if not intake_path.is_file():
            state.update(
                status="intake_required",
                next_action="Run prepare_voice_deck_revision.py against the current deck and attributed transcript.",
            )
        else:
            intake = _read(intake_path)
            dependencies = [intake_path, case_dir / "case_manifest.json"]
            for section, keys in {
                "speaker_attribution": ["attributed_transcript_path"],
                "deck": ["path", "snapshot_path"],
                "deck_style": ["snapshot_path", "spec_path"],
                "evidence": [
                    "feedback_timeline_path",
                    "video_timeline_path",
                    "screen_video_path",
                    "raw_transcript_path",
                ],
                "company_profile": ["path"],
            }.items():
                for key in keys:
                    raw = intake.get(section, {}).get(key)
                    if raw:
                        dependencies.append((case_dir / raw).resolve())
            workbench = step("workbench", build_deck_revision_workbench, dependencies)
            packets = step(
                "interpretation_packets",
                build_deck_revision_interpretation_packets,
                workbench,
            )
            changes = session / "deck_revision_changes.json"
            previous_inputs = (
                state["stages"].get("normalized_plan", {}).get("inputs", {})
            )
            current_evidence = _hashes([*workbench, *packets])
            interpretation_stale = (
                bool(previous_inputs)
                and previous_inputs.get(str(changes))
                == _hashes([changes])[str(changes)]
                and any(
                    previous_inputs.get(path) != digest
                    for path, digest in current_evidence.items()
                )
            )
            if not changes.is_file() or interpretation_stale:
                state.update(
                    status="interpretation_required",
                    next_action="Inspect interpretation packets and author deck_revision_changes.json from the feedback evidence.",
                    interpretation_stale=interpretation_stale,
                )
            else:
                normalized = step(
                    "normalized_plan",
                    finalize_deck_revision_plan,
                    [changes, *workbench, *packets],
                    changes_path=changes,
                )
                plan = step(
                    "execution_plan", build_deck_revision_execution_plan, normalized
                )
                quote = session / "deck_revision_quote_candidate_matrix.json"
                step(
                    "execution_packets",
                    build_deck_revision_execution_packets,
                    [*normalized, *plan, *workbench, quote],
                )
                # Approval and missing materials must be evaluated fresh, including revoked approval.
                needs = analyze_deck_revision_materials(case_dir, voice_session=session)
                payload = _read(needs.needs_path)
                status = payload["summary"]["status"]
                actions = {
                    "ready_for_auto_apply": "Run apply_deck_revision_plan.py, then render and review the exact output.",
                    "ready_for_approval": "Review deck_revision_understanding.md with the user and record the existing authorized approval.",
                    "no_changes": "Review whether the feedback requires any changes.",
                    "partial_or_manual_work_required": "Resolve the listed material gaps or execute the model-assisted packets before application.",
                }
                state.update(
                    status=status,
                    next_action=actions[status],
                    material_needs=str(needs.needs_path),
                    missing_material=[
                        {"change_id": item["change_id"], "missing": item["missing"]}
                        for item in payload["changes"]
                        if item["missing"]
                    ],
                )
                review_path = session / "deck_revision_output_review.json"
                external_review = (
                    review_path.is_file()
                    and _read(review_path).get("execution_mode")
                    == "registered_external_output"
                )
                if external_review:
                    # Never overwrite an external edit while reconciling its exact identities.
                    try:
                        _verified_output_review(case_dir, review_path)
                    except CaseWorkspaceError as error:
                        state["status"] = "external_output_review_stale"
                        state["final_review_error"] = str(error)
                        state["next_action"] = (
                            "Review current approval and re-register the external deck; its bytes have been preserved."
                        )
                    else:
                        state["status"] = "external_output_pending_review"
                        state["next_action"] = (
                            "Render and review the registered external deck, then complete its exact-output review."
                        )
                        if (
                            session / "deck_revision_output_review_completion.json"
                        ).is_file():
                            try:
                                verify_deck_revision_output_review(
                                    case_dir, voice_session=session
                                )
                            except CaseWorkspaceError as error:
                                state["final_review_error"] = str(error)
                            else:
                                state["status"] = "final_review_record_current"
                                state["next_action"] = (
                                    "Use the reviewed output in the advisory delivery gate when applicable."
                                )
                elif status == "ready_for_auto_apply" and apply_approved:
                    step(
                        "application",
                        apply_deck_revision_plan,
                        [
                            *normalized,
                            *workbench,
                            session / "deck_revision_approval.json",
                            *dependencies,
                        ],
                    )
                    applied = _read(session / "deck_revision_apply_report.json")
                    state["status"] = applied["summary"]["status"]
                    state["next_action"] = (
                        "Inspect the apply and verification reports; render the corrected deck and complete its exact-output review."
                    )
                    completion = session / "deck_revision_output_review_completion.json"
                    if completion.is_file():
                        try:
                            verify_deck_revision_output_review(
                                case_dir, voice_session=session
                            )
                        except CaseWorkspaceError as error:
                            state["final_review_error"] = str(error)
                        else:
                            state["status"] = "final_review_record_current"
                            state["next_action"] = (
                                "Use the reviewed output in the advisory delivery gate when applicable."
                            )
        atomic_text(receipt, json.dumps(state, indent=2) + "\n")
        return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--voice-session", type=Path, required=True)
    parser.add_argument(
        "--apply-approved",
        action="store_true",
        help="Apply only a current approved automatic plan; never create approval or review confirmations.",
    )
    args = parser.parse_args()
    state = run_deck_revision(
        args.case_dir,
        voice_session=args.voice_session,
        apply_approved=args.apply_approved,
    )
    LOGGER.info("%s: %s", state["status"], state["next_action"])
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
