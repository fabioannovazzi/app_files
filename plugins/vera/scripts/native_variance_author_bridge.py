"""Public variance schema preflight; semantic choices remain explicit proposals."""

from __future__ import annotations

import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Check actual columns through the unchanged public validator, without export."""
    root = Path(sys.argv[1])
    request = json.loads(sys.stdin.read(128001))
    sys.path.insert(0, str(root / "scripts"))
    import run_variance
    import variance_core
    import vera_assurance

    vendor = root / "vendor"
    shared = root.parent / "_shared/variance/vendor"
    if (shared / "modules/__init__.py").is_file():
        vendor = shared
    sys.path.insert(0, str(vendor))
    from modules.utilities.utils import get_row_count

    source = Path(request["source"])
    context = vera_assurance.load_client_engagement_context_file(
        Path(request["context"]),
        expected_workflow_id="variance-analysis",
        input_paths=[source],
    )
    recipe = request["recipe"]
    if not isinstance(recipe, dict) or not isinstance(recipe.get("mappings"), dict):
        raise ValueError("Propose the complete public variance recipe")
    options = recipe.get("options", {})
    if options.get("comparison_basis") not in variance_core.COMPARISON_BASIS_VALUES:
        raise ValueError(
            "Propose an explicit comparison basis; do not adopt an inferred default"
        )
    if (
        options.get("period_comparison_mode")
        not in variance_core.PERIOD_COMPARISON_MODE_VALUES
    ):
        raise ValueError("Propose the explicit period comparison mode")
    if recipe.get("language") != request["language"]:
        raise ValueError("The proposal language differs from the authorized question")
    if options.get("currency", request["currency"]) != request["currency"]:
        raise ValueError("The proposal currency differs from the authorized question")
    review = recipe.get("accounting_review", {})
    if not isinstance(review, dict):
        raise ValueError("Retain the public accounting-review object")
    # These are the two public attestation slots, not a semantic classifier.
    # Prior raw review remains in its original receipt and a separate sidecar;
    # a newly authored comparison requires renewed professional decisions.
    for key in ("professional_review", "root_cause_review"):
        supplied = review.get(key, {})
        if (
            not isinstance(supplied, dict)
            or supplied.get("status", "pending") != "pending"
        ):
            raise ValueError("A model proposal cannot create or inherit human approval")
        if any(
            v not in (None, "", "pending") for k, v in supplied.items() if k != "status"
        ):
            raise ValueError(
                "A model proposal cannot attribute a human or select an approved alternative"
            )
    dataframe = variance_core.read_table(source)
    checked = variance_core.validate_recipe(dataframe, recipe)
    recipe["source_file"] = (
        source.resolve().relative_to(Path(context["run_root"]).resolve()).as_posix()
    )
    result = {
        "recipe": recipe,
        "validation": {
            "public_recipe_schema_checked": True,
            "source_rows": get_row_count(dataframe),
            "columns": variance_core.get_schema_and_column_names(dataframe)[0],
            "pvm_mapped": bool(checked["mappings"].get("units_column")),
            "calculated": False,
            "accounting_tie_out_passed": False,
            "professional_approval": False,
        },
    }
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
