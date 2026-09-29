"""Bind valuation workpapers to evidence, audience and exact review dependencies."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from valuation_engine import ValuationError, calculate_method, decimal

__all__ = [
    "build_valuation",
    "digest",
    "read_json",
    "source_paths",
    "reviewed",
    "CASE_SCHEMA",
]
CASE_SCHEMA = "vera.business_valuation.case.v1"


def digest(value: Any) -> str:
    """Hash complete canonical JSON; a digest does not authenticate a reviewer."""
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def read_json(path: Path) -> dict:
    """Read bounded non-executable JSON with no duplicate keys or nonfinite values."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValuationError("Expected a regular JSON file of at most 8 MiB")

    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ValuationError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject(value: str) -> None:
        raise ValuationError(f"Nonfinite JSON constant: {value}")

    result = json.loads(
        path.read_text(encoding="utf-8-sig"),
        object_pairs_hook=pairs,
        parse_constant=reject,
    )
    if not isinstance(result, dict):
        raise ValuationError("Expected a JSON object")
    return result


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValuationError(message)


def fields(record: Any, required: set[str], optional: set[str] | None = None) -> None:
    require(isinstance(record, dict), "Expected object")
    require(
        not (required - set(record) or set(record) - required - (optional or set())),
        f"Expected fields: {sorted(required)}",
    )


def text(value: Any, label: str) -> str:
    require(
        isinstance(value, str) and bool(value.strip()) and len(value) <= 20000,
        f"Missing or invalid {label}",
    )
    return value


def indexed(records: Any) -> dict[str, dict]:
    require(
        isinstance(records, list) and len(records) <= 2000,
        "Expected bounded record list",
    )
    result = {}
    for record in records:
        require(isinstance(record, dict), "Expected record")
        identifier = record.get("id")
        require(
            isinstance(identifier, str)
            and re.fullmatch(r"[a-z][a-z0-9_-]{0,79}", identifier) is not None,
            "Invalid stable ID",
        )
        require(identifier not in result, "Duplicate record ID")
        result[identifier] = record
    return result


def reviewed(record: Any, expected_digest: str) -> bool:
    """Validate an explicit local attestation, never assert human authentication."""
    if (
        not isinstance(record, dict)
        or record.get("dependency_sha256") != expected_digest
        or record.get("decision") != "accepted"
    ):
        return False
    if not isinstance(record.get("reviewer"), str) or not record["reviewer"].strip():
        return False
    try:
        timestamp = datetime.fromisoformat(record["reviewed_at"])
    except (KeyError, ValueError, TypeError):
        return False
    return timestamp.tzinfo is not None and timestamp.utcoffset() is not None


def source_paths(case: dict, root: Path) -> list[Path]:
    """Close nested sources to a declared root before receipt validation or reads."""
    root = root.resolve(strict=True)
    result = []
    for source in case["sources"]:
        relative = Path(text(source["path"], "source path"))
        require(
            not relative.is_absolute() and ".." not in relative.parts,
            "Source path must be relative and contained",
        )
        path = root / relative
        require(
            not any(
                p.is_symlink()
                for p in (path, *path.parents)
                if p != root and p.is_relative_to(root)
            ),
            "Source symlinks are not allowed",
        )
        resolved = path.resolve(strict=True)
        require(
            resolved.is_relative_to(root) and resolved.is_file(),
            "Source escapes root or is not a file",
        )
        result.append(resolved)
    require(len(set(result)) == len(result), "Duplicate selected source paths")
    return result


def _sources(case: dict, root: Path) -> dict:
    sources = indexed(case["sources"])
    require(bool(sources), "At least one source is required")
    for source, path in zip(sources.values(), source_paths(case, root)):
        fields(
            source,
            {"id", "path", "sha256", "description", "allowed_audiences", "status"},
        )
        text(source["description"], "source description")
        require(
            isinstance(source["allowed_audiences"], list)
            and case["audience"] in source["allowed_audiences"],
            "Source does not allow this report audience",
        )
        require(
            source["status"] in {"reviewed", "unverified"},
            "Invalid source review status",
        )
        require(path.stat().st_size <= 100 * 1024 * 1024, "Source exceeds 100 MiB")
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"],
            "Source bytes changed; import and review a new revision",
        )
    return sources


def _inputs(case: dict, sources: dict) -> dict:
    inputs = indexed(case["inputs"])
    for item in inputs.values():
        fields(
            item,
            {
                "id",
                "value",
                "unit",
                "description",
                "source_ids",
                "locator",
                "kind",
                "status",
            },
            {"benchmark", "plan_calculation_ids"},
        )
        text(item["description"], "input meaning")
        text(item["locator"], "page/cell or evidence locator")
        require(
            item["kind"] in {"fact", "assumption", "hypothesis"}, "Invalid input kind"
        )
        require(
            item["status"] in {"confirmed", "proposed"}, "Invalid input review status"
        )
        require(
            item["unit"] in {case["currency"], "ratio", "multiple"},
            "Unsupported input unit",
        )
        require(
            isinstance(item["source_ids"], list)
            and bool(item["source_ids"])
            and set(item["source_ids"]) <= sources.keys(),
            "Unresolved input sources",
        )
        if item["value"] is not None:
            decimal(item["value"])
        if "plan_calculation_ids" in item:
            require(
                bool(case.get("plan_binding")), "Plan lineage requires a plan binding"
            )
            require(
                isinstance(item["plan_calculation_ids"], list)
                and bool(item["plan_calculation_ids"])
                and all(
                    isinstance(ref, str) and ref for ref in item["plan_calculation_ids"]
                ),
                "Plan lineage requires explicit calculation IDs",
            )
        if "benchmark" in item:
            benchmark = item["benchmark"]
            fields(
                benchmark,
                {
                    "source_url",
                    "observed_on",
                    "published_on",
                    "retrieved_on",
                    "vintage",
                    "definition",
                    "geography",
                    "max_age_days",
                    "selection_reason",
                },
            )
            for key in ("vintage", "definition", "geography", "selection_reason"):
                text(benchmark[key], key)
            url = urlsplit(benchmark["source_url"])
            require(
                url.scheme == "https"
                and bool(url.hostname)
                and not url.username
                and not url.password,
                "Benchmark requires a public HTTPS citation",
            )
            observed, published, retrieved = (
                date.fromisoformat(benchmark[key])
                for key in ("observed_on", "published_on", "retrieved_on")
            )
            cutoff = date.fromisoformat(case["mandate"]["information_cutoff"])
            require(
                observed <= published <= retrieved and published <= cutoff,
                "Benchmark uses inconsistent dates or look-ahead information",
            )
            age = benchmark["max_age_days"]
            require(
                type(age) is int and age >= 0 and (cutoff - observed).days <= age,
                "Benchmark exceeds the explicitly chosen age policy",
            )
    return inputs


def _purpose(case: dict, sources: dict) -> dict:
    """Record an explicit semantic choice without enabling professional profiles."""
    registry = read_json(
        Path(__file__).resolve().parents[1] / "references/purpose-profiles.json"
    )
    selection = case.get("purpose_profile")
    profile = None
    if selection is not None:
        fields(selection, {"id", "selection_reason", "source_ids", "locator"})
        profiles = indexed(registry["profiles"])
        text(selection["id"], "purpose profile ID")
        require(selection["id"] in profiles, "Unknown purpose profile; use custom")
        text(selection["selection_reason"], "purpose selection reason")
        text(selection["locator"], "mandate source locator")
        require(
            isinstance(selection["source_ids"], list)
            and bool(selection["source_ids"])
            and all(isinstance(ref, str) for ref in selection["source_ids"])
            and set(selection["source_ids"]) <= sources.keys(),
            "Purpose selection requires declared mandate sources",
        )
        profile = profiles[selection["id"]]
    return {
        "profile": profile,
        "selection": selection,
        "coverage": registry["coverage"],
        "status": (
            "development_workpapers_only" if profile else "purpose_not_classified"
        ),
        "piv_review": "pending_primary_and_professional_review",
    }


def _checked_timing(method: dict, mandate: dict, plan_bridge: dict | None) -> None:
    """Bind a method's clock and any annual plan flows to their actual periods."""
    if "timing" not in method:
        return
    timing = method["timing"]
    require(
        isinstance(timing, dict)
        and timing.get("valuation_date") == mandate["valuation_date"],
        "Method timing must use the mandate valuation date",
    )
    args = method["inputs"]
    if (
        not plan_bridge
        or not isinstance(args, dict)
        or not isinstance(args.get("flows"), list)
    ):
        return
    annual_ids = plan_bridge["binding"]["annual_input_ids"]
    if any(ref in annual_ids for ref in args["flows"]):
        require(
            args["flows"] == annual_ids
            and timing.get("period_end_dates")
            == [f"{row['year']}-12-31" for row in plan_bridge["annual"]],
            "Annual plan flows must keep their complete annual periods; no monthly relabelling",
        )


def _bind_normalizations(result: dict, groups: dict) -> list[dict]:
    """Keep method formulas and transitive evidence linked to reconciled amounts."""
    from valuation_normalization import normalization_dependencies

    used = sorted({ref for row in result["calculations"] for ref in row["input_ids"]})
    dependent = normalization_dependencies(used, groups)
    for row in result["calculations"]:
        affected = [
            group for group in dependent if group["adjusted_input"] in row["input_ids"]
        ]
        if row["op"] == "input" and affected:
            row["op"] = "sum"
            row["arguments"] = [affected[0]["value_id"]]
        row["input_ids"] = sorted(
            set(row["input_ids"])
            | {ref for group in affected for ref in group["input_ids"]}
        )
    return dependent


def _conclusion(case: dict, active: list, claims: list) -> dict | None:
    """Bind separately reviewed prose to its selected methods and explicit claims."""
    candidate = case.get("conclusion")
    if not candidate:
        return None
    fields(candidate, {"text", "method_ids", "review"}, {"claim_ids"})
    text(candidate["text"], "conclusion")
    require(
        isinstance(candidate["method_ids"], list) and bool(candidate["method_ids"]),
        "Conclusion must name its methods",
    )
    by_id = {row["method_id"]: row for row in active}
    require(
        set(candidate["method_ids"]) <= by_id.keys(),
        "Conclusion references an unselected method",
    )
    claim_ids = candidate.get("claim_ids", [])
    require(
        isinstance(claim_ids, list)
        and all(isinstance(ref, str) for ref in claim_ids)
        and len(set(claim_ids)) == len(claim_ids),
        "Invalid conclusion claim IDs",
    )
    by_claim = {row["id"]: row for row in claims}
    require(set(claim_ids) <= by_claim.keys(), "Conclusion references an unknown claim")
    dependencies = {
        key: by_id[key].get("dependency_sha256") for key in candidate["method_ids"]
    }
    conclusion_hash = digest(
        {
            "text": candidate["text"],
            "methods": dependencies,
            "claims": [by_claim[key] for key in claim_ids],
            "limitations": case["limitations"],
        }
    )
    accepted = (
        all(
            by_id[key]["status"] == "accepted_workpaper"
            for key in candidate["method_ids"]
        )
        and all(by_claim[key]["status"] == "accepted_workpaper" for key in claim_ids)
        and reviewed(candidate["review"], conclusion_hash)
    )
    return {
        **candidate,
        "dependency_sha256": conclusion_hash,
        "status": "accepted_workpaper" if accepted else "draft",
        "narrative_traceability": (
            "explicit_claim_bindings" if claim_ids else "no_structured_claim_bindings"
        ),
    }


def build_valuation(
    case: dict, source_root: Path, *, replay_parent: Path | None = None
) -> dict:
    """Compile independent methods; stale attestations cannot authorize new values."""
    fields(
        case,
        {
            "schema_version",
            "case_id",
            "entity_name",
            "currency",
            "audience",
            "synthetic",
            "mandate",
            "sources",
            "inputs",
            "methods",
            "limitations",
        },
        {
            "conclusion",
            "plan_binding",
            "sensitivity",
            "purpose_profile",
            "normalizations",
            "claims",
        },
    )
    require(case["schema_version"] == CASE_SCHEMA, "Unsupported valuation case schema")
    for key in ("case_id", "entity_name", "audience"):
        text(case[key], key)
    require(
        isinstance(case["currency"], str)
        and re.fullmatch(r"[A-Z]{3}", case["currency"]) is not None,
        "Declare one currency and normalize units first",
    )
    require(type(case["synthetic"]) is bool, "synthetic must be explicit")
    mandate = case["mandate"]
    fields(
        mandate,
        {
            "purpose",
            "subject",
            "valuation_date",
            "information_cutoff",
            "basis_of_value",
            "premise",
            "rights",
            "professional_limitations",
        },
    )
    for key, value in mandate.items():
        text(value, key)
    for key in ("valuation_date", "information_cutoff"):
        date.fromisoformat(mandate[key])
    require(
        isinstance(case["limitations"], list)
        and all(isinstance(x, str) and x.strip() for x in case["limitations"]),
        "Declare limitations explicitly",
    )
    sources = _sources(case, source_root)
    inputs = _inputs(case, sources)
    purpose = _purpose(case, sources)
    from valuation_normalization import build_normalizations

    normalizations, calculations = build_normalizations(case, inputs, sources)
    plan_bridge = None
    if "plan_binding" in case:
        require(
            replay_parent is not None,
            "A bound replay directory is required for the plan bridge",
        )
        from valuation_plan import bridge_plan

        plan_bridge = bridge_plan(case, source_root, replay_parent)
    methods = indexed(case["methods"])
    require(bool(methods), "Select or explicitly exclude valuation methods")
    outputs, issues = [], []
    for group in normalizations.values():
        if group["status"] != "accepted_workpaper":
            issues.append(
                f"Normalization {group['id']}: {group.get('reason', 'adjustment review pending')}"
            )
    for method in methods.values():
        fields(
            method,
            {"id", "kind", "selected", "rationale", "inputs", "limitations"},
            {"bridge", "review", "timing"},
        )
        text(method["rationale"], "method selection rationale")
        text(method["kind"], "method kind")
        require(type(method["selected"]) is bool, "Method selection must be explicit")
        require(
            isinstance(method["limitations"], list)
            and all(isinstance(x, str) and x.strip() for x in method["limitations"]),
            "Invalid method limitations",
        )
        if not method["selected"]:
            outputs.append(
                {
                    "method_id": method["id"],
                    "kind": method["kind"],
                    "status": "excluded",
                    "rationale": method["rationale"],
                }
            )
            continue
        try:
            _checked_timing(method, mandate, plan_bridge)
            result = calculate_method(method, inputs, case["currency"])
            dependent_normalizations = _bind_normalizations(result, normalizations)
        except ValuationError as exc:
            outputs.append(
                {
                    "method_id": method["id"],
                    "kind": method["kind"],
                    "status": "blocked",
                    "reason": str(exc),
                }
            )
            issues.append(f"{method['id']}: {exc}")
            continue
        used = sorted(
            {ref for row in result["calculations"] for ref in row["input_ids"]}
        )
        dependent_bridge = (
            plan_bridge
            if plan_bridge and set(used) & set(case["plan_binding"]["annual_input_ids"])
            else None
        )
        if dependent_bridge:
            used = sorted(
                set(used)
                | set(case["plan_binding"]["cash_operating_taxes"].values())
                | {case["plan_binding"]["opening_operating_nwc"]}
            )
        source_ids = sorted(
            {ref for key in used for ref in inputs[key]["source_ids"]}
            | set((purpose["selection"] or {}).get("source_ids", []))
            | {ref for group in dependent_normalizations for ref in group["source_ids"]}
        )
        if dependent_bridge:
            source_ids = sorted(
                set(source_ids) | set(case["plan_binding"]["source_map"].values())
            )
        dependency = digest(
            {
                "case_id": case["case_id"],
                "entity_name": case["entity_name"],
                "mandate": mandate,
                "purpose": purpose,
                "currency": case["currency"],
                "audience": case["audience"],
                "synthetic": case["synthetic"],
                "method": {k: v for k, v in method.items() if k != "review"},
                "inputs": [inputs[key] for key in used],
                "sources": [sources[key] for key in source_ids],
                "plan_bridge": dependent_bridge,
                "normalizations": dependent_normalizations,
            }
        )
        complete = (
            all(inputs[key]["status"] == "confirmed" for key in used)
            and all(sources[key]["status"] == "reviewed" for key in source_ids)
            and all(
                group["status"] == "accepted_workpaper"
                for group in dependent_normalizations
            )
        )
        accepted = complete and reviewed(method.get("review"), dependency)
        result.update(
            {
                "status": (
                    "accepted_workpaper"
                    if accepted
                    else "ready_for_professional_review" if complete else "partial"
                ),
                "dependency_sha256": dependency,
                "input_ids": used,
                "source_ids": source_ids,
                "normalization_ids": [
                    group["id"] for group in dependent_normalizations
                ],
                "rationale": method["rationale"],
                "limitations": method["limitations"],
                "review": method.get("review"),
                "stale_review": bool(method.get("review"))
                and not reviewed(method["review"], dependency),
            }
        )
        if not complete:
            issues.append(f"{method['id']}: source or assumption review pending")
        for row in result.pop("calculations"):
            row["source_ids"] = sorted(
                {
                    source
                    for ref in row["input_ids"]
                    for source in inputs[ref]["source_ids"]
                }
                | {
                    ref
                    for group in dependent_normalizations
                    for ref in group["source_ids"]
                }
            )
            row["formula_version"] = "1"
            calculations.append(row)
        outputs.append(result)
    active = [row for row in outputs if row["status"] != "excluded"]
    require(bool(active), "At least one method must be selected")
    sensitivity = []
    for scenario in indexed(case.get("sensitivity", [])).values():
        fields(
            scenario,
            {"id", "method_id", "discount_rate", "terminal_rate", "terminal_growth"},
        )
        require(
            scenario["method_id"] in methods
            and methods[scenario["method_id"]]["selected"]
            and methods[scenario["method_id"]]["kind"] in {"DCF_FCFF", "DCF_FCFE"},
            "Sensitivity requires a selected DCF method",
        )
        require(
            scenario["id"] not in methods, "Sensitivity IDs must differ from method IDs"
        )
        method = deepcopy(methods[scenario["method_id"]])
        method["id"] = scenario["id"]
        method["inputs"].update(
            {key: scenario[key] for key in ("terminal_rate", "terminal_growth")}
        )
        try:
            if "timing" in method:
                require(
                    isinstance(method["timing"], dict)
                    and method["timing"].get("rate_model") == "flat",
                    "A single-rate sensitivity requires a flat curve; supply a separate case revision for a curve change",
                )
                method["timing"]["rate_ids"] = [scenario["discount_rate"]]
            else:
                method["inputs"]["discount_rate"] = scenario["discount_rate"]
            _checked_timing(method, mandate, plan_bridge)
            result = calculate_method(method, inputs, case["currency"])
            dependent_normalizations = _bind_normalizations(result, normalizations)
        except ValuationError as exc:
            sensitivity.append(
                {"id": scenario["id"], "status": "blocked", "reason": str(exc)}
            )
            continue
        for row in result.pop("calculations"):
            row["source_ids"] = sorted(
                {
                    source
                    for ref in row["input_ids"]
                    for source in inputs[ref]["source_ids"]
                }
                | {
                    ref
                    for group in dependent_normalizations
                    for ref in group["source_ids"]
                }
            )
            row["formula_version"] = "1"
            calculations.append(row)
        sensitivity.append(
            {"id": scenario["id"], "status": "illustrative_sensitivity", **result}
        )
    from valuation_claims import build_claims

    claims = build_claims(
        case, inputs, sources, calculations, outputs, sensitivity, normalizations
    )
    for claim in claims:
        if claim["status"] in {"blocked", "partial"}:
            issues.append(
                f"Claim {claim['id']}: {'; '.join(claim['issues']) or 'evidence review pending'}"
            )
    conclusion = _conclusion(case, active, claims)
    status = "partial" if issues else "ready_for_professional_review"
    if all(row["status"] == "blocked" for row in active):
        status = "blocked"
    if (
        not issues
        and conclusion
        and conclusion["status"] == "accepted_workpaper"
        and all(claim["status"] == "accepted_workpaper" for claim in claims)
    ):
        status = "accepted_workpaper"
    report = {
        "schema_version": "vera.business_valuation.result.v1",
        "case_sha256": digest(case),
        "case": deepcopy(case),
        "status": status,
        "methods": outputs,
        "calculations": calculations,
        "sensitivity": sensitivity,
        "plan_bridge": plan_bridge,
        "conclusion": conclusion,
        "issues": issues,
        "purpose_coverage": purpose,
        "normalizations": list(normalizations.values()),
        "claims": claims,
        "claim_registry_status": "explicit_bindings" if claims else "not_supplied",
        "piv_conformity": "not_assessed",
        "legal_purpose_qualification": "requires_separate_professional_review",
        "review_identity": "local_attestation_not_authenticated",
    }
    report["report_sha256"] = digest(report)
    return report
