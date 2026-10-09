"""Isolated complete SARI proposals through unchanged source/validation/package producers."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Keep model interpretation and human selection outside mechanical public writers."""
    root = Path(sys.argv[1])
    if root.name != "registro-imprese-sari":
        raise PermissionError("Unsupported registry authoring producer")
    sys.path.insert(0, str(root / "scripts"))
    from case_core import (
        load_client_engagement_context_file,
        load_running_case_context,
        sha256_file,
        write_private_json,
    )
    from package_practice import package_practice
    from register_official_source import register_source
    from validate_practice_case import validate_practice_case

    raw = sys.stdin.read(200_001)
    if len(raw.encode()) > 200_000:
        raise ValueError("Complete registry proposal exceeds the bridge limit")
    request = json.loads(raw)
    context = load_client_engagement_context_file(
        Path(request["context"]),
        expected_workflow_id=root.name,
        allowed_statuses=("running",),
    )
    output = Path(context["output_dir"])
    load_running_case_context(Path(request["context"]), output_dir=output)
    proposal = request["proposal"]
    if set(proposal) != {"case_intake", "practice_plan", "sources"}:
        raise ValueError("Use the complete public intake, plan and source proposal")
    intake, plan = proposal["case_intake"], proposal["practice_plan"]
    original = json.loads((output / "case_intake_draft.json").read_bytes())
    for value in (intake, plan):
        if value["plugin"] != root.name or value["run_id"] != context["run_id"]:
            raise PermissionError("Registry proposal belongs to another run")
    for key in ("reference_date", "client_reference", "jurisdiction"):
        if intake[key] != original[key]:
            raise ValueError("Model cannot change the confirmed initial parameters")
    if plan["jurisdiction"] != intake["jurisdiction"]:
        raise ValueError("Plan jurisdiction must match the independently selected case")
    for name, value in (("case_intake", intake), ("practice_plan", plan)):
        schema = json.loads((root / "schemas" / (name + ".schema.json")).read_bytes())
        if set(value) - set(schema["properties"]):
            raise ValueError("Proposal contains fields outside the public schema")
    for section, key in (
        ("competent_chamber", "confirmation_status"),
        ("subject", "confirmation_status"),
        ("activity", "classification_status"),
        ("requested_operation", "confirmation_status"),
    ):
        if intake[section][key] == "confirmed":
            raise PermissionError(
                "Model cannot attest a professional case confirmation"
            )
    review = plan["professional_review"]
    if review["status"] != "pending" or any(
        review.get(key) not in (None, "")
        for key in ("reviewer_id", "reviewer_role", "reviewed_at", "notes")
    ):
        raise PermissionError("Model professional decisions must remain pending")
    for key in (
        "classification_proposals",
        "position_matrix",
        "dire_steps",
        "required_documents",
        "application_fields",
        "risks",
        "missing_information",
    ):
        for item in plan[key]:
            if (
                item["review_status"] == "confirmed"
                or item.get("confirmation") is not None
            ):
                raise PermissionError("Model cannot create a professional confirmation")
    sources = proposal["sources"]
    if not isinstance(sources, list) or not 1 <= len(sources) <= 50:
        raise ValueError("Propose one to fifty complete official-source records")
    required = {
        "source_id",
        "source_type",
        "title",
        "official_url",
        "publisher",
        "territorial_applicability",
    }
    allowed = required | {"updated_date", "snapshot_input_id"}
    if any(
        not isinstance(row, dict) or required - set(row) or set(row) - allowed
        for row in sources
    ):
        raise ValueError("Invalid proposed source fields")
    if len({row["source_id"] for row in sources}) != len(sources):
        raise ValueError("Proposed official-source identities must be unique")
    registered = {Path(row["path"]): row["sha256"] for row in context["input_bindings"]}
    selected = {row["input_id"]: row for row in request["selected_inputs"]}
    for row in selected.values():
        path = Path(row["path"])
        if registered.get(path) != row["sha256"] or sha256_file(path) != row["sha256"]:
            raise PermissionError("Registry original is outside the unchanged mandate")
    snapshots = {}
    for row in sources:
        identifier = row.get("snapshot_input_id")
        if identifier is not None:
            if identifier not in selected:
                raise PermissionError(
                    "Source copy was not selected in the exact mandate"
                )
            snapshots[row["source_id"]] = Path(selected[identifier]["path"])
    if request["operation"] == "preview":
        destination = Path(request["destination"])
        if destination.exists() or destination.is_symlink():
            raise ValueError("Registry staged preview must be a new private directory")
        shutil.copytree(output, destination)
        destination.chmod(0o700)
        selected_by = "model_proposal_for_human_selection"
    elif request["operation"] == "register":
        if set(request["source_ids"]) != {row["source_id"] for row in sources} or len(
            request["source_ids"]
        ) != len(sources):
            raise PermissionError(
                "Explicitly select every source used by this complete proposal"
            )
        selected_by = request["reviewer"]
        if (
            not isinstance(selected_by, str)
            or not selected_by.strip()
            or len(selected_by) > 120
        ):
            raise ValueError("Declare the actual person selecting the sources")
        destination = output
    else:
        raise ValueError("Unsupported registry authoring operation")
    write_private_json(destination / "case_intake_draft.json", intake)
    write_private_json(destination / "practice_plan_draft.json", plan)
    for row in sources:
        snapshot = snapshots.get(row["source_id"])
        register_source(
            output_dir=destination,
            run_id=context["run_id"],
            **{key: row[key] for key in required},
            updated_date=row.get("updated_date"),
            snapshot=snapshot,
            authorization_basis=(
                "user_provided_copy" if snapshot else "browser_assisted_metadata"
            ),
            authorization_reference=request["grant_ref"],
            selected_by=selected_by,
        )
    audit = validate_practice_case(
        destination / "case_intake_draft.json",
        destination / "practice_plan_draft.json",
        destination / "official_sources.json",
        destination,
        local_inventory_path=destination / "local_evidence_inventory.json",
    )
    final = package_practice(destination) if audit["status"] != "schema_error" else None
    result = {
        "audit": audit,
        "final_artifacts": final,
        "public_outputs_registered": request["operation"] == "register",
        "network_calls_performed": False,
        "actual_model_reads_verified": False,
    }
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
