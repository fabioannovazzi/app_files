"""Bind explicit mandate evidence without deciding competence or legal suitability."""

from __future__ import annotations

from copy import deepcopy

from valuation_case import digest, require, reviewed
from valuation_engine import decimal

__all__ = ["build_mandate", "MANDATE_FIELDS", "STANDARD_FIELDS"]

MANDATE_FIELDS = (
    "subject_type",
    "engagement_date",
    "report_date",
    "commissioning_party",
    "expert_identity",
    "expert_activity",
    "written_mandate",
    "remuneration",
    "delivery_terms",
    "amendments",
    "participant_perspective",
    "recipients",
    "use_restrictions",
    "competencies",
    "conflicts",
)
STANDARD_FIELDS = ("name", "edition", "adoption_reason", "departures")


def build_mandate(case: dict, inputs: dict, sources: dict) -> dict:
    """Retain unknowns and exact review dependencies; never infer missing rights."""
    details = case.get("mandate_details")
    issues: list[str] = []
    source_ids: set[str] = set()
    input_ids: set[str] = set()
    if details is None:
        issues.append("Structured mandate details have not been collected")
    else:
        for name in MANDATE_FIELDS:
            item = details.get(name)
            if item is None:
                issues.append(f"Mandate {name}: evidence or confirmation pending")
                continue
            require(
                set(item["source_ids"]) <= sources.keys(),
                "Unresolved mandate evidence",
            )
            source_ids.update(item["source_ids"])
            if (
                item["value"] is None
                or item["status"] != "confirmed"
                or not item["source_ids"]
                or item["locator"] is None
            ):
                issues.append(f"Mandate {name}: evidence or confirmation pending")
        standards = details.get("standards", [])
        if not standards:
            issues.append("Mandate standards: explicit selection and evidence pending")
        standard_ids = [row["id"] for row in standards]
        require(
            len(set(standard_ids)) == len(standard_ids), "Duplicate mandate standard"
        )
        for item in standards:
            require(
                set(item["source_ids"]) <= sources.keys(),
                "Unresolved mandate standard evidence",
            )
            source_ids.update(item["source_ids"])
            if (
                any(item[key] is None for key in STANDARD_FIELDS)
                or item["status"] != "confirmed"
                or not item["source_ids"]
                or item["locator"] is None
            ):
                issues.append(f"Standard {item['id']}: selection or evidence pending")
        interest_ids = [row["id"] for row in details["interests"]]
        require(
            len(set(interest_ids)) == len(interest_ids), "Duplicate mandate interest"
        )
        subject = details["subject_type"]["value"]
        if subject in {"equity_interest", "specific_right"} and not interest_ids:
            issues.append("Selected subject requires an explicit rights record")
        for item in details["interests"]:
            require(
                set(item["source_ids"]) <= sources.keys(),
                "Unresolved rights evidence",
            )
            source_ids.update(item["source_ids"])
            required_text = (
                "description",
                "ownership_basis",
                "economic_rights",
                "administrative_rights",
                "statutes",
                "agreements",
                "restrictions",
                "thresholds",
                "locator",
            )
            if (
                any(item[key] is None for key in required_text)
                or not item["source_ids"]
                or item["status"] != "confirmed"
            ):
                issues.append(f"Rights {item['id']}: evidence or confirmation pending")
            ref = item["ownership_input_id"]
            if ref is None:
                if subject == "equity_interest":
                    issues.append(f"Rights {item['id']}: ownership ratio missing")
                continue
            require(ref in inputs, "Unresolved ownership input")
            amount = inputs[ref]
            require(amount["unit"] == "ratio", "Ownership requires an explicit ratio")
            input_ids.add(ref)
            source_ids.update(amount["source_ids"])
            if amount["value"] is None or amount["status"] != "confirmed":
                issues.append(f"Rights {item['id']}: ownership evidence pending")
            elif not 0 <= decimal(amount["value"]) <= 1:
                issues.append(
                    f"Rights {item['id']}: ownership ratio outside zero to one"
                )
    if any(sources[ref]["status"] != "reviewed" for ref in source_ids):
        issues.append("Mandate source review pending")
    dependency = digest(
        {
            "case_id": case["case_id"],
            "entity_name": case["entity_name"],
            "mandate": case["mandate"],
            "details": (
                {key: value for key, value in details.items() if key != "review"}
                if details is not None
                else None
            ),
            "purpose_profile": case.get("purpose_profile"),
            "currency": case["currency"],
            "audience": case["audience"],
            "synthetic": case["synthetic"],
            "inputs": [inputs[ref] for ref in sorted(input_ids)],
            "sources": [sources[ref] for ref in sorted(source_ids)],
        }
    )
    attestation = details.get("review") if details is not None else None
    return {
        "details": deepcopy(details),
        "status": (
            "partial"
            if issues
            else (
                "accepted_workpaper"
                if reviewed(attestation, dependency)
                else "ready_for_professional_review"
            )
        ),
        "issues": issues,
        "dependency_sha256": dependency,
        "source_ids": sorted(source_ids),
        "input_ids": sorted(input_ids),
        "review": deepcopy(attestation),
        "stale_review": bool(attestation) and not reviewed(attestation, dependency),
        "scope": "explicit_local_mandate_attestation_not_legal_or_professional_qualification",
    }
