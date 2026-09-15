"""Compile declared role columns and resolved period scopes without guessing meaning."""

from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path
from typing import Any

from profile_dataset import load_dataset_frame, parse_period_value
from semantic_execution import verify_execution_context

__all__ = ["compile_reviewed_execution"]


def compile_reviewed_execution(dataset_path: Path, **identity: Any) -> dict[str, Any]:
    """Compile reviewed column bindings; reject preparation the adapters cannot honor."""
    context = verify_execution_context(dataset_path, **identity)
    policy = context["policy"]
    if policy["validity"] != "valid":
        raise ValueError("Selected policy still has unresolved execution conditions")
    metric_requirements = {
        item["role"]: item
        for item in context["capability_contract"]["metric_requirements"][
            "source_metric_roles"
        ]
    }
    concepts = {
        item[key]: item
        for collection, key in (
            ("metrics", "metric_id"),
            ("dimensions", "dimension_id"),
            ("periods", "period_id"),
        )
        for item in context[collection]
    }
    bindings: dict[str, Any] = {}
    currencies: set[str] = set()
    metric_contracts: dict[str, Any] = {}
    for role, binding in policy["role_bindings"].items():
        if binding["binding_type"] != "concept":
            raise ValueError(
                f"Reviewed {role} needs an explicit preparation adapter for {binding['binding_type']}"
            )
        concept = concepts[binding["concept_id"]]
        if concept["status"] != "defined":
            raise ValueError(f"Reviewed {role} is not fully defined")
        column = concept.get("column")
        if "metric_id" in concept:
            if concept["binding"]["binding_type"] != "column":
                raise ValueError(
                    f"Reviewed {role} must be materialized before execution"
                )
            column = concept["binding"]["column"]
            metric_contracts[role] = {
                "metric_id": concept["metric_id"],
                "aggregation": concept["aggregation"],
                "unit": concept["unit"],
            }
            # Current grouped adapters sum their input measures. Never pass a
            # weighted rate to that code as if it were an additive measure.
            observation_level = (
                metric_requirements[role]["aggregation"]
                == "none_observation_level_or_explicit_grouping"
            )
            if not observation_level and (
                concept["aggregation"]["default"] != "sum"
                or "sum" not in concept["aggregation"]["allowed"]
                or "sum" in concept["aggregation"].get("forbidden", [])
            ):
                raise ValueError(
                    f"Reviewed {role} requires aggregation preparation: {concept['aggregation']['default']}"
                )
            if concept["unit"].get("currency"):
                currencies.add(concept["unit"]["currency"])
        if not column:
            raise ValueError(f"Reviewed {role} has no materialized column")
        bindings[role] = column
    if len(currencies) > 1:
        raise ValueError(
            "Selected metrics use different currencies; explicit conversion is required"
        )
    rule_id = policy.get("period_rule_id")
    scope = None
    options: dict[str, Any] = {
        "currency": next(iter(currencies), ""),
        "reporting_entity_label": dataset_path.stem.replace("_", " "),
    }
    if rule_id:
        results = context["snapshot_attachment"]["compatibility"]["period_resolution"][
            "results"
        ]
        resolution = next(item for item in results if item["period_rule_id"] == rule_id)
        if resolution["resolution_status"] != "resolved":
            raise ValueError("Reviewed period rule could not be resolved")
        scope = resolution["resolved_scope"]
        period_column = scope["period_column"]
        if period_column is None:
            contract = context["capability_contract"]["period_scope_contract"]
            if (
                scope["scope_type"] != "all_available"
                or not contract.get("explicit_all_data_allowed")
                or contract.get("period_column_required")
                or contract.get("comparison_pair_required_for_render")
                or "options.selected_periods" not in contract["accepted_scope_controls"]
            ):
                raise ValueError("This capability requires a reviewed period column")
            options["selected_periods"] = ["all_data"]
            return {
                "context": context,
                "role_bindings": bindings,
                "options": options,
                "currency": next(iter(currencies), None),
                "metric_contracts": metric_contracts,
                "resolved_scope": scope,
            }
        windows = scope["windows"]
        frame, _ = load_dataset_frame(dataset_path, **context["parser_settings"])
        selected = []
        periods = frame.select(period_column).unique(maintain_order=True)
        serialized = list(csv.DictReader(io.StringIO(periods.write_csv())))
        for value, encoded in zip(
            periods.get_column(period_column).to_list(), serialized, strict=True
        ):
            parsed = parse_period_value(value)
            if parsed is None:
                raise ValueError("Reviewed period column contains an unparseable value")
            if any(
                date.fromisoformat(window["start"])
                <= parsed
                <= date.fromisoformat(window["end"])
                for window in windows
            ):
                selected.append(encoded[period_column])
        if not selected:
            raise ValueError("Reviewed period scope contains no observations")
        filters = [
            {"column": period_column, "include": selected, "display_in_title": False}
        ]
        options["period_grain"] = resolution["grain"]
        options["period_selection"] = "all"
        period_binding = {
            "column": period_column,
            "date_column": period_column,
            "period_column": period_column,
            "filters": filters,
            "period_grain": resolution["grain"],
        }
        if len(windows) == 2:
            indexed = {window["role"]: window for window in windows}
            if set(indexed) != {"current", "baseline"}:
                raise ValueError(
                    "Comparison windows require current and baseline roles"
                )
            if max(window["start"] for window in windows) <= min(
                window["end"] for window in windows
            ):
                raise ValueError("Overlapping comparison windows require preparation")
            for role, option in (
                ("current", "current_period_label"),
                ("baseline", "previous_period_label"),
            ):
                window = indexed[role]
                if window["start"][:4] != window["end"][:4]:
                    raise ValueError(
                        "Cross-year comparison windows require an explicit preparation adapter"
                    )
                options[option] = window["start"][:4]
                period_binding[option] = window["start"][:4]
            if options["current_period_label"] == options["previous_period_label"]:
                raise ValueError(
                    "Same-year comparison windows require an explicit preparation adapter"
                )
        contract = context["capability_contract"]["period_scope_contract"]
        scope_role = contract["role"]
        if scope_role == "none":
            if scope["scope_type"] != "all_available":
                raise ValueError(
                    "This capability cannot apply the reviewed period scope"
                )
        else:
            if not {"filters", "options.filters"}.intersection(
                contract["accepted_scope_controls"]
            ):
                raise ValueError(
                    "This capability needs a period-scope preparation adapter"
                )
            role = (
                "period_axis"
                if scope_role in {"axis", "axis_or_table"}
                else "period_filter"
            )
            bindings[role] = period_binding
    return {
        "context": context,
        "role_bindings": bindings,
        "options": options,
        "currency": next(iter(currencies), None),
        "metric_contracts": metric_contracts,
        "resolved_scope": scope,
    }
