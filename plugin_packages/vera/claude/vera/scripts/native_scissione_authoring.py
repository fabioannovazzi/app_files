"""Fixed public Scissione adapter for shared literal-source mandates.

Only byte membership, lineage and exact public artifact shapes are deterministic.
The model proposes the operation, facts, materiality and applicable source basis.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash
from native_scissione import FILES, engine_call

__all__ = ["artifact_names", "catalogue", "inspect", "published_scope_matches"]


def artifact_names(reference: str) -> set[str]:
    """Preserve the actual public version and original execution request."""
    return {"scissione_versions/" + reference + "/" + name for name in FILES} | {
        "scissione-native-proposal-" + reference + ".json"
    }


def catalogue(root: Path, binding: dict, loaded: dict, api: Any) -> dict:
    from native_scissione import catalogue as versions

    current = versions(root, binding, loaded, api)
    reference = current["current"]
    path = (
        Path(loaded["output_dir"]) / "scissione_versions" / reference / "revision.json"
        if reference
        else None
    )
    return {
        **current,
        "case_scope": (
            {"revision_sha256": reference, "path": str(path), "sha256": file_hash(path)}
            if path
            else None
        ),
    }


def published_scope_matches(base: Path, value: dict, current: dict, api: Any) -> bool:
    """An exact successful retry may reopen its own conserved case, not a foreign successor."""
    old = {k: v for k, v in value["identity"].items() if k != "case_scope"}
    fresh = {k: v for k, v in current["identity"].items() if k != "case_scope"}
    state = api.read_json(base / "state.json") if (base / "state.json").exists() else {}
    case_scope = current["identity"]["case_scope"]
    return (
        old == fresh
        and case_scope is not None
        and any(
            row["result"]["source_ref"] == case_scope["revision_sha256"]
            for row in state.get("publications", [])
        )
    )


def inspect(
    review: dict,
    value: dict,
    loaded: dict,
    root: Path,
    base: Path,
    api: Any,
    *,
    save: bool = False,
) -> dict:
    """Bind the complete model case and invoke only the unchanged public producer."""
    if (
        not isinstance(review, dict)
        or not set(review) <= {"case", "revision_sha256", "previous_revision_path"}
        or not isinstance(review.get("case"), dict)
    ):
        raise ValueError("Propose a complete Scissione case without approval fields")
    expected = value["identity"]["case_scope"]
    if expected:
        if (
            review.get("revision_sha256") != expected["revision_sha256"]
            or "previous_revision_path" in review
        ):
            raise ValueError("Correction requires this mandate's exact current version")
    elif "revision_sha256" in review:
        raise ValueError("Initial preparation cannot manufacture a preceding revision")
    indexed = {row["relative_path"]: row for row in value["sources"]}
    previous = review.get("previous_revision_path")
    if previous is not None:
        row = indexed.get(previous)
        if (
            row is None
            or row["kind"] != "upstream_artifact"
            or row["upstream_workflow_id"] != "scissione-guidata"
        ):
            raise PermissionError(
                "Continuation requires a chosen sealed Scissione predecessor"
            )
    evidence = review["case"].get("evidence")
    selected = set(indexed) - ({previous} if previous is not None else set())
    if (
        not isinstance(evidence, list)
        or len(evidence) != len(selected)
        or any(not isinstance(row, dict) for row in evidence)
        or {row["path"] for row in evidence} != selected
        or any(row["sha256"] != indexed[row["path"]]["sha256"] for row in evidence)
    ):
        raise PermissionError(
            "Keep every chosen original with its complete byte identity"
        )
    with tempfile.TemporaryDirectory(
        prefix="inspect-scissione-", dir=base
    ) as temporary:
        path = Path(temporary) / "proposal.json"
        api.atomic_json(path, review)
        return engine_call(
            root,
            {
                "operation": "save_proposal" if save else "inspect_proposal",
                "context": str(Path(loaded["run_root"]) / "context.json"),
                "request": str(path),
            },
        )
