"""Mechanical finalization for Clara strategic-commercial business plans."""

from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from business_planning_handoff import HANDOFF_SCHEMA, counterpart_handoff_status

__all__ = [
    "CASE_SCHEMA",
    "PLAN_SCHEMA",
    "StrategicPlanningContractError",
    "build_counterpart_handoff",
    "build_model_context",
    "build_strategic_plan",
    "load_json",
    "render_html",
    "render_markdown",
    "validate_case_workspace_boundary",
    "validate_case",
    "write_assumption_ledger",
]

WORKFLOW_ID = "business-planning"
CASE_SCHEMA = "mparanza.business_planning_strategic_case.v1"
PLAN_SCHEMA = "mparanza.business_planning_strategic_plan.v2"
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,119}$")
_EVIDENCE_KINDS = {
    "historical_fact",
    "market_evidence",
    "management_statement",
    "external_evidence",
    "model_hypothesis",
}
_EVIDENCE_STATUSES = {"reviewed", "confirmed", "unverified"}
_CONFIDENCE_VALUES = {"high", "medium", "low", "unknown"}
_TOP_LEVEL_FIELDS = {
    "schema_version",
    "case_id",
    "entity_name",
    "company_stage",
    "planning_objective",
    "audience",
    "planning_horizon",
    "professional_lens",
    "review",
    "evidence_register",
    "assumptions",
    "findings",
    "options",
    "recommendation",
    "initiatives",
    "risks",
    "open_questions",
}


class StrategicPlanningContractError(ValueError):
    """Raised when a reviewed strategic case is mechanically inconsistent."""


def load_json(path: Path) -> dict[str, Any]:
    """Load one JSON object from a regular file."""

    if path.is_symlink() or not path.is_file():
        raise StrategicPlanningContractError(
            f"JSON input must be a regular file: {path}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StrategicPlanningContractError(
            f"Invalid JSON in {path.name}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise StrategicPlanningContractError(
            f"JSON must contain an object: {path.name}"
        )
    return payload


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StrategicPlanningContractError(f"{label} must be an object")
    return value


def _list(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise StrategicPlanningContractError(f"{label} must be a list")
    return list(value)


def _exact_keys(value: Mapping[str, Any], *, expected: set[str], label: str) -> None:
    observed = set(value)
    if observed != expected:
        raise StrategicPlanningContractError(
            f"{label} fields do not match the contract; "
            f"missing={sorted(expected - observed)}, extra={sorted(observed - expected)}"
        )


def _text(value: object, *, label: str, maximum: int = 1200) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise StrategicPlanningContractError(f"{label} must be non-empty trimmed text")
    if len(value) > maximum:
        raise StrategicPlanningContractError(
            f"{label} must contain at most {maximum} characters"
        )
    return value


def _identifier(value: object, *, label: str) -> str:
    identifier = _text(value, label=label, maximum=120)
    if _IDENTIFIER_RE.fullmatch(identifier) is None:
        raise StrategicPlanningContractError(f"{label} must be a lowercase identifier")
    return identifier


def _text_list(value: object, *, label: str, allow_empty: bool = False) -> list[str]:
    items = [
        _text(item, label=f"{label} item", maximum=500)
        for item in _list(value, label=label)
    ]
    if not items and not allow_empty:
        raise StrategicPlanningContractError(f"{label} must not be empty")
    return items


def _unique_ids(value: object, *, label: str, allow_empty: bool = False) -> list[str]:
    items = [
        _identifier(item, label=f"{label} item") for item in _list(value, label=label)
    ]
    if not items and not allow_empty:
        raise StrategicPlanningContractError(f"{label} must not be empty")
    if len(items) != len(set(items)):
        raise StrategicPlanningContractError(f"{label} must contain unique identifiers")
    return items


def _review_timestamp(value: object, *, label: str) -> str:
    timestamp = _text(value, label=label, maximum=80)
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StrategicPlanningContractError(
            f"{label} must be an ISO 8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StrategicPlanningContractError(f"{label} must include a timezone")
    return timestamp


def _known_references(
    values: object, *, known: set[str], label: str, allow_empty: bool = True
) -> list[str]:
    references = _unique_ids(values, label=label, allow_empty=allow_empty)
    unknown = sorted(set(references) - known)
    if unknown:
        raise StrategicPlanningContractError(
            f"{label} contains unknown references: {unknown}"
        )
    return references


def _require_support(
    evidence_references: Sequence[str],
    assumption_references: Sequence[str],
    *,
    label: str,
) -> None:
    """Require a declared evidence or confirmed-assumption basis."""

    if not evidence_references and not assumption_references:
        raise StrategicPlanningContractError(
            f"{label} must reference evidence or a confirmed assumption"
        )


def validate_case_workspace_boundary(
    case_path: Path,
    output_dir: Path,
    case_workspace: Path,
    *,
    additional_inputs: Sequence[Path] = (),
) -> None:
    """Keep Clara inputs and outputs inside one recognizable case workspace."""

    if case_workspace.is_symlink() or not case_workspace.is_dir():
        raise StrategicPlanningContractError(
            f"Clara case workspace must be a regular directory: {case_workspace}"
        )
    workspace = case_workspace.resolve()
    if case_path.is_symlink() or not case_path.is_file():
        raise StrategicPlanningContractError(
            f"Strategic case must be a regular file: {case_path}"
        )
    if case_path.resolve().parent != workspace:
        raise StrategicPlanningContractError(
            "strategic_business_plan_case.json must be at the Clara case-workspace root"
        )
    if output_dir.resolve() != workspace / "business-plan":
        raise StrategicPlanningContractError(
            "output directory must be <case-workspace>/business-plan"
        )
    if output_dir.is_symlink():
        raise StrategicPlanningContractError(
            "Clara business-plan output directory must not be a symlink"
        )
    for path in additional_inputs:
        if path.is_symlink() or not path.is_file():
            raise StrategicPlanningContractError(
                f"Counterpart handoff must be a regular file: {path}"
            )
        try:
            path.resolve().relative_to(workspace)
        except ValueError as exc:
            raise StrategicPlanningContractError(
                "counterpart handoff must remain inside the Clara case workspace"
            ) from exc

    required_files = (
        "case_manifest.json",
        "material_registry.json",
        "judgement_log.json",
        "open_questions.json",
        "case_issues.json",
        "clara_mandate.json",
    )
    missing = [
        name
        for name in required_files
        if (workspace / name).is_symlink() or not (workspace / name).is_file()
    ]
    if missing:
        raise StrategicPlanningContractError(
            f"Clara case workspace is incomplete; missing={missing}"
        )
    manifest = load_json(workspace / "case_manifest.json")
    if manifest.get("schema_version") != 1:
        raise StrategicPlanningContractError(
            "case_manifest.json has an unsupported schema_version"
        )
    for field in ("client", "project", "objective", "audience", "status"):
        _text(manifest.get(field), label=f"case_manifest.{field}")


def validate_case(case: Mapping[str, Any]) -> None:
    """Validate shape and references without making strategic judgments."""

    _exact_keys(case, expected=_TOP_LEVEL_FIELDS, label="case")
    if case["schema_version"] != CASE_SCHEMA:
        raise StrategicPlanningContractError(
            f"case.schema_version must be {CASE_SCHEMA}"
        )
    _identifier(case["case_id"], label="case.case_id")
    _text(case["entity_name"], label="case.entity_name", maximum=200)
    _text(case["company_stage"], label="case.company_stage", maximum=300)
    _text(case["planning_objective"], label="case.planning_objective", maximum=500)
    _text(case["audience"], label="case.audience", maximum=200)
    _text(case["planning_horizon"], label="case.planning_horizon", maximum=200)
    if case["professional_lens"] != "strategic_commercial":
        raise StrategicPlanningContractError(
            "case.professional_lens must be strategic_commercial for this runner"
        )

    review = _mapping(case["review"], label="case.review")
    _exact_keys(
        review,
        expected={"status", "reviewer", "reviewed_at"},
        label="case.review",
    )
    if review["status"] != "reviewed":
        raise StrategicPlanningContractError(
            "case.review.status must be reviewed before finalization"
        )
    _text(review["reviewer"], label="case.review.reviewer", maximum=200)
    _review_timestamp(review["reviewed_at"], label="case.review.reviewed_at")

    evidence_ids: set[str] = set()
    evidence_items = _list(case["evidence_register"], label="case.evidence_register")
    if not evidence_items:
        raise StrategicPlanningContractError("case.evidence_register must not be empty")
    for index, raw_item in enumerate(evidence_items):
        item = _mapping(raw_item, label=f"case.evidence_register[{index}]")
        _exact_keys(
            item,
            expected={"id", "kind", "description", "source_ref", "status"},
            label=f"case.evidence_register[{index}]",
        )
        evidence_id = _identifier(item["id"], label=f"evidence[{index}].id")
        if evidence_id in evidence_ids:
            raise StrategicPlanningContractError(
                f"Duplicate evidence id: {evidence_id}"
            )
        evidence_ids.add(evidence_id)
        if item["kind"] not in _EVIDENCE_KINDS:
            raise StrategicPlanningContractError(
                f"evidence[{index}].kind is unsupported"
            )
        _text(item["description"], label=f"evidence[{index}].description")
        _text(item["source_ref"], label=f"evidence[{index}].source_ref")
        if item["status"] not in _EVIDENCE_STATUSES:
            raise StrategicPlanningContractError(
                f"evidence[{index}].status is unsupported"
            )

    assumption_ids: set[str] = set()
    assumption_items = _list(case["assumptions"], label="case.assumptions")
    if not assumption_items:
        raise StrategicPlanningContractError("case.assumptions must not be empty")
    for index, raw_item in enumerate(assumption_items):
        item = _mapping(raw_item, label=f"case.assumptions[{index}]")
        _exact_keys(
            item,
            expected={
                "id",
                "category",
                "description",
                "evidence_ids",
                "rationale",
                "status",
            },
            label=f"case.assumptions[{index}]",
        )
        assumption_id = _identifier(item["id"], label=f"assumption[{index}].id")
        if assumption_id in assumption_ids:
            raise StrategicPlanningContractError(
                f"Duplicate assumption id: {assumption_id}"
            )
        assumption_ids.add(assumption_id)
        _text(item["category"], label=f"assumption[{index}].category", maximum=200)
        _text(item["description"], label=f"assumption[{index}].description")
        _known_references(
            item["evidence_ids"],
            known=evidence_ids,
            label=f"assumption[{index}].evidence_ids",
            allow_empty=False,
        )
        _text(item["rationale"], label=f"assumption[{index}].rationale")
        if item["status"] != "confirmed":
            raise StrategicPlanningContractError(
                f"assumption[{index}].status must be confirmed"
            )

    finding_ids: set[str] = set()
    finding_items = _list(case["findings"], label="case.findings")
    if not finding_items:
        raise StrategicPlanningContractError("case.findings must not be empty")
    for index, raw_item in enumerate(finding_items):
        item = _mapping(raw_item, label=f"case.findings[{index}]")
        _exact_keys(
            item,
            expected={
                "id",
                "domain",
                "statement",
                "implication",
                "evidence_ids",
                "assumption_ids",
                "confidence",
            },
            label=f"case.findings[{index}]",
        )
        finding_id = _identifier(item["id"], label=f"finding[{index}].id")
        if finding_id in finding_ids:
            raise StrategicPlanningContractError(f"Duplicate finding id: {finding_id}")
        finding_ids.add(finding_id)
        _text(item["domain"], label=f"finding[{index}].domain", maximum=200)
        _text(item["statement"], label=f"finding[{index}].statement")
        _text(item["implication"], label=f"finding[{index}].implication")
        linked_evidence = _known_references(
            item["evidence_ids"],
            known=evidence_ids,
            label=f"finding[{index}].evidence_ids",
        )
        linked_assumptions = _known_references(
            item["assumption_ids"],
            known=assumption_ids,
            label=f"finding[{index}].assumption_ids",
        )
        _require_support(
            linked_evidence,
            linked_assumptions,
            label=f"finding[{index}]",
        )
        if item["confidence"] not in _CONFIDENCE_VALUES:
            raise StrategicPlanningContractError(
                f"finding[{index}].confidence is unsupported"
            )

    option_ids: set[str] = set()
    option_items = _list(case["options"], label="case.options")
    if not option_items:
        raise StrategicPlanningContractError("case.options must not be empty")
    for index, raw_item in enumerate(option_items):
        item = _mapping(raw_item, label=f"case.options[{index}]")
        _exact_keys(
            item,
            expected={
                "id",
                "title",
                "description",
                "benefits",
                "drawbacks",
                "evidence_ids",
                "assumption_ids",
            },
            label=f"case.options[{index}]",
        )
        option_id = _identifier(item["id"], label=f"option[{index}].id")
        if option_id in option_ids:
            raise StrategicPlanningContractError(f"Duplicate option id: {option_id}")
        option_ids.add(option_id)
        _text(item["title"], label=f"option[{index}].title", maximum=240)
        _text(item["description"], label=f"option[{index}].description")
        _text_list(item["benefits"], label=f"option[{index}].benefits")
        _text_list(item["drawbacks"], label=f"option[{index}].drawbacks")
        linked_evidence = _known_references(
            item["evidence_ids"],
            known=evidence_ids,
            label=f"option[{index}].evidence_ids",
        )
        linked_assumptions = _known_references(
            item["assumption_ids"],
            known=assumption_ids,
            label=f"option[{index}].assumption_ids",
        )
        _require_support(
            linked_evidence,
            linked_assumptions,
            label=f"option[{index}]",
        )

    recommendation = _mapping(case["recommendation"], label="case.recommendation")
    _exact_keys(
        recommendation,
        expected={
            "statement",
            "option_ids",
            "evidence_ids",
            "assumption_ids",
            "conditions",
        },
        label="case.recommendation",
    )
    _text(recommendation["statement"], label="recommendation.statement")
    _known_references(
        recommendation["option_ids"],
        known=option_ids,
        label="recommendation.option_ids",
        allow_empty=False,
    )
    recommendation_evidence = _known_references(
        recommendation["evidence_ids"],
        known=evidence_ids,
        label="recommendation.evidence_ids",
    )
    recommendation_assumptions = _known_references(
        recommendation["assumption_ids"],
        known=assumption_ids,
        label="recommendation.assumption_ids",
    )
    _require_support(
        recommendation_evidence,
        recommendation_assumptions,
        label="recommendation",
    )
    _text_list(
        recommendation["conditions"],
        label="recommendation.conditions",
        allow_empty=True,
    )

    initiative_ids: set[str] = set()
    initiative_items = _list(case["initiatives"], label="case.initiatives")
    if not initiative_items:
        raise StrategicPlanningContractError("case.initiatives must not be empty")
    for index, raw_item in enumerate(initiative_items):
        item = _mapping(raw_item, label=f"case.initiatives[{index}]")
        _exact_keys(
            item,
            expected={
                "id",
                "title",
                "objective",
                "owner",
                "milestones",
                "kpis",
                "evidence_ids",
                "assumption_ids",
            },
            label=f"case.initiatives[{index}]",
        )
        initiative_id = _identifier(item["id"], label=f"initiative[{index}].id")
        if initiative_id in initiative_ids:
            raise StrategicPlanningContractError(
                f"Duplicate initiative id: {initiative_id}"
            )
        initiative_ids.add(initiative_id)
        _text(item["title"], label=f"initiative[{index}].title", maximum=240)
        _text(item["objective"], label=f"initiative[{index}].objective")
        _text(item["owner"], label=f"initiative[{index}].owner", maximum=240)
        milestones = _list(item["milestones"], label=f"initiative[{index}].milestones")
        if not milestones:
            raise StrategicPlanningContractError(
                f"initiative[{index}].milestones must not be empty"
            )
        for milestone_index, raw_milestone in enumerate(milestones):
            milestone = _mapping(
                raw_milestone,
                label=f"initiative[{index}].milestones[{milestone_index}]",
            )
            _exact_keys(
                milestone,
                expected={"period", "outcome"},
                label=f"initiative[{index}].milestones[{milestone_index}]",
            )
            _text(
                milestone["period"],
                label=f"initiative[{index}].milestones[{milestone_index}].period",
                maximum=120,
            )
            _text(
                milestone["outcome"],
                label=f"initiative[{index}].milestones[{milestone_index}].outcome",
            )
        _text_list(item["kpis"], label=f"initiative[{index}].kpis")
        linked_evidence = _known_references(
            item["evidence_ids"],
            known=evidence_ids,
            label=f"initiative[{index}].evidence_ids",
        )
        linked_assumptions = _known_references(
            item["assumption_ids"],
            known=assumption_ids,
            label=f"initiative[{index}].assumption_ids",
        )
        _require_support(
            linked_evidence,
            linked_assumptions,
            label=f"initiative[{index}]",
        )

    risk_items = _list(case["risks"], label="case.risks")
    if not risk_items:
        raise StrategicPlanningContractError("case.risks must not be empty")
    risk_ids: set[str] = set()
    for index, raw_item in enumerate(risk_items):
        item = _mapping(raw_item, label=f"case.risks[{index}]")
        _exact_keys(
            item,
            expected={
                "id",
                "description",
                "response",
                "evidence_ids",
                "assumption_ids",
            },
            label=f"case.risks[{index}]",
        )
        risk_id = _identifier(item["id"], label=f"risk[{index}].id")
        if risk_id in risk_ids:
            raise StrategicPlanningContractError(f"Duplicate risk id: {risk_id}")
        risk_ids.add(risk_id)
        _text(item["description"], label=f"risk[{index}].description")
        _text(item["response"], label=f"risk[{index}].response")
        linked_evidence = _known_references(
            item["evidence_ids"],
            known=evidence_ids,
            label=f"risk[{index}].evidence_ids",
        )
        linked_assumptions = _known_references(
            item["assumption_ids"],
            known=assumption_ids,
            label=f"risk[{index}].assumption_ids",
        )
        _require_support(
            linked_evidence,
            linked_assumptions,
            label=f"risk[{index}]",
        )

    question_items = _list(case["open_questions"], label="case.open_questions")
    question_ids: set[str] = set()
    for index, raw_item in enumerate(question_items):
        item = _mapping(raw_item, label=f"case.open_questions[{index}]")
        _exact_keys(
            item,
            expected={"id", "question", "why_it_matters"},
            label=f"case.open_questions[{index}]",
        )
        question_id = _identifier(item["id"], label=f"open_question[{index}].id")
        if question_id in question_ids:
            raise StrategicPlanningContractError(
                f"Duplicate open question id: {question_id}"
            )
        question_ids.add(question_id)
        _text(item["question"], label=f"open_question[{index}].question")
        _text(
            item["why_it_matters"],
            label=f"open_question[{index}].why_it_matters",
        )


def build_strategic_plan(case: Mapping[str, Any]) -> dict[str, Any]:
    """Finalize a reviewed model-authored strategic case."""

    validate_case(case)
    evidence_items = [dict(item) for item in case["evidence_register"]]
    referenced_evidence = {
        str(evidence_id)
        for collection_name in (
            "assumptions",
            "findings",
            "options",
            "initiatives",
            "risks",
        )
        for item in case[collection_name]
        for evidence_id in item["evidence_ids"]
    } | {str(item) for item in case["recommendation"]["evidence_ids"]}
    referenced_items = [
        item for item in evidence_items if str(item["id"]) in referenced_evidence
    ]
    counts = Counter(str(item["status"]) for item in referenced_items)
    unverified = sorted(
        str(item["id"]) for item in referenced_items if item["status"] == "unverified"
    )
    return {
        "schema_version": PLAN_SCHEMA,
        "workflow_id": WORKFLOW_ID,
        "case_id": case["case_id"],
        "entity_name": case["entity_name"],
        "company_stage": case["company_stage"],
        "planning_objective": case["planning_objective"],
        "audience": case["audience"],
        "planning_horizon": case["planning_horizon"],
        "professional_lens": case["professional_lens"],
        "status": "partial" if unverified else "ready_for_professional_review",
        "review_status": "draft_pending_professional_review",
        "evidence_coverage": {
            "referenced_evidence_ids": sorted(referenced_evidence),
            "status_counts": dict(sorted(counts.items())),
            "unverified_evidence_ids": unverified,
        },
        "evidence_register": [
            {
                "id": item["id"],
                "kind": item["kind"],
                "description": item["description"],
                "status": item["status"],
            }
            for item in referenced_items
        ],
        "assumptions": [dict(item) for item in case["assumptions"]],
        "findings": [dict(item) for item in case["findings"]],
        "options": [dict(item) for item in case["options"]],
        "recommendation": dict(case["recommendation"]),
        "initiatives": [dict(item) for item in case["initiatives"]],
        "risks": [dict(item) for item in case["risks"]],
        "open_questions": [dict(item) for item in case["open_questions"]],
        "limitations": [
            "Reference closure does not establish market truth, strategic fit, feasibility, or professional approval.",
            "The strategic content is model-authored from reviewed evidence and assumptions; deterministic code does not select or score options.",
            *(["One or more evidence items remain unverified."] if unverified else []),
        ],
    }


def build_model_context(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Project the strategic plan without evidence source locations."""

    return {
        key: plan[key]
        for key in (
            "schema_version",
            "workflow_id",
            "case_id",
            "entity_name",
            "company_stage",
            "planning_objective",
            "audience",
            "planning_horizon",
            "professional_lens",
            "status",
            "review_status",
            "evidence_coverage",
            "evidence_register",
            "assumptions",
            "findings",
            "options",
            "recommendation",
            "initiatives",
            "risks",
            "open_questions",
            "limitations",
        )
    } | {
        "schema_version": "mparanza.business_planning_strategic_model_context.v2",
        "excluded_by_default": [
            "raw source documents",
            "absolute source paths",
            "original filenames",
            "evidence source_ref values",
        ],
    }


def build_counterpart_handoff(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Build the reviewed Clara-to-Vera bridge without semantic merging."""

    return {
        "schema_version": HANDOFF_SCHEMA,
        "workflow_id": WORKFLOW_ID,
        "case_id": plan["case_id"],
        "entity_name": plan["entity_name"],
        "company_stage": plan["company_stage"],
        "planning_objective": plan["planning_objective"],
        "audience": plan["audience"],
        "from_product": "Clara",
        "from_lens": "strategic_commercial",
        "to_product": "Vera",
        "to_lens": "accounting_financial",
        "status": counterpart_handoff_status(plan["status"]),
        "source_plan_status": plan["status"],
        "source_review_status": plan["review_status"],
        "assumptions": [
            {
                "id": item["id"],
                "category": item["category"],
                "description": item["description"],
                "rationale": item["rationale"],
                "status": item["status"],
            }
            for item in plan["assumptions"]
        ],
        "recommendation": plan["recommendation"],
        "initiatives": [
            {
                "id": item["id"],
                "title": item["title"],
                "objective": item["objective"],
                "milestones": item["milestones"],
                "kpis": item["kpis"],
                "assumption_ids": item["assumption_ids"],
            }
            for item in plan["initiatives"]
        ],
        "risks": plan["risks"],
        "open_questions": plan["open_questions"],
        "limitations": plan["limitations"],
        "handoff_boundary": (
            "Vera may use this reviewed bridge to build or revise the financial plan, "
            "but must not convert strategic statements into figures or alter Clara's "
            "recommendation silently. Any divergence must be stated and returned for "
            "professional review."
        ),
    }


def write_assumption_ledger(path: Path, plan: Mapping[str, Any]) -> None:
    """Write the reviewed strategic assumption register as CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "id",
                "category",
                "description",
                "evidence_ids",
                "rationale",
                "status",
            ),
        )
        writer.writeheader()
        for item in plan["assumptions"]:
            writer.writerow(
                {
                    **item,
                    "evidence_ids": "|".join(item["evidence_ids"]),
                }
            )


def render_markdown(plan: Mapping[str, Any]) -> str:
    """Render a consultant-readable strategic plan summary."""

    lines = [
        f"# Strategic business plan — {plan['entity_name']}",
        "",
        f"- Company stage: {plan['company_stage']}",
        f"- Objective: {plan['planning_objective']}",
        f"- Audience: {plan['audience']}",
        f"- Horizon: {plan['planning_horizon']}",
        f"- Status: `{plan['status']}`",
        f"- Review: `{plan['review_status']}`",
        "",
        "## Evidence register",
        "",
    ]
    lines.extend(
        f"- `{item['id']}` ({item['kind']}, {item['status']}): {item['description']}"
        for item in plan["evidence_register"]
    )
    lines.extend(["", "## Confirmed assumptions", ""])
    lines.extend(
        f"- `{item['id']}`: {item['description']} Evidence: {', '.join(item['evidence_ids'])}. Rationale: {item['rationale']}"
        for item in plan["assumptions"]
    )
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            str(plan["recommendation"]["statement"]),
            "",
            f"Selected options: {', '.join(plan['recommendation']['option_ids'])}",
            f"Conditions: {'; '.join(plan['recommendation']['conditions']) or 'none'}",
            f"Evidence: {', '.join(plan['recommendation']['evidence_ids'])}",
            f"Assumptions: {', '.join(plan['recommendation']['assumption_ids'])}",
            "",
            "## Strategic findings",
            "",
        ]
    )
    for item in plan["findings"]:
        lines.extend(
            [
                f"### {item['domain']}",
                "",
                str(item["statement"]),
                "",
                f"Implication: {item['implication']}",
                f"Confidence: {item['confidence']}",
                f"Evidence: {', '.join(item['evidence_ids'])}",
                f"Assumptions: {', '.join(item['assumption_ids'])}",
                "",
            ]
        )
    lines.extend(["## Options and trade-offs", ""])
    for item in plan["options"]:
        lines.extend(
            [
                f"### {item['title']}",
                "",
                str(item["description"]),
                "",
                f"Benefits: {'; '.join(item['benefits'])}",
                f"Drawbacks: {'; '.join(item['drawbacks'])}",
                f"Evidence: {', '.join(item['evidence_ids'])}",
                f"Assumptions: {', '.join(item['assumption_ids'])}",
                "",
            ]
        )
    lines.extend(["## Initiatives", ""])
    for item in plan["initiatives"]:
        lines.extend(
            [
                f"### {item['title']}",
                "",
                str(item["objective"]),
                "",
                f"Owner: {item['owner']}",
                "Milestones: "
                + "; ".join(
                    f"{milestone['period']}: {milestone['outcome']}"
                    for milestone in item["milestones"]
                ),
                f"KPIs: {'; '.join(item['kpis'])}",
                f"Evidence: {', '.join(item['evidence_ids'])}",
                f"Assumptions: {', '.join(item['assumption_ids'])}",
                "",
            ]
        )
    lines.extend(["## Risks", ""])
    lines.extend(
        f"- {item['description']} Response: {item['response']} Evidence: {', '.join(item['evidence_ids'])}. Assumptions: {', '.join(item['assumption_ids'])}."
        for item in plan["risks"]
    )
    lines.extend(["", "## Open questions", ""])
    if plan["open_questions"]:
        lines.extend(
            f"- {item['question']} Why it matters: {item['why_it_matters']}"
            for item in plan["open_questions"]
        )
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in plan["limitations"])
    return "\n".join(lines) + "\n"


def render_html(plan: Mapping[str, Any]) -> str:
    """Render a self-contained strategic plan review page."""

    def references(item: Mapping[str, Any]) -> str:
        evidence = " · ".join(item.get("evidence_ids", [])) or "none"
        assumptions = " · ".join(item.get("assumption_ids", [])) or "none"
        return (
            '<p class="refs"><strong>Evidence:</strong> '
            f"{html.escape(evidence)} · <strong>Assumptions:</strong> "
            f"{html.escape(assumptions)}</p>"
        )

    def bullets(items: Sequence[object]) -> str:
        return (
            "<ul>"
            + "".join(f"<li>{html.escape(str(item))}</li>" for item in items)
            + "</ul>"
        )

    evidence_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['id']))}</td>"
        f"<td>{html.escape(str(item['kind']))}</td>"
        f"<td>{html.escape(str(item['description']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        "</tr>"
        for item in plan["evidence_register"]
    )
    assumption_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['id']))}</td>"
        f"<td>{html.escape(str(item['category']))}</td>"
        f"<td>{html.escape(str(item['description']))}</td>"
        f"<td>{html.escape(' · '.join(item['evidence_ids']))}</td>"
        f"<td>{html.escape(str(item['rationale']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        "</tr>"
        for item in plan["assumptions"]
    )
    findings = "".join(
        "<article>"
        f"<p class=\"eyebrow\">{html.escape(str(item['domain']))}</p>"
        f"<h3>{html.escape(str(item['statement']))}</h3>"
        f"<p>{html.escape(str(item['implication']))}</p>"
        f"<p><strong>Confidence:</strong> {html.escape(str(item['confidence']))}</p>"
        f"{references(item)}"
        "</article>"
        for item in plan["findings"]
    )
    options = "".join(
        "<article>"
        f"<h3>{html.escape(str(item['title']))}</h3>"
        f"<p>{html.escape(str(item['description']))}</p>"
        "<h4>Benefits</h4>"
        f"{bullets(item['benefits'])}"
        "<h4>Drawbacks</h4>"
        f"{bullets(item['drawbacks'])}"
        f"{references(item)}"
        "</article>"
        for item in plan["options"]
    )
    initiatives = "".join(
        "<article>"
        f"<h3>{html.escape(str(item['title']))}</h3>"
        f"<p>{html.escape(str(item['objective']))}</p>"
        f"<p><strong>Owner:</strong> {html.escape(str(item['owner']))}</p>"
        "<h4>Milestones</h4>"
        + bullets(
            [
                f"{milestone['period']}: {milestone['outcome']}"
                for milestone in item["milestones"]
            ]
        )
        + "<h4>KPIs</h4>"
        + bullets(item["kpis"])
        + references(item)
        + "</article>"
        for item in plan["initiatives"]
    )
    risks = "".join(
        "<article>"
        f"<h3>{html.escape(str(item['description']))}</h3>"
        f"<p><strong>Response:</strong> {html.escape(str(item['response']))}</p>"
        f"{references(item)}"
        "</article>"
        for item in plan["risks"]
    )
    questions = (
        "".join(
            "<article>"
            f"<h3>{html.escape(str(item['question']))}</h3>"
            f"<p>{html.escape(str(item['why_it_matters']))}</p>"
            "</article>"
            for item in plan["open_questions"]
        )
        or "<p>None recorded.</p>"
    )
    limitations = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in plan["limitations"]
    )
    recommendation = plan["recommendation"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Strategic business plan — {html.escape(str(plan['entity_name']))}</title>
  <style>
    :root {{ color-scheme: light; font-family: "Instrument Sans", sans-serif; color: #183765; background: #fff; }}
    body {{ margin: 0; }} main {{ max-width: 1180px; margin: 0 auto; padding: 52px 24px 80px; }}
    h1 {{ color: #002060; font-size: clamp(2.2rem, 6vw, 4.8rem); line-height: 1; margin: 12px 0 24px; }}
    h2, h3 {{ color: #002060; }} h2 {{ margin-top: 48px; }} .meta {{ border-block: 1px solid #b7dded; padding: 18px 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; background: #b7dded; border: 1px solid #b7dded; }}
    article {{ background: white; padding: 24px; }} .eyebrow {{ color: #0070c0; font-size: .78rem; font-weight: 700; text-transform: uppercase; }} .refs {{ color: #52657f; font-size: .9rem; }}
    .recommendation {{ margin: 36px 0; padding: 24px 28px; border-left: 3px solid #00b0f0; background: #f3fbff; }}
    .table-wrap {{ overflow-x: auto; }} table {{ width: 100%; border-collapse: collapse; }} th, td {{ padding: 12px; border-bottom: 1px solid #dbe4f2; text-align: left; vertical-align: top; }} th {{ color: #002060; white-space: nowrap; }}
    @media (max-width: 720px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body><main>
  <p>Clara · Business planning · strategic and commercial lens</p>
  <h1>{html.escape(str(plan['entity_name']))}</h1>
  <p class="meta">{html.escape(str(plan['company_stage']))} · {html.escape(str(plan['planning_horizon']))} · {html.escape(str(plan['status']))}</p>
  <p><strong>Objective:</strong> {html.escape(str(plan['planning_objective']))}</p>
  <p><strong>Audience:</strong> {html.escape(str(plan['audience']))} · <strong>Review:</strong> {html.escape(str(plan['review_status']))}</p>
  <h2>Evidence register</h2><div class="table-wrap"><table><thead><tr><th>ID</th><th>Kind</th><th>Description</th><th>Status</th></tr></thead><tbody>{evidence_rows}</tbody></table></div>
  <h2>Confirmed assumptions</h2><div class="table-wrap"><table><thead><tr><th>ID</th><th>Category</th><th>Description</th><th>Evidence</th><th>Rationale</th><th>Status</th></tr></thead><tbody>{assumption_rows}</tbody></table></div>
  <section class="recommendation"><h2>Recommendation</h2><p>{html.escape(str(recommendation['statement']))}</p><p><strong>Selected options:</strong> {html.escape(' · '.join(recommendation['option_ids']))}</p><h3>Conditions</h3>{bullets(recommendation['conditions']) if recommendation['conditions'] else '<p>None recorded.</p>'}{references(recommendation)}</section>
  <h2>Strategic findings</h2><section class="grid">{findings}</section>
  <h2>Options and trade-offs</h2><section class="grid">{options}</section>
  <h2>Initiatives</h2><section class="grid">{initiatives}</section>
  <h2>Risks and responses</h2><section class="grid">{risks}</section>
  <h2>Open questions</h2><section class="grid">{questions}</section>
  <h2>Limitations</h2><ul>{limitations}</ul>
</main></body></html>
"""
