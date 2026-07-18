"""Create and validate dataset-specific Reporting Engine semantic layers.

The semantic layer records reviewed business meaning and analysis validity. The
deterministic code in this module only scaffolds mechanical observations and
checks contract consistency; it never promotes profiler guesses into semantic
facts or chooses a chart.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

__all__ = [
    "SEMANTIC_LAYER_SCHEMA_VERSION",
    "build_semantic_acceptance_summary",
    "build_authoring_context",
    "build_semantic_layer_scaffold",
    "canonical_profile_fingerprint",
    "main",
    "validate_semantic_layer",
]

SEMANTIC_LAYER_SCHEMA_VERSION = "0.1"
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
    "period_scope",
    "literal",
    "derived",
    "package",
    "unresolved",
}
PERIOD_SCOPE_TYPES = {"single", "comparison_pair", "rolling", "all_available"}


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


def canonical_profile_fingerprint(profile: dict[str, Any]) -> str:
    """Hash profile content while ignoring its machine-specific source path."""

    encoded = json.dumps(
        _normalized_profile(profile),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
                "profile_observation": {
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
                "profile_observation": {
                    "source_role": source_role,
                    "confidence": candidate.get("confidence"),
                    "distinct_count": candidate.get("distinct_count"),
                    "cardinality_class": candidate.get("cardinality_class"),
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
                "profile_observation": {
                    "confidence": candidate.get("confidence"),
                    "grain": candidate.get("grain"),
                    "parseability": candidate.get("period_parseability") or {},
                    "minimum": candidate.get("min"),
                    "maximum": candidate.get("max"),
                },
            }
        )
    return records


def build_semantic_layer_scaffold(
    profile: dict[str, Any],
    *,
    semantic_layer_id: str | None = None,
    profile_locator: str | None = None,
) -> dict[str, Any]:
    """Create an unreviewed scaffold without making semantic assertions."""

    dataset_id = str(profile.get("dataset_id") or "dataset")
    layer_id = semantic_layer_id or f"{_slug(dataset_id)}.reporting_semantics"
    return {
        "schema_version": SEMANTIC_LAYER_SCHEMA_VERSION,
        "semantic_layer_id": layer_id,
        "dataset_profile": {
            "dataset_id": dataset_id,
            "profile_schema_version": str(profile.get("schema_version") or "unknown"),
            "profile_fingerprint": canonical_profile_fingerprint(profile),
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
        "period_scopes": [],
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
                    "reviewed concepts and period scopes?"
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
                "Schema, identifiers, evidence references, profile bindings, manifest "
                "intent references, and required role coverage only."
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
        "dataset_profile_fingerprint": canonical_profile_fingerprint(profile),
        "dataset_profile": profile,
        "semantic_layer_draft": scaffold,
        "analysis_catalog": _analysis_catalog(manifest),
        "authoring_rules": [
            "Inspect source data and business evidence; profiler labels are candidates, not semantic facts.",
            "Keep metric definitions, aggregation, units, dimensions, calendars, and period scopes explicit.",
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


def _schema_invalid_report(
    layer: dict[str, Any],
    profile: dict[str, Any],
    manifest: dict[str, Any],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a stable report without traversing schema-invalid structures."""

    profile_binding = layer.get("dataset_profile")
    expected_fingerprint = (
        profile_binding.get("profile_fingerprint")
        if isinstance(profile_binding, dict)
        else None
    )
    actual_fingerprint = canonical_profile_fingerprint(profile)
    catalog_index = _analysis_catalog_index(manifest)
    unassessed_selection_emphases = sorted(catalog_index)

    record_keys = (
        "sources",
        "evidence",
        "metrics",
        "dimensions",
        "periods",
        "period_scopes",
        "analysis_policies",
        "open_questions",
    )
    record_counts = {
        key: len(value) if isinstance((value := layer.get(key)), list) else 0
        for key in record_keys
    }
    return {
        "schema_version": SEMANTIC_LAYER_SCHEMA_VERSION,
        "semantic_layer_id": layer.get("semantic_layer_id"),
        "status": "contract_invalid",
        "semantic_readiness": "contract_invalid",
        "dataset_profile": {
            "dataset_id": profile.get("dataset_id"),
            "expected_fingerprint": expected_fingerprint,
            "actual_fingerprint": actual_fingerprint,
            "matches": expected_fingerprint == actual_fingerprint,
        },
        "counts": {
            **record_counts,
            "assessed_selection_emphases": 0,
            "unassessed_selection_emphases": len(unassessed_selection_emphases),
            "unknown_concepts": 0,
            "analysis_validities": {value: 0 for value in sorted(ANALYSIS_VALIDITIES)},
            "errors": len(errors),
            "warnings": 0,
        },
        "policy_results": [],
        "analysis_coverage": {
            "manifest_selection_emphasis_count": len(catalog_index),
            "assessed_selection_emphases": [],
            "unassessed_selection_emphases": unassessed_selection_emphases,
            "unlisted_policy_default": "unknown",
        },
        "errors": errors,
        "warnings": [],
        "boundary": (
            "Schema-invalid documents are rejected before semantic wiring is "
            "evaluated. Passing schema validation would not prove that business "
            "judgments are true."
        ),
    }


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
    period_scope_id: Any,
    concept_index: dict[str, tuple[str, dict[str, Any]]],
    period_scope_index: dict[str, dict[str, Any]],
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
    if period_scope_id in period_scope_index:
        scope_status = period_scope_index[period_scope_id].get("status")
        if scope_status not in allowed_statuses:
            mismatches.append(
                {
                    "code": "period_scope_not_ready",
                    "period_scope_id": period_scope_id,
                    "message": (
                        f"{validity} policy cannot use period scope status "
                        f"{scope_status!r}."
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
    if period_scope_id in period_scope_index:
        scope_period_id = period_scope_index[period_scope_id].get("period_id")
        scope_period = concept_index.get(str(scope_period_id))
        if scope_period is not None and scope_period[0] == "period":
            periods.append((str(scope_period_id), scope_period[1]))
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
    period_scope_index: dict[str, dict[str, Any]],
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
    elif binding_type == "period_scope":
        scope_id = binding.get("period_scope_id")
        if scope_id not in period_scope_index:
            _issue(
                errors,
                "unknown_period_scope",
                f"{path}.period_scope_id",
                f"Unknown period scope: {scope_id}",
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

    if (
        binding_type in {"literal", "derived", "package", "period_scope"}
        and expected_kinds
    ):
        _issue(
            warnings,
            "non_concept_role_binding",
            path,
            f"Role {role} is bound through {binding_type}; deterministic kind checking is limited.",
        )


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
    if errors:
        return _schema_invalid_report(layer, profile, manifest, errors)
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

    actual_fingerprint = canonical_profile_fingerprint(profile)
    profile_binding = layer.get("dataset_profile")
    if not isinstance(profile_binding, dict):
        _issue(errors, "invalid_type", "dataset_profile", "Expected an object.")
        profile_binding = {}
    if profile_binding.get("dataset_id") != profile.get("dataset_id"):
        _issue(
            errors,
            "dataset_id_mismatch",
            "dataset_profile.dataset_id",
            f"Expected {profile.get('dataset_id')!r} from the supplied profile.",
        )
    expected_fingerprint = profile_binding.get("profile_fingerprint")
    if expected_fingerprint != actual_fingerprint:
        _issue(
            errors,
            "profile_fingerprint_mismatch",
            "dataset_profile.profile_fingerprint",
            "The semantic layer is not bound to the supplied profile content.",
        )

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
            if column not in profile_columns:
                _issue(
                    errors,
                    "unknown_column",
                    f"{path}.binding.column",
                    f"Unknown profile column: {column}",
                )
            elif (profile_columns.get(column) or {}).get("role") != "metric":
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
            if label not in derived_profile_metrics:
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
        if column not in profile_columns:
            _issue(
                errors,
                "unknown_column",
                f"{path}.column",
                f"Unknown profile column: {column}",
            )
        elif (profile_columns.get(column) or {}).get("role") not in {
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
        if column not in profile_columns:
            _issue(
                errors,
                "unknown_column",
                f"{path}.column",
                f"Unknown profile column: {column}",
            )
        elif (profile_columns.get(column) or {}).get("role") != "period":
            _issue(
                warnings,
                "profile_role_override",
                f"{path}.column",
                f"Column {column} is not mechanically classified as a period.",
            )

    period_scopes, period_scope_index = _records(
        layer, "period_scopes", "period_scope_id", errors
    )
    for position, period_scope in enumerate(period_scopes):
        path = f"period_scopes[{position}]"
        scope_type = period_scope.get("scope_type")
        _check_enum(scope_type, PERIOD_SCOPE_TYPES, f"{path}.scope_type", errors)
        _check_enum(
            period_scope.get("status"), CONCEPT_STATUSES, f"{path}.status", errors
        )
        _check_enum(
            period_scope.get("confidence"),
            CONFIDENCE_LEVELS,
            f"{path}.confidence",
            errors,
        )
        _check_assertion_evidence(
            period_scope,
            status_key="status",
            unknown_value="unknown",
            path=path,
            evidence_index=evidence_index,
            source_index=source_index,
            errors=errors,
            warnings=warnings,
        )
        if period_scope.get("period_id") not in period_index:
            _issue(
                errors,
                "unknown_period",
                f"{path}.period_id",
                f"Unknown period: {period_scope.get('period_id')}",
            )
        windows = period_scope.get("windows")
        if not isinstance(windows, list):
            _issue(errors, "invalid_type", f"{path}.windows", "Expected a list.")
            windows = []
        roles = []
        for window_position, window in enumerate(windows):
            window_path = f"{path}.windows[{window_position}]"
            if not isinstance(window, dict):
                _issue(errors, "invalid_type", window_path, "Expected an object.")
                continue
            roles.append(window.get("role"))
            _check_iso_date(window.get("start"), f"{window_path}.start", errors)
            _check_iso_date(window.get("end"), f"{window_path}.end", errors)
            start = window.get("start")
            end = window.get("end")
            if isinstance(start, str) and isinstance(end, str) and start > end:
                _issue(
                    errors,
                    "invalid_period_window",
                    window_path,
                    "Window start is after window end.",
                )
        if scope_type == "comparison_pair" and not {"current", "baseline"} <= set(
            roles
        ):
            _issue(
                errors,
                "missing_comparison_pair",
                f"{path}.windows",
                "A comparison pair needs current and baseline windows.",
            )
        if scope_type == "single" and "current" not in roles:
            _issue(
                errors,
                "missing_current_window",
                f"{path}.windows",
                "A single scope needs a current window.",
            )
        if scope_type == "rolling" and not windows:
            _issue(
                errors,
                "missing_rolling_window",
                f"{path}.windows",
                "A rolling scope needs a window definition.",
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
                period_scope_index=period_scope_index,
                role_registry=role_registry,
                source_index=source_index,
                errors=errors,
                warnings=warnings,
            )

        period_scope_id = policy.get("period_scope_id")
        if period_scope_id is not None and period_scope_id not in period_scope_index:
            _issue(
                errors,
                "unknown_period_scope",
                f"{path}.period_scope_id",
                f"Unknown period scope: {period_scope_id}",
            )

        policy_semantic_mismatches = _policy_semantic_mismatches(
            validity=validity,
            role_bindings=role_bindings,
            period_scope_id=period_scope_id,
            concept_index=concept_index,
            period_scope_index=period_scope_index,
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
            ) and period_scope_id is None
            wrong_scope_type = False
            if comparison_scope_required and period_scope_id in period_scope_index:
                wrong_scope_type = (
                    period_scope_index[period_scope_id].get("scope_type")
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
                    "period_scope_required": explicit_scope_required,
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
    return {
        "schema_version": SEMANTIC_LAYER_SCHEMA_VERSION,
        "semantic_layer_id": layer.get("semantic_layer_id"),
        "status": "contract_valid" if not errors else "contract_invalid",
        "semantic_readiness": semantic_readiness,
        "dataset_profile": {
            "dataset_id": profile.get("dataset_id"),
            "expected_fingerprint": expected_fingerprint,
            "actual_fingerprint": actual_fingerprint,
            "matches": expected_fingerprint == actual_fingerprint,
        },
        "counts": {
            "sources": len(sources),
            "evidence": len(evidence),
            "metrics": len(metrics),
            "dimensions": len(dimensions),
            "periods": len(periods),
            "period_scopes": len(period_scopes),
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
            "Pass means the semantic document is internally coherent and wired to "
            "the supplied profile and manifest. It does not prove that its business "
            "judgments are true."
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
) -> dict[str, Any]:
    """Bind one reviewed fixture validation to exact packaged input digests."""

    validation = validate_semantic_layer(
        layer,
        profile,
        manifest,
        semantic_schema=_load_json(schema_path),
    )
    acceptance_passed = (
        validation["status"] == "contract_valid"
        and validation["semantic_readiness"] == "ready_as_scoped_semantic_input"
    )
    return {
        "schema_version": "0.1",
        "result": "pass" if acceptance_passed else "fail",
        "semantic_layer_id": layer.get("semantic_layer_id"),
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
        },
        "dataset_profile": {
            "dataset_id": profile.get("dataset_id"),
            "schema_version": profile.get("schema_version"),
            "profile_fingerprint": canonical_profile_fingerprint(profile),
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
        "boundary": (
            "This acceptance proves the exact packaged fixture's semantic "
            "contract wiring. It does not prove semantic truth for another "
            "dataset and does not select or render a chart."
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create an unreviewed scaffold.")
    init_parser.add_argument("--profile", type=Path, required=True)
    init_parser.add_argument("--output", type=Path, required=True)
    init_parser.add_argument("--semantic-layer-id")

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
    acceptance_parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run semantic scaffolding, context, validation, or fixture acceptance."""

    args = _parser().parse_args(argv)
    if args.command == "acceptance":
        profile = _profile_dataset_for_acceptance(args.dataset, args.dataset_id)
        manifest = _load_json(args.manifest)
        layer = _load_json(args.layer)
        payload = build_semantic_acceptance_summary(
            profile,
            layer,
            manifest,
            dataset_path=args.dataset,
            layer_path=args.layer,
            manifest_path=args.manifest,
            schema_path=args.schema,
            source_paths=args.source,
        )
        _write_json(args.output, payload)
        sys.stdout.write(f"{args.output}\n")
        return 0 if payload["result"] == "pass" else 1

    profile = _load_json(args.profile)
    if args.command == "init":
        payload = build_semantic_layer_scaffold(
            profile,
            semantic_layer_id=args.semantic_layer_id,
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
    if args.output:
        _write_json(args.output, report)
        sys.stdout.write(f"{args.output}\n")
    else:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if report["status"] == "contract_valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
