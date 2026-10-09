"""Fixed packet, proposal and decision adapter over the maintained grant engine."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

__all__ = ["main"]

LIMIT = 2_000_000


def files(output: Path) -> dict:
    """Exact bytes, rather than semantic interpretation, govern mutation scope."""
    result = {}
    for path in sorted(output.rglob("*")):
        if path.is_symlink() or (path.is_file() and path.stat().st_nlink != 1):
            raise PermissionError("Grant authoring artifacts cannot be links")
        if path.is_file() and path.name != ".bandi-agevolazioni.lock":
            result[path.relative_to(output).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return result


def main() -> None:
    """No provider execution or professional confirmation is inferred here."""
    root = Path(sys.argv[1]).resolve()
    if root.name != "bandi-agevolazioni":
        raise PermissionError("Unsupported grant intelligence producer")
    sys.path.insert(0, str(root / "scripts"))
    from case_core import (
        load_client_engagement_context_file,
        load_running_context,
        require_run_artifact,
        safe_identifier,
    )
    from intelligence_contract import (
        CONTRACT_VERSION,
        IntelligenceTask,
        artifact_input_hashes,
        intelligence_packet_hash,
        validate_intelligence_output,
    )
    from intelligence_workflow import (
        _candidate_workbench,
        create_intelligence_packet,
        decide_intelligence,
        record_intelligence,
    )
    from schema_validation import validate_artifact_schema

    raw = sys.stdin.read(LIMIT + 1)
    if len(raw.encode("utf-8")) > LIMIT:
        raise ValueError("Complete grant intelligence request exceeds its limit")
    request = json.loads(raw)
    operation = request["operation"]
    if operation == "describe":
        result = {
            "tasks": [task.value for task in IntelligenceTask],
            "contract_version": CONTRACT_VERSION,
        }
    else:
        context_path = Path(request["context"])
        initial = load_client_engagement_context_file(
            context_path,
            expected_workflow_id="bandi-agevolazioni",
            allowed_statuses=("running",),
        )
        output = Path(initial["output_dir"])
        context = load_running_context(context_path, output_dir=output)
        before = files(output)
        if before != request["expected_files"]:
            raise ValueError("Grant intelligence inputs changed")
        common = {"output_dir": output, "client_engagement": context_path}
        if operation in {"packet", "validate"}:
            packet = create_intelligence_packet(
                **common,
                task=request["task"],
                subject_ids=request["subject_ids"],
                model_session_ref=request["model_session_ref"],
            )
            digest = intelligence_packet_hash(packet)
            result = {"packet": packet, "packet_sha256": digest}
            if operation == "validate":
                if digest != request["packet_sha256"]:
                    raise ValueError("Exact supplied grant packet changed")
                result["normalized_output"] = validate_intelligence_output(
                    packet, request["proposal"]
                )
        elif operation == "record":
            metadata = request["metadata"]
            if set(metadata) != {"provider", "model", "prompt_template_version"}:
                raise ValueError("Declare the exact model provenance")
            if metadata["prompt_template_version"] != CONTRACT_VERSION:
                raise ValueError("Use the maintained grant intelligence contract")
            result = record_intelligence(
                **common,
                task=request["task"],
                subject_ids=request["subject_ids"],
                model_session_ref=request["model_session_ref"],
                model_output=request["proposal"],
                expected_packet_sha256=request["packet_sha256"],
                recorded_by=request["recorded_by"],
                idempotency_key=request["idempotency_key"],
                **metadata,
            )
        elif operation in {"preflight_decide", "decide", "preflight_expire", "expire"}:
            values = request["fields"]
            if set(values) != {"decision", "reviewer_id", "reviewer_role", "notes"}:
                raise ValueError("Inspect and declare the exact intelligence decision")
            if any(
                not isinstance(value, str) or len(value) > 4000
                for value in values.values()
            ):
                raise ValueError("Declare bounded literal professional decision fields")
            safe_identifier(values["reviewer_id"], field="reviewer_id")
            if (
                values["decision"] not in {"accepted", "returned", "rejected"}
                or not values["reviewer_role"].strip()
            ):
                raise ValueError("Choose an explicit professional decision and role")
            register = require_run_artifact(
                output / "intelligence_register.json", run_id=context["run_id"]
            )
            runs = [
                row
                for row in register["runs"]
                if row["intelligence_run_id"] == request["intelligence_run_id"]
            ]
            if len(runs) != 1 or runs[0]["status"] != "MODEL_SUGGESTED":
                raise ValueError("Select one current undecided grant suggestion")
            intake = require_run_artifact(
                output / "case_intake.json", run_id=context["run_id"]
            )
            sources = require_run_artifact(
                output / "source_register.json", run_id=context["run_id"]
            )
            workbench = require_run_artifact(
                output / "application_workbench.json", run_id=context["run_id"]
            )
            stale = runs[0]["input_artifact_hashes"] != artifact_input_hashes(
                intake, sources, workbench
            )
            expiring = operation in {"preflight_expire", "expire"}
            if expiring and (not stale or values["decision"] != "returned"):
                raise ValueError(
                    "Only an obsolete suggestion can be explicitly marked stale"
                )
            if stale and not expiring:
                raise ValueError("Grant suggestion is stale; obtain a new contribution")
            if not expiring and values["decision"] == "accepted":
                # Reuse the producer's exact projection, not a second merge algorithm.
                candidate = _candidate_workbench(
                    workbench,
                    runs[0]["output"],
                    source_ids={row["source_id"] for row in sources["sources"]},
                )
                if validate_artifact_schema("application_workbench", candidate):
                    raise ValueError(
                        "Accepted proposal violates the public workbench schema"
                    )
            if operation in {"preflight_decide", "preflight_expire"}:
                result = {"status": "decision_valid", "public_writes": False}
            else:
                if request.get("confirmed") is not True:
                    raise ValueError("Confirm this exact grant suggestion decision")
                if expiring:
                    # The public producer durably marks changed inputs STALE before
                    # raising; recognize only that exact, verified transition.
                    try:
                        decide_intelligence(
                            **common,
                            intelligence_run_id=request["intelligence_run_id"],
                            confirmed_by_user=True,
                            **values,
                        )
                    except ValueError as error:
                        if (
                            str(error)
                            != "case inputs changed; intelligence run was marked STALE"
                        ):
                            raise
                    register = require_run_artifact(
                        output / "intelligence_register.json", run_id=context["run_id"]
                    )
                    selected = [
                        row
                        for row in register["runs"]
                        if row["intelligence_run_id"] == request["intelligence_run_id"]
                    ]
                    if len(selected) != 1 or selected[0]["status"] != "STALE":
                        raise ValueError("Public stale transition requires recovery")
                    result = selected[0]
                else:
                    result = decide_intelligence(
                        **common,
                        intelligence_run_id=request["intelligence_run_id"],
                        confirmed_by_user=True,
                        **values,
                    )
        elif operation == "source":
            sources = require_run_artifact(
                output / "source_register.json", run_id=context["run_id"]
            )
            selected = [
                row
                for row in sources["sources"]
                if row["source_id"] == request["source_id"]
            ]
            if len(selected) != 1:
                raise PermissionError("Choose one registered source from the mandate")
            row = selected[0]
            path = Path(context["run_root"]) / row["path"]
            load_running_context(context_path, output_dir=output, input_paths=[path])
            if path.is_symlink() or path.stat().st_nlink != 1:
                raise PermissionError("Selected grant source cannot be a link")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise ValueError("Selected grant source changed")
            if len(data) > LIMIT:
                raise ValueError(
                    "Selected source exceeds whole-source preview; use the exact registered original"
                )
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError:
                content = None
            result = {
                "source_id": row["source_id"],
                "path": str(path),
                "sha256": row["sha256"],
                "content": content,
                "untrusted_evidence": True,
                "binary_original_requires_supported_read": content is None,
            }
        else:
            raise ValueError("Unsupported grant intelligence operation")
        after = files(output)
        permitted = (
            {"intelligence_register.json"}
            if operation in {"record", "expire"}
            else (
                {"intelligence_register.json", "application_workbench.json"}
                if operation == "decide"
                else set()
            )
        )
        if any(
            before.get(name) != after.get(name)
            for name in (set(before) | set(after)) - permitted
        ):
            raise ValueError("Unexpected grant writes require ordinary recovery")
        result["files"] = after
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
