#!/usr/bin/env python3
"""Structured, paginated professional-review views for Bilancio cases."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

__all__ = ["REVIEW_VIEWS", "build_review_view"]

REVIEW_VIEWS = frozenset(
    {
        "CASE_DASHBOARD",
        "SOURCE_REVIEW",
        "MAPPING_GRID",
        "STATEMENTS",
        "SCHEDULES",
        "QUESTIONNAIRE",
        "NOTES_EDITOR",
        "ISSUES_PANEL",
        "PREVIEW",
        "APPROVAL_EXPORT",
    }
)


def _page(
    items: Sequence[Mapping[str, Any]], offset: int, limit: int
) -> dict[str, Any]:
    if isinstance(offset, bool) or offset < 0:
        raise ValueError("Review view offset must be a non-negative integer")
    if isinstance(limit, bool) or not 1 <= limit <= 500:
        raise ValueError("Review view limit must be an integer from 1 to 500")
    total = len(items)
    return {
        "items": [dict(item) for item in items[offset : offset + limit]],
        "page": {
            "offset": offset,
            "limit": limit,
            "returned": len(items[offset : offset + limit]),
            "total": total,
            "has_more": offset + limit < total,
        },
    }


def _next_action(case: Mapping[str, Any]) -> str:
    if case.get("unsupported_reasons"):
        return "STOP_UNSUPPORTED"
    pdf_candidate = case.get("pdf_trial_balance_candidate") or {}
    if pdf_candidate.get("status") == "PENDING_REVIEW":
        return "REVIEW_PDF_EXTRACTION"
    if pdf_candidate.get("status") == "REJECTED":
        return "REPLACE_PDF_SOURCE"
    trial_balance = case.get("trial_balance") or {}
    if not trial_balance:
        return "INGEST_TRIAL_BALANCE"
    if not trial_balance.get("confirmed_convention"):
        return "CONFIRM_PARSER"
    if not case.get("form_analysis"):
        return "DETERMINE_FORMS"
    if not case.get("selected_form"):
        return "SELECT_FORM"
    entries = trial_balance.get("entries", [])
    if (
        case.get("statutory_presentation_required", True)
        and not case.get("taxonomy_mapping_index")
        and len(case.get("mappings", [])) != len(entries)
    ):
        return "BUILD_TAXONOMY_MAPPING_INDEX"
    if len(case.get("mappings", [])) != len(entries):
        return "REVIEW_MAPPINGS"
    if not case.get("statements"):
        return "COMPUTE_STATEMENTS"
    if case.get("statutory_presentation_required", True):
        presentation = case.get("statutory_presentation") or {}
        if presentation.get("status") != "COMPLETE":
            return "REVIEW_STATUTORY_PRESENTATION"
    if not case.get("disclosure_rule_pack"):
        return "ACTIVATE_DISCLOSURES"
    manual_flags = {
        str(item.get("trigger", {}).get("flag"))
        for item in (case.get("disclosure_rule_pack") or {}).get("rules", [])
        if item.get("trigger", {}).get("kind") == "MANUAL_FLAG"
    }
    reviewed_flags = {
        str(item.get("flag")) for item in case.get("disclosure_trigger_decisions", [])
    }
    if manual_flags - reviewed_flags:
        return "REVIEW_DISCLOSURE_APPLICABILITY"
    if any(
        question.get("state") in {"OPEN", "BLOCKED"}
        for question in case.get("questionnaire", [])
    ):
        return "ANSWER_CONTEXTUAL_QUESTIONS"
    if not case.get("preview"):
        return "CREATE_PREVIEW"
    validation = case.get("validation") or {}
    if not validation:
        return "VALIDATE"
    if validation.get("status") != "PASS" or validation.get("review_required"):
        return "RESOLVE_VALIDATION_ISSUES"
    if not case.get("xbrl_review"):
        return "PREPARE_XBRL_REVIEW"
    if not case.get("approval"):
        return "PROFESSIONAL_REVIEW_AND_APPROVAL"
    if not case.get("artifacts"):
        return "EXPORT_APPROVED_SNAPSHOT"
    return "REVIEW_EXPORTED_ARTIFACTS"


def _base(case: Mapping[str, Any], view: str) -> dict[str, Any]:
    return {
        "view": view,
        "case_id": case["case_id"],
        "revision_id": case["revision_id"],
        "state": case["state"],
    }


def _dashboard(case: Mapping[str, Any]) -> dict[str, Any]:
    trial_balance = case.get("trial_balance") or {}
    mappings = case.get("mappings", [])
    validation = case.get("validation") or {}
    pdf_candidate = case.get("pdf_trial_balance_candidate") or {}
    return {
        **_base(case, "CASE_DASHBOARD"),
        "selected_form": case.get("selected_form"),
        "forms": case.get("form_analysis"),
        "mapping": {
            "total_accounts": len(trial_balance.get("entries", [])),
            "accepted": sum(item.get("decision") == "ACCEPTED" for item in mappings),
            "excluded": sum(item.get("decision") == "EXCLUDED" for item in mappings),
            "review_required": max(
                len(trial_balance.get("entries", [])) - len(mappings), 0
            ),
        },
        "validation": {
            "status": validation.get("status", "NOT_RUN"),
            "blockers": validation.get("blockers"),
            "high": validation.get("high"),
            "review_required": validation.get("review_required"),
        },
        "pdf_extraction": {
            "status": pdf_candidate.get("status", "NOT_PRESENT"),
            "row_count": pdf_candidate.get("row_count", 0),
            "page_count": pdf_candidate.get("page_count", 0),
            "ocr_used": pdf_candidate.get("ocr_used", False),
            "issue_count": len(pdf_candidate.get("issues", [])),
        },
        "schedule_statuses": [
            {
                "schedule_id": item.get("schedule_id"),
                "schedule_type": item.get("schedule_type"),
                "status": item.get("status"),
            }
            for item in case.get("schedules", [])
        ],
        "next_action": _next_action(case),
    }


def build_review_view(
    case: Mapping[str, Any],
    view: str,
    *,
    offset: int = 0,
    limit: int = 200,
) -> dict[str, Any]:
    """Return one bounded structured view without local file-system paths."""

    selected = view.upper()
    if selected not in REVIEW_VIEWS:
        raise ValueError(f"Unsupported Bilancio review view: {view}")
    if selected == "CASE_DASHBOARD":
        return _dashboard(case)
    if selected == "SOURCE_REVIEW":
        trial_balance = case.get("trial_balance") or {}
        pdf_candidate = case.get("pdf_trial_balance_candidate") or {}
        return {
            **_base(case, selected),
            "documents": [dict(item) for item in case.get("source_documents", [])],
            "parser": {
                "layout": trial_balance.get("layout"),
                "confirmed_convention": trial_balance.get("confirmed_convention"),
                "account_count": len(trial_balance.get("entries", [])),
                "source_anchor_count": len(trial_balance.get("source_anchors", [])),
                "calibration": trial_balance.get("calibration"),
            },
            "anchors": _page(trial_balance.get("source_anchors", []), offset, limit),
            "pdf_extraction": {
                "status": pdf_candidate.get("status", "NOT_PRESENT"),
                "source_document_id": pdf_candidate.get("source_document_id"),
                "content_sha256": pdf_candidate.get("content_sha256"),
                "page_count": pdf_candidate.get("page_count", 0),
                "row_count": pdf_candidate.get("row_count", 0),
                "methods": list(pdf_candidate.get("methods", [])),
                "ocr_used": pdf_candidate.get("ocr_used", False),
                "columns": list(pdf_candidate.get("columns", [])),
                "issues": list(pdf_candidate.get("issues", [])),
                "review": pdf_candidate.get("review"),
                "rows": _page(pdf_candidate.get("rows", []), offset, limit),
            },
            "prior_xbrl": case.get("prior_xbrl"),
        }
    if selected == "MAPPING_GRID":
        trial_balance = case.get("trial_balance") or {}
        mappings = {str(item["account_id"]): item for item in case.get("mappings", [])}
        candidates = {
            str(item["account_id"]): item for item in case.get("mapping_candidates", [])
        }
        rows = [
            {
                "account_id": entry["account_id"],
                "account_code": entry["account_code"],
                "account_description": entry["account_description"],
                "current_balance": entry["closing_signed"],
                "prior_balance": entry["prior_closing_signed"],
                "source_refs": entry.get("source_refs", []),
                "candidate": candidates.get(str(entry["account_id"])),
                "decision": mappings.get(str(entry["account_id"])),
            }
            for entry in trial_balance.get("entries", [])
        ]
        return {
            **_base(case, selected),
            "taxonomy_mapping_index": case.get("taxonomy_mapping_index"),
            "rows": _page(rows, offset, limit),
        }
    if selected == "STATEMENTS":
        statements = case.get("statements") or {}
        presentation = case.get("statutory_presentation") or {}
        inventory = presentation.get("inventory") or {}
        decision_lookup = {
            str(item["xbrl_concept"]): item
            for item in presentation.get("decisions", [])
        }
        missing_lookup: dict[str, list[str]] = {}
        for item in presentation.get("missing", []):
            missing_lookup.setdefault(str(item["xbrl_concept"]), []).append(
                str(item["period"])
            )
        presentation_rows = [
            {
                **dict(requirement),
                "decision": decision_lookup.get(str(requirement["xbrl_concept"])),
                "missing_periods": sorted(
                    missing_lookup.get(str(requirement["xbrl_concept"]), [])
                ),
            }
            for requirement in inventory.get("requirements", [])
        ]
        return {
            **_base(case, selected),
            "selected_form": case.get("selected_form"),
            "section_totals": statements.get("section_totals", {}),
            "reporting_precision": statements.get("reporting_precision"),
            "rounding_adjustments": statements.get("rounding_adjustments", []),
            "facts": _page(statements.get("facts", []), offset, limit),
            "statutory_presentation": {
                "status": presentation.get("status", "NOT_REVIEWED"),
                "summary": presentation.get("summary"),
                "inventory": {
                    key: value
                    for key, value in inventory.items()
                    if key not in {"requirements", "totals", "formulas"}
                },
                "requirements": _page(presentation_rows, offset, limit),
                "issues": presentation.get("issues", []),
            },
        }
    if selected == "SCHEDULES":
        return {
            **_base(case, selected),
            "schedules": _page(case.get("schedules", []), offset, limit),
            "taxonomy_adapter": case.get("schedule_taxonomy_adapter"),
            "taxonomy_facts": _page(
                case.get("schedule_taxonomy_facts", []), offset, limit
            ),
        }
    if selected == "QUESTIONNAIRE":
        return {
            **_base(case, selected),
            "coverage": case.get("disclosure_coverage"),
            "trigger_decisions": case.get("disclosure_trigger_decisions", []),
            "activation_suggestions": case.get("disclosure_activation_suggestions", []),
            "questions": _page(case.get("questionnaire", []), offset, limit),
        }
    if selected == "NOTES_EDITOR":
        return {
            **_base(case, selected),
            "outline": case.get("note_outline", []),
            "accepted_facts": _page(case.get("canonical_facts", []), offset, limit),
            "narrative_blocks": case.get("narrative_blocks", []),
            "prior_suggestions": case.get("prior_narrative_suggestions", []),
        }
    if selected == "ISSUES_PANEL":
        validation = case.get("validation") or {}
        summary = {key: value for key, value in validation.items() if key != "issues"}
        return {
            **_base(case, selected),
            "validation": summary,
            "prior_xbrl_reconciliation": validation.get("prior_xbrl_reconciliation"),
            "comparative_reconciliation_decisions": case.get(
                "comparative_reconciliation_decisions", []
            ),
            "issues": _page(validation.get("issues", []), offset, limit),
            "review_decisions": case.get("review_decisions", []),
        }
    if selected == "PREVIEW":
        preview = case.get("preview") or {}
        return {
            **_base(case, selected),
            "preview": {
                key: value for key, value in preview.items() if key != "content_base64"
            },
            "xbrl_review": case.get("xbrl_review"),
            "resource_ids": {
                "preview": f"xbrl-preview://{case['case_id']}/{case['revision_id']}",
                "local_validation": (
                    f"xbrl-local-review://{case['case_id']}/{case['revision_id']}"
                ),
            },
        }
    approval = case.get("approval")
    approval_summary = (
        {key: value for key, value in approval.items() if key != "snapshot"}
        if approval
        else None
    )
    return {
        **_base(case, selected),
        "approval": approval_summary,
        "artifacts": case.get("artifacts", []),
        "external_validation": case.get("external_validation"),
        "resource_ids": {
            "workpaper": f"xbrl-workpaper://{case['case_id']}",
            "artifacts": f"xbrl-artifacts://{case['case_id']}",
        },
    }
