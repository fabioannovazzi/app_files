"""Reflect public accounting readiness and insert only literal user attribution."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    root = Path(sys.argv[1])
    request = json.loads(sys.stdin.read(2000001))
    sys.path.insert(0, str(root / "scripts"))
    from accounting_controls import (
        evaluate_accounting_readiness,
        normalize_accounting_review,
    )

    recipe = deepcopy(request["recipe"])
    used = request["used_recipe"]
    review = request["review"]
    section = request["section"]
    # Replay the unchanged producer's mechanically verifiable eligibility on
    # its exact retained totals; semantic correctness is a literal user decision.
    public = request["readiness"]
    tie = public["source_tie_out"]
    replay = evaluate_accounting_readiness(
        used["accounting_review"],
        amount_baseline=tie["baseline_calculated_total"],
        amount_comparison=tie["comparison_calculated_total"],
        max_abs_component_reconciliation_delta=public["component_bridge"][
            "max_abs_reconciliation_delta"
        ],
    )
    if replay != public:
        raise ValueError(
            "Retained public variance accounting readiness disagrees with replay"
        )
    accepted = review["decision"] == "accepted"
    if accepted and replay["accounting_status"] != "ready_for_professional_review":
        raise ValueError(
            "The public accounting controls do not permit positive professional acceptance"
        )
    controls = normalize_accounting_review(recipe.get("accounting_review"))
    raw = controls[section]
    status = "approved" if accepted else review["decision"]
    attribution = {
        "status": status,
        "reviewed_by": review["reviewer"],
        "reviewed_at": review["reviewed_at"],
        "decision_basis": review["basis"],
    }
    if section == "root_cause_review":
        if request["alternative"] not in request["available_alternatives"]:
            raise ValueError(
                "Root-cause decision requires an actual retained public alternative"
            )
        attribution.update(
            selected_alternative=request["alternative"], rationale=review["basis"]
        )
    elif section == "professional_review":
        prior = controls["root_cause_review"]
        if (
            accepted
            and prior["status"] == "approved"
            and prior["selected_alternative"] not in request["available_alternatives"]
        ):
            raise ValueError(
                "The prior approved alternative is absent from the retained public output"
            )
    else:
        raise ValueError("Unknown public professional-review section")
    controls[section] = {**raw, **attribution}
    recipe["accounting_review"] = controls
    # Calculation-derived readiness is regenerated only by a separate public
    # runner call in the successor; do not carry its old report-ready result.
    recipe.pop("accounting_readiness", None)
    sys.stdout.write(
        json.dumps({"recipe": recipe}, ensure_ascii=False, allow_nan=False)
    )


if __name__ == "__main__":
    main()
