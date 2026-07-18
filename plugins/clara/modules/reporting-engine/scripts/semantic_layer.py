"""Create and validate stable dataset-contract Reporting Engine semantics.

The semantic layer records reviewed business meaning and analysis validity. The
deterministic code in this module only scaffolds mechanical observations and
checks contract consistency, snapshot compatibility, and period-rule
resolution; it never promotes profiler guesses into semantic facts or chooses
a chart.
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import importlib.util
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

__all__ = [
    "SEMANTIC_LAYER_SCHEMA_VERSION",
    "assess_snapshot_compatibility",
    "build_semantic_acceptance_summary",
    "build_authoring_context",
    "build_semantic_layer_scaffold",
    "build_snapshot_attachment",
    "canonical_profile_fingerprint",
    "canonical_snapshot_fingerprint",
    "main",
    "resolve_period_rules",
    "validate_semantic_layer",
]

SEMANTIC_LAYER_SCHEMA_VERSION = "0.2"
REPORTING_ENGINE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPORTING_ENGINE_ROOT / "catalog" / "selection_manifest.json"
DEFAULT_SEMANTIC_SCHEMA = (
    REPORTING_ENGINE_ROOT / "catalog" / "semantic_layer.schema.json"
)

CONCEPT_STATUSES = {"defined", "conditional", "excluded", "unknown"}
ANALYSIS_VALIDITIES = {"valid", "conditional", "invalid", "unknown"}
CONFIDENCE_LEVELS = {"high", "medium", "low", "unknown"}
COVERAGE_LEVELS = {
    "unreviewed",
    "limited",
    "directional",
    "strong",
    "conflicted",
    "blocked",
}
REVIEW_STATUSES = {"draft", "model_reviewed", "human_reviewed"}
EVIDENCE_STATUSES = {"supported", "inferred", "conflicted", "unverified"}
SOURCE_AUTHORITIES = {
    "canonical",
    "corroborating",
    "observed",
    "mechanical",
    "unverified",
}
BINDING_TYPES = {
    "concept",
    "concept_list",
    "literal",
    "derived",
    "package",
    "unresolved",
}
PERIOD_RULE_TYPES = {
    "all_available",
    "latest_available_period",
    "trailing_periods",
    "current_ytd",
    "current_vs_prior_year",
    "current_ytd_vs_prior_ytd",
    "caller_bounded",
}
PERIOD_SCOPE_TYPES = {"single", "comparison_pair", "all_available"}
SNAPSHOT_COMPATIBILITY_STATUSES = {
    "compatible",
    "compatible_with_extensions",
    "partially_compatible",
    "incompatible",
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _normalized_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Return profile content normalized for a location-independent digest."""

    normalized = json.loads(json.dumps(profile, sort_keys=True, ensure_ascii=False))
    source = normalized.get("source")
    if isinstance(source, dict):
        source.pop("path", None)
    return normalized


def canonical_snapshot_fingerprint(profile: dict[str, Any]) -> str:
    """Hash one snapshot profile while ignoring its machine-specific path."""

    encoded = json.dumps(
        _normalized_profile(profile),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_profile_fingerprint(profile: dict[str, Any]) -> str:
    """Return the snapshot digest under the original public helper name."""

    return canonical_snapshot_fingerprint(profile)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _portable_component_path(path: Path) -> str:
    resolved_path = path.resolve()
    try:
        return str(resolved_path.relative_to(REPORTING_ENGINE_ROOT))
    except ValueError:
        return resolved_path.name


def _profile_dataset_for_acceptance(path: Path, dataset_id: str) -> dict[str, Any]:
    module_path = Path(__file__).resolve().parent / "profile_dataset.py"
    spec = importlib.util.spec_from_file_location(
        "reporting_engine_semantic_acceptance_profiler", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load dataset profiler from {module_path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.profile_dataset(path, dataset_id=dataset_id)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return slug or "unnamed"


def _unique_id(prefix: str, label: str, used: set[str]) -> str:
    base = f"{prefix}.{_slug(label)}"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _profile_source_locator(profile: dict[str, Any]) -> str:
    source = profile.get("source") or {}
    return str(source.get("path") or f"dataset-profile:{profile.get('dataset_id')}")


def _metric_scaffold(profile: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = (
        (profile.get("selector_profile") or {}).get("metric_candidates")
    ) or []
    used_ids: set[str] = set()
    column_to_metric_id: dict[str, str] = {}
    for candidate in candidates:
        column = str(candidate.get("column") or "unnamed")
        column_to_metric_id[column] = _unique_id("metric", column, used_ids)

    records: list[dict[str, Any]] = []
    for candidate in candidates:
        column = str(candidate.get("column") or "unnamed")
        source_role = str(candidate.get("source_role") or "metric")
        produced_from = [str(value) for value in candidate.get("produced_from") or []]
        is_derived = source_role == "derived_metric"
        binding = {
            "binding_type": "derived" if is_derived else "column",
            "column": None if is_derived else column,
            "expression": (
                " / ".join(produced_from) if is_derived and produced_from else None
            ),
            "input_metric_ids": [
                column_to_metric_id[source]
                for source in produced_from
                if source in column_to_metric_id
            ],
        }
        records.append(
            {
                "metric_id": column_to_metric_id[column],
                "label": column,
                "binding": binding,
                "definition": None,
                "metric_class": None,
                "aggregation": {
                    "default": "unknown",
                    "allowed": [],
                    "forbidden": [],
                    "weight_metric_id": None,
                },
                "unit": {
                    "kind": "unknown",
                    "currency": None,
                    "symbol": None,
                },
                "directionality": "unknown",
                "valid_period_grains": [],
                "compatible_dimension_ids": [],
                "forbidden_dimension_ids": [],
                "status": "unknown",
                "confidence": "unknown",
                "rationale": (
                    "Generated from a mechanical metric candidate; business meaning "
                    "and aggregation remain unreviewed."
                ),
                "evidence_ids": ["evidence.dataset_profile"],
                "caveats": [],
                "origin_profile_observation": {
                    "source_role": source_role,
                    "metric_class": candidate.get("metric_class"),
                    "aggregation": candidate.get("aggregation"),
                    "confidence": candidate.get("confidence"),
                    "inference_reasons": candidate.get("inference_reasons") or [],
                },
            }
        )
    return records


def _dimension_scaffold(profile: dict[str, Any]) -> list[dict[str, Any]]:
    selector = profile.get("selector_profile") or {}
    candidates = [
        *(selector.get("dimension_candidates") or []),
        *(selector.get("identifier_candidates") or []),
    ]
    used_ids: set[str] = set()
    records: list[dict[str, Any]] = []
    for candidate in candidates:
        column = str(candidate.get("column") or "unnamed")
        source_role = str(candidate.get("source_role") or "dimension")
        records.append(
            {
                "dimension_id": _unique_id("dimension", column, used_ids),
                "label": column,
                "column": column,
                "definition": None,
                "semantic_type": (
                    "identifier" if source_role == "identifier" else "categorical"
                ),
                "valid_uses": [],
                "hierarchy_parent_id": None,
                "status": "unknown",
                "confidence": "unknown",
                "rationale": (
                    "Generated from a mechanical dimension candidate; grouping, "
                    "hierarchy, and business meaning remain unreviewed."
                ),
                "evidence_ids": ["evidence.dataset_profile"],
                "caveats": [],
                "origin_profile_observation": {
                    "source_role": source_role,
                    "confidence": candidate.get("confidence"),
                    "inference_reasons": candidate.get("inference_reasons") or [],
                },
            }
        )
    return records


def _period_scaffold(profile: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = (
        (profile.get("selector_profile") or {}).get("period_candidates")
    ) or []
    used_ids: set[str] = set()
    records: list[dict[str, Any]] = []
    for candidate in candidates:
        column = str(candidate.get("column") or "unnamed")
        records.append(
            {
                "period_id": _unique_id("period", column, used_ids),
                "label": column,
                "column": column,
                "definition": None,
                "grain": candidate.get("grain") or "unknown",
                "calendar": "unknown",
                "timezone": None,
                "status": "unknown",
                "confidence": "unknown",
                "rationale": (
                    "Generated from a mechanically parseable period candidate; "
                    "calendar and reporting meaning remain unreviewed."
                ),
                "evidence_ids": ["evidence.dataset_profile"],
                "caveats": [],
                "origin_profile_observation": {
                    "confidence": candidate.get("confidence"),
                    "grain": candidate.get("grain"),
                },
            }
        )
    return records


def build_semantic_layer_scaffold(
    profile: dict[str, Any],
    *,
    dataset_contract_id: str | None = None,
    semantic_layer_id: str | None = None,
    semantic_version: int = 1,
    identity_method: str = "caller_assigned",
    identity_value: str | None = None,
    profile_locator: str | None = None,
) -> dict[str, Any]:
    """Create an unreviewed stable contract without semantic assertions."""

    dataset_id = str(profile.get("dataset_id") or "dataset")
    contract_id = dataset_contract_id or dataset_id
    layer_id = semantic_layer_id or f"{_slug(contract_id)}.reporting_semantics"
    return {
        "schema_version": SEMANTIC_LAYER_SCHEMA_VERSION,
        "semantic_layer_id": layer_id,
        "semantic_version": semantic_version,
        "dataset_contract": {
            "dataset_contract_id": contract_id,
            "contract_version": 1,
            "identity": {
                "method": identity_method,
                "value": identity_value or contract_id,
            },
            "origin_snapshot": {
                "profile_schema_version": str(
                    profile.get("schema_version") or "unknown"
                ),
                "snapshot_fingerprint": canonical_snapshot_fingerprint(profile),
            },
            "unknown_column_policy": "allow_as_unclassified_extension",
        },
        "scope": {
            "title": f"{dataset_id} reporting semantics",
            "business_area": None,
            "purpose": (
                "Define source-backed business concepts and analysis validity for "
                "Reporting Engine chart selection."
            ),
            "coverage_level": "unreviewed",
            "included_subjects": [],
            "excluded_subjects": [],
        },
        "sources": [
            {
                "source_id": "source.dataset_profile",
                "source_type": "dataset_profile",
                "locator": profile_locator or _profile_source_locator(profile),
                "authority": "mechanical",
                "supports": [
                    "physical columns",
                    "types and cardinality",
                    "mechanical metric, dimension, and period candidates",
                ],
                "caveats": [
                    "The profile does not establish business meaning or analysis validity."
                ],
                "last_checked": None,
            }
        ],
        "evidence": [
            {
                "evidence_id": "evidence.dataset_profile",
                "source_id": "source.dataset_profile",
                "locator": "dataset profile root",
                "claim": (
                    "The referenced fields and profiler candidates exist mechanically; "
                    "their business interpretation remains unreviewed."
                ),
                "confidence": "high",
                "status": "supported",
                "notes": [],
            }
        ],
        "metrics": _metric_scaffold(profile),
        "dimensions": _dimension_scaffold(profile),
        "periods": _period_scaffold(profile),
        "period_rules": [],
        "analysis_policies": [],
        "open_questions": [
            {
                "question_id": "question.canonical_metrics",
                "question": (
                    "Which metric candidates are canonical, and how may each be "
                    "aggregated?"
                ),
                "why_it_matters": (
                    "Chart metric roles cannot be bound safely until metric meaning "
                    "and aggregation are reviewed."
                ),
                "owner_or_source": None,
                "status": "open",
            },
            {
                "question_id": "question.dimension_meaning",
                "question": (
                    "Which dimensions are valid for grouping, filtering, hierarchy, "
                    "panels, or entity identity?"
                ),
                "why_it_matters": (
                    "Mechanical cardinality alone cannot establish a meaningful split."
                ),
                "owner_or_source": None,
                "status": "open",
            },
            {
                "question_id": "question.analysis_validity",
                "question": (
                    "Which manifest analysis types make business sense for these "
                    "reviewed concepts and reusable period rules?"
                ),
                "why_it_matters": (
                    "The semantic layer must approve, reject, or condition analyses "
                    "before a future selector chooses a chart."
                ),
                "owner_or_source": None,
                "status": "open",
            },
        ],
        "review": {
            "status": "draft",
            "reviewed_by": None,
            "reviewed_at": None,
            "notes": [
                "Scaffold generated mechanically; no semantic assertion is approved."
            ],
        },
        "boundaries": {
            "semantic_judgment_owner": "model_or_human_review",
            "deterministic_validation_scope": (
                "Schema, identifiers, evidence references, stable dataset identity, "
                "snapshot compatibility, period-rule resolution, manifest intent "
                "references, and required role coverage only."
            ),
            "chart_selection_included": False,
            "rendering_included": False,
        },
    }


def _caller_required_roles(capability: dict[str, Any]) -> list[dict[str, Any]]:
    contract = capability.get("normalized_invocation_contract") or {}
    metric_requirements = (
        ((capability.get("selection_contract") or {}).get("dataset_requirements") or {})
        .get("metrics", {})
        .get("source_metric_roles", [])
    )
    metric_classes_by_role = {
        str(requirement.get("role")): list(
            requirement.get("accepted_metric_classes") or []
        )
        for requirement in metric_requirements
    }
    roles = []
    for role in contract.get("required_role_contracts") or []:
        if role.get("required", True) and role.get("caller_binding_required", True):
            roles.append(
                {
                    "role": str(role.get("role")),
                    "kind": str(role.get("kind") or "unknown"),
                    "mapping_kind": role.get("mapping_kind"),
                    "scope_binding": role.get("scope_binding") or {},
                    "accepted_metric_classes": metric_classes_by_role.get(
                        str(role.get("role")), []
                    ),
                }
            )
    return roles


def _analysis_catalog(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    capabilities = manifest.get("capabilities") or {}
    records: dict[str, dict[str, Any]] = {}
    for task_id, task in (manifest.get("analysis_tasks") or {}).items():
        for emphasis, treatment in (task.get("treatments") or {}).items():
            record = records.setdefault(
                emphasis,
                {
                    "selection_emphasis": emphasis,
                    "analysis_task_ids": [],
                    "capability_ids": [],
                    "best_when": treatment.get("best_when"),
                    "avoid_when": treatment.get("avoid_when"),
                    "required_role_sets": [],
                },
            )
            if task_id not in record["analysis_task_ids"]:
                record["analysis_task_ids"].append(task_id)
            for capability_id in treatment.get("capability_ids") or []:
                if capability_id not in record["capability_ids"]:
                    record["capability_ids"].append(capability_id)
                capability = capabilities.get(capability_id) or {}
                role_set = {
                    "capability_id": capability_id,
                    "roles": _caller_required_roles(capability),
                    "period_scope_contract": capability.get("period_scope_contract")
                    or {},
                }
                if role_set not in record["required_role_sets"]:
                    record["required_role_sets"].append(role_set)
    for record in records.values():
        record["analysis_task_ids"].sort()
        record["capability_ids"].sort()
        record["required_role_sets"].sort(key=lambda item: item["capability_id"])
    return [records[key] for key in sorted(records)]


def build_authoring_context(
    profile: dict[str, Any],
    manifest: dict[str, Any],
    *,
    semantic_layer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Package mechanical evidence and manifest intents for semantic review."""

    scaffold = semantic_layer or build_semantic_layer_scaffold(profile)
    return {
        "schema_version": SEMANTIC_LAYER_SCHEMA_VERSION,
        "purpose": (
            "Model-facing context for authoring or reviewing one dataset-specific "
            "Reporting Engine semantic layer."
        ),
        "snapshot_fingerprint": canonical_snapshot_fingerprint(profile),
        "snapshot_profile": profile,
        "semantic_layer_draft": scaffold,
        "analysis_catalog": _analysis_catalog(manifest),
        "authoring_rules": [
            "Inspect source data and business evidence; profiler labels are candidates, not semantic facts.",
            "Keep metric definitions, aggregation, units, dimensions, calendars, and reusable period rules explicit.",
            "Do not copy row counts, values, members, available date bounds, or concrete run windows into stable semantics.",
            "Bind the layer to a caller-, connector-, or project-assigned dataset contract id; never infer logical identity from schema alone.",
            "Every valid, conditional, or invalid semantic assertion needs rationale and source-backed evidence.",
            "Preserve conflicts and unknowns instead of guessing.",
            "Add analysis policies only for meaningful reusable analysis families; do not manufacture one policy per chart.",
            "Treat every manifest selection emphasis without a reviewed policy as unknown, not valid or invalid by default.",
            "Use manifest analysis_task_ids and selection_emphases as join keys, then bind their canonical roles to reviewed concepts.",
            "Do not choose a chart in the semantic layer. The manifest remains the plot-side contract.",
        ],
        "boundary": (
            "This context supports model-led semantic authoring. It is not a "
            "classifier, selector, orchestrator, or rendering request."
        ),
    }


def _issue(target: list[dict[str, Any]], code: str, path: str, message: str) -> None:
    target.append({"code": code, "path": path, "message": message})


def _schema_error_path(parts: Any) -> str:
    """Return a stable JSONPath-like location for one schema error."""

    path = "$"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def _check_json_schema(
    layer: dict[str, Any],
    schema: dict[str, Any],
    errors: list[dict[str, Any]],
) -> None:
    """Apply the packaged schema because structure is mechanically verifiable."""

    validator = Draft202012Validator(schema)
    validation_errors = sorted(
        validator.iter_errors(layer),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    for validation_error in validation_errors:
        _issue(
            errors,
            "schema_validation_error",
            _schema_error_path(validation_error.absolute_path),
            validation_error.message,
        )


def _records(
    layer: dict[str, Any],
    key: str,
    id_key: str,
    errors: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    raw = layer.get(key)
    if not isinstance(raw, list):
        _issue(errors, "invalid_type", key, "Expected a list.")
        return [], {}
    index: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    for position, value in enumerate(raw):
        path = f"{key}[{position}]"
        if not isinstance(value, dict):
            _issue(errors, "invalid_type", path, "Expected an object.")
            continue
        record_id = value.get(id_key)
        if not isinstance(record_id, str) or not record_id.strip():
            _issue(
                errors, "missing_id", f"{path}.{id_key}", "A non-empty id is required."
            )
            continue
        if record_id in index:
            _issue(
                errors, "duplicate_id", f"{path}.{id_key}", f"Duplicate id: {record_id}"
            )
            continue
        index[record_id] = value
        records.append(value)
    return records, index


def _check_enum(
    value: Any,
    allowed: set[str],
    path: str,
    errors: list[dict[str, Any]],
) -> None:
    if value not in allowed:
        _issue(
            errors,
            "invalid_enum",
            path,
            f"Expected one of {sorted(allowed)}; got {value!r}.",
        )


def _check_assertion_evidence(
    record: dict[str, Any],
    *,
    status_key: str,
    unknown_value: str,
    path: str,
    evidence_index: dict[str, dict[str, Any]],
    source_index: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    if record.get(status_key) == unknown_value:
        return
    rationale = record.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        _issue(
            errors,
            "missing_rationale",
            f"{path}.rationale",
            "Reviewed semantic assertions require a rationale.",
        )
    evidence_ids = record.get("evidence_ids")
    if not isinstance(evidence_ids, list) or not evidence_ids:
        _issue(
            errors,
            "missing_evidence",
            f"{path}.evidence_ids",
            "Reviewed semantic assertions require at least one evidence reference.",
        )
        return
    resolved_evidence: list[dict[str, Any]] = []
    for evidence_id in evidence_ids:
        evidence = evidence_index.get(str(evidence_id))
        if evidence is None:
            _issue(
                errors,
                "unknown_evidence",
                f"{path}.evidence_ids",
                f"Unknown evidence id: {evidence_id}",
            )
            continue
        resolved_evidence.append(evidence)
    if resolved_evidence and not any(
        (source_index.get(str(evidence.get("source_id"))) or {}).get("authority")
        in {"canonical", "corroborating", "observed"}
        for evidence in resolved_evidence
    ):
        _issue(
            errors,
            "semantic_assertion_only_mechanical_evidence",
            f"{path}.evidence_ids",
            "A reviewed semantic assertion needs at least one non-mechanical source.",
        )
    if any(evidence.get("status") == "conflicted" for evidence in resolved_evidence):
        _issue(
            warnings,
            "conflicted_evidence_cited",
            f"{path}.evidence_ids",
            "The assertion cites conflicted evidence; preserve the conflict in status, rationale, or caveats.",
        )


def _check_iso_date(value: Any, path: str, errors: list[dict[str, Any]]) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        _issue(errors, "invalid_date", path, "Expected an ISO date string or null.")
        return
    try:
        date.fromisoformat(value)
    except ValueError:
        _issue(errors, "invalid_date", path, f"Invalid ISO date: {value}")


def _analysis_catalog_index(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        record["selection_emphasis"]: record for record in _analysis_catalog(manifest)
    }


def _binding_is_resolved(binding: dict[str, Any]) -> bool:
    return binding.get("binding_type") != "unresolved"


def _binding_concept_ids(binding: Any) -> list[str]:
    if not isinstance(binding, dict):
        return []
    if binding.get("binding_type") == "concept" and binding.get("concept_id"):
        return [str(binding["concept_id"])]
    if binding.get("binding_type") == "concept_list":
        return [str(value) for value in binding.get("concept_ids") or []]
    return []


def _policy_semantic_mismatches(
    *,
    validity: Any,
    role_bindings: dict[str, Any],
    period_rule_id: Any,
    concept_index: dict[str, tuple[str, dict[str, Any]]],
    period_rule_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if validity not in {"valid", "conditional"}:
        return []
    allowed_statuses = (
        {"defined"} if validity == "valid" else {"defined", "conditional"}
    )
    bound_concepts = [
        (role, concept_id, concept_index.get(concept_id))
        for role, binding in role_bindings.items()
        for concept_id in _binding_concept_ids(binding)
    ]
    mismatches: list[dict[str, Any]] = []
    for role, concept_id, concept in bound_concepts:
        if concept is None:
            continue
        if concept[1].get("status") not in allowed_statuses:
            mismatches.append(
                {
                    "code": "concept_not_ready",
                    "role": role,
                    "concept_id": concept_id,
                    "message": (
                        f"{validity} policy cannot use concept status "
                        f"{concept[1].get('status')!r}."
                    ),
                }
            )
    if period_rule_id in period_rule_index:
        rule_status = period_rule_index[period_rule_id].get("status")
        if rule_status not in allowed_statuses:
            mismatches.append(
                {
                    "code": "period_rule_not_ready",
                    "period_rule_id": period_rule_id,
                    "message": (
                        f"{validity} policy cannot use period rule status "
                        f"{rule_status!r}."
                    ),
                }
            )

    metrics = [
        (concept_id, concept[1])
        for _, concept_id, concept in bound_concepts
        if concept is not None and concept[0] == "metric"
    ]
    dimensions = [
        (concept_id, concept[1])
        for _, concept_id, concept in bound_concepts
        if concept is not None and concept[0] == "dimension"
    ]
    periods = [
        (concept_id, concept[1])
        for _, concept_id, concept in bound_concepts
        if concept is not None and concept[0] == "period"
    ]
    if period_rule_id in period_rule_index:
        rule_period_id = period_rule_index[period_rule_id].get("period_id")
        rule_period = concept_index.get(str(rule_period_id))
        if rule_period is not None and rule_period[0] == "period":
            periods.append((str(rule_period_id), rule_period[1]))
    dimensions = list(dict(dimensions).items())
    periods = list(dict(periods).items())
    for metric_id, metric in metrics:
        compatible_dimensions = set(metric.get("compatible_dimension_ids") or [])
        forbidden_dimensions = set(metric.get("forbidden_dimension_ids") or [])
        for dimension_id, _ in dimensions:
            if dimension_id in forbidden_dimensions:
                mismatches.append(
                    {
                        "code": "forbidden_metric_dimension",
                        "metric_id": metric_id,
                        "dimension_id": dimension_id,
                        "message": f"{metric_id} forbids analysis by {dimension_id}.",
                    }
                )
            elif compatible_dimensions and dimension_id not in compatible_dimensions:
                mismatches.append(
                    {
                        "code": "unapproved_metric_dimension",
                        "metric_id": metric_id,
                        "dimension_id": dimension_id,
                        "message": (
                            f"{dimension_id} is not in the reviewed compatible "
                            f"dimensions for {metric_id}."
                        ),
                    }
                )
        valid_grains = set(metric.get("valid_period_grains") or [])
        for period_id, period in periods:
            grain = period.get("grain")
            if valid_grains and grain not in valid_grains:
                mismatches.append(
                    {
                        "code": "unapproved_metric_period_grain",
                        "metric_id": metric_id,
                        "period_id": period_id,
                        "grain": grain,
                        "message": (
                            f"Period grain {grain!r} is not approved for {metric_id}."
                        ),
                    }
                )
    return mismatches


def _check_role_binding(
    *,
    role: str,
    binding: Any,
    path: str,
    concept_index: dict[str, tuple[str, dict[str, Any]]],
    role_registry: dict[str, Any],
    source_index: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    if not isinstance(binding, dict):
        _issue(errors, "invalid_role_binding", path, "Expected a role-binding object.")
        return
    binding_type = binding.get("binding_type")
    _check_enum(binding_type, BINDING_TYPES, f"{path}.binding_type", errors)
    role_contract = (role_registry.get("chart_roles") or {}).get(role)
    if role_contract is None:
        _issue(errors, "unknown_chart_role", path, f"Unknown manifest role: {role}")
    expected_kinds = set((role_contract or {}).get("kinds") or []) - {"variant"}
    if binding_type == "concept":
        concept_id = binding.get("concept_id")
        concept = concept_index.get(str(concept_id))
        if concept is None:
            _issue(
                errors,
                "unknown_concept",
                f"{path}.concept_id",
                f"Unknown concept: {concept_id}",
            )
        elif expected_kinds and concept[0] not in expected_kinds:
            _issue(
                errors,
                "role_concept_kind_mismatch",
                f"{path}.concept_id",
                f"Role {role} expects {sorted(expected_kinds)}, not {concept[0]}.",
            )
    elif binding_type == "concept_list":
        concept_ids = binding.get("concept_ids")
        if not isinstance(concept_ids, list) or not concept_ids:
            _issue(
                errors,
                "missing_concepts",
                f"{path}.concept_ids",
                "A non-empty concept list is required.",
            )
        else:
            for concept_id in concept_ids:
                concept = concept_index.get(str(concept_id))
                if concept is None:
                    _issue(
                        errors,
                        "unknown_concept",
                        f"{path}.concept_ids",
                        f"Unknown concept: {concept_id}",
                    )
                elif expected_kinds and concept[0] not in expected_kinds:
                    _issue(
                        errors,
                        "role_concept_kind_mismatch",
                        f"{path}.concept_ids",
                        f"Role {role} expects {sorted(expected_kinds)}, not {concept[0]}.",
                    )
    elif binding_type == "derived":
        if not binding.get("expression"):
            _issue(
                errors,
                "missing_expression",
                f"{path}.expression",
                "A derived binding needs an expression.",
            )
    elif binding_type == "package":
        source_id = binding.get("source_id")
        if source_id not in source_index:
            _issue(
                errors,
                "unknown_source",
                f"{path}.source_id",
                f"Unknown package source: {source_id}",
            )
    elif binding_type == "unresolved" and not binding.get("reason"):
        _issue(
            errors,
            "missing_reason",
            f"{path}.reason",
            "An unresolved binding needs a reason.",
        )
    elif binding_type == "literal" and "value" not in binding:
        _issue(
            errors,
            "missing_literal",
            f"{path}.value",
            "A literal binding needs a value.",
        )

    if binding_type in {"literal", "derived", "package"} and expected_kinds:
        _issue(
            warnings,
            "non_concept_role_binding",
            path,
            f"Role {role} is bound through {binding_type}; deterministic kind checking is limited.",
        )


def _parse_profile_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _shift_months(value: date, months: int) -> date:
    absolute_month = value.year * 12 + value.month - 1 + months
    year, zero_based_month = divmod(absolute_month, 12)
    month = zero_based_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _shift_years(value: date, years: int) -> date:
    year = value.year + years
    day = min(value.day, calendar.monthrange(year, value.month)[1])
    return date(year, value.month, day)


def _period_start(value: date, grain: str) -> date:
    if grain == "week":
        return value - timedelta(days=value.weekday())
    if grain == "month":
        return date(value.year, value.month, 1)
    if grain == "quarter":
        return date(value.year, 1 + 3 * ((value.month - 1) // 3), 1)
    if grain == "year":
        return date(value.year, 1, 1)
    return value


def _period_end(value: date, grain: str) -> date:
    start = _period_start(value, grain)
    if grain == "week":
        return start + timedelta(days=6)
    if grain == "month":
        return date(
            start.year, start.month, calendar.monthrange(start.year, start.month)[1]
        )
    if grain == "quarter":
        next_quarter = _shift_months(start, 3)
        return next_quarter - timedelta(days=1)
    if grain == "year":
        return date(start.year, 12, 31)
    return start


def _shift_period(value: date, grain: str, periods: int) -> date:
    if grain == "day":
        return value + timedelta(days=periods)
    if grain == "week":
        return value + timedelta(days=periods * 7)
    if grain == "month":
        return _shift_months(value, periods)
    if grain == "quarter":
        return _shift_months(value, periods * 3)
    if grain == "year":
        return _shift_years(value, periods)
    return value


def _window(role: str, start: date, end: date) -> dict[str, Any]:
    return {
        "role": role,
        "label": f"{start.isoformat()} to {end.isoformat()}",
        "start": start.isoformat(),
        "end": end.isoformat(),
    }


def _expected_period_starts(start: date, end: date, grain: str) -> list[date]:
    values: list[date] = []
    current = _period_start(start, grain)
    final = _period_start(end, grain)
    for _ in range(5000):
        if current > final:
            break
        values.append(current)
        next_value = _shift_period(current, grain, 1)
        if next_value <= current:
            break
        current = next_value
    return values


def _available_period_starts(
    profile: dict[str, Any], column: str | None, grain: str
) -> tuple[set[date], bool]:
    column_profile = (profile.get("columns") or {}).get(column) or {}
    if column_profile.get("ordered_values_complete") is not True:
        return set(), False
    values = {
        _period_start(parsed, grain)
        for raw_value in column_profile.get("ordered_values") or []
        if (parsed := _parse_profile_date(str(raw_value))) is not None
    }
    return values, True


def _period_bounds(
    period: dict[str, Any], profile: dict[str, Any]
) -> tuple[date | None, date | None, str | None, str | None]:
    column = period.get("column")
    column_profile = (profile.get("columns") or {}).get(column) or {}
    parseability = column_profile.get("period_parseability") or {}
    minimum = _parse_profile_date(parseability.get("parsed_min"))
    maximum = _parse_profile_date(parseability.get("parsed_max"))
    profile_grain = column_profile.get("period_grain") or parseability.get(
        "inferred_grain"
    )
    return (
        minimum,
        maximum,
        str(column) if column else None,
        (str(profile_grain) if profile_grain else None),
    )


def _resolve_period_rule(
    rule: dict[str, Any],
    period_index: dict[str, dict[str, Any]],
    profile: dict[str, Any],
) -> dict[str, Any]:
    rule_id = rule.get("period_rule_id")
    period = period_index.get(str(rule.get("period_id")))
    base = {
        "period_rule_id": rule_id,
        "rule_type": rule.get("rule_type"),
        "scope_type": rule.get("scope_type"),
        "resolution_status": "unavailable",
        "reason": None,
        "period_column": None,
        "grain": None,
        "snapshot_bounds": None,
        "coverage_check": {
            "status": "not_checked",
            "missing_period_starts": [],
        },
        "resolved_scope": None,
    }
    if rule.get("status") not in {"defined", "conditional"}:
        base["reason"] = "period_rule_not_reviewed"
        return base
    if period is None or period.get("status") not in {"defined", "conditional"}:
        base["reason"] = "period_concept_not_available"
        return base
    minimum, maximum, column, profile_grain = _period_bounds(period, profile)
    grain = str(period.get("grain") or "unknown")
    base["period_column"] = column
    base["grain"] = grain
    if profile_grain not in {None, "unknown", grain}:
        base["reason"] = "snapshot_period_grain_mismatch"
        return base
    if minimum is None or maximum is None:
        base["reason"] = "snapshot_period_bounds_unavailable"
        return base
    base["snapshot_bounds"] = {
        "minimum": minimum.isoformat(),
        "maximum": maximum.isoformat(),
    }
    rule_type = rule.get("rule_type")
    parameters = rule.get("parameters") or {}
    if rule_type == "caller_bounded":
        base["resolution_status"] = "requires_runtime_input"
        base["reason"] = "caller_must_supply_concrete_period_bounds"
        return base

    latest_start = _period_start(maximum, grain)
    latest_end = _period_end(maximum, grain)
    windows: list[dict[str, Any]]
    if rule_type == "all_available":
        windows = [_window("current", _period_start(minimum, grain), latest_end)]
    elif rule_type == "latest_available_period":
        windows = [_window("current", latest_start, latest_end)]
    elif rule_type == "trailing_periods":
        window_length = int(parameters.get("window_length") or 0)
        if window_length < 1:
            base["reason"] = "invalid_window_length"
            return base
        windows = [
            _window(
                "current",
                _shift_period(latest_start, grain, -(window_length - 1)),
                latest_end,
            )
        ]
    elif rule_type == "current_ytd":
        fiscal_month = int(parameters.get("fiscal_year_start_month") or 1)
        fiscal_year = (
            maximum.year if maximum.month >= fiscal_month else maximum.year - 1
        )
        windows = [_window("current", date(fiscal_year, fiscal_month, 1), latest_end)]
    elif rule_type == "current_vs_prior_year":
        window_length = int(parameters.get("window_length") or 0)
        if window_length < 1:
            base["reason"] = "invalid_window_length"
            return base
        offset = int(parameters.get("comparison_offset_years") or 1)
        current_start = _shift_period(latest_start, grain, -(window_length - 1))
        baseline_start = _shift_years(current_start, -offset)
        baseline_end = _shift_years(latest_end, -offset)
        windows = [
            _window("current", current_start, latest_end),
            _window("baseline", baseline_start, baseline_end),
        ]
    elif rule_type == "current_ytd_vs_prior_ytd":
        fiscal_month = int(parameters.get("fiscal_year_start_month") or 1)
        fiscal_year = (
            maximum.year if maximum.month >= fiscal_month else maximum.year - 1
        )
        current_start = date(fiscal_year, fiscal_month, 1)
        offset = int(parameters.get("comparison_offset_years") or 1)
        baseline_start = _shift_years(current_start, -offset)
        baseline_end = _shift_years(latest_end, -offset)
        windows = [
            _window("current", current_start, latest_end),
            _window("baseline", baseline_start, baseline_end),
        ]
    else:
        base["reason"] = "unsupported_period_rule"
        return base

    available_periods, available_periods_complete = _available_period_starts(
        profile, column, grain
    )
    if rule_type != "all_available" and available_periods_complete:
        expected_periods = {
            period_start
            for window in windows
            for period_start in _expected_period_starts(
                _parse_profile_date(window["start"]),
                _parse_profile_date(window["end"]),
                grain,
            )
        }
        missing_periods = sorted(expected_periods - available_periods)
        base["coverage_check"] = {
            "status": "complete" if not missing_periods else "missing_periods",
            "missing_period_starts": [value.isoformat() for value in missing_periods],
        }
        if missing_periods:
            base["reason"] = "snapshot_lacks_required_period_values"
            return base
    elif rule_type != "all_available":
        base["coverage_check"] = {
            "status": "not_proven_from_truncated_period_values",
            "missing_period_starts": [],
        }

    baseline_windows = [window for window in windows if window["role"] == "baseline"]
    if baseline_windows and any(
        _parse_profile_date(window["start"]) < minimum
        or _parse_profile_date(window["end"]) > _period_end(maximum, grain)
        for window in baseline_windows
    ):
        base["reason"] = "snapshot_lacks_required_baseline_history"
        return base
    base["resolution_status"] = "resolved"
    base["resolved_scope"] = {
        "source_period_rule_id": rule_id,
        "scope_type": rule.get("scope_type"),
        "period_column": column,
        "windows": windows,
    }
    return base


def resolve_period_rules(
    layer: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    """Resolve stable period rules from mechanically observed snapshot bounds."""

    period_index = {
        str(period.get("period_id")): period
        for period in layer.get("periods") or []
        if isinstance(period, dict) and period.get("period_id")
    }
    results = [
        _resolve_period_rule(rule, period_index, profile)
        for rule in layer.get("period_rules") or []
        if isinstance(rule, dict)
    ]
    counts = {
        status: sum(1 for result in results if result["resolution_status"] == status)
        for status in ("resolved", "requires_runtime_input", "unavailable")
    }
    return {
        "snapshot_fingerprint": canonical_snapshot_fingerprint(profile),
        "results": results,
        "counts": counts,
        "boundary": (
            "Resolution converts reviewed period rules into snapshot-specific bounds. "
            "It does not establish business meaning or period completeness."
        ),
    }


def _concept_snapshot_results(
    layer: dict[str, Any], profile: dict[str, Any]
) -> tuple[list[dict[str, Any]], set[str]]:
    profile_columns = profile.get("columns") or {}
    results: list[dict[str, Any]] = []
    known_columns: set[str] = set()
    direct_metric_status: dict[str, str] = {}
    metrics = [
        metric for metric in layer.get("metrics") or [] if isinstance(metric, dict)
    ]
    for metric in metrics:
        metric_id = str(metric.get("metric_id"))
        binding = metric.get("binding") or {}
        column = binding.get("column")
        if binding.get("binding_type") == "column" and column:
            known_columns.add(str(column))
            observed_role = (profile_columns.get(column) or {}).get("role")
            if column not in profile_columns:
                status, reason = "missing", "bound_metric_column_missing"
            elif observed_role != "metric":
                status, reason = "incompatible", "bound_metric_column_role_changed"
            else:
                status, reason = "compatible", None
            direct_metric_status[metric_id] = status
            results.append(
                {
                    "concept_id": metric_id,
                    "kind": "metric",
                    "semantic_status": metric.get("status"),
                    "column": column,
                    "status": status,
                    "reason": reason,
                    "observed_role": observed_role,
                }
            )
    for metric in metrics:
        binding = metric.get("binding") or {}
        if binding.get("binding_type") != "derived":
            continue
        metric_id = str(metric.get("metric_id"))
        input_ids = [str(value) for value in binding.get("input_metric_ids") or []]
        incompatible_inputs = [
            value
            for value in input_ids
            if direct_metric_status.get(value) != "compatible"
        ]
        status = "compatible" if not incompatible_inputs else "incompatible"
        results.append(
            {
                "concept_id": metric_id,
                "kind": "metric",
                "semantic_status": metric.get("status"),
                "column": None,
                "status": status,
                "reason": (
                    None
                    if status == "compatible"
                    else "derived_metric_input_unavailable"
                ),
                "incompatible_input_metric_ids": incompatible_inputs,
            }
        )
    for dimension in layer.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        column = dimension.get("column")
        if column:
            known_columns.add(str(column))
        observed_role = (profile_columns.get(column) or {}).get("role")
        if column not in profile_columns:
            status, reason = "missing", "bound_dimension_column_missing"
        elif observed_role not in {"dimension", "identifier"}:
            status, reason = "incompatible", "bound_dimension_column_role_changed"
        else:
            status, reason = "compatible", None
        results.append(
            {
                "concept_id": dimension.get("dimension_id"),
                "kind": "dimension",
                "semantic_status": dimension.get("status"),
                "column": column,
                "status": status,
                "reason": reason,
                "observed_role": observed_role,
            }
        )
    for period in layer.get("periods") or []:
        if not isinstance(period, dict):
            continue
        column = period.get("column")
        if column:
            known_columns.add(str(column))
        column_profile = profile_columns.get(column) or {}
        observed_role = column_profile.get("role")
        observed_grain = column_profile.get("period_grain") or (
            column_profile.get("period_parseability") or {}
        ).get("inferred_grain")
        expected_grain = period.get("grain")
        if column not in profile_columns:
            status, reason = "missing", "bound_period_column_missing"
        elif observed_role != "period":
            status, reason = "incompatible", "bound_period_column_role_changed"
        elif observed_grain not in {None, "unknown", expected_grain}:
            status, reason = "incompatible", "bound_period_grain_changed"
        else:
            status, reason = "compatible", None
        results.append(
            {
                "concept_id": period.get("period_id"),
                "kind": "period",
                "semantic_status": period.get("status"),
                "column": column,
                "status": status,
                "reason": reason,
                "observed_role": observed_role,
                "expected_grain": expected_grain,
                "observed_grain": observed_grain,
            }
        )
    return results, known_columns


def assess_snapshot_compatibility(
    layer: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    """Check explicit identity and mechanical concept availability for one snapshot."""

    raw_dataset_contract = layer.get("dataset_contract")
    dataset_contract = (
        raw_dataset_contract if isinstance(raw_dataset_contract, dict) else {}
    )
    contract_id = dataset_contract.get("dataset_contract_id")
    snapshot_dataset_id = profile.get("dataset_id")
    identity_matches = contract_id == snapshot_dataset_id
    concept_results, known_columns = _concept_snapshot_results(layer, profile)
    relevant_concepts = {
        str(result["concept_id"]): result
        for result in concept_results
        if result.get("semantic_status") in {"defined", "conditional"}
    }
    period_resolution = resolve_period_rules(layer, profile)
    period_results = {
        str(result.get("period_rule_id")): result
        for result in period_resolution["results"]
    }
    policy_results = []
    for policy in layer.get("analysis_policies") or []:
        if not isinstance(policy, dict):
            continue
        validity = policy.get("validity")
        raw_role_bindings = policy.get("role_bindings")
        role_bindings = raw_role_bindings if isinstance(raw_role_bindings, dict) else {}
        bound_ids = sorted(
            {
                concept_id
                for binding in role_bindings.values()
                for concept_id in _binding_concept_ids(binding)
            }
        )
        unavailable_concepts = [
            concept_id
            for concept_id in bound_ids
            if (relevant_concepts.get(concept_id) or {}).get("status") != "compatible"
        ]
        period_rule_id = policy.get("period_rule_id")
        period_result = (
            period_results.get(str(period_rule_id)) if period_rule_id else None
        )
        if validity not in {"valid", "conditional"}:
            availability = "not_applicable"
        elif not identity_matches or unavailable_concepts:
            availability = "unavailable"
        elif period_result and period_result["resolution_status"] == "unavailable":
            availability = "unavailable"
        elif (
            period_result
            and period_result["resolution_status"] == "requires_runtime_input"
        ):
            availability = "available_with_runtime_input"
        else:
            availability = "available"
        policy_results.append(
            {
                "analysis_id": policy.get("analysis_id"),
                "validity": validity,
                "availability": availability,
                "unavailable_concept_ids": unavailable_concepts,
                "period_rule_id": period_rule_id,
                "period_resolution_status": (
                    period_result.get("resolution_status") if period_result else None
                ),
            }
        )

    semantic_issues = [
        result
        for result in relevant_concepts.values()
        if result.get("status") != "compatible"
    ]
    profile_columns = set((profile.get("columns") or {}).keys())
    extension_columns = sorted(profile_columns - known_columns)
    available_policy_count = sum(
        result["availability"] in {"available", "available_with_runtime_input"}
        for result in policy_results
    )
    reviewed_policy_count = sum(
        result["validity"] in {"valid", "conditional"} for result in policy_results
    )
    if not identity_matches:
        status = "incompatible"
    elif semantic_issues and available_policy_count:
        status = "partially_compatible"
    elif semantic_issues:
        status = "incompatible"
    elif extension_columns:
        status = "compatible_with_extensions"
    else:
        status = "compatible"
    if status not in SNAPSHOT_COMPATIBILITY_STATUSES:
        raise ValueError(f"Unexpected snapshot compatibility status: {status}")
    return {
        "status": status,
        "semantic_layer_reusable": status != "incompatible",
        "dataset_contract_id": contract_id,
        "snapshot_dataset_id": snapshot_dataset_id,
        "identity_matches": identity_matches,
        "snapshot_fingerprint": canonical_snapshot_fingerprint(profile),
        "origin_snapshot_matches": (
            (
                (dataset_contract.get("origin_snapshot") or {}).get(
                    "snapshot_fingerprint"
                )
            )
            == canonical_snapshot_fingerprint(profile)
        ),
        "extension_columns": extension_columns,
        "concept_results": concept_results,
        "semantic_issue_count": len(semantic_issues),
        "policy_results": policy_results,
        "reviewed_policy_count": reviewed_policy_count,
        "available_policy_count": available_policy_count,
        "period_resolution": period_resolution,
        "boundary": (
            "Compatibility checks explicit dataset identity and mechanically verifiable "
            "bindings only. Equal schemas do not establish logical dataset identity, "
            "and value changes do not change semantic meaning."
        ),
    }


def build_snapshot_attachment(
    layer: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    """Bind one uploaded snapshot to a reusable semantic version when compatible."""

    compatibility = assess_snapshot_compatibility(layer, profile)
    fingerprint = compatibility["snapshot_fingerprint"]
    return {
        "schema_version": "0.1",
        "attachment_status": (
            "attached" if compatibility["semantic_layer_reusable"] else "rejected"
        ),
        "dataset_contract_id": compatibility["dataset_contract_id"],
        "semantic_layer_id": layer.get("semantic_layer_id"),
        "semantic_version": layer.get("semantic_version"),
        "snapshot": {
            "snapshot_id": f"snapshot.{fingerprint[:16]}",
            "snapshot_fingerprint": fingerprint,
            "profile_schema_version": profile.get("schema_version"),
            "source": profile.get("source") or {},
        },
        "compatibility": compatibility,
        "boundary": (
            "An attachment reuses reviewed semantics for one compatible snapshot. "
            "It does not regenerate semantic definitions or choose an analysis."
        ),
    }


def validate_semantic_layer(
    layer: dict[str, Any],
    profile: dict[str, Any],
    manifest: dict[str, Any],
    *,
    semantic_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate wiring and provenance without judging semantic truth."""

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    _check_json_schema(
        layer,
        semantic_schema or _load_json(DEFAULT_SEMANTIC_SCHEMA),
        errors,
    )
    if layer.get("schema_version") != SEMANTIC_LAYER_SCHEMA_VERSION:
        _issue(
            errors,
            "unsupported_schema_version",
            "schema_version",
            f"Expected {SEMANTIC_LAYER_SCHEMA_VERSION}.",
        )
    if not isinstance(layer.get("semantic_layer_id"), str) or not layer.get(
        "semantic_layer_id"
    ):
        _issue(
            errors,
            "missing_id",
            "semantic_layer_id",
            "A semantic layer id is required.",
        )

    if (
        not isinstance(layer.get("semantic_version"), int)
        or layer.get("semantic_version", 0) < 1
    ):
        _issue(
            errors,
            "invalid_semantic_version",
            "semantic_version",
            "A positive semantic version is required.",
        )

    snapshot_fingerprint = canonical_snapshot_fingerprint(profile)
    dataset_contract = layer.get("dataset_contract")
    if not isinstance(dataset_contract, dict):
        _issue(errors, "invalid_type", "dataset_contract", "Expected an object.")
        dataset_contract = {}
    contract_id = dataset_contract.get("dataset_contract_id")
    origin_snapshot = dataset_contract.get("origin_snapshot")
    if not isinstance(origin_snapshot, dict):
        origin_snapshot = {}
    origin_snapshot_fingerprint = origin_snapshot.get("snapshot_fingerprint")
    origin_snapshot_matches = origin_snapshot_fingerprint == snapshot_fingerprint

    scope = layer.get("scope")
    if not isinstance(scope, dict):
        _issue(errors, "invalid_type", "scope", "Expected an object.")
        scope = {}
    _check_enum(
        scope.get("coverage_level"), COVERAGE_LEVELS, "scope.coverage_level", errors
    )

    sources, source_index = _records(layer, "sources", "source_id", errors)
    evidence, evidence_index = _records(layer, "evidence", "evidence_id", errors)
    for position, record in enumerate(sources):
        path = f"sources[{position}]"
        _check_enum(
            record.get("authority"), SOURCE_AUTHORITIES, f"{path}.authority", errors
        )
        for field in ("source_type", "locator"):
            if not isinstance(record.get(field), str) or not record.get(field).strip():
                _issue(
                    errors,
                    "missing_source_field",
                    f"{path}.{field}",
                    "A non-empty source field is required.",
                )
    for position, record in enumerate(evidence):
        path = f"evidence[{position}]"
        if record.get("source_id") not in source_index:
            _issue(
                errors,
                "unknown_source",
                f"{path}.source_id",
                f"Unknown source: {record.get('source_id')}",
            )
        _check_enum(
            record.get("confidence"), CONFIDENCE_LEVELS, f"{path}.confidence", errors
        )
        _check_enum(record.get("status"), EVIDENCE_STATUSES, f"{path}.status", errors)
        for field in ("locator", "claim"):
            if not isinstance(record.get(field), str) or not record.get(field).strip():
                _issue(
                    errors,
                    "missing_evidence_field",
                    f"{path}.{field}",
                    "A non-empty evidence field is required.",
                )

    metrics, metric_index = _records(layer, "metrics", "metric_id", errors)
    dimensions, dimension_index = _records(layer, "dimensions", "dimension_id", errors)
    periods, period_index = _records(layer, "periods", "period_id", errors)
    concept_index: dict[str, tuple[str, dict[str, Any]]] = {}
    for kind, records_by_id in (
        ("metric", metric_index),
        ("dimension", dimension_index),
        ("period", period_index),
    ):
        for concept_id, record in records_by_id.items():
            if concept_id in concept_index:
                _issue(
                    errors,
                    "duplicate_concept_id",
                    concept_id,
                    "Concept ids must be unique across all concept types.",
                )
            concept_index[concept_id] = (kind, record)

    profile_columns = profile.get("columns") or {}
    derived_profile_metrics = profile.get("derived_metrics") or {}
    for position, metric in enumerate(metrics):
        path = f"metrics[{position}]"
        _check_enum(metric.get("status"), CONCEPT_STATUSES, f"{path}.status", errors)
        _check_enum(
            metric.get("confidence"), CONFIDENCE_LEVELS, f"{path}.confidence", errors
        )
        _check_assertion_evidence(
            metric,
            status_key="status",
            unknown_value="unknown",
            path=path,
            evidence_index=evidence_index,
            source_index=source_index,
            errors=errors,
            warnings=warnings,
        )
        if metric.get("status") in {"defined", "conditional"}:
            if (
                not isinstance(metric.get("definition"), str)
                or not metric.get("definition").strip()
            ):
                _issue(
                    errors,
                    "missing_semantic_definition",
                    f"{path}.definition",
                    "A defined or conditional metric needs a business definition.",
                )
            if (
                not isinstance(metric.get("metric_class"), str)
                or not metric.get("metric_class").strip()
            ):
                _issue(
                    errors,
                    "missing_metric_class",
                    f"{path}.metric_class",
                    "A defined or conditional metric needs a reviewed metric class.",
                )
            raw_aggregation = metric.get("aggregation")
            aggregation = raw_aggregation if isinstance(raw_aggregation, dict) else {}
            if aggregation.get("default") in {None, "", "unknown"}:
                _issue(
                    errors,
                    "missing_aggregation",
                    f"{path}.aggregation.default",
                    "A defined or conditional metric needs a reviewed aggregation.",
                )
        binding = metric.get("binding")
        if not isinstance(binding, dict):
            _issue(
                errors,
                "invalid_metric_binding",
                f"{path}.binding",
                "Expected an object.",
            )
            continue
        binding_type = binding.get("binding_type")
        if binding_type == "column":
            column = binding.get("column")
            if origin_snapshot_matches and column not in profile_columns:
                _issue(
                    errors,
                    "unknown_column",
                    f"{path}.binding.column",
                    f"Unknown profile column: {column}",
                )
            elif (
                origin_snapshot_matches
                and (profile_columns.get(column) or {}).get("role") != "metric"
            ):
                _issue(
                    warnings,
                    "profile_role_override",
                    f"{path}.binding.column",
                    f"Column {column} is not mechanically classified as a metric.",
                )
        elif binding_type == "derived":
            input_ids = binding.get("input_metric_ids")
            if not isinstance(input_ids, list) or not input_ids:
                _issue(
                    errors,
                    "missing_inputs",
                    f"{path}.binding.input_metric_ids",
                    "A derived metric needs input metric ids.",
                )
            else:
                for metric_id in input_ids:
                    if metric_id not in metric_index:
                        _issue(
                            errors,
                            "unknown_metric",
                            f"{path}.binding.input_metric_ids",
                            f"Unknown metric: {metric_id}",
                        )
            if not binding.get("expression"):
                _issue(
                    errors,
                    "missing_expression",
                    f"{path}.binding.expression",
                    "A derived metric needs an expression.",
                )
            label = metric.get("label")
            if origin_snapshot_matches and label not in derived_profile_metrics:
                _issue(
                    warnings,
                    "unprofiled_derived_metric",
                    f"{path}.label",
                    "The derived metric is semantic-only and will require data preparation before rendering.",
                )
        else:
            _issue(
                errors,
                "invalid_metric_binding",
                f"{path}.binding.binding_type",
                "Expected column or derived.",
            )
        raw_aggregation = metric.get("aggregation")
        aggregation = raw_aggregation if isinstance(raw_aggregation, dict) else {}
        weight_metric_id = aggregation.get("weight_metric_id")
        if weight_metric_id is not None and weight_metric_id not in metric_index:
            _issue(
                errors,
                "unknown_metric",
                f"{path}.aggregation.weight_metric_id",
                f"Unknown metric: {weight_metric_id}",
            )
        for key in ("compatible_dimension_ids", "forbidden_dimension_ids"):
            for dimension_id in metric.get(key) or []:
                if dimension_id not in dimension_index:
                    _issue(
                        errors,
                        "unknown_dimension",
                        f"{path}.{key}",
                        f"Unknown dimension: {dimension_id}",
                    )

    for position, dimension in enumerate(dimensions):
        path = f"dimensions[{position}]"
        _check_enum(dimension.get("status"), CONCEPT_STATUSES, f"{path}.status", errors)
        _check_enum(
            dimension.get("confidence"), CONFIDENCE_LEVELS, f"{path}.confidence", errors
        )
        _check_assertion_evidence(
            dimension,
            status_key="status",
            unknown_value="unknown",
            path=path,
            evidence_index=evidence_index,
            source_index=source_index,
            errors=errors,
            warnings=warnings,
        )
        if dimension.get("status") in {"defined", "conditional"}:
            if (
                not isinstance(dimension.get("definition"), str)
                or not dimension.get("definition").strip()
            ):
                _issue(
                    errors,
                    "missing_semantic_definition",
                    f"{path}.definition",
                    "A defined or conditional dimension needs a business definition.",
                )
            if not dimension.get("valid_uses"):
                _issue(
                    errors,
                    "missing_dimension_uses",
                    f"{path}.valid_uses",
                    "A defined or conditional dimension needs at least one valid use.",
                )
        column = dimension.get("column")
        if origin_snapshot_matches and column not in profile_columns:
            _issue(
                errors,
                "unknown_column",
                f"{path}.column",
                f"Unknown profile column: {column}",
            )
        elif origin_snapshot_matches and (profile_columns.get(column) or {}).get(
            "role"
        ) not in {
            "dimension",
            "identifier",
        }:
            _issue(
                warnings,
                "profile_role_override",
                f"{path}.column",
                f"Column {column} is not mechanically classified as a dimension or identifier.",
            )
        parent_id = dimension.get("hierarchy_parent_id")
        if parent_id is not None and parent_id not in dimension_index:
            _issue(
                errors,
                "unknown_dimension",
                f"{path}.hierarchy_parent_id",
                f"Unknown dimension: {parent_id}",
            )

    for position, period in enumerate(periods):
        path = f"periods[{position}]"
        _check_enum(period.get("status"), CONCEPT_STATUSES, f"{path}.status", errors)
        _check_enum(
            period.get("confidence"), CONFIDENCE_LEVELS, f"{path}.confidence", errors
        )
        _check_assertion_evidence(
            period,
            status_key="status",
            unknown_value="unknown",
            path=path,
            evidence_index=evidence_index,
            source_index=source_index,
            errors=errors,
            warnings=warnings,
        )
        if period.get("status") in {"defined", "conditional"}:
            if (
                not isinstance(period.get("definition"), str)
                or not period.get("definition").strip()
            ):
                _issue(
                    errors,
                    "missing_semantic_definition",
                    f"{path}.definition",
                    "A defined or conditional period needs a business definition.",
                )
            if period.get("grain") in {None, "", "unknown"}:
                _issue(
                    errors,
                    "missing_period_grain",
                    f"{path}.grain",
                    "A defined or conditional period needs a reviewed grain.",
                )
            if period.get("calendar") in {None, "", "unknown"}:
                _issue(
                    errors,
                    "missing_period_calendar",
                    f"{path}.calendar",
                    "A defined or conditional period needs a reviewed calendar.",
                )
        column = period.get("column")
        if origin_snapshot_matches and column not in profile_columns:
            _issue(
                errors,
                "unknown_column",
                f"{path}.column",
                f"Unknown profile column: {column}",
            )
        elif (
            origin_snapshot_matches
            and (profile_columns.get(column) or {}).get("role") != "period"
        ):
            _issue(
                warnings,
                "profile_role_override",
                f"{path}.column",
                f"Column {column} is not mechanically classified as a period.",
            )

    period_rules, period_rule_index = _records(
        layer, "period_rules", "period_rule_id", errors
    )
    expected_scope_by_rule = {
        "all_available": "all_available",
        "latest_available_period": "single",
        "trailing_periods": "single",
        "current_ytd": "single",
        "current_vs_prior_year": "comparison_pair",
        "current_ytd_vs_prior_ytd": "comparison_pair",
        "caller_bounded": "single",
    }
    for position, period_rule in enumerate(period_rules):
        path = f"period_rules[{position}]"
        rule_type = period_rule.get("rule_type")
        scope_type = period_rule.get("scope_type")
        _check_enum(rule_type, PERIOD_RULE_TYPES, f"{path}.rule_type", errors)
        _check_enum(scope_type, PERIOD_SCOPE_TYPES, f"{path}.scope_type", errors)
        _check_enum(
            period_rule.get("status"), CONCEPT_STATUSES, f"{path}.status", errors
        )
        _check_enum(
            period_rule.get("confidence"),
            CONFIDENCE_LEVELS,
            f"{path}.confidence",
            errors,
        )
        _check_assertion_evidence(
            period_rule,
            status_key="status",
            unknown_value="unknown",
            path=path,
            evidence_index=evidence_index,
            source_index=source_index,
            errors=errors,
            warnings=warnings,
        )
        if period_rule.get("period_id") not in period_index:
            _issue(
                errors,
                "unknown_period",
                f"{path}.period_id",
                f"Unknown period: {period_rule.get('period_id')}",
            )
        expected_scope = expected_scope_by_rule.get(str(rule_type))
        if expected_scope is not None and scope_type != expected_scope:
            _issue(
                errors,
                "period_rule_scope_mismatch",
                f"{path}.scope_type",
                f"Rule {rule_type} requires scope type {expected_scope}.",
            )
        parameters = period_rule.get("parameters")
        if not isinstance(parameters, dict):
            _issue(errors, "invalid_type", f"{path}.parameters", "Expected an object.")
            parameters = {}
        if rule_type in {
            "trailing_periods",
            "current_vs_prior_year",
        } and not isinstance(parameters.get("window_length"), int):
            _issue(
                errors,
                "missing_period_rule_window_length",
                f"{path}.parameters.window_length",
                f"Rule {rule_type} requires a positive window length.",
            )
        requires_runtime_bounds = parameters.get("requires_runtime_bounds")
        if rule_type == "caller_bounded" and requires_runtime_bounds is not True:
            _issue(
                errors,
                "caller_bounded_rule_requires_runtime_bounds",
                f"{path}.parameters.requires_runtime_bounds",
                "A caller-bounded rule must require runtime bounds.",
            )
        elif rule_type != "caller_bounded" and requires_runtime_bounds is not False:
            _issue(
                errors,
                "unexpected_runtime_bounds_requirement",
                f"{path}.parameters.requires_runtime_bounds",
                f"Rule {rule_type} resolves from snapshot data and must not require caller bounds.",
            )

    analysis_tasks = manifest.get("analysis_tasks") or {}
    catalog_index = _analysis_catalog_index(manifest)
    role_registry = manifest.get("role_registry") or {}
    policies, _ = _records(layer, "analysis_policies", "analysis_id", errors)
    policy_results: list[dict[str, Any]] = []
    for position, policy in enumerate(policies):
        path = f"analysis_policies[{position}]"
        validity = policy.get("validity")
        _check_enum(validity, ANALYSIS_VALIDITIES, f"{path}.validity", errors)
        _check_enum(
            policy.get("confidence"), CONFIDENCE_LEVELS, f"{path}.confidence", errors
        )
        _check_assertion_evidence(
            policy,
            status_key="validity",
            unknown_value="unknown",
            path=path,
            evidence_index=evidence_index,
            source_index=source_index,
            errors=errors,
            warnings=warnings,
        )
        if validity != "unknown":
            for field in ("question_family", "business_purpose"):
                if (
                    not isinstance(policy.get(field), str)
                    or not policy.get(field).strip()
                ):
                    _issue(
                        errors,
                        "missing_analysis_field",
                        f"{path}.{field}",
                        "A reviewed analysis policy needs a non-empty field.",
                    )
        task_ids = policy.get("analysis_task_ids") or []
        emphases = policy.get("selection_emphases") or []
        for task_id in task_ids:
            if task_id not in analysis_tasks:
                _issue(
                    errors,
                    "unknown_analysis_task",
                    f"{path}.analysis_task_ids",
                    f"Unknown analysis task: {task_id}",
                )
        catalog_records = []
        for emphasis in emphases:
            record = catalog_index.get(str(emphasis))
            if record is None:
                _issue(
                    errors,
                    "unknown_selection_emphasis",
                    f"{path}.selection_emphases",
                    f"Unknown selection emphasis: {emphasis}",
                )
                continue
            catalog_records.append(record)
            if task_ids and not set(task_ids) & set(record["analysis_task_ids"]):
                _issue(
                    errors,
                    "task_emphasis_mismatch",
                    f"{path}.selection_emphases",
                    f"Selection emphasis {emphasis} is not registered under {task_ids}.",
                )
        if validity in {"valid", "conditional"} and not catalog_records:
            _issue(
                errors,
                "missing_manifest_join",
                f"{path}.selection_emphases",
                "A valid or conditional policy must join to a manifest selection emphasis.",
            )

        role_bindings = policy.get("role_bindings")
        if not isinstance(role_bindings, dict):
            _issue(
                errors, "invalid_type", f"{path}.role_bindings", "Expected an object."
            )
            role_bindings = {}
        for role, binding in role_bindings.items():
            _check_role_binding(
                role=str(role),
                binding=binding,
                path=f"{path}.role_bindings.{role}",
                concept_index=concept_index,
                role_registry=role_registry,
                source_index=source_index,
                errors=errors,
                warnings=warnings,
            )

        period_rule_id = policy.get("period_rule_id")
        if period_rule_id is not None and period_rule_id not in period_rule_index:
            _issue(
                errors,
                "unknown_period_rule",
                f"{path}.period_rule_id",
                f"Unknown period rule: {period_rule_id}",
            )

        policy_semantic_mismatches = _policy_semantic_mismatches(
            validity=validity,
            role_bindings=role_bindings,
            period_rule_id=period_rule_id,
            concept_index=concept_index,
            period_rule_index=period_rule_index,
        )
        data_preparation_requirements = []
        for role, binding in role_bindings.items():
            for concept_id in _binding_concept_ids(binding):
                concept = concept_index.get(concept_id)
                metric_binding = (
                    concept[1].get("binding")
                    if concept is not None and concept[0] == "metric"
                    else None
                )
                if (
                    isinstance(metric_binding, dict)
                    and metric_binding.get("binding_type") == "derived"
                ):
                    data_preparation_requirements.append(
                        {
                            "role": role,
                            "metric_id": concept_id,
                            "requirement": "materialize_reviewed_derived_metric",
                            "expression": metric_binding.get("expression"),
                        }
                    )

        role_sets = [
            role_set
            for record in catalog_records
            for role_set in record.get("required_role_sets") or []
        ]
        role_set_results = []
        for role_set in role_sets:
            required_role_contracts = role_set.get("roles") or []
            required_roles = [item["role"] for item in required_role_contracts]
            missing_roles = [
                role for role in required_roles if role not in role_bindings
            ]
            unresolved_roles = [
                role
                for role in required_roles
                if role in role_bindings
                and isinstance(role_bindings[role], dict)
                and not _binding_is_resolved(role_bindings[role])
            ]
            scope_contract = role_set.get("period_scope_contract") or {}
            comparison_scope_required = bool(
                scope_contract.get("comparison_pair_required_for_render", False)
            )
            explicit_scope_required = bool(
                scope_contract.get("scope_required_for_render", False)
            )
            scope_missing = (
                comparison_scope_required or explicit_scope_required
            ) and period_rule_id is None
            wrong_scope_type = False
            if comparison_scope_required and period_rule_id in period_rule_index:
                wrong_scope_type = (
                    period_rule_index[period_rule_id].get("scope_type")
                    != "comparison_pair"
                )
            semantic_mismatches = list(policy_semantic_mismatches)
            for role_contract in required_role_contracts:
                role = role_contract["role"]
                accepted_metric_classes = set(
                    role_contract.get("accepted_metric_classes") or []
                )
                if not accepted_metric_classes:
                    continue
                binding = role_bindings.get(role)
                for concept_id in _binding_concept_ids(binding):
                    concept = concept_index.get(concept_id)
                    if concept is None or concept[0] != "metric":
                        continue
                    metric_class = concept[1].get("metric_class")
                    if metric_class not in accepted_metric_classes:
                        semantic_mismatches.append(
                            {
                                "code": "metric_class_not_accepted",
                                "role": role,
                                "metric_id": concept_id,
                                "metric_class": metric_class,
                                "accepted_metric_classes": sorted(
                                    accepted_metric_classes
                                ),
                                "message": (
                                    f"Role {role} does not accept metric class "
                                    f"{metric_class!r}."
                                ),
                            }
                        )
            complete = (
                not missing_roles
                and not unresolved_roles
                and not scope_missing
                and not wrong_scope_type
                and not semantic_mismatches
            )
            role_set_results.append(
                {
                    "capability_id": role_set.get("capability_id"),
                    "required_roles": required_roles,
                    "missing_roles": missing_roles,
                    "unresolved_roles": unresolved_roles,
                    "period_rule_required": explicit_scope_required,
                    "comparison_scope_required": comparison_scope_required,
                    "scope_missing": scope_missing,
                    "wrong_scope_type": wrong_scope_type,
                    "semantic_mismatches": semantic_mismatches,
                    "complete": complete,
                }
            )
        has_complete_role_set = any(result["complete"] for result in role_set_results)
        conditions = policy.get("conditions")
        conditional_conditions_complete = validity != "conditional" or (
            isinstance(conditions, list)
            and any(
                isinstance(condition, str) and condition.strip()
                for condition in conditions
            )
        )
        if validity == "valid" and role_sets and not has_complete_role_set:
            _issue(
                errors,
                "incomplete_manifest_role_binding",
                f"{path}.role_bindings",
                "A valid policy must completely bind at least one joined manifest capability.",
            )
        elif validity == "conditional" and role_sets and not has_complete_role_set:
            _issue(
                warnings,
                "conditional_role_binding_incomplete",
                f"{path}.role_bindings",
                "No joined capability is fully bound; the policy conditions must resolve this before use.",
            )
        if validity == "conditional" and not conditional_conditions_complete:
            _issue(
                warnings,
                "conditional_conditions_incomplete",
                f"{path}.conditions",
                "A conditional policy needs at least one explicit, non-empty condition before use.",
            )
        policy_results.append(
            {
                "analysis_id": policy.get("analysis_id"),
                "validity": validity,
                "selection_emphases": emphases,
                "candidate_capability_ids": sorted(
                    {
                        capability_id
                        for record in catalog_records
                        for capability_id in record.get("capability_ids") or []
                    }
                ),
                "role_set_results": role_set_results,
                "has_complete_manifest_role_set": has_complete_role_set,
                "conditional_conditions_complete": conditional_conditions_complete,
                "usable_as_semantic_input": (
                    validity in {"valid", "conditional"}
                    and has_complete_role_set
                    and conditional_conditions_complete
                ),
                "data_preparation_requirements": data_preparation_requirements,
            }
        )

    open_questions, _ = _records(layer, "open_questions", "question_id", errors)
    review = layer.get("review")
    if not isinstance(review, dict):
        _issue(errors, "invalid_type", "review", "Expected an object.")
        review = {}
    _check_enum(review.get("status"), REVIEW_STATUSES, "review.status", errors)
    if review.get("status") == "human_reviewed":
        if not review.get("reviewed_by"):
            _issue(
                errors,
                "missing_reviewer",
                "review.reviewed_by",
                "Human-reviewed layers need a reviewer.",
            )
        _check_iso_date(review.get("reviewed_at"), "review.reviewed_at", errors)
        if not review.get("reviewed_at"):
            _issue(
                errors,
                "missing_review_date",
                "review.reviewed_at",
                "Human-reviewed layers need a review date.",
            )
    if review.get("status") != "draft" and not policies:
        _issue(
            warnings,
            "reviewed_without_policies",
            "analysis_policies",
            "The layer is marked reviewed but contains no analysis policy.",
        )
    if review.get("status") != "draft" and scope.get("coverage_level") == "unreviewed":
        _issue(
            errors,
            "reviewed_layer_has_unreviewed_coverage",
            "scope.coverage_level",
            "A reviewed layer must state a reviewed source-coverage level.",
        )

    boundaries = layer.get("boundaries")
    if not isinstance(boundaries, dict):
        _issue(errors, "invalid_type", "boundaries", "Expected an object.")
    else:
        if boundaries.get("chart_selection_included") is not False:
            _issue(
                errors,
                "semantic_boundary_violation",
                "boundaries.chart_selection_included",
                "The semantic layer must not claim to select a chart.",
            )
        if boundaries.get("rendering_included") is not False:
            _issue(
                errors,
                "semantic_boundary_violation",
                "boundaries.rendering_included",
                "The semantic layer must not claim to render charts.",
            )

    unknown_concepts = sum(
        1
        for record in [*metrics, *dimensions, *periods]
        if record.get("status") == "unknown"
    )
    validity_counts = {
        value: sum(1 for policy in policies if policy.get("validity") == value)
        for value in sorted(ANALYSIS_VALIDITIES)
    }
    review_status = review.get("status")
    usable_policy_count = sum(
        1 for result in policy_results if result["usable_as_semantic_input"]
    )
    if errors:
        semantic_readiness = "contract_invalid"
    elif review_status == "draft":
        semantic_readiness = "draft_unreviewed"
    elif usable_policy_count == 0:
        semantic_readiness = "reviewed_no_usable_analysis_policies"
    elif unknown_concepts:
        semantic_readiness = "reviewed_with_unresolved_concepts"
    else:
        semantic_readiness = "ready_as_scoped_semantic_input"
    assessed_selection_emphases = sorted(
        {
            str(emphasis)
            for policy in policies
            for emphasis in policy.get("selection_emphases") or []
            if str(emphasis) in catalog_index
        }
    )
    unassessed_selection_emphases = sorted(
        set(catalog_index) - set(assessed_selection_emphases)
    )
    snapshot_compatibility = assess_snapshot_compatibility(layer, profile)
    return {
        "schema_version": SEMANTIC_LAYER_SCHEMA_VERSION,
        "semantic_layer_id": layer.get("semantic_layer_id"),
        "semantic_version": layer.get("semantic_version"),
        "status": "contract_valid" if not errors else "contract_invalid",
        "semantic_readiness": semantic_readiness,
        "dataset_contract": {
            "dataset_contract_id": contract_id,
            "contract_version": dataset_contract.get("contract_version"),
        },
        "snapshot": {
            "dataset_id": profile.get("dataset_id"),
            "snapshot_fingerprint": snapshot_fingerprint,
            "is_origin_snapshot": origin_snapshot_matches,
            "compatibility": snapshot_compatibility,
        },
        "counts": {
            "sources": len(sources),
            "evidence": len(evidence),
            "metrics": len(metrics),
            "dimensions": len(dimensions),
            "periods": len(periods),
            "period_rules": len(period_rules),
            "analysis_policies": len(policies),
            "assessed_selection_emphases": len(assessed_selection_emphases),
            "unassessed_selection_emphases": len(unassessed_selection_emphases),
            "open_questions": len(open_questions),
            "unknown_concepts": unknown_concepts,
            "analysis_validities": validity_counts,
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "policy_results": policy_results,
        "analysis_coverage": {
            "manifest_selection_emphasis_count": len(catalog_index),
            "assessed_selection_emphases": assessed_selection_emphases,
            "unassessed_selection_emphases": unassessed_selection_emphases,
            "unlisted_policy_default": "unknown",
        },
        "errors": errors,
        "warnings": warnings,
        "boundary": (
            "Pass means the stable semantic document is internally coherent and "
            "wired to the manifest. Snapshot compatibility is reported separately; "
            "neither result proves that business judgments are true."
        ),
    }


def build_semantic_acceptance_summary(
    profile: dict[str, Any],
    layer: dict[str, Any],
    manifest: dict[str, Any],
    *,
    dataset_path: Path,
    layer_path: Path,
    manifest_path: Path,
    schema_path: Path,
    source_paths: list[Path],
    snapshot_cases: list[tuple[str, str, Path, dict[str, Any]]] | None = None,
    snapshot_suite_path: Path | None = None,
) -> dict[str, Any]:
    """Bind reviewed semantics and recurring-snapshot proofs to exact digests."""

    validation = validate_semantic_layer(
        layer,
        profile,
        manifest,
        semantic_schema=_load_json(schema_path),
    )
    origin_attachment = build_snapshot_attachment(layer, profile)
    compatibility_cases = [
        {
            "case_id": "origin_snapshot",
            "expected_status": "compatible",
            "dataset_path": dataset_path,
            "attachment": origin_attachment,
        },
        *[
            {
                "case_id": case_id,
                "expected_status": expected_status,
                "dataset_path": case_path,
                "attachment": build_snapshot_attachment(layer, case_profile),
            }
            for case_id, expected_status, case_path, case_profile in (
                snapshot_cases or []
            )
        ],
    ]
    compatibility_passed = all(
        case["attachment"]["compatibility"]["status"] == case["expected_status"]
        for case in compatibility_cases
    )
    acceptance_passed = (
        validation["status"] == "contract_valid"
        and validation["semantic_readiness"] == "ready_as_scoped_semantic_input"
        and compatibility_passed
    )
    return {
        "schema_version": "0.2",
        "result": "pass" if acceptance_passed else "fail",
        "semantic_layer_id": layer.get("semantic_layer_id"),
        "semantic_version": layer.get("semantic_version"),
        "inputs": {
            "manifest": {
                "path": _portable_component_path(manifest_path),
                "sha256": _sha256_file(manifest_path),
            },
            "semantic_schema": {
                "path": _portable_component_path(schema_path),
                "sha256": _sha256_file(schema_path),
            },
            "dataset": {
                "path": _portable_component_path(dataset_path),
                "sha256": _sha256_file(dataset_path),
            },
            "semantic_layer": {
                "path": _portable_component_path(layer_path),
                "sha256": _sha256_file(layer_path),
            },
            "semantic_sources": [
                {
                    "path": _portable_component_path(source_path),
                    "sha256": _sha256_file(source_path),
                }
                for source_path in source_paths
            ],
            "snapshot_suite": (
                {
                    "path": _portable_component_path(snapshot_suite_path),
                    "sha256": _sha256_file(snapshot_suite_path),
                }
                if snapshot_suite_path is not None
                else None
            ),
            "snapshot_cases": [
                {
                    "case_id": case["case_id"],
                    "path": _portable_component_path(case["dataset_path"]),
                    "sha256": _sha256_file(case["dataset_path"]),
                }
                for case in compatibility_cases
            ],
        },
        "dataset_contract": {
            "dataset_contract_id": (
                (layer.get("dataset_contract") or {}).get("dataset_contract_id")
            ),
            "contract_version": (
                (layer.get("dataset_contract") or {}).get("contract_version")
            ),
        },
        "validation": {
            "status": validation["status"],
            "semantic_readiness": validation["semantic_readiness"],
            "counts": validation["counts"],
            "analysis_coverage": validation["analysis_coverage"],
            "errors": validation["errors"],
            "warnings": validation["warnings"],
        },
        "policy_proof": [
            {
                "analysis_id": result["analysis_id"],
                "validity": result["validity"],
                "candidate_capability_ids": result["candidate_capability_ids"],
                "has_complete_manifest_role_set": result[
                    "has_complete_manifest_role_set"
                ],
                "data_preparation_requirements": result[
                    "data_preparation_requirements"
                ],
            }
            for result in validation["policy_results"]
        ],
        "snapshot_reuse_proof": [
            {
                "case_id": case["case_id"],
                "expected_status": case["expected_status"],
                "actual_status": case["attachment"]["compatibility"]["status"],
                "semantic_layer_reusable": case["attachment"]["compatibility"][
                    "semantic_layer_reusable"
                ],
                "snapshot_fingerprint": case["attachment"]["snapshot"][
                    "snapshot_fingerprint"
                ],
                "extension_columns": case["attachment"]["compatibility"][
                    "extension_columns"
                ],
                "available_policy_count": case["attachment"]["compatibility"][
                    "available_policy_count"
                ],
                "period_resolution_counts": case["attachment"]["compatibility"][
                    "period_resolution"
                ]["counts"],
                "resolved_period_rules": [
                    {
                        "period_rule_id": resolution["period_rule_id"],
                        "resolution_status": resolution["resolution_status"],
                        "resolved_scope": resolution["resolved_scope"],
                    }
                    for resolution in case["attachment"]["compatibility"][
                        "period_resolution"
                    ]["results"]
                ],
            }
            for case in compatibility_cases
        ],
        "boundary": (
            "This acceptance proves stable semantic-contract wiring and expected "
            "reuse outcomes for exact packaged snapshots. It does not infer dataset "
            "identity, prove semantic truth, select an analysis, or render a chart."
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create an unreviewed scaffold.")
    init_parser.add_argument("--profile", type=Path, required=True)
    init_parser.add_argument("--output", type=Path, required=True)
    init_parser.add_argument("--dataset-contract-id")
    init_parser.add_argument("--semantic-layer-id")
    init_parser.add_argument("--semantic-version", type=int, default=1)
    init_parser.add_argument(
        "--identity-method",
        choices=["caller_assigned", "source_connector", "project_configuration"],
        default="caller_assigned",
    )
    init_parser.add_argument("--identity-value")

    context_parser = subparsers.add_parser(
        "context", help="Build a model-facing semantic authoring context."
    )
    context_parser.add_argument("--profile", type=Path, required=True)
    context_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    context_parser.add_argument("--layer", type=Path)
    context_parser.add_argument("--output", type=Path, required=True)

    validate_parser = subparsers.add_parser(
        "validate", help="Validate semantic wiring against profile and manifest."
    )
    validate_parser.add_argument("--layer", type=Path, required=True)
    validate_parser.add_argument("--profile", type=Path, required=True)
    validate_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    validate_parser.add_argument("--schema", type=Path, default=DEFAULT_SEMANTIC_SCHEMA)
    validate_parser.add_argument("--output", type=Path)

    attach_parser = subparsers.add_parser(
        "attach", help="Attach a compatible snapshot to an existing semantic version."
    )
    attach_parser.add_argument("--layer", type=Path, required=True)
    attach_parser.add_argument("--profile", type=Path, required=True)
    attach_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    attach_parser.add_argument("--schema", type=Path, default=DEFAULT_SEMANTIC_SCHEMA)
    attach_parser.add_argument("--output", type=Path, required=True)

    acceptance_parser = subparsers.add_parser(
        "acceptance", help="Validate a reviewed fixture and bind exact digests."
    )
    acceptance_parser.add_argument("--dataset", type=Path, required=True)
    acceptance_parser.add_argument("--dataset-id", required=True)
    acceptance_parser.add_argument("--layer", type=Path, required=True)
    acceptance_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    acceptance_parser.add_argument(
        "--schema", type=Path, default=DEFAULT_SEMANTIC_SCHEMA
    )
    acceptance_parser.add_argument("--source", type=Path, action="append", default=[])
    acceptance_parser.add_argument("--snapshot-suite", type=Path)
    acceptance_parser.add_argument("--output", type=Path, required=True)
    return parser


def _load_snapshot_cases(
    suite_path: Path | None, dataset_contract_id: str
) -> list[tuple[str, str, Path, dict[str, Any]]]:
    if suite_path is None:
        return []
    suite = _load_json(suite_path)
    if suite.get("dataset_contract_id") != dataset_contract_id:
        raise ValueError(
            "Snapshot suite dataset_contract_id does not match the acceptance run."
        )
    cases: list[tuple[str, str, Path, dict[str, Any]]] = []
    for raw_case in suite.get("cases") or []:
        if not isinstance(raw_case, dict):
            raise ValueError("Snapshot suite cases must be objects.")
        case_id = str(raw_case.get("case_id") or "")
        expected_status = str(raw_case.get("expected_status") or "")
        relative_path = raw_case.get("dataset")
        if not case_id or expected_status not in SNAPSHOT_COMPATIBILITY_STATUSES:
            raise ValueError(f"Invalid snapshot compatibility case: {raw_case!r}")
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError(f"Snapshot case {case_id} needs a dataset path.")
        dataset_path = (suite_path.parent / relative_path).resolve()
        profile = _profile_dataset_for_acceptance(dataset_path, dataset_contract_id)
        cases.append((case_id, expected_status, dataset_path, profile))
    return cases


def main(argv: list[str] | None = None) -> int:
    """Run semantic scaffolding, context, validation, or fixture acceptance."""

    args = _parser().parse_args(argv)
    if args.command == "acceptance":
        profile = _profile_dataset_for_acceptance(args.dataset, args.dataset_id)
        manifest = _load_json(args.manifest)
        layer = _load_json(args.layer)
        snapshot_cases = _load_snapshot_cases(args.snapshot_suite, args.dataset_id)
        payload = build_semantic_acceptance_summary(
            profile,
            layer,
            manifest,
            dataset_path=args.dataset,
            layer_path=args.layer,
            manifest_path=args.manifest,
            schema_path=args.schema,
            source_paths=args.source,
            snapshot_cases=snapshot_cases,
            snapshot_suite_path=args.snapshot_suite,
        )
        _write_json(args.output, payload)
        sys.stdout.write(f"{args.output}\n")
        return 0 if payload["result"] == "pass" else 1

    profile = _load_json(args.profile)
    if args.command == "init":
        payload = build_semantic_layer_scaffold(
            profile,
            dataset_contract_id=args.dataset_contract_id,
            semantic_layer_id=args.semantic_layer_id,
            semantic_version=args.semantic_version,
            identity_method=args.identity_method,
            identity_value=args.identity_value,
            profile_locator=str(args.profile),
        )
        _write_json(args.output, payload)
        sys.stdout.write(f"{args.output}\n")
        return 0

    manifest = _load_json(args.manifest)
    if args.command == "context":
        layer = _load_json(args.layer) if args.layer else None
        payload = build_authoring_context(profile, manifest, semantic_layer=layer)
        _write_json(args.output, payload)
        sys.stdout.write(f"{args.output}\n")
        return 0

    layer = _load_json(args.layer)
    report = validate_semantic_layer(
        layer,
        profile,
        manifest,
        semantic_schema=_load_json(args.schema),
    )
    if args.command == "attach":
        attachment = build_snapshot_attachment(layer, profile)
        attachment["semantic_contract_validation"] = {
            "status": report["status"],
            "semantic_readiness": report["semantic_readiness"],
            "errors": report["errors"],
        }
        if report["status"] != "contract_valid":
            attachment["attachment_status"] = "rejected"
        _write_json(args.output, attachment)
        sys.stdout.write(f"{args.output}\n")
        return 0 if attachment["attachment_status"] == "attached" else 1
    if args.output:
        _write_json(args.output, report)
        sys.stdout.write(f"{args.output}\n")
    else:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if report["status"] == "contract_valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
