"""Record advisory legal/tax model preferences without choosing or calling a model.

Model capability is a host/user-informed judgment. Model identity never gates work. Code preserves evidence, revisions and run
ownership for auditability, including when the model or conversation changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["apply_request", "main"]

ROOT = Path(__file__).resolve().parents[1]
for vendor in (
    ROOT / "vendor" / "modules",
    ROOT.parent.parent / "vendor" / "modules",
    ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (vendor / "vera_assurance").is_dir():
        sys.path.insert(0, str(vendor))
        break

from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

FILENAME = "legal_tax_model.json"
PHASES = {
    "preparation",
    "research",
    "drafting",
    "validation",
    "opposing_opinion",
    "revision",
}


def _text(value: Any, name: str, limit: int = 1000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"Invalid {name}")
    return value.strip()


def _bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _safe_file(root: Path, name: str) -> Path:
    target = root / name
    for ancestor in (target, *target.parents):
        if ancestor.is_symlink():
            raise ValueError("Symlink model-policy path rejected")
    return target


def _read(root: Path, run_id: str) -> dict[str, Any] | None:
    file = _safe_file(root, FILENAME)
    if not file.exists():
        return None
    if not file.is_file() or file.stat().st_size > 1_000_000:
        raise ValueError("Invalid model-policy record")
    value = json.loads(file.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != "vera.legal_tax_model.v1"
        or value.get("run_id") != run_id
    ):
        raise ValueError("Model-policy record belongs to another run")
    required = value.get("preferred_model")
    if required is not None:
        _text(required, "preferred_model", 160)
    advisory = value.get("enforcement") == "advisory"
    for field, limit in (("host", 80), ("session_ref", 240), ("selection_basis", 3000)):
        _text(value.get(field), field, limit)
    identity = value.get("identity_basis")
    active = value.get("active_model")
    if identity == "host_reported":
        _text(active, "active_model", 160)
        _text(value.get("observation_reference"), "observation_reference", 3000)
        expected = (
            "ready_host_reported"
            if advisory or active == required
            else "requires_switch"
        )
    elif identity == "user_confirmed":
        if (not advisory and active != required) or value.get(
            "confirmation_source"
        ) not in {
            "plugin_ui",
            "chat",
        }:
            raise ValueError("Invalid user-confirmed model identity")
        _text(value.get("confirmation_reference"), "confirmation_reference", 3000)
        expected = "ready_user_confirmed"
    elif identity == "unknown" and active is None:
        expected = "ready_unknown" if advisory else "awaiting_confirmation"
    else:
        raise ValueError("Invalid model identity evidence")
    if (
        value.get("status") != expected
        or value.get("policy") != "most_capable_available"
        or not isinstance(value.get("phases"), list)
    ):
        raise ValueError("Inconsistent model-policy record")
    return value


def _write(root: Path, record: dict[str, Any], previous: dict[str, Any] | None) -> None:
    if previous:
        history = _safe_file(root, "model-policy-history")
        history.mkdir(exist_ok=True)
        old = _safe_file(history, _digest(previous) + ".json")
        if not old.exists():
            with old.open("xb") as stream:
                stream.write(_bytes(previous))
    temporary = _safe_file(root, f".model-policy-{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(_bytes(record))
        os.replace(temporary, _safe_file(root, FILENAME))
    finally:
        temporary.unlink(missing_ok=True)


def _apply(request: dict[str, Any], root: Path, run_id: str) -> dict[str, Any]:
    action = request["action"]
    previous = _read(root, run_id)
    now = datetime.now(timezone.utc).isoformat()
    if action == "prepare":
        host = _text(request.get("host"), "host", 80)
        required = request.get("preferred_model")
        if required is not None:
            required = _text(required, "preferred_model", 160)
        session = _text(request.get("session_ref"), "session_ref", 240)
        basis = _text(
            request.get(
                "selection_basis",
                "No capability recommendation available; continue with the current host model.",
            ),
            "selection_basis",
            3000,
        )
        language = request.get("language", "en")
        if language not in {"it", "en", "fr", "de", "es"}:
            raise ValueError("Unsupported language")
        observed = request.get("observed_model")
        if observed is not None:
            observed = _text(observed, "observed_model", 160)
            _text(request.get("observation_reference"), "observation_reference", 3000)
        # Reopening the same check must not erase a real confirmation or phase history.
        same = previous and all(
            previous.get(k) == v
            for k, v in (
                ("host", host),
                ("preferred_model", required),
                ("session_ref", session),
                ("selection_basis", basis),
            )
        )
        if same and (observed is None or observed == previous.get("active_model")):
            record = previous
        else:
            record = {
                "schema_version": "vera.legal_tax_model.v1",
                "run_id": run_id,
                "policy": "most_capable_available",
                "enforcement": "advisory",
                "host": host,
                "preferred_model": required,
                "selection_basis": basis,
                "session_ref": session,
                "language": language,
                "active_model": observed,
                "identity_basis": "host_reported" if observed else "unknown",
                "observation_reference": (
                    request.get("observation_reference") if observed else None
                ),
                "status": ("ready_host_reported" if observed else "ready_unknown"),
                "phases": (
                    json.loads(json.dumps(previous["phases"])) if previous else []
                ),
                "updated_at": now,
                "previous_sha256": _digest(previous) if previous else None,
            }
    else:
        if previous is None:
            raise ValueError("Prepare the model record first")
        record = json.loads(json.dumps(previous))
        if action in {"confirm", "phase"}:
            if request.get("expected_sha256") != _digest(previous):
                raise ValueError("Stale model check; reload before continuing")
            session = _text(request.get("session_ref"), "session_ref", 240)
        if action == "confirm":
            if request.get("confirmation_source") not in {"plugin_ui", "chat"}:
                raise ValueError("An explicit UI or chat confirmation is required")
            confirmed = _text(request.get("confirmed_model"), "confirmed_model", 160)
            record.update(
                {
                    "active_model": confirmed,
                    "session_ref": session,
                    "identity_basis": "user_confirmed",
                    "status": "ready_user_confirmed",
                    "observation_reference": None,
                    "confirmation_source": request["confirmation_source"],
                    "confirmation_reference": _text(
                        request.get("confirmation_reference"),
                        "confirmation_reference",
                        3000,
                    ),
                    "updated_at": now,
                }
            )
        elif action == "phase":
            phase = request.get("phase")
            if phase not in PHASES:
                raise ValueError("Unsupported legal/tax phase")
            model = request.get("model")
            if model is not None:
                model = _text(model, "model", 160)
            same_identity = (
                session == previous["session_ref"] and model == previous["active_model"]
            )
            identity = previous["identity_basis"] if same_identity else "unknown"
            observation = request.get("observation_reference")
            if observation is not None and model is not None:
                _text(observation, "observation_reference", 3000)
                identity = "host_reported"
            if not same_identity:
                record.update(
                    session_ref=session,
                    active_model=None,
                    identity_basis="unknown",
                    observation_reference=None,
                )
                record.pop("confirmation_reference", None)
                record.pop("confirmation_source", None)
            if identity == "host_reported":
                record.update(
                    active_model=model,
                    identity_basis=identity,
                    observation_reference=observation
                    or previous["observation_reference"],
                )
            record["phases"].append(
                {
                    "phase": phase,
                    "model": model,
                    "identity_basis": identity,
                    "session_ref": session,
                    "execution_reference": _text(
                        request.get("execution_reference"), "execution_reference", 3000
                    ),
                    "recorded_at": now,
                }
            )
            record["updated_at"] = now
        elif action != "read":
            raise ValueError("Unknown model-policy action")
    # Reading a finalized run must not invalidate its saved artifact receipts.
    # Legacy statuses are historical evidence; they never gate continuation.
    if action != "read":
        record = json.loads(json.dumps(record))
        record["enforcement"] = "advisory"
        record["status"] = {
            "host_reported": "ready_host_reported",
            "user_confirmed": "ready_user_confirmed",
            "unknown": "ready_unknown",
        }[record["identity_basis"]]
        if record != previous:
            _write(root, record, previous)
    return {
        "ok": True,
        "record": record,
        "sha256": _digest(record),
        "can_continue": True,
        "enforcement": "advisory",
        "model_selection_required": False,
        "path": str(root / FILENAME),
        "host_switch_performed": False,
    }


def apply_request(request: dict[str, Any]) -> dict[str, Any]:
    """Validate the existing managed run; UI and Cowork use this same contract."""
    if not isinstance(request, dict) or request.get("action") not in {
        "prepare",
        "read",
        "confirm",
        "phase",
    }:
        raise ValueError("Invalid model-policy request")
    workflow = request.get("workflow_id", "prompt-optimizer")
    if workflow not in {"prompt-optimizer", "deep-research-validator"}:
        raise ValueError("Model policy is limited to the legal/tax pipeline")
    root = Path(_text(request.get("output_dir"), "output_dir", 4096)).absolute()
    _safe_file(root, FILENAME)
    context = load_client_engagement_context_file(
        Path(_text(request.get("client_engagement"), "client_engagement", 4096)),
        expected_workflow_id=workflow,
        input_paths=[],
        output_dir=root,
        allowed_statuses=(
            ("running", "ready_for_review", "completed")
            if request["action"] == "read"
            else ("running",)
        ),
    )
    if request.get("run_id") != context["run_id"]:
        raise ValueError("Model check run identity mismatch")
    if request["action"] == "read":
        return _apply(request, root, context["run_id"])
    root.mkdir(parents=True, exist_ok=True)
    lock = _safe_file(root, ".model-policy.lock")
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise ValueError(
            "Model check is being updated; reload before retrying"
        ) from exc
    try:
        return _apply(request, root, context["run_id"])
    finally:
        lock.rmdir()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, help="JSON request; omit to read stdin")
    args = parser.parse_args(argv)
    try:
        raw = (
            args.request.read_text(encoding="utf-8")
            if args.request
            else sys.stdin.buffer.read(50_001).decode("utf-8")
        )
        if len(raw) > 50_000:
            raise ValueError("Model-policy request too large")
        result = apply_request(json.loads(raw))
    except (OSError, ValueError, AssuranceContractError) as exc:
        parser.error(str(exc))
    # ASCII JSON escapes preserve Unicode even on hosts with a legacy stdio codec.
    sys.stdout.write(json.dumps(result, ensure_ascii=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
