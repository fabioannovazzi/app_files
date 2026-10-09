"""Public valuation preflight and exact inherited review provenance, without export.

Fixed receipt identity and unchanged attestation bytes are audit requirements;
the model and professional own economic meanings and proposed data states.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

__all__ = ["main", "retain_reviews"]


def review_slots(value: dict) -> dict:
    """Use explicit JSON identities, never semantic similarity between records."""
    slots: dict = {}

    def visit(node: object, path: tuple) -> None:
        if isinstance(node, dict):
            # The public plan source map contains arbitrary source IDs, including
            # "review". Its string values are receipt identities, not attestations.
            if "review" in node and path != ("plan_binding", "source_map"):
                if path in slots:
                    raise ValueError("Duplicate valuation review identity")
                slots[path] = node
            for key, item in node.items():
                if key != "review":
                    visit(item, (*path, key))
        elif isinstance(node, list):
            identities = set()
            for index, item in enumerate(node):
                identity = (
                    "id=" + item["id"]
                    if isinstance(item, dict) and isinstance(item.get("id"), str)
                    else "index=" + str(index)
                )
                if identity in identities:
                    raise ValueError("Duplicate valuation record identity")
                identities.add(identity)
                visit(item, (*path, identity))

    visit(value, ())
    return slots


def retain_reviews(proposal: dict, base: dict | None) -> dict:
    """Retain actual raw reviews; new or changed model attestations are refused."""
    case = deepcopy(proposal)
    baseline = review_slots(base or {})
    current = review_slots(case)
    for identity, row in current.items():
        prior = baseline.get(identity, {}).get("review")
        if row["review"] is not None and row["review"] != prior:
            raise ValueError("A model proposal cannot create or change human review")
    for identity, row in baseline.items():
        if row["review"] is None:
            continue
        if identity not in current:
            raise ValueError("Keep the exact prior review-bearing valuation record")
        current[identity]["review"] = deepcopy(row["review"])
    return case


def main() -> None:
    """Validate complete proposals against selected receipts and unchanged producer."""
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root / "scripts"))
    import check_dependencies

    if check_dependencies.main([]):
        raise ValueError("Valuation declared dependencies are unavailable")
    # The maintained entry point initializes the packaged assurance import path.
    import run_valuation
    import valuation_case
    import vera_assurance

    raw = sys.stdin.read(9000001)
    if len(raw.encode()) > 9000000:
        raise ValueError(
            "Complete valuation proposal and predecessor exceed the bridge limit"
        )
    request = json.loads(raw)
    case = retain_reviews(request["case"], request["base"])
    context = vera_assurance.load_client_engagement_context_file(
        Path(request["context"]), expected_workflow_id="business-valuation"
    )
    valuation_case.require(
        context["schema_version"] == "vera.client_workflow_context.v2",
        "Valuation authoring requires a portable v2 context",
    )
    inputs = {row["binding_id"]: row for row in context["input_bindings"]}
    selected = set(request["selected_input_ids"])
    valuation_case.require(selected <= inputs.keys(), "Foreign authoring source")
    bindings = request["source_bindings"]
    valuation_case.require(
        set(bindings) == {row["id"] for row in case["sources"]},
        "Bind every valuation source exactly once",
    )
    source_root = Path(context["run_root"]) / "inputs"
    for row in case["sources"]:
        identity = bindings[row["id"]]
        valuation_case.require(identity in selected, "Unselected authoring source")
        receipt = inputs[identity]
        path = Path(receipt["path"])
        row["path"] = path.relative_to(source_root).as_posix()
        row["sha256"] = receipt["sha256"]
    paths = valuation_case.source_paths(case, source_root)
    vera_assurance.load_client_engagement_context_file(
        Path(request["context"]),
        expected_workflow_id="business-valuation",
        input_paths=paths,
    )
    if "plan_binding" in case:
        identity = bindings[case["plan_binding"]["source_id"]]
        receipt = inputs[identity]
        valuation_case.require(
            receipt["kind"] == "upstream_artifact"
            and receipt["upstream_workflow_id"] == "business-planning",
            "Plan must be a finalized same-engagement Business Planning artifact",
        )
    # No report is exported. Prospective statuses are model-proposed data choices,
    # awaiting the separate named full-case readback and conservation action.
    report = run_valuation.build_valuation(
        case, source_root, replay_parent=Path(context["output_dir"]) / "plan-replay"
    )
    result = {
        "case": case,
        "validation": {
            "valid": True,
            "prospective_status": report["status"],
            "case_sha256": report["case_sha256"],
            "method_states": [
                {k: row[k] for k in ("method_id", "kind", "status")}
                for row in report["methods"]
            ],
            "issues": report["issues"],
            "case_contents_confirmed": False,
            "piv_conformity": report["piv_conformity"],
        },
    }
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
